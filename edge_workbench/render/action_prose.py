# -*- coding: utf-8 -*-
"""Describe what an Einsum DOES over its iteration space, from the IR.

Two sentences sit under each formula on the page. The first says what the
Einsum means for the problem -- "an edge is downhill when d(u) = d(v)+1" --
and only the author can write that; it comes from the tutorial.

The second says what the Einsum does mechanically: which ranks it reduces,
which merge decides where a value exists, which compute combines the operands.
An author's `Einsum meaning:` line takes that place when there is one. For
every other Einsum the IR determines the sentence, and this module generates it.

It used to be hand-written, one entry per Einsum, in the algorithm's
`meta.py`. Twenty-six paragraphs of prose restating something the program
already said, with nothing checking that the restatement was right -- the same
arrangement that let the displayed FORMULA drift from the program until it was
generated too.

The wording aims to read like a person explaining the step: name the operation
and its operands together ("add F at (u,v) and delta at (u,v), then subtract
delta at (v,u)"), mention a merge only when it changes the result, and leave the
generation out of a coordinate unless the operands read different generations.
The formula sits directly above and carries the rest. Where the IR does not
determine something, this says nothing about it instead of guessing.
"""

from __future__ import annotations

from edge_workbench.cascade_shape import flat_nodes, stopping_conditions  # noqa: F401

from typing import Any

THAT = "that"          # the value of the step just described

# What a Map does, with its two operands in place. `update` and the
# take-one-side operators read as a sentence of their own; the merge is spoken
# only by `_where`.
COMPUTE_PHRASE = {
    "+": "add {a} and {b}",
    "-": "take {a} and subtract {b}",
    "*": "multiply {a} by {b}",
    "/": "divide {a} by {b}",
    "min": "take the smaller of {a} and {b}",
    "max": "take the larger of {a} and {b}",
    "eq": "check whether {a} equals {b}",
    "equals": "check whether {a} equals {b}",
    "ne": "check whether {a} differs from {b}",
    "not_equals": "check whether {a} differs from {b}",
    "lt": "check whether {a} is less than {b}",
    "less_than": "check whether {a} is less than {b}",
    "le": "check whether {a} is at most {b}",
    "less_equal": "check whether {a} is at most {b}",
    "gt": "check whether {a} is greater than {b}",
    "greater_than": "check whether {a} is greater than {b}",
    "ge": "check whether {a} is at least {b}",
    "greater_equal": "check whether {a} is at least {b}",
    "OR": "take {a} or {b}",
    "update": "take {b} where it exists, otherwise keep {a}",
}

# The same, when the right operand is a constant: "add 1 to D at v".
LITERAL_PHRASE = {
    "+": "add {b} to {a}",
    "-": "subtract {b} from {a}",
}

# The same, when the step just described is the operand being updated.
AFTER_PHRASE = {
    "+": "add {b}",
    "-": "subtract {b}",
    "*": "multiply by {b}",
    "/": "divide by {b}",
}

# Where a merge narrows the result. Arithmetic over a union needs no mention:
# a missing value simply counts as empty.
WHERE_PHRASE = {
    "intersect": " where both exist",
    "union": " where either exists",
    "xor": " where exactly one exists",
    "xnor": " where both or neither exist",
    "not_left": " where {a} is absent",
    "left_only": " where {a} exists and {b} does not",
    "take_right": " where {b} exists",
}
QUIET_UNION = {"+", "-", "*", "/", "min", "max", "OR", "update"}

# How a Reduce folds a fiber: "for each v, sum delta at (u,v) over every u".
REDUCE_PHRASE = {
    "+": ("sum {x} over every {r}", "sum over {r}"),
    "*": ("multiply {x} over every {r}", "multiply over {r}"),
    "min": ("take the smallest {x} over every {r}", "keep the smallest over {r}"),
    "max": ("take the largest {x} over every {r}", "keep the largest over {r}"),
    "OR": ("OR {x} over every {r}", "OR over {r}"),
    "AND": ("AND {x} over every {r}", "AND over {r}"),
    "ANY": ("take any one {x} over every {r}", "keep any one over {r}"),
}

UNARY_SYMBOL = {"not": "¬"}
UNARY_STEP = {"not": "negate {x}", "floor": "round {x} down"}


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
        return f"|{str(r.get('name', '?')).strip('|')}|"
    return "?"


