# -*- coding: utf-8 -*-
"""Facts about an algorithm's tensors, read off the IR rather than restated.

Three things the page needs about each tensor, all of which the program already
determines, and all of which used to be hand-listed in the algorithm's
`meta.py`:

    rank_names    which ranks a tensor is drawn over, ignoring the
                  generational one -- so a grid knows its axes
    generational  does it carry a generational rank at all
    stateful      is it LOOP-CARRIED: does a round read what the previous
                  round wrote

`stateful` is the interesting one, and it is the reason this is a module rather
than a one-liner. The obvious rule -- "written at i+1 and read at a plain i" --
over-collects badly: on max-flow it returns thirteen tensors where five are
carried. `Lbl` is written at `i` and read at `i` within the same round, so
reading it at a plain `i` says nothing about state. The rule needs all three
clauses:

    advanced at i+1   AND   read at a plain i   AND   NOT rewritten at plain i

With the third clause max-flow comes out as exactly `{Act, D, E, F, R}`, which
is what the hand-written list said. Without it, the before/after toggle would
offer a previous generation for tensors that do not have one.
"""

from __future__ import annotations

import json as _json
import re

from typing import Any


def _projections(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("kind") == "input" and "proj" in node:
            out.append(node["proj"])
        if node.get("kind") == "occupancy" and "operand" in node:
            out.append(node["operand"])
        for value in node.values():
            _projections(value, out)
    elif isinstance(node, list):
        for value in node:
            _projections(value, out)


def _declared(program: dict) -> dict[str, list[str]]:
    return {
        d["name"]: [r["name"] for r in d.get("ranks", []) or []]
        for d in program.get("declarations", [])
    }


def rank_names(program: dict, gen_rank: str = "I",
               alias: dict | None = None) -> dict[str, list[str]]:
    """tensor -> the ranks it is drawn over, generational rank dropped.

    The generational rank is not an axis of the picture: a grid shows one
    generation at a time, and which one is the transport's business.
    """
    alias = alias or {}
    out = {}
    for name, ranks in _declared(program).items():
        axes = [r for r in ranks if r != gen_rank]
        if axes:
            out[alias.get(name, name)] = axes
    return out


def generational(program: dict, gen_rank: str = "I",
                 alias: dict | None = None) -> set[str]:
    """Tensors declared over the generational rank."""
    alias = alias or {}
    return {
        alias.get(name, name)
        for name, ranks in _declared(program).items()
        if gen_rank in ranks
    }


def stateful(program: dict, gen_rank: str = "I",
             alias: dict | None = None) -> set[str]:
    """Tensors a round reads from the round before -- the loop-carried state.

    All three clauses are needed; see the module docstring for what happens
    without the third.
    """
    alias = alias or {}
    declared = _declared(program)
    einsums = program["main_edge"]["cascade"]["einsums"]

    advanced: set[str] = set()      # written at i+1
    at_current: set[str] = set()    # written at a plain i
    read_current: set[str] = set()  # read at a plain i

    for einsum in einsums:
        ranks = einsum.get("output_ranks") or []
        first = ranks[0] if ranks else {}
        if first.get("kind") == "arith":
            advanced.add(einsum["output_tensor"])
        elif first.get("kind") == "var":
            at_current.add(einsum["output_tensor"])

        projections: list[dict] = []
        _projections(einsum["expression"], projections)
        for proj in projections:
            tensor = proj["tensor"]
            if gen_rank not in declared.get(tensor, []):
                continue
            first_read = (proj.get("ranks") or [{}])[0]
            if first_read.get("kind") == "var":
                read_current.add(tensor)

    carried = {
        t for t in advanced
        if t in read_current and t not in at_current
    }
    return {alias.get(t, t) for t in carried}


def all_facts(program: dict, cascade: dict | None = None) -> dict:
    """Everything above, in one call, with the cascade's aliases applied."""
    cascade = cascade or {}
    gen = cascade.get("generationalRank", "I")
    alias = cascade.get("displayNames", {})
    return {
        "rankNames": rank_names(program, gen, alias),
        "generational": generational(program, gen, alias),
        "stateful": stateful(program, gen, alias),
    }


def rank_sides(program: dict, gen_rank: str = "I",
               alias: dict | None = None) -> dict[str, tuple[str, ...]]:
    """tensor -> the ranks it is indexed by, generational rank dropped.

    The same information `rank_names` returns, kept separate because it
    answers a different question. `rank_names` is asked "what are this grid's
    axes"; this is asked "which side of the picture does this tensor
    decorate".

    In a graph over one vertex rank those questions collapse -- everything
    rank-1 decorates the one node set. They come apart as soon as a spec has
    TWO node ranks: exact cover's `SelRow` is over `R` and `CovCol` is over
    `C`, and a renderer that treats both as "the nodes" will put a column
    marking on a row.
    """
    return {k: tuple(v) for k, v in rank_names(program, gen_rank, alias).items()}


def node_ranks(program: dict, gen_rank: str = "I") -> list[str]:
    """The ranks that behave like node sets, in declaration order.

    A rank is a node set when some tensor is indexed by it. Ranks are returned
    in the order they first appear, so a two-rank algorithm gets a stable
    left/right assignment rather than one that depends on dict ordering.
    """
    seen: list[str] = []
    for ranks in _declared(program).values():
        for rank in ranks:
            if rank != gen_rank and rank not in seen:
                seen.append(rank)
    return seen


def extents_of(instance: dict) -> dict[str, int]:
    """rank -> how many coordinates the instance gives it."""
    return dict(instance.get("extent", {}))


def inputs(program: dict, gen_rank: str = "I") -> list[str]:
    """Tensors the program READS but never writes: what a host must supply.

    A tensor written by no Einsum and no initialization has no source inside
    the program, so its values arrive from outside. That is the host contract,
    and it is decidable from the IR alone.

    WHY THIS IS WORTH DERIVING. It is the one list a tutorial can get wrong
    without any reader noticing, because an input that is missing from the
    prose still works for whoever wrote the cascade -- they know what it
    holds. Exact cover reads `Col` and `Row`, writes neither, and declares
    neither; they are the rank universes, and nothing in the tutorial says so.
    Max-flow's inputs are G, C, S, T and |V|, and its prose lists all of them.

    Zero-rank tensors carrying a literal `value` are excluded: `One` is a
    constant the artifact already contains, not something a host provides.
    """
    decls = {d["name"]: d for d in program.get("declarations", [])}
    written = set()
    for einsum in (program.get("initialization", {}).get("einsums", [])
                   + program["main_edge"]["cascade"]["einsums"]):
        written.add(einsum["output_tensor"])

    read: list[dict] = []
    _projections(program["main_edge"]["cascade"]["einsums"], read)
    _projections(program.get("initialization", {}).get("einsums", []), read)

    out = set()
    for proj in read:
        name = proj["tensor"]
        if name in written:
            continue
        decl = decls.get(name, {})
        if not decl.get("ranks") and decl.get("value") is not None:
            continue                      # a literal, not host data
        out.add(name)
    return sorted(out)


def _all_read(program: dict) -> set[str]:
    """Every tensor the program reads, STOPPING CONDITIONS INCLUDED.

    The stopping predicate is not in the einsum tree, and forgetting it makes
    a declared-but-unread check report `Lit_0` -- the literal 0 that the
    predicate compares occupancy against, read on every single iteration. A
    check whose first finding is wrong is a check nobody runs twice.
    """
    read: list[dict] = []
    _projections(program["main_edge"]["cascade"]["einsums"], read)
    _projections(program.get("initialization", {}).get("einsums", []), read)
    names = {p["tensor"] for p in read}
    for stop in program["main_edge"]["cascade"].get("stopping_conditions", []):
        stop_projs: list[dict] = []
        _projections(stop, stop_projs)
        names |= {p["tensor"] for p in stop_projs}
        # Stopping predicates carry projections under `proj` keys that are not
        # wrapped in an `input` node, so _projections does not see them.
        for m in re.finditer(r'"tensor":\s*"([A-Za-z_][A-Za-z0-9_]*)"',
                             _json.dumps(stop)):
            names.add(m.group(1))
    return names


def unused(program: dict) -> list[str]:
    """Tensors that are declared and then never read by anything.

    Dead weight, and it propagates: max-flow declares `G`, the graph's
    adjacency, and no Einsum reads it. The declaration still reached the IR,
    the instance file, and the random-instance generator in the verifier,
    which faithfully builds a G for every generated graph that nothing will
    look at. The tutorial declares it too, so this is inherited rather than
    introduced.
    """
    declared = {d["name"] for d in program.get("declarations", [])}
    written = {e["output_tensor"] for e
               in (program.get("initialization", {}).get("einsums", [])
                   + program["main_edge"]["cascade"]["einsums"])}
    return sorted(declared - _all_read(program) - written)
