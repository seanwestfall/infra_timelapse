#!/usr/bin/env bash
set -euo pipefail

PRODUCTION_ORIGIN="${PRODUCTION_ORIGIN:-https://infratimelapse.pages.dev}"
API_ORIGIN="${TIMELAPSE_API_BASE:-https://if-api.acceler.workers.dev}"
CHECK_DIRECTORY="$(mktemp -d)"
trap 'rm -rf -- "${CHECK_DIRECTORY}"' EXIT

curl --fail --silent --show-error \
  --header "Origin: ${PRODUCTION_ORIGIN}" \
  --dump-header "${CHECK_DIRECTORY}/index.headers" \
  --output "${CHECK_DIRECTORY}/index.json" \
  "${API_ORIGIN}/api/index?production-smoke=${GITHUB_SHA:-local}"

grep -Fqi "access-control-allow-origin: ${PRODUCTION_ORIGIN}" \
  "${CHECK_DIRECTORY}/index.headers"

CAPTURE_PATH="$(python3 - "${CHECK_DIRECTORY}/index.json" <<'PY'
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
  --output "${CHECK_DIRECTORY}/capture.png" \
  "${API_ORIGIN}${CAPTURE_PATH}"

test -s "${CHECK_DIRECTORY}/capture.png"
echo "Production index CORS and capture delivery are healthy."
