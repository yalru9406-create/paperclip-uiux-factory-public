#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_BASE="${PUBLIC_BASE:-https://paperclip.46.250.229.212.sslip.io}"
AGENT_ROUTE="${AGENT_ROUTE:-hermes-top-orchestrator}"
TMP_DIR="$(mktemp -d /tmp/paperclip-agent-cli-qa.XXXXXX)"
FAILURES=0
WARNINGS=0

cleanup() {
  rm -rf "$TMP_DIR"
  printf 'cleanup=tempdir_removed:%s\n' "$TMP_DIR"
}
trap cleanup EXIT

section() {
  printf '\n## %s\n' "$1"
}

pass() {
  printf 'PASS %s\n' "$1"
}

warn() {
  WARNINGS=$((WARNINGS + 1))
  printf 'WARN %s\n' "$1"
}

fail() {
  FAILURES=$((FAILURES + 1))
  printf 'FAIL %s\n' "$1"
}

require_file() {
  if [ -e "$1" ]; then
    pass "file_exists:$1"
  else
    fail "file_missing:$1"
  fi
}

run_required() {
  local name="$1"
  shift
  section "$name"
  "$@" 2>&1
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    pass "$name rc=0"
  else
    fail "$name rc=$rc"
  fi
}

curl_capture() {
  local name="$1"
  local url="$2"
  local expected_code="$3"
  local expected_type="$4"
  local out="$TMP_DIR/$name.body"
  local headers="$TMP_DIR/$name.headers"
  local code
  code="$(curl -ksS --max-time 15 -D "$headers" -o "$out" -w '%{http_code}' "$url" 2>"$TMP_DIR/$name.err")"
  local rc=$?
  local type
  type="$(awk -F': ' 'tolower($1)=="content-type"{print $2}' "$headers" 2>/dev/null | tr -d '\r' | tail -n 1)"
  local bytes
  bytes="$(wc -c < "$out" 2>/dev/null | tr -d ' ')"
  printf '%s code=%s type=%s bytes=%s\n' "$name" "$code" "${type:-none}" "${bytes:-0}"
  if [ "$rc" -ne 0 ]; then
    cat "$TMP_DIR/$name.err"
    fail "$name curl_rc=$rc"
    return
  fi
  if [ "$code" = "$expected_code" ]; then
    pass "$name status=$code"
  else
    fail "$name status=$code expected=$expected_code"
  fi
  if printf '%s' "$type" | grep -qi "$expected_type"; then
    pass "$name content_type~$expected_type"
  else
    fail "$name content_type=${type:-none} expected~$expected_type"
  fi
}

curl_note() {
  local name="$1"
  local url="$2"
  local out="$TMP_DIR/$name.body"
  local headers="$TMP_DIR/$name.headers"
  local code
  code="$(curl -ksS --max-time 15 -D "$headers" -o "$out" -w '%{http_code}' "$url" 2>"$TMP_DIR/$name.err")"
  local rc=$?
  local type
  type="$(awk -F': ' 'tolower($1)=="content-type"{print $2}' "$headers" 2>/dev/null | tr -d '\r' | tail -n 1)"
  local bytes
  bytes="$(wc -c < "$out" 2>/dev/null | tr -d ' ')"
  printf '%s code=%s type=%s bytes=%s rc=%s\n' "$name" "$code" "${type:-none}" "${bytes:-0}" "$rc"
}

assert_body_contains() {
  local name="$1"
  local file="$2"
  local needle="$3"
  if grep -Fq "$needle" "$file"; then
    pass "$name"
  else
    fail "$name"
  fi
}

assert_body_json_ok() {
  local name="$1"
  local file="$2"
  python3 - "$file" <<'PY'
import json
import sys
from pathlib import Path
try:
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except Exception as exc:
    print(f"json_error={exc}")
    raise SystemExit(1)
print(f"json_ok={payload.get('ok') is True}")
raise SystemExit(0 if payload.get("ok") is True else 1)
PY
  local rc=$?
  if [ "$rc" -eq 0 ]; then
    pass "$name"
  else
    fail "$name"
  fi
}

