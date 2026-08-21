import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "deploy"))

from cloudflare_manifest import cors_exact_origins, load_manifest  # noqa: E402


class CloudflareManifestTests(unittest.TestCase):
    def test_manifest_owns_production_and_cors_origins(self):
        manifest = load_manifest()
        self.assertEqual(manifest["production"]["branch"], "main")
        self.assertEqual(
            manifest["production"]["pages_origin"],
            "https://infratimelapse.pages.dev",
        )
        self.assertEqual(
            manifest["production"]["worker_origin"],
            "https://if-api.acceler.workers.dev",
        )
        self.assertIn(
            manifest["production"]["pages_origin"], cors_exact_origins(manifest)
        )
        self.assertIn(
            ".infratimelapse.pages.dev",
            manifest["cors"]["https_subdomain_suffixes"],
        )

    def test_manifest_rejects_wildcard_suffixes(self):
        manifest = json.loads(
            (REPOSITORY_ROOT / "deploy" / "cloudflare-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["cors"]["https_subdomain_suffixes"] = ["*.pages.dev"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            manifest_path = Path(temporary_directory) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hostname suffixes"):
                load_manifest(manifest_path)


if __name__ == "__main__":
    unittest.main()
