#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

"${SCRIPT_DIR}/run_lambic_brief_publish.sh" \
  --mode backfill-missing \
  --start-date "${start_date}" \
  --end-date "${end_date}"

for missing_date in "${missing_dates[@]}"; do
  if [[ -f "${digest_dir}/${missing_date}.json" ]]; then
    continue
  fi
  DAILY_DIGEST_MIN_ITEMS="${DAILY_DIGEST_BACKFILL_MIN_ITEMS:-1}" \
  DAILY_DIGEST_BACKFILL_MIN_SOURCE_COUNT="${DAILY_DIGEST_BACKFILL_MIN_SOURCE_COUNT:-1}" \
  DAILY_DIGEST_BACKFILL_FALLBACK_LOOKBACK_DAYS="${DAILY_DIGEST_BACKFILL_FALLBACK_LOOKBACK_DAYS:-3}" \
  "${SCRIPT_DIR}/run_lambic_brief_publish.sh" \
    --mode backfill-range \
    --start-date "${missing_date}" \
    --end-date "${missing_date}"
done
