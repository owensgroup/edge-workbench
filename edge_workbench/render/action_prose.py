# -*- coding: utf-8 -*-
"""Describe what an Einsum DOES over its iteration space, from the IR.

Two sentences sit under each formula on the page. The first says what the
Einsum means for the problem -- "an edge is downhill when d(u) = d(v)+1" --
and only the author can write that; it comes from the tutorial.

The second says what the Einsum does mechanically: which ranks it reduces,
which merge decides where a value exists, which compute combines the operands.
That one is fully determined by the IR, and this module generates it.

It used to be hand-written, one entry per Einsum, in the algorithm's
`meta.py`. Twenty-six paragraphs of prose restating something the program
already said, with nothing checking that the restatement was right -- the same
arrangement that let the displayed FORMULA drift from the program until it was
generated too.

The wording aims to be readable and exact rather than literary. Where the IR
does not determine something, this says nothing about it instead of guessing.
"""

from __future__ import annotations

from typing import Any

# What a merge operator decides: where the result exists.
MERGE_PHRASE = {
    "intersect": "kept where both operands exist",
    "union": "kept where either operand exists",
    "take_left": "kept where the left operand exists",
    "not_left": "kept where the left operand is ABSENT",
    "take_right": "kept where the right operand exists",
    "xor": "kept where exactly one operand exists",
    "xnor": "kept where the operands agree on existence",
    "left_only": "kept where the left operand exists and the right does not",
}

# What a compute operator does with the two values.
COMPUTE_PHRASE = {
    "+": "the value is their sum",
    "-": "the value is the left minus the right",
    "*": "the value is their product",
    "/": "the value is the left divided by the right",
    "min": "the value is the smaller",
    "max": "the value is the larger",
    "take_left": "the value is the left operand's",
    "take_right": "the value is the right operand's",
    "eq": "the value is whether they are equal",
    "equals": "the value is whether they are equal",
    "ne": "the value is whether they differ",
    "not_equals": "the value is whether they differ",
    "lt": "the value is whether the left is smaller",
    "less_than": "the value is whether the left is smaller",
    "le": "the value is whether the left is no larger",
    "less_equal": "the value is whether the left is no larger",
    "gt": "the value is whether the left is larger",
    "greater_than": "the value is whether the left is larger",
    "ge": "the value is whether the left is no smaller",
    "greater_equal": "the value is whether the left is no smaller",
    "AND": "the value is their conjunction",
    "OR": "the value is their disjunction",
    "ANY": "the value is one of the contributions",
    "update": "the right operand's value where it exists, otherwise the left "
              "is carried forward",
    "identity": "the value passes through unchanged",
    "pass_through": "the value passes through unchanged",
}

UNARY_PHRASE = {"not": "negated", "floor": "rounded down"}


def _name(op: dict | None) -> str | None:
    if not op:
        return None
    return op.get("symbol") or op.get("name")


def _rank(r: dict) -> str:
    kind = r.get("kind")
    if kind == "var":
        return r["name"]
    if kind == "literal":
        return str(r["value"])
    if kind == "arith":
        return f"{_rank(r['lhs'])}{r['op']}{_rank(r['rhs'])}"
    if kind == "shape_sym":
        return f"|{r.get('name', '?')}|"
    return "?"


def _ranks(ranks: list[dict]) -> str:
    return ",".join(_rank(r) for r in ranks or [])


def _point(ranks: list[dict]) -> str:
    """`(i,u,v)` for several ranks, a bare `u` for one -- as prose reads."""
    text = _ranks(ranks)
    return f"({text})" if "," in text else text


