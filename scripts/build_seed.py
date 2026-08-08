#!/usr/bin/env python3
"""Generate the deterministic infra-inventory-v0.1.0 SQL seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "infra_timelapse_ports_corridors.json"
OUTPUT_DIR = ROOT / "db" / "seeds" / "infra-inventory-v0.1.0"
SEED_VERSION = "infra-inventory-v0.1.0"
SOURCE_UPDATED_AT = "2026-08-02T05:46:46Z"
STATUS_AS_OF = "2026-08-02"
PROJECT_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://github.com/seanwestfall/infra_timelapse",
)


COUNTRIES: dict[str, tuple[str, str]] = {
    "AE": ("ARE", "United Arab Emirates"),
    "AO": ("AGO", "Angola"),
    "AU": ("AUS", "Australia"),
    "BD": ("BGD", "Bangladesh"),
    "BR": ("BRA", "Brazil"),
    "CI": ("CIV", "Côte d’Ivoire"),
    "CM": ("CMR", "Cameroon"),
    "CN": ("CHN", "China"),
    "DE": ("DEU", "Germany"),
    "DJ": ("DJI", "Djibouti"),
    "DZ": ("DZA", "Algeria"),
    "EG": ("EGY", "Egypt"),
    "ER": ("ERI", "Eritrea"),
    "ES": ("ESP", "Spain"),
    "GH": ("GHA", "Ghana"),
    "GI": ("GIB", "Gibraltar"),
    "GN": ("GIN", "Guinea"),
    "GQ": ("GNQ", "Equatorial Guinea"),
    "GR": ("GRC", "Greece"),
    "HN": ("HND", "Honduras"),
    "ID": ("IDN", "Indonesia"),
    "IL": ("ISR", "Israel"),
    "IR": ("IRN", "Iran"),
    "KE": ("KEN", "Kenya"),
    "KH": ("KHM", "Cambodia"),
    "KW": ("KWT", "Kuwait"),
    "KZ": ("KAZ", "Kazakhstan"),
    "LK": ("LKA", "Sri Lanka"),
    "MA": ("MAR", "Morocco"),
    "MM": ("MMR", "Myanmar"),
    "MR": ("MRT", "Mauritania"),
    "MY": ("MYS", "Malaysia"),
    "MZ": ("MOZ", "Mozambique"),
    "NG": ("NGA", "Nigeria"),
    "NI": ("NIC", "Nicaragua"),
    "OM": ("OMN", "Oman"),
    "PA": ("PAN", "Panama"),
    "PE": ("PER", "Peru"),
    "PK": ("PAK", "Pakistan"),
    "PL": ("POL", "Poland"),
    "RU": ("RUS", "Russia"),
    "SG": ("SGP", "Singapore"),
    "SL": ("SLE", "Sierra Leone"),
    "TH": ("THA", "Thailand"),
    "TR": ("TUR", "Türkiye"),
    "TW": ("TWN", "Taiwan"),
    "TZ": ("TZA", "Tanzania"),
    "US": ("USA", "United States"),
    "YE": ("YEM", "Yemen"),
    "ZA": ("ZAF", "South Africa"),
}


CORRIDOR_RULES: dict[str, dict[str, str]] = {
    "new_eurasian_land_bridge": {
        "code": "cor-nelb",
        "lifecycle": "operational",
        "relationship": "official_bri_designation",
    },
    "china_mongolia_russia": {
        "code": "cor-cmrec",
        "lifecycle": "partially_operational",
        "relationship": "official_bri_designation",
    },
    "china_central_asia_west_asia": {
        "code": "cor-ccawa",
        "lifecycle": "partially_operational",
        "relationship": "official_bri_designation",
    },
    "china_indochina_peninsula": {
        "code": "cor-cipc",
        "lifecycle": "partially_operational",
        "relationship": "official_bri_designation",
    },
    "cpec": {
        "code": "cor-cpec",
        "lifecycle": "partially_operational",
        "relationship": "official_bri_designation",
    },
    "bcim": {
        "code": "cor-bcim",
        "lifecycle": "dormant",
        "relationship": "official_bri_designation",
        "assertion": "contested",
    },
    "maritime_silk_road": {
        "code": "cor-msr",
        "lifecycle": "operational",
        "relationship": "official_bri_designation",
    },
    "china_europe_railway_express": {
        "code": "cor-cere",
        "lifecycle": "operational",
        "relationship": "bri_linked",
    },
    "trans_caspian_middle_corridor": {
        "code": "cor-titr",
        "lifecycle": "expanding",
        "relationship": "strategically_adjacent",
    },
    "new_international_land_sea": {
        "code": "cor-nilstc",
        "lifecycle": "operational",
        "relationship": "bri_linked",
    },
    "china_laos_pan_asian": {
        "code": "cor-clr",
        "lifecycle": "partially_operational",
        "relationship": "bri_linked",
    },
    "cku_railway": {
        "code": "cor-cku",
        "lifecycle": "under_construction",
        "relationship": "bri_linked",
    },
    "china_myanmar": {
        "code": "cor-cmec",
        "lifecycle": "partially_operational",
        "relationship": "bri_linked",
    },
    "piraeus_belgrade_budapest": {
        "code": "cor-pbb",
        "lifecycle": "partially_operational",
        "relationship": "bri_linked",
    },
    "addis_djibouti": {
        "code": "cor-aadj",
        "lifecycle": "operational",
        "relationship": "bri_linked",
    },
    "mombasa_nairobi_sgr": {
        "code": "cor-mombasa",
        "lifecycle": "partially_operational",
        "relationship": "bri_linked",
    },
    "tazara": {
        "code": "cor-tazara",
        "lifecycle": "operational",
        "relationship": "bri_linked",
    },
    "brazil_peru_bioceanic": {
        "code": "cor-bioceanic",
        "lifecycle": "feasibility",
        "relationship": "bri_linked",
    },
    "polar_silk_road_nsr": {
        "code": "cor-polar-nsr",
        "lifecycle": "partially_operational",
        "relationship": "bri_linked",
    },
}


PORT_CODE_OVERRIDES = {
    "lianyungang_port": "n-lianyungang-port",
    "xian_international_port": "n-xian-international-port",
    "khorgos_gateway_dry_port": "n-khorgos-eastern-gate-kz",
    "altynkol_gateway": "n-altynkol-rail-gateway",
    "qinzhou_beibu_gulf_port": "n-qinzhou-port",
    "gwadar_port": "n-gwadar-port",
    "karachi_port": "n-karachi-port",
    "port_qasim": "n-port-qasim",
    "hambantota_international_port": "n-hambantota-port",
    "colombo_cict": "n-cict-colombo",
    "kyaukphyu_deepwater_port": "n-kyaukphyu-port",
    "chattogram_port": "n-chattogram-port",
    "mongla_port": "n-mongla-port",
    "port_of_piraeus": "n-piraeus-port",
    "duisburg_inland_port": "n-duisburg-port",
    "malaszewicze_logistics_hub": "n-malaszewicze-hub",
    "doraleh_multipurpose_port": "n-doraleh-port",
    "damerjog_facilities": "n-damerjog-facilities",
    "pla_support_base_djibouti": "n-pla-base-djibouti",
    "khalifa_port": "n-khalifa-port",
    "csp_abu_dhabi_terminal": "n-csp-abu-dhabi-terminal",
    "port_of_duqm": "n-duqm-port",
    "haifa_bayport_terminal": "n-bayport-terminal",
    "kribi_deepwater_port": "n-kribi-port",
    "lekki_deep_sea_port": "n-lekki-port",
    "port_of_mombasa": "n-mombasa-port",
    "port_of_dar_es_salaam": "n-dar-es-salaam-port",
    "port_of_chancay": "n-chancay-port",
    "tcp_paranagua": "n-tcp-paranagua",
    "porto_sul": "n-porto-sul",
    "ream_naval_base": "n-ream-naval-base",
}


CANONICAL_NAME_OVERRIDES = {
    "khorgos_gateway_dry_port": "Khorgos Eastern Gate Dry Port",
    "altynkol_gateway": "Altynkol Rail Gateway",
    "qinzhou_beibu_gulf_port": "Qinzhou Port",
    "port_of_boffa_dapilon": "Port of Boffa",
    "haifa_bayport_terminal": "Bayport Terminal",
    "ream_naval_base": "Ream Naval Base",
}


ALIAS_ADDITIONS = {
    "malaszewicze_logistics_hub": ["Malaszewicze Logistics Hub"],
}


ASSET_TYPE_MAP = {
    "seaport": "seaport",
    "rail_logistics_hub": "rail_hub",
    "dry_port": "dry_port",
    "rail_border_gateway": "border_gateway",
    "deepwater_port": "seaport",
    "planned_deepwater_port": "seaport",
    "proposed_deepwater_port": "seaport",
    "planned_port": "seaport",
    "planned_seaport": "seaport",
    "multipurpose_port": "seaport",
    "container_terminal": "container_terminal",
    "seaport_terminal": "container_terminal",
    "inland_port": "inland_port",
    "lake_port": "inland_port",
    "port_industrial_complex": "port_complex",
    "military_logistics_base": "military_logistics_facility",
    "naval_logistics_facility": "naval_base",
    "fishing_port": "fishing_port",
    "bulk_export_port": "bulk_terminal",
    "bulk_liquid_terminal": "bulk_terminal",
    "coal_export_terminal": "bulk_terminal",
}


LIFECYCLE_MAP = {
    "operational": "operational",
    "operational_expanding": "expanding",
    "operational_or_under_development": "partially_operational",
    "operational_rehabilitated": "operational",
    "operational_with_proposals": "operational",
    "planned": "planned",
    "planned_or_delayed": "delayed",
    "proposed": "proposed",
    "under_development": "under_construction",
    "under_development_or_delayed": "delayed",
    "delayed_or_reconfigured": "delayed",
}


ADDED_NODES = [
    {
        "code": "n-horgos-gateway-cn",
        "name": "Horgos Gateway",
        "iso2": "CN",
        "node_type": "border_gateway",
        "tier": "priority",
        "aliases": ["Horgos Border Gateway"],
    },
    {
        "code": "n-beibu-gulf-port",
        "name": "Beibu Gulf Port",
        "iso2": "CN",
        "node_type": "port_system",
        "tier": "priority",
        "aliases": ["Guangxi Beibu Gulf Port"],
    },
    {
        "code": "n-colombo-port",
        "name": "Colombo Port",
        "iso2": "LK",
        "node_type": "port_complex",
        "tier": "priority",
        "aliases": ["Port of Colombo"],
    },
    {
        "code": "n-haifa-port",
        "name": "Haifa Port",
        "iso2": "IL",
        "node_type": "port_complex",
        "tier": "priority",
        "aliases": ["Port of Haifa"],
    },
    {
        "code": "n-ream-joint-logistics-centre",
        "name": "Joint Logistics and Training Centre",
        "iso2": "KH",
        "node_type": "military_logistics_facility",
        "tier": "watchlist",
        "aliases": ["Ream Joint Logistics and Training Centre"],
    },
]


PRIORITY_LIFECYCLES = {
    "n-altynkol-rail-gateway": "operational",
    "n-bayport-terminal": "operational",
    "n-beibu-gulf-port": "operational",
    "n-chancay-port": "operational",
    "n-chattogram-port": "operational",
    "n-cict-colombo": "operational",
    "n-colombo-port": "operational",
    "n-csp-abu-dhabi-terminal": "operational",
    "n-damerjog-facilities": "unknown",
    "n-dar-es-salaam-port": "operational",
    "n-doraleh-port": "operational",
    "n-duisburg-port": "operational",
    "n-duqm-port": "operational",
    "n-gwadar-port": "operational",
    "n-haifa-port": "operational",
    "n-hambantota-port": "operational",
    "n-horgos-gateway-cn": "operational",
    "n-karachi-port": "operational",
    "n-khalifa-port": "operational",
    "n-khorgos-eastern-gate-kz": "operational",
    "n-kribi-port": "operational",
    "n-kyaukphyu-port": "delayed",
    "n-lekki-port": "operational",
    "n-lianyungang-port": "operational",
    "n-malaszewicze-hub": "operational",
    "n-mombasa-port": "operational",
    "n-mongla-port": "operational",
    "n-piraeus-port": "operational",
    "n-pla-base-djibouti": "operational",
    "n-port-qasim": "operational",
    "n-porto-sul": "pledged",
    "n-qinzhou-port": "operational",
    "n-tcp-paranagua": "operational",
    "n-xian-international-port": "operational",
}


OVERLAY_JURISDICTIONS: dict[str, list[tuple[str, str]]] = {
    "strait_of_malacca": [("ID", "shoreline"), ("MY", "shoreline"), ("SG", "shoreline")],
    "sunda_strait": [("ID", "primary")],
    "lombok_strait": [("ID", "primary")],
    "strait_of_hormuz": [("IR", "shoreline"), ("OM", "shoreline")],
    "bab_el_mandeb": [("DJ", "shoreline"), ("ER", "shoreline"), ("YE", "shoreline")],
    "suez_canal": [("EG", "primary")],
    "bosporus": [("TR", "primary")],
    "dardanelles": [("TR", "primary")],
    "strait_of_gibraltar": [("ES", "shoreline"), ("GI", "shoreline"), ("MA", "shoreline")],
    "panama_canal": [("PA", "primary")],
    "cape_of_good_hope_route": [("ZA", "shoreline")],
    "taiwan_strait": [("CN", "shoreline"), ("TW", "shoreline")],
    "south_china_sea_approaches": [],
    "bering_strait_northern_sea_route": [("RU", "shoreline"), ("US", "shoreline")],
}


OVERLAY_CODE_OVERRIDES = {
    "bering_strait_northern_sea_route": "n-bering-strait",
    "south_china_sea_approaches": "n-south-china-sea-approaches",
    "cape_of_good_hope_route": "n-cape-of-good-hope-route",
}


PROJECTS = [
    ("prj-cku-railway", "China–Kyrgyzstan–Uzbekistan Railway", "railway", "under_construction", []),
    ("prj-pan-asian-southern-links", "Pan-Asian Railway Southern Links", "railway", "planned", []),
    ("prj-kyaukphyu-port-development", "Kyaukphyu Port Development", "port_development", "delayed", ["n-kyaukphyu-port"]),
    ("prj-cmec-port-rail-components", "China–Myanmar Port and Rail Components", "mixed_infrastructure", "delayed", ["n-kyaukphyu-port"]),
    ("prj-mongla-expansion", "Mongla Port Expansion", "port_expansion", "proposed", ["n-mongla-port"]),
    ("prj-pbb-rail-buildout", "Piraeus–Belgrade–Budapest Rail Buildout", "railway", "under_construction", ["n-piraeus-port"]),
    ("prj-mombasa-inland-extensions", "Mombasa Inland Extensions", "logistics", "planned", ["n-mombasa-port"]),
    ("prj-tazara-revitalization", "TAZARA Revitalization", "rehabilitation", "planned", ["n-dar-es-salaam-port"]),
    ("prj-brazil-peru-feasibility-study", "Brazil–Peru Bioceanic Feasibility Study", "feasibility_study", "feasibility", ["n-porto-sul", "n-chancay-port"]),
    ("prj-porto-sul-development", "Porto Sul Development", "port_development", "pledged", ["n-porto-sul"]),
]


NODE_RELATIONSHIPS: dict[str, list[str]] = {
    "n-gwadar-port": ["official_bri_designation"],
    "n-hambantota-port": ["official_bri_designation", "prc_owned", "prc_operated"],
    "n-piraeus-port": ["official_bri_designation", "prc_owned", "prc_operated"],
    "n-pla-base-djibouti": ["prc_security_presence"],
    "n-csp-abu-dhabi-terminal": ["official_bri_designation", "prc_operated"],
    "n-bayport-terminal": ["prc_financed", "prc_operated"],
    "n-kribi-port": ["prc_financed"],
    "n-lekki-port": ["prc_financed", "prc_owned", "prc_epc_contractor"],
    "n-chancay-port": ["prc_operated"],
    "n-tcp-paranagua": ["prc_owned"],
    "n-port-of-newcastle": ["prc_financed"],
    "n-port-of-melbourne": ["prc_financed"],
    "n-wiggins-island-coal-export-terminal": ["prc_financed"],
    "n-ream-joint-logistics-centre": ["prc_security_presence"],
}


NODE_LINKS = [
    ("n-beibu-gulf-port", "n-qinzhou-port", "contains"),
    ("n-colombo-port", "n-cict-colombo", "contains"),
    ("n-khalifa-port", "n-csp-abu-dhabi-terminal", "contains"),
    ("n-haifa-port", "n-bayport-terminal", "same_harbor"),
    ("n-ream-naval-base", "n-ream-joint-logistics-centre", "contains"),
    ("n-horgos-gateway-cn", "n-khorgos-eastern-gate-kz", "paired_with"),
]


ADDED_MEMBERSHIPS = [
    ("n-horgos-gateway-cn", "cor-nelb", "official_route", "border_crossing"),
    ("n-horgos-gateway-cn", "cor-cere", "linked", "border_crossing"),
    ("n-horgos-gateway-cn", "cor-titr", "linked", "gateway"),
    ("n-beibu-gulf-port", "cor-nilstc", "linked", "maritime_outlet"),
    ("n-colombo-port", "cor-msr", "linked", "transshipment_hub"),
    ("n-haifa-port", "cor-ccawa", "adjacent", "gateway"),
    ("n-haifa-port", "cor-msr", "linked", "gateway"),
    ("n-ream-joint-logistics-centre", "cor-msr", "linked", "security_support"),
]


ROLE_OVERRIDES: dict[tuple[str, str], tuple[str, str]] = {
    ("n-lianyungang-port", "cor-nelb"): ("official_route", "origin"),
    ("n-xian-international-port", "cor-nelb"): ("official_route", "rail_hub"),
    ("n-xian-international-port", "cor-cere"): ("linked", "rail_hub"),
    ("n-khorgos-eastern-gate-kz", "cor-nelb"): ("official_route", "transfer_point"),
    ("n-khorgos-eastern-gate-kz", "cor-cere"): ("linked", "transfer_point"),
    ("n-khorgos-eastern-gate-kz", "cor-titr"): ("linked", "transfer_point"),
    ("n-altynkol-rail-gateway", "cor-nelb"): ("official_route", "transfer_point"),
    ("n-qinzhou-port", "cor-nilstc"): ("linked", "maritime_outlet"),
    ("n-gwadar-port", "cor-cpec"): ("official_route", "terminus"),
    ("n-gwadar-port", "cor-msr"): ("linked", "anchor"),
    ("n-piraeus-port", "cor-pbb"): ("linked", "origin"),
    ("n-piraeus-port", "cor-msr"): ("linked", "gateway"),
    ("n-duisburg-port", "cor-nelb"): ("linked", "distribution_hub"),
    ("n-malaszewicze-hub", "cor-nelb"): ("linked", "transfer_point"),
    ("n-doraleh-port", "cor-aadj"): ("linked", "maritime_outlet"),
    ("n-pla-base-djibouti", "cor-msr"): ("linked", "security_support"),
    ("n-mombasa-port", "cor-mombasa"): ("linked", "maritime_outlet"),
    ("n-dar-es-salaam-port", "cor-tazara"): ("linked", "maritime_outlet"),
    ("n-chancay-port", "cor-bioceanic"): ("linked", "terminus"),
    ("n-porto-sul", "cor-bioceanic"): ("linked", "origin"),
}


@dataclass(frozen=True)
class RawSQL:
    value: str


def stable_uuid(scope: str, key: str) -> str:
    return str(uuid.uuid5(PROJECT_NAMESPACE, f"{scope}:{key}"))


def slug(value: str) -> str:
    value = value.replace("_", "-").casefold()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def normalized_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE)
    return normalized.strip("-")


def canonical_port_code(legacy_id: str) -> str:
    return PORT_CODE_OVERRIDES.get(legacy_id, f"n-{slug(legacy_id)}")


def canonical_overlay_code(legacy_id: str) -> str:
    return OVERLAY_CODE_OVERRIDES.get(legacy_id, f"n-{slug(legacy_id)}")


def sql_value(value: Any) -> str:
    if isinstance(value, RawSQL):
        return value.value
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def render_insert(
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    conflict_sql: str,
) -> str:
    rendered_rows = [
        "    (" + ", ".join(sql_value(value) for value in row) + ")"
        for row in rows
    ]
    if not rendered_rows:
        return f"-- No rows for {table}.\n"
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n"
        + ",\n".join(rendered_rows)
        + f"\n{conflict_sql};\n"
    )


def format_number(value: Any) -> str:
    return format(float(value), ".10g")


def point_ewkt(coordinates: Sequence[Any]) -> str:
    longitude, latitude = coordinates
    return f"SRID=4326;POINT({format_number(longitude)} {format_number(latitude)})"


def multiline_ewkt(lines: Sequence[Sequence[Sequence[Any]]]) -> str:
    components = []
    for line in lines:
        coordinates = ", ".join(
            f"{format_number(point[0])} {format_number(point[1])}" for point in line
        )
        components.append(f"({coordinates})")
    return "SRID=4326;MULTILINESTRING(" + ", ".join(components) + ")"


def multipoint_ewkt(points: Sequence[Sequence[Any]]) -> str:
    coordinates = ", ".join(
        f"({format_number(point[0])} {format_number(point[1])})" for point in points
    )
    return f"SRID=4326;MULTIPOINT({coordinates})"


def load_inventory() -> dict[str, Any]:
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    expected_counts = {
        "ports_and_logistics_nodes": 54,
        "corridors": 19,
        "chokepoints_and_route_overlays": 14,
        "corridor_waypoints": 150,
    }
    if inventory.get("inventory_counts") != expected_counts:
        raise ValueError(
            "Inventory counts changed. Review the normalization crosswalk and create "
            "a new seed version before regenerating SQL."
        )
    if inventory.get("crs", {}).get("epsg") != 4326:
        raise ValueError("The v0.1 inventory must use EPSG:4326")
    if inventory.get("crs", {}).get("coordinate_order") != "longitude, latitude":
        raise ValueError("The v0.1 inventory must use longitude, latitude ordering")
    return inventory


def validate_coordinate(coordinates: Sequence[Any], context: str) -> None:
    if len(coordinates) != 2:
        raise ValueError(f"{context} must contain exactly two coordinates")
    longitude, latitude = (float(coordinates[0]), float(coordinates[1]))
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError(f"{context} falls outside WGS84 longitude/latitude bounds")


def build_nodes(inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nodes: list[dict[str, Any]] = []
    legacy_to_code: dict[str, str] = {}

    for source_node in inventory["ports_and_logistics_nodes"]:
        legacy_id = source_node["id"]
        code = canonical_port_code(legacy_id)
        legacy_to_code[legacy_id] = code
        coordinates = source_node["coordinates"]
        validate_coordinate(coordinates, f"node {legacy_id}")
        aliases = list(source_node.get("aliases", []))
        aliases.extend(ALIAS_ADDITIONS.get(legacy_id, []))
        source_name = source_node["name"]
        canonical_name = CANONICAL_NAME_OVERRIDES.get(legacy_id, source_name)
        if canonical_name != source_name:
            aliases.append(source_name)
        nodes.append(
            {
                "legacy_id": legacy_id,
                "code": code,
                "name": canonical_name,
                "iso2": source_node["iso_country_code"],
                "node_type": ASSET_TYPE_MAP[source_node["asset_type"]],
                "tier": {
                    "pipeline_or_proposed": "watchlist"
                }.get(source_node["monitoring_tier"], source_node["monitoring_tier"]),
                "aliases": sorted(set(aliases)),
                "lifecycle": LIFECYCLE_MAP[source_node["project_status"]],
                "geometry": {
                    "role": "centroid",
                    "ewkt": point_ewkt(coordinates),
                    "source_legacy_id": source_node["coordinate_source_ids"][0],
                },
                "linked_corridor_ids": source_node.get("linked_corridor_ids", []),
            }
        )

    for added_node in ADDED_NODES:
        nodes.append(
            {
                **added_node,
                "legacy_id": None,
                "lifecycle": "unknown",
                "geometry": None,
                "linked_corridor_ids": [],
            }
        )

    for overlay in inventory["chokepoints_and_route_overlays"]:
        legacy_id = overlay["id"]
        code = canonical_overlay_code(legacy_id)
        legacy_to_code[legacy_id] = code
        geometry_type = overlay["geometry_type"]
        if legacy_id == "bering_strait_northern_sea_route":
            geometry = {
                "role": "centroid",
                "ewkt": point_ewkt([-169.0, 65.9]),
                "source_legacy_id": "github_issue_1",
            }
            canonical_name = "Bering Strait"
        elif geometry_type == "Point":
            validate_coordinate(overlay["coordinates"], f"overlay {legacy_id}")
            geometry = {
                "role": "centroid",
                "ewkt": point_ewkt(overlay["coordinates"]),
                "source_legacy_id": "github_issue_1",
            }
            canonical_name = overlay["name"]
        elif geometry_type == "LineString":
            points = [waypoint["coordinates"] for waypoint in overlay["waypoints"]]
            for index, coordinates in enumerate(points, start=1):
                validate_coordinate(coordinates, f"overlay {legacy_id} point {index}")
            geometry = {
                "role": "route_centerline",
                "ewkt": multiline_ewkt([points]),
                "source_legacy_id": "github_issue_1",
            }
            canonical_name = overlay["name"]
        elif geometry_type == "MultiPoint":
            points = [waypoint["coordinates"] for waypoint in overlay["waypoints"]]
            for index, coordinates in enumerate(points, start=1):
                validate_coordinate(coordinates, f"overlay {legacy_id} point {index}")
            geometry = {
                "role": "control_points",
                "ewkt": multipoint_ewkt(points),
                "source_legacy_id": "github_issue_1",
            }
            canonical_name = overlay["name"]
        else:
            raise ValueError(f"Unsupported overlay geometry type: {geometry_type}")

        if legacy_id in {"suez_canal", "panama_canal"}:
            node_type = "canal"
        elif legacy_id in {
            "strait_of_malacca",
            "sunda_strait",
            "lombok_strait",
            "strait_of_hormuz",
            "bab_el_mandeb",
            "bosporus",
            "dardanelles",
            "strait_of_gibraltar",
            "taiwan_strait",
            "bering_strait_northern_sea_route",
        }:
            node_type = "strait"
        else:
            node_type = "route_overlay"

        nodes.append(
            {
                "legacy_id": legacy_id,
                "code": code,
                "name": canonical_name,
                "iso2": None,
                "node_type": node_type,
                "tier": "overlay",
                "aliases": [],
                "lifecycle": "unknown",
                "geometry": geometry,
                "linked_corridor_ids": overlay.get("linked_corridor_ids", []),
            }
        )

    priority_codes = {node["code"] for node in nodes if node["tier"] == "priority"}
    if priority_codes != set(PRIORITY_LIFECYCLES):
        missing = sorted(set(PRIORITY_LIFECYCLES) - priority_codes)
        unexpected = sorted(priority_codes - set(PRIORITY_LIFECYCLES))
        raise ValueError(
            "Priority lifecycle crosswalk changed; "
            f"missing={missing}, unexpected={unexpected}"
        )

    for node in nodes:
        if node["tier"] == "priority":
            node["lifecycle"] = PRIORITY_LIFECYCLES[node["code"]]
        elif node["tier"] in {"expanded", "watchlist", "overlay"}:
            node["lifecycle"] = "unknown"
        else:
            raise ValueError(f"Unsupported monitoring tier: {node['tier']}")

    codes = [node["code"] for node in nodes]
    if len(nodes) != 73 or len(set(codes)) != 73:
        raise ValueError(
            f"Normalized node set must contain 73 unique codes; got {len(nodes)} "
            f"rows and {len(set(codes))} unique codes"
        )
    return sorted(nodes, key=lambda node: node["code"]), legacy_to_code


def build_corridors(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    corridors: list[dict[str, Any]] = []
    for source_corridor in inventory["corridors"]:
        legacy_id = source_corridor["id"]
        rule = CORRIDOR_RULES[legacy_id]
        lines: list[list[list[Any]]] = []
        for segment_index, segment in enumerate(source_corridor["route_segments"], start=1):
            points = [waypoint["coordinates"] for waypoint in segment["waypoints"]]
            if len(points) < 2:
                raise ValueError(
                    f"Corridor {legacy_id} segment {segment_index} requires two points"
                )
            for point_index, coordinates in enumerate(points, start=1):
                validate_coordinate(
                    coordinates,
                    f"corridor {legacy_id} segment {segment_index} point {point_index}",
                )
            for first, second in zip(points, points[1:]):
                if abs(float(first[0]) - float(second[0])) > 180:
                    raise ValueError(
                        f"Corridor {legacy_id} crosses the date line without a split"
                    )
            lines.append(points)

        if legacy_id in {"maritime_silk_road", "polar_silk_road_nsr"}:
            corridor_type = "maritime"
        elif len(source_corridor.get("route_type", [])) > 1:
            corridor_type = "multimodal"
        else:
            corridor_type = "land"

        corridors.append(
            {
                "legacy_id": legacy_id,
                "code": rule["code"],
                "name": source_corridor["name"],
                "lifecycle": rule["lifecycle"],
                "relationship": rule["relationship"],
                "assertion": rule.get("assertion", "reported"),
                "corridor_type": corridor_type,
                "service_pattern": (
                    "seasonal" if legacy_id == "polar_silk_road_nsr" else "continuous"
                ),
                "route_ewkt": multiline_ewkt(lines),
                "route_segments": source_corridor["route_segments"],
            }
        )
    if len(corridors) != 19:
        raise ValueError(f"Expected 19 corridors, got {len(corridors)}")
    return sorted(corridors, key=lambda corridor: corridor["code"])


def build_sources(inventory: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rules = {
        "github_issue_1": ("GitHub", "project_inventory", False),
        "upply_seaports": ("Upply", "dataset", False),
        "openstreetmap": ("OpenStreetMap contributors", "coordinate", False),
        "geonames": ("GeoNames", "coordinate", False),
        "official_and_open_sources": ("AidData", "dataset", True),
        "bri_framework": ("Belt and Road Portal", "official", True),
    }
    sources: list[dict[str, Any]] = []
    source_ids: dict[str, str] = {}
    for source in inventory["sources"]:
        legacy_id = source["id"]
        publisher, source_kind, is_substantive = rules[legacy_id]
        source_id = stable_uuid("source", source["url"])
        source_ids[legacy_id] = source_id
        sources.append(
            {
                "source_id": source_id,
                "url": source["url"],
                "title": source["name"],
                "publisher": publisher,
                "source_kind": source_kind,
                "is_substantive": is_substantive,
                "license_code": source.get("license"),
            }
        )
    return sources, source_ids


def build_model() -> dict[str, Any]:
    inventory = load_inventory()
    nodes, legacy_node_codes = build_nodes(inventory)
    corridors = build_corridors(inventory)
    sources, source_ids = build_sources(inventory)
    source_sha256 = hashlib.sha256(INVENTORY_PATH.read_bytes()).hexdigest()

    entity_rows: list[dict[str, Any]] = []
    for node in nodes:
        entity_rows.append(
            {
                "entity_id": stable_uuid("entity:node", node["code"]),
                "code": node["code"],
                "kind": "node",
                "name": node["name"],
                "lifecycle": node["lifecycle"],
            }
        )
    for corridor in corridors:
        entity_rows.append(
            {
                "entity_id": stable_uuid("entity:corridor", corridor["code"]),
                "code": corridor["code"],
                "kind": "corridor",
                "name": corridor["name"],
                "lifecycle": corridor["lifecycle"],
            }
        )
    for code, name, project_type, lifecycle, node_codes in PROJECTS:
        entity_rows.append(
            {
                "entity_id": stable_uuid("entity:project", code),
                "code": code,
                "kind": "project",
                "name": name,
                "lifecycle": lifecycle,
                "project_type": project_type,
                "node_codes": node_codes,
            }
        )

    entity_rows.sort(key=lambda entity: entity["code"])
    entity_ids = {entity["code"]: entity["entity_id"] for entity in entity_rows}
    corridor_codes = {
        corridor["legacy_id"]: corridor["code"] for corridor in corridors
    }
    return {
        "inventory": inventory,
        "nodes": nodes,
        "corridors": corridors,
        "sources": sources,
        "source_ids": source_ids,
        "source_sha256": source_sha256,
        "entities": entity_rows,
        "entity_ids": entity_ids,
        "legacy_node_codes": legacy_node_codes,
        "corridor_codes": corridor_codes,
    }


def generated_header(model: dict[str, Any]) -> str:
    return (
        "-- Generated by scripts/build_seed.py. Do not edit by hand.\n"
        f"-- Seed: {SEED_VERSION}\n"
        f"-- Source SHA-256: {model['source_sha256']}\n\n"
    )


def render_reference_seed(model: dict[str, Any]) -> str:
    used_country_codes = {
        node["iso2"] for node in model["nodes"] if node["iso2"] is not None
    }
    for jurisdictions in OVERLAY_JURISDICTIONS.values():
        used_country_codes.update(iso2 for iso2, _ in jurisdictions)
    missing = used_country_codes - COUNTRIES.keys()
    if missing:
        raise ValueError(f"Missing country reference rows: {sorted(missing)}")

    release_guard = f"""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM catalog.seed_releases
        WHERE seed_version = {sql_value(SEED_VERSION)}
          AND btrim(source_sha256) <> {sql_value(model['source_sha256'])}
    ) THEN
        RAISE EXCEPTION
            'seed version {SEED_VERSION} already exists with a different source checksum';
    END IF;
