"""The builder refuses to write a page it has not verified.

This replaces `test_move_is_faithful.py`, which diffed the generated page
against the copy GraphEinsums still produces. That test had a stated
retirement condition -- "delete it once the two legitimately diverge" -- and
2026-09-22 is when they did: upstream's IR gained `AdmPost`, so E17 writes a
tensor of its own rather than a second generation of `Adm`. GraphEinsums is
pinned to the older spec as research content, and the pages are now different
on purpose.

What the move test was really guarding is now guarded better, and by things
that keep working as the spec moves:

  tests/drive_and_compare.js   the driven trace against the hand-written one,
                               all 236 steps, plus a fault self-test
  tests/verify_interp.js       the interpreter replayed against that trace
  tests/check_page.js          163 checks on the rendered page
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
    stale silently, which is exactly what happened before `AdmPost` landed --
    so when the sibling IS present, say so.
    """
    import json
    import pytest

    upstream = Path(os.environ.get(
        "EDGE_IR_REPO", str(Path.home() / "Projects/edge-ir-interpreter")
    )) / "test-algorithms/max-flow/max_flow_program.json"
    if not upstream.exists():
        pytest.skip(f"upstream checkout not present at {upstream}")
    ours = ROOT / "algorithms/max-flow/spec/max_flow_program.json"
    assert json.loads(ours.read_text()) == json.loads(upstream.read_text()), (
        "the vendored IR differs from upstream's. If upstream moved, re-vendor "
        "and re-run the driver comparison; if this repo changed it locally, "
        "that change belongs upstream."
    )
