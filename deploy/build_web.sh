#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIRECTORY="${REPOSITORY_ROOT}/dist"

if [[ "${OUTPUT_DIRECTORY}" != "${REPOSITORY_ROOT}/dist" ]]; then
  echo "Refusing to clean an unexpected output directory" >&2
  exit 64
fi

rm -rf -- "${OUTPUT_DIRECTORY}"
mkdir -p "${OUTPUT_DIRECTORY}"

"${PYTHON:-python3}" "${REPOSITORY_ROOT}/deploy/render_web.py" \
  "${REPOSITORY_ROOT}/web/public/index.html" \
  "${OUTPUT_DIRECTORY}/index.html"
install -m 0644 "${REPOSITORY_ROOT}/infra_timelapse_ports_corridors.json" \
  "${OUTPUT_DIRECTORY}/infra_timelapse_ports_corridors.json"
install -m 0644 "${REPOSITORY_ROOT}/web/public/dashboard-theme.js" \
  "${OUTPUT_DIRECTORY}/dashboard-theme.js"

echo "Built Cloudflare Pages assets in ${OUTPUT_DIRECTORY}"
