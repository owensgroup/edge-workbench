"""What a new algorithm should not be able to get silently wrong.

Each of these was found by auditing a page by hand. The checks are written
over every example, so the next algorithm gets them for free.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import spec_check, tensor_facts, verifier  # noqa: E402
from edge_workbench.render import action_prose  # noqa: E402

SPECS = sorted(p.parent for p in ROOT.glob("examples/*/workbench/spec/cascade.json"))


def _load(spec):
    program = json.loads(next(spec.glob("*_program.json")).read_text())
    return program, json.loads((spec / "cascade.json").read_text())


def _read(node, out):
    if isinstance(node, dict):
        if node.get("kind") == "input":
            out.add(node["proj"]["tensor"])
        for v in node.values():
            _read(v, out)
    elif isinstance(node, list):
        for v in node:
            _read(v, out)
    return out


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.parents[1].name)
def test_the_prose_names_every_tensor_the_einsum_reads(spec):
    """Bellman-Ford's E01 lost `D_{i,s}`: the Reduce branch described one
    operand of the Map it folds, and set-cover's E09, E11, E15 and E18 with it.
    """
    if spec_check.upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    program, cascade = _load(spec)
    prose = action_prose.describe_all(program, cascade)
    alias = cascade.get("displayNames", {})
    literals = {d["name"] for d in program["declarations"]
                if not d.get("ranks") and d.get("value") is not None}
    nodes = program["main_edge"]["cascade"]["einsums"]
    for label, idx in cascade["labels"].items():
        for k in (idx if isinstance(idx, list) else [idx]):
            for name in _read(nodes[k]["expression"], set()) - literals:
                assert alias.get(name, name) in prose[label], (label, name)


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.parents[1].name)
def test_a_stopping_condition_has_words(spec):
    program, cascade = _load(spec)
    assert action_prose.describe_all(program, cascade)["stop"]


def _bellman_ford():
    return _load(ROOT / "examples/bellman-ford/workbench/spec")[0]


def test_a_value_equal_to_empty_is_reported():
    """A weight-0 edge against `G empty = 0` is silently not an edge."""
    inst = {"extent": {"S": 2, "D": 2}, "tensors": {"G": {"0,1": 0}},
            "coordSets": {"root_id": ["0"]}}
    problems = verifier.instance_problems(inst, _bellman_ford())
    assert any("empty value" in p for p in problems)


def test_a_coordinate_set_is_required_and_bounded():
    program = _bellman_ford()
    assert tensor_facts.coord_sets(program) == {"root_id": "S"}
    bare = {"extent": {"S": 2, "D": 2}, "tensors": {"G": {"0,1": 5}}}
    assert any("root_id" in p for p in verifier.instance_problems(bare, program))
    wild = dict(bare, coordSets={"root_id": ["9"]})
    assert any("outside" in p for p in verifier.instance_problems(wild, program))


def test_a_cascade_that_never_stops_fails_rather_than_hangs():
    from edge_workbench.driver import run as driver
    if spec_check.upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    assert json.loads((ROOT / "examples/bellman-ford/workbench/spec/cascade.json")
                      .read_text())["maxGenerations"] <= 500
    spec = ROOT / "examples/bellman-ford/workbench/spec"
    inst = json.loads((spec / "instance.json").read_text())
    inst["tensors"]["G"]["1,0"] = -3
    tmp = Path(__file__).parent / "_negative_cycle.json"
    tmp.write_text(json.dumps(inst))
    try:
        with pytest.raises(driver.DriverError, match="without its stopping"):
            driver.run(spec_dir=spec, instance=tmp)
    finally:
        tmp.unlink(missing_ok=True)


@pytest.mark.parametrize("spec", SPECS, ids=lambda p: p.parents[1].name)
def test_the_prose_reads_like_an_explanation(spec):
    """Each operation is said once, with its operands, in plain words."""
    program, cascade = _load(spec)
    for label, text in action_prose.describe_all(program, cascade).items():
        for word in ("operand", "sub-expression", "step 1", "the value is",
                     "kept where"):
            assert word not in text, (label, word, text)


def test_prose_wording_on_bellman_ford():
    spec = next(p for p in SPECS if p.parents[1].name == "bellman-ford")
    program, cascade = _load(spec)
    prose = action_prose.describe_all(program, cascade)
    assert prose["E01"] == ("For each d of N, add G at (s,d) and D at s where "
                            "both exist, then keep the smallest over s.")
    assert prose["E04"] == ("For each d of D, take NewlyRelaxed at d where it "
                            "exists, otherwise keep D at d.")
    assert prose["init"] == "For each s of D in root_id, assign 0."


def test_a_generation_shows_only_when_the_reads_mix_them():
    spec = next(p for p in SPECS if p.parents[1].name == "maximum-flow")
    program, cascade = _load(spec)
    prose = action_prose.describe_all(program, cascade)
    assert "(i" not in prose["E12"]
    assert "R at (i+1,u,v)" in prose["E17"] and "Lbl at (i,u,v)" in prose["E17"]
