from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_seed  # noqa: E402


class BuildSeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = build_seed.build_model()

    def test_normalized_inventory_counts(self) -> None:
        self.assertEqual(len(self.model["nodes"]), 73)
        self.assertEqual(len(self.model["corridors"]), 19)
        self.assertEqual(len(build_seed.PROJECTS), 10)
        self.assertEqual(
            self.model["inventory"]["inventory_counts"]["corridor_waypoints"],
            150,
        )

    def test_composite_records_are_split(self) -> None:
        codes = {node["code"] for node in self.model["nodes"]}
        required = {
            "n-horgos-gateway-cn",
            "n-khorgos-eastern-gate-kz",
            "n-beibu-gulf-port",
            "n-qinzhou-port",
            "n-colombo-port",
            "n-cict-colombo",
            "n-haifa-port",
            "n-bayport-terminal",
            "n-ream-naval-base",
            "n-ream-joint-logistics-centre",
        }
        self.assertTrue(required.issubset(codes))
        self.assertFalse(
            any("/" in node["name"] for node in self.model["nodes"]),
            "canonical node names must not combine independent facilities",
        )

        malaszewicze = next(
            node
            for node in self.model["nodes"]
            if node["code"] == "n-malaszewicze-hub"
        )
        self.assertIn("Malaszewicze Logistics Hub", malaszewicze["aliases"])

    def test_entity_ids_are_uuidv5_and_reproducible(self) -> None:
        entity = next(
            entity
            for entity in self.model["entities"]
            if entity["code"] == "n-lianyungang-port"
        )
        expected = build_seed.stable_uuid(
            "entity:node", "n-lianyungang-port"
        )
        self.assertEqual(entity["entity_id"], expected)
        self.assertEqual(uuid.UUID(entity["entity_id"]).version, 5)

    def test_corridors_are_date_line_safe(self) -> None:
        for corridor in self.model["corridors"]:
            for segment in corridor["route_segments"]:
                points = [waypoint["coordinates"] for waypoint in segment["waypoints"]]
                for first, second in zip(points, points[1:]):
                    self.assertLessEqual(
                        abs(float(first[0]) - float(second[0])),
                        180,
                        corridor["code"],
                    )

    def test_node_lifecycle_confidence_boundaries(self) -> None:
        priority_nodes = {
            node["code"]: node["lifecycle"]
            for node in self.model["nodes"]
            if node["tier"] == "priority"
        }
        self.assertEqual(priority_nodes, build_seed.PRIORITY_LIFECYCLES)

        for node in self.model["nodes"]:
            if node["tier"] != "priority":
                self.assertEqual(node["lifecycle"], "unknown", node["code"])

    def test_rendering_is_deterministic(self) -> None:
        first = build_seed.render_outputs(self.model)
        second = build_seed.render_outputs(build_seed.build_model())
        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "seed.sql",
                "001_countries_and_sources.sql",
                "002_entities_and_subtypes.sql",
                "003_node_details_and_geometries.sql",
                "004_network_and_projects.sql",
                "005_claims_and_status.sql",
                "099_validate.sql",
            },
        )


if __name__ == "__main__":
    unittest.main()
