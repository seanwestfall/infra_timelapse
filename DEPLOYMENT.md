# Deployment

Infra Timelapse has three deliberately separate pieces:

1. A finite Cloud Run Job currently captures images daily for short-term
   schedule validation.
2. A read-only Cloud Run service exposes a sanitized aggregate index and
   authorized image responses from the private capture bucket.
3. Cloudflare Pages serves the static map, while the standalone `if-api`
   Cloudflare Worker reads the public geospatial inventory from Neon and
   forwards only allowlisted capture routes to the private-storage service.

The browser never receives a `gs://` URI or an anonymous Cloud Storage URL.

## Feature preview process

Frontend features are developed on dedicated branches and reviewed through a
pull request before production deployment. Pull requests originating from this
repository run the complete test/build suite and deploy only the static Pages
frontend; they never deploy the production API Worker.

Cloudflare Pages publishes an immutable deployment URL and a moving branch
alias. For example, `codex/reconstruction-theme-preview` is available at
`codex-reconstruction-theme-preview.<pages-project>.pages.dev`. The workflow
adds that branch alias to its GitHub Actions job summary. Production remains
restricted to pushes on `main`.

Recommended feature flow:

1. Branch from the current integration branch.
2. Commit and push the feature branch.
3. Open a draft pull request and wait for tests plus the Pages preview.
4. Review the preview URL from the Actions summary before marking the PR ready.
5. Merge through the PR; never deploy a feature branch as production.

The preview job expects a GitHub environment named `preview` with access to the
same `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` secrets used for Pages,
plus the `CLOUDFLARE_PAGES_PROJECT` and `TIMELAPSE_API_BASE` variables.

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
standalone Worker setup below.

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

Each Static Maps request is retried up to four times for network failures and
HTTP `429`, `500`, `502`, `503`, or `504` responses, using exponential backoff
with jitter. If an individual target still fails, the run continues, uploads
the successful captures, and publishes a `partial_success` manifest containing
the failed target ID, name, status code, and attempt count. The job fails only
when every selected target fails or a job-level operation such as storage
uploading fails.

The read service requires the Worker-to-origin token. Verify it with the URL
printed by the setup script and the same token stored in Secret Manager:

```bash
curl -H "X-Infra-Timelapse-Origin-Token: YOUR-TOKEN" \
  "https://YOUR-SERVICE-URL/healthz"
curl -H "X-Infra-Timelapse-Origin-Token: YOUR-TOKEN" \
  "https://YOUR-SERVICE-URL/api/index"
```

## Configure the standalone Cloudflare Worker

Install the pinned dependencies, replace `API_BASE_URL` in
`web/worker/wrangler.jsonc` with the Cloud Run service URL, and configure the same
origin token that `deploy/setup_gcp.sh` stored in Google Secret Manager. Then
store the Neon pooled connection string as a second Worker secret:

```bash
npm install
npx wrangler secret put ORIGIN_AUTH_TOKEN --config web/worker/wrangler.jsonc
npm run secret:database
```

The final command prompts for the value of `DATABASE_URL`; paste the Neon
pooled connection string at that prompt. Do not add it to `wrangler.jsonc`, a
shell script, a `.env` file, GitHub Actions variables, or the static Pages
bundle. The equivalent direct Wrangler command is:

```bash
npx wrangler secret put DATABASE_URL --config web/worker/wrangler.jsonc
```

The Worker reads only the schema-qualified `infratimelapse` tables and exposes:

- `GET /api/nodes`
- `GET /api/corridors`
- `GET /api/projects`
- `GET /api/satellites/{norad_id}/elements`

These inventory responses are cached at the edge for five minutes. Deprecated
entities are excluded. Database failures return bounded `502`/`503` responses
without exposing the connection string or database error details.

The satellite-elements demo accepts only Sentinel-2B (`42063`), Sentinel-2C
(`60989`), Landsat 8 (`39084`), and Landsat 9 (`49260`). The Worker retrieves
public OMM JSON from CelesTrak and caches successful responses for two hours;
the browser propagates those elements locally for the live globe marker. No
satellite API key is required. Do not lower the upstream refresh interval.

If Pages and the Worker use separate hostnames, set `ALLOWED_ORIGINS` in the
Worker configuration to a comma-separated list of the exact Pages production
and preview origins. Leave it empty for same-origin routing. Worker routes are
intentionally absent from the repository configuration so dashboard-managed
routes are not overwritten by a later Wrangler deployment.

## Deploy the Worker and Cloudflare Pages

The deployment script always deploys the Worker by default and lets you select
when the static Pages bundle should be deployed:

```bash
# Always deploy the Worker; deploy Pages only when frontend inputs changed.
npm run deploy -- --pages auto --base-ref HEAD^ --head-ref HEAD

# Deploy both regardless of the Git diff.
npm run deploy -- --pages always

# Deploy only the Worker.
npm run deploy -- --pages never

# Deploy only Pages.
npm run deploy -- --worker never --pages always
```

`--pages auto` watches `web/public/`, the packaged inventory, the web build
files, and the Pages Wrangler configuration. Set `TIMELAPSE_API_BASE` during
the build only when the API uses a separate HTTPS hostname; otherwise the
rendered page uses same-origin `/api/index`.

The `Deploy Cloudflare` GitHub Actions workflow runs on each update to `main`.
It tests and deploys the Worker every time, while deploying Pages only when a
static input changed. Configure its protected `production` environment with
the `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` secrets. Optional
variables are `CLOUDFLARE_PAGES_PROJECT` and `TIMELAPSE_API_BASE`.

For a manual Pages-only integration, use:

- Build command: `npm run build`
- Build output directory: `dist`

`web/public/index.html` is rendered to `dist/index.html` together with the
monitoring inventory. API and caching behavior can be deployed independently
without rebuilding that bundle.

To verify the static bundle locally:

```bash
npm run build
python -m http.server --directory dist 8081
```

That local static server will load all 204 inventory markers. Live private
captures require the standalone Worker. The existing `?index=` and `?assets=`
parameters remain available for a local manifest and local image directory.

## Storage and access boundary

The setup creates or updates:

- an Artifact Registry Docker repository;
- a Cloud Storage bucket with uniform bucket-level access and public-access
  prevention;
- a capture-job service account with object-user access;
- a read-service account with object-viewer access only;
- a scheduler service account that can invoke only the capture job;
- Secret Manager secrets for the Google Maps API key and Worker-to-origin
  token;
- the Cloud Run job, authenticated read service, and Scheduler job.

The Worker is the public delivery boundary. `DATABASE_URL` remains a Worker
secret, and all public database queries are fixed, schema-qualified, read-only
statements. The Cloud Run read service rejects
requests without the shared origin token. It returns only the aggregate capture
fields needed by the page and PNG objects under the `captures/` prefix. It
never exposes metadata objects, bucket credentials, or direct object URIs.
Capture image paths are immutable and may be cached; the aggregate index is
refreshed every five minutes at most.

The current test schedule expression is `0 3 * * *`, which runs daily at 03:00
in `Pacific/Honolulu`. To restore the twice-monthly cadence without changing
the script default, deploy with `SCHEDULE="0 3 1,15 * *"`. For a weekly Sunday
capture, use `SCHEDULE="0 3 * * 0"`.

## Roll back compute resources

```bash
bash deploy/cleanup_gcp.sh
```

The cleanup script has a separate confirmation gate. It preserves the bucket
and secret deliberately; deleting either could destroy capture history or a
credential version.
