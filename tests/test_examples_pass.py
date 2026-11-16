"""The worked examples pass `edge_workbench check`, end to end.

The one test of the author workflow as an author runs it: tutorial,
einsum.edge, verifier, the committed model replies, and every stage through to
index.html. Skips without edge-core-ir or node, like the other cross-repo
gates.

Each example's verifier must carry a COMMITTED approval (verifier.lock at
HEAD, matching verifier.py). Until a person has run `approve-verifier` on an
example and committed the lock, its test fails and says which command to run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from approval_fixture import trust_committed_copy  # noqa: E402
from edge_workbench.approval import LEDGER_ENV  # noqa: E402

from edge_workbench.spec_check import upstream  # noqa: E402

EXAMPLES = sorted(p for p in (ROOT / "examples").iterdir() if p.is_dir())


@pytest.mark.parametrize("example", EXAMPLES, ids=[p.name for p in EXAMPLES])
def test_example_passes_every_check(example: Path, tmp_path: Path) -> None:
    if upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    # A copy, so a run never leaves generated files in the repository.
    work = tmp_path / example.name
    shutil.copytree(example, work)
    # The copy has no git history, so the committed approval is checked on
    # the example itself, and the copy's identical lock is trusted after.
    ledger = tmp_path / "approved.json"
    trust_committed_copy(example, work, ledger)
    r = subprocess.run([sys.executable, "-m", "edge_workbench", "check", str(work)],
                       cwd=ROOT, capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, **{LEDGER_ENV: str(ledger)}))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (work / "index.html").exists()
    assert "✗" not in r.stdout, r.stdout