END;
$$;
"""
    release_insert = render_insert(
        "catalog.seed_releases",
        ["seed_version", "source_uri", "source_updated_at", "source_sha256"],
        [
            (
                SEED_VERSION,
                "https://github.com/seanwestfall/infra_timelapse/issues/1",
                RawSQL(f"{sql_value(SOURCE_UPDATED_AT)}::timestamptz"),
                model["source_sha256"],
            )
        ],
        "ON CONFLICT (seed_version) DO NOTHING",
    )
    countries_insert = render_insert(
        "catalog.countries",
        ["iso2", "iso3", "name"],
        [
            (iso2, COUNTRIES[iso2][0], COUNTRIES[iso2][1])
            for iso2 in sorted(used_country_codes)
        ],
        "ON CONFLICT (iso2) DO UPDATE SET iso3 = EXCLUDED.iso3, name = EXCLUDED.name",
    )
    sources_insert = render_insert(
        "evidence.sources",
        [
            "source_id",
            "url",
            "title",
            "publisher",
            "source_kind",
            "is_substantive",
            "accessed_on",
            "license_code",
        ],
        [
            (
                source["source_id"],
                source["url"],
                source["title"],
                source["publisher"],
                source["source_kind"],
                source["is_substantive"],
                RawSQL(f"{sql_value(STATUS_AS_OF)}::date"),
                source["license_code"],
            )
            for source in model["sources"]
        ],
        """ON CONFLICT (url) DO UPDATE SET
    title = EXCLUDED.title,
    publisher = EXCLUDED.publisher,
    source_kind = EXCLUDED.source_kind,
    accessed_on = EXCLUDED.accessed_on,
    license_code = EXCLUDED.license_code""",
    )
    return generated_header(model) + release_guard + release_insert + countries_insert + sources_insert


def render_entities_seed(model: dict[str, Any]) -> str:
    entity_insert = render_insert(
        "catalog.entities",
        ["entity_id", "code", "entity_kind", "canonical_name", "record_status"],
        [
            (
                entity["entity_id"],
                entity["code"],
                entity["kind"],
                entity["name"],
                "draft",
            )
            for entity in model["entities"]
        ],
        "ON CONFLICT (code) DO UPDATE SET canonical_name = EXCLUDED.canonical_name",
    )
    release_entities = render_insert(
        "catalog.seed_release_entities",
        ["seed_version", "entity_id"],
        [(SEED_VERSION, entity["entity_id"]) for entity in model["entities"]],
        "ON CONFLICT (seed_version, entity_id) DO NOTHING",
    )
    nodes_insert = render_insert(
        "catalog.nodes",
        ["entity_id", "node_type", "monitoring_tier"],
        [
            (model["entity_ids"][node["code"]], node["node_type"], node["tier"])
            for node in model["nodes"]
        ],
        """ON CONFLICT (entity_id) DO UPDATE SET
    node_type = EXCLUDED.node_type,
    monitoring_tier = EXCLUDED.monitoring_tier""",
    )
    corridors_insert = render_insert(
        "catalog.corridors",
        ["entity_id", "corridor_type", "service_pattern"],
        [
            (
                model["entity_ids"][corridor["code"]],
                corridor["corridor_type"],
                corridor["service_pattern"],
            )
            for corridor in model["corridors"]
        ],
        """ON CONFLICT (entity_id) DO UPDATE SET
    corridor_type = EXCLUDED.corridor_type,
    service_pattern = EXCLUDED.service_pattern""",
    )
    projects_insert = render_insert(
        "catalog.projects",
        ["entity_id", "project_type"],
        [
            (entity["entity_id"], entity["project_type"])
            for entity in model["entities"]
            if entity["kind"] == "project"
        ],
        "ON CONFLICT (entity_id) DO UPDATE SET project_type = EXCLUDED.project_type",
    )
    return (
        generated_header(model)
        + entity_insert
        + release_entities
        + nodes_insert
        + corridors_insert
        + projects_insert
    )


def render_node_details_seed(model: dict[str, Any]) -> str:
    alias_rows = []
    jurisdiction_rows = []
    geometry_rows = []
    issue_source_id = model["source_ids"]["github_issue_1"]

    for node in model["nodes"]:
        node_id = model["entity_ids"][node["code"]]
        for alias in node["aliases"]:
            alias_rows.append((node_id, normalized_alias(alias), "und", alias))

        if node["legacy_id"] in OVERLAY_JURISDICTIONS:
            for iso2, role in OVERLAY_JURISDICTIONS[node["legacy_id"]]:
                jurisdiction_rows.append((node_id, iso2, role))
        elif node["iso2"] is not None:
            jurisdiction_rows.append((node_id, node["iso2"], "primary"))

        geometry = node["geometry"]
        if geometry is not None:
            source_id = model["source_ids"].get(
                geometry["source_legacy_id"], issue_source_id
            )
            geometry_id = stable_uuid(
                "node-geometry",
                f"{node['code']}:{geometry['role']}:{source_id}:v1",
            )
            geometry_rows.append(
                (
                    geometry_id,
                    node_id,
                    geometry["role"],
                    RawSQL(f"ST_GeomFromEWKT({sql_value(geometry['ewkt'])})"),
                    source_id,
                    "source",
                    "draft",
                    True,
                )
            )

    aliases_insert = render_insert(
        "catalog.node_aliases",
        ["node_id", "normalized_alias", "language_tag", "alias"],
        sorted(set(alias_rows)),
        """ON CONFLICT (node_id, normalized_alias, language_tag) DO UPDATE SET
    alias = EXCLUDED.alias""",
    )
    jurisdictions_insert = render_insert(
        "catalog.node_jurisdictions",
        ["node_id", "country_iso2", "jurisdiction_role"],
        sorted(set(jurisdiction_rows)),
        "ON CONFLICT (node_id, country_iso2, jurisdiction_role) DO NOTHING",
    )
    geometries_insert = render_insert(
        "catalog.node_geometries",
        [
            "geometry_id",
            "node_id",
            "geometry_role",
            "geom",
            "source_id",
            "derivation_kind",
            "record_status",
            "is_current",
        ],
        geometry_rows,
        """ON CONFLICT (geometry_id) DO UPDATE SET
    geom = EXCLUDED.geom,
    source_id = EXCLUDED.source_id,
    derivation_kind = EXCLUDED.derivation_kind""",
    )
    links_insert = render_insert(
        "catalog.node_links",
        ["from_node_id", "to_node_id", "link_type"],
        [
            (
                model["entity_ids"][from_code],
                model["entity_ids"][to_code],
                link_type,
            )
            for from_code, to_code, link_type in NODE_LINKS
        ],
        "ON CONFLICT (from_node_id, to_node_id, link_type) DO NOTHING",
    )
    return generated_header(model) + aliases_insert + jurisdictions_insert + geometries_insert + links_insert


def build_memberships(model: dict[str, Any]) -> list[tuple[Any, ...]]:
    rows: dict[tuple[str, str, str, str], tuple[Any, ...]] = {}
    node_pair_seen: set[tuple[str, str]] = set()
    node_by_legacy = model["legacy_node_codes"]
    corridor_by_legacy = model["corridor_codes"]

    for corridor in model["corridors"]:
        corridor_code = corridor["code"]
        corridor_id = model["entity_ids"][corridor_code]
        for segment_index, segment in enumerate(corridor["route_segments"], start=1):
            branch_code = f"segment-{segment_index:02d}"
            waypoints = segment["waypoints"]
            for sequence_no, waypoint in enumerate(waypoints, start=1):
                legacy_node_id = waypoint.get("node_id")
                if legacy_node_id is None:
                    continue
                node_code = node_by_legacy[legacy_node_id]
                node_id = model["entity_ids"][node_code]
                default_role = (
                    "origin"
                    if sequence_no == 1
                    else "terminus"
                    if sequence_no == len(waypoints)
                    else "intermediate"
                )
                membership, role = ROLE_OVERRIDES.get(
                    (node_code, corridor_code), ("linked", default_role)
                )
                key = (corridor_code, node_code, branch_code, role)
                rows[key] = (
                    corridor_id,
                    node_id,
                    branch_code,
                    role,
                    membership,
                    sequence_no,
                )
                node_pair_seen.add((node_code, corridor_code))

    for node in model["nodes"]:
        if node["tier"] == "overlay":
            continue
        node_code = node["code"]
        for legacy_corridor_id in node["linked_corridor_ids"]:
            corridor_code = corridor_by_legacy[legacy_corridor_id]
            if (node_code, corridor_code) in node_pair_seen:
                continue
            default_membership = (
                "adjacent" if node["tier"] in {"expanded", "watchlist"} else "linked"
            )
            default_role = (
                "adjacent" if default_membership == "adjacent" else "intermediate"
            )
            membership, role = ROLE_OVERRIDES.get(
                (node_code, corridor_code), (default_membership, default_role)
            )
            key = (corridor_code, node_code, "inventory", role)
            rows[key] = (
                model["entity_ids"][corridor_code],
                model["entity_ids"][node_code],
                "inventory",
                role,
                membership,
                None,
            )

    for node_code, corridor_code, membership, role in ADDED_MEMBERSHIPS:
        key = (corridor_code, node_code, "inventory", role)
        rows[key] = (
            model["entity_ids"][corridor_code],
            model["entity_ids"][node_code],
            "inventory",
            role,
            membership,
            None,
        )

    for overlay in model["inventory"]["chokepoints_and_route_overlays"]:
        node_code = model["legacy_node_codes"][overlay["id"]]
        for legacy_corridor_id in overlay["linked_corridor_ids"]:
            corridor_code = corridor_by_legacy[legacy_corridor_id]
            key = (corridor_code, node_code, "overlay", "overlay")
            rows[key] = (
                model["entity_ids"][corridor_code],
                model["entity_ids"][node_code],
                "overlay",
                "overlay",
                "overlay",
                None,
            )
    return [rows[key] for key in sorted(rows)]


def render_network_seed(model: dict[str, Any]) -> str:
    geonames_source_id = model["source_ids"]["geonames"]
    corridor_geometry_insert = render_insert(
        "catalog.corridor_geometries",
        [
            "geometry_id",
            "corridor_id",
            "branch_code",
            "geometry_role",
            "route_geometry",
            "source_id",
            "derivation_kind",
            "record_status",
            "is_current",
        ],
        [
            (
                stable_uuid("corridor-geometry", f"{corridor['code']}:schematic:v1"),
                model["entity_ids"][corridor["code"]],
                "main",
                "schematic",
                RawSQL(
                    f"ST_GeomFromEWKT({sql_value(corridor['route_ewkt'])})"
                ),
                geonames_source_id,
                "normalized",
                "draft",
                True,
            )
            for corridor in model["corridors"]
        ],
        """ON CONFLICT (geometry_id) DO UPDATE SET
    route_geometry = EXCLUDED.route_geometry,
    source_id = EXCLUDED.source_id,
    derivation_kind = EXCLUDED.derivation_kind""",
    )
    memberships_insert = render_insert(
        "catalog.corridor_nodes",
        [
            "corridor_id",
            "node_id",
            "branch_code",
            "role",
            "membership_type",
            "sequence_no",
        ],
        build_memberships(model),
        """ON CONFLICT (corridor_id, node_id, branch_code, role) DO UPDATE SET
    membership_type = EXCLUDED.membership_type,
    sequence_no = EXCLUDED.sequence_no""",
    )
    project_nodes_insert = render_insert(
        "catalog.project_nodes",
        ["project_id", "node_id", "role"],
        [
            (
                model["entity_ids"][project_code],
                model["entity_ids"][node_code],
                "site",
            )
            for project_code, _name, _project_type, _lifecycle, node_codes in PROJECTS
            for node_code in node_codes
        ],
        "ON CONFLICT (project_id, node_id, role) DO NOTHING",
    )
    return generated_header(model) + corridor_geometry_insert + memberships_insert + project_nodes_insert


def render_claims_seed(model: dict[str, Any]) -> str:
    issue_source_id = model["source_ids"]["github_issue_1"]
    relationship_rows = []
    relationship_source_rows = []

    for corridor in model["corridors"]:
        relationship_id = stable_uuid(
            "relationship",
            f"{corridor['code']}:{corridor['relationship']}:{STATUS_AS_OF}",
        )
        relationship_rows.append(
            (
                relationship_id,
                model["entity_ids"][corridor["code"]],
                corridor["relationship"],
                corridor["assertion"],
                RawSQL(f"{sql_value(STATUS_AS_OF)}::date"),
            )
        )
        relationship_source_rows.append(
            (relationship_id, issue_source_id, "provenance", "Issue #1")
        )

    for node_code, relationship_types in sorted(NODE_RELATIONSHIPS.items()):
        for relationship_type in relationship_types:
            relationship_id = stable_uuid(
                "relationship", f"{node_code}:{relationship_type}:{STATUS_AS_OF}"
            )
            relationship_rows.append(
                (
                    relationship_id,
                    model["entity_ids"][node_code],
                    relationship_type,
                    "reported",
                    RawSQL(f"{sql_value(STATUS_AS_OF)}::date"),
                )
            )
            relationship_source_rows.append(
                (relationship_id, issue_source_id, "provenance", "Issue #1")
            )

    relationships_insert = render_insert(
        "evidence.entity_relationships",
        [
            "relationship_id",
            "subject_entity_id",
            "relationship_type",
            "assertion_status",
            "status_as_of",
        ],
        relationship_rows,
        """ON CONFLICT (relationship_id) DO UPDATE SET
    relationship_type = EXCLUDED.relationship_type,
    status_as_of = EXCLUDED.status_as_of""",
    )
    relationship_sources_insert = render_insert(
        "evidence.relationship_sources",
        ["relationship_id", "source_id", "evidence_role", "source_locator"],
        relationship_source_rows,
        """ON CONFLICT (relationship_id, source_id) DO UPDATE SET
    evidence_role = EXCLUDED.evidence_role,
    source_locator = EXCLUDED.source_locator""",
    )

    status_rows = []
    status_source_rows = []
    for entity in model["entities"]:
        status_id = stable_uuid(
            "status",
            f"{entity['code']}:{entity['lifecycle']}:{STATUS_AS_OF}",
        )
        status_rows.append(
            (
                status_id,
                entity["entity_id"],
                entity["lifecycle"],
                "reported",
                RawSQL(f"{sql_value(STATUS_AS_OF)}::date"),
                RawSQL(f"{sql_value(STATUS_AS_OF)}::date"),
            )
        )
        status_source_rows.append(
            (status_id, issue_source_id, "provenance", "Issue #1")
        )

    statuses_insert = render_insert(
        "evidence.entity_status_history",
        [
            "status_id",
            "entity_id",
            "lifecycle_status",
            "assertion_status",
            "status_as_of",
            "effective_from",
        ],
        status_rows,
        """ON CONFLICT (status_id) DO UPDATE SET
    status_as_of = EXCLUDED.status_as_of,
    effective_from = EXCLUDED.effective_from""",
    )
    status_sources_insert = render_insert(
        "evidence.status_sources",
        ["status_id", "source_id", "evidence_role", "source_locator"],
        status_source_rows,
        """ON CONFLICT (status_id, source_id) DO UPDATE SET
    evidence_role = EXCLUDED.evidence_role,
    source_locator = EXCLUDED.source_locator""",
    )
    return (
        generated_header(model)
        + relationships_insert
        + relationship_sources_insert
        + statuses_insert
        + status_sources_insert
    )


def render_validation_seed(model: dict[str, Any]) -> str:
    expected_uuid_values = ",\n".join(
        f"                ({sql_value(entity['code'])}, {sql_value(entity['entity_id'])}::uuid)"
        for entity in model["entities"]
    )
    return generated_header(model) + f"""
