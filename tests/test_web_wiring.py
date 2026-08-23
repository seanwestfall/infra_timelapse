import subprocess
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class WebWiringTests(unittest.TestCase):
    def test_main_page_uses_worker_api_and_packaged_inventory(self):
        html = (REPOSITORY_ROOT / "web" / "public" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('content="__TIMELAPSE_INDEX_URL__"', html)
        self.assertIn(
            "collectCaptures(indexResult.data, { index_url: indexResult.url })",
            html,
        )
        self.assertIn(
            'fetchJson("./infra_timelapse_ports_corridors.json")', html
        )
        self.assertIn('id="satellite-globe"', html)
        self.assertIn('id="satellite-select"', html)
        map_start = html.index('<div id="map"')
        map_end = html.index("</div>", html.index('id="satellite-status"'))
        image_stage_start = html.index('<div id="image-stage"')
        self.assertLess(map_start, html.index('id="satellite-card"'))
        self.assertLess(html.index('id="satellite-card"'), map_end)
        self.assertLess(map_end, image_stage_start)
        self.assertIn(
            'import * as maplibregl from "https://unpkg.com/maplibre-gl@6.4.1/dist/maplibre-gl.mjs"',
            html,
        )
        self.assertNotIn("dist/maplibre-gl.js", html)
        self.assertIn("const SATELLITE_GLOBE_STYLE", html)
        self.assertIn('projection: { type: "globe" }', html)
        self.assertIn('"atmosphere-blend"', html)
        self.assertIn("style: SATELLITE_GLOBE_STYLE", html)
        self.assertIn("addMapLayers();\n  ensureSatelliteGlobe();", html)
        self.assertIn('class="orbit-back"', html)
        self.assertIn('class="orbit-front"', html)
        self.assertIn('id="satellite-orbit-marker"', html)
        self.assertIn("function updateSatelliteOrbitTrail", html)
        self.assertIn("ellipseX = 108 * Math.cos(phase)", html)
        self.assertIn("zoom: 0", html)
        self.assertIn('versionPrefix = apiUrl.pathname.startsWith("/api/v1/")', html)
        self.assertIn("satellite.js@6.0.1", html)
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
        rendered = (REPOSITORY_ROOT / "dist" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'content="https://if-api.acceler.workers.dev/api/v1/index"', rendered
        )
        self.assertNotIn("__TIMELAPSE_INDEX_URL__", rendered)
        self.assertTrue(
            (
                REPOSITORY_ROOT
                / "dist"
                / "infra_timelapse_ports_corridors.json"
            ).is_file()
        )

    def test_standalone_worker_uses_runtime_api_base(self):
        worker = (
            REPOSITORY_ROOT / "web" / "worker" / "src" / "index.js"
        ).read_text(encoding="utf-8")
        self.assertIn("env.API_BASE_URL", worker)
        self.assertIn("env.ORIGIN_AUTH_TOKEN", worker)
        self.assertIn("cloudflareManifest.production.pages_origin", worker)
        self.assertIn("MANIFEST_ALLOWED_SUFFIXES", worker)
        self.assertIn('const CELESTRAK_BASE = "https://celestrak.org/', worker)
        self.assertIn("SATELLITE_PREFIX", worker)
        self.assertNotIn("storage.googleapis.com", worker)
        wrangler = (
            REPOSITORY_ROOT / "web" / "worker" / "wrangler.jsonc"
        ).read_text(encoding="utf-8")
        self.assertNotIn("infratimelapse.pages.dev", wrangler)


if __name__ == "__main__":
    unittest.main()
