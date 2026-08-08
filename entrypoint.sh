#!/usr/bin/env sh
set -eu

case "${APP_MODE:-job}" in
  job)
    exec python cloud_run_job.py
    ;;
  api)
    exec gunicorn \
      --bind "0.0.0.0:${PORT:-8080}" \
      --workers "${WEB_CONCURRENCY:-2}" \
      --threads "${WEB_THREADS:-4}" \
      --timeout 120 \
      capture_api:app
    ;;
  *)
    echo "APP_MODE must be job or api" >&2
    exit 64
    ;;
esac
