"""Render environment-specific values into the static frontend."""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_INDEX_URL = "https://if-api.acceler.workers.dev/api/v1/index"


def index_url(api_base: str) -> str:
    value = api_base.strip().rstrip("/")
    if not value:
        return DEFAULT_INDEX_URL
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.params:
        raise ValueError("TIMELAPSE_API_BASE must be an HTTPS origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("TIMELAPSE_API_BASE must not contain a path, query, or fragment")
    if parsed.username or parsed.password:
        raise ValueError("TIMELAPSE_API_BASE must not contain credentials")
    return f"{value}/api/v1/index"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: render_web.py SOURCE DESTINATION")
    source = Path(sys.argv[1])
    destination = Path(sys.argv[2])
    document = source.read_text(encoding="utf-8")
    if document.count(DEFAULT_INDEX_URL) != 1:
        raise RuntimeError(f"Expected exactly one {DEFAULT_INDEX_URL} value")
    rendered = document.replace(
        DEFAULT_INDEX_URL,
        html.escape(index_url(os.getenv("TIMELAPSE_API_BASE", "")), quote=True),
    )
    destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
