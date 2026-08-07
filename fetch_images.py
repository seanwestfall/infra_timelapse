from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Iterator

try:
    import config as project_config
except ModuleNotFoundError:
    project_config = None


BASE_URL = "https://maps.googleapis.com/maps/api/staticmap"
DEFAULT_INVENTORY_PATH = Path(__file__).with_name(
    "infra_timelapse_ports_corridors.json"
)
IDENTIFIER_PATTERN = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*\Z")


def config_value(name: str, environment_name: str, default: Any) -> Any:
    """Read a setting from config.py, then the environment, then a default."""
    if project_config is not None and hasattr(project_config, name):
        return getattr(project_config, name)
    return os.getenv(environment_name, default)


API_KEY = str(config_value("API_KEY", "GOOGLE_MAPS_API_KEY", ""))
OUTPUT_DIR = Path(config_value("OUTPUT_DIR", "OUTPUT_DIR", "images"))
IMAGE_SIZE = str(config_value("IMAGE_SIZE", "IMAGE_SIZE", "640x640"))
IMAGE_SCALE = int(config_value("IMAGE_SCALE", "IMAGE_SCALE", 2))
MAP_TYPE = str(config_value("MAP_TYPE", "MAP_TYPE", "satellite"))
PORT_ZOOM = int(config_value("PORT_ZOOM", "PORT_ZOOM", 15))
CORRIDOR_ZOOM = int(config_value("CORRIDOR_ZOOM", "CORRIDOR_ZOOM", 12))
METADATA_FILE = Path(
    config_value("METADATA_FILE", "METADATA_FILE", "metadata.json")
)
CAPTURE_REPORT_FILE = Path(
    config_value(
        "CAPTURE_REPORT_FILE", "CAPTURE_REPORT_FILE", "capture-report.json"
    )
)
MAX_FETCH_ATTEMPTS = int(
    config_value("MAX_FETCH_ATTEMPTS", "MAX_FETCH_ATTEMPTS", 4)
)
RETRY_BACKOFF_SECONDS = float(
    config_value("RETRY_BACKOFF_SECONDS", "RETRY_BACKOFF_SECONDS", 1)
)
RETRY_MAX_BACKOFF_SECONDS = float(
    config_value(
        "RETRY_MAX_BACKOFF_SECONDS", "RETRY_MAX_BACKOFF_SECONDS", 30
    )
)
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class SatelliteImageFetchError(RuntimeError):
    """A sanitized request failure that never includes the Maps API key."""

    def __init__(
        self, target_id: str, attempts: int, status_code: int | None
    ) -> None:
        detail = f"HTTP {status_code}" if status_code else "network error"
        super().__init__(
            f"Static Maps request for {target_id!r} failed after "
            f"{attempts} attempt(s): {detail}"
        )
        self.attempts = attempts
        self.status_code = status_code


def load_inventory(path: Path) -> dict[str, Any]:
    """Load and minimally validate the ports-and-corridors inventory."""
    with path.open(encoding="utf-8") as inventory_file:
        inventory = json.load(inventory_file)

    for key in ("ports_and_logistics_nodes", "corridors"):
        if not isinstance(inventory.get(key), list):
            raise ValueError(f"Inventory field {key!r} must be a list")

    return inventory


def parse_coordinates(value: Any, context: str) -> tuple[float, float]:
    """Convert a WGS84 [longitude, latitude] array into latitude/longitude."""
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{context} must contain [longitude, latitude]")

    longitude, latitude = (float(value[0]), float(value[1]))
    if not -180 <= longitude <= 180:
        raise ValueError(f"{context} longitude is outside [-180, 180]")
    if not -90 <= latitude <= 90:
        raise ValueError(f"{context} latitude is outside [-90, 90]")

    return latitude, longitude


def validate_identifier(value: Any, context: str) -> str:
    """Return an ASCII machine identifier or raise a useful validation error."""
    identifier = str(value or "")
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(
            f"{context} must be a lowercase ASCII identifier using "
            "letters, numbers, and single underscores"
        )
    return identifier


