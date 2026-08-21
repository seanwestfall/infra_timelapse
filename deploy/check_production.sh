#!/usr/bin/env bash
set -euo pipefail

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_COMMAND="${PYTHON:-python3}"
MANIFEST_TOOL="${REPOSITORY_ROOT}/deploy/cloudflare_manifest.py"
PRODUCTION_ORIGIN="${PRODUCTION_ORIGIN:-$("${PYTHON_COMMAND}" "${MANIFEST_TOOL}" get production.pages_origin)}"
API_ORIGIN="${TIMELAPSE_API_BASE:-$("${PYTHON_COMMAND}" "${MANIFEST_TOOL}" get production.worker_origin)}"
CHECK_DIRECTORY="$(mktemp -d)"
trap 'rm -rf -- "${CHECK_DIRECTORY}"' EXIT

curl --fail --silent --show-error \
  --header "Origin: ${PRODUCTION_ORIGIN}" \
  --dump-header "${CHECK_DIRECTORY}/index.headers" \
  --output "${CHECK_DIRECTORY}/index.json" \
  "${API_ORIGIN}/api/index?production-smoke=${GITHUB_SHA:-local}"

grep -Fqi "access-control-allow-origin: ${PRODUCTION_ORIGIN}" \
  "${CHECK_DIRECTORY}/index.headers"

CAPTURE_PATH="$("${PYTHON_COMMAND}" - "${CHECK_DIRECTORY}/index.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as index_file:
    index = json.load(index_file)
for manifest in index.get("manifests", []):
    for capture in manifest.get("files", []):
        if capture.get("image_url"):
            print(capture["image_url"])
            raise SystemExit(0)
raise SystemExit("Capture index contains no image URL")
PY
)"

curl --fail --silent --show-error \
  --header "Origin: ${PRODUCTION_ORIGIN}" \
  --dump-header "${CHECK_DIRECTORY}/capture.headers" \
  --output "${CHECK_DIRECTORY}/capture.png" \
  "${API_ORIGIN}${CAPTURE_PATH}"

grep -Fqi "access-control-allow-origin: ${PRODUCTION_ORIGIN}" \
  "${CHECK_DIRECTORY}/capture.headers"
"${PYTHON_COMMAND}" - "${CHECK_DIRECTORY}/capture.png" <<'PY'
import sys

with open(sys.argv[1], "rb") as capture_file:
    if capture_file.read(8) != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("Capture response is not a PNG")
PY

echo "Production index CORS and capture delivery are healthy."
