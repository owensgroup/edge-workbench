# -*- coding: utf-8 -*-
"""Run a cascade and get a trace back, from Python.

The driver is JavaScript because the browser needs it: the page's execution
panel recomputes an Einsum live, so the evaluator has to exist as JS whatever
else is true. Rather than write a second one in Python and have two to keep
honest, the build shells out to the same one.

    trace = run("max-flow")

Requires `node` and nothing else. That matters: `edge-ir-interpreter` is a
private repo, so nothing a stranger needs in order to `git clone && npm run
build` may live there. The reference evaluator is a verification step, not a
build step.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from edge_workbench import paths

_RUNNER = r"""
const fs = require("fs");
const { runCascade, makeSelector } = require(process.env.EW_DRIVER);
const rd = (p) => JSON.parse(fs.readFileSync(p, "utf8"));
const spec = process.env.EW_SPEC;

const cascade = rd(spec + "/cascade.json");
if (process.env.EW_SELECTORS) {
  cascade.selectors = JSON.parse(process.env.EW_SELECTORS);
}
const r = runCascade(rd(process.env.EW_PROGRAM), rd(spec + "/instance.json"),
                     cascade, {});
process.stdout.write(JSON.stringify(r));
"""


class DriverError(RuntimeError):
    pass


def run(algorithm: str = "max-flow", *, program: str | None = None,
        selectors: dict | None = None) -> dict:
    """Execute the cascade and return {generations, steps}.

    `selectors` overrides the algorithm's own mapping -- used by tests that
    need to pin a free choice, never by the build.
    """
    if shutil.which("node") is None:
        raise DriverError(
            "node is not on PATH. The cascade driver is JavaScript because "
            "the page's execution panel needs the same evaluator in the "
            "browser; there is no Python fallback on purpose, so that there "
            "is only one evaluator to keep honest."
        )
    spec = paths.spec(algorithm)
    prog = Path(program) if program else _program_file(spec)
    env = dict(
        os.environ,
        EW_DRIVER=str(paths.TOOL / "driver" / "cascade.js"),
        EW_SPEC=str(spec),
        EW_PROGRAM=str(prog),
    )
    if selectors is not None:
        env["EW_SELECTORS"] = json.dumps(selectors)

    p = subprocess.run(["node", "-e", _RUNNER], capture_output=True, text=True,
                       env=env)
    if p.returncode != 0:
        raise DriverError(
            f"the cascade did not run.\n{p.stderr.strip() or p.stdout.strip()}")
    return json.loads(p.stdout)


def _program_file(spec: Path) -> Path:
    """The IR program in an algorithm's spec directory.

    Found rather than named, so an algorithm does not have to call its program
    `max_flow_program.json`; exactly one is required, because two would make
    the choice silent.
    """
    candidates = sorted(
        p for p in spec.glob("*.json")
        if p.name not in {"cascade.json", "instance.json"}
    )
    if len(candidates) != 1:
        raise DriverError(
            f"expected exactly one IR program in {spec}, found "
            f"{[p.name for p in candidates]}. cascade.json and instance.json "
            f"are the algorithm's own files; anything else is taken to be the "
            f"program."
        )
    return candidates[0]
