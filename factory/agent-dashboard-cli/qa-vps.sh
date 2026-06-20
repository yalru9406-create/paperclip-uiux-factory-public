#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PUBLIC_BASE="${PUBLIC_BASE:-https://paperclip.46.250.229.212.sslip.io}"
AGENT_ROUTE="${AGENT_ROUTE:-hermes-top-orchestrator}"
BROWSER_QA_ARTIFACT="${BROWSER_QA_ARTIFACT:-}"
TMP_DIR="$(mktemp -d /tmp/paperclip-agent-cli-qa.XXXXXX)"
FAILURES=0
WARNINGS=0

. "$SCRIPT_DIR/qa_vps_lib.sh"
trap cleanup EXIT

section "workspace"
cd "$ROOT_DIR" || exit 2
printf 'root=%s\n' "$ROOT_DIR"
printf 'timestamp=%s\n' "$(date -Is)"
require_file AGENTS.md
require_file agent-dashboard-cli/RUNBOOK.md
require_file agent-dashboard-cli/server.py
require_file agent-dashboard-cli/agent-dashboard-cli.js
require_file agent-dashboard-cli/agent-dashboard-state.js
require_file agent-dashboard-cli/agent-dashboard-dom.js
require_file agent-dashboard-cli/agent-dashboard-terminal.js
require_file agent-dashboard-cli/agent-dashboard-bootstrap.js
require_file agent-dashboard-cli/qa_vps_lib.sh
require_file agent-dashboard-cli/nginx-location.conf

