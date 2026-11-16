"""The tutorial's `ranks:` block: parsed, checked, and deciding the view.

The author may be an agent, so every declaration is checked against
einsum.edge, and an unknown kind stops the run rather than being guessed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import author, domain_shape, rank_kinds  # noqa: E402


def _md(tmp_path, body):
    p = tmp_path / "t.md"
    p.write_text(body)
    return p


def _decls(**tensors):
    return {n: SimpleNamespace(ranks=tuple(r)) for n, r in tensors.items()}


def _program(decls):
    return {
        "declarations": [
            {"name": n, "ranks": [{"name": r, "shape": None} for r in rs],
             "data_type": {"name": "int"}, "empty_value": 0}
            for n, rs in decls.items()
        ],
        "main_edge": {"cascade": {"einsums": []}},
    }


def test_reads_the_block_from_front_matter_only(tmp_path):
    md = _md(tmp_path, "---\ntitle: X\nranks:\n  I: generational   # gen\n"
                       "  S: vertex\n  D: Vertex\ntags: [a]\n---\n"
                       "ranks:\n  Q: position\n")
    assert rank_kinds.read(md) == {"I": "generational", "S": "vertex", "D": "vertex"}


def test_no_block_means_none(tmp_path):
    assert rank_kinds.read(_md(tmp_path, "---\ntitle: X\n---\n")) is None


def test_unknown_kind_and_missing_rank_are_both_reported():
    found = rank_kinds.problems(
        {"I": "generational", "S": "node"},
        _decls(G=("S", "D"), F=("I", "S")))
    assert any("'node'" in f and "not a rank kind" in f for f in found)
    assert any("D is used by einsum.edge but has no kind" in f for f in found)


def test_rank_not_in_spec_and_misplaced_round():
    found = rank_kinds.problems(
        {"I": "generational", "S": "vertex", "Z": "vertex"},
        _decls(F=("S", "I")))
    assert any("declares Z" in f for f in found)
    assert any("not the first rank of F" in f for f in found)


def test_set_needs_element():
    found = rank_kinds.problems({"R": "set"}, _decls(A=("R",)))
    assert any("no `element` rank" in f for f in found)


def test_a_clean_block_has_no_problems():
    assert rank_kinds.problems(
        {"I": "generational", "S": "vertex", "XY": "spatial"},
        _decls(L=("S", "XY"), PQ=("I", "S"))) == []


def test_declared_kinds_decide_the_view():
    # Two position ranks: inference sees a rank-2 tensor and says graph; the
    # declaration says this is a table over positions, not edges.
    program = _program({"DP": ["P", "Q"], "Mark": ["P"]})
    assert domain_shape.classify(program)["view"] == "graph"
    kinds = {"P": "position", "Q": "position"}
    assert domain_shape.classify(program, kinds=kinds)["view"] == "sequence"
    note = domain_shape.declared_vs_inferred(kinds, program)
    assert note and "would imply graph" in note


def test_set_and_element_give_bipartite_sides():
    program = _program({"A": ["R", "C"], "Sel": ["I", "R"], "Cov": ["I", "C"]})
    shape = domain_shape.classify(program, kinds={"I": "generational", "R": "set",
                                                  "C": "element"})
    assert shape["view"] == "bipartite" and shape["sides"] == ("R", "C")
    assert domain_shape.declared_vs_inferred(
        {"I": "generational", "R": "set", "C": "element"}, program) is None


def test_location_tensor_places_vertices_and_is_not_an_edge():
    # A*: G is the graph, L_{S, XY} each vertex's location.
    program = _program({"G": ["S", "D"], "L": ["S", "XY"], "PQ": ["I", "S"]})
    # One Einsum reading G and L, so both count as inputs.
    program["main_edge"]["cascade"]["einsums"] = [{
        "output_tensor": "PQ", "output_ranks": [],
        "expression": {"kind": "binary",
                       "left": {"kind": "input", "proj": {"tensor": "G"}},
                       "right": {"kind": "input", "proj": {"tensor": "L"}}},
    }]
    artifact = {"example": {
        "kind": "tensors",
        "extent": {"S": 3, "D": 3, "XY": 2},
        "tensors": {
            "G": {"0,1": 4, "1,2": 5},
            "L": {"0,0": 0, "0,1": 0, "1,0": 10, "1,1": 0, "2,0": 10, "2,1": 10},
        },
    }}
    cascade = {"generationalRank": "I",
               "rankKinds": {"I": "generational", "S": "vertex", "D": "vertex",
                             "XY": "spatial"}}
    inst = author.make_instance(artifact, program, cascade)
    dom = inst["domain"]
    assert dom["view"] == "graph"
    assert {(e["u"], e["v"]) for e in dom["graph"]["edges"]} == {(0, 1), (1, 2)}
    assert all("L" not in e for e in dom["graph"]["edges"])
    pos = dom["positions"]
    assert pos[0][0] < pos[1][0] and pos[1][1] > pos[2][1]   # x right, y up