DO $$
DECLARE
    actual_count integer;
BEGIN
    SELECT count(*) INTO actual_count
    FROM catalog.seed_release_entities AS release_entities
    JOIN catalog.entities AS entities
      ON entities.entity_id = release_entities.entity_id
    WHERE release_entities.seed_version = {sql_value(SEED_VERSION)}
      AND entities.entity_kind = 'node';
    IF actual_count <> 73 THEN
        RAISE EXCEPTION 'expected 73 seed nodes, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM catalog.seed_release_entities AS release_entities
    JOIN catalog.entities AS entities
      ON entities.entity_id = release_entities.entity_id
    WHERE release_entities.seed_version = {sql_value(SEED_VERSION)}
      AND entities.entity_kind = 'corridor';
    IF actual_count <> 19 THEN
        RAISE EXCEPTION 'expected 19 seed corridors, found %', actual_count;
    END IF;

    SELECT count(*) INTO actual_count
    FROM catalog.seed_release_entities AS release_entities
    JOIN catalog.entities AS entities
      ON entities.entity_id = release_entities.entity_id
    WHERE release_entities.seed_version = {sql_value(SEED_VERSION)}
      AND entities.entity_kind = 'project';
    IF actual_count <> 10 THEN
        RAISE EXCEPTION 'expected 10 seed projects, found %', actual_count;
    END IF;

    IF EXISTS (
        WITH expected(code, entity_id) AS (
            VALUES
{expected_uuid_values}
        )
        SELECT 1
        FROM expected
        LEFT JOIN catalog.entities USING (code)
        WHERE entities.entity_id IS DISTINCT FROM expected.entity_id
    ) THEN
        RAISE EXCEPTION 'one or more entity UUIDv5 values are not reproducible';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.entities AS entities
        JOIN catalog.seed_release_entities AS release_entities
          ON release_entities.entity_id = entities.entity_id
        WHERE release_entities.seed_version = {sql_value(SEED_VERSION)}
          AND entities.entity_kind = 'node'
          AND entities.canonical_name LIKE '%/%'
    ) THEN
        RAISE EXCEPTION 'canonical seed node names must not combine facilities with /';
    END IF;

    IF EXISTS (
        WITH expected(code, normalized_alias) AS (
            VALUES
                ('n-chattogram-port', 'chittagong-port'),
                ('n-el-hamdania-deepwater-port', 'hamdania-port'),
                ('n-malaszewicze-hub', 'malaszewicze-logistics-hub')
        )
        SELECT 1
        FROM expected
        JOIN catalog.entities USING (code)
        LEFT JOIN catalog.node_aliases
          ON node_aliases.node_id = entities.entity_id
         AND node_aliases.normalized_alias = expected.normalized_alias
        WHERE node_aliases.node_id IS NULL
    ) THEN
        RAISE EXCEPTION 'one or more required normalized aliases are missing';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.node_geometries
        WHERE ST_SRID(geom) <> 4326
           OR ST_NDims(geom) <> 2
           OR ST_IsEmpty(geom)
    ) THEN
        RAISE EXCEPTION 'seed node geometries must be nonempty 2D EPSG:4326 values';
    END IF;

    SELECT count(*) INTO actual_count
    FROM catalog.corridor_geometries AS corridor_geometries
    JOIN catalog.seed_release_entities AS release_entities
      ON release_entities.entity_id = corridor_geometries.corridor_id
    WHERE release_entities.seed_version = {sql_value(SEED_VERSION)};
    IF actual_count <> 19 THEN
        RAISE EXCEPTION 'expected 19 seed corridor geometries, found %', actual_count;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.seed_release_entities AS release_entities
        JOIN catalog.entities AS entities
          ON entities.entity_id = release_entities.entity_id
        LEFT JOIN catalog.nodes ON catalog.nodes.entity_id = entities.entity_id
        LEFT JOIN catalog.corridors ON catalog.corridors.entity_id = entities.entity_id
        LEFT JOIN catalog.projects ON catalog.projects.entity_id = entities.entity_id
        WHERE release_entities.seed_version = {sql_value(SEED_VERSION)}
          AND (
              (entities.entity_kind = 'node' AND catalog.nodes.entity_id IS NULL)
              OR (entities.entity_kind = 'corridor' AND catalog.corridors.entity_id IS NULL)
              OR (entities.entity_kind = 'project' AND catalog.projects.entity_id IS NULL)
          )
    ) THEN
        RAISE EXCEPTION 'one or more seed entities are missing their subtype row';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM catalog.node_links AS links
        JOIN catalog.entities AS parent ON parent.entity_id = links.from_node_id
        JOIN catalog.entities AS child ON child.entity_id = links.to_node_id
        WHERE parent.code = 'n-ream-naval-base'
          AND child.code = 'n-ream-joint-logistics-centre'
          AND links.link_type = 'contains'
    ) THEN
        RAISE EXCEPTION 'Ream facilities were not normalized into linked nodes';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.nodes AS nodes
        JOIN catalog.corridor_nodes AS corridor_nodes
          ON corridor_nodes.node_id = nodes.entity_id
        WHERE nodes.monitoring_tier = 'overlay'
          AND (
              corridor_nodes.membership_type <> 'overlay'
              OR corridor_nodes.role <> 'overlay'
          )
    ) THEN
        RAISE EXCEPTION 'chokepoints and route overlays must use overlay membership only';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.nodes AS nodes
        JOIN evidence.entity_relationships AS relationships
          ON relationships.subject_entity_id = nodes.entity_id
        WHERE nodes.monitoring_tier = 'overlay'
    ) THEN
        RAISE EXCEPTION 'chokepoints and route overlays must not carry BRI/PRC assertions';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.nodes AS nodes
        JOIN evidence.entity_status_history AS status_history
          ON status_history.entity_id = nodes.entity_id
        WHERE nodes.monitoring_tier IN ('expanded', 'watchlist', 'overlay')
          AND status_history.effective_to IS NULL
          AND status_history.assertion_status <> 'superseded'
          AND status_history.lifecycle_status <> 'unknown'
    ) THEN
        RAISE EXCEPTION
            'expanded, watchlist, and overlay lifecycle claims must begin unknown';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM catalog.project_parties AS first_party
        JOIN catalog.project_parties AS second_party
          ON second_party.party_id > first_party.party_id
         AND second_party.project_id = first_party.project_id
         AND second_party.organization_id = first_party.organization_id
         AND second_party.party_role = first_party.party_role
         AND daterange(
                 COALESCE(second_party.effective_from, '-infinity'::date),
                 COALESCE(second_party.effective_to, 'infinity'::date),
                 '[]'
             ) && daterange(
                 COALESCE(first_party.effective_from, '-infinity'::date),
                 COALESCE(first_party.effective_to, 'infinity'::date),
                 '[]'
             )
    ) THEN
        RAISE EXCEPTION 'project party roles must not have overlapping effective periods';
    END IF;
