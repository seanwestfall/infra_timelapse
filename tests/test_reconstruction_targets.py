import json
import unittest
from pathlib import Path

import fetch_images


ROOT = Path(__file__).resolve().parents[1]


class ReconstructionTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = fetch_images.load_inventory(
            ROOT / "infra_timelapse_ports_corridors.json"
        )

    def test_reconstruction_inventory_is_additive(self):
        targets = self.inventory["capture_targets"]
        self.assertEqual(self.inventory["inventory_counts"]["capture_targets"], 2)
        self.assertEqual(
            {target["id"] for target in targets},
            {"lahaina_recovery_area", "pacific_palisades_recovery_area"},
        )
        self.assertTrue(all(target["theme"] == "reconstruction" for target in targets))

    def test_generic_targets_are_captureable_with_stable_paths(self):
        targets = list(fetch_images.iter_targets(self.inventory, "targets"))
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0]["output_parts"], ("targets", "lahaina_recovery_area"))
        self.assertEqual(
            targets[1]["output_parts"],
            ("targets", "pacific_palisades_recovery_area"),
        )

    def test_legacy_inventory_shape_still_loads_and_captures(self):
        legacy = dict(self.inventory)
        legacy.pop("capture_targets")
        targets = list(fetch_images.iter_targets(legacy))
        expected = (
            self.inventory["inventory_counts"]["ports_and_logistics_nodes"]
            + self.inventory["inventory_counts"]["corridor_waypoints"]
        )
        self.assertEqual(len(targets), expected)

    def test_deployed_inventory_matches_reconstruction_targets(self):
        deployed = json.loads(
            (ROOT / "dist" / "infra_timelapse_ports_corridors.json").read_text()
        )
        self.assertEqual(
            deployed["capture_targets"], self.inventory["capture_targets"]
        )


if __name__ == "__main__":
    unittest.main()
