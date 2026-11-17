"""Macros, multi-output case statements and constants, through the tool.

`examples/direction-optimizing-bfs/` is the hybrid cascade of the DO-BFS
tutorial: two macros (TOP-DOWN, BOTTOM-UP), a multi-output case statement
choosing one per generation, and two thresholds the tutorial leaves to the
user. Every layer that reads a cascade has to follow it: the einsum.edge
reader, the comparison with the tutorial, the label map (a macro's body is
written in formal names, the IR holds the expansion), the checks against the
IR, coverage, the formulas, the driver and the page.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from approval_fixture import approve_in_tmp  # noqa: E402
from edge_workbench import builder_prompt, coverage, spec_check  # noqa: E402
from edge_workbench import cascade_shape as shape  # noqa: E402
from edge_workbench import spec_surface as ss  # noqa: E402
from edge_workbench import tensor_facts  # noqa: E402
from edge_workbench import tutorial_vs_edge as tve  # noqa: E402
from edge_workbench.approval import LEDGER_ENV  # noqa: E402
from edge_workbench.render import latex  # noqa: E402
from edge_workbench.spec_check import upstream  # noqa: E402

DOBFS = ROOT / "examples" / "direction-optimizing-bfs"
EDGE = DOBFS / "einsum.edge"
MD = DOBFS / "direction-optimizing-bfs.md"
TOP_DOWN = [f"E{n:02d}" for n in range(4, 14)]
BOTTOM_UP = [f"E{n:02d}" for n in range(14, 22)]


# ------------------------------------------------------- einsum.edge ---

def test_a_multi_output_case_statement_is_read_apart_from_the_einsums() -> None:
    surface = ss.parse_edge_file(EDGE)
    assert "E03" not in surface and len(surface) == 20
    (stmt,) = surface.conditionals
    assert stmt.label == "E03"
    assert [name for name, _ in stmt.outputs] == ["Tree", "F", "TopDown"]
    assert stmt.outputs[0][1] == ("i+1", "s", "d")
    assert [(a.macro, a.cond) for a in stmt.arms] == [
        ("TOP-DOWN", "TopDown_i == True"), ("BOTTOM-UP", "TopDown_i == False")]
    assert [name for name, _ in stmt.arms[1].args] == [
        "G", "F", "Tree", "NV", "NF"]


def test_a_macro_section_owns_the_einsums_under_it() -> None:
    surface = ss.parse_edge_file(EDGE)
    assert list(surface.macros) == ["TOP-DOWN", "BOTTOM-UP"]
    assert surface.macros["TOP-DOWN"].labels == TOP_DOWN
    assert surface.macros["BOTTOM-UP"].labels == BOTTOM_UP
    assert [n for n, _ in surface.macros["TOP-DOWN"].inputs] == [
        "TG", "TF", "TTree", "TNV", "TMF", "TMU"]
    assert [n for n, _ in surface.macros["TOP-DOWN"].outputs] == [
        "TTree", "TF", "TTopDown"]
    assert surface["E01"].macro is None and surface["E08"].macro == "TOP-DOWN"


def test_a_macro_body_writes_what_the_call_binds_its_formal_name_to() -> None:
    surface = ss.parse_edge_file(EDGE)
    written = {label: e.actual for label, e in surface.items()}
    assert surface["E08"].output == "TTree" and written["E08"] == "Tree"
    assert written["E09"] == "F" and written["E13"] == "TopDown"
    # Bound by the call although the header lists them as inputs.
    assert written["E10"] == "MF" and written["E19"] == "NF"
    # Not a parameter: left alone, formal-looking name or not.
    assert written["E12"] == "TB" and written["E04"] == "Nei"
    order = ss.expansion_order(surface)
    assert [label for label, _, _ in order] == ["E01", "E02"] + TOP_DOWN + BOTTOM_UP
    assert ("E17", "Tree", ("i+1", "s", "d")) in order


def test_constants_and_a_coordinate_subscript_are_read(tmp_path) -> None:
    assert ss.parse_constants(EDGE) == {"alpha": "15", "beta": "18"}
    assert ss.HEAD_RE.match("TopDown_0 = True").group(3) == "0"
    plain = tmp_path / "einsum.edge"
    plain.write_text("- Tensors\nA^{I} -> integer, empty = 0\n"
                     "- Extended Einsums\n# E01: x\nA_i = B_i\n")
    surface = ss.parse_edge_file(plain)
    assert ss.parse_constants(plain) == {} and not surface.conditionals
    assert ss.expansion_order(surface) == [("E01", "A", ("i",))]


# ---------------------------------------------- tutorial vs einsum.edge ---

def test_the_tutorial_reader_reads_the_hybrid_and_its_own_macros() -> None:
    t = tve.read_tutorial(MD, "Hybrid")
    assert [ln.einsum.output for ln in t.cascade] == ["Visited", "NV", ""]
    assert ss.CONDITIONAL_RE.match(t.cascade[2].text)
    assert t.initialization[-1] == "TopDown_0 = True"
    # The tutorial defines TOP-DOWN twice; the compact hybrid's is not this
    # cascade's.
    assert [ln.einsum.output for ln in t.macros["TOP-DOWN"].cascade] == [
        "Nei", "NeiNV", "CandTree", "Temp", "TTree", "TF", "TMF", "TMU", "TB",
        "TTopDown"]
    assert [ln.einsum.output for ln in t.macros["BOTTOM-UP"].cascade] == [
        "CandParents", "InF", "Temp", "TTree", "TF", "TNF", "BT", "TTopDown"]
    assert t.macros["BOTTOM-UP"].header.startswith("BOTTOM-UP(TG_{s,d}")
    assert "InF" not in [ln.einsum.output
                         for ln in t.macros["TOP-DOWN"].cascade]


def test_the_example_matches_its_tutorial() -> None:
    assert tve.compare(MD, EDGE) == []


@pytest.mark.parametrize("old, new, expect", [
    ("if TopDown_i == False", "if TopDown_i == True", "arm 2 differs"),
    ("TOP-DOWN(G_{s, d}, F_{i, s}, Tree_{i, s, d}, NV_{i, c}, MF_i, MU_i)",
     "TOP-DOWN(G_{s, d}, F_{i, s}, Tree_{i, s, d}, NV_{i, c}, MU_i, MF_i)",
     "arm 1 differs"),
    ("TB_i = TMF_i . (TMU_i / alpha) :: /\\ >(∩)",
     "TB_i = TMF_i . (TMU_i / alpha) :: /\\ >(∪)", "E12 TB_{i}: operators differ"),
    ("TTopDown_{i+1} = BT_i", "TTopDown_{i+1} = TNF_i", "operands differ"),
    ("TNF_i) -> TTree_{i+1, s, d}", "TNF_i) -> TF_{i+1, d}, TTree_{i+1, s, d}",
     "macro BOTTOM-UP: the headers differ"),
    ("# E19: the frontier's size\nTNF_i = TF_{i, s} :: \\/ +(∪)\n", "",
     "macro BOTTOM-UP: the tutorial writes ['TNF_{i}']"),
    ("alpha = 15", "alpha = 14", "constant alpha"),
])
def test_a_changed_macro_call_or_constant_is_a_finding(tmp_path, old, new,
                                                      expect) -> None:
    edge = tmp_path / "einsum.edge"
    text = EDGE.read_text()
    assert old in text
    edge.write_text(text.replace(old, new, 1))
    found = tve.compare(MD, edge)
    assert any(expect in f for f in found), found


def test_a_missing_macro_section_is_a_finding(tmp_path) -> None:
    edge = tmp_path / "einsum.edge"
    edge.write_text(EDGE.read_text().split("- Macro BOTTOM-UP")[0])
    assert any("macro BOTTOM-UP" in f and "no `- Macro BOTTOM-UP(...)` section"
               in f for f in tve.compare(MD, edge))


def test_the_page_gets_the_authors_form_of_every_statement() -> None:
    written = tve.written_forms(MD, EDGE)
    assert r"\begin{pmatrix}" in written["E03"] and "TOP-DOWN" in written["E03"]
    assert written["E08"].startswith(r"\mathit{TTree}_{i+1,s,d}")
    assert r"\alpha" in written["E12"]
    assert set(written["macros"]) == {"TOP-DOWN", "BOTTOM-UP"}
    assert {f"E{n:02d}" for n in range(1, 22)} <= set(written)


# ------------------------------------------------------------ the IR ---

@pytest.fixture(scope="module")
def program() -> dict:
    """The IR the example's committed builder makes."""
    root = upstream()
    if root is None:
        pytest.skip("no edge-core-ir checkout")
    spec = DOBFS / "workbench" / "spec"
    r = subprocess.run(
        [sys.executable, "build_direction_optimizing_bfs_program.py"],
        cwd=spec, capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=os.pathsep.join([str(root), str(spec)]),
                 PYTHONDONTWRITEBYTECODE="1"))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _cascade(program: dict) -> dict:
    labels, problems = spec_check.label_map(ss.parse_edge_file(EDGE), program, {})
    assert not problems
    return {"labels": labels, "displayNames": {}, "generationalRank": "I",
            "conditionals": {"E03": {"conditional": 0,
                                     "macros": ["TOP-DOWN", "BOTTOM-UP"]}}}


