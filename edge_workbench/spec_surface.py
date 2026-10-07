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

import re
from dataclasses import dataclass, field
from pathlib import Path

#: `# E10: some comment` -- the label that ties a surface Einsum to the IR.
LABEL_RE = re.compile(r"^#\s*(E\d{2})\s*:")

#: `Out_{i, u, v} = ...` or `Out_u = ...`
# The output name may be lower-case: the spec writes `delta`, which the IR
# declares as `Delta` and cascade.json aliases back for display.
# A starred name (`d*_i`, exact cover's chosen depth) is a name too.
HEAD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*\*?)(?:_\{([^}]*)\}|_([a-z][A-Za-z0-9]*))\s*=")

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


def _split_ranks(raw: str | None, bare: str | None) -> tuple[str, ...]:
    if bare:
        return (bare,)
    if not raw:
        return ()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def parse_edge_file(path: Path) -> dict[str, SurfaceEinsum]:
    """label -> the Einsum the spec writes under it.

    A label comment introduces the Einsum on the following non-comment,
    non-blank lines, up to the next label or blank line. `cases` blocks run
    over several indented lines and are kept whole.
    """
    lines = Path(path).read_text().splitlines()
    out: dict[str, SurfaceEinsum] = {}

    i = 0
    while i < len(lines):
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
            # left-aligned assignment starts a different Einsum.
            if body and not line[:1].isspace() and "=" in stripped:
                break
            body.append(stripped)
            i += 1
        if body:
            out[label] = _analyse(label, " ".join(body))
    return out


def _analyse(label: str, text: str) -> SurfaceEinsum:
    e = SurfaceEinsum(label=label, text=text)
    head = HEAD_RE.match(text)
    if head:
        e.output = head.group(1)
        e.output_ranks = _split_ranks(head.group(2), head.group(3))
        rhs = text[head.end():]
    else:
        rhs = text

    e.named_ops = tuple(sorted(set(NAMED_OP_RE.findall(rhs))))

    # Operand tensors: capitalised names on the right, minus the operator
    # words that happen to be capitalised.
    words = {"AND", "OR", "ANY", "NOT"}
    e.operands = tuple(
        t for t in OPERAND_RE.findall(rhs) if t not in words
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

    Returns {} if the walk cannot consume every node, because a partial map
    would be worse than none -- the caller should treat that as the lowering
    not corresponding to the specification.
    """
    alias = alias or {}
    nodes = program["main_edge"]["cascade"]["einsums"]
    spec_writes = {e.output for e in surface.values()}

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
    for label in sorted(surface):
        einsum = surface[label]
        want = (
            einsum.output,
            tuple(r.replace(" ", "").replace("*", "")
                  for r in einsum.output_ranks),
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
        out[label] = claimed[0] if len(claimed) == 1 else claimed

    return out if cursor == len(nodes) else {}


def helper_tensors(surface: dict, program: dict, labels: dict,
                   alias: dict | None = None) -> set[str]:
    """Tensors written only by helper nodes: the lowering's, not the spec's."""
    alias = alias or {}
    nodes = program["main_edge"]["cascade"]["einsums"]
    spec_writes = {e.output for e in surface.values()}
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
