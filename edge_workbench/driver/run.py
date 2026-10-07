# -*- coding: utf-8 -*-
"""Run a cascade and get a trace back, from Python.

The driver is JavaScript because the browser needs it: the page's execution
panel recomputes an Einsum live, so the evaluator has to exist as JS whatever
else is true. Rather than write a second one in Python and have two to keep
honest, the build shells out to the same one.

    trace = run()          # or run("some-algorithm")

Requires `node` and nothing else. That matters: `edge-core-ir` is a separate
checkout, so nothing a stranger needs in order to `git clone && npm run build`
may live there. The IR is vendored; the reference evaluator is a verification
step, not a build step.
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
const r = runCascade(rd(process.env.EW_PROGRAM),
                     rd(process.env.EW_INSTANCE || spec + "/instance.json"),
                     cascade, {});
process.stdout.write(JSON.stringify(r));
"""


class DriverError(RuntimeError):
    pass


def run(algorithm: str | None = None, *, spec_dir: str | Path | None = None,
        program: str | None = None, instance: str | None = None,
        selectors: dict | None = None) -> dict:
    """Execute the cascade and return {generations, steps, executed}.

    `executed` is the IR-node coverage tally -- node key to run count --
    which `edge_workbench.coverage` checks against the specification.

    `selectors` overrides the algorithm's own mapping -- used by tests that
    need to pin a free choice, never by the build.

    `instance` runs a different problem instance than the algorithm's own.
    The verifier uses it to sweep generated instances through THIS driver,
    rather than through a second implementation of the cascade written to
    agree with it.

    `spec_dir` runs a spec directory that is not one of this repository's
    algorithms -- an author's own, being checked by `edge_workbench check`.
    """
    if shutil.which("node") is None:
        raise DriverError(
            "node is not on PATH. The cascade driver is JavaScript because "
            "the page's execution panel needs the same evaluator in the "
            "browser; there is no Python fallback on purpose, so that there "
            "is only one evaluator to keep honest."
        )
    spec = Path(spec_dir) if spec_dir is not None else paths.spec(algorithm)
    prog = Path(program) if program else _program_file(spec)
    env = dict(
        os.environ,
        EW_DRIVER=str(paths.TOOL / "driver" / "cascade.js"),
        EW_SPEC=str(spec),
        EW_PROGRAM=str(prog),
    )
    if instance is not None:
        env["EW_INSTANCE"] = str(instance)
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

    Matched by the `*_program.json` convention rather than by excluding the
    files we happen to know about. The denylist version of this ("any .json
    that is not cascade.json or instance.json") treated every new file in
    spec/ as a candidate program, so adding `known_ir_violations.json`
    silently broke three tools at once. A spec directory is going to
    accumulate files; the program is the one that says it is the program.

    Exactly one is required, because two would make the choice silent.
    """
    candidates = sorted(spec.glob("*_program.json"))
    if len(candidates) != 1:
        raise DriverError(
            f"expected exactly one *_program.json in {spec}, found "
            f"{[p.name for p in candidates]}. The IR program is identified by "
            f"the `_program.json` suffix; other files in spec/ are the "
            f"algorithm's own."
        )
    return candidates[0]
