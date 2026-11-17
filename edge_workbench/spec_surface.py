# -*- coding: utf-8 -*-
"""Read the specification's surface Einsums, so the SPEC can check the IR.

WHY THIS EXISTS
---------------
The formula on the page is rendered from the IR, on the reasoning that a
derived formula cannot contradict the program. That is true and it is not
enough, because it makes the IR the authority -- and the IR is a LOWERING of
the specification, written by hand, and it can be wrong.

It was. `einsum.edge` writes E10 as

    PushCand_{i, u, v*} = Adm_{i, u, v} <<<_{v*} 1(pick-admissible-edge)

one operator name. The IR lowered it with `pick-admissible-edge` in the
compute slot -- aliased to `identity` so it would behave like the `1` it
displaced -- and a name appearing in NO specification, `select-one-admissible-v`,
invented to fill the coordinate slot and bound to a lowest-coordinate rule the
algorithm never asks for. Rendering from the IR faithfully displayed that, and
the displayed formula named an operator the author had never written.

So the direction of authority is fixed here: `einsum.edge` is the source of
truth, the IR is checked against it, and a disagreement means the IR is wrong.

WHAT THIS CHECKS, AND WHAT IT DOES NOT
--------------------------------------
Not a parser for the EDGE language. It extracts, per labelled Einsum:

  * the output tensor and its rank list
  * the operand tensors, in order
  * the *named* operators -- hyphenated identifiers like
    `pick-admissible-edge`, which is the kind a lowering invents or misplaces

It deliberately does not try to match glyph operators (`<-`, `/\\`, `∩`) or
reconstruct the expression tree; that needs the real parser, and a
half-parser that quietly skips what it cannot read is worse than none. The
three things above are the ones that went wrong in practice.
"""

from __future__ import annotations

from edge_workbench.cascade_shape import flat_nodes, stopping_conditions  # noqa: F401

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: `# E10: some comment` -- the label that ties a surface Einsum to the IR.
LABEL_RE = re.compile(r"^#\s*(E\d{2})\s*:")

#: `Out_{i, u, v} = ...` or `Out_u = ...`
# The output name may be lower-case: the spec writes `delta`, which the IR
# declares as `Delta` and cascade.json aliases back for display.
# A starred name (`d*_i`, exact cover's chosen depth) is a name too.
# A bare subscript may be a coordinate: `TopDown_0 = True`.
HEAD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*\*?)(?:_\{([^}]*)\}|_([a-z0-9][A-Za-z0-9]*))\s*=")

#: An operator name a human wrote out, rather than a glyph. These are the ones
#: a lowering invents (`select-one-admissible-v`) or moves between slots.
NAMED_OP_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")

#: `FS^{I, U = |V|, V = |V|}  -> integer, empty = 0`
DECL_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9_]*)\^\{([^}]*)\}\s*->\s*([A-Za-z]+)\s*,\s*"
    r"empty\s*=\s*(\S+)\s*$"
)

#: Tensor references on the right-hand side.
OPERAND_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*)(?=_|\b)")


@dataclass
class SurfaceEinsum:
    """One Einsum as the specification writes it."""

    label: str
    text: str
    output: str = ""
    output_ranks: tuple[str, ...] = ()
    named_ops: tuple[str, ...] = ()
    operands: tuple[str, ...] = field(default_factory=tuple)
    depth: int = 1
    """How many cascades it sits in: 1 in the outer cascade, 2 in an inner
    one (`cascade_depths`)."""
    macro: str | None = None
    """The `- Macro NAME(...)` section it is written in, if any. Its text is
    then in the macro's FORMAL names."""
    writes: tuple[str, ...] = ()
    """The tensors it writes once every macro call is expanded: its own
    output, or, in a macro, what each call binds that formal name to."""
    written_ranks: tuple[tuple[str, ...], ...] = ()
    """The output ranks to go with each of `writes`."""

    @property
    def actual(self) -> str:
        """The tensor the IR writes for it (the first call's, in a macro)."""
        return self.writes[0] if self.writes else self.output


