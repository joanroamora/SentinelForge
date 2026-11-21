"""Local product shell with bundled static assets."""

from pathlib import Path

WEB_PAGE = Path(__file__).with_name("static").joinpath("index.html").read_text(encoding="utf-8")
