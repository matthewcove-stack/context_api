#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
}

require_cmd flock

PUBLISH_LOCK_FILE="${BRIEF_PUBLISH_LOCK_FILE:-/tmp/lambic-ai-brief-publish.lock}"
if [[ ! -e "${PUBLISH_LOCK_FILE}" ]]; then
  (umask 022; : >"${PUBLISH_LOCK_FILE}")
fi
exec 9<"${PUBLISH_LOCK_FILE}"
if ! flock -n 9; then
  echo "Another Lambic AI Brief publish is already running; skipping." >&2
  exit 0
fi
export BRIEF_PUBLISH_LOCK_HELD=true

# Daily mode covers the period since the last published issue. Missing calendar
# dates are intentional when the evidence or writing does not pass review.
# Never lower item/source thresholds or retry every date to fill the archive.
# Provider failures propagate (75 transient, 78 account-blocked) unchanged.
exec "${SCRIPT_DIR}/run_lambic_brief_publish.sh" \
  --mode daily --allow-skipped-weak
