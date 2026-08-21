"""Load and validate the repository-owned Cloudflare deployment manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


MANIFEST_PATH = Path(__file__).with_name("cloudflare-manifest.json")
PRODUCTION_KEYS = ("branch", "pages_project", "pages_origin", "worker_origin")


def _https_origin(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty HTTPS origin")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must be an HTTPS origin without a path")
    normalized = f"https://{parsed.netloc}"
    if value != normalized:
        raise ValueError(f"{label} must use its canonical origin form")
    return normalized


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return value


def validate_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0.0":
        raise ValueError("Cloudflare manifest schema_version must be 1.0.0")
    production = manifest.get("production")
    cors = manifest.get("cors")
    if not isinstance(production, dict) or not isinstance(cors, dict):
        raise ValueError("Cloudflare manifest requires production and cors objects")
    for key in PRODUCTION_KEYS:
        if key not in production:
            raise ValueError(f"Cloudflare manifest is missing production.{key}")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", str(production["branch"])):
        raise ValueError("production.branch contains unsupported characters")
    if not re.fullmatch(r"[a-z0-9-]+", str(production["pages_project"])):
        raise ValueError("production.pages_project must be a Cloudflare project name")
    production["pages_origin"] = _https_origin(
        production["pages_origin"], "production.pages_origin"
    )
    production["worker_origin"] = _https_origin(
        production["worker_origin"], "production.worker_origin"
    )
    if production["pages_origin"] == production["worker_origin"]:
        raise ValueError("Pages and Worker production origins must be distinct")

    additional = _string_list(
        cors.get("additional_exact_origins", []),
        "cors.additional_exact_origins",
    )
    normalized_additional = [
        _https_origin(origin, "cors.additional_exact_origins item")
        for origin in additional
    ]
    if production["pages_origin"] in normalized_additional:
        raise ValueError("The production Pages origin is already included automatically")
    suffixes = _string_list(
        cors.get("https_subdomain_suffixes", []),
        "cors.https_subdomain_suffixes",
    )
    for suffix in suffixes:
        if (
            not suffix.startswith(".")
            or suffix != suffix.lower()
            or "/" in suffix
            or "*" in suffix
            or urlsplit(f"https://preview{suffix}").hostname != f"preview{suffix}"
        ):
            raise ValueError(
                "CORS suffixes must be lowercase hostname suffixes beginning with a dot"
            )
    cors["additional_exact_origins"] = normalized_additional
    return manifest


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as manifest_file:
        return validate_manifest(json.load(manifest_file))


def cors_exact_origins(manifest: dict[str, Any]) -> list[str]:
    return [
        manifest["production"]["pages_origin"],
        *manifest["cors"]["additional_exact_origins"],
    ]


def manifest_value(manifest: dict[str, Any], dotted_key: str) -> Any:
    value: Any = manifest
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted_key)
        value = value[part]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "get"))
    parser.add_argument("key", nargs="?")
    args = parser.parse_args()
    manifest = load_manifest()
    if args.command == "validate":
        if args.key:
            parser.error("validate does not accept a key")
        print(f"Validated {MANIFEST_PATH}")
        return
    if not args.key:
        parser.error("get requires a dotted manifest key")
    value = manifest_value(manifest, args.key)
    if isinstance(value, (dict, list)):
        print(json.dumps(value, separators=(",", ":")))
    else:
        print(value)


if __name__ == "__main__":
    main()
