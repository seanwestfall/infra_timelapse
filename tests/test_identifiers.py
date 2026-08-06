import re
import unittest

import fetch_images


class IdentifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = fetch_images.load_inventory(
            fetch_images.DEFAULT_INVENTORY_PATH
        )
        cls.targets = list(fetch_images.iter_targets(cls.inventory))

    def test_every_target_path_is_ascii(self):
        for target in self.targets:
            relative_path = "/".join(target["output_parts"])
            with self.subTest(target=target["id"]):
                self.assertTrue(relative_path.isascii())
                self.assertRegex(
                    relative_path,
                    re.compile(r"[a-z0-9_/-]+\Z"),
                )

    def test_unicode_display_names_have_explicit_machine_identifiers(self):
        expected = {
            "Ürümqi": "urumqi",
            "Małaszewicze": "malaszewicze_logistics_hub",
            "Constanța": "constanta",
            "Caetité": "caetite",
            "Figueirópolis": "figueiropolis",
            "Brasília": "brasilia",
            "Xi’an International Port": "xian_international_port",
        }
        observed = {}
        for target in self.targets:
            waypoint_name = target.get("waypoint_name")
            if waypoint_name in expected:
                observed[waypoint_name] = target["waypoint_id"]

        self.assertEqual(observed, expected)

    def test_display_names_remain_unicode(self):
        names = {
            target.get("waypoint_name")
            for target in self.targets
            if target["target_type"] == "corridor_waypoint"
        }
        self.assertIn("Ürümqi", names)
        self.assertIn("Małaszewicze", names)
        self.assertIn("Constanța", names)

    def test_missing_waypoint_identifier_is_rejected(self):
        corridors = [
            {
                "id": "test_corridor",
                "name": "Test corridor",
                "route_segments": [
                    {
                        "waypoints": [
                            {"name": "No identifier", "coordinates": [0, 0]}
                        ]
                    }
                ],
            }
        ]
        with self.assertRaisesRegex(ValueError, "waypoint 1 identifier"):
            list(fetch_images.iter_corridor_waypoints(corridors))


if __name__ == "__main__":
    unittest.main()
