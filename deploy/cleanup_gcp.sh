#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-west1}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-infra-timelapse}"
JOB_NAME="${JOB_NAME:-infra-timelapse-capture}"
INDEX_SERVICE_NAME="${INDEX_SERVICE_NAME:-infra-timelapse-index}"
SCHEDULER_NAME="${SCHEDULER_NAME:-infra-timelapse-biweekly}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-infra-timelapse-job}"
INDEX_SA_NAME="${INDEX_SA_NAME:-infra-timelapse-index}"
SCHEDULER_SA_NAME="${SCHEDULER_SA_NAME:-infra-timelapse-scheduler}"

cat <<EOF
This removes the Scheduler job, Cloud Run job and read service, Artifact
Registry repository, and the three dedicated service accounts from project
${PROJECT_ID}.

It deliberately preserves the image bucket and Maps API secret so historical
captures and credentials are not deleted accidentally.
EOF

read -r -p "Type 'cleanup' to continue: " confirmation
if [[ "${confirmation}" != "cleanup" ]]; then
  echo "No changes made."
  exit 0
fi

gcloud scheduler jobs delete "${SCHEDULER_NAME}" \
  --location "${REGION}" --project "${PROJECT_ID}" --quiet || true
gcloud run jobs delete "${JOB_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" --quiet || true
gcloud run services delete "${INDEX_SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" --quiet || true
gcloud artifacts repositories delete "${ARTIFACT_REPOSITORY}" \
  --location "${REGION}" --project "${PROJECT_ID}" --quiet || true
gcloud iam service-accounts delete \
  "${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project "${PROJECT_ID}" --quiet || true
gcloud iam service-accounts delete \
  "${INDEX_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project "${PROJECT_ID}" --quiet || true
gcloud iam service-accounts delete \
  "${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project "${PROJECT_ID}" --quiet || true

echo "Compute resources removed. Storage bucket and secret were preserved."
