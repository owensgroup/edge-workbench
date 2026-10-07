# -*- coding: utf-8 -*-
"""Render an IR Einsum as the paper's notation.

WHY THIS EXISTS
---------------
The formula shown above each step used to be a hand-transcribed string in the
algorithm's `meta.py`. Nothing checked it against the program, and it was
demonstrably free to lie: swapping E03's entry for one with a different
reduced rank, a different compute operator and a different merge operator
built cleanly, passed both gates and all page checks, and rendered on the
page.

That is the worst possible failure for a tool whose purpose is to show a
reader what a specification does. Every other claim the page makes is now
derived from the program; the formula -- the most load-bearing text on the
screen -- was the exception.

Deriving it removes the possibility. The formula cannot disagree with the
program because it is produced from the program, and a change to the IR moves
the rendering with it.

THAT IS NOT THE SAME AS BEING RIGHT
-----------------------------------
This renders the IR faithfully, and the IR is a hand-written LOWERING of the
specification. When the lowering is wrong, this renders the mistake just as
faithfully: E10's populate had the spec's one operator name in the compute
slot and an invented name -- `select-one-admissible-v`, in no specification --
in the coordinate slot, and the page displayed it. The derivation is what
makes such a formula look trustworthy.

So `einsum.edge` is the source of truth, not the IR, and
`tests/test_ir_matches_the_spec.py` checks the IR against it.

WHAT IS NOT RECOVERABLE
-----------------------
One thing genuinely cannot be derived, and it is worth stating rather than
papering over. A written `cases` lowers to several IR nodes whose conditions
are encoded STRUCTURALLY -- max-flow's E04 becomes three Einsums writing the
same slice in order, each overwriting the last, with "u = s" expressed as an
intersection against the one-hot S rather than as a predicate. The
`predicates` list on those nodes is empty. So `\\begin{cases}` is a human
summary of something the IR does not contain, and this module renders the
arms instead: what actually executes, in the order it executes.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------- glyphs ---
# The paper's notation. An unknown name falls back to \text{name} rather than
# being dropped -- a formula with an unfamiliar operator spelled out is
# honest; one with the operator silently missing is not.

MERGE = {
    "intersect": r"\cap",
    "union": r"\cup",
    "take_left": r"\leftarrow",
    "not_left": r"\nleftarrow",
    "take_right": r"\rightarrow",
    "xor": r"\oplus",
    "xnor": r"\equiv",
    "left_only": r"\setminus",
}

COMPUTE = {
    "+": "+", "-": "-", "*": "*", "/": "/",
    "take_left": r"\leftarrow",
    "take_right": r"\rightarrow",
    "min": r"\min", "max": r"\max",
    "eq": r"\equiv", "ne": r"\neq",
    "lt": "<", "le": r"\leq", "gt": ">", "ge": r"\geq",
    "equals": r"\equiv", "not_equals": r"\neq",
    "less_than": "<", "less_equal": r"\leq",
    "greater_than": ">", "greater_equal": r"\geq",
    "AND": r"\text{AND}", "OR": r"\text{OR}", "ANY": r"\text{ANY}",
    "update": r"\mathbin{<\!\!<}",
    "floor": r"\lfloor\;\rfloor",
    # The paper's 1 glyph. `identity` / `pass_through` are its ASCII names in
    # the registry; printing the word would make a populate read as though it
    # named a function where the notation shows a glyph.
    "identity": r"\mathbf{1}",
    "pass_through": r"\mathbf{1}",
}

UNARY = {"not": r"\neg", "floor": None}   # None => wraps, handled below

GREEK = {"delta", "alpha", "beta", "gamma", "sigma", "lambda", "mu", "tau",
         "phi", "psi", "omega", "theta", "rho", "epsilon"}


def _sub(s: str) -> str:
    """`_u` for a single token, `_{i,u,v}` otherwise -- as the paper sets it."""
    return f"_{s}" if len(s) == 1 else f"_{{{s}}}"


def _esc(name: str) -> str:
    return name.replace("_", r"\_")


def _op_name(op: dict | None) -> str | None:
    if not op:
        return None
    return op.get("symbol") or op.get("name")


def _glyph(table: dict, name: str | None) -> str:
    if name is None:
        return ""
    if name in table and table[name] is not None:
        return table[name]
    return r"\text{" + name.replace("_", r"\_") + "}"


def tensor(name: str) -> str:
    """A tensor name as the paper sets it.

    Single letters stay upright, multi-letter names are italicised as a unit
    so `FS` does not read as F times S, and a Greek name becomes the letter.
    """
    if name in GREEK:
        return "\\" + name
    low = name.lower()
    if low in GREEK:
        return "\\" + low
    if len(name) == 1:
        return name
    return r"\mathit{" + name + "}"


class Renderer:
    """Renders against one program, which it needs for two things.

    Declarations tell it which rank position of a tensor is the generational
    one (so a literal there reads `i \\equiv 1` rather than a bare `1`), and
    which zero-rank tensors are scalar literals (so `Zero` reads `0`).
    """

    def __init__(self, program: dict, cascade: dict | None = None,
                 alias: dict | None = None):
        cascade = cascade or {}
        self.alias = alias or cascade.get("displayNames", {})
        self.gen_rank = cascade.get("generationalRank", "I")
        self.gen_var = self.gen_rank.lower()

        self.ranks_of: dict[str, list[str]] = {}
        self.scalar: dict[str, Any] = {}
        for d in program.get("declarations", []):
            self.ranks_of[d["name"]] = [r["name"] for r in d.get("ranks", [])]
            if not d.get("ranks") and d.get("value") is not None:
                self.scalar[d["name"]] = d["value"]

    # -- names ------------------------------------------------------------
    def name(self, t: str) -> str:
        return tensor(self.alias.get(t, t))

    # -- rank expressions --------------------------------------------------
    def rank(self, r: dict, generational: bool = False) -> str:
        kind = r.get("kind")
        if kind == "var":
            return r["name"]
        if kind == "literal":
            v = r["value"]
            # A literal in the generational position is a specific generation,
            # and the paper writes that as a binding of the rank variable.
            return rf"{self.gen_var}\equiv {v}" if generational else str(v)
        if kind == "arith":
            return f"{self.rank(r['lhs'])}{r['op']}{self.rank(r['rhs'])}"
        if kind == "shape_sym":
            return r"\lvert " + str(r.get("name", "?")) + r"\rvert"
        if kind == "rank_value":
            # EDGE's "rank variables as tensors": a coordinate read as a
            # value. The IR field is `expr`; `rank` and `value` are read too
            # because this case was written before anything used it, guessed
            # the field name, and rendered `?` the first time a cascade did --
            # exact cover's stamp, sigma(d, r) = d*|R| + r.
            inner = r.get("expr") or r.get("rank") or r.get("value")
            return self.rank(inner) if isinstance(inner, dict) else str(inner)
        return r"\text{?}"

    def subscript(self, t: str, ranks: list[dict]) -> str:
        """`F_{i \\equiv 1,u,v}` -- with the generational position marked."""
        declared = self.ranks_of.get(t, [])
        parts = []
        for pos, r in enumerate(ranks):
            gen = pos < len(declared) and declared[pos] == self.gen_rank
            parts.append(self.rank(r, generational=gen))
        return ",".join(parts)

    def projection(self, proj: dict) -> str:
        t = proj["tensor"]
        if t in self.scalar and not proj.get("ranks"):
            return self.value(self.scalar[t])
        sub = self.subscript(t, proj.get("ranks", []))
        return self.name(t) + (_sub(sub) if sub else "")

    @staticmethod
    def value(v: Any) -> str:
        """A scalar declaration's value, as the paper would set it.

        Infinity arrives as the STRING "inf" rather than a float, because the
        IR is JSON and JSON has no infinity. Rendering it as `inf` would be a
        small lie in a formula, which is the one thing this module exists to
        prevent.
        """
        if v is True:
            return r"\text{true}"
        if v is False:
            return r"\text{false}"
        if isinstance(v, str) and v.lower() in ("inf", "infinity", "+inf"):
            return r"\infty"
        if isinstance(v, str) and v.lower() in ("-inf", "-infinity"):
            return r"-\infty"
        if isinstance(v, float) and v == float("inf"):
            return r"\infty"
        if isinstance(v, float) and v == float("-inf"):
            return r"-\infty"
        return str(v)

    # -- expressions -------------------------------------------------------
    @staticmethod
    def _wrapper_label(specs: list[dict]) -> set:
        """Labels whose binary is a placeholder, not a real combine.

        The IR has no way to hang a Reduce or a Populate on a lone tensor, so
        a pure reduction is written `X op identityScalar` purely to give the
        spec a label to attach to. `edge_interp.js` treats exactly this case
        as a wrapper -- it returns the left operand untouched -- and the
        rendering has to agree, or the page would show an operand the
        evaluator ignores.

        Eliding it is exact rather than cosmetic: the accompanying Map spec is
        `take_left(take_left)`, which is the identity on the left operand in
        both value and presence.

        AND THAT MAP SPEC IS THE TEST, not the presence of a Reduce. This used
        to return every label carrying a reduce or a populate, which was
        indistinguishable on max-flow -- every one of its reductions is the
        `unary_reduce` placeholder shape. Exact cover has four reductions that
        are genuine binaries:

            CovCol_{i+1,c} = A_{r,c} . SelRow_{i+1,r} :: /\\ <-(^) \\/ ANY(u)

        a matrix-vector product whose Map combines two real operands and whose
        Reduce then contracts r. Treating that as a wrapper dropped `SelRow`
        from the formula -- rendering a matrix-vector product as though it
        read the matrix alone, which is not a smaller claim but a different
        one.
        """
        labelled = {s.get("label") for s in specs
                    if s.get("kind") in ("reduce", "populate")}
        transparent = {
            s.get("label") for s in specs
            if s.get("kind") == "map"
            and _op_name(s.get("compute_op", {})) == "take_left"
            and _op_name(s.get("merge_op", {})) == "take_left"
        }
        return labelled & transparent

    def _infix_labels(self, expr: Any, specs: list[dict]) -> dict:
        """label -> comparison glyph, for binaries comparing an occupancy."""
        comparisons = {"eq": r"\equiv", "equals": r"\equiv", "ne": r"\neq",
                       "lt": "<", "le": r"\le", "gt": ">", "ge": r"\ge"}
        by_label = {s.get("label"): s for s in specs if s.get("kind") == "map"}
        out = {}

        def walk(n):
            if isinstance(n, dict):
                if n.get("kind") == "binary" and "occupancy" in (
                        n["lhs"].get("kind"), n["rhs"].get("kind")):
                    name = _op_name((by_label.get(n.get("label")) or {})
                                    .get("compute_op") or {})
                    if name in comparisons:
                        out[n["label"]] = comparisons[name]
                for v in n.values():
                    walk(v)
            elif isinstance(n, list):
                for v in n:
                    walk(v)

        walk(expr)
        return out

    def expression(self, n: dict, multi: bool, wrappers: set = frozenset(),
                   gen_literal: Any = None) -> str:
        if n.get("kind") == "binary" and n.get("label") in wrappers:
            return self.expression(n["lhs"], multi, wrappers, gen_literal)
        return self._expr(n, multi, wrappers, gen_literal)

    def _expr(self, n: dict, multi: bool, wrappers: set = frozenset(),
              gen_literal: Any = None) -> str:
        kind = n.get("kind")
        if kind == "input":
            return self.projection(n["proj"])
        if kind == "rank_value":
            # A coordinate read as a value -- EDGE's "rank variables as
            # tensors". It is a leaf of the EXPRESSION union, so it lands
            # here and not in `rank`, which handles subscripts. Exact cover's
            # stamp sigma(d, r) = d*|R| + r is the first cascade to use one.
            return self.rank(n["expr"])
        if kind == "occupancy":
            return r"\lVert " + self.projection(n["operand"]) + r" \rVert"
        if kind == "unary":
            name = _op_name(n["op"])
            inner = self.expression(n["operand"], multi, wrappers, gen_literal)
            if name == "floor":
                return rf"\lfloor {inner} \rfloor"
            return _glyph(UNARY, name) + " " + inner
        if kind == "anonymous":
            inner = self.expression(n["expression"], multi, wrappers, gen_literal)
            sub = ",".join(
                self.rank(r, generational=(gen_literal is not None
                                           and r.get("kind") == "literal"
                                           and r.get("value") == gen_literal))
                for r in n.get("ranks", []))
            return rf"({inner})_{{{sub}}}" if sub else f"({inner})"
        if kind == "binary":
            lhs = self.expression(n["lhs"], multi, wrappers, gen_literal)
            rhs = self.expression(n["rhs"], multi, wrappers, gen_literal)
            infix = getattr(self, "_infix", {}).get(n.get("label"))
            if infix:
                return f"{lhs} {infix} {rhs}"
            # The label ties this operator to its spec. It is only written
            # when there is more than one spec to tell apart.
            lab = rf"\cdot^{n['label']}" if multi else r"\cdot"
            return f"{lhs} {lab} {rhs}"
        return r"\text{?}"

    # -- specs -------------------------------------------------------------
    def specs(self, specs: list[dict]) -> str:
        """`:: \\bigwedge^1 +(\\cup) \\bigvee \\min(\\cup)`

        Map is the conjunction, Reduce the disjunction -- the paper's own
        quantifiers. Populate is written with its own operator, below.
        """
        wrappers = self._wrapper_label(specs)
        infix = getattr(self, "_infix", {})
        maps = [s for s in specs
                if s.get("kind") == "map" and s.get("label") not in wrappers
                and s.get("label") not in infix]
        reduces = [s for s in specs if s.get("kind") == "reduce"]
        multi = len(maps) > 1
        out = []
        placed = set()

        def vee(s):
            # With several labels a reduce says which one it folds and over
            # which rank, and sits right after that label's map -- the
            # paper's own order (`/\^1 +(^) \/^1_s ANY(u) /\^2 <-(^)`).
            if not multi:
                return rf"\bigvee {self._opsig(s)}"
            ranks = ",".join(s.get("rank_list") or [])
            sub = f"_{{{ranks}}}" if ranks else ""
            return rf"\bigvee\nolimits^{s.get('label')}{sub} {self._opsig(s)}"

        for s in maps:
            q = (rf"\bigwedge\nolimits^{s['label']}" if multi
                 else r"\bigwedge")
            out.append(f"{q} {self._opsig(s)}")
            for k, r in enumerate(reduces):
                if r.get("label") == s.get("label"):
                    out.append(vee(r))
                    placed.add(k)
        for k, s in enumerate(reduces):
            if k not in placed:
                out.append(vee(s))
        return r" \;::\; " + r"\;\; ".join(out) if out else ""

    def _opsig(self, s: dict) -> str:
        c = _glyph(COMPUTE, _op_name(s.get("compute_op")))
        m = _op_name(s.get("merge_op"))
        return f"{c}({_glyph(MERGE, m)})" if m else c

    def populate(self, s: dict) -> str:
        """`<<<_{v*} compute(coord)`.

        Both names are printed, in the same compute(bracketed) shape Map and
        Reduce use. The bracketed one is the COORDINATE operator, because
        that is the one that chooses which coordinate survives; the compute
        operator only says what value to write once a coordinate is chosen.
        Printing just one of them -- which the hand-written table did, naming
        the compute op in the deciding position -- tells the reader the
        opposite of how the action works.
        """
        coord = _op_name(s.get("coord_op")) or "?"
        compute = _op_name(s.get("compute_op")) or "?"
        starred = ",".join(f"{r}^*" for r in (s.get("rank_list") or []))
        # The compute op goes through the glyph table so `identity` prints as
        # the paper's bold 1, the way the specification writes it. The
        # coordinate op is a name and stays a name.
        return (rf"\lll_{{{starred}}} {_glyph(COMPUTE, compute)}"
                rf"(\text{{{_esc(coord)}}})")

    # -- a whole Einsum ----------------------------------------------------
    def einsum(self, e: dict) -> str:
        out = e["output_tensor"]
        ranks = e.get("output_ranks", [])
        pops = [s for s in e.get("specs", []) if s.get("kind") == "populate"]

        declared = self.ranks_of.get(out, [])
        starred = set()
        for s in pops:
            starred |= set(s.get("rank_list") or [])

        parts = []
        for pos, r in enumerate(ranks):
            gen = pos < len(declared) and declared[pos] == self.gen_rank
            text = self.rank(r, generational=gen)
            if r.get("kind") == "var" and r["name"] in starred:
                text += "^*"
            parts.append(text)
        lhs = self.name(out) + (_sub(",".join(parts)) if parts else "")

        specs = e.get("specs", [])
        wrappers = self._wrapper_label(specs)
        # A comparison against an occupancy is written infix, as the paper
        # writes it in stopping conditions: `||ActiveCol_{i+1}|| == 0`. Its
        # Map is then shown in the expression rather than after `::`.
        self._infix = self._infix_labels(e["expression"], specs)
        multi = len([s for s in specs if s.get("kind") == "map"
                     and s.get("label") not in wrappers
                     and s.get("label") not in self._infix]) > 1
        gen_literal = next(
            (r["value"] for pos, r in enumerate(ranks)
             if r.get("kind") == "literal"
             and pos < len(declared) and declared[pos] == self.gen_rank),
            None)
        rhs = self.expression(e["expression"], multi, wrappers, gen_literal)

        if pops:
            return f"{lhs} = {rhs} {self.populate(pops[0])}"
        return f"{lhs} = {rhs}{self.specs(e.get('specs', []))}"

    def arms(self, einsums: list[dict]) -> str:
        """Several IR nodes the author wrote as one Einsum.

        Rendered as an ordered stack because that is what runs: each arm
        overwrites the last on the coordinates it produces. The conditions a
        `cases` would show are not in the IR to recover.
        """
        if len(einsums) == 1:
            return self.einsum(einsums[0])
        lines = r" \\[2pt] ".join(
            rf"\text{{({i + 1})}}\quad {self.einsum(e)}"
            for i, e in enumerate(einsums)
        )
        return r"\begin{array}{l} " + lines + r" \end{array}"

    # -- the stopping condition -------------------------------------------
    def stopping(self, cond: dict) -> str:
        p = cond.get("predicate", {})
        if p.get("kind") != "comparison":
            return r"\diamond"
        lhs, rhs, op = p.get("lhs", {}), p.get("rhs", {}), p.get("op", "=")
        sym = r"\equiv" if op == "==" else op
        return (rf"\diamond \,:\; {self._pred(lhs)} "
                rf"{sym} {self._pred(rhs)}")

    def _pred(self, n: dict) -> str:
        kind = n.get("kind")
        if kind == "property_app" and n.get("name") == "occupancy":
            o = n["operands"][0]
            sub = self.subscript(o["tensor"], o.get("ranks", []))
            return rf"\lVert {self.name(o['tensor'])}_{{{sub}}} \rVert"
        if kind == "tensor_value":
            return self.projection(n["proj"])
        if kind == "property_app":
            return rf"\text{{{n.get('name', '?')}}}"
        return r"\text{?}"


def generations(program: dict, cascade: dict) -> dict:
    """label -> the generation its output is written at: "i", "i+1" or "1".

    Read off the IR's output ranks, not scraped out of the rendered formula.
    The page used to regex this from the hand-written LaTeX string, which
    made a caption feature depend on the punctuation of a piece of prose --
    and silently returned None the moment the prose was reformatted. It
    drives the before/after toggle's labels, so a None there is a visible
    hole in the page produced by an invisible cause.
    """
    r = Renderer(program, cascade)
    nodes = program["main_edge"]["cascade"]["einsums"]
    out: dict[str, str | None] = {}
    for label, idx in (cascade.get("labels") or {}).items():
        first = nodes[idx[0] if isinstance(idx, list) else idx]
        declared = r.ranks_of.get(first["output_tensor"], [])
        gen = None
        for pos, rk in enumerate(first.get("output_ranks", [])):
            if pos < len(declared) and declared[pos] == r.gen_rank:
                gen = (str(rk["value"]) if rk.get("kind") == "literal"
                       else r.rank(rk))
                break
        out[label] = gen
    return out


def render_all(program: dict, cascade: dict, alias: dict | None = None) -> dict:
    """label -> LaTeX, for every written Einsum plus init and stop."""
    r = Renderer(program, cascade, alias)
    nodes = program["main_edge"]["cascade"]["einsums"]
    out: dict[str, str] = {}

    for label, idx in (cascade.get("labels") or {}).items():
        idxs = idx if isinstance(idx, list) else [idx]
        out[label] = r.arms([nodes[i] for i in idxs])

    init = program.get("initialization", {}).get("einsums", [])
    if init:
        out[cascade.get("initLabel", "init")] = r.arms(init)

    conds = program["main_edge"]["cascade"].get("stopping_conditions") or []
    if conds:
        out[cascade.get("stopLabel", "stop")] = r.stopping(conds[0])
    return out
