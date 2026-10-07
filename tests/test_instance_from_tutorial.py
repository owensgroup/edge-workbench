"""The instance comes from the tutorial, and the tutorial checks the answer.

WHAT THIS REPLACED
------------------
`instance.json` used to be written by hand here, describing a 6-vertex graph
(CLRS Figure 26.1) that appeared nowhere else. The tutorial on the website
described a *different* graph in its worked example -- 4 vertices, maximum flow
5 -- with a generation-by-generation trace. So the page offered a careful
walkthrough of a problem its own prose never mentioned, and nothing connected
the two. Either could have been wrong without the other noticing.

Now the tutorial's `working_example_data` IS the instance, and its `expect`
block is the oracle. That inverts the usual arrangement: the answer being
checked against is the author's published one, not a number written in this
repository. A tool that grades itself is not being graded.

WHY THE PUSHES CAN BE ASSERTED EXACTLY
--------------------------------------
`pick-admissible-edge` is a free choice, so in general a run may differ from
another legitimately, and asserting a specific trace would be asserting a
choice the specification does not make. On this instance it does not arise:
measured over 12 seeds, every seed produces the same push sequence, the same
4 generations and the same flow. The example is choice-independent, which is
what lets the tutorial publish a trace at all -- and
`test_the_example_does_not_depend_on_the_free_choice` keeps that honest, so if
a future instance loses the property the exact-trace check stops being trusted
rather than starting to lie.

    EDGE_TUTORIAL=~/Projects/edge-algorithms/_algorithms/maximum-flow.md pytest
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import tutorial  # noqa: E402
from edge_workbench.driver import run as driver  # noqa: E402

ALG = "max-flow"
SPEC = ROOT / "algorithms" / ALG / "spec"
DEFAULT_TUTORIAL = (
    Path.home() / "Projects/edge-algorithms/_algorithms/maximum-flow.md"
)


def _tutorial() -> Path:
    return Path(os.environ.get("EDGE_TUTORIAL", DEFAULT_TUTORIAL))


def _require_tutorial() -> Path:
    md = _tutorial()
    if not md.exists():
        pytest.skip(f"no tutorial checkout at {md}")
    return md


def _expect() -> dict:
    example = tutorial.read_example(_require_tutorial())
    if "expect" not in example:
        pytest.skip("the tutorial publishes no expected answer")
    return example["expect"]


def _pushes(steps: list[dict]) -> dict[int, list]:
    """Per generation, the pushes the run actually made.

    `delta` is antisymmetric, so each push appears twice -- once positive on
    the forward cell and once negative on the reverse. Only the positive
    entries are pushes.
    """
    out: dict[int, list] = {}
    for s in steps:
        if s["einsum"] == "E11" and s.get("iteration"):
            out[s["iteration"]] = sorted(
                [int(c.split(",")[0]), int(c.split(",")[1]), v]
                for c, v in s["state"].get("delta", {}).items() if v > 0
            )
    return out


# --------------------------------------------------------------- drift ---

def test_the_committed_instance_is_the_one_the_tutorial_describes():
    """No drift between instance.json and the tutorial's worked example.

    The instance is committed rather than built during `npm run build`, for
    the same reason the IR program is vendored: a clean clone must build with
    node and Python and no sibling checkout. This is what stops that
    convenience from quietly becoming a second, divergent copy.
    """
    md = _require_tutorial()
    builder = SPEC / "build_instance.py"
    assert builder.exists(), f"no {builder.name}; the instance has no source"

    r = subprocess.run(
        [sys.executable, str(builder)],
        capture_output=True, text=True, cwd=ROOT,
        env=dict(os.environ, EDGE_TUTORIAL=str(md)),
    )
    assert r.returncode == 0, f"{builder.name} failed:\n{r.stderr}"
    assert json.loads(r.stdout) == json.loads(
        (SPEC / "instance.json").read_text()
    ), (
        f"instance.json differs from what the tutorial describes. "
        f"Regenerate it:\n"
        f"    EDGE_TUTORIAL={md} python3 "
        f"{builder.relative_to(ROOT)} > {(SPEC / 'instance.json').relative_to(ROOT)}"
    )


def test_the_instance_is_not_hand_written():
    """It must say where it came from, so nobody edits it in place."""
    inst = json.loads((SPEC / "instance.json").read_text())
    note = " ".join(inst.get("_comment", []))
    assert "GENERATED" in note and "tutorial" in note.lower(), (
        "instance.json carries no provenance note"
    )


# -------------------------------------------------------------- oracle ---

def test_the_run_reproduces_the_tutorials_published_answer():
    """The flow and the generation count the tutorial states."""
    expect = _expect()
    r = driver.run(ALG)
    inst = json.loads((SPEC / "instance.json").read_text())
    sink = str(inst["domain"]["graph"]["sink"])

    flow = r["steps"][-1]["state"].get("E", {}).get(sink)
    assert flow == expect["flow"], (
        f"the tutorial publishes a maximum flow of {expect['flow']}; the run "
        f"produced {flow}"
    )
    if "generations" in expect:
        assert r["generations"] == expect["generations"], (
            f"the tutorial's trace runs {expect['generations']} generations; "
            f"the run took {r['generations']}"
        )


def test_the_run_reproduces_every_push_the_tutorial_states():
    """Not just the answer -- the route to it, generation by generation.

    The flow value alone is a weak check: a wrong cascade can reach the right
    total. The tutorial states which vertex pushed how much along which edge
    in each generation, and that is a real trace to be held to.
    """
    expect = _expect()
    if "pushes" not in expect:
        pytest.skip("the tutorial publishes no per-generation trace")

    want = {int(g): sorted(map(list, p)) for g, p in expect["pushes"].items()}
    got = _pushes(driver.run(ALG)["steps"])

    for g in sorted(want):
        assert got.get(g) == want[g], (
            f"generation {g}: the tutorial states pushes {want[g]}, the run "
            f"made {got.get(g)}"
        )
    assert set(got) == set(want), (
        f"the run has generations {sorted(got)}, the tutorial states "
        f"{sorted(want)}"
    )


def test_the_example_does_not_depend_on_the_free_choice():
    """What licenses the exact-trace check above.

    `pick-admissible-edge` says ANY admissible edge, so two runs may differ
    legitimately and a pinned trace would be asserting a choice the spec does
    not make. This instance happens not to exercise the freedom -- every seed
    takes the same route. If that ever stops being true, this fails and the
    trace check above must weaken to the flow value, rather than silently
    becoming a claim about one arbitrary execution.
    """
    seeds = range(8)
    routes = {
        json.dumps(_pushes(driver.run(
            ALG, selectors={"pick-admissible-edge":
                            {"rule": "seeded", "seed": s}}
        )["steps"]), sort_keys=True)
        for s in seeds
    }
    assert len(routes) == 1, (
        f"{len(routes)} different push sequences over {len(list(seeds))} "
        f"seeds, so the tutorial's trace is only one legal execution. The "
        f"exact-trace check is no longer safe: hold the run to the flow value "
        f"instead."
    )


################################################################################
# a matrix problem -- the shape max-flow's contract could not express
################################################################################

SET_COVER = Path(__file__).resolve().parent / "fixtures" / "set_cover_tutorial.md"


def _set_cover():
    if not SET_COVER.exists():
        pytest.skip("no set-cover tutorial fixture")
    return tutorial.read_example(SET_COVER)


def test_a_matrix_example_needs_no_source_or_sink():
    """Required fields follow the SHAPE of the problem.

    `working_example_data` was written for max-flow and demanded vertices, a
    source, a sink and capacities. Exact cover has none of those -- it has
    rows over columns -- and forcing that vocabulary would make a tutorial
    describe its problem as something it is not.
    """
    example = _set_cover()
    assert example["kind"] == "matrix"
    assert "source" not in example and "sink" not in example
    assert example["rows"] == 4 and example["columns"] == 3


def test_the_matrix_is_the_one_the_prose_states():
    """R0={C0}, R1={C1}, R2={C0,C1}, R3={C2} -- Working Example 1."""
    instance = tutorial.to_instance(_set_cover())
    assert instance["tensors"]["A"] == {
        "0,0": True, "1,1": True, "2,0": True, "2,1": True, "3,2": True,
    }
    assert instance["extent"] == {"R": 4, "C": 3}


def test_a_matrix_becomes_a_bipartite_graph():
    """Rows one side, columns the other, an edge per matrix entry.

    Not a reinterpretation: for exact cover this IS the standard formulation.
    Rows are sets, columns are elements, and a cover picks rows so that every
    column has degree exactly one.
    """
    instance = tutorial.to_instance(_set_cover())
    graph = instance["domain"]["graph"]
    assert instance["domain"]["view"] == "bipartite"
    assert graph["sides"] == {"left": "R", "right": "C"}
    assert len(graph["edges"]) == 5, "one edge per matrix entry"
    assert {"u": "R:2", "v": "C:1"} in graph["edges"]


def test_node_ids_carry_their_side():
    """Row 0 and column 0 are different nodes that share an index.

    A flat id list cannot express that, and a renderer keying `positions[0]`
    would put a column's marking on a row.
    """
    instance = tutorial.to_instance(_set_cover())
    nodes = instance["domain"]["graph"]["nodes"]
    assert "R:0" in nodes and "C:0" in nodes
    positions = instance["domain"]["positions"]
    assert positions["R:0"] != positions["C:0"]


def test_the_tutorial_publishes_the_solutions_it_traces():
    """The oracle for exact cover, read off the tutorial's own trace table.

    Generation 1 reaches Succ=T with Path {R3,R2}; generation 3 with
    {R3,R0,R1}. Both are exact covers of the three columns, which is
    checkable here without running anything.
    """
    example = _set_cover()
    instance = tutorial.to_instance(example)
    cells = instance["tensors"]["A"]
    solutions = example["expect"]["solutions"]
    assert solutions, "the tutorial publishes no solution to check against"

    for rows in solutions:
        covered = [c for r in rows
                   for c in range(example["columns"])
                   if cells.get(f"{r},{c}")]
        assert sorted(covered) == list(range(example["columns"])), (
            f"rows {rows} do not cover every column exactly once: {covered}"
        )