END;
$$;

ANALYZE catalog.entities;
ANALYZE catalog.node_geometries;
ANALYZE catalog.corridor_geometries;

SELECT
    {sql_value(SEED_VERSION)} AS seed_version,
    count(*) FILTER (WHERE entities.entity_kind = 'node') AS node_count,
    count(*) FILTER (WHERE entities.entity_kind = 'corridor') AS corridor_count,
    count(*) FILTER (WHERE entities.entity_kind = 'project') AS project_count
FROM catalog.seed_release_entities AS release_entities
JOIN catalog.entities AS entities
  ON entities.entity_id = release_entities.entity_id
WHERE release_entities.seed_version = {sql_value(SEED_VERSION)};
"""


def render_outputs(model: dict[str, Any]) -> dict[str, str]:
    return {
        "seed.sql": """\\set ON_ERROR_STOP on
BEGIN;
\\ir 001_countries_and_sources.sql
\\ir 002_entities_and_subtypes.sql
\\ir 003_node_details_and_geometries.sql
\\ir 004_network_and_projects.sql
\\ir 005_claims_and_status.sql
\\ir 099_validate.sql
COMMIT;
""",
        "001_countries_and_sources.sql": render_reference_seed(model),
        "002_entities_and_subtypes.sql": render_entities_seed(model),
        "003_node_details_and_geometries.sql": render_node_details_seed(model),
        "004_network_and_projects.sql": render_network_seed(model),
        "005_claims_and_status.sql": render_claims_seed(model),
        "099_validate.sql": render_validation_seed(model),
    }


def write_or_check(outputs: dict[str, str], check: bool) -> None:
    failures: list[str] = []
    if not check:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, content in outputs.items():
        path = OUTPUT_DIR / filename
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                failures.append(filename)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if failures:
        raise RuntimeError(
            "Generated seed files are stale: "
            + ", ".join(failures)
            + ". Run scripts/build_seed.py and commit the results."
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed seed SQL differs from freshly generated output",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        model = build_model()
        write_or_check(render_outputs(model), args.check)
        print(
            f"validated {len(model['nodes'])} nodes, "
            f"{len(model['corridors'])} corridors, and {len(PROJECTS)} projects"
        )
    except (KeyError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
