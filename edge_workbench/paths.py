"""Where things live.

The lifted tooling used to be one flat directory where every file found its
neighbours with `os.path.join(HERE, ...)`. That is fine for one algorithm and
impossible for many, so the flat lookups are replaced by exactly two ideas:

    TOOL          files that belong to the workbench    (edge_interp.js, ...)
    algorithm()   files that belong to one algorithm    (spec/, fixtures/)

Nothing else about the lifted code changed in the move. The move is proven by
generating max-flow's page here and diffing it against the page GraphEinsums
produces -- byte for byte -- so a path mistake shows up as a failed diff
rather than as a subtly different page.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "edge_workbench"
RENDER = TOOL / "render"
ALGORITHMS = ROOT / "algorithms"
TESTS = ROOT / "tests"

#: Overridable so a tutorial being checked from outside the repo -- the
#: eventual upload path -- can point at its own directory without copying
#: itself in here first.
ENV_ALG_DIR = "EDGE_WORKBENCH_ALG_DIR"


def algorithm(name: str = "max-flow") -> Path:
    """The directory holding one algorithm's spec and fixtures."""
    override = os.environ.get(ENV_ALG_DIR)
    if override:
        return Path(override).resolve()
    d = ALGORITHMS / name
    if not d.is_dir():
        raise FileNotFoundError(
            f"no algorithm directory {d}\n"
            f"  available: {sorted(p.name for p in ALGORITHMS.iterdir() if p.is_dir())}"
        )
    return d


def spec(name: str = "max-flow") -> Path:
    return algorithm(name) / "spec"


def fixtures(name: str = "max-flow") -> Path:
    return algorithm(name) / "fixtures"
