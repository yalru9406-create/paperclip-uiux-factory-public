#!/usr/bin/env bash
set -euo pipefail

data_dir="${PAPER_DATA_DIR:-/srv/hermes-os/paper/data}"
output_path="${PAPER_RESEARCH_OUTPUT-}"
send_discord="${PAPER_SEND_DISCORD:-1}"
uv_bin="${PAPER_UV_BIN:-/root/.local/bin/uv}"

if [[ -z "$output_path" || "$(basename -- "$output_path")" != "paper_research_gate_latest.txt" ]]; then
  echo "invalid output path for PAPER_RESEARCH_OUTPUT" >&2
  exit 64
fi

output_dir="$(dirname -- "$output_path")"
mkdir -p -- "$output_dir"
tmp_file="$(mktemp "${output_dir}/paper_research_gate_latest.XXXXXX")"
cleanup() {
  rm -f -- "$tmp_file"
}
trap cleanup EXIT

{
  printf 'generated_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$uv_bin" run paper research-gate --data-dir "$data_dir" --dry-run
} > "$tmp_file"
mv -- "$tmp_file" "$output_path"
trap - EXIT

case "${send_discord,,}" in
  1 | true | yes | on)
    if ! "$uv_bin" run paper research-gate --data-dir "$data_dir" --send-discord; then
      echo "paper auto-research discord send failed after latest file was written" >&2
    fi
    ;;
esac
