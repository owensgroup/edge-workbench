"""Run the page walk from pytest, so `pytest` alone covers the page too."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_every_page_survives_a_walk_with_no_network():
    if not shutil.which("node") or not (ROOT / "node_modules/jsdom").exists():
        pytest.skip("run `npm install` for the page walk")
    if not list(ROOT.glob("examples/*/index.html")):
        pytest.skip("no page built yet")
    r = subprocess.run(["node", "tests/check_pages.js"], cwd=ROOT,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]
