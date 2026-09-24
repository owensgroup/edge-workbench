"""Every algorithm's program must be real IR, and must come from a builder.

THE MISTAKE THIS EXISTS TO PREVENT
----------------------------------
Algorithm X's first spec was typed by hand as JSON, on the theory that the
schema was simple enough to transcribe. It was not. It carried 21
declarations keyed `dtype` where the IR says `data_type`, two populates
keyed `coordinate_op` where the field is `coord_op`, a unary whose `op` was
a bare string rather than a discriminated node, and `+` used as a
user-defined function NAME, which the identifier pattern rejects outright.
Four mistakes, 49 validation errors, and none of them surfaced until someone
thought to run the IR's own parser over the file -- because nothing in the
build path ever did.

Worse, the tool ran it anyway. Our driver reads the JSON directly and only
looks at the keys it happens to need, so a spec that upstream would reject
outright drove a cascade, produced a trace, and rendered a page. A viewer
whose job is to tell an author their specification is wrong instead showed
them a picture of it.

So the pipeline is fixed in one direction, and this file is what holds it:

    builder (edge_ir objects)  ->  program.json  ->  interpreter  ->  page
                               ^
                               the only way JSON gets here

A program constructed from `edge_ir`'s pydantic classes cannot make any of
those four mistakes: a misspelled field is a TypeError at authoring time, and
a bad operator name fails its pattern before anything is written. Hand-edited
JSON can make all four, so hand-edited JSON is what this rejects.

WHAT IS CHECKED, FOR EVERY ALGORITHM
------------------------------------
1. the committed program parses as IR (Layer 1, pydantic);
2. it passes such Layer 2 checks as upstream ships (today: single assignment);
3. it did not drift from whatever produces it -- a builder if the algorithm
   has one, upstream's copy if the program is vendored.

(3) is what keeps (1) and (2) honest over time. Validating a file says
nothing about where it came from; an algorithm could pass this today and be
hand-patched tomorrow.

Discovery is by glob, so an algorithm added next month is covered by this
file without being named in it.

    EDGE_IR_REPO=~/Projects/edge-core-ir pytest tests/test_spec_is_valid_ir.py

Skips when no upstream checkout is present: the vendored IR means the build
itself needs nothing but `node`, and validation is a verification step, not a
build step. That is the same bargain `test_agrees_with_reference.py` makes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ALGORITHMS = ROOT / "algorithms"


def _upstream() -> Path | None:
    named = os.environ.get("EDGE_IR_REPO")
    if named:
        return Path(named)
    p = Path.home() / "Projects" / "edge-core-ir"
    return p if (p / "edge_ir/ir/program.py").exists() else None


UPSTREAM = _upstream() or Path("/nonexistent")


def _specs() -> list[Path]:
    """Every committed program, found rather than listed."""
    return sorted(ALGORITHMS.glob("*/spec/*_program.json"))


def _ids(paths: list[Path]) -> list[str]:
    return [p.parent.parent.name for p in paths]


SPECS = _specs()


def _require_upstream():
    if not (UPSTREAM / "edge_ir/ir/program.py").exists():
        pytest.skip(f"no IR checkout at {UPSTREAM}")
    if str(UPSTREAM) not in sys.path:
        sys.path.insert(0, str(UPSTREAM))


def _builder_for(spec: Path) -> Path | None:
    """The script that generates this program, if the algorithm has one."""
    cands = sorted(spec.parent.glob("build_*_program.py"))
    return cands[0] if cands else None


def test_there_is_at_least_one_spec_to_check():
    """A glob that matches nothing passes every parametrized test below."""
    assert SPECS, f"no */spec/*_program.json under {ALGORITHMS}"


@pytest.mark.parametrize("spec", SPECS, ids=_ids(SPECS))
def test_program_parses_as_ir(spec: Path):
    """Layer 1: the IR's own parser accepts it.

    This is the check whose absence let four transcription errors through.
    """
    _require_upstream()
    from pydantic import ValidationError

    from edge_ir.ir.program import Program

    try:
        Program.model_validate(json.loads(spec.read_text()))
    except ValidationError as e:
        # Group by (error kind, field): 49 raw errors were 4 real mistakes,
        # and the raw list buries that.
        seen: dict[tuple[str, str], tuple[int, str]] = {}
        for err in e.errors():
            key = (err["type"], str(err["loc"][-1] if err["loc"] else "?"))
            n, where = seen.get(key, (0, ".".join(str(x) for x in err["loc"])))
            seen[key] = (n + 1, where)
        lines = [
            f"  {n:3}x  {kind:22} {field:18} e.g. {where}"
            for (kind, field), (n, where) in sorted(
                seen.items(), key=lambda kv: -kv[1][0]
            )
        ]
        pytest.fail(
            f"{spec.relative_to(ROOT)} is not valid IR: "
            f"{e.error_count()} errors, {len(seen)} distinct kinds.\n"
            + "\n".join(lines)
            + "\n\nThis file should be GENERATED by a builder that constructs "
            "edge_ir objects, not written by hand -- see this module's "
            "docstring."
        )


@pytest.mark.parametrize("spec", SPECS, ids=_ids(SPECS))
def test_program_passes_layer_two(spec: Path):
    """Layer 2: the cross-reference checks upstream ships.

    Today that is single assignment -- no two Einsums writing the same tensor
    slice. Note that upstream's pass REPORTS and does not raise, so a program
    that violates the rule still loads and still runs; nothing but a test like
    this one makes the finding matter.

    Clean is the default, and it is achievable: upstream's bfs, dfs,
    bellman-ford and label-propagation all come out empty. Max-flow does not,
    for reasons that are known and mostly not its fault -- so it carries a
    baseline in `spec/known_ir_violations.json`, asserted in BOTH directions.
    A newly violating tensor fails, and so does one that has been fixed, since
    then the baseline is stale and should shrink. A finding that is merely
    tolerated is a finding nobody will ever read again.
    """
    _require_upstream()
    from edge_ir.ir.program import Program
    from edge_ir.validator.single_assignment import check_single_assignment

    try:
        program = Program.model_validate(json.loads(spec.read_text()))
    except Exception:
        pytest.skip("covered by test_program_parses_as_ir")

    baseline_file = spec.parent / "known_ir_violations.json"
    expected = set()
    if baseline_file.exists():
        expected = set(
            json.loads(baseline_file.read_text())
            .get("singleAssignment", {})
            .get("tensors", [])
        )

    violations = check_single_assignment(program)
    actual = {v.tensor for v in violations}

    new = actual - expected
    assert not new, (
        f"{spec.relative_to(ROOT)}: single assignment violated for "
        f"{sorted(new)}, which the baseline does not allow.\n"
        + "\n".join(f"  {v}" for v in violations if v.tensor in new)
        + f"\n\nIf this is deliberate, add it to {baseline_file.name} WITH A "
        f"REASON. If it is not, two Einsums are writing the same slice."
    )

    fixed = expected - actual
    assert not fixed, (
        f"{spec.relative_to(ROOT)}: {sorted(fixed)} no longer violate single "
        f"assignment. Good -- now remove them from {baseline_file.name}, so "
        f"the baseline keeps meaning what it says."
    )


@pytest.mark.parametrize("spec", SPECS, ids=_ids(SPECS))
def test_program_matches_whatever_generates_it(spec: Path):
    """No drift between the committed JSON and its source.

    Validity alone is not enough: a valid file can still be a hand-patched
    one, and then the builder is decoration. An algorithm's program is
    either BUILT here (a `build_*_program.py` beside it) or VENDORED from
    upstream, and either way the committed copy has to match its source.
    """
    _require_upstream()

    builder = _builder_for(spec)
    if builder is None:
        # Vendored. test_build_gate.py compares it against upstream's copy;
        # this only insists that one of the two paths applies.
        upstream_copy = next(
            (
                p
                for rel in ("examples/algorithms", "test-algorithms")
                if (p := UPSTREAM / rel / spec.parent.parent.name / spec.name).exists()
            ),
            None,
        )
        assert upstream_copy is not None, (
            f"{spec.relative_to(ROOT)} has neither a builder beside it nor a "
            f"copy upstream, so nothing says where it came from. Add a "
            f"build_*_program.py, or vendor it from a program upstream ships."
        )
        assert json.loads(spec.read_text()) == json.loads(
            upstream_copy.read_text()
        ), f"{spec.relative_to(ROOT)} has drifted from upstream's copy"
        return

    env = dict(os.environ, PYTHONPATH=str(UPSTREAM))
    r = subprocess.run(
        [sys.executable, str(builder)],
        capture_output=True, text=True, cwd=ROOT, env=env,
    )
    assert r.returncode == 0, (
        f"{builder.relative_to(ROOT)} failed:\n{r.stderr}"
    )
    assert json.loads(r.stdout) == json.loads(spec.read_text()), (
        f"{spec.relative_to(ROOT)} differs from what "
        f"{builder.relative_to(ROOT)} produces. Regenerate it:\n"
        f"    PYTHONPATH=$EDGE_IR_REPO python3 {builder.relative_to(ROOT)} "
        f"> {spec.relative_to(ROOT)}"
    )
