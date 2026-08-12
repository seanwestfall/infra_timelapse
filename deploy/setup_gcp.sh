#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-west1}"
ARTIFACT_REPOSITORY="${ARTIFACT_REPOSITORY:-infra-timelapse}"
IMAGE_NAME="${IMAGE_NAME:-capture}"
JOB_NAME="${JOB_NAME:-infra-timelapse-capture}"
INDEX_SERVICE_NAME="${INDEX_SERVICE_NAME:-infra-timelapse-index}"
SCHEDULER_NAME="${SCHEDULER_NAME:-infra-timelapse-biweekly}"
BUCKET_NAME="${BUCKET_NAME:-${PROJECT_ID}-infra-timelapse-images}"
SECRET_NAME="${SECRET_NAME:-google-maps-api-key}"
ORIGIN_SECRET_NAME="${ORIGIN_SECRET_NAME:-infra-timelapse-origin-token}"
RUNTIME_SA_NAME="${RUNTIME_SA_NAME:-infra-timelapse-job}"
INDEX_SA_NAME="${INDEX_SA_NAME:-infra-timelapse-index}"
SCHEDULER_SA_NAME="${SCHEDULER_SA_NAME:-infra-timelapse-scheduler}"
SCHEDULE="${SCHEDULE:-0 3 * * *}"
TIME_ZONE="${TIME_ZONE:-Pacific/Honolulu}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "No Google Cloud project is selected."
  echo "Run: gcloud config set project PROJECT_ID"
  exit 1
fi

PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
INDEX_SA="${INDEX_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="${SCHEDULER_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}/${IMAGE_NAME}:latest"
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB_NAME}:run"

cat <<EOF
Infra Timelapse deployment plan

Project:             ${PROJECT_ID} (${PROJECT_NUMBER})
Region:              ${REGION}
Artifact repository: ${ARTIFACT_REPOSITORY}
Container image:     ${IMAGE_URI}
Storage bucket:      gs://${BUCKET_NAME}
Secret:              ${SECRET_NAME}
Origin auth secret:  ${ORIGIN_SECRET_NAME}
Cloud Run job:       ${JOB_NAME}
Capture read service: ${INDEX_SERVICE_NAME}
Scheduler job:       ${SCHEDULER_NAME}
Schedule:            ${SCHEDULE}
Time zone:           ${TIME_ZONE}
Runtime identity:    ${RUNTIME_SA}
Read identity:       ${INDEX_SA}
Scheduler identity:  ${SCHEDULER_SA}

This will enable Google Cloud APIs, create or update resources, and add
the minimum IAM bindings described above. Existing unrelated resources are
not modified.
EOF

read -r -p "Apply this plan? Type 'deploy' to continue: " confirmation
if [[ "${confirmation}" != "deploy" ]]; then
  echo "No changes made."
  exit 0
fi

gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  iam.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  --project "${PROJECT_ID}"

if ! gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" \
  --location "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
    --repository-format docker \
    --location "${REGION}" \
    --description "Infra Timelapse container images" \
    --project "${PROJECT_ID}"
fi

if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" \
  --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET_NAME}" \
    --location "${REGION}" \
    --uniform-bucket-level-access \
    --public-access-prevention \
    --project "${PROJECT_ID}"
fi

gcloud storage buckets update "gs://${BUCKET_NAME}" \
  --uniform-bucket-level-access \
  --public-access-prevention \
  --project "${PROJECT_ID}"

