"""Case statements, inner cascades and conditional cascades, through the tool.

These are the constructs edge-core-ir's local patches for issues 8, 9 and 10
(docs/issues-for-edge-core-ir.md) add. Each layer of the workbench that reads
a cascade has to understand them: the einsum.edge reader, the comparison with
the tutorial, the checks against the IR, coverage, the driver and the
formulas.

`tests/fixtures/bubble-sort/` is an author directory for the bubble-sort
tutorial (edge-algorithms `_algorithms/bubble-sort.md`): a nested cascade
whose every Einsum is a case statement. It is a fixture rather than an
example because nobody has approved its verifier; the end-to-end test
approves a temporary copy with a throwaway ledger. Its tutorial is the
published one plus a `ranks:` block (the tutorial has none); its Einsums are
untouched. `builder.md` and `tutorial-data.json` are the two model replies,
saved so the test needs no model.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from approval_fixture import approve_in_tmp  # noqa: E402
from edge_workbench import builder_prompt  # noqa: E402
from edge_workbench import cascade_shape as shape  # noqa: E402
from edge_workbench import coverage, spec_check  # noqa: E402
from edge_workbench import spec_surface as ss  # noqa: E402
from edge_workbench import tutorial_vs_edge as tve  # noqa: E402
from edge_workbench.approval import LEDGER_ENV  # noqa: E402
from edge_workbench.render import latex  # noqa: E402
from edge_workbench.spec_check import upstream  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bubble-sort"
DOBFS = ROOT / "examples" / "direction-optimizing-bfs"


# ------------------------------------------------------- einsum.edge ---

def test_a_case_statement_keeps_its_arms() -> None:
    e = ss.parse_edge_file(FIXTURE / "einsum.edge")["E01"]
    assert e.output == "Z" and e.output_ranks == ("0", "j", "n")
    arms = ss.case_arms(e.text)
    assert [(a.expr, a.cond) for a in arms] == [
        ("Z_{0, j-1, n}", "n < j"),
        ("min(Z_{0, j-1, j}, A_{j+1})", "n = j"),
        ("max(Z_{0, j-1, j}, A_{j+1})", "n = j+1"),
        ("empty", ""),
    ]
    assert arms[-1].is_empty


def test_rank_arithmetic_in_a_subscript_is_not_an_operator_name() -> None:
    """`j-1` used to read as a hyphenated operator, like `pick-parent`."""
    surface = ss.parse_edge_file(FIXTURE / "einsum.edge")
    assert all(e.named_ops == () for e in surface.values())
    assert ss._analyse("E", "T_{i, s*} = C_{i-1, s} :: <<<_{s*} 1(pick-one)"
                       ).named_ops == ("pick-one",)


def test_an_arm_may_carry_its_own_actions() -> None:
    text = ss.join_statement([
        "Z_{m, n} = cases:",
        "A_{m, n}                                   if n != m",
        "B_{k, m} . C_{k, n} :: /\\_k *(∩) \\/_k +(∪)   otherwise",
    ])
    first, second = ss.case_arms(text)
    assert (first.expr, first.cond) == ("A_{m, n}", "n != m")
    assert second.cond == ""
    assert [(s.action, s.compute, s.merge) for s in ss.parse_specs(second.expr)] \
        == [("map", "*", "intersect"), ("reduce", "+", "union")]


def test_inner_cascade_depth_is_read_from_the_markers() -> None:
    surface = ss.parse_edge_file(FIXTURE / "einsum.edge")
    assert {k: e.depth for k, e in surface.items()} == {
        "E01": 2, "E02": 2, "E03": 2}
    flat = ss.parse_edge_file(DOBFS / "einsum.edge")
    assert {e.depth for e in flat.values()} == {1}


# ---------------------------------------------- tutorial vs einsum.edge ---

def test_the_fixture_tutorial_matches_its_einsum_edge() -> None:
    assert tve.compare(FIXTURE / "bubble-sort.md", FIXTURE / "einsum.edge") == []


def test_the_tutorial_side_reads_cases_init_and_both_diamonds() -> None:
    t = tve.read_tutorial(FIXTURE / "bubble-sort.md")
    assert t.initialization == [
        "Z_{0, 0, n} = cases: min(A_0, A_1) if n = 0 ; max(A_0, A_1) if n = 1 "
        "; empty otherwise"]
    assert [ln.key() for ln in t.cascade] == [("z", "0"), ("z", "i"), ("z", "i")]
    assert t.stopping == ["<><> : j == J", "<> : Z_{i+1, J-1} == Z_{i, J-1}"]
    assert t.declarations["Z"].ranks == ("I", "J", "M")


@pytest.mark.parametrize("old, new, expect", [
    ("if n = j+1", "if n = j+2", "arm 3 differs"),
    ("min(Z_{0, j-1, j}, A_{j+1})", "max(Z_{0, j-1, j}, A_{j+1})",
     "arm 2 differs"),
    ("    Z_{i-1, J-1, n}                         if n > j+1\n", "",
     "has 4 arm(s), einsum.edge's has 3"),
    ("    empty           otherwise", "    empty           if n = 2",
     "initialization"),
    ("<><> : j == J", "<><> : j == J-1", "stopping condition"),
])
def test_a_changed_arm_or_diamond_is_a_finding(tmp_path, old, new, expect) -> None:
    edge = tmp_path / "einsum.edge"
    text = (FIXTURE / "einsum.edge").read_text()
    assert old in text
    edge.write_text(text.replace(old, new, 1))
    found = tve.compare(FIXTURE / "bubble-sort.md", edge)
    assert any(expect in f for f in found), found


def test_einsum_edge_may_name_another_of_the_tutorials_cascades(tmp_path) -> None:
    """DO-BFS gives top-down in `edge_expression` and bottom-up under
    Variants; `- Cascade: Bottom-Up` selects the second."""
    md = next(DOBFS.glob("*.md"))
    bottom_up = tve.read_tutorial(md, "Bottom-Up")
    assert [ln.einsum.output for ln in bottom_up.cascade] == [
        "Visited", "NV", "CandParents", "InF", "Temp", "Tree", "F"]
    assert "InF" in bottom_up.declarations
    edge = tmp_path / "einsum.edge"
    edge.write_text("- Cascade: Bottom-Up\n- Tensors\n")
    assert tve.selected_cascade(edge) == "Bottom-Up"
    assert tve.selected_cascade(DOBFS / "einsum.edge") is None
    # The walkthrough explains the edge_expression cascade, not this one.
    assert tve.authored_meanings(md, edge) == {}
    with pytest.raises(tve.tut.TutorialError, match="Cascades it gives in full"):
        tve.read_tutorial(md, "Sideways")


# ------------------------------------------------------------ the IR ---

@pytest.fixture(scope="module")
def program(tmp_path_factory) -> dict:
    root = upstream()
    if root is None:
        pytest.skip("no edge-core-ir checkout")
    files, problems = builder_prompt.parse_reply(
        (FIXTURE / "builder.md").read_text(), "bubble-sort")
    assert not problems
    work = tmp_path_factory.mktemp("builder")
    for name, body in files.items():
        (work / name).write_text(body)
    r = subprocess.run([sys.executable, "build_bubble_sort_program.py"],
                       cwd=work, capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=str(root)))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _cascade(program: dict) -> dict:
    surface = ss.parse_edge_file(FIXTURE / "einsum.edge")
    labels, problems = spec_check.label_map(surface, program, {})
    assert not problems
    return {"labels": labels, "displayNames": {}, "generationalRank": "I"}


def _findings(program: dict) -> list[str]:
    return spec_check.spec_versus_ir(
        ss.parse_edge_file(FIXTURE / "einsum.edge"),
        ss.parse_declarations(FIXTURE / "einsum.edge"),
        program, _cascade(program))


def test_the_tree_is_numbered_depth_first(program) -> None:
    nodes = shape.flat_nodes(program)
    assert [shape.rank_text(n["output_ranks"][0]) + ","
            + shape.rank_text(n["output_ranks"][1]) for n in nodes] == [
        "0,j", "i,0", "i,j"]
    assert [p["ranks"] for p in shape.placement(program)] == [["i", "j"]] * 3
    assert len(shape.stopping_conditions(program)) == 2
    assert _cascade(program)["labels"] == {"E01": 0, "E02": 1, "E03": 2}


def test_the_fixture_program_matches_einsum_edge(program) -> None:
    assert spec_check.layer_one(program) == []
    assert _findings(program) == []
    assert spec_check.single_assignment(
        program, FIXTURE / "einsum.edge", _cascade(program)) == []


def _inner(program: dict) -> dict:
    return program["main_edge"]["cascade"]["einsums"][0]


def test_a_wrong_arm_condition_is_a_finding(program) -> None:
    bad = copy.deepcopy(program)
    _inner(bad)["einsums"][0]["expression"]["arms"][1]["where"]["op"] = "<="
    found = _findings(bad)
    assert any("E01 arm 2" in f and "spec condition `n = j`" in f
               and "IR condition `n <= j`" in f for f in found), found


def test_a_dropped_arm_and_a_filled_empty_arm_are_findings(program) -> None:
    bad = copy.deepcopy(program)
    arms = _inner(bad)["einsums"][0]["expression"]["arms"]
    arms[3]["expression"] = arms[0]["expression"]
    assert any("E01 arm 4" in f and "`empty`" in f for f in _findings(bad))
    del arms[3]
    assert any("E01: einsum.edge writes 4 arm(s), the IR has 3" in f
               for f in _findings(bad))


def test_an_arm_must_apply_the_function_the_spec_writes(program) -> None:
    bad = copy.deepcopy(program)
    arm = _inner(bad)["einsums"][2]["expression"]["arms"][1]
    arm["specs"][0]["compute_op"]["name"] = "max"
    assert any("E03 arm 2" in f and "applies `min`" in f for f in _findings(bad))


def test_an_einsum_lifted_out_of_its_inner_cascade_is_a_finding(program) -> None:
    bad = copy.deepcopy(program)
    outer = bad["main_edge"]["cascade"]
    outer["einsums"].append(_inner(bad)["einsums"].pop())
    found = _findings(bad)
    assert any(f.startswith("E03: einsum.edge puts it in an inner cascade")
               for f in found), found


def test_a_case_statement_must_lower_to_cases(program) -> None:
    bad = copy.deepcopy(program)
    node = _inner(bad)["einsums"][1]
    node["expression"] = node["expression"]["arms"][2]["expression"]
    assert any("E02" in f and "is not a `Cases`" in f for f in _findings(bad))


def test_a_case_statement_renders_as_cases(program) -> None:
    shown = latex.render_all(program, _cascade(program), {})
    assert shown["E03"].startswith(r"Z_{i,j,n} = \begin{cases} ")
    assert r"\text{min}" in shown["E03"] or r"\min" in shown["E03"]
    assert r"& n = j+1" in shown["E03"] and r"& n > j+1" in shown["E03"]
    assert r"\text{empty} & \text{otherwise}" in shown["E01"]
    assert "?" not in "".join(shown.values())
    # The inner cascade's diamond is doubled and comes first.
    assert shown["stop"].index(r"\diamond\diamond") < shown["stop"].index(
        r"\diamond \,:\; Z_{i+1,J-1}")


# ---------------------------------------------------------- coverage ---

def test_a_case_arm_that_claims_no_point_must_be_exercised_somewhere(program) -> None:
    cascade = _cascade(program)
    ran = {"0": 9, "1": 9, "2": 9, "init:0": 1,
           **{coverage.arm_key(n, a): 5 for n in range(3) for a in range(4)}}
    assert coverage.measure(program, cascade, ran).ok

    del ran[coverage.arm_key(2, 3)]
    cov = coverage.measure(program, cascade, ran)
    assert cov.needs_instances
    assert cov.not_on_example == ["E03 case 4 (n > j+1)"]
    # Reached by a random instance: named on the coverage line, not fatal.
    reached = coverage.measure(program, cascade, ran, {coverage.arm_key(2, 3): 2})
    assert reached.ok and "E03 case 4" in reached.summary()
    # Reached by nothing: the build stops.
    dead = coverage.measure(program, cascade, ran, {})
    assert not dead.ok and "arms nothing exercised" in dead.report()
    # An arm written `empty` computes nothing and is never asked for.
    assert coverage.arm_key(0, 3) not in cov.arm_keys


def _conditional_program() -> dict:
    def einsum(name):
        return {"output_tensor": name,
                "output_ranks": [{"kind": "var", "name": "i"}],
                "expression": {"kind": "input",
                               "proj": {"tensor": "X", "ranks": []}},
                "specs": []}
    return {
        "declarations": [],
        "initialization": {"einsums": []},
        "main_edge": {"cascade": {"einsums": [
            einsum("A"),
            {"kind": "conditional", "arms": [
                {"when": None, "macro": "TOP-DOWN", "einsums": [einsum("B")]},
                {"when": None, "macro": "BOTTOM-UP",
                 "einsums": [einsum("C"), einsum("D")]}]},
            einsum("E")]}},
    }


def test_conditional_arms_are_numbered_and_placed() -> None:
    program = _conditional_program()
    assert [n["output_tensor"] for n in shape.flat_nodes(program)] == list("ABCDE")
    placed = shape.placement(program)
    assert placed[0]["arms"] == [] and placed[4]["arms"] == []
    assert [p["arms"][0]["macro"] for p in placed[1:4]] == [
        "TOP-DOWN", "BOTTOM-UP", "BOTTOM-UP"]


def test_an_untaken_conditional_arm_is_not_a_dead_einsum_if_instances_take_it() -> None:
    program = _conditional_program()
    cascade = {"labels": {f"E0{k + 1}": k for k in range(5)}}
    ran = {"0": 3, "1": 3, "4": 3}                  # BOTTOM-UP never taken
    cov = coverage.measure(program, cascade, ran)
    assert cov.never_executed == []
    assert cov.not_on_example == ["E03 (BOTTOM-UP arm)", "E04 (BOTTOM-UP arm)"]
    assert coverage.measure(program, cascade, ran, {"2": 1, "3": 1}).ok
    assert coverage.measure(program, cascade, ran, {"2": 1}).unexercised == [
        "E04 (BOTTOM-UP arm)"]
    # Outside an arm nothing changes: an Einsum that never ran is fatal.
    assert coverage.measure(program, cascade, {"0": 3, "1": 3},
                            {"4": 9}).never_executed == ["E05"]


# -------------------------------------------------------- end to end ---

def test_bubble_sort_passes_every_check(tmp_path: Path) -> None:
    if upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    work = tmp_path / "bubble-sort"
    work.mkdir()
    for name in ("bubble-sort.md", "einsum.edge", "verifier.py"):
        shutil.copy(FIXTURE / name, work / name)
    replies = work / "workbench" / "replies"
    replies.mkdir(parents=True)
    shutil.copy(FIXTURE / "builder.md", replies / "builder.md")
    shutil.copy(FIXTURE / "tutorial-data.json", replies / "tutorial-data.json")
    ledger = tmp_path / "approved.json"
    env = dict(os.environ, **{LEDGER_ENV: str(ledger)})
    out = ""
    for _ in range(3):
        # Approved twice by design: once for the verifier, once more when the
        # tutorial-data step first records the published answer.
        approve_in_tmp(work, ledger)
        r = subprocess.run(
            [sys.executable, "-m", "edge_workbench", "check", str(work)],
            cwd=ROOT, capture_output=True, text=True, timeout=600, env=env)
        out = r.stdout + r.stderr
        if r.returncode == 0:
            break
    assert r.returncode == 0, out
    assert "3 Einsums -> 3 IR nodes" in out
    # 3 passes x 3 steps x 3 Einsums: the inner cascade ran inside the outer.
    assert "27 executions" in out
    assert "random instances: 12/12 agree" in out
    assert "sorted array [1, 2, 3, 4]" in out
    assert (work / "index.html").exists()
