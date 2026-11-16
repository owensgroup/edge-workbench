"""Where things live.

    TOOL / RENDER   files that belong to the workbench    (display.js, ...)
    algorithm()     the directory holding one algorithm's generated spec/

An algorithm's directory is wherever its author keeps it: `edge_workbench
check <dir>` sets EDGE_WORKBENCH_ALG_DIR to `<dir>/workbench` before it runs
the page build, so nothing here assumes a layout inside this repository.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "edge_workbench"
RENDER = TOOL / "render"
TESTS = ROOT / "tests"

#: The algorithm's working directory, set by `edge_workbench check`.
ENV_ALG_DIR = "EDGE_WORKBENCH_ALG_DIR"


def algorithm(name: str | None = None) -> Path:
    """The directory holding one algorithm's spec/.

    `name` is only used to say which algorithm was asked for when the
    directory was not given.
    """
    override = os.environ.get(ENV_ALG_DIR)
    if override:
        return Path(override).resolve()
    raise FileNotFoundError(
        f"no directory for algorithm {name or '(unnamed)'}: set "
        f"{ENV_ALG_DIR}, or run `python3 -m edge_workbench check <dir>`, "
        f"which sets it")


def spec(name: str | None = None) -> Path:
    return algorithm(name) / "spec"
