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

start_date="$(date -u -d '8 days ago' +%F)"
end_date="$(date -u -d '1 day ago' +%F)"
website_repo="${BRIEF_WEBSITE_REPO:-/srv/lambic/apps/lambic-labs-site}"
digest_content_dir="${DAILY_DIGEST_WEBSITE_CONTENT_DIR:-apps/web/content/research-digests}"
digest_dir="${website_repo}/${digest_content_dir}"

missing_dates=()
current_date="${start_date}"
while [[ "${current_date}" < "${end_date}" || "${current_date}" == "${end_date}" ]]; do
  if [[ ! -f "${digest_dir}/${current_date}.json" ]]; then
    missing_dates+=("${current_date}")
  fi
  current_date="$(date -u -d "${current_date} +1 day" +%F)"
done

strict_status=0
set +e
"${SCRIPT_DIR}/run_lambic_brief_publish.sh" \
  --mode backfill-missing \
  --start-date "${start_date}" \
  --end-date "${end_date}"
strict_status=$?
set -e

if (( strict_status != 0 )); then
  echo "Strict backfill pass reported missing or weak dates; attempting bounded fallback." >&2
fi

remaining_failures=0
fallback_attempted=0
for missing_date in "${missing_dates[@]}"; do
  if [[ -f "${digest_dir}/${missing_date}.json" ]]; then
    continue
  fi
  fallback_attempted=$((fallback_attempted + 1))
  set +e
  BRIEF_MAINTAIN_RESEARCH_CORPUS=false \
  DAILY_DIGEST_MIN_ITEMS="${DAILY_DIGEST_BACKFILL_MIN_ITEMS:-1}" \
  DAILY_DIGEST_BACKFILL_MIN_SOURCE_COUNT="${DAILY_DIGEST_BACKFILL_MIN_SOURCE_COUNT:-1}" \
  DAILY_DIGEST_BACKFILL_FALLBACK_LOOKBACK_DAYS="${DAILY_DIGEST_BACKFILL_FALLBACK_LOOKBACK_DAYS:-3}" \
  "${SCRIPT_DIR}/run_lambic_brief_publish.sh" \
    --mode backfill-range \
    --start-date "${missing_date}" \
    --end-date "${missing_date}"
  fallback_status=$?
  set -e
  if (( fallback_status != 0 )) || [[ ! -f "${digest_dir}/${missing_date}.json" ]]; then
    remaining_failures=$((remaining_failures + 1))
  fi
done

if (( remaining_failures > 0 )); then
  echo "${remaining_failures} publication date(s) remain unavailable after fallback." >&2
  exit 1
fi
if (( strict_status != 0 && fallback_attempted == 0 )); then
  echo "Strict publication failed before any fallback was applicable." >&2
  exit "${strict_status}"
fi
