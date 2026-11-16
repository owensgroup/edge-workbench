"""A tutorial's `working_example_data` becomes the instance.

Checked on the set-cover fixture: a matrix example, the shape max-flow's
original contract could not express.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import tutorial  # noqa: E402


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