def _ranks(ranks: list[dict]) -> str:
    return ",".join(_rank(r) for r in ranks or [])


def _point(ranks: list[dict]) -> str:
    """`(i,u,v)` for several ranks, a bare `u` for one -- as prose reads."""
    text = _ranks(ranks)
    return f"({text})" if "," in text else text


def _exists(name: str) -> str:
    """`F at r exists`, or `is absent` for a negated operand: ¬F holds there."""
    return (f"{name[1:]} is absent" if name.startswith("¬")
            else f"{name} exists")


def _both(a: str, b: str) -> str:
    if a.startswith("¬") and b.startswith("¬"):
        return f"where {a[1:]} and {b[1:]} are both absent"
    if a.startswith("¬") or b.startswith("¬"):
        return f"where {_exists(a)} and {_exists(b)}"
    return f"where both {a} and {b} exist"


class Describer:
    def __init__(self, program: dict, alias: dict | None = None,
                 generational: str = "I"):
        self.alias = alias or {}
        self.scalar = {
            d["name"]: d["value"]
            for d in program.get("declarations", [])
            if not d.get("ranks") and d.get("value") is not None
        }
        # Which coordinate of each tensor is the generation.
        self.generation = {
            d["name"]: [r["name"] for r in d["ranks"]].index(generational)
            for d in program.get("declarations", [])
            if generational in [r["name"] for r in d.get("ranks") or []]
        }
        self.keep_generation = False

    def tensor(self, name: str) -> str:
        return self.alias.get(name, name)

    def _at(self, proj: dict) -> str:
        """Where a tensor is read, without the generation unless it matters."""
        ranks = proj.get("ranks", [])
        at = self.generation.get(proj["tensor"])
        if at is not None and at < len(ranks) and not self.keep_generation:
            ranks = ranks[:at] + ranks[at + 1:]
        return _point(ranks)

    def _output_point(self, einsum: dict) -> str:
        ranks = einsum.get("output_ranks", [])
        at = self.generation.get(einsum["output_tensor"])
        if at is not None and at < len(ranks):
            ranks = ranks[:at] + ranks[at + 1:]
        return _point(ranks)

    def _read_generations(self, node: Any, out: set[str]) -> set[str]:
        """The generations this expression reads, as written."""
        if isinstance(node, dict):
            proj = node.get("proj") if node.get("kind") == "input" else None
            if proj:
                at = self.generation.get(proj["tensor"])
                if at is not None and at < len(proj.get("ranks", [])):
                    out.add(_rank(proj["ranks"][at]))
            for value in node.values():
                self._read_generations(value, out)
        elif isinstance(node, list):
            for value in node:
                self._read_generations(value, out)
        return out

    # -- operands ---------------------------------------------------------
    def _is_atom(self, node: dict) -> bool:
        """An operand that can be named, as opposed to a step to describe."""
        kind = node.get("kind")
        if kind == "anonymous":
            return self._is_atom(node["expression"])
        if kind == "unary":
            return (_name(node["op"]) in UNARY_SYMBOL
                    and self._is_atom(node["operand"]))
        return kind != "binary"

    def operand(self, node: dict) -> str:
        kind = node.get("kind")
        if kind == "input":
            proj = node["proj"]
            t = proj["tensor"]
            if t in self.scalar and not proj.get("ranks"):
                return str(self.scalar[t])
            sub = self._at(proj)
            return f"{self.tensor(t)} at {sub}" if sub else self.tensor(t)
        if kind == "unary":
            return (UNARY_SYMBOL.get(_name(node["op"]), "")
                    + self.operand(node["operand"]))
        if kind == "occupancy":
            proj = node["operand"]
            sub = self._at(proj)
            name = self.tensor(proj["tensor"])
            return (f"the number of entries in {name} at {sub}" if sub
                    else f"the number of entries in {name}")
        if kind == "rank_value":
            return _rank(node["expr"])
        if kind == "anonymous":
            return self.operand(node["expression"])
        return "an operand"

    def _is_literal(self, node: dict) -> bool:
        """A scalar constant: the `1` or `0` a lowering adds, never written."""
        proj = node.get("proj") or {}
        return (node.get("kind") == "input" and proj.get("tensor") in self.scalar
                and not proj.get("ranks"))

    # -- steps ------------------------------------------------------------
    def _where(self, merge: str | None, compute: str | None,
               a: str, b: str) -> str:
        """The merge, when it changes the result."""
        if merge in (None, "take_left") or (merge == "union"
                                            and compute in QUIET_UNION):
            return ""
        return WHERE_PHRASE.get(merge, "").format(a=a, b=b)

    def _always_there(self, node: dict) -> bool:
        """A constant or a coordinate: it cannot be what removes a point."""
        return self._is_literal(node) or node.get("kind") == "rank_value"

    def _map(self, spec: dict, a: str, b: str, literal: bool = False) -> str:
        """One Map, its operands already in words."""
        compute, merge = _name(spec.get("compute_op")), _name(spec.get("merge_op"))
        if literal and merge == "intersect":
            merge = None
        if compute in ("identity", "pass_through"):
            return f"take {a}"
        if compute in UNARY_STEP:
            return UNARY_STEP[compute].format(x=a)
        if compute == "take_left":
            line = f"take {a}" if a != THAT else "keep that"
            if merge == "intersect":
                return f"{line} where {_exists(b)}"
            return line + self._where(merge, compute, a, b)
        if compute == "take_right":
            line = f"take {b}" if b != THAT else "keep that"
            if merge == "intersect":
                return f"{line} where {_exists(a)}"
            return line + self._where(merge, compute, a, b)
        if compute == "AND" and merge == "intersect":
            return f"keep it {_both(a, b)}"
        table = (LITERAL_PHRASE if literal and a != THAT else
                 AFTER_PHRASE if a == THAT else COMPUTE_PHRASE)
        phrase = table.get(compute) or COMPUTE_PHRASE.get(compute)
        if phrase is None:
            return f"combine {a} and {b} with `{compute}`"
        where = self._where(merge, compute, a, b)
        if where and phrase.startswith("check"):
            where = "," + where
        return phrase.format(a=a, b=b) + where

    def _steps(self, node: dict, spec_of: dict, reduce_of: dict) -> list[str]:
        """An expression as the steps a reader would do, innermost first."""
        kind = node.get("kind")
        if kind == "anonymous":
            return self._steps(node["expression"], spec_of, reduce_of)
        if kind == "unary":
            steps = self._steps(node["operand"], spec_of, reduce_of)
            how = UNARY_STEP.get(_name(node["op"]),
                                 f"apply {_name(node['op'])} to {{x}}")
            return steps + [how.format(x=THAT)]
        if kind != "binary":
            return [f"take {self.operand(node)}"]

        lhs, rhs = node["lhs"], node["rhs"]
        spec = spec_of.get(node.get("label"), {})
        left_atom, right_atom = self._is_atom(lhs), self._is_atom(rhs)
        if left_atom and right_atom:
            steps = [self._map(spec, self.operand(lhs), self.operand(rhs),
                               self._always_there(lhs)
                               or self._always_there(rhs))]
        elif right_atom:
            steps = (self._steps(lhs, spec_of, reduce_of)
                     + [self._map(spec, THAT, self.operand(rhs),
                                  self._always_there(rhs))])
        elif left_atom:
            steps = self._steps(rhs, spec_of, reduce_of)
            step = self._map(spec, self.operand(lhs), THAT)
            if steps[-1].startswith("check"):
                step = step.replace("where that exists", "where that holds")
            steps.append(step)
        else:
            first = self._steps(lhs, spec_of, reduce_of)
            second = self._steps(rhs, spec_of, reduce_of)
            steps = first + [f"separately, {second[0]}"] + second[1:] + [
                self._map(spec, "the first result", "the second")]

        reduce = reduce_of.get(node.get("label"))
        if reduce:
            over = ",".join(reduce.get("rank_list") or [])
            _, fold = REDUCE_PHRASE.get(
                _name(reduce.get("compute_op")),
                ("", f"combine over {over} with "
                     f"`{_name(reduce.get('compute_op'))}`"))
            steps.append(fold.format(r=over))
        return steps

    def _body(self, einsum: dict) -> str:
        """What is done at each point, with no leading capital or full stop."""
        specs = einsum.get("specs", [])
        expr = einsum["expression"]
        spec_of = {s.get("label"): s for s in specs if s.get("kind") == "map"}
        reduce_of = {s.get("label"): s for s in specs if s.get("kind") == "reduce"}
        if expr.get("kind") != "binary" and not self._is_atom(expr):
            return ", then ".join(self._steps(expr, spec_of, reduce_of))
        if self._is_atom(expr):
            return f"assign {self.operand(expr)}"
        return ", then ".join(self._steps(expr, spec_of, reduce_of))

    def _bare_reduce(self, einsum: dict) -> str | None:
        """A Reduce with no Map of its own to speak of: "sum F over every u"."""
        reduces = [s for s in einsum.get("specs", []) if s.get("kind") == "reduce"]
        if not reduces:
            return None
        spec = reduces[0]
        expr = einsum["expression"]
        node = expr
        while node.get("kind") == "anonymous":
            node = node["expression"]
        folded = next((m for m in einsum.get("specs", [])
                       if m.get("kind") == "map"
                       and m.get("label") == spec.get("label")), None)
        if folded and not (node.get("kind") == "binary"
                           and node.get("label") == spec.get("label")
                           and self._is_literal(node["rhs"])):
            return None
        target = node["lhs"] if folded else node
        if not self._is_atom(target):
            return None
        operand = self.operand(target)
        if folded and _name(folded.get("compute_op")) == "floor":
            operand += ", rounded down"
        over = ",".join(spec.get("rank_list") or [])
        whole, _ = REDUCE_PHRASE.get(
            _name(spec.get("compute_op")),
            (f"combine {{x}} over every {{r}} with "
             f"`{_name(spec.get('compute_op'))}`", ""))
        return whole.format(x=operand, r=over)

    def _restricted(self, einsum: dict) -> str:
        """` in root_id` or ` with j ≥ 1`, when the output is limited."""
        text = ""
        for p in einsum.get("predicates", []):
            if p.get("kind") == "set_membership":
                name = (p.get("coord_set") or {}).get("name", "?")
                text += (f" not in {name}" if p.get("negated")
                         else f" in {name}")
            else:
                text += f" with {self._condition(p)}"
        return text

    _OP = {"==": "=", "!=": "≠", ">=": "≥", "<=": "≤", ">": ">", "<": "<"}

    def _condition(self, p: dict | None) -> str:
        """A predicate over rank variables, as written: `n = j+1`."""
        if not p:
            return ""
        kind = p.get("kind")
        if kind == "comparison":
            return (f"{_rank(p['lhs'])} {self._OP.get(p['op'], p['op'])} "
                    f"{_rank(p['rhs'])}")
        if kind in ("and", "or"):
            return f" {kind} ".join(self._condition(q)
                                    for q in p.get("operands", []))
        if kind == "not":
            return f"not ({self._condition(p.get('operand'))})"
        if kind == "set_membership":
            name = (p.get("coord_set") or {}).get("name", "?")
            return (f"{_rank(p['member'])} "
                    f"{'not in' if p.get('negated') else 'in'} {name}")
        return "?"

    def _cases(self, einsum: dict) -> str:
        """One clause per arm, in order: the first arm that holds wins."""
        parts = []
        for arm in einsum["expression"].get("arms", []):
            cond = self._condition(arm.get("where")) or "otherwise"
            if arm.get("when"):
                cond = (cond + " and when " if arm.get("where") else "when ") \
                    + "its condition holds"
            if arm.get("expression") is None:
                parts.append(f"nothing (empty) {('if ' + cond) if cond != 'otherwise' else 'otherwise'}")
                continue
            sub = {"output_tensor": einsum["output_tensor"],
                   "output_ranks": einsum.get("output_ranks", []),
                   "expression": arm["expression"],
                   "specs": arm.get("specs", [])}
            body = self._bare_reduce(sub) or self._body(sub)
            parts.append(f"{body} {('if ' + cond) if cond != 'otherwise' else 'otherwise'}")
        return "by cases, the first that holds: " + "; ".join(parts)

    # -- the stopping condition -------------------------------------------
    def _stop_value(self, node: dict) -> str:
        kind = node.get("kind")
        if kind == "property_app":
            proj = node["operands"][0]
            return f"{self.tensor(proj['tensor'])} at {_ranks(proj['ranks'])}"
        if kind == "tensor_projection" or "proj" in node:
            proj = node["proj"]
            if proj["tensor"] in self.scalar and not proj.get("ranks"):
                return str(self.scalar[proj["tensor"]])
            sub = _ranks(proj.get("ranks", []))
            return f"{self.tensor(proj['tensor'])} at {sub}" if sub \
                else self.tensor(proj["tensor"])
        return "?"

    def stopping(self, cond: dict) -> str:
        """In words, what ends the cascade. Empty if the form is not known."""
        p = cond.get("predicate", {})
        if p.get("kind") != "comparison":
            return ""
        lhs, rhs, op = p["lhs"], p["rhs"], p.get("op")
        left, right = self._stop_value(lhs), self._stop_value(rhs)
        if lhs.get("kind") == "property_app" and op == "==" and right == "0":
            return f"The cascade stops when {left} has no entries left."
        if op == "==":
            return (f"The cascade stops when {left} equals {right} at every "
                    f"point: the last generation changed nothing.")
        return f"The cascade stops when {left} {op} {right}."

    # -- one Einsum -------------------------------------------------------
    def describe(self, einsum: dict, head: bool = True) -> str:
        expr = einsum["expression"]
        self.keep_generation = len(self._read_generations(expr, set())) > 1
        point = self._output_point(einsum)
        limit = self._restricted(einsum)
        out = self.tensor(einsum["output_tensor"])
        specs = einsum.get("specs", [])

        if expr.get("kind") == "cases":
            body = self._cases(einsum)
            if not head:
                return body
            return (f"For each {point} of {out}{limit}, {body}." if point
                    else f"{body[0].upper() + body[1:]}.")

        populates = [s for s in specs if s.get("kind") == "populate"]
        if populates:
            spec = populates[0]
            starred = ",".join(spec.get("rank_list") or [])
            fiber = [r for r in einsum.get("output_ranks", [])
                     if _rank(r) not in (spec.get("rank_list") or [])]
            at = self.generation.get(einsum["output_tensor"])
            if at is not None and at < len(einsum.get("output_ranks", [])):
                fiber = [r for r in fiber
                         if r is not einsum["output_ranks"][at]]
            coord = _name(spec.get("coord_op")) or "?"
            source = self.operand(expr["lhs"] if expr.get("kind") == "binary"
                                  else expr)
            each = f", for each {_point(fiber)}" if fiber else ""
            return (f"From {source}{each}, `{coord}` keeps one {starred} and "
                    f"drops the rest; what is left is {out}.")

        bare = self._bare_reduce(einsum)
        body = bare or self._body(einsum)
        if not head:
            return body
        if not point:
            return f"{body[0].upper() + body[1:]}."
        return (f"For each {point}{limit}, {body}." if bare
                else f"For each {point} of {out}{limit}, {body}.")

    def describe_group(self, einsums: list[dict]) -> str:
        """Several IR nodes the author wrote as one Einsum."""
        if len(einsums) == 1:
            return self.describe(einsums[0])
        written = list(dict.fromkeys(e["output_tensor"] for e in einsums))
        if len(written) == 1:
            first = einsums[0]
            point = self._output_point(first)
            arms = "; ".join(f"({i + 1}) {self.describe(e, head=False)}"
                             for i, e in enumerate(einsums))
            return (f"For each {point} of {self.tensor(written[0])}, "
                    f"{len(einsums)} cases run in order, each overriding the "
                    f"last where it has a value: {arms}.")
        names = [self.tensor(w) for w in written]
        listed = (", ".join(names[:-1]) + f" and {names[-1]}")
        body = " ".join(f"({i + 1}) {self.describe(e)}"
                        for i, e in enumerate(einsums))
        return f"Sets {listed}, in order. {body}"


def describe_all(program: dict, cascade: dict,
                 alias: dict | None = None) -> dict[str, str]:
    """label -> what that Einsum does over its iteration space."""
    d = Describer(program, alias or cascade.get("displayNames", {}),
                  cascade.get("generationalRank", "I"))
    nodes = flat_nodes(program)
    out: dict[str, str] = {}
    for label, idx in (cascade.get("labels") or {}).items():
        idxs = idx if isinstance(idx, list) else [idx]
        out[label] = d.describe_group([nodes[i] for i in idxs])

    init = program.get("initialization", {}).get("einsums", [])
    if init:
        out[cascade.get("initLabel", "init")] = d.describe_group(init)
    conds = stopping_conditions(program)
    if conds:
        out[cascade.get("stopLabel", "stop")] = d.stopping(conds[0])
    return out