for service_account_name in \
  "${RUNTIME_SA_NAME}" "${INDEX_SA_NAME}" "${SCHEDULER_SA_NAME}"; do
  if ! gcloud iam service-accounts describe \
    "${service_account_name}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --project "${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${service_account_name}" \
      --project "${PROJECT_ID}" \
      --display-name "${service_account_name}"
  fi
done

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role roles/storage.objectUser \
  --project "${PROJECT_ID}"

gcloud storage buckets add-iam-policy-binding "gs://${BUCKET_NAME}" \
  --member "serviceAccount:${INDEX_SA}" \
  --role roles/storage.objectViewer \
  --project "${PROJECT_ID}"

if ! gcloud secrets describe "${SECRET_NAME}" \
  --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" \
    --replication-policy automatic \
    --project "${PROJECT_ID}"
fi

if ! gcloud secrets describe "${ORIGIN_SECRET_NAME}" \
  --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${ORIGIN_SECRET_NAME}" \
    --replication-policy automatic \
    --project "${PROJECT_ID}"
fi

if ! gcloud secrets versions list "${ORIGIN_SECRET_NAME}" \
  --project "${PROJECT_ID}" --filter='state=ENABLED' \
  --format='value(name)' --limit=1 | grep -q .; then
  read -r -s -p "Worker-to-origin token (input hidden): " origin_auth_token
  echo
  if [[ -z "${origin_auth_token}" ]]; then
    echo "The origin token cannot be empty. No secret version was added."
    exit 1
  fi
  printf '%s' "${origin_auth_token}" | \
    gcloud secrets versions add "${ORIGIN_SECRET_NAME}" \
      --data-file=- --project "${PROJECT_ID}"
  unset origin_auth_token
fi

if ! gcloud secrets versions list "${SECRET_NAME}" \
  --project "${PROJECT_ID}" --filter='state=ENABLED' \
  --format='value(name)' --limit=1 | grep -q .; then
  read -r -s -p "Google Maps API key (input hidden): " maps_api_key
  echo
  if [[ -z "${maps_api_key}" ]]; then
    echo "The API key cannot be empty. No secret version was added."
    exit 1
  fi
  printf '%s' "${maps_api_key}" | gcloud secrets versions add "${SECRET_NAME}" \
    --data-file=- --project "${PROJECT_ID}"
  unset maps_api_key
fi

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --member "serviceAccount:${RUNTIME_SA}" \
  --role roles/secretmanager.secretAccessor \
  --project "${PROJECT_ID}"

gcloud secrets add-iam-policy-binding "${ORIGIN_SECRET_NAME}" \
  --member "serviceAccount:${INDEX_SA}" \
  --role roles/secretmanager.secretAccessor \
  --project "${PROJECT_ID}"

gcloud builds submit \
  --tag "${IMAGE_URI}" \
  --project "${PROJECT_ID}" .

gcloud run jobs deploy "${JOB_NAME}" \
  --image "${IMAGE_URI}" \
  --region "${REGION}" \
  --service-account "${RUNTIME_SA}" \
  --set-env-vars "APP_MODE=job,GCS_BUCKET=${BUCKET_NAME},CAPTURE_SCOPE=all" \
  --set-secrets "GOOGLE_MAPS_API_KEY=${SECRET_NAME}:latest" \
  --tasks 1 \
  --max-retries 2 \
  --task-timeout 30m \
  --memory 512Mi \
  --cpu 1 \
  --project "${PROJECT_ID}"

gcloud run deploy "${INDEX_SERVICE_NAME}" \
  --image "${IMAGE_URI}" \
  --region "${REGION}" \
  --service-account "${INDEX_SA}" \
  --set-env-vars "APP_MODE=api,GCS_BUCKET=${BUCKET_NAME}" \
  --set-secrets "ORIGIN_AUTH_TOKEN=${ORIGIN_SECRET_NAME}:latest" \
  --no-invoker-iam-check \
  --memory 512Mi \
  --cpu 1 \
  --concurrency 8 \
  --min 0 \
  --max 2 \
  --project "${PROJECT_ID}"

gcloud run jobs add-iam-policy-binding "${JOB_NAME}" \
  --region "${REGION}" \
  --member "serviceAccount:${SCHEDULER_SA}" \
  --role roles/run.invoker \
  --project "${PROJECT_ID}"

if gcloud scheduler jobs describe "${SCHEDULER_NAME}" \
  --location "${REGION}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_NAME}" \
    --location "${REGION}" \
    --schedule "${SCHEDULE}" \
    --time-zone "${TIME_ZONE}" \
    --uri "${RUN_URI}" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
    --project "${PROJECT_ID}"
else
  gcloud scheduler jobs create http "${SCHEDULER_NAME}" \
    --location "${REGION}" \
    --schedule "${SCHEDULE}" \
    --time-zone "${TIME_ZONE}" \
    --uri "${RUN_URI}" \
    --http-method POST \
    --oauth-service-account-email "${SCHEDULER_SA}" \
    --oauth-token-scope "https://www.googleapis.com/auth/cloud-platform" \
    --project "${PROJECT_ID}"
fi

INDEX_SERVICE_URL="$(gcloud run services describe "${INDEX_SERVICE_NAME}" \
  --region "${REGION}" --project "${PROJECT_ID}" \
  --format='value(status.url)')"

cat <<EOF

Deployment complete. The schedule is configured but no capture was started.

Test once:
  gcloud run jobs execute ${JOB_NAME} --region ${REGION} --project ${PROJECT_ID} --wait

Inspect captures:
  gcloud storage ls gs://${BUCKET_NAME}/manifests/

Private capture API origin:
  ${INDEX_SERVICE_URL}

Set API_BASE_URL in web/worker/wrangler.jsonc to:
  ${INDEX_SERVICE_URL}

Set the same origin token as the Worker secret:
  npx wrangler secret put ORIGIN_AUTH_TOKEN --config web/worker/wrangler.jsonc
EOF
