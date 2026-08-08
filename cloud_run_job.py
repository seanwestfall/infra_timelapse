"""Run an Infra Timelapse capture and persist its artifacts in Cloud Storage."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MANIFEST_PREFIX = "manifests/"
INDEX_OBJECT = "index.json"


def required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_capture(scope: str) -> None:
    command = [sys.executable, "fetch_images.py", "--scope", scope]
    subprocess.run(command, check=True)


def build_capture_index(bucket: Any) -> dict[str, Any]:
    """Build one aggregate index from every immutable run manifest."""
    manifests: list[dict[str, Any]] = []
    for blob in bucket.list_blobs(prefix=MANIFEST_PREFIX):
        if not blob.name.endswith(".json"):
            continue
        manifest = json.loads(blob.download_as_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not isinstance(
            manifest.get("files"), list
        ):
            raise ValueError(f"Invalid capture manifest: {blob.name}")
        manifests.append(manifest)

    manifests.sort(
        key=lambda manifest: (
            str(manifest.get("generated_at", "")),
            str(manifest.get("run_id", "")),
        )
    )
    return {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "manifest_count": len(manifests),
        "capture_count": sum(len(manifest["files"]) for manifest in manifests),
        "manifests": manifests,
    }


def publish_capture_index(bucket: Any) -> dict[str, Any]:
    """Publish the aggregate index without changing bucket visibility."""
    capture_index = build_capture_index(bucket)
    index_blob = bucket.blob(INDEX_OBJECT)
    index_blob.cache_control = "private, max-age=0, no-store"
    index_blob.upload_from_string(
        json.dumps(capture_index, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json",
    )
    return capture_index


def upload_capture(
    bucket_name: str,
    output_dir: Path,
    metadata_file: Path,
    run_id: str,
    scope: str,
) -> dict[str, Any]:
    from google.cloud import storage

    image_paths = sorted(output_dir.rglob("*.png"))
    if not image_paths:
        raise RuntimeError(f"Capture produced no PNG files beneath {output_dir}")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    object_prefix = f"captures/{run_id}"
    files: list[dict[str, Any]] = []

    for image_path in image_paths:
        relative_path = image_path.relative_to(output_dir).as_posix()
        object_name = f"{object_prefix}/{relative_path}"
        checksum = sha256(image_path)
        blob = bucket.blob(object_name)
        blob.metadata = {"sha256": checksum, "capture_run_id": run_id}
        blob.upload_from_filename(image_path, content_type="image/png")
        files.append(
            {
                "object": f"gs://{bucket_name}/{object_name}",
                "relative_path": relative_path,
                "bytes": image_path.stat().st_size,
                "sha256": checksum,
            }
        )

    if metadata_file.exists():
        metadata_object = f"{object_prefix}/metadata.json"
        bucket.blob(metadata_object).upload_from_filename(
            metadata_file, content_type="application/json"
        )
    else:
        metadata_object = None

    manifest = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "image_count": len(files),
        "metadata_object": (
            f"gs://{bucket_name}/{metadata_object}" if metadata_object else None
        ),
        "files": files,
    }
    manifest_blob = bucket.blob(f"{MANIFEST_PREFIX}{run_id}.json")
    manifest_blob.upload_from_string(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        content_type="application/json",
    )
    publish_capture_index(bucket)
    return manifest


def main() -> None:
    bucket_name = required_environment("GCS_BUCKET")
    scope = os.getenv("CAPTURE_SCOPE", "all")
    if scope not in {"ports", "corridors", "all"}:
        raise RuntimeError("CAPTURE_SCOPE must be ports, corridors, or all")

    output_dir = Path(os.getenv("OUTPUT_DIR", "/tmp/infra-timelapse/images"))
    metadata_file = Path(
        os.getenv("METADATA_FILE", "/tmp/infra-timelapse/metadata.json")
    )
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    run_capture(scope)
    manifest = upload_capture(
        bucket_name, output_dir, metadata_file, run_id, scope
    )
    print(
        f"Uploaded {manifest['image_count']} image(s) to "
        f"gs://{bucket_name}/captures/{run_id}/"
    )
    print(f"Manifest: gs://{bucket_name}/manifests/{run_id}.json")
    print(f"Aggregate index: gs://{bucket_name}/{INDEX_OBJECT}")


if __name__ == "__main__":
    main()