def _findings(program: dict) -> list[str]:
    return spec_check.spec_versus_ir(
        ss.parse_edge_file(EDGE), ss.parse_declarations(EDGE), program,
        _cascade(program))


def test_the_label_map_follows_formal_names_into_the_expansion(program) -> None:
    labels = _cascade(program)["labels"]
    nodes = shape.flat_nodes(program)
    assert len(labels) == 20 and "E03" not in labels
    assert nodes[labels["E08"]]["output_tensor"] == "Tree"
    assert nodes[labels["E17"]]["output_tensor"] == "Tree"
    assert nodes[labels["E10"]]["output_tensor"] == "MF"
    placed = shape.placement(program)
    assert all(placed[labels[lb]]["arms"][0]["macro"] == "TOP-DOWN"
               for lb in TOP_DOWN)
    assert all(placed[labels[lb]]["arms"][0]["macro"] == "BOTTOM-UP"
               for lb in BOTTOM_UP)
    assert placed[labels["E02"]]["arms"] == []


def test_the_built_program_matches_einsum_edge(program) -> None:
    if upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    assert spec_check.layer_one(program) == []
    assert _findings(program) == []
    # Temp, Tree, F and TopDown are each written in both arms; one arm runs.
    assert spec_check.single_assignment(program, EDGE, _cascade(program)) == []
    assert spec_check.constants_versus_ir(ss.parse_constants(EDGE), program) == []


