"""A Populate with a mutable rank is recorded round by round.

A round (paper, Inset 4) is one point of the iteration space at which
Populate runs. edge-core-ir's evaluator records each one (local patch, issue
11) and the driver passes it through as `step["populate"]`; nothing in this
repo works a round out. These tests read the recording on every example and
check it against the paper's constraint, W ∩ (dom(S) ∪ D) = ∅, and against
the tensors the driver snapshots around the Einsum.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import spec_check, verifier  # noqa: E402
from edge_workbench.cascade_shape import flat_nodes  # noqa: E402
from edge_workbench.driver import run as driver  # noqa: E402

SPECS = sorted(p.parent for p in ROOT.glob("examples/*/workbench/spec/cascade.json"))


def _populates(spec: Path) -> bool:
    program = json.loads(next(spec.glob("*_program.json")).read_text())
    return any(s.get("kind") == "populate" and s.get("rank_list")
               for node in flat_nodes(program) for s in node.get("specs", []))


WITH_POPULATE = [s for s in SPECS if _populates(s)]
name = lambda p: p.parents[1].name  # noqa: E731


def _run(spec: Path, seed=None) -> list[dict]:
    if spec_check.upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    steps = driver.run(spec_dir=spec, seed=seed)["steps"]
    found = [s for s in steps if s.get("populate")]
    if not found:
        pytest.skip("this edge-core-ir does not record Populate rounds")
    return steps


def test_some_example_has_a_populate() -> None:
    if not SPECS:
        pytest.skip("no example built yet")
    assert WITH_POPULATE


@pytest.mark.parametrize("spec", WITH_POPULATE, ids=name)
def test_every_populate_that_wrote_recorded_its_rounds(spec) -> None:
    for step in _run(spec):
        specs = (step.get("exec") or {}).get("einsum", {}).get("specs", [])
        starred = any(s.get("kind") == "populate" and s.get("rank_list")
                      for s in specs)
        if starred and step["exec"]["result"]:
            assert step.get("populate"), step["einsum"]
        if not starred:
            assert "populate" not in step, step["einsum"]


@pytest.mark.parametrize("spec", WITH_POPULATE, ids=name)
def test_every_round_obeys_inset_4(spec) -> None:
    for step in _run(spec):
        p = step.get("populate")
        if not p:
            continue
        for k, r in enumerate(p["rounds"]):
            at = f"{step['einsum']} i={step['iteration']} round {k + 1}"
            writes, deletes, dom = set(r["W"]), set(r["D"]), set(r["pre"])
            loc = set(p["fibers"][r["fiber"]]["loc"])
            assert r["checked"], at
            assert not writes & (dom | deletes), at       # the constraint
            assert deletes <= dom, at                      # only what is there
            assert writes | deletes | dom <= loc, at       # one fiber only
            assert set(r["post"]) == (dom - deletes) | writes, at
            assert all(r["post"][c] == v for c, v in r["W"].items()), at
            assert all(r["post"][c] == r["pre"][c] for c in dom - deletes), at
            assert {c for c, a in r["writeDel"] if a == "Write"} == writes, at
            assert {c for c, a in r["writeDel"] if a == "Delete"} == deletes, at
            assert r["writeDelSize"] >= len(r["writeDel"]), at


@pytest.mark.parametrize("spec", WITH_POPULATE, ids=name)
def test_the_rounds_chain_and_end_at_the_recorded_output(spec) -> None:
    """Round k+1 on a fiber starts from what round k left, and the last
    round of each fiber is what the driver's own snapshot of the output
    holds after the Einsum."""
    for step in _run(spec):
        p = step.get("populate")
        if not p:
            continue
        final = step["state"][step["output"]]
        for fiber, f in p["fibers"].items():
            rounds = [p["rounds"][k] for k in f["rounds"]]
            assert all(r["fiber"] == fiber for r in rounds)
            for before, after in zip(rounds, rounds[1:]):
                assert after["pre"] == before["post"], (step["einsum"], fiber)
            held = {c: v for c, v in final.items() if c in set(f["loc"])}
            assert held == rounds[-1]["post"], (step["einsum"], fiber)
        assert sorted(k for f in p["fibers"].values() for k in f["rounds"]) \
            == list(range(len(p["rounds"])))


@pytest.mark.parametrize("spec", WITH_POPULATE, ids=name)
def test_a_free_choice_is_marked_free_and_decided_by_the_schedule(spec) -> None:
    cascade = json.loads((spec / "cascade.json").read_text())
    free = set(verifier.free_choices(cascade))
    sequential = _run(spec)
    for step in sequential:
        p = step.get("populate")
        if p:
            assert p["free"] == (p["operator"] in free), step["einsum"]
            assert p["schedule"] == {"kind": "sequential"}
            # The sequential schedule offers coordinates in sorted order.
            # (Within a fiber: the keys drop the generation.)
            for f in p["fibers"].values():
                offered = [tuple(int(x) for x in p["rounds"][k]["coord"].split(","))
                           for k in f["rounds"]]
                assert offered == sorted(offered)
    if not free:
        return
    for seed in range(3):
        for step in _run(spec, seed=seed):
            p = step.get("populate")
            if not p or not p["free"]:
                continue
            assert p["schedule"] == {"kind": "shuffled", "seed": seed}
            for f in p["fibers"].values():
                first, *rest = (p["rounds"][k] for k in f["rounds"])
                if first["pre"]:
                    continue        # the fiber already held something
                # select-any: the first arrival is written, nothing after.
                assert list(first["W"]) == [first["coord"]]
                assert all(not r["W"] and not r["D"] for r in rest)


def test_a_ranking_operator_deletes_what_it_outranks() -> None:
    """Set-cover's `select-max-val`: a later, larger candidate deletes the
    one held and is written in the same round -- at a different location."""
    spec = ROOT / "examples/set-cover/workbench/spec"
    if spec not in WITH_POPULATE:
        pytest.skip("set-cover is not built")
    rounds = [r for step in _run(spec) if step.get("populate")
              and step["populate"]["operator"] == "select-max-val"
              for r in step["populate"]["rounds"] if r["D"]]
    assert rounds
    for r in rounds:
        (gone,), (kept,) = r["D"], list(r["W"])
        assert r["value"] > r["pre"][gone] and kept == r["coord"] != gone
