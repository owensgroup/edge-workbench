"""The builder refuses to write a page it has not verified.

Two gates run inside build_page.py before index.html is written, and there is
no flag to skip them: coverage (every Einsum the author wrote executed) and
the algorithm's own answer check. This file guards the things around them --
that an unknown algorithm builds nothing, and that the vendored IR still
matches what upstream ships.
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


def test_the_vendored_ir_is_the_one_upstream_ships():
    """Vendoring is deliberate; drifting is not.

    The IR is copied in rather than read across checkouts so the build does
    not depend on a sibling repo being present. The cost is that it can go
    stale silently, which is exactly what happened when `AdmPost` landed --
    so when the sibling IS present, say so.
    """
    import json
    import pytest

    root = Path(os.environ.get(
        "EDGE_IR_REPO", str(Path.home() / "Projects/edge-core-ir")
    ))
    # `examples/algorithms` is upstream's layout; `test-algorithms` is what an
    # older checkout pointed at by EDGE_IR_REPO calls the same directory.
    upstream = next(
        (p for rel in ("examples/algorithms", "test-algorithms")
         if (p := root / rel / "max-flow/max_flow_program.json").exists()),
        None,
    )
    if upstream is None:
        pytest.skip(f"upstream checkout not present at {root}")
    ours = ROOT / "algorithms/max-flow/spec/max_flow_program.json"
    assert json.loads(ours.read_text()) == json.loads(upstream.read_text()), (
        "the vendored IR differs from upstream's. If upstream moved, re-vendor "
        "and re-run the driver comparison; if this repo changed it locally, "
        "that change belongs upstream."
    )