def _conditional(program: dict) -> dict:
    return shape.conditionals(program)[0]


def test_a_wrong_macro_condition_or_arm_is_a_finding(program) -> None:
    bad = copy.deepcopy(program)
    _conditional(bad)["arms"][1]["macro"] = "TOP-DOWN"
    assert any("E03 arm 2 (BOTTOM-UP): the IR arm is from macro 'TOP-DOWN'" in f
               for f in _findings(bad))

    bad = copy.deepcopy(program)
    _conditional(bad)["arms"][0]["when"]["rhs"]["proj"]["tensor"] = "Lit_False"
    assert any("E03 arm 1 (TOP-DOWN): spec condition `TopDown_i == True`" in f
               for f in _findings(bad))

    bad = copy.deepcopy(program)
    del _conditional(bad)["arms"][1]
    assert any("einsum.edge labels with no IR node" in f or "could not" in f
               or "arm(s)" in f for f in _findings(bad) + spec_check.label_map(
                   ss.parse_edge_file(EDGE), bad, {})[1])


def test_an_arm_must_be_exactly_its_macros_body(program) -> None:
    bad = copy.deepcopy(program)
    arms = _conditional(bad)["arms"]
    # The frontier-size Einsum computed outside the arm it was written in.
    moved = next(e for e in arms[1]["einsums"] if e["output_tensor"] == "NF")
    arms[1]["einsums"].remove(moved)
    bad["main_edge"]["cascade"]["einsums"].append(moved)
    labels, problems = spec_check.label_map(ss.parse_edge_file(EDGE), bad, {})
    assert problems or any("the macro's body is" in f for f in _findings(bad))


def test_an_unwritten_merge_is_lowered_as_pass_through(program) -> None:
    """E12 writes two operations and one action; the division's merge is the
    paper's default (7.3.4), and the written `>(∩)` is still required."""
    node = shape.flat_nodes(program)[_cascade(program)["labels"]["E12"]]
    specs = {(s["compute_op"].get("symbol") or s["compute_op"].get("name"),
              s["merge_op"]["symbol"]) for s in node["specs"]}
    assert specs == {("/", "pass_through"), ("gt", "intersect")}
    bad = copy.deepcopy(program)
    spec = next(s for s in shape.flat_nodes(bad)[_cascade(bad)["labels"]["E12"]]
                ["specs"] if s["merge_op"]["symbol"] == "intersect")
    spec["merge_op"]["symbol"] = "union"
    assert any("E12" in f and "gt(intersect)" in f for f in _findings(bad))


def test_a_constant_must_carry_its_value_in_the_ir(program) -> None:
    assert tensor_facts.inputs(program) == ["G"]          # not alpha, not beta
    bad = copy.deepcopy(program)
    next(d for d in bad["declarations"] if d["name"] == "Alpha")["value"] = 14
    assert any("constant alpha" in f for f in spec_check.constants_versus_ir(
        ss.parse_constants(EDGE), bad))
    bad["declarations"] = [d for d in bad["declarations"]
                           if d["name"] != "Beta"]
    assert any("constant beta" in f and "no zero-rank declaration" in f
               for f in spec_check.constants_versus_ir(
                   ss.parse_constants(EDGE), bad))


