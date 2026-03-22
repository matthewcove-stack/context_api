#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BRAIN_OS_ENV_FILE="${BRAIN_OS_ENV_FILE:-/srv/lambic/apps/brainos-workspace/brain_os/.env}"
WEBSITE_REPO="${BRIEF_WEBSITE_REPO:-/srv/lambic/apps/lambic-labs-site}"
POSTGRES_CONTAINER_NAME="${POSTGRES_CONTAINER_NAME:-brainos_context_postgres}"
PUBLISH_VENV_DIR="${PUBLISH_VENV_DIR:-${REPO_ROOT}/.venv_publish}"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

if [[ ! -f "${BRAIN_OS_ENV_FILE}" ]]; then
  echo "Missing BrainOS env file: ${BRAIN_OS_ENV_FILE}" >&2
  exit 1
fi

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Missing required command: ${cmd}" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd git
require_cmd npm
require_cmd "${PYTHON_BIN}"

set -a
# shellcheck disable=SC1090
source "${BRAIN_OS_ENV_FILE}"
set +a

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY is missing from ${BRAIN_OS_ENV_FILE}" >&2
  exit 1
fi

if [[ -z "${CONTEXT_API_BEARER_TOKEN:-}" ]]; then
  echo "CONTEXT_API_BEARER_TOKEN is missing from ${BRAIN_OS_ENV_FILE}" >&2
  exit 1
fi

POSTGRES_HOST_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "${POSTGRES_CONTAINER_NAME}" 2>/dev/null || true)"
if [[ -z "${POSTGRES_HOST_IP}" ]]; then
  echo "Unable to resolve container IP for ${POSTGRES_CONTAINER_NAME}" >&2
  exit 1
fi

if [[ ! -d "${WEBSITE_REPO}/.git" ]]; then
  echo "Website repo is not a git repository: ${WEBSITE_REPO}" >&2
  exit 1
fi

WEB_APP_DIR="${WEBSITE_REPO}/apps/web"
if [[ ! -f "${WEB_APP_DIR}/package.json" ]]; then
  echo "Website web app directory is missing package.json: ${WEB_APP_DIR}" >&2
  exit 1
fi

if [[ ! -x "${PUBLISH_VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${PUBLISH_VENV_DIR}"
fi

if ! "${PUBLISH_VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1; then
  rm -rf "${PUBLISH_VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${PUBLISH_VENV_DIR}"
fi

if ! "${PUBLISH_VENV_DIR}/bin/python" -c "import sqlalchemy" >/dev/null 2>&1; then
  "${PUBLISH_VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${PUBLISH_VENV_DIR}/bin/python" -m pip install -r "${REPO_ROOT}/requirements.txt"
fi

if [[ ! -d "${WEB_APP_DIR}/node_modules" || "${WEB_APP_DIR}/package-lock.json" -nt "${WEB_APP_DIR}/node_modules" ]]; then
  (
    cd "${WEB_APP_DIR}"
    npm ci
  )
fi

export DATABASE_URL="postgresql+psycopg://context:context@${POSTGRES_HOST_IP}:5432/context"
export CONTEXT_API_TOKEN="${CONTEXT_API_BEARER_TOKEN}"
export BRIEF_PUBLISH_ENV="prod"
export BRIEF_WEBSITE_REPO="${WEBSITE_REPO}"
export DAILY_DIGEST_GIT_REMOTE="${DAILY_DIGEST_GIT_REMOTE:-origin}"
export DAILY_DIGEST_GIT_BRANCH="${DAILY_DIGEST_GIT_BRANCH:-main}"
export DAILY_DIGEST_TOPIC_KEY="${DAILY_DIGEST_TOPIC_KEY:-ai_research}"

cd "${REPO_ROOT}"
"${PUBLISH_VENV_DIR}/bin/python" scripts/publish_lambic_ai_brief.py "$@"
