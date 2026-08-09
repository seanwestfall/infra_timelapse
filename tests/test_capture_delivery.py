import json
import os
from io import BytesIO
import unittest

import capture_api
from cloud_run_job import build_capture_index, publish_capture_index


BUCKET_NAME = "private-capture-bucket"
RUN_ID = "2026-08-08T00-00-00Z"
OBJECT_NAME = f"captures/{RUN_ID}/ports/long_beach/2026-08-08.png"


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name
        self.cache_control = None
        self.content_type = None
        self.etag = "test-etag"

    def download_as_text(self, encoding="utf-8"):
        value = self.bucket.objects[self.name]
        return value.decode(encoding) if isinstance(value, bytes) else value

    def download_as_bytes(self):
        value = self.bucket.objects[self.name]
        return value if isinstance(value, bytes) else value.encode("utf-8")

    def open(self, mode):
        if mode != "rb":
            raise ValueError("FakeBlob supports only binary reads")
        return BytesIO(self.download_as_bytes())

    def upload_from_string(self, value, content_type=None):
        self.bucket.objects[self.name] = value
        self.content_type = content_type


class FakeBucket:
    def __init__(self, objects=None):
        self.name = BUCKET_NAME
        self.objects = dict(objects or {})
        self.blobs = {}

    def blob(self, name):
        return self.blobs.setdefault(name, FakeBlob(self, name))

    def get_blob(self, name):
        return self.blob(name) if name in self.objects else None

    def list_blobs(self, prefix=""):
        return [
            self.blob(name)
            for name in sorted(self.objects)
            if name.startswith(prefix)
        ]


def manifest(run_id=RUN_ID):
    return {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": "2026-08-08T00:00:00+00:00",
        "scope": "all",
        "image_count": 1,
        "metadata_object": f"gs://{BUCKET_NAME}/captures/{run_id}/metadata.json",
        "files": [
            {
                "object": f"gs://{BUCKET_NAME}/{OBJECT_NAME}",
                "relative_path": "ports/long_beach/2026-08-08.png",
                "bytes": 7,
                "sha256": "abc123",
            }
        ],
    }


class CaptureIndexTests(unittest.TestCase):
    def test_build_and_publish_private_aggregate_index(self):
        bucket = FakeBucket(
            {f"manifests/{RUN_ID}.json": json.dumps(manifest())}
        )

        capture_index = build_capture_index(bucket)
        self.assertEqual(capture_index["manifest_count"], 1)
        self.assertEqual(capture_index["capture_count"], 1)

        publish_capture_index(bucket)
        stored = json.loads(bucket.objects["index.json"])
        self.assertEqual(stored["manifests"][0]["run_id"], RUN_ID)
        self.assertEqual(
            bucket.blobs["index.json"].cache_control,
            "private, max-age=0, no-store",
        )

    def test_read_service_falls_back_to_existing_manifests(self):
        bucket = FakeBucket(
            {f"manifests/{RUN_ID}.json": json.dumps(manifest())}
        )
        result = capture_api.load_capture_index(bucket)
        self.assertEqual(result["capture_count"], 1)

    def test_public_index_replaces_private_object_uris(self):
        private_index = {
            "schema_version": "1.0.0",
            "manifests": [manifest()],
        }
        result = capture_api.public_capture_index(private_index, BUCKET_NAME)
        public_manifest = result["manifests"][0]
        public_file = public_manifest["files"][0]

        self.assertNotIn("metadata_object", public_manifest)
        self.assertNotIn("object", public_file)
        self.assertEqual(
            public_file["image_url"], f"/api/captures/{OBJECT_NAME}"
        )

    def test_capture_object_validation_rejects_other_bucket_paths(self):
        self.assertTrue(capture_api.safe_capture_object(OBJECT_NAME))
        self.assertFalse(capture_api.safe_capture_object("metadata.json"))
        self.assertFalse(
            capture_api.safe_capture_object("captures/run/../metadata.json")
        )
        with self.assertRaisesRegex(ValueError, "configured bucket"):
            capture_api.capture_object_name(
                f"gs://another-bucket/{OBJECT_NAME}", BUCKET_NAME
            )

    def test_http_boundary_serves_index_and_capture(self):
        bucket = FakeBucket(
            {
                "index.json": json.dumps(
                    {"schema_version": "1.0.0", "manifests": [manifest()]}
                ),
                OBJECT_NAME: b"PNGDATA",
            }
        )
        previous_bucket = capture_api._bucket
        previous_token = os.environ.get("ORIGIN_AUTH_TOKEN")
        capture_api._bucket = bucket
        os.environ["ORIGIN_AUTH_TOKEN"] = "test-origin-token"
        try:
            client = capture_api.app.test_client()
            headers = {
                capture_api.ORIGIN_AUTH_HEADER: "test-origin-token",
            }
            index_response = client.get("/api/index", headers=headers)
            image_response = client.get(
                f"/api/captures/{OBJECT_NAME}", headers=headers
            )
        finally:
            capture_api._bucket = previous_bucket
            if previous_token is None:
                os.environ.pop("ORIGIN_AUTH_TOKEN", None)
            else:
                os.environ["ORIGIN_AUTH_TOKEN"] = previous_token

        self.assertEqual(index_response.status_code, 200)
        self.assertNotIn(b"gs://", index_response.data)
        self.assertEqual(image_response.status_code, 200)
        self.assertEqual(image_response.data, b"PNGDATA")
        self.assertEqual(image_response.content_type, "image/png")

    def test_http_boundary_rejects_direct_unauthorized_requests(self):
        previous_token = os.environ.get("ORIGIN_AUTH_TOKEN")
        os.environ["ORIGIN_AUTH_TOKEN"] = "test-origin-token"
        try:
            response = capture_api.app.test_client().get("/api/index")
        finally:
            if previous_token is None:
                os.environ.pop("ORIGIN_AUTH_TOKEN", None)
            else:
                os.environ["ORIGIN_AUTH_TOKEN"] = previous_token

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
