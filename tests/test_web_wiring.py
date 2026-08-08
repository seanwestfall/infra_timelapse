import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class WebWiringTests(unittest.TestCase):
    def test_main_page_uses_same_origin_api_and_packaged_inventory(self):
        html = (REPOSITORY_ROOT / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('content="/api/index"', html)
        self.assertIn(
            'fetchJson("./infra_timelapse_ports_corridors.json")', html
        )
        self.assertNotIn("storage.googleapis.com", html)

    def test_pages_build_contains_real_entry_point_and_inventory(self):
        subprocess.run(
            ["bash", "deploy/build_web.sh"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertTrue((REPOSITORY_ROOT / "dist" / "index.html").is_file())
        self.assertTrue(
            (
                REPOSITORY_ROOT
                / "dist"
                / "infra_timelapse_ports_corridors.json"
            ).is_file()
        )

    def test_pages_function_uses_runtime_api_base(self):
        function = (
            REPOSITORY_ROOT / "functions" / "api" / "[[path]].js"
        ).read_text(encoding="utf-8")
        self.assertIn("context.env.API_BASE_URL", function)
        self.assertNotIn("storage.googleapis.com", function)


if __name__ == "__main__":
    unittest.main()
