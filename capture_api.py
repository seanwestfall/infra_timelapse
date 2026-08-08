"""Read-only HTTP boundary for the private Infra Timelapse bucket."""

from __future__ import annotations

import json
import os
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from flask import Flask, Response, jsonify, request
from google.cloud import storage

from cloud_run_job import INDEX_OBJECT, build_capture_index, required_environment


app = Flask(__name__)
_bucket: Any | None = None


def get_bucket() -> Any:
    """Return the configured private bucket using ambient service identity."""
    global _bucket
    if _bucket is None:
        _bucket = storage.Client().bucket(required_environment("GCS_BUCKET"))
    return _bucket


def safe_capture_object(object_name: str) -> bool:
    """Allow only immutable PNG objects beneath the capture prefix."""
    path = PurePosixPath(object_name)
    return (
        not path.is_absolute()
        and len(path.parts) >= 4
        and path.parts[0] == "captures"
        and ".." not in path.parts
        and path.suffix.lower() == ".png"
    )


def capture_object_name(value: Any, bucket_name: str) -> str:
    prefix = f"gs://{bucket_name}/"
    object_uri = str(value or "")
    if not object_uri.startswith(prefix):
        raise ValueError("Capture object is outside the configured bucket")
    object_name = object_uri[len(prefix) :]
    if not safe_capture_object(object_name):
        raise ValueError("Capture object is outside the allowed prefix")
    return object_name


def load_capture_index(bucket: Any) -> dict[str, Any]:
    """Read the published index, falling back to existing run manifests."""
    index_blob = bucket.get_blob(INDEX_OBJECT)
    if index_blob is None:
        return build_capture_index(bucket)
    capture_index = json.loads(index_blob.download_as_text(encoding="utf-8"))
    if not isinstance(capture_index, dict) or not isinstance(
        capture_index.get("manifests"), list
    ):
        raise ValueError("The aggregate capture index is invalid")
    return capture_index


def public_capture_index(
    capture_index: dict[str, Any], bucket_name: str
) -> dict[str, Any]:
    """Replace private object URIs with same-origin authorized proxy URLs."""
    manifests: list[dict[str, Any]] = []
    for manifest in capture_index.get("manifests", []):
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("files"), list
        ):
            raise ValueError(
                "The aggregate capture index contains an invalid manifest"
            )
        public_manifest = {
            key: value
            for key, value in manifest.items()
            if key not in {"files", "metadata_object"}
        }
        public_files: list[dict[str, Any]] = []
        for file_record in manifest["files"]:
            if not isinstance(file_record, dict):
                raise ValueError(
                    "The aggregate capture index contains an invalid file"
                )
            object_name = capture_object_name(
                file_record.get("object"), bucket_name
            )
            public_file = {
                key: value
                for key, value in file_record.items()
                if key != "object"
            }
            public_file["image_url"] = (
                f"/api/captures/{quote(object_name, safe='/')}"
            )
            public_files.append(public_file)
        public_manifest["files"] = public_files
        manifests.append(public_manifest)

    return {
        key: value
        for key, value in capture_index.items()
        if key != "manifests"
    } | {"manifests": manifests}


def cache_headers(response: Response, value: str) -> Response:
    response.headers["Cache-Control"] = value
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/healthz")
def health() -> Response:
    return cache_headers(jsonify({"status": "ok"}), "no-store")


@app.get("/api/index")
def capture_index() -> Response:
    try:
        bucket = get_bucket()
        result = public_capture_index(load_capture_index(bucket), bucket.name)
    except Exception:
        app.logger.exception("Could not load the private capture index")
        return cache_headers(
            jsonify({"error": "Capture index unavailable"}), "no-store"
        ), 503

    return cache_headers(
        jsonify(result), "public, max-age=60, s-maxage=300"
    )


@app.get("/api/captures/<path:object_name>")
def capture_image(object_name: str) -> Response:
    if not safe_capture_object(object_name):
        return cache_headers(
            jsonify({"error": "Capture not found"}), "no-store"
        ), 404

    blob = get_bucket().get_blob(object_name)
    if blob is None:
        return cache_headers(
            jsonify({"error": "Capture not found"}), "no-store"
        ), 404

    etag = str(blob.etag or "").strip('"')
    if etag and request.if_none_match.contains(etag):
        response = Response(status=304)
    else:
        response = Response(
            blob.download_as_bytes(),
            content_type="image/png",
        )
    if etag:
        response.set_etag(etag)
    return cache_headers(response, "public, max-age=31536000, immutable")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
