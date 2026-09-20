"""The move changed where files live and nothing else. Prove it.

Lifting a working tool into a new layout is the kind of change that looks
free and is not: a path repointed at the wrong fixture, a stale copy, an
import that resolves somewhere unexpected. The cheapest possible guard is to
generate the page here and diff it against the page the original still
produces -- byte for byte.

This test is temporary by design. It is worth keeping only while GraphEinsums
still holds a working copy of the viz; once the interpreter is promoted to a
cascade driver the two will legitimately diverge, and at that point this file
should be deleted rather than updated. It exists to make ONE commit
trustworthy: "max-flow reproduces bit-for-bit in its new home."

    pytest tests/test_move_is_faithful.py

Skips, rather than fails, when the original is not on this machine.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_REL = "Projects/GraphEinsums/notebooks/zoo/tutorials/maxflow/viz/index.html"
ORIGINAL = Path(
    os.environ.get("EDGE_WORKBENCH_ORIGINAL", str(Path.home() / _REL))
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _build() -> Path:
    r = subprocess.run(
        [sys.executable, str(ROOT / "edge_workbench/render/build_page.py")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert r.returncode == 0, "build failed:\n" + r.stdout + r.stderr
    out = ROOT / "build/max-flow/index.html"
    assert out.exists(), "build reported success but wrote no page"
    return out


def test_page_is_byte_identical_to_the_original():
    if not ORIGINAL.exists():
        pytest.skip(f"original not present at {ORIGINAL}")
    built = _build()
    assert _sha(built) == _sha(ORIGINAL), (
        "the lifted build produces a different page.\n"
        f"  built    {built}  {built.stat().st_size} bytes\n"
        f"  original {ORIGINAL}  {ORIGINAL.stat().st_size} bytes\n"
        "The move was supposed to change file locations only."
    )


def test_the_build_gate_actually_gates():
    """The builder refuses to write a page when verification fails.

    Without this the byte-identical test above could pass on a build that
    silently skipped its checks.
    """
    env = dict(os.environ, EDGE_WORKBENCH_ALG="does-not-exist")
    r = subprocess.run(
        [sys.executable, str(ROOT / "edge_workbench/render/build_page.py")],
        capture_output=True, text=True, cwd=ROOT, env=env,
    )
    assert r.returncode != 0, "an unknown algorithm should not build a page"
    assert "does-not-exist" in (r.stdout + r.stderr)
