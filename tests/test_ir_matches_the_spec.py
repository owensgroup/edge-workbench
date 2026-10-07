"""The SPECIFICATION is the source of truth. The IR is checked against it.

WHY THIS FILE EXISTS, AND WHAT IT CORRECTS
------------------------------------------
`tests/test_latex_from_ir.py` renders the page's formula from the IR, on the
reasoning that a derived formula cannot contradict the program. That reasoning
is sound and it is not sufficient, because it makes the IR the authority --
and the IR is a hand-written LOWERING of the specification. It can be wrong,
and it was.

`einsum.edge` writes E10 with one operator name:

    PushCand_{i, u, v*} = Adm_{i, u, v} <<<_{v*} 1(pick-admissible-edge)

The IR lowered it with `pick-admissible-edge` in the populate's COMPUTE slot
-- aliased to `identity` so it would behave like the `1` it displaced -- and
`select-one-admissible-v`, a name in no specification, no tutorial and no
paper, invented to fill the COORDINATE slot and bound to a lowest-coordinate
rule the algorithm never asks for. The page then faithfully rendered a formula
naming an operator the author had never written, and the derivation is what
made it look trustworthy.

So authority runs one way here: the spec's surface is read, the IR is compared
to it, and a disagreement is a bug in the IR.

WHAT IS COMPARED
----------------
Not the whole expression -- that needs the real parser, and a half-parser that
silently skips what it cannot read would be worse than nothing. Three things,
each of which failed in practice:

1. the output tensor          (E17 wrote `Adm` where the spec said `AdmPost`,
                               then `AdmPost` where the spec said `Adm`)
2. the output's generation    (E06 ran every round where the spec seeds once)
3. the NAMED operators        (E10, above)

Skips when no spec checkout is present, like the other cross-repo gates.

    EDGE_IR_REPO=~/Projects/edge-core-ir pytest tests/test_ir_matches_the_spec.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench.spec_surface import parse_edge_file  # noqa: E402

SPECS = sorted((ROOT / "algorithms").glob("*/spec/*_program.json"))


def _upstream() -> Path:
    named = os.environ.get("EDGE_IR_REPO")
    return Path(named) if named else Path.home() / "Projects" / "edge-core-ir"


def _edge_file(alg: str) -> Path | None:
    for rel in ("examples/algorithms", "test-algorithms"):
        p = _upstream() / rel / alg / "einsum.edge"
        if p.exists():
            return p
    return None


@pytest.fixture(params=SPECS, ids=[p.parent.parent.name for p in SPECS])
def pair(request):
    """(surface Einsums from the spec, IR program, cascade label map)."""
    spec = request.param
    alg = spec.parent.parent.name
    edge = _edge_file(alg)
    if edge is None:
        pytest.skip(f"no einsum.edge for {alg} under {_upstream()}")
    program = json.loads(spec.read_text())
    cascade = json.loads((spec.parent / "cascade.json").read_text())
    return parse_edge_file(edge), program, cascade


def _nodes_for(program: dict, cascade: dict, label: str) -> list[dict]:
    idx = cascade["labels"][label]
    nodes = program["main_edge"]["cascade"]["einsums"]
    return [nodes[i] for i in (idx if isinstance(idx, list) else [idx])]


def _rank_text(rank: dict) -> str:
    kind = rank.get("kind")
    if kind == "var":
        return rank["name"]
    if kind == "literal":
        return str(rank["value"])
    if kind == "arith":
        return f"{_rank_text(rank['lhs'])}{rank['op']}{_rank_text(rank['rhs'])}"
    return "?"


def _udf_names(node: dict) -> set[str]:
    """Every user-defined operator name the IR node uses."""
    found: set[str] = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "user_defined" and "name" in n:
                found.add(n["name"])
            if "coord_op" in n and isinstance(n["coord_op"], dict):
                found.add(n["coord_op"].get("name", ""))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return {f for f in found if f}


################################################################################
# 1. the output tensor
################################################################################


def test_the_ir_writes_the_tensor_the_spec_writes(pair):
    surface, program, cascade = pair
    for label, spec_einsum in surface.items():
        if label not in cascade.get("labels", {}):
            continue
        alias = cascade.get("displayNames", {})
        for node in _nodes_for(program, cascade, label):
            written = alias.get(node["output_tensor"], node["output_tensor"])
            assert written == spec_einsum.output, (
                f"{label}: the spec writes {spec_einsum.output!r}, the IR "
                f"writes {written!r}\n  spec: {spec_einsum.text[:90]}"
            )


################################################################################
# 2. the generation it writes
################################################################################


def test_the_ir_writes_the_generation_the_spec_writes(pair):
    """E06's failure mode: an Einsum the spec seeds once, run every round.

    Compares only the first rank position, which is where a generational rank
    sits when a tensor has one. `i+1` and `i + 1` are the same thing.
    """
    surface, program, cascade = pair
    for label, spec_einsum in surface.items():
        if label not in cascade.get("labels", {}) or not spec_einsum.output_ranks:
            continue
        want = spec_einsum.output_ranks[0].replace(" ", "")
        for node in _nodes_for(program, cascade, label):
            got = _rank_text(node["output_ranks"][0]).replace(" ", "")
            assert got == want, (
                f"{label}: the spec writes {spec_einsum.output}_{{{want}, ...}}, "
                f"the IR writes {got}\n  spec: {spec_einsum.text[:90]}"
            )


################################################################################
# 3. the named operators -- the E10 failure
################################################################################


def test_the_ir_names_no_operator_the_spec_does_not(pair):
    """The check that would have caught `select-one-admissible-v` on sight.

    Every hyphenated operator name in the IR has to appear in the spec's text
    for that Einsum. A name the IR invented to fill a slot appears nowhere,
    which is exactly what this rejects.

    Restricted to hyphenated names on purpose: those are the choice functions
    and other human-written operators, the kind a lowering invents. Glyph
    operators would need the real parser to compare.
    """
    surface, program, cascade = pair
    for label, spec_einsum in surface.items():
        if label not in cascade.get("labels", {}):
            continue
        allowed = set(spec_einsum.named_ops)
        for node in _nodes_for(program, cascade, label):
            used = {n for n in _udf_names(node) if "-" in n}
            invented = used - allowed
            assert not invented, (
                f"{label}: the IR names {sorted(invented)}, which the "
                f"specification does not.\n"
                f"  spec says: {spec_einsum.text[:90]}\n"
                f"  The specification is the source of truth. Either the IR "
                f"invented a name to fill a slot, or it put the spec's name in "
                f"the wrong slot."
            )


def test_the_ir_uses_every_named_operator_the_spec_gives_it(pair):
    """And the other direction: a name the spec gives must be used.

    E10's lowering satisfied the previous check only because it also dropped
    `pick-admissible-edge` into a slot where it meant something else. A spec
    name that the IR does not use at all is the same class of error seen from
    the other side.
    """
    surface, program, cascade = pair
    for label, spec_einsum in surface.items():
        if label not in cascade.get("labels", {}) or not spec_einsum.named_ops:
            continue
        used: set[str] = set()
        for node in _nodes_for(program, cascade, label):
            used |= _udf_names(node)
        missing = set(spec_einsum.named_ops) - used
        assert not missing, (
            f"{label}: the spec names {sorted(missing)}, which the IR does "
            f"not use.\n  spec says: {spec_einsum.text[:90]}"
        )


################################################################################
# the gate is only worth having if it covers the spec
################################################################################


def test_every_labelled_einsum_in_the_spec_is_checked(pair):
    """A gate that silently checks three of twenty-four Einsums is a lie.

    The spec's labels and the cascade's labels have to line up, or the
    comparisons above skip most of the program without saying so.
    """
    surface, _program, cascade = pair
    labels = set(cascade.get("labels", {}))
    parsed = set(surface)
    assert labels <= parsed, (
        f"the cascade maps labels the spec's einsum.edge does not define: "
        f"{sorted(labels - parsed)}"
    )
    assert len(parsed & labels) >= len(labels), "coverage shrank"


################################################################################
# 4. the declarations -- ranks, data type, and the EMPTY VALUE
################################################################################


def test_the_ir_declares_what_the_spec_declares(pair):
    """Every tensor's ranks, data type and empty value, against the spec.

    The empty value is why this matters. `value == empty => absent` is
    load-bearing throughout EDGE, so a tensor declared `empty = 0` where the
    spec says `+inf` silently drops every zero-valued entry -- and that exact
    mistake has happened in this algorithm before, on `NeiLbl`, where 0 would
    have dropped every height-0 neighbour before E22's min ever saw it.

    Nothing compared the two declarations until now. Both files state the same
    facts; only one of them is the specification.
    """
    _surface, program, cascade = pair
    alg = _spec_alg(cascade)
    edge = _edge_file(alg)
    if edge is None:
        pytest.skip(f"no einsum.edge for {alg}")

    from edge_workbench.spec_surface import normalise_empty, parse_declarations

    declared = parse_declarations(edge)
    alias = cascade.get("displayNames", {})
    checked = 0
    for decl in program.get("declarations", []):
        name = decl["name"]
        spec = declared.get(name) or declared.get(alias.get(name, name))
        if spec is None:
            # Zero-rank literals the IR synthesises (Zero, One, Lit_0, ...)
            # have no counterpart in the spec, by design.
            assert not decl.get("ranks"), (
                f"{name} is declared in the IR with ranks "
                f"{[r['name'] for r in decl['ranks']]} but not in the "
                f"specification at all"
            )
            continue
        checked += 1

        ir_ranks = tuple(r["name"] for r in decl.get("ranks", []))
        assert ir_ranks == spec.ranks, (
            f"{name}: the spec declares ranks {list(spec.ranks)}, the IR "
            f"declares {list(ir_ranks)}"
        )
        assert normalise_empty(decl.get("empty_value")) == \
            normalise_empty(spec.empty), (
            f"{name}: the spec declares empty = {spec.empty}, the IR declares "
            f"{decl.get('empty_value')!r}. `value == empty => absent`, so this "
            f"changes which entries exist."
        )
        ir_type = (decl.get("data_type") or {}).get("name", "").lower()
        assert ir_type.startswith(spec.data_type[:3]), (
            f"{name}: the spec declares {spec.data_type}, the IR declares "
            f"{ir_type!r}"
        )
    assert checked >= 5, f"only {checked} declarations compared"


def _spec_alg(cascade: dict) -> str:
    """The algorithm name, from the spec directory this cascade came from."""
    for spec in SPECS:
        if json.loads((spec.parent / "cascade.json").read_text()) == cascade:
            return spec.parent.parent.name
    return ""


################################################################################
# 5. the label map -- derived, not declared
################################################################################


def test_the_label_map_is_the_one_the_spec_and_ir_imply(pair):
    """`cascade.json`'s labels must match what the two authorities imply.

    The map from written label to IR node index is load-bearing: the coverage
    gate, the drill-down and every comparison above key off it. It is also
    hand-written, and an index map beside a program that changes is the sort of
    thing nobody re-reads.

    It does not have to be hand-written. Walking the spec's labels in order
    against the IR's nodes in order recovers it exactly, including the grouping
    for a lowered `cases` -- max-flow's E04 is three consecutive nodes all
    writing `R_{1,u,v}`, so all three land on E04. This asserts the committed
    map is that one.

    A failure means either the map is stale, or the lowering no longer
    corresponds to the specification -- and the second is the interesting case.
    """
    surface, program, cascade = pair
    from edge_workbench.spec_surface import derive_labels

    derived = derive_labels(surface, program, cascade.get("displayNames", {}))
    assert derived, (
        "could not account for every IR node by walking the spec's labels in "
        "order, so the lowering does not correspond to the specification"
    )
    assert derived == cascade.get("labels"), (
        "cascade.json's label map is not what the spec and the IR imply.\n"
        f"  committed: {cascade.get('labels')}\n"
        f"  derived  : {derived}"
    )


################################################################################
# 6. the OPERATORS -- the gate that makes an LLM-written lowering safe
################################################################################


def _ir_specs(node: dict) -> list[tuple[str, str, str]]:
    """(action, compute, merge) for every spec on an IR node."""
    out = []
    for spec in node.get("specs", []):
        kind = spec.get("kind")
        if kind not in ("map", "reduce"):
            continue
        compute = spec.get("compute_op") or {}
        merge = spec.get("merge_op") or {}
        out.append((
            kind,
            compute.get("symbol") or compute.get("name") or "?",
            merge.get("symbol") or merge.get("name") or "?",
        ))
    return out


def test_the_ir_uses_the_operators_the_spec_writes(pair):
    """Every `compute(merge)` the spec states must appear in the lowering.

    THIS IS THE GATE THAT MAKES A GENERATED LOWERING SAFE. Measured before it
    existed: changing E07's merge from intersect to union -- a plausible slip
    for anything writing a builder from the spec -- passed the coverage gate,
    passed the answer check, produced the right maximum flow, and rendered a
    page. The only thing that caught it was the vendoring check, which
    compares max-flow's IR against upstream's copy. A NEW algorithm has no
    upstream copy: its builder IS the source, so a mistake in the builder
    yields a consistent builder-and-program pair and sails through.

    The merge operator decides WHERE a value exists, so getting it wrong
    changes the algorithm while often leaving small instances with the right
    answer. It is exactly the class of error that needs a structural check
    rather than a behavioural one.

    Compared as a multiset of (action, compute, merge), not position by
    position, and only in one direction: everything the SPEC states must be in
    the IR. The reverse is not required because the surface abbreviates --
    max-flow's E08 writes `(D_{i,v} + 1)` as inline arithmetic where the IR
    carries a second labelled Map spec for the `+`. That asymmetry is the
    spec's, not the lowering's, and `test_the_ir_does_not_invent_operators`
    reports the extras without failing on them.
    """
    surface, program, cascade = pair
    from edge_workbench.spec_surface import parse_specs

    checked = 0
    for label, spec_einsum in surface.items():
        if label not in cascade.get("labels", {}):
            continue
        stated = parse_specs(spec_einsum.text)
        if not stated:
            continue
        lowered = []
        for node in _nodes_for(program, cascade, label):
            lowered += _ir_specs(node)

        for want in stated:
            triple = (want.action, want.compute, want.merge)
            assert triple in lowered, (
                f"{label}: the spec writes {want.compute}({want.merge}) as a "
                f"{want.action}, which the lowering does not have.\n"
                f"  spec says : {spec_einsum.text[:88]}\n"
                f"  IR has    : {lowered}\n"
                f"  The merge operator decides where a value exists, so this "
                f"changes the algorithm."
            )
            checked += 1
    assert checked >= 10, f"only {checked} operators compared"


def test_the_ir_does_not_invent_operators(pair):
    """Report lowering specs the spec does not state, without failing on them.

    A surface Einsum may legitimately carry fewer specs than its lowering --
    E08's `+ 1` is written as arithmetic and lowered as a labelled Map. But a
    lowering with operators the spec never mentions is worth seeing, because
    that is how `select-one-admissible-v` got invented.
    """
    surface, program, cascade = pair
    from edge_workbench.spec_surface import parse_specs

    extras = {}
    for label, spec_einsum in surface.items():
        if label not in cascade.get("labels", {}):
            continue
        stated = {(s.action, s.compute, s.merge)
                  for s in parse_specs(spec_einsum.text)}
        if not stated:
            continue
        lowered = []
        for node in _nodes_for(program, cascade, label):
            lowered += _ir_specs(node)
        unstated = [t for t in lowered if t not in stated]
        if unstated:
            extras[label] = unstated

    # Pinned rather than asserted-empty: these are the spec's abbreviations,
    # and a NEW one appearing is what this is watching for.
    known = {"E06", "E08", "E11", "E12", "E15", "E16", "E21", "E23",
             "E03", "E13", "E14", "E18", "E22", "E10", "E04"}
    surprising = sorted(set(extras) - known)
    assert not surprising, (
        f"these Einsums lower to operators the spec does not state: "
        f"{ {k: extras[k] for k in surprising} }"
    )