def _split_ranks(raw: str | None, bare: str | None) -> tuple[str, ...]:
    if bare:
        return (bare,)
    if not raw:
        return ()
    # `j : j >= 1` (or `s : s in id`) is the rank `j` with a condition on
    # where the Einsum runs; the rank is what the output is written at.
    return tuple(p.split(":")[0].strip() for p in raw.split(",")
                 if p.strip())


class Surface(dict):
    """label -> SurfaceEinsum, plus what einsum.edge says around them.

    A plain dict of the labelled Einsums, so every reader that wants "the
    Einsums" is unchanged. A file with macros also has

      conditionals  the labelled multi-output case statements, in order;
                    each lowers to a conditional cascade, not to an Einsum,
                    so it is NOT a key of this dict
      macros        name -> the `- Macro` section, with its body's labels
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.conditionals: list[SurfaceConditional] = []
        self.macros: dict[str, SurfaceMacro] = {}


def parse_edge_file(path: Path) -> Surface:
    """label -> the Einsum the spec writes under it.

    A label comment introduces the Einsum on the following non-comment,
    non-blank lines, up to the next label or blank line. `cases` blocks run
    over several indented lines and are kept whole.

    A labelled multi-output case statement (`(A_{..}, B_{..}) = cases:` with
    one macro call per arm) is kept apart, in `.conditionals`; an Einsum in a
    `- Macro` section knows its macro and what each call makes it write.
    """
    lines = Path(path).read_text().splitlines()
    out = Surface()
    macro: SurfaceMacro | None = None

    i = 0
    while i < len(lines):
        section = MACRO_RE.match(lines[i].strip())
        if section:
            macro = SurfaceMacro(
                name=section.group(1), text=lines[i].strip()[1:].strip(),
                inputs=split_projections(section.group(2)),
                outputs=split_projections(section.group(3)))
            out.macros[macro.name] = macro
        elif lines[i].strip().startswith("- "):
            macro = None          # any other section ends a macro's body
        m = LABEL_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        label = m.group(1)
        i += 1
        body: list[str] = []
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if LABEL_RE.match(stripped):
                break
            if stripped.startswith("#"):
                i += 1
                continue          # a continuation comment
            if not stripped:
                if body:
                    break
                i += 1
                continue
            # An indented line continues a `cases` block; a fresh
            # left-aligned assignment starts a different Einsum, and so does
            # a section line (`- Macro ...`) or a stopping condition.
            if body and not line[:1].isspace() and (
                    "=" in stripped or stripped.startswith(("- ", "<>"))):
                break
            body.append(stripped.split("  #", 1)[0].rstrip())
            i += 1
        if body:
            text = join_statement(body)
            head = CONDITIONAL_RE.match(text)
            if head:
                out.conditionals.append(SurfaceConditional(
                    label=label, text=text,
                    outputs=split_projections(head.group(1)),
                    arms=tuple(_call(a) for a in case_arms(text))))
                continue
            out[label] = _analyse(label, text)
            if macro is not None:
                out[label].macro = macro.name
                macro.labels.append(label)
    for label, depth in cascade_depths(path).items():
        if label in out:
            out[label].depth = depth
    _bind_macros(out)
    return out


# --------------------------------------------- macros and their calls ---
# A macro section and a statement that calls macros are written
#
#     # E03: one direction per generation
#     (Tree_{i+1, s, d}, F_{i+1, d}, TopDown_{i+1}) = cases:
#         TOP-DOWN(G_{s, d}, F_{i, s}, Tree_{i, s, d})    if TopDown_i == True
#         BOTTOM-UP(G_{s, d}, F_{i, s}, Tree_{i, s, d})   if TopDown_i == False
#
#     - Macro TOP-DOWN(TG_{s, d}, TF_{i, s}, TTree_{i, s, d}) -> TTree_{i+1, s, d}, TF_{i+1, d}, TTopDown_{i+1}
#     # E04: ...
#     Nei_{i, d} = TG_{s, d} . TF_{i, s} :: /\ AND(∩) \/ OR(∪)
#
# The macro's body is written in its formal names, exactly as the tutorial
# writes it. A macro is a lexical substitution (paper, appendix B.8), so the
# IR holds the EXPANDED Einsums: a call binds each formal tensor to the
# actual one in the same position, inputs then outputs, and the body's
# Einsums follow those bindings.

#: `- Macro TOP-DOWN(TG_{s, d}, TF_{i, s}) -> TTree_{i+1, s, d}, TF_{i+1, d}`
MACRO_RE = re.compile(
    r"^-\s*Macro\s+([A-Za-z][A-Za-z0-9-]*)\s*\((.*)\)\s*->\s*(.+?)\s*$",
    re.IGNORECASE)
#: `(Tree_{i+1, s, d}, F_{i+1, d}) = cases: ...`, joined onto one line.
CONDITIONAL_RE = re.compile(r"^\((.*?)\)\s*=\s*cases\s*:?")
_PROJECTION = re.compile(
    r"^([A-Za-z][A-Za-z0-9]*\*?)(?:_\{([^}]*)\}|_([a-z0-9][A-Za-z0-9]*))?$")
_CALL = re.compile(r"^([A-Za-z][A-Za-z0-9-]*)\s*\((.*)\)$")

Projection = tuple  # (tensor name, (rank, ...))


def split_projections(text: str) -> tuple[Projection, ...]:
    """`G_{s, d}, F_{i, s}, MF_i` -> (("G", ("s", "d")), ("F", ("i", "s")),
    ("MF", ("i",))). A piece that is not a projection keeps its text as the
    name, so a comparison shows it rather than dropping it."""
    pieces, depth, start = [], 0, 0
    for k, ch in enumerate(text):
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth -= 1
        elif ch == "," and depth == 0:
            pieces.append(text[start:k])
            start = k + 1
    pieces.append(text[start:])
    out = []
    for piece in (p.strip() for p in pieces):
        if not piece:
            continue
        m = _PROJECTION.match(piece)
        out.append((m.group(1), _split_ranks(m.group(2), m.group(3)))
                   if m else (piece, ()))
    return tuple(out)


@dataclass(frozen=True)
class SurfaceCall:
    """One arm of a multi-output case statement: a macro call and when."""

    macro: str
    args: tuple[Projection, ...]
    cond: str                       # "" for `otherwise`


@dataclass
class SurfaceConditional:
    """A labelled multi-output case statement over macro calls."""

    label: str
    text: str
    outputs: tuple[Projection, ...]
    arms: tuple[SurfaceCall, ...]


@dataclass
class SurfaceMacro:
    """A `- Macro NAME(inputs) -> outputs` section."""

    name: str
    text: str                       # the header, without its leading dash
    inputs: tuple[Projection, ...]
    outputs: tuple[Projection, ...]
    labels: list[str] = field(default_factory=list)


def _call(arm: "SurfaceArm") -> SurfaceCall:
    m = _CALL.match(arm.expr.strip())
    if not m:
        return SurfaceCall(arm.expr.strip(), (), arm.cond)
    return SurfaceCall(m.group(1), split_projections(m.group(2)), arm.cond)


def call_bindings(macro: SurfaceMacro, call: SurfaceCall,
                  outputs: tuple[Projection, ...]
                  ) -> tuple[dict[str, str], dict[str, str]]:
    """(formal tensor -> actual tensor, formal rank variable -> actual) for
    one call: inputs bind positionally to the call's arguments, the declared
    outputs to the statement's left-hand side.

    A formal subscript that is a plain variable binds to whatever the call
    writes there; one written as a shift (`TF_{i+1, d}`) binds through the
    shift only when the call writes the same shift, which is all the label
    map needs to follow an output's ranks.
    """
    tensors: dict[str, str] = {}
    ranks: dict[str, str] = {}
    for formals, actuals in ((macro.inputs, call.args),
                             (macro.outputs, outputs)):
        for (f_name, f_ranks), (a_name, a_ranks) in zip(formals, actuals):
            tensors.setdefault(f_name, a_name)
            for f, a in zip(f_ranks, a_ranks):
                f, a = f.replace(" ", ""), a.replace(" ", "")
                if re.fullmatch(r"[a-z][A-Za-z0-9]*", f):
                    ranks.setdefault(f, a)
    return tensors, ranks


def _bind_macros(surface: Surface) -> None:
    """Fill `writes` / `written_ranks` on every Einsum."""
    for e in surface.values():
        e.writes, e.written_ranks = (e.output,), (e.output_ranks,)
    found: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
    for stmt in surface.conditionals:
        for call in stmt.arms:
            macro = surface.macros.get(call.macro)
            if macro is None:
                continue
            tensors, ranks = call_bindings(macro, call, stmt.outputs)
            for label in macro.labels:
                e = surface[label]
                bound = (tensors.get(e.output, e.output),
                         tuple(ranks.get(r.replace(" ", ""), r)
                               for r in e.output_ranks))
                if bound not in found.setdefault(label, []):
                    found[label].append(bound)
    for label, bound in found.items():
        surface[label].writes = tuple(name for name, _ in bound)
        surface[label].written_ranks = tuple(r for _, r in bound)


def expansion_order(surface: dict) -> list[tuple[str, str, tuple[str, ...]]]:
    """(label, tensor written, output ranks) in the order the IR's flat
    nodes come: the cascade's own Einsums in label order, and at each
    multi-output case statement the body of each arm's macro, expanded.

    A file without macros is its labels in order.
    """
    conditionals = {c.label: c for c in getattr(surface, "conditionals", [])}
    macros = getattr(surface, "macros", {})
    out: list[tuple[str, str, tuple[str, ...]]] = []
    for label in sorted(set(surface) | set(conditionals)):
        if label in conditionals:
            stmt = conditionals[label]
            for call in stmt.arms:
                macro = macros.get(call.macro)
                if macro is None:
                    continue
                tensors, ranks = call_bindings(macro, call, stmt.outputs)
                for body in macro.labels:
                    e = surface[body]
                    out.append((body, tensors.get(e.output, e.output),
                                tuple(ranks.get(r.replace(" ", ""), r)
                                      for r in e.output_ranks)))
            continue
        e = surface[label]
        if getattr(e, "macro", None):
            continue                  # reached through its macro's calls
        out.append((label, e.output, e.output_ranks))
    return out


#: `alpha = 15` under `- Constants`.
_CONSTANT = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(\S+)$")


def parse_constants(path: Path) -> dict[str, str]:
    """name -> value, for every line of a `- Constants` section.

    A constant is a number the cascade reads by name and nothing writes
    (DO-BFS's switching thresholds). It lowers to a zero-rank declaration
    carrying the value, so it is part of the program and not an input.
    """
    out: dict[str, str] = {}
    inside = False
    for raw in Path(path).read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if raw.strip().startswith("- "):
            inside = raw.strip().lower().startswith("- constant")
            continue
        m = _CONSTANT.match(line) if inside else None
        if m:
            out[m.group(1)] = m.group(2)
    return out


# ------------------------------------------------------ case statements ---
# A case statement is written
#
#     Z_{0, j, n} = cases:
#         Z_{0, j-1, n}                  if n < j
#         min(Z_{0, j-1, j}, A_{j+1})    if n = j
#         empty                          otherwise
#
# one arm per indented line: an EDGE expression (with its own `:: ...` when it
# needs one), then `if <condition>` or `otherwise`. `empty` as the expression
# means the region gets no value. On one line the arms are separated by ` ; `,
# which is the form every reader below works on.

ARM_SEP = " ; "
_CASES_HEAD = re.compile(r"=\s*cases\s*:?\s*")


def join_statement(lines: list[str]) -> str:
    """One statement's lines as one line; a `cases` block keeps its arms apart."""
    if len(lines) > 1 and re.search(r"=\s*cases\s*:?\s*$", lines[0]):
        return lines[0].rstrip() + " " + ARM_SEP.join(lines[1:])
    return " ".join(lines)


@dataclass(frozen=True)
class SurfaceArm:
    """One arm of a written case statement."""

    expr: str            # the expression, with its `:: ...` if it has one
    cond: str            # "" for `otherwise`

    def key(self) -> tuple[str, str]:
        """Whitespace-free, `==` and `=` alike, for comparing two spellings."""
        def flat(text: str) -> str:
            return re.sub(r"\s+", "", text).replace("==", "=")
        return flat(self.expr), flat(self.cond)

    @property
    def is_empty(self) -> bool:
        return self.expr.strip() == "empty"


def split_arm(text: str) -> SurfaceArm:
    text = text.strip()
    m = re.match(r"^(.*?)\s+otherwise$", text)
    if m:
        return SurfaceArm(m.group(1).strip(), "")
    # The LAST ` if `: an expression never contains one, a condition might
    # not either, and the condition is what the line ends with.
    head, sep, cond = text.rpartition(" if ")
    if sep:
        return SurfaceArm(head.strip(), cond.strip())
    return SurfaceArm(text, "")


def case_arms(text: str) -> list[SurfaceArm]:
    """The arms of a one-line case statement; [] when `text` is not one."""
    m = _CASES_HEAD.search(text)
    if not m:
        return []
    rest = text[m.end():].strip()
    return [split_arm(a) for a in rest.split(ARM_SEP) if a.strip()] if rest else []


def is_cases(text: str) -> bool:
    return bool(_CASES_HEAD.search(text))


def strip_subscripts(text: str) -> str:
    """`text` without its `_{...}` subscripts: `j-1` in a subscript is rank
    arithmetic, not a hyphenated operator name."""
    return re.sub(r"_\{[^{}]*\}", "_", text)


def _analyse(label: str, text: str) -> SurfaceEinsum:
    e = SurfaceEinsum(label=label, text=text)
    head = HEAD_RE.match(text)
    if head:
        e.output = head.group(1)
        e.output_ranks = _split_ranks(head.group(2), head.group(3))
        rhs = text[head.end():]
    else:
        rhs = text

    e.named_ops = tuple(sorted(set(NAMED_OP_RE.findall(strip_subscripts(rhs)))))

    # Operand tensors: capitalised names on the right, minus the operator
    # words that happen to be capitalised.
    words = {"AND", "OR", "ANY", "NOT"}
    e.operands = tuple(
        t for t in OPERAND_RE.findall(strip_subscripts(rhs)) if t not in words
    )
    return e


@dataclass
class SurfaceDeclaration:
    """One tensor as the specification declares it."""

    name: str
    ranks: tuple[str, ...]
    data_type: str
    empty: str


def parse_declarations(path: Path) -> dict[str, SurfaceDeclaration]:
    """name -> the declaration the spec gives it.

    Every tensor the spec declares, primary and intermediate alike. The empty
    value is the reason this matters: `value == empty => absent` is load-bearing
    everywhere in EDGE, and a tensor declared `empty = 0` where the spec says
    `+inf` drops every zero-valued entry. That exact mistake has happened here
    before, on `NeiLbl`, and nothing compared the two declarations.

    Ranks are kept as written (`U = |V|`), not normalised; the extent side is
    the instance's business, not the declaration's.
    """
    out: dict[str, SurfaceDeclaration] = {}
    for line in Path(path).read_text().splitlines():
        m = DECL_RE.match(line.strip())
        if not m:
            continue
        name, ranks, dtype, empty = m.groups()
        out[name] = SurfaceDeclaration(
            name=name,
            ranks=tuple(r.split("=")[0].strip() for r in ranks.split(",")),
            data_type=dtype.lower(),
            empty=empty,
        )
    return out


def normalise_empty(value: object) -> str:
    """The spec and the IR spell empty values differently; compare meanings.

    `False` / `false`, `+inf` / `"inf"`, `0` / `0`. JSON has no infinity, so
    the IR carries it as a string.
    """
    if isinstance(value, bool):
        return "false" if value is False else "true"
    text = str(value).strip().lower().lstrip("+")
    return {"infinity": "inf", "none": "none"}.get(text, text)


def _rank_text(rank: dict) -> str:
    kind = rank.get("kind")
    if kind == "var":
        return rank["name"]
    if kind == "literal":
        return str(rank["value"])
    if kind == "arith":
        return f"{_rank_text(rank['lhs'])}{rank['op']}{_rank_text(rank['rhs'])}"
    return "?"


def derive_labels(surface: dict, program: dict,
                  alias: dict | None = None) -> dict:
    """label -> IR node index (or indices), derived rather than declared.

    `cascade.json` used to state this by hand, and it is load-bearing: the
    coverage gate, the drill-down and the spec-vs-IR comparison all key off it.

    Walk the spec's labels in order and the IR's nodes in order. A label
    claims the consecutive nodes that write what it writes -- same tensor,
    same output ranks -- so max-flow's E04, a three-arm `cases` lowered to
    three writes of `R_{1,u,v}`, lands whole on E04.

    It may also claim HELPER nodes immediately before those: nodes writing a
    tensor the specification never writes, introduced because the IR cannot
    say the Einsum in one node. Exact cover's `d*_i = floor(F/|R|) :: max`
    lowers to `FQuot` then `DStar`. A helper belongs to the label whose own
    write follows it.

    An Einsum in a macro's body is written in formal names (`TTree_{i+1,s,d}`)
    and the IR holds the expansion (`Tree`), so the walk follows each call's
    bindings and visits the body once per call, where the call stands in the
    cascade (`expansion_order`). A macro called twice maps each body label
    to a list of nodes.

    Returns {} if the walk cannot consume every node, because a partial map
    would be worse than none -- the caller should treat that as the lowering
    not corresponding to the specification.
    """
    alias = alias or {}
    nodes = flat_nodes(program)
    order = expansion_order(surface)
    spec_writes = {tensor for _, tensor, _ in order}

    def shown(node: dict) -> str:
        return alias.get(node["output_tensor"], node["output_tensor"])

    def signature(node: dict) -> tuple:
        return (
            shown(node),
            tuple(_rank_text(r).replace("*", "")
                  for r in node.get("output_ranks", [])),
        )

    out: dict[str, Any] = {}
    cursor = 0
    for label, tensor, ranks in order:
        want = (
            tensor,
            tuple(r.replace(" ", "").replace("*", "") for r in ranks),
        )
        own = cursor
        while own < len(nodes) and shown(nodes[own]) not in spec_writes:
            own += 1                                  # helpers
        end = own
        while end < len(nodes) and signature(nodes[end]) == want:
            end += 1
        if end == own:
            continue
        claimed = list(range(cursor, end))
        cursor = end
        if label in out:              # a macro called more than once
            before = out[label] if isinstance(out[label], list) else [out[label]]
            claimed = before + claimed
        out[label] = claimed[0] if len(claimed) == 1 else claimed

    return out if cursor == len(nodes) else {}


def helper_tensors(surface: dict, program: dict, labels: dict,
                   alias: dict | None = None) -> set[str]:
    """Tensors written only by helper nodes: the lowering's, not the spec's."""
    alias = alias or {}
    nodes = flat_nodes(program)
    spec_writes = {tensor for _, tensor, _ in expansion_order(surface)}
    out = set()
    for idx in labels.values():
        for i in (idx if isinstance(idx, list) else [idx]):
            name = nodes[i]["output_tensor"]
            if alias.get(name, name) not in spec_writes:
                out.add(name)
    return out


# ---------------------------------------------------------- operators ---
# The surface writes operators as glyphs; the IR writes them as names. These
# are the two halves of the same table, and the mapping is what lets the spec
# check the lowering.
SURFACE_COMPUTE = {
    "+": "+", "-": "-", "*": "*", "/": "/",
    "<-": "take_left", "->": "take_right",
    "==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge",
    "min": "min", "max": "max",
    "AND": "AND", "OR": "OR", "ANY": "ANY",
    "<<": "update",
    "1": "identity",
}
#: Spelled-out names upstream registers as exact aliases of the short ones
#: (`edge_ir/udf/builtins.py`). The same operator under either name is not a
#: disagreement; Bellman-Ford's IR writes `less_than` where the table says `lt`.
COMPUTE_ALIASES = {
    "equals": "eq", "not_equals": "ne", "less_than": "lt",
    "less_equal": "le", "greater_than": "gt", "greater_equal": "ge",
    "pass_through": "identity",
}
SURFACE_MERGE = {
    "∩": "intersect", "∪": "union",
    "<-": "take_left", "->": "take_right",
    "!<-": "not_left",
}
#: `/\^1 <-(∩)` or `\/ +(∪)` -- quantifier, optional label, compute, merge.
#: The quantifier may name its rank, `/\_s +(∩)` or `\/_{v*}`, as
#: Bellman-Ford's spec does; the rank is not compared, only skipped over.
SPEC_RE = re.compile(
    r"(/\\|\\/)(?:_(?:\{[^}]*\}|[A-Za-z0-9*]+))?(?:\^(\d+))?\s*"
    r"([^\s(]+)\(([^)]*)\)"
)


@dataclass(frozen=True)
class SurfaceSpec:
    """One `compute(merge)` group from a surface Einsum's `::` section."""

    action: str          # "map" or "reduce"
    label: int | None
    compute: str         # IR name, not the glyph
    merge: str


def parse_specs(text: str) -> tuple[SurfaceSpec, ...]:
    r"""The operators a surface Einsum states, as the IR would name them.

    `/\` is Map and `\/` is Reduce, matching the paper's quantifiers. An
    unrecognised glyph is kept verbatim rather than dropped, so a comparison
    fails loudly on a spelling this table has not learned instead of silently
    checking nothing.
    """
    if "::" not in text:
        return ()
    out = []
    for quant, label, compute, merge in SPEC_RE.findall(text.split("::", 1)[1]):
        out.append(SurfaceSpec(
            action="map" if quant == "/\\" else "reduce",
            label=int(label) if label else None,
            compute=SURFACE_COMPUTE.get(compute, compute),
            merge=SURFACE_MERGE.get(merge, merge),
        ))
    return tuple(out)


# ------------------------------------------------------ nested cascades ---

def cascade_depths(path: Path) -> dict[str, int]:
    """label -> how many cascades the Einsum sits in (1 = the outer one).

    An inner cascade is the labelled Einsums between a `- Begin inner
    cascade` line and the `<><> : ...` line that ends it; without the
    `Begin` line, everything since the previous stopping condition. Each
    further `<>` in the stopping condition is one more level.
    """
    out: dict[str, int] = {}
    depth = 1
    since: list[str] = []            # labels since the last boundary
    opened = 0                       # explicit `Begin inner` lines still open
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        m = LABEL_RE.match(line)
        if m:
            out[m.group(1)] = depth
            since.append(m.group(1))
            continue
        if line.startswith("- ") and "inner cascade" in line.lower():
            depth += 1
            opened += 1
            since = []
            continue
        stop = re.match(r"^((?:<>)+)\s*:", line)
        if stop:
            level = stop.group(1).count("<>")
            if level > 1:
                if opened:
                    opened -= 1
                    depth -= 1
                else:
                    for label in since:      # no `Begin` line: retroactive
                        out[label] = max(out[label], level)
            since = []
    return out
