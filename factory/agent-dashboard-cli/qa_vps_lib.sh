#!/usr/bin/env bash

cleanup() {
  rm -rf "$TMP_DIR"
  printf 'cleanup=tempdir_removed:%s\n' "$TMP_DIR"
}

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
except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
