import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import cloud_run_job


class FakeBlob:
    def __init__(self, name):
        self.name = name
        self.metadata = None
        self.cache_control = None
        self.uploaded_from = None
        self.uploaded_string = None

    def upload_from_filename(self, path, content_type=None):
        self.uploaded_from = (path, content_type)

    def upload_from_string(self, value, content_type=None):
        self.uploaded_string = (value, content_type)

    def download_as_text(self, encoding="utf-8"):
        return self.uploaded_string[0]


class FakeBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        return self.blobs.setdefault(name, FakeBlob(name))

    def list_blobs(self, prefix=""):
        return [
            blob
            for name, blob in sorted(self.blobs.items())
            if name.startswith(prefix)
        ]


class CloudRunJobTests(unittest.TestCase):
    def test_partial_capture_manifest_is_uploaded(self):
        bucket = FakeBucket()
        client = types.SimpleNamespace(bucket=lambda name: bucket)
        storage = types.SimpleNamespace(Client=lambda: client)
        google_cloud = types.ModuleType("google.cloud")
        google_cloud.storage = storage
        google = types.ModuleType("google")
        google.cloud = google_cloud

        failure = {
            "target_id": "failed_port",
            "target_type": "port",
            "name": "Failed Port",
            "status_code": 500,
            "attempts": 4,
        }
        report = {
            "status": "partial_success",
            "requested_count": 2,
            "success_count": 1,
            "failure_count": 1,
            "failures": [failure],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "images"
            image = output_dir / "ports" / "working_port" / "2026-08-07.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"png")
            report_file = root / "capture-report.json"
            report_file.write_text(json.dumps(report))

            with mock.patch.dict(
                sys.modules,
                {"google": google, "google.cloud": google_cloud},
            ):
                manifest = cloud_run_job.upload_capture(
                    "test-bucket",
                    output_dir,
                    root / "metadata.json",
                    report_file,
                    "test-run",
                    "all",
                )

        self.assertEqual(manifest["status"], "partial_success")
        self.assertEqual(manifest["requested_count"], 2)
        self.assertEqual(manifest["image_count"], 1)
        self.assertEqual(manifest["failure_count"], 1)
        self.assertEqual(manifest["failures"], [failure])
        uploaded_manifest = bucket.blobs["manifests/test-run.json"]
        payload = json.loads(uploaded_manifest.uploaded_string[0])
        self.assertEqual(payload, manifest)
        capture_index = json.loads(
            bucket.blobs["index.json"].uploaded_string[0]
        )
        self.assertEqual(capture_index["manifest_count"], 1)
        self.assertEqual(capture_index["capture_count"], 1)


if __name__ == "__main__":
    unittest.main()