def iter_ports(inventory: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield one satellite-image target for each port or logistics node."""
    for port in inventory["ports_and_logistics_nodes"]:
        port_id = validate_identifier(port.get("id"), "port id")
        latitude, longitude = parse_coordinates(
            port.get("coordinates"), f"port {port_id!r} coordinates"
        )
        yield {
            "id": port_id,
            "target_type": "port",
            "name": str(port["name"]),
            "latitude": latitude,
            "longitude": longitude,
            "zoom": int(port.get("zoom", PORT_ZOOM)),
            "output_parts": ("ports", port_id),
            "country_or_area": port.get("country_or_area"),
            "asset_type": port.get("asset_type"),
            "monitoring_tier": port.get("monitoring_tier"),
            "project_status": port.get("project_status"),
        }


def iter_corridors(inventory: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield each corridor record from the inventory."""
    yield from inventory["corridors"]


def iter_corridor_waypoints(
    corridors: Iterable[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Yield every ordered waypoint from every corridor route segment."""
    for corridor in corridors:
        corridor_id = validate_identifier(corridor.get("id"), "corridor id")
        corridor_name = str(corridor["name"])
        route_segments = corridor.get("route_segments")
        if not isinstance(route_segments, list):
            raise ValueError(
                f"Corridor {corridor_id!r} route_segments must be a list"
            )

        for segment_index, segment in enumerate(route_segments, start=1):
            segment_name = str(segment.get("name", f"segment-{segment_index}"))
            waypoints = segment.get("waypoints")
            if not isinstance(waypoints, list):
                raise ValueError(
                    f"Corridor {corridor_id!r} segment {segment_index} "
                    "waypoints must be a list"
                )

            for waypoint_index, waypoint in enumerate(waypoints, start=1):
                waypoint_name = str(
                    waypoint.get("name", f"waypoint-{waypoint_index}")
                )
                latitude, longitude = parse_coordinates(
                    waypoint.get("coordinates"),
                    (
                        f"corridor {corridor_id!r} segment {segment_index} "
                        f"waypoint {waypoint_index} coordinates"
                    ),
                )
                waypoint_identifier = validate_identifier(
                    waypoint.get("node_id") or waypoint.get("id"),
                    (
                        f"corridor {corridor_id!r} segment {segment_index} "
                        f"waypoint {waypoint_index} identifier"
                    ),
                )
                target_id = (
                    f"{corridor_id}-{segment_index:02d}-"
                    f"{waypoint_index:03d}-{waypoint_identifier}"
                )
                yield {
                    "id": target_id,
                    "target_type": "corridor_waypoint",
                    "name": f"{corridor_name} — {waypoint_name}",
                    "latitude": latitude,
                    "longitude": longitude,
                    "zoom": int(waypoint.get("zoom", CORRIDOR_ZOOM)),
                    "output_parts": (
                        "corridors",
                        corridor_id,
                        f"segment-{segment_index:02d}",
                        f"{waypoint_index:03d}-{waypoint_identifier}",
                    ),
                    "corridor_id": corridor_id,
                    "corridor_name": corridor_name,
                    "segment_index": segment_index,
                    "segment_name": segment_name,
                    "waypoint_index": waypoint_index,
                    "waypoint_id": waypoint_identifier,
                    "waypoint_name": waypoint_name,
                    "node_id": waypoint.get("node_id"),
                }


def iter_targets(
    inventory: dict[str, Any], scope: str = "all"
) -> Iterator[dict[str, Any]]:
    """Cycle through ports, corridor waypoints, or both."""
    if scope not in {"ports", "corridors", "all"}:
        raise ValueError("scope must be 'ports', 'corridors', or 'all'")

    if scope in {"ports", "all"}:
        yield from iter_ports(inventory)
    if scope in {"corridors", "all"}:
        yield from iter_corridor_waypoints(iter_corridors(inventory))


def fetch_satellite_image(
    target: dict[str, Any],
    *,
    request_get: Any = None,
    sleep: Any = time.sleep,
    random_uniform: Any = random.uniform,
) -> Path:
    """Fetch one Google Static Maps satellite image for a monitoring target."""
    if not API_KEY:
        raise RuntimeError(
            "Set API_KEY in config.py or GOOGLE_MAPS_API_KEY in the environment"
        )

    try:
        import requests
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "The requests package is required to fetch satellite images"
        ) from error

    date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_dir = OUTPUT_DIR.joinpath(*target["output_parts"])
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / f"{date_tag}.png"

    params = {
        "center": f'{target["latitude"]},{target["longitude"]}',
        "zoom": target["zoom"],
        "size": IMAGE_SIZE,
        "scale": IMAGE_SCALE,
        "maptype": MAP_TYPE,
        "key": API_KEY,
    }

    if MAX_FETCH_ATTEMPTS < 1:
        raise RuntimeError("MAX_FETCH_ATTEMPTS must be at least 1")

    get = request_get or requests.get
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            response = get(BASE_URL, params=params, timeout=30)
            status_code = response.status_code
        except requests.RequestException:
            response = None
            status_code = None

        retryable = (
            status_code is None or status_code in RETRYABLE_STATUS_CODES
        )
        if response is not None and not retryable:
            try:
                response.raise_for_status()
            except requests.RequestException:
                raise SatelliteImageFetchError(
                    target["id"], attempt, status_code
                ) from None
            break

        if response is not None and status_code < 400:
            break

        if not retryable or attempt == MAX_FETCH_ATTEMPTS:
            raise SatelliteImageFetchError(
                target["id"], attempt, status_code
            ) from None

        delay = min(
            RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)),
            RETRY_MAX_BACKOFF_SECONDS,
        ) + random_uniform(0, RETRY_BACKOFF_SECONDS)
        detail = f"HTTP {status_code}" if status_code else "network error"
        print(
            f"Retrying {target['id']} after {detail}; "
            f"attempt {attempt + 1}/{MAX_FETCH_ATTEMPTS} in {delay:.1f}s",
            file=sys.stderr,
        )
        sleep(delay)

    filepath.write_bytes(response.content)
    return filepath


def log_metadata(target: dict[str, Any], filepath: Path) -> None:
    """Append one image result to the existing JSON metadata log."""
    entry = {
        key: value
        for key, value in target.items()
        if key != "output_parts" and value is not None
    }
    entry.update(
        {
            "image": str(filepath),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )

    if METADATA_FILE.exists():
        with METADATA_FILE.open(encoding="utf-8") as metadata_input:
            metadata = json.load(metadata_input)
        if not isinstance(metadata, list):
            raise ValueError(f"{METADATA_FILE} must contain a JSON list")
    else:
        metadata = []

    metadata.append(entry)
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_FILE.open("w", encoding="utf-8") as metadata_output:
        json.dump(metadata, metadata_output, ensure_ascii=False, indent=2)
        metadata_output.write("\n")


def write_capture_report(
    report_file: Path,
    requested_count: int,
    success_count: int,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Write the capture outcome consumed by the Cloud Run uploader."""
    if not failures:
        status = "success"
    elif success_count:
        status = "partial_success"
    else:
        status = "failed"

    report = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_count": requested_count,
        "success_count": success_count,
        "failure_count": len(failures),
        "failures": failures,
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with report_file.open("w", encoding="utf-8") as report_output:
        json.dump(report, report_output, ensure_ascii=False, indent=2)
        report_output.write("\n")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch satellite images for ports and corridor waypoints in the "
            "Infra Timelapse JSON inventory."
        )
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY_PATH,
        help=f"Inventory JSON path (default: {DEFAULT_INVENTORY_PATH.name})",
    )
    parser.add_argument(
        "--scope",
        choices=("ports", "corridors", "all"),
        default="all",
        help="Targets to cycle through (default: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N selected targets",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List targets and coordinates without calling Google Maps",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=CAPTURE_REPORT_FILE,
        help="Write a JSON capture report to this path",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if not args.dry_run and not API_KEY:
        parser.error(
            "Set API_KEY in config.py or GOOGLE_MAPS_API_KEY in the environment"
        )

    inventory = load_inventory(args.inventory)
    targets: Iterable[dict[str, Any]] = iter_targets(inventory, args.scope)
    if args.limit is not None:
        targets = islice(targets, args.limit)

    action = "Would fetch" if args.dry_run else "Fetching"
    requested_count = 0
    success_count = 0
    failures: list[dict[str, Any]] = []
    for requested_count, target in enumerate(targets, start=1):
        print(
            f"[{requested_count}] {action} {target['target_type']}: "
            f"{target['name']} "
            f"({target['latitude']:.6f}, {target['longitude']:.6f})"
        )
        if args.dry_run:
            continue
        try:
            image_path = fetch_satellite_image(target)
        except SatelliteImageFetchError as error:
            failure = {
                "target_id": target["id"],
                "target_type": target["target_type"],
                "name": target["name"],
                "status_code": error.status_code,
                "attempts": error.attempts,
            }
            failures.append(failure)
            print(f"Failed {target['id']}: {error}", file=sys.stderr)
            continue
        log_metadata(target, image_path)
        success_count += 1

    if args.dry_run:
        print(f"Processed {requested_count} target(s).")
        return

    report = write_capture_report(
        args.report_file, requested_count, success_count, failures
    )
    print(
        f"Processed {requested_count} target(s): {success_count} succeeded, "
        f"{len(failures)} failed ({report['status']})."
    )
    if requested_count and not success_count:
        raise RuntimeError("Every satellite image request failed")


if __name__ == "__main__":
    main()
