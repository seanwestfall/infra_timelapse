"""Runtime configuration for the Infra Timelapse image fetcher.

Set GOOGLE_MAPS_API_KEY in the environment before making live API requests.
The remaining values have practical defaults and can also be overridden with
environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path


# Keep credentials outside source control:
# export GOOGLE_MAPS_API_KEY="your-api-key"
API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# Google Static Maps and local output settings.
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "images"))
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "640x640")
# Google Static Maps accepts a maximum standard size of 640x640, while
# scale=2 returns a 1280x1280 image covering the same geographic area.
IMAGE_SCALE = int(os.getenv("IMAGE_SCALE", "2"))
MAP_TYPE = os.getenv("MAP_TYPE", "satellite")

# Default zoom levels used when a JSON target does not define its own zoom.
PORT_ZOOM = int(os.getenv("PORT_ZOOM", "15"))
CORRIDOR_ZOOM = int(os.getenv("CORRIDOR_ZOOM", "12"))

# The fetcher maintains this as a JSON list of completed image requests.
METADATA_FILE = Path(os.getenv("METADATA_FILE", "metadata.json"))

# Per-target request resilience and the machine-readable outcome consumed by
# cloud_run_job.py. Retry delays use exponential backoff plus jitter.
CAPTURE_REPORT_FILE = Path(
    os.getenv("CAPTURE_REPORT_FILE", "capture-report.json")
)
MAX_FETCH_ATTEMPTS = int(os.getenv("MAX_FETCH_ATTEMPTS", "4"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "1"))
RETRY_MAX_BACKOFF_SECONDS = float(
    os.getenv("RETRY_MAX_BACKOFF_SECONDS", "30")
)