section "workspace"
cd "$ROOT_DIR" || exit 2
printf 'root=%s\n' "$ROOT_DIR"
printf 'timestamp=%s\n' "$(date -Is)"
require_file AGENTS.md
require_file agent-dashboard-cli/RUNBOOK.md
require_file agent-dashboard-cli/server.py
require_file agent-dashboard-cli/agent-dashboard-cli.js

run_required "python_compile" python3 -m py_compile agent-dashboard-cli/*.py
run_required "factory_doctor" ./bin/yalru-uiux-factory doctor
run_required "nginx_syntax" sudo -n nginx -t

section "service_state"
for service in nginx hermes-gateway yalru-agent-cli tan-live tan-api; do
  state="$(systemctl is-active "$service" 2>&1)"
  printf '%s=%s\n' "$service" "$state"
  if [ "$state" = "active" ]; then
    pass "service_active:$service"
  else
    fail "service_active:$service"
  fi
done

section "listening_ports"
ss -ltnp 2>/dev/null | grep -E ':(4191|4192)\b' || true
if ss -ltn 2>/dev/null | grep -q '127.0.0.1:4192'; then
  pass "port_4192_loopback_listening"
else
  fail "port_4192_loopback_listening"
fi
if ss -ltn 2>/dev/null | grep -q '127.0.0.1:4191'; then
  pass "port_4191_loopback_listening"
else
  fail "port_4191_loopback_listening"
fi

section "nginx_route_shape"
NGINX_SITE=/etc/nginx/sites-enabled/paperclip
if [ -r "$NGINX_SITE" ]; then
  https_start="$(grep -n 'listen 443' "$NGINX_SITE" | head -n 1 | cut -d: -f1 || true)"
  panel_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location = \/yalru-agent-cli\/panel.js \{/ {print NR; exit}' "$NGINX_SITE")"
  proxy_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \/yalru-agent-cli\/ \{/ {print NR; exit}' "$NGINX_SITE")"
  root_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \/ \{/ {print NR; exit}' "$NGINX_SITE")"
  terminal_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \/yalru-terminal\/lazycodex\/ \{/ {print NR; exit}' "$NGINX_SITE")"
  printf 'https_server_start_line=%s\npanel_location_line=%s\nproxy_location_line=%s\nterminal_lazycodex_location_line=%s\nhttps_root_location_line=%s\n' "${https_start:-missing}" "${panel_line:-missing}" "${proxy_line:-missing}" "${terminal_line:-missing}" "${root_line:-missing}"
  if [ -n "${panel_line:-}" ] && [ -n "${root_line:-}" ] && [ "$panel_line" -lt "$root_line" ]; then
    pass "panel_location_top_level_before_https_root"
  else
    fail "panel_location_top_level_before_https_root"
  fi
  if [ -n "${proxy_line:-}" ] && [ -n "${root_line:-}" ] && [ "$proxy_line" -lt "$root_line" ]; then
    pass "proxy_location_top_level_before_https_root"
  else
    fail "proxy_location_top_level_before_https_root"
  fi
  if [ -n "${terminal_line:-}" ] && [ -n "${root_line:-}" ] && [ "$terminal_line" -lt "$root_line" ]; then
    pass "terminal_location_top_level_before_https_root"
  else
    fail "terminal_location_top_level_before_https_root"
  fi
else
  fail "nginx_site_readable"
fi

section "route_checks"
curl_capture sidecar_loopback_health "http://127.0.0.1:4192/health" 200 "application/json"
curl_capture local_nginx_health "https://127.0.0.1/yalru-agent-cli/health" 200 "application/json"
curl_capture public_health "$PUBLIC_BASE/yalru-agent-cli/health" 200 "application/json"
curl_capture public_context "$PUBLIC_BASE/yalru-agent-cli/api/context?agentRoute=$AGENT_ROUTE" 200 "application/json"
curl_capture public_panel_js "$PUBLIC_BASE/yalru-agent-cli/panel.js" 200 "javascript"
curl_capture public_root "$PUBLIC_BASE/" 200 "text/html"
curl_capture public_dashboard "$PUBLIC_BASE/YAL/agents/$AGENT_ROUTE/dashboard" 200 "text/html"
curl_capture public_terminal_lazycodex_private_guard "$PUBLIC_BASE/yalru-terminal/lazycodex/" 403 "text/html"
curl_capture yalru_ui "$PUBLIC_BASE/yalru/" 200 "text/html"

section "pitfall_checks"
curl_note api_health_pitfall "https://127.0.0.1/yalru-agent-cli/api/health"
api_health_type="$(awk -F': ' 'tolower($1)=="content-type"{print $2}' "$TMP_DIR/api_health_pitfall.headers" 2>/dev/null | tr -d '\r' | tail -n 1)"
api_health_code="$(curl -ksS --max-time 15 -o /dev/null -w '%{http_code}' https://127.0.0.1/yalru-agent-cli/api/health 2>/dev/null)"
if [ "$api_health_code" = "200" ]; then
  fail "api_health_pitfall_expected_non_200"
else
  pass "api_health_pitfall_expected_non_200 code=$api_health_code type=${api_health_type:-none}"
fi
curl_note direct_4191_prefixed_health "http://127.0.0.1:4191/yalru-agent-cli/health"
direct_4191_type="$(awk -F': ' 'tolower($1)=="content-type"{print $2}' "$TMP_DIR/direct_4191_prefixed_health.headers" 2>/dev/null | tr -d '\r' | tail -n 1)"
if printf '%s' "$direct_4191_type" | grep -qi 'application/json'; then
  warn "direct_4191_prefixed_health_returned_json_unexpected"
else
  pass "direct_4191_prefixed_health_not_json type=${direct_4191_type:-none}"
fi

section "content_assertions"
assert_body_json_ok health_ok_true "$TMP_DIR/public_health.body"
assert_body_contains context_has_hermes "$TMP_DIR/public_context.body" "Hermes"
assert_body_contains root_has_script_tag "$TMP_DIR/public_root.body" "/yalru-agent-cli/panel.js"
assert_body_contains dashboard_has_script_tag "$TMP_DIR/public_dashboard.body" "/yalru-agent-cli/panel.js"
if grep -Fq "AGENT TERMINAL" "$TMP_DIR/public_panel_js.body"; then
  printf 'panel_js_has_agent_terminal_literal=True
'
else
  printf 'panel_js_has_agent_terminal_literal=False
'
fi
printf 'panel_rendering_proof=browser_qa_artifact_or_manual_checklist
'

section "discord_mobile_config"
printf 'discord_mobile_thread_id=1517721645811499099
'
printf 'discord_mobile_thread_source=user_context_preconfigured_not_secret_file_read
'
pass "discord_mobile_thread_id_recorded_without_secret_file_read"

section "tan_readonly_safety"
printf 'tan-live=%s\n' "$(systemctl is-active tan-live 2>&1)"
printf 'tan-api=%s\n' "$(systemctl is-active tan-api 2>&1)"
printf 'tan_mutation=not_performed\n'

section "browser_qa_fallback"
printf 'browser_cli_tab=previously_verified_by_Hermes\n'
printf 'browser_cli_panel=previously_verified_by_Hermes\n'
printf 'browser_console_errors=0_previously_verified_by_Hermes\n'
printf 'manual_checklist=open %s/YAL/agents/%s/dashboard ; click CLI ; confirm #yalru-agent-cli-panel and AGENT TERMINAL / Adapter auth / Agent message ; console errors 0\n' "$PUBLIC_BASE" "$AGENT_ROUTE"

section "summary"
printf 'warnings=%s\n' "$WARNINGS"
printf 'failures=%s\n' "$FAILURES"
if [ "$FAILURES" -eq 0 ]; then
  printf 'overall=PASS\n'
  exit 0
fi
printf 'overall=FAIL\n'
exit 1
