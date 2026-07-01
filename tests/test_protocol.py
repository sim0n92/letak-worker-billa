"""Protocol-contract tests: run src/main.py as a subprocess and check exit codes,
stdout JSON Lines shape, and --version - all offline via file:// fixtures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
MAIN_PY = SRC_DIR / "main.py"

LISTING_HTML = """<html><body>
<a href="detail.html" class="ws-teaser" data-teaser-name="Test Leták" data-teaser-group="marketing">
<h4 class="text-highlight text-left">Test Leták</h4>
<div class="text-base-color py-2 flex-grow-1 text-left">platí od pondelka 1. 1. do nedele 7. 1. 2026</div>
</a>
</body></html>"""

DETAIL_HTML = """<html><body>
<a href="https://letak.billa.sk/x/y/pdfs/11111111-1111-1111-1111-111111111111.pdf?a=b" target="_blank" aria-label="Stiahnuť PDF">Stiahnuť PDF</a>
</body></html>"""


def _run(stdin_obj, argv=None, env_extra=None):
    env = dict(os.environ)
    env["LOG_LEVEL"] = "Debug"
    if env_extra:
        env.update(env_extra)
    cmd = [sys.executable, str(MAIN_PY)] + (argv or [])
    proc = subprocess.run(
        cmd,
        input=(json.dumps(stdin_obj) + "\n") if stdin_obj is not None else "",
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    return proc


def _stdout_lines(proc):
    return [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]


class VersionFlagTests(unittest.TestCase):
    def test_version_matches_manifest(self):
        manifest = json.loads((SRC_DIR.parent / "manifest.json").read_text(encoding="utf-8"))
        proc = _run(None, argv=["--version"])
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), manifest["version"])


class HappyPathTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self.tmpdir.name)
        (tmp / "listing.html").write_text(LISTING_HTML, encoding="utf-8")
        (tmp / "detail.html").write_text(DETAIL_HTML, encoding="utf-8")
        self.listing_url = (tmp / "listing.html").as_uri()
        self.output_path = tmp / "result.json"
        self.logs_dir = tmp / "logs"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _execute(self, **overrides):
        payload = {
            "_action": "execute",
            "outputPath": str(self.output_path),
            "pageUrl": self.listing_url,
            "_meta": {"executionId": "test-exec-id"},
        }
        payload.update(overrides)
        return _run(payload, env_extra={"LOG_DIR": str(self.logs_dir)})

    def test_exit_code_zero_and_result_emitted(self):
        proc = self._execute()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = _stdout_lines(proc)
        self.assertTrue(lines, "expected at least one stdout line")
        for line in lines:
            self.assertIn(line["type"], ("progress", "result", "error"))
        self.assertEqual(lines[-1]["type"], "result")

    def test_only_json_lines_on_stdout(self):
        proc = self._execute()
        for raw_line in proc.stdout.splitlines():
            if raw_line.strip():
                json.loads(raw_line)  # raises if not valid JSON

    def test_new_leaflet_is_returned(self):
        proc = self._execute()
        result = _stdout_lines(proc)[-1]["data"]
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["hasNew"])
        leaflet = result["leaflets"][0]
        self.assertEqual(leaflet["type"], "Test Leták")
        self.assertEqual(leaflet["from"], "2026-01-01")
        self.assertEqual(leaflet["to"], "2026-01-07")
        self.assertTrue(leaflet["url"].startswith("https://letak.billa.sk/"))

    def test_known_leaflet_is_filtered_out(self):
        proc = self._execute(knownLeaflets=["Test Leták|2026-01-01|2026-01-07"])
        result = _stdout_lines(proc)[-1]["data"]
        self.assertEqual(result["count"], 0)
        self.assertFalse(result["hasNew"])

    def test_type_filter_excludes_non_matching_types(self):
        proc = self._execute(types=["Katalóg Iný"])
        result = _stdout_lines(proc)[-1]["data"]
        self.assertEqual(result["count"], 0)

    def test_output_file_is_written(self):
        proc = self._execute()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.output_path.exists())
        written = json.loads(self.output_path.read_text(encoding="utf-8"))
        self.assertEqual(written["count"], 1)


class ErrorPathTests(unittest.TestCase):
    def test_missing_output_path_is_input_error(self):
        proc = _run({"_action": "execute", "_meta": {}})
        self.assertEqual(proc.returncode, 2)
        lines = _stdout_lines(proc)
        self.assertEqual(lines[-1]["type"], "error")

    def test_invalid_json_on_stdin_is_input_error(self):
        proc = subprocess.run(
            [sys.executable, str(MAIN_PY)],
            input="not json\n",
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 2)

    def test_empty_stdin_is_input_error(self):
        proc = _run(None)
        self.assertEqual(proc.returncode, 2)

    def test_unknown_action_is_input_error(self):
        proc = _run({"_action": "bogus", "_meta": {}})
        self.assertEqual(proc.returncode, 2)

    def test_fetch_failure_is_dependency_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(
                {
                    "_action": "execute",
                    "outputPath": str(Path(tmp) / "result.json"),
                    "pageUrl": (Path(tmp) / "does-not-exist.html").as_uri(),
                    "_meta": {},
                }
            )
            self.assertEqual(proc.returncode, 4)
            lines = _stdout_lines(proc)
            self.assertEqual(lines[-1]["type"], "error")
            self.assertEqual(lines[-1].get("code"), "FETCH_FAILED")


class TerminateActionTests(unittest.TestCase):
    def test_terminate_as_initial_action_returns_cleaned(self):
        proc = _run({"_action": "terminate", "_meta": {}})
        self.assertEqual(proc.returncode, 0)
        lines = _stdout_lines(proc)
        self.assertEqual(lines[-1]["type"], "result")
        self.assertTrue(lines[-1]["data"]["cleaned"])


if __name__ == "__main__":
    unittest.main()
