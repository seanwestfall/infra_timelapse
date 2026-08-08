import json
import sys
import tempfile
import types
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

import fetch_images


class FakeRequestException(Exception):
    pass


fake_requests = types.SimpleNamespace(
    RequestException=FakeRequestException,
    HTTPError=FakeRequestException,
    get=None,
)


class FakeResponse:
    def __init__(self, status_code, content=b"image"):
        self.status_code = status_code
        self.content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeRequestException(f"HTTP {self.status_code}")


class CaptureResilienceTests(unittest.TestCase):
    def setUp(self):
        self.target = {
            "id": "test_port",
            "target_type": "port",
            "name": "Test Port",
            "latitude": 1.0,
            "longitude": 2.0,
            "zoom": 12,
            "output_parts": ("ports", "test_port"),
        }

    def test_retries_transient_response_then_writes_image(self):
        responses = iter(
            [FakeResponse(500), FakeResponse(503), FakeResponse(200, b"png")]
        )
        delays = []
        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            fetch_images, "OUTPUT_DIR", Path(temp_dir)
        ), mock.patch.object(fetch_images, "API_KEY", "test-key"):
            with mock.patch.dict(sys.modules, {"requests": fake_requests}):
                path = fetch_images.fetch_satellite_image(
                    self.target,
                    request_get=lambda *args, **kwargs: next(responses),
                    sleep=delays.append,
                    random_uniform=lambda start, end: 0,
                )

            self.assertEqual(path.read_bytes(), b"png")
            self.assertEqual(delays, [1, 2])

    def test_non_retryable_response_fails_without_exposing_url(self):
        with (
            mock.patch.dict(sys.modules, {"requests": fake_requests}),
            mock.patch.object(fetch_images, "API_KEY", "test-key"),
        ):
            with self.assertRaises(
                fetch_images.SatelliteImageFetchError
            ) as result:
                fetch_images.fetch_satellite_image(
                    self.target,
                    request_get=lambda *args, **kwargs: FakeResponse(403),
                    sleep=lambda delay: None,
                )

        self.assertEqual(result.exception.status_code, 403)
        self.assertNotIn("key=", str(result.exception))

    def test_capture_report_describes_partial_success(self):
        failures = [
            {
                "target_id": "failed_port",
                "target_type": "port",
                "name": "Failed Port",
                "status_code": 500,
                "attempts": 4,
            }
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            report = fetch_images.write_capture_report(
                report_path, requested_count=2, success_count=1, failures=failures
            )

            self.assertEqual(report["status"], "partial_success")
            self.assertEqual(json.loads(report_path.read_text()), report)

    def test_main_continues_after_one_target_fails(self):
        second_target = dict(
            self.target,
            id="second_port",
            name="Second Port",
            output_parts=("ports", "second_port"),
        )
        parser = mock.Mock()
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            parser.parse_args.return_value = Namespace(
                inventory=Path("inventory.json"),
                scope="all",
                limit=None,
                dry_run=False,
                report_file=report_path,
            )
            with (
                mock.patch.object(fetch_images, "API_KEY", "test-key"),
                mock.patch.object(fetch_images, "build_parser", return_value=parser),
                mock.patch.object(fetch_images, "load_inventory", return_value={}),
                mock.patch.object(
                    fetch_images,
                    "iter_targets",
                    return_value=iter([self.target, second_target]),
                ),
                mock.patch.object(
                    fetch_images,
                    "fetch_satellite_image",
                    side_effect=[
                        fetch_images.SatelliteImageFetchError(
                            "test_port", 4, 500
                        ),
                        Path(temp_dir) / "second.png",
                    ],
                ) as fetch,
                mock.patch.object(fetch_images, "log_metadata") as log_metadata,
            ):
                fetch_images.main()

            report = json.loads(report_path.read_text())
            self.assertEqual(fetch.call_count, 2)
            log_metadata.assert_called_once()
            self.assertEqual(report["status"], "partial_success")
            self.assertEqual(report["requested_count"], 2)
            self.assertEqual(report["success_count"], 1)
            self.assertEqual(report["failure_count"], 1)


if __name__ == "__main__":
    unittest.main()
