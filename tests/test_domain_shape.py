"""Which picture an algorithm wants, and why that is a rule rather than a taste.

A rank-2 tensor is a graph on its two rank sets -- an adjacency matrix is
exactly that. Same rank set on both sides gives the directed graph max-flow
draws; different sets give a bipartite graph, which is what exact cover IS
(rows are sets, columns are elements, a cover picks rows so every column has
degree one). So `graph` and `bipartite` are one renderer over two layouts.

THE TRAP THESE TESTS EXIST FOR
------------------------------
"Two rank names means bipartite" is wrong, and wrong on the algorithm we
already ship: max-flow declares `U` and `V` and they are the same six
vertices. A rule built on rank COUNT would classify max-flow as bipartite and
draw twelve nodes where there are six.

The signal that works is where the rank-1 tensors live. A vertex property is a
property of a vertex whichever position it is read in, so max-flow's twelve
rank-1 tensors are all over `U` and none over `V`. Rows and columns are
different things with different properties, so exact cover has them over both.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import domain_shape, tensor_facts  # noqa: E402

SPEC = ROOT / "algorithms" / "max-flow" / "spec"


def _decl(name, ranks, dtype="bool", empty=False):
    return {
        "name": name,
        "ranks": [{"name": r, "shape": None} for r in ranks],
        "data_type": {"name": dtype},
        "empty_value": empty,
    }


def _program(decls):
    return {"declarations": decls, "main_edge": {"cascade": {"einsums": []}}}


EXACT_COVER = _program([
    _decl("A", ["R", "C"]),
    _decl("SelRow", ["I", "R"]), _decl("ActiveRow", ["I", "R"]),
    _decl("CovCol", ["I", "C"]), _decl("ActiveCol", ["I", "C"]),
    _decl("RowCounts", ["I", "C"], "int", 0),
])
SEQUENCE_ONLY = _program([_decl("Arr", ["I", "P"], "int", 0)])


################################################################################
# the shipped algorithm must not be misread
################################################################################


def test_max_flow_is_a_plain_graph_despite_declaring_two_ranks():
    """The case a rank-count rule gets wrong.

    `U` and `V` are the same vertex set, and the giveaway is that every
    rank-1 tensor is over `U`. Classifying this as bipartite would draw two
    node sets of six where there are six vertices.
    """
    program = json.loads((SPEC / "max_flow_program.json").read_text())
    instance = json.loads((SPEC / "instance.json").read_text())

    assert len(tensor_facts.node_ranks(program)) == 2, (
        "this test is pointless unless max-flow really does declare two ranks"
    )
    result = domain_shape.classify(program, instance)
    assert result["view"] == domain_shape.GRAPH
    assert result["sides"] == ()


def test_max_flows_rank_one_tensors_all_live_on_one_rank():
    """The property the rule rests on, asserted directly.

    If a spec change ever puts a rank-1 tensor on `V`, the classification
    above silently flips and the page draws a different picture. Better to
    fail here, where the reason is written down.
    """
    program = json.loads((SPEC / "max_flow_program.json").read_text())
    sides = tensor_facts.rank_sides(program)
    ranks = {v[0] for v in sides.values() if len(v) == 1}
    assert ranks == {"U"}, f"rank-1 tensors are spread over {sorted(ranks)}"


################################################################################
# the shapes we do not ship yet
################################################################################


def test_two_decorated_ranks_are_a_bipartite_graph():
    result = domain_shape.classify(EXACT_COVER, {"extent": {"R": 4, "C": 3}})
    assert result["view"] == domain_shape.BIPARTITE
    assert result["sides"] == ("R", "C")
    assert "different sets" in result["reason"]


def test_equal_extents_do_not_make_it_a_plain_graph():
    """A 4x4 exact-cover matrix is still bipartite.

    Extents are the weaker signal and only ever confirm; a rule that leaned on
    them would misread a square instance.
    """
    result = domain_shape.classify(EXACT_COVER, {"extent": {"R": 4, "C": 4}})
    assert result["view"] == domain_shape.BIPARTITE


def test_no_rank_two_tensor_is_a_sequence():
    result = domain_shape.classify(SEQUENCE_ONLY, {"extent": {"P": 8}})
    assert result["view"] == domain_shape.SEQUENCE
    assert "no tensor is indexed by two ranks" in result["reason"]


def test_every_classification_says_why():
    """A view chosen for no stated reason is a view nobody can argue with."""
    for program, instance in (
        (json.loads((SPEC / "max_flow_program.json").read_text()),
         json.loads((SPEC / "instance.json").read_text())),
        (EXACT_COVER, {"extent": {"R": 4, "C": 3}}),
        (SEQUENCE_ONLY, {"extent": {"P": 8}}),
    ):
        assert len(domain_shape.classify(program, instance)["reason"]) > 30


################################################################################
# the layout
################################################################################


def test_bipartite_node_ids_are_side_qualified():
    """Row 0 and column 0 are different nodes that share an index.

    A flat id list cannot express that, and a renderer keying `positions[0]`
    would put a column marking on a row. This is why bipartite support is not
    only a layout change.
    """
    pos = domain_shape.bipartite_positions(4, 3, "R", "C")
    assert set(pos) == {f"R:{i}" for i in range(4)} | {f"C:{i}" for i in range(3)}
    assert pos["R:0"] != pos["C:0"]


def test_the_two_sides_are_in_two_columns():
    pos = domain_shape.bipartite_positions(4, 3, "R", "C")
    left = {pos[f"R:{i}"][0] for i in range(4)}
    right = {pos[f"C:{i}"][0] for i in range(3)}
    assert len(left) == 1 and len(right) == 1, "each side is one column"
    assert left.pop() < right.pop(), "left rank on the left"


def test_a_single_node_on_a_side_is_centred_not_at_the_top():
    pos = domain_shape.bipartite_positions(3, 1, "R", "C")
    assert pos["C:0"][1] == pytest.approx(160, abs=2)


def test_positions_do_not_collide_within_a_side():
    pos = domain_shape.bipartite_positions(6, 6, "R", "C")
    ys = [pos[f"R:{i}"][1] for i in range(6)]
    assert len(set(ys)) == 6, "rows must not overlap"
