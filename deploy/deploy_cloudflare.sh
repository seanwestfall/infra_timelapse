#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAGES_MODE="auto"
WORKER_MODE="production"
BASE_REF=""
HEAD_REF="HEAD"
PAGES_PROJECT="${CLOUDFLARE_PAGES_PROJECT:-infratimelapse}"
PAGES_BRANCH="${CLOUDFLARE_PAGES_BRANCH:-main}"

usage() {
  cat <<'EOF'
Usage: deploy/deploy_cloudflare.sh [options]

Options:
  --pages auto|always|never   Deploy Pages when changed, always, or never.
  --worker production|preview|never
                              Promote the Worker, upload a preview, or skip it.
  --base-ref REF              Base Git revision for --pages auto.
  --head-ref REF              Head Git revision for --pages auto (default: HEAD).
  --help                      Show this help.

Environment:
  CLOUDFLARE_PAGES_PROJECT    Pages project name (default: infratimelapse).
  CLOUDFLARE_PAGES_BRANCH     Pages deployment branch (default: main).
  TIMELAPSE_API_BASE          Optional HTTPS Worker origin for separate-host mode.
  CLOUDFLARE_WORKER_ALIAS     Optional preview alias (defaults to Pages branch).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pages)
      PAGES_MODE="${2:-}"
      shift 2
      ;;
    --worker)
      WORKER_MODE="${2:-}"
      shift 2
      ;;
    --base-ref)
      BASE_REF="${2:-}"
      shift 2
      ;;
    --head-ref)
      HEAD_REF="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

if [[ ! " ${PAGES_MODE} " =~ ^\ (auto|always|never)\ $ ]]; then
  echo "--pages must be auto, always, or never" >&2
  exit 64
fi
if [[ ! " ${WORKER_MODE} " =~ ^\ (production|preview|never)\ $ ]]; then
  echo "--worker must be production, preview, or never" >&2
  exit 64
fi

cd "${REPOSITORY_ROOT}"

if [[ "${WORKER_MODE}" != "never" ]]; then
  if grep -q "replace-with-cloud-run-service" web/worker/wrangler.jsonc; then
    echo "Set API_BASE_URL in web/worker/wrangler.jsonc before deploying" >&2
    exit 78
  fi
  if [[ "${WORKER_MODE}" == "production" ]]; then
    echo "Deploying standalone Worker to production"
    npx --no-install wrangler deploy --config web/worker/wrangler.jsonc
  else
    worker_alias="${CLOUDFLARE_WORKER_ALIAS:-${PAGES_BRANCH}}"
    worker_alias="$(printf '%s' "${worker_alias}" | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/^[^a-z]+/preview-/')"
    worker_alias="${worker_alias:0:40}"
    if [[ -z "${worker_alias}" ]]; then
      worker_alias="preview"
    fi
    worker_log="$(mktemp)"
    trap 'rm -f "${worker_log}"' EXIT
    echo "Uploading standalone Worker preview (${worker_alias})"
    npx --no-install wrangler versions upload \
      --config web/worker/wrangler.jsonc \
      --preview-alias "${worker_alias}" | tee "${worker_log}"
    preview_api_base="$(grep -Eo 'https://[a-z0-9-]+-if-api\.[a-z0-9.-]+\.workers\.dev' "${worker_log}" | tail -1)"
    if [[ -z "${preview_api_base}" ]]; then
      echo "Wrangler did not return a Worker preview URL" >&2
      exit 70
    fi
    export TIMELAPSE_API_BASE="${preview_api_base}"
    echo "Worker preview: ${TIMELAPSE_API_BASE}"
  fi
else
  echo "Skipping Worker deployment"
fi

deploy_pages=false
case "${PAGES_MODE}" in
  always)
    deploy_pages=true
    ;;
  never)
    ;;
  auto)
    if [[ -z "${BASE_REF}" ]]; then
      if git rev-parse --verify HEAD^ >/dev/null 2>&1; then
        BASE_REF="HEAD^"
      else
        deploy_pages=true
      fi
    fi
    if [[ "${deploy_pages}" == false ]]; then
      if ! git rev-parse --verify "${BASE_REF}^{commit}" >/dev/null 2>&1; then
        echo "Base revision is unavailable; deploying Pages safely"
        deploy_pages=true
      elif ! git diff --quiet "${BASE_REF}" "${HEAD_REF}" -- \
        web/public/ \
        infra_timelapse_ports_corridors.json \
        deploy/build_web.sh \
        deploy/render_web.py \
        wrangler.toml; then
        deploy_pages=true
      fi
    fi
    ;;
esac

if [[ "${deploy_pages}" == true ]]; then
  echo "Building and deploying Cloudflare Pages"
  bash deploy/build_web.sh
  npx --no-install wrangler pages deploy dist \
    --project-name "${PAGES_PROJECT}" \
    --branch "${PAGES_BRANCH}"
else
  echo "Static frontend inputs are unchanged; skipping Pages deployment"
fi
