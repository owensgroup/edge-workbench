"""Where things live.

The lifted tooling used to be one flat directory where every file found its
neighbours with `os.path.join(HERE, ...)`. That is fine for one algorithm and
impossible for many, so the flat lookups are replaced by exactly two ideas:

    TOOL          files that belong to the workbench    (edge_interp.js, ...)
    algorithm()   files that belong to one algorithm    (spec/, tests/)

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


def available() -> list[str]:
    """Every algorithm in the repo."""
    if not ALGORITHMS.is_dir():
        return []
    return sorted(p.name for p in ALGORITHMS.iterdir()
                  if p.is_dir() and not p.name.startswith("."))


def default() -> str:
    """The algorithm to use when nobody said.

    Exactly one in the repo means there is no ambiguity to resolve; more than
    one and the caller has to choose, because picking for them would silently
    build the wrong page. No algorithm named here on purpose -- the tool has
    no favourite.
    """
    names = available()
    if len(names) == 1:
        return names[0]
    if not names:
        raise FileNotFoundError(f"no algorithms in {ALGORITHMS}")
    raise ValueError(
        f"{len(names)} algorithms available ({', '.join(names)}); say which "
        f"with EDGE_WORKBENCH_ALG"
    )


def algorithm(name: str | None = None) -> Path:
    """The directory holding one algorithm's spec, verifier and tests."""
    override = os.environ.get(ENV_ALG_DIR)
    if override:
        return Path(override).resolve()
    d = ALGORITHMS / (name or default())
    if not d.is_dir():
        raise FileNotFoundError(
            f"no algorithm directory {d}\n  available: {available()}"
        )
    return d


def spec(name: str | None = None) -> Path:
    return algorithm(name) / "spec"


