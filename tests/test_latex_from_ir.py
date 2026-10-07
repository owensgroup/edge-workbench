"""The formula on the page must come from the program, and must not lie.

WHAT WENT WRONG BEFORE
----------------------
The formula above each step was a hand-transcribed string in the algorithm's
`meta.py`. Nothing compared it to the IR, and it was wrong in four places
that had been on the page for as long as anyone had been reading it:

  E17   showed `Adm` for an Einsum whose output tensor is `AdmPost`, and E18
        showed itself reading `Adm`. Both were stale from the change that
        introduced `AdmPost` as a tensor of its own -- a change the spec has
        since adopted, because the two hold different quantities.
  E10   wrote `1(pick-admissible-edge)`, naming the COMPUTE operator in the
        position that holds the choice. The operator that actually decides
        which coordinate survives is the coordinate op,
        `select-one-admissible-v` -- the name `cascade.json` maps, and the
        one the reader needs.
  E08   collapsed `D_{i,v} .^2 1 :: +(cap)` into a plain `+ 1`, hiding one
        of the Einsum's two labelled Map specs.
  init  claimed to assign `S` and `T`. Initialization does no such thing;
        they are inputs.

None of these changed a result, which is exactly why they survived: the
cascade was right and only the description of it was wrong. A tool whose
purpose is to show a reader what a specification does had four places where
it showed them something else.

Rendering from the IR removes the category. These tests hold that line.

ONE THING THESE TESTS DO NOT ESTABLISH
--------------------------------------
That the formula is RIGHT. They establish that it agrees with the IR, and the
IR is a hand-written lowering of the specification that can itself be wrong --
E10 was. `tests/test_ir_matches_the_spec.py` is the pass that checks the IR
against `einsum.edge`, and that is where authority lives: the spec is the
source of truth, and a disagreement means the IR is wrong.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(ROOT))

from edge_workbench.render import latex  # noqa: E402

SPECS = sorted((ROOT / "algorithms").glob("*/spec"))


def _load(spec: Path):
    prog = json.loads(next(spec.glob("*_program.json")).read_text())
    casc = json.loads((spec / "cascade.json").read_text())
    return prog, casc


@pytest.fixture(params=SPECS, ids=[p.parent.name for p in SPECS])
def spec(request):
    # An algorithm mid-authoring has a spec directory and a prepared artifact
    # before it has a program -- that is the order the workflow runs in. These
    # tests are about the program, so there is nothing yet to be right or
    # wrong about, and failing would only teach an author that starting work
    # breaks the suite.
    if not any(request.param.glob("*_program.json")):
        pytest.skip(f"{request.param.parent.name} has no program yet")
    return request.param


def test_every_written_einsum_gets_a_formula(spec):
    prog, casc = _load(spec)
    out = latex.render_all(prog, casc)
    missing = [k for k in casc.get("labels", {}) if not out.get(k)]
    assert not missing, f"no formula rendered for {missing}"


def test_the_formula_names_the_tensor_the_program_writes(spec):
    """The E17 failure, as a property rather than a special case.

    Whatever the formula says is being computed has to be what the IR node's
    `output_tensor` says, modulo the display alias. This is the single check
    that would have caught `Adm` standing in for `AdmPost`.
    """
    prog, casc = _load(spec)
    alias = casc.get("displayNames", {})
    nodes = prog["main_edge"]["cascade"]["einsums"]
    out = latex.render_all(prog, casc)

    for label, idx in casc.get("labels", {}).items():
        for i in idx if isinstance(idx, list) else [idx]:
            written = alias.get(nodes[i]["output_tensor"],
                                nodes[i]["output_tensor"])
            rendered = latex.tensor(written)
            assert rendered in out[label], (
                f"{label} writes {written!r}, but its formula does not name "
                f"it:\n  {out[label]}"
            )


def test_the_formula_names_the_coordinate_operator_of_a_populate(spec):
    """The E10 failure. The coordinate op is the one that chooses, so it is
    the one the reader has to see; naming only the compute op describes the
    action backwards."""
    prog, casc = _load(spec)
    nodes = prog["main_edge"]["cascade"]["einsums"]
    out = latex.render_all(prog, casc)

    checked = 0
    for label, idx in casc.get("labels", {}).items():
        for i in idx if isinstance(idx, list) else [idx]:
            for s in nodes[i].get("specs", []):
                if s.get("kind") != "populate":
                    continue
                coord = (s.get("coord_op") or {}).get("name")
                assert coord and coord.replace("_", r"\_") in out[label], (
                    f"{label} is a populate whose coordinate op is {coord!r}, "
                    f"which its formula does not name:\n  {out[label]}"
                )
                checked += 1
    if not checked:
        pytest.skip("no populate in this algorithm")


def test_every_labelled_map_spec_appears(spec):
    """The E08 failure: a spec that runs but is not shown.

    A Map spec carries a compute and a merge operator and a label tying it to
    one binary. Dropping one from the formula makes the Einsum look simpler
    than it is.
    """
    prog, casc = _load(spec)
    nodes = prog["main_edge"]["cascade"]["einsums"]
    out = latex.render_all(prog, casc)

    for label, idx in casc.get("labels", {}).items():
        for i in idx if isinstance(idx, list) else [idx]:
            specs = nodes[i].get("specs", [])
            wrappers = latex.Renderer._wrapper_label(specs)
            shown = [s for s in specs
                     if s.get("kind") == "map" and s["label"] not in wrappers]
            if len(shown) < 2:
                continue
            for s in shown:
                assert rf"\bigwedge\nolimits^{s['label']}" in out[label], (
                    f"{label} has {len(shown)} Map specs; spec "
                    f"{s['label']} is not shown:\n  {out[label]}"
                )


def test_changing_the_program_changes_the_formula(spec):
    """The anti-lie property, stated directly.

    A formula derived from the program must move when the program moves. If
    this ever fails, the rendering has drifted back to being a description
    that happens to sit near the IR rather than one produced from it.
    """
    prog, casc = _load(spec)
    before = latex.render_all(prog, casc)

    label, idx = next(iter(casc["labels"].items()))
    i = idx[0] if isinstance(idx, list) else idx
    mutated = copy.deepcopy(prog)
    mutated["main_edge"]["cascade"]["einsums"][i]["output_tensor"] = "Zzz"
    mutated["declarations"].append(
        {"name": "Zzz", "ranks": [], "data_type": {"name": "int"},
         "empty_value": 0}
    )

    after = latex.render_all(mutated, casc)
    assert after[label] != before[label], (
        f"{label}'s formula did not change when its output tensor did"
    )
    assert "Zzz" in after[label]


def test_the_generation_comes_from_the_ir_not_from_the_prose(spec):
    """`outGen` drives the before/after toggle and used to be regexed out of
    the hand-written formula -- a caption feature depending on the
    punctuation of a string. Every label must resolve to a generation the
    page understands, or to None deliberately."""
    prog, casc = _load(spec)
    gens = latex.generations(prog, casc)
    assert set(gens) == set(casc.get("labels", {}))
    for label, g in gens.items():
        assert g is None or g == "i" or g == "i+1" or g.isdigit(), (
            f"{label} resolved to an unusable generation {g!r}"
        )


################################################################################
# what a SECOND algorithm found
################################################################################


def test_a_real_map_and_reduce_keeps_both_operands(spec):
    """A matrix-vector product must not render as though it read the matrix.

    The IR cannot hang a Reduce on a lone tensor, so a pure reduction is
    written `X op identityScalar` purely to give the spec a label. The
    renderer elides that operand, correctly -- its Map spec is
    `take_left(take_left)`, the identity in both value and presence.

    It used to elide EVERY binary carrying a Reduce. On max-flow that was
    invisible, because all of its reductions are that placeholder shape. Exact
    cover has four that are not:

        CovCol_{i+1,c} = A_{r,c} . SelRow_{i+1,r} :: /\\ <-(^) \\/ ANY(u)

    and those rendered as `CovCol = A :: \\/ ANY(u)` -- SelRow gone. Not a
    smaller claim than the tutorial's, a different one.

    So the test is: any binary whose Map is NOT the transparent
    take_left(take_left) must have both its operands in the formula.
    """
    prog, casc = _load(spec)
    rendered = latex.render_all(prog, casc)
    nodes = prog["main_edge"]["cascade"]["einsums"]

    checked = 0
    for label, idx in (casc.get("labels") or {}).items():
        for i in (idx if isinstance(idx, list) else [idx]):
            expr = nodes[i]["expression"]
            if expr.get("kind") != "binary":
                continue
            specs = nodes[i].get("specs", [])
            reduced = {s.get("label") for s in specs
                       if s.get("kind") in ("reduce", "populate")}
            if expr.get("label") not in reduced:
                continue
            maps = [s for s in specs if s.get("kind") == "map"
                    and s.get("label") == expr.get("label")]
            transparent = maps and all(
                latex._op_name(m.get("compute_op", {})) == "take_left"
                and latex._op_name(m.get("merge_op", {})) == "take_left"
                for m in maps
            )
            if transparent:
                continue
            rhs = expr["rhs"]
            name = (rhs.get("proj", {}).get("tensor")
                    if rhs.get("kind") == "input" else None)
            if not name:
                continue
            checked += 1
            assert latex.tensor(name) in rendered[label], (
                f"{label} combines two operands under a real Map spec, but "
                f"{name} is missing from its formula:\n  {rendered[label]}"
            )
    if not checked:
        pytest.skip("no genuine map+reduce binaries in this cascade")


def test_a_coordinate_read_as_a_value_renders_as_that_coordinate(spec):
    """EDGE's "rank variables as tensors" must not render as `?`.

    Exact cover's depth stamp, sigma(d, r) = d*|R| + r, is the first cascade
    here to put a coordinate in value position. The renderer had a case for
    it that had never run, guessed the IR's field name, and so printed
    `\\text{?}` where the `r` belongs -- in a formula whose whole job is to
    be the tutorial's line.
    """
    prog, casc = _load(spec)
    rendered = latex.render_all(prog, casc)
    nodes = prog["main_edge"]["cascade"]["einsums"]

    def uses_rank_value(n) -> bool:
        if isinstance(n, dict):
            return (n.get("kind") == "rank_value"
                    or any(uses_rank_value(v) for v in n.values()))
        return isinstance(n, list) and any(uses_rank_value(v) for v in n)

    checked = 0
    for label, idx in (casc.get("labels") or {}).items():
        for i in (idx if isinstance(idx, list) else [idx]):
            if not uses_rank_value(nodes[i]["expression"]):
                continue
            checked += 1
            assert r"\text{?}" not in rendered[label], (
                f"{label} reads a coordinate as a value and rendered a "
                f"placeholder:\n  {rendered[label]}"
            )
    if not checked:
        pytest.skip("no coordinate-as-value operands in this cascade")
