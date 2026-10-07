"""The author-facing pieces of `edge_workbench check`, without a model.

Each test pins one thing that went wrong while the workflow was being built,
so it cannot quietly go wrong again.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import builder_prompt, tutorial_vs_edge, verifier  # noqa: E402
from edge_workbench.author import view_problems  # noqa: E402
from edge_workbench.spec_surface import parse_specs  # noqa: E402

# ------------------------------------------------- LaTeX -> surface --------


def _ops(text):
    return [(s.action, s.label, s.compute, s.merge) for s in parse_specs(text)]


def test_latex_spacing_does_not_eat_the_quantifier():
    """`\\ ` and `\\_` both used to swallow the backslash of `/\\`."""
    line = (r"&N_{i,d} = G_{s,d} \cdot D_{i,s} :: \textstyle\bigwedge_s "
            r"+(\cap)\ \bigvee_s \min(\cup)\\")
    assert _ops(tutorial_vs_edge.latex_to_surface(line)) == [
        ("map", None, "+", "intersect"), ("reduce", None, "min", "union")]


def test_latex_labels_and_texttt():
    line = (r"&D_{i+1,d} = D_{i,d} \cdot^1 X_{i,d} :: \textstyle"
            r"\bigwedge^1 \texttt{<<}(\cup)\\")
    assert _ops(tutorial_vs_edge.latex_to_surface(line)) == [
        ("map", 1, "update", "union")]


def test_rank_subscripted_quantifiers_parse():
    assert _ops(r"z :: \/_{v*} OR(∪)") == [("reduce", None, "OR", "union")]


# ------------------------------------------- tutorial versus einsum.edge ---

TUTORIAL = r"""---
title: Toy
edge_expression: |
  $$
  \begin{aligned}
  &\triangleright \textbf{Tensors}\\
  &A^{U \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\
  &B^{I,\, U \equiv \lvert V\rvert} \to \text{integer},\ \text{empty}=0\\[4pt]
  &\triangleright \textbf{Extended Einsum}\\
  &B_{i+1,u} = A_u \cdot B_{i,u} :: \textstyle\bigwedge +(MERGE)\\
  &\diamond : \lvert B_{i+1}\rvert \equiv 0
  \end{aligned}
  $$
---
"""

EDGE = """- Tensors
A^{U = |V|}    -> integer, empty = 0
B^{I, U = |V|} -> integer, empty = 0

- Extended Einsums
# E01: add
B_{i+1, u} = A_u . B_{i, u} :: /\\ +(∩)

<> : ||B_{i+1}|| == 0
"""


def _pair(tmp_path, merge):
    md = tmp_path / "toy.md"
    md.write_text(TUTORIAL.replace("MERGE", merge))
    edge = tmp_path / "einsum.edge"
    edge.write_text(EDGE)
    return md, edge


def test_agreeing_tutorial_and_edge_report_nothing(tmp_path):
    assert tutorial_vs_edge.compare(*_pair(tmp_path, r"\cap")) == []


def test_a_different_merge_in_the_tutorial_is_reported(tmp_path):
    found = tutorial_vs_edge.compare(*_pair(tmp_path, r"\cup"))
    assert len(found) == 1 and "operators differ" in found[0], found


# ------------------------------------------------------- pasted replies ----

def test_reply_files_are_found_by_info_string_or_heading():
    reply = ("Sure.\n\n```python file=build_toy_program.py\nprint(1)\n```\n\n"
             "**toy_functions.py**\n```python\nX = 1\n```\n")
    files, problems = builder_prompt.parse_reply(reply, "toy")
    assert set(files) == {"build_toy_program.py", "toy_functions.py"}
    assert problems == []


def test_back_to_back_fences_are_all_found():
    reply = ("```python file=build_toy_program.py\nprint(1)\n```\n"
             "```python file=toy_functions.py\nX = 1\n```\n")
    files, _ = builder_prompt.parse_reply(reply, "toy")
    assert set(files) == {"build_toy_program.py", "toy_functions.py"}


def test_a_reply_cannot_write_arbitrary_files():
    reply = "```python file=../../evil.py\nx\n```\n"
    files, problems = builder_prompt.parse_reply(reply, "toy")
    assert files == {}
    assert any("no `build_toy_program.py`" in p for p in problems)


# ------------------------------------------------------------ instances ----

PROGRAM = {
    "declarations": [
        {"name": "C", "ranks": [{"name": "U"}, {"name": "V"}]},
        {"name": "S", "ranks": [{"name": "U"}]},
        {"name": "F", "ranks": [{"name": "I"}, {"name": "U"}, {"name": "V"}]},
        {"name": "N", "ranks": []},
    ],
    "initialization": {"einsums": []},
    "main_edge": {"cascade": {"einsums": [{
        "output_tensor": "F",
        "expression": {"kind": "binary",
                       "lhs": {"kind": "input", "proj": {"tensor": "C"}},
                       "rhs": {"kind": "input", "proj": {"tensor": "S"}}},
    }, {
        "output_tensor": "F",
        "expression": {"kind": "input", "proj": {"tensor": "N"}},
    }]}},
}


def test_an_instance_must_supply_exactly_the_inputs():
    good = {"extent": {"U": 3, "V": 3}, "scalars": {"N": 3},
            "tensors": {"C": {"0,1": 2}, "S": {"0": True}}}
    assert verifier.instance_problems(good, PROGRAM) == []

    missing = dict(good, tensors={"C": {"0,1": 2}})
    assert any("S is not supplied" in p
               for p in verifier.instance_problems(missing, PROGRAM))

    written = dict(good, tensors=dict(good["tensors"], F={"0,0,1": 1}))
    assert any("F is supplied but is not an input" in p
               for p in verifier.instance_problems(written, PROGRAM))


def test_coordinates_are_checked_against_extent_and_arity():
    bad = {"extent": {"U": 3, "V": 3}, "scalars": {"N": 3},
           "tensors": {"C": {"0,9": 2}, "S": {"0,1": True}}}
    found = verifier.instance_problems(bad, PROGRAM)
    assert any("outside the extent" in p for p in found)
    assert any("has 2 coordinates" in p for p in found)


def test_answers_compare_as_values_not_as_containers():
    assert verifier.normalise({(1, 2), (0,)}) == verifier.normalise([[0], [1, 2]])
    assert verifier.normalise(5.0) == 5


# ---------------------------------------------------------------- view -----

def test_styling_names_real_tensors_of_the_right_rank():
    cascade = {"generationalRank": "I", "displayNames": {}}
    view = {"nodeFill": [{"tensor": "C"}],
            "edgeLabel": {"tensor": "S", "over": "F"}}
    found = view_problems(view, PROGRAM, cascade)
    assert any("nodeFill uses C" in p for p in found)
    assert any("edgeLabel uses S" in p for p in found)
    assert any("over is 'F'" in p for p in found)


# ------------------------------------------- single assignment, derived ----

def _need_ir():
    import pytest

    from edge_workbench.spec_check import _import_edge_ir, upstream
    if upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    _import_edge_ir()


def test_expected_overlaps_come_from_the_spec_not_a_waiver_file():
    """Max-flow's five were listed by hand in known_ir_violations.json; the
    specification alone gives the same five."""
    _need_ir()
    from edge_ir.validator.single_assignment import _Iteration

    from edge_workbench.spec_check import _overlaps, spec_write_sites
    edge = ROOT / "examples" / "maximum-flow" / "einsum.edge"
    found = _overlaps(spec_write_sites(edge), _Iteration("i", 0))
    assert sorted(found) == ["Act", "D", "E", "F", "R"]
    assert found["F"] == ["E02 and E12"]


def test_surface_ranks_read_as_upstream_reads_them():
    _need_ir()
    from edge_workbench.spec_check import _surface_key
    assert (_surface_key("i+1").kind, _surface_key("i+1").offset) == ("var", 1)
    assert _surface_key("1").kind == "const"
    assert _surface_key("u : u = s").name == "u"       # predicates not read
    assert _surface_key("v*").name == "v"
    assert _surface_key("|V|").kind == "const"
