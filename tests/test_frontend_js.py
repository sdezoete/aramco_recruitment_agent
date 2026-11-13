"""Runs the frontend unit tests (tests/js/*.test.mjs) with Node's built-in test runner.

Node is a dev-machine tool only: nothing in the app needs it and it is never shipped. Skipped when `node`
is not on PATH. Run directly with:  node --test "tests/js/*.test.mjs"
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_TESTS = sorted((ROOT / "tests" / "js").glob("*.test.mjs"))


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed (frontend tests are dev-only)")
@pytest.mark.parametrize("test_file", JS_TESTS, ids=[p.stem for p in JS_TESTS])
def test_frontend_js(test_file):
    proc = subprocess.run(["node", "--test", str(test_file)], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=120)
    assert proc.returncode == 0, f"{test_file.name} failed:\n{proc.stdout[-6000:]}\n{proc.stderr[-2000:]}"
