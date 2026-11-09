"""Shared fixtures: run the worker as a subprocess against an offline (file://) Billa site."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAIN = next(p for p in (ROOT / "src" / "main.py", ROOT / "main.py") if p.is_file())  # repo or container layout
FIXTURES = ROOT / "tests" / "fixtures"

MAIN_TYPE = "Aktuálny leták"
BONUS_TYPE = "BILLA Bonus leták"
MAIN_KEY = f"{MAIN_TYPE}|2026-01-01|2026-01-07"
BONUS_KEY = f"{BONUS_TYPE}|2026-01-01|2026-01-07"
UNREACHABLE = "http://127.0.0.1:9/nope"

_TEASER = ('<a href="{detail}" class="ws-teaser" data-teaser-name="{name}" data-teaser-group="marketing">'
           '<h4>{name}</h4><div class="text-base-color py-2">platí od pondelka 1. 1. do nedele 7. 1. 2026</div></a>')
_DETAIL = ('<html><body><a href="https://letak.billa.sk/x/y/pdfs/{uuid}.pdf?a=b" target="_blank" '
           'aria-label="Stiahnuť PDF">Stiahnuť PDF</a></body></html>')


@dataclass(frozen=True)
class Run:
    """The outcome of one worker invocation: exit code and the parsed stdout JSON lines."""

    returncode: int
    lines: list[dict[str, Any]]
    stdout: str

    @property
    def result(self) -> dict[str, Any]:
        results = [m for m in self.lines if m.get("type") == "result"]
        assert results, f"no result line in {self.stdout!r}"
        return results[-1]["data"]

    @property
    def error(self) -> dict[str, Any]:
        errors = [m for m in self.lines if m.get("type") == "error"]
        assert errors, f"no error line in {self.stdout!r}"
        return errors[-1]


def write_site(directory: Path, listing: str | None = None, detail: str | None = None) -> str:
    """Writes a listing page with two parallel leaflet types and their detail pages; returns the listing URI."""
    directory.mkdir(parents=True, exist_ok=True)
    teasers = _TEASER.format(detail="detail_main.html", name=MAIN_TYPE) + _TEASER.format(
        detail="detail_bonus.html", name=BONUS_TYPE)
    (directory / "listing.html").write_text(
        listing if listing is not None else f"<html><body>{teasers}</body></html>", encoding="utf-8")
    (directory / "detail_main.html").write_text(
        detail if detail is not None else _DETAIL.format(uuid="11111111-1111-1111-1111-111111111111"), encoding="utf-8")
    (directory / "detail_bonus.html").write_text(
        detail if detail is not None else _DETAIL.format(uuid="22222222-2222-2222-2222-222222222222"), encoding="utf-8")
    return (directory / "listing.html").as_uri()


@pytest.fixture
def fixture_config(tmp_path: Path) -> dict[str, str]:
    """Offline overrides: the listing page points at a generated local site."""
    return {"pageUrl": write_site(tmp_path / "site")}


@pytest.fixture
def empty_page(tmp_path: Path) -> str:
    """A listing page without any leaflet teaser (the site layout changed)."""
    return write_site(tmp_path / "empty-site", listing="<html><body>redesigned page</body></html>")


@pytest.fixture
def run_action(tmp_path: Path):
    """Run the worker with `_action` + params; returns a Run. Logs go to tmp_path."""

    def _run(action: str, **params: Any) -> Run:
        env = {**os.environ, "LOG_DIR": str(tmp_path / "logs"), "PYTHONIOENCODING": "utf-8"}
        payload = json.dumps({"_action": action, **params}, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, str(MAIN)], input=payload.encode("utf-8"),
            capture_output=True, env=env, check=False)
        stdout = proc.stdout.decode("utf-8")
        lines = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        return Run(proc.returncode, lines, stdout)

    return _run
