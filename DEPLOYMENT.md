# Deployment

Infra Timelapse has three deliberately separate pieces:

1. A finite Cloud Run Job captures images on the 1st and 15th of each month.
2. A read-only Cloud Run service exposes a sanitized aggregate index and
   authorized image responses from the private capture bucket.
3. Cloudflare Pages serves the static map and forwards only `/api/*` requests
   to that read service.

The browser never receives a `gs://` URI or an anonymous Cloud Storage URL.

## Google Cloud prerequisites

- Google Cloud CLI installed and authenticated
- `gcloud config set project infra-timelapse` completed
- billing enabled on the selected project
- permission to enable APIs, create service accounts, deploy Cloud Run, and
  add the listed IAM bindings

## Deploy the capture job and read service

From the repository root:

```bash
bash deploy/setup_gcp.sh
```

The script prints its resource plan and makes no changes unless you type
`deploy`. It is safe to run again to rebuild the shared image and update both
Cloud Run workloads.

Defaults can be overridden for one invocation:

```bash
REGION=us-west1 BUCKET_NAME=my-private-bucket bash deploy/setup_gcp.sh
```

The final output includes the Cloud Run read-service URL. Keep it for the
Cloudflare Pages setup below.

## Verify with one manual capture

The setup script creates the schedule without triggering an immediate run.
Test the complete write path explicitly:

```bash
gcloud run jobs execute infra-timelapse-capture \
  --region us-west1 \
  --project infra-timelapse \
  --wait

gcloud storage ls gs://infra-timelapse-infra-timelapse-images/manifests/
gcloud storage cat gs://infra-timelapse-infra-timelapse-images/index.json \
  | head
```

A full run should report 204 uploaded images. It writes an immutable run
manifest and then regenerates the private root `index.json` from every run
manifest. If an older bucket has manifests but no root index yet, the read
service aggregates those manifests in memory until the next capture publishes
the file.

Verify the read service with the URL printed by the setup script:

```bash
curl "https://YOUR-SERVICE-URL/healthz"
curl "https://YOUR-SERVICE-URL/api/index"
```

## Deploy the main page to Cloudflare Pages

Connect the repository to a Cloudflare Pages project and configure:

- Build command: `npm run build`
- Build output directory: `dist`
- Runtime variable: `API_BASE_URL=https://YOUR-CLOUD-RUN-SERVICE-URL`

`web/index.html` is copied to the real `dist/index.html` entry point together
with the monitoring inventory. The Pages Function at
`functions/api/[[path]].js` forwards same-origin `/api/*` requests to the fixed
Cloud Run URL. It does not forward browser cookies, authorization headers, or
client-address headers.

To verify the static bundle locally:

```bash
npm run build
python -m http.server --directory dist 8081
```

That local static server will load all 204 inventory markers. Live private
captures require the Pages Function. The existing `?index=` and `?assets=`
parameters remain available for a local manifest and local image directory.

## Storage and access boundary

The setup creates or updates:

- an Artifact Registry Docker repository;
- a Cloud Storage bucket with uniform bucket-level access and public-access
  prevention;
- a capture-job service account with object-user access;
- a read-service account with object-viewer access only;
- a scheduler service account that can invoke only the capture job;
- a Secret Manager secret for the Google Maps API key;
- the Cloud Run job, public read service, and Scheduler job.

The public read service is the intentional delivery boundary. It returns only
the aggregate capture fields needed by the page and only PNG objects under the
`captures/` prefix. It never exposes metadata objects, bucket credentials, or
direct object URIs. Capture image paths are immutable and may be cached; the
aggregate index is refreshed every five minutes at most.

The schedule expression is `0 3 1,15 * *` in `Pacific/Honolulu`. This means
twice monthly, not an exact 14-day interval.

## Roll back compute resources

```bash
bash deploy/cleanup_gcp.sh
```

The cleanup script has a separate confirmation gate. It preserves the bucket
and secret deliberately; deleting either could destroy capture history or a
credential version.