def test_a_condition_is_a_read(program) -> None:
    """`TopDown_i == False` reads the mode and the literal False."""
    assert tensor_facts.unused(program) == []
    assert "TopDown" in tensor_facts.stateful(program)


# ------------------------------------------------- coverage and formulas ---

def test_an_untaken_macro_is_named_arm_by_arm(program) -> None:
    cascade = _cascade(program)
    ran = {str(cascade["labels"][lb]): 4 for lb in ["E01", "E02"] + TOP_DOWN}
    ran.update({f"init:{k}": 1 for k in range(3)})
    cov = coverage.measure(program, cascade, ran)
    assert cov.never_executed == []
    assert cov.not_on_example == [f"{lb} (BOTTOM-UP arm)" for lb in BOTTOM_UP]
    reached = {str(cascade["labels"][lb]): 1 for lb in BOTTOM_UP}
    assert coverage.measure(program, cascade, ran, reached).ok
    assert not coverage.measure(program, cascade, ran, {}).ok


def test_the_statement_and_the_expansion_render(program) -> None:
    shown = latex.render_all(program, _cascade(program), {})
    assert shown["E03"].startswith(r"\begin{pmatrix}\mathit{Tree}_{i+1,s,d}")
    assert (r"\text{TOP-DOWN}(\cdots) & \mathit{TopDown}_{i} \equiv \text{True}"
            in " ".join(shown["E03"].split()))
    assert r"\text{BOTTOM-UP}" in shown["E03"]
    # The expansion is in the call's tensors, and MU is not the letter mu.
    assert shown["E08"].startswith(r"\mathit{Tree}_{i+1,s,d}")
    assert r"\mathit{MU}" in shown["E12"] and r"\mu" not in shown["E12"]
    assert r"/(\mathbf{1})" in shown["E12"]              # pass-through
    assert "?" not in "".join(shown.values())


def test_the_builder_prompt_explains_the_syntax() -> None:
    if upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    prompt = builder_prompt.build_prompt("direction-optimizing-bfs", EDGE, MD)
    for phrase in ("MacroDefinition", "ConditionalCascade", "CONSTANTS",
                   "pass_through", "- Macro TOP-DOWN("):
        assert phrase in prompt


# -------------------------------------------------------- end to end ---

def test_the_hybrid_runs_both_directions_end_to_end(tmp_path: Path) -> None:
    """A copy with the committed files only and a throwaway approval: every
    stage, then the page itself."""
    if upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    if shutil.which("node") is None:
        pytest.skip("node is not on PATH")
    # The committed inputs and model output only: nothing `check` generates.
    work = tmp_path / "direction-optimizing-bfs"
    (work / "workbench" / "spec").mkdir(parents=True)
    for name in (MD.name, "einsum.edge", "verifier.py"):
        shutil.copy(DOBFS / name, work / name)
    for name in ("build_direction_optimizing_bfs_program.py",
                 "direction_optimizing_bfs_functions.py", "authored.json"):
        shutil.copy(DOBFS / "workbench" / "spec" / name,
                    work / "workbench" / "spec" / name)
    ledger = tmp_path / "approved.json"
    env = dict(os.environ, **{LEDGER_ENV: str(ledger)})
    out = ""
    for _ in range(3):
        approve_in_tmp(work, ledger)
        r = subprocess.run(
            [sys.executable, "-m", "edge_workbench", "check", str(work)],
            cwd=ROOT, capture_output=True, text=True, timeout=600, env=env)
        out = r.stdout + r.stderr
        if r.returncode == 0:
            break
    assert r.returncode == 0, out
    assert "20 Einsums -> 20 IR nodes" in out
    assert "random instances: 12/12 agree" in out
    assert "not reached on the worked example" not in out   # both macros ran
    html = (work / "index.html").read_text()
    at = re.search(r"\bT\s*=\s*\{", html).end() - 1
    trace, _ = json.JSONDecoder().raw_decode(html[at:])
    chosen = [(s["iteration"], s["choice"]["macro"]) for s in trace["steps"]
              if s.get("choice")]
    assert chosen == [(0, "TOP-DOWN"), (1, "BOTTOM-UP"), (2, "BOTTOM-UP"),
                      (3, "BOTTOM-UP")]
    assert all(s["einsum"] == "E03" and s["graphMeaning"]
               for s in trace["steps"] if s.get("choice"))
    tb = next(s for s in trace["steps"] if s["einsum"] == "E12")
    assert tb["state"]["MF"] == {"": 2} and tb["state"]["MU"] == {"": 5}
    assert tb["state"]["TB"] == {"": True}                  # 2 > 5 / 15
    assert tb["macro"] == "TOP-DOWN" and r"\mathit{MU}" in tb["latexParts"]