run_required "python_compile" python3 -m py_compile agent-dashboard-cli/*.py
run_required "bash_syntax" bash -n agent-dashboard-cli/qa-vps.sh agent-dashboard-cli/qa_vps_lib.sh
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
if grep -Fq "location ^~ /yalru-terminal/" agent-dashboard-cli/nginx-location.conf; then
  pass "tracked_nginx_snippet_has_terminal_fallback"
else
  fail "tracked_nginx_snippet_has_terminal_fallback"
fi
if grep -Fq "location = /yalru-terminal" agent-dashboard-cli/nginx-location.conf; then
  pass "tracked_nginx_snippet_has_terminal_exact_guard"
else
  fail "tracked_nginx_snippet_has_terminal_exact_guard"
fi
enabled_backup_count="$(find /etc/nginx/sites-enabled -maxdepth 1 -name '*.bak-*' | wc -l | tr -d ' ')"
printf 'sites_enabled_backup_count=%s\n' "$enabled_backup_count"
if [ "$enabled_backup_count" = "0" ]; then
  pass "sites_enabled_has_no_active_backups"
else
  fail "sites_enabled_has_no_active_backups count=$enabled_backup_count"
fi
if [ -r "$NGINX_SITE" ]; then
  https_start="$(grep -n 'listen 443' "$NGINX_SITE" | head -n 1 | cut -d: -f1 || true)"
  panel_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location = \/yalru-agent-cli\/panel.js \{/ {print NR; exit}' "$NGINX_SITE")"
  proxy_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \/yalru-agent-cli\/ \{/ {print NR; exit}' "$NGINX_SITE")"
  root_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \/ \{/ {print NR; exit}' "$NGINX_SITE")"
  terminal_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \/yalru-terminal\/lazycodex\/ \{/ {print NR; exit}' "$NGINX_SITE")"
  terminal_exact_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location = \/yalru-terminal \{/ {print NR; exit}' "$NGINX_SITE")"
  terminal_fallback_line="$(awk -v start="${https_start:-0}" 'NR>start && /^    location \^~ \/yalru-terminal\/ \{/ {print NR; exit}' "$NGINX_SITE")"
  printf 'https_server_start_line=%s\npanel_location_line=%s\nproxy_location_line=%s\nterminal_lazycodex_location_line=%s\nterminal_exact_location_line=%s\nterminal_fallback_location_line=%s\nhttps_root_location_line=%s\n' "${https_start:-missing}" "${panel_line:-missing}" "${proxy_line:-missing}" "${terminal_line:-missing}" "${terminal_exact_line:-missing}" "${terminal_fallback_line:-missing}" "${root_line:-missing}"
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
  if [ -n "${terminal_exact_line:-}" ] && [ -n "${root_line:-}" ] && [ "$terminal_exact_line" -lt "$root_line" ]; then
    pass "terminal_exact_guard_before_https_root"
  else
    fail "terminal_exact_guard_before_https_root"
  fi
  if [ -n "${terminal_fallback_line:-}" ] && [ -n "${root_line:-}" ] && [ "$terminal_fallback_line" -lt "$root_line" ]; then
    pass "terminal_fallback_before_https_root"
  else
    fail "terminal_fallback_before_https_root"
  fi
else
  fail "nginx_site_readable"
fi

section "route_checks"
curl_capture sidecar_loopback_health "http://127.0.0.1:4192/health" 200 "application/json"
curl_capture local_nginx_health "https://127.0.0.1/yalru-agent-cli/health" 200 "application/json"
curl_capture public_health "$PUBLIC_BASE/yalru-agent-cli/health" 200 "application/json"
curl_capture public_context "$PUBLIC_BASE/yalru-agent-cli/api/context?agentRoute=$AGENT_ROUTE" 200 "application/json"
curl_capture public_status "$PUBLIC_BASE/yalru-agent-cli/api/public-status" 200 "application/json"
curl_capture public_panel_js "$PUBLIC_BASE/yalru-agent-cli/panel.js" 200 "javascript"
curl_capture public_panel_state_js "$PUBLIC_BASE/yalru-agent-cli/agent-dashboard-state.js" 200 "javascript"
curl_capture public_panel_dom_js "$PUBLIC_BASE/yalru-agent-cli/agent-dashboard-dom.js" 200 "javascript"
curl_capture public_panel_terminal_js "$PUBLIC_BASE/yalru-agent-cli/agent-dashboard-terminal.js" 200 "javascript"
curl_capture public_panel_bootstrap_js "$PUBLIC_BASE/yalru-agent-cli/agent-dashboard-bootstrap.js" 200 "javascript"
curl_capture public_root "$PUBLIC_BASE/" 200 "text/html"
curl_capture public_dashboard "$PUBLIC_BASE/YAL/agents/$AGENT_ROUTE/dashboard" 200 "text/html"
curl_capture public_terminal_bare_guard "$PUBLIC_BASE/yalru-terminal" 403 "text/html"
curl_capture public_terminal_lazycodex_private_guard "$PUBLIC_BASE/yalru-terminal/lazycodex/" 403 "text/html"
curl_capture public_terminal_lazycodex_full_key_guard "$PUBLIC_BASE/yalru-terminal/lazycodex-gpt-lane/" 403 "text/html"
curl_capture public_terminal_hermes_full_key_guard "$PUBLIC_BASE/yalru-terminal/hermes-top-orchestrator/" 403 "text/html"
curl_capture yalru_ui "$PUBLIC_BASE/yalru/" 200 "text/html"

section "private_endpoint_guards"
terminal_output_code="$(curl -ksS --max-time 15 -o "$TMP_DIR/terminal_output_private_guard.body" -w '%{http_code}' "$PUBLIC_BASE/yalru-agent-cli/api/terminal/output?agentRoute=$AGENT_ROUTE" 2>"$TMP_DIR/terminal_output_private_guard.err")"
printf 'terminal_output_private_guard code=%s\n' "$terminal_output_code"
if [ "$terminal_output_code" = "403" ]; then
  pass "terminal_output_private_guard status=403"
else
  fail "terminal_output_private_guard status=$terminal_output_code expected=403"
fi

spoofed_terminal_output_code="$(curl -ksS --max-time 15 -H 'X-Forwarded-For: 127.0.0.1' -o "$TMP_DIR/spoofed_terminal_output_private_guard.body" -w '%{http_code}' "$PUBLIC_BASE/yalru-agent-cli/api/terminal/output?agentRoute=$AGENT_ROUTE" 2>"$TMP_DIR/spoofed_terminal_output_private_guard.err")"
printf 'spoofed_terminal_output_private_guard code=%s\n' "$spoofed_terminal_output_code"
if [ "$spoofed_terminal_output_code" = "403" ]; then
  pass "spoofed_terminal_output_private_guard status=403"
else
  fail "spoofed_terminal_output_private_guard status=$spoofed_terminal_output_code expected=403"
fi

spoofed_terminal_input_code="$(curl -ksS --max-time 15 -H 'X-Forwarded-For: 127.0.0.1' -H 'Content-Type: application/json' -X POST -d "{\"agentRoute\":\"$AGENT_ROUTE\",\"input\":\"pwd\"}" -o "$TMP_DIR/spoofed_terminal_input_private_guard.body" -w '%{http_code}' "$PUBLIC_BASE/yalru-agent-cli/api/terminal/input" 2>"$TMP_DIR/spoofed_terminal_input_private_guard.err")"
printf 'spoofed_terminal_input_private_guard code=%s\n' "$spoofed_terminal_input_code"
if [ "$spoofed_terminal_input_code" = "403" ]; then
  pass "spoofed_terminal_input_private_guard status=403"
else
  fail "spoofed_terminal_input_private_guard status=$spoofed_terminal_input_code expected=403"
fi

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
assert_body_json_ok public_status_ok_true "$TMP_DIR/public_status.body"
assert_body_contains context_has_hermes "$TMP_DIR/public_context.body" "Hermes"
assert_body_contains context_has_public_ops_status "$TMP_DIR/public_context.body" "\"opsStatus\""
assert_body_contains context_has_tan_mutation_guard "$TMP_DIR/public_context.body" "\"tanMutation\": \"not_performed\""
assert_body_contains context_has_private_terminal_guard "$TMP_DIR/public_context.body" "\"privateTerminalEndpoints\": \"not_exposed_public\""
assert_body_contains public_status_has_live_mutation_guard "$TMP_DIR/public_status.body" "\"liveMutationAllowed\": false"
assert_body_contains public_status_has_private_controls_guard "$TMP_DIR/public_status.body" "\"privateControls\""
assert_body_contains public_status_has_live_approval_state "$TMP_DIR/public_status.body" "\"liveApprovalState\""
if grep -Fq '"commands"' "$TMP_DIR/public_context.body"; then
  fail "public_context_no_command_preview"
else
  pass "public_context_no_command_preview"
fi
assert_body_contains root_has_script_tag "$TMP_DIR/public_root.body" "/yalru-agent-cli/panel.js"
assert_body_contains dashboard_has_script_tag "$TMP_DIR/public_dashboard.body" "/yalru-agent-cli/panel.js"
assert_body_contains panel_loader_references_state_chunk "$TMP_DIR/public_panel_js.body" "agent-dashboard-state.js"
assert_body_contains panel_loader_references_dom_chunk "$TMP_DIR/public_panel_js.body" "agent-dashboard-dom.js"
assert_body_contains panel_loader_references_terminal_chunk "$TMP_DIR/public_panel_js.body" "agent-dashboard-terminal.js"
assert_body_contains panel_loader_references_bootstrap_chunk "$TMP_DIR/public_panel_js.body" "agent-dashboard-bootstrap.js"
assert_body_contains panel_state_has_agent_terminal_literal "$TMP_DIR/public_panel_state_js.body" "Agent Terminal"
assert_body_contains panel_state_has_public_ops_status_literal "$TMP_DIR/public_panel_state_js.body" "Public ops status"
assert_body_contains panel_state_has_c5_lock_literal "$TMP_DIR/public_panel_state_js.body" "Live mutation locked / C5"
assert_body_contains panel_dom_has_placement_logic "$TMP_DIR/public_panel_dom_js.body" "placePanel"
assert_body_contains panel_terminal_has_private_endpoint_calls "$TMP_DIR/public_panel_terminal_js.body" "/api/terminal/start"
assert_body_contains panel_bootstrap_has_observer "$TMP_DIR/public_panel_bootstrap_js.body" "MutationObserver"

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
printf 'browser_qa_not_run_by_qa_vps=true\n'
if [ -n "$BROWSER_QA_ARTIFACT" ]; then
  printf 'browser_qa_artifact=%s\n' "$BROWSER_QA_ARTIFACT"
  if [ -f "$BROWSER_QA_ARTIFACT" ]; then
    pass "browser_qa_artifact_exists"
  else
    fail "browser_qa_artifact_missing:$BROWSER_QA_ARTIFACT"
  fi
else
  printf 'browser_qa_artifact=external_browser_qa_required\n'
fi
printf 'manual_checklist=open %s/YAL/agents/%s/dashboard ; click CLI ; confirm #yalru-agent-cli-panel, Discord chat surfaces, no private terminal/control sections, console errors 0\n' "$PUBLIC_BASE" "$AGENT_ROUTE"

section "summary"
printf 'warnings=%s\n' "$WARNINGS"
printf 'failures=%s\n' "$FAILURES"
if [ "$FAILURES" -eq 0 ]; then
  printf 'overall=PASS\n'
  exit 0
fi
printf 'overall=FAIL\n'
exit 1
