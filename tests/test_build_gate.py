"""The builder refuses to write a page it has not verified.

Two gates run inside build_page.py before index.html is written, and there is
no flag to skip them: coverage (every Einsum the author wrote executed) and
the algorithm's own answer check. This file guards the thing around them:
that an unknown algorithm builds nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_an_unknown_algorithm_does_not_build_a_page():
    env = dict(os.environ, EDGE_WORKBENCH_ALG="does-not-exist")
    r = subprocess.run(
        [sys.executable, str(ROOT / "edge_workbench/render/build_page.py")],
        capture_output=True, text=True, cwd=ROOT, env=env,
    )
    assert r.returncode != 0, "an unknown algorithm should not build a page"
    assert "does-not-exist" in (r.stdout + r.stderr)

