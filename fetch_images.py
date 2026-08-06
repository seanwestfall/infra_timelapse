from __future__ import annotations

import argparse
import json
import os
import re
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


def iter_ports(inventory: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Yield one satellite-image target for each port or logistics node."""
    for port in inventory["ports_and_logistics_nodes"]:
        port_id = str(port["id"])
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
        corridor_id = str(corridor["id"])
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
                waypoint_id = (
                    f"{corridor_id}-{segment_index:02d}-{waypoint_index:03d}"
                )
                yield {
                    "id": waypoint_id,
                    "target_type": "corridor_waypoint",
                    "name": f"{corridor_name} — {waypoint_name}",
                    "latitude": latitude,
                    "longitude": longitude,
                    "zoom": int(waypoint.get("zoom", CORRIDOR_ZOOM)),
                    "output_parts": (
                        "corridors",
                        corridor_id,
                        f"segment-{segment_index:02d}",
                        f"{waypoint_index:03d}-{slugify(waypoint_name)}",
                    ),
                    "corridor_id": corridor_id,
                    "corridor_name": corridor_name,
                    "segment_index": segment_index,
                    "segment_name": segment_name,
                    "waypoint_index": waypoint_index,
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


def slugify(value: str) -> str:
    """Create a stable, filesystem-safe path component."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug or "waypoint"


def fetch_satellite_image(target: dict[str, Any]) -> Path:
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

    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
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
    processed = 0
    for processed, target in enumerate(targets, start=1):
        print(
            f"[{processed}] {action} {target['target_type']}: "
            f"{target['name']} "
            f"({target['latitude']:.6f}, {target['longitude']:.6f})"
        )
        if args.dry_run:
            continue
        image_path = fetch_satellite_image(target)
        log_metadata(target, image_path)

    print(f"Processed {processed} target(s).")


if __name__ == "__main__":
    main()