class Describer:
    def __init__(self, program: dict, alias: dict | None = None):
        self.alias = alias or {}
        self.scalar = {
            d["name"]: d["value"]
            for d in program.get("declarations", [])
            if not d.get("ranks") and d.get("value") is not None
        }

    def tensor(self, name: str) -> str:
        return self.alias.get(name, name)

    # -- operands ---------------------------------------------------------
    def operand(self, node: dict) -> str:
        kind = node.get("kind")
        if kind == "input":
            proj = node["proj"]
            t = proj["tensor"]
            if t in self.scalar and not proj.get("ranks"):
                return str(self.scalar[t])
            sub = _point(proj.get("ranks", []))
            return f"{self.tensor(t)} at {sub}" if sub else self.tensor(t)
        if kind == "unary":
            inner = self.operand(node["operand"])
            how = UNARY_PHRASE.get(_name(node["op"]), _name(node["op"]))
            return f"{inner}, {how}"
        if kind == "occupancy":
            proj = node["operand"]
            sub = _point(proj.get("ranks", []))
            name = self.tensor(proj["tensor"])
            return (f"the number of entries in {name} at {sub}" if sub
                    else f"the number of entries in {name}")
        if kind == "anonymous":
            return f"the sub-expression over {_point(node.get('ranks', []))}"
        if kind == "binary":
            return (f"{self.operand(node['lhs'])} and "
                    f"{self.operand(node['rhs'])}")
        return "an operand"

    def _operands_of(self, node: dict, label: int) -> tuple[str, str] | None:
        """The two operands of the binary carrying `label`."""
        if node.get("kind") == "binary":
            if node.get("label") == label:
                return self.operand(node["lhs"]), self.operand(node["rhs"])
            for side in ("lhs", "rhs"):
                found = self._operands_of(node[side], label)
                if found:
                    return found
        if node.get("kind") == "anonymous":
            return self._operands_of(node["expression"], label)
        if node.get("kind") == "unary":
            return self._operands_of(node["operand"], label)
        return None

    # -- one Einsum -------------------------------------------------------
    def describe(self, einsum: dict) -> str:
        out = self.tensor(einsum["output_tensor"])
        out_ranks = _ranks(einsum.get("output_ranks", []))
        specs = einsum.get("specs", [])
        expr = einsum["expression"]

        wrappers = {s.get("label") for s in specs
                    if s.get("kind") in ("reduce", "populate")}
        maps = [s for s in specs
                if s.get("kind") == "map" and s.get("label") not in wrappers]
        reduces = [s for s in specs if s.get("kind") == "reduce"]
        populates = [s for s in specs if s.get("kind") == "populate"]

        parts: list[str] = []

        if populates:
            spec = populates[0]
            starred = ",".join(spec.get("rank_list") or [])
            fiber = [r for r in einsum.get("output_ranks", [])
                     if _rank(r) not in (spec.get("rank_list") or [])]
            coord = _name(spec.get("coord_op")) or "?"
            return (f"For each {_point(fiber)} fiber of {out}, the "
                    f"coordinate operator `{coord}` keeps one {starred} and "
                    f"deletes the rest.")

        if reduces:
            spec = reduces[0]
            over = ",".join(spec.get("rank_list") or [])
            operand = self.operand(expr if expr.get("kind") != "binary"
                                   or expr.get("label") not in wrappers
                                   else expr["lhs"])
            phrase = COMPUTE_PHRASE.get(_name(spec.get("compute_op")), "")
            merge = MERGE_PHRASE.get(_name(spec.get("merge_op")), "")
            line = (f"Reduce over rank {over}: for each "
                    f"{_point(einsum.get('output_ranks', []))} of {out}, "
                    f"combine {operand} over every {over}")
            if phrase:
                line += f", where {phrase}"
            if merge:
                line += f"; the result is {merge}"
            return line + "."

        if maps:
            clauses: list[str] = []
            for spec in maps:
                pair = self._operands_of(expr, spec.get("label"))
                merge = MERGE_PHRASE.get(_name(spec.get("merge_op")), "")
                phrase = COMPUTE_PHRASE.get(_name(spec.get("compute_op")), "")
                lead = f"step {spec['label']}, " if len(maps) > 1 else ""
                bits = []
                if pair:
                    bits.append(f"{lead}take {pair[0]} and {pair[1]}")
                bits += [b for b in (merge, phrase) if b]
                clauses.append("; ".join(bits))
            body = ". ".join(c[0].upper() + c[1:] for c in clauses)
            return (f"For each point "
                    f"{_point(einsum.get('output_ranks', []))} of {out}: "
                    f"{body[0].lower() + body[1:]}.")

        # A bare projection or unary with no spec: an assignment.
        return (f"For each point {_point(einsum.get('output_ranks', []))} "
                f"of {out}: assign {self.operand(expr)}.")

    def describe_group(self, einsums: list[dict]) -> str:
        """Several IR nodes the author wrote as one Einsum."""
        if len(einsums) == 1:
            return self.describe(einsums[0])
        body = " ".join(
            f"({i + 1}) {self.describe(e)}" for i, e in enumerate(einsums)
        )
        written = {e["output_tensor"] for e in einsums}
        if len(written) == 1:
            out = self.tensor(einsums[0]["output_tensor"])
            head = (f"{len(einsums)} arms write {out} in order, each "
                    f"overwriting the last where it produces a value.")
        else:
            names = ", ".join(sorted(self.tensor(w) for w in written))
            head = (f"{len(einsums)} Einsums, run in order, setting "
                    f"{names}.")
        return f"{head} {body}"


def describe_all(program: dict, cascade: dict,
                 alias: dict | None = None) -> dict[str, str]:
    """label -> what that Einsum does over its iteration space."""
    d = Describer(program, alias or cascade.get("displayNames", {}))
    nodes = program["main_edge"]["cascade"]["einsums"]
    out: dict[str, str] = {}
    for label, idx in (cascade.get("labels") or {}).items():
        idxs = idx if isinstance(idx, list) else [idx]
        out[label] = d.describe_group([nodes[i] for i in idxs])

    init = program.get("initialization", {}).get("einsums", [])
    if init:
        out[cascade.get("initLabel", "init")] = d.describe_group(init)
    return out
