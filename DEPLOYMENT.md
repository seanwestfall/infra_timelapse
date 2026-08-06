# Google Cloud deployment

Infra Timelapse runs as a finite Cloud Run Job. Cloud Scheduler currently
invokes it daily at 03:00 in `Pacific/Honolulu` for short-term schedule
validation. Each execution stores images and a SHA-256 manifest in a private
Cloud Storage bucket.

## Prerequisites

- Google Cloud CLI installed and authenticated
- `gcloud config set project infra-timelapse` completed
- billing enabled on the selected project
- permission to enable APIs, create service accounts, and add the listed IAM
  bindings

## Deploy

From the repository root:

```bash
bash deploy/setup_gcp.sh
```

The script prints its exact resource plan and makes no changes unless you type
`deploy`. If the Secret Manager secret has no enabled version, it asks for the
Google Maps API key using hidden terminal input. It is safe to run again to
update the container and job configuration.

Defaults can be overridden for one invocation:

```bash
REGION=us-west1 BUCKET_NAME=my-private-bucket bash deploy/setup_gcp.sh
```

## Verify with one manual capture

The setup script creates the schedule without triggering an immediate run.
Test the complete path explicitly:

```bash
gcloud run jobs execute infra-timelapse-capture \
  --region us-west1 \
  --project infra-timelapse \
  --wait

gcloud storage ls gs://infra-timelapse-infra-timelapse-images/manifests/
```

A full run should report 204 uploaded images. Objects are stored under a unique
UTC run identifier, so later captures do not overwrite earlier captures.

## Resources and access

The setup creates or updates:

- an Artifact Registry Docker repository
- a private Cloud Storage bucket with public-access prevention
- a Secret Manager secret for the Maps API key
- a runtime service account with bucket object access and secret access
- a scheduler service account with permission to execute only the Cloud Run job
- the Cloud Run job and Cloud Scheduler HTTP job

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
