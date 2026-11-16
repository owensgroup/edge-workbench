# -*- coding: utf-8 -*-
"""What each rank IS, as the author declares it in the tutorial's front matter.

WHY THE AUTHOR SAYS IT
----------------------
Ranks say what shape the data has; they do not say what an index means.
`dp_{i,j}` over two string positions, `A_{m,k}` in a matrix product and
`G_{s,d}` over vertices all have two ranks, and only the first is not a
graph. A* declares `L_{S, XY = 2}`, each vertex's location: read as an edge
tensor it would be drawn as edges from every vertex to "vertex" 0 and 1 of
rank XY. Inference from ranks (`domain_shape.classify`) cannot tell
these apart, so the author -- increasingly an agent following the
`write-edge-tutorial` skill -- states it:

    ranks:
      I: generational
      S: vertex
      D: vertex

The vocabulary is CLOSED. A word not in `KINDS` stops the run, the same way an
unknown operator name does: guessing what an unknown kind means would change
the picture without anyone deciding it. Because the author may be an agent,
every declaration is checked against `einsum.edge` (`problems`), and the view
it implies is checked against the inference (`domain_shape.disagreement`).

A tutorial with no `ranks:` block still works: the view falls back to
`domain_shape.classify`'s inference and the generational rank to the existing rule.
"""

from __future__ import annotations

import re
from pathlib import Path

KEY = "ranks"

GENERATIONAL = "generational"
VERTEX = "vertex"
SET = "set"
ELEMENT = "element"
POSITION = "position"
SPATIAL = "spatial"

#: kind -> what it means, quoted in error messages so an author can choose.
KINDS = {
    GENERATIONAL: "the generational (or iterative) rank: one coordinate per "
                  "generation of the cascade (at most one rank)",
    VERTEX: "a vertex of a graph; every vertex rank indexes the same vertex set",
    SET: "a set (the rows of an exact-cover matrix): one side of a bipartite "
         "picture",
    ELEMENT: "an element the sets cover (the columns): the other side",
    POSITION: "a position in a sequence (bubble sort's array index)",
    SPATIAL: "an axis of physical space (A*'s XY): a tensor over a vertex "
             "rank and a spatial rank gives each vertex's location; it is "
             "not an edge tensor",
}

#: The kinds that are node sets of the picture.
NODE_KINDS = (VERTEX, SET, ELEMENT, POSITION)

_LINE = re.compile(r"^(\s+)([A-Za-z][A-Za-z0-9_.]*)\s*:\s*([^#\s]*)\s*(#.*)?$")


def read(tutorial: Path) -> dict[str, str] | None:
    """rank -> kind, from the front matter's `ranks:` mapping; None if absent.

    Hand-rolled, like `tutorial._block_scalar`, so the repository builds
    without a YAML library. Only the front matter is searched: a `ranks:` line
    in the body of the page is prose.
    """
    text = Path(tutorial).read_text()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        text = text[: end if end >= 0 else len(text)]
    m = re.search(rf"^{KEY}:\s*(#.*)?$", text, re.MULTILINE)
    if not m:
        return None
    out: dict[str, str] = {}
    indent = None
    for line in text[m.end():].splitlines()[1:]:
        if not line.strip() or line.strip().startswith("#"):
            continue
        lm = _LINE.match(line)
        if not lm or (indent is not None and len(lm.group(1)) != indent):
            break
        indent = len(lm.group(1))
        out[lm.group(2)] = lm.group(3).strip().strip("'\"").lower()
    return out


def generational_rank(kinds: dict[str, str] | None) -> str | None:
    """The rank declared `generational`, if any."""
    for rank, kind in (kinds or {}).items():
        if kind == GENERATIONAL:
            return rank
    return None


def problems(kinds: dict[str, str] | None, declarations: dict) -> list[str]:
    """Everything wrong with a `ranks:` block, against einsum.edge's tensors.

    `declarations` is `spec_surface.parse_declarations(einsum.edge)`: name ->
    an object with `.ranks`, the rank names as written. All problems are
    listed at once (DESIGN.md decision 13).
    """
    if kinds is None:
        return []
    out: list[str] = []
    menu = "; ".join(f"`{k}`: {v}" for k, v in KINDS.items())
    used: list[str] = []
    for d in declarations.values():
        for r in d.ranks:
            if r not in used:
                used.append(r)

    for rank, kind in kinds.items():
        if kind not in KINDS:
            out.append(f"ranks: {rank} is declared {kind!r}, which is not a "
                       f"rank kind. Choose one of: {menu}")
        if rank not in used:
            out.append(f"ranks: declares {rank}, but no tensor in einsum.edge "
                       f"has a rank {rank} (ranks used: {', '.join(used)})")
    for rank in used:
        if rank not in kinds:
            out.append(f"ranks: {rank} is used by einsum.edge but has no kind; "
                       f"add `  {rank}: <kind>`")

    gens = [r for r, k in kinds.items() if k == GENERATIONAL]
    if len(gens) > 1:
        out.append(f"ranks: {', '.join(gens)} are all `generational`; a "
                   f"cascade has one generational rank")
    for name, d in declarations.items():
        for r in gens:
            if r in d.ranks and d.ranks[0] != r:
                out.append(f"ranks: {r} is the generational rank but is not the first "
                           f"rank of {name}^{{{', '.join(d.ranks)}}}")

    present = set(kinds.values())
    if (SET in present) != (ELEMENT in present):
        have, need = (SET, ELEMENT) if SET in present else (ELEMENT, SET)
        out.append(f"ranks: there is a `{have}` rank but no `{need}` rank; a "
                   f"bipartite picture needs both sides")
    for name, d in declarations.items():
        ks = [kinds.get(r) for r in d.ranks]
        if SPATIAL in ks and not any(k in NODE_KINDS for k in ks):
            out.append(f"ranks: {name} is over a `spatial` rank but no "
                       f"node rank, so there is nothing it places")
    return out


def view(kinds: dict[str, str], gen_rank: str | None = None) -> dict:
    """The picture the declared kinds imply: `{"view", "sides", "reason"}`.

    vertex -> graph; set + element -> bipartite (sets left); position ->
    sequence. A spec mixing these gets the first in that order; the other
    tensors still appear in the tensor grids.
    """
    def ranks_of(kind):
        return [r for r, k in kinds.items() if k == kind and r != gen_rank]

    if ranks_of(VERTEX):
        vs = ranks_of(VERTEX)
        return {"view": "graph", "sides": (),
                "reason": f"ranks: declares {', '.join(vs)} as vertex"}
    if ranks_of(SET) and ranks_of(ELEMENT):
        left, right = ranks_of(SET)[0], ranks_of(ELEMENT)[0]
        return {"view": "bipartite", "sides": (left, right),
                "reason": f"ranks: declares {left} as set and {right} as "
                          f"element"}
    if ranks_of(POSITION):
        return {"view": "sequence", "sides": (),
                "reason": f"ranks: declares {', '.join(ranks_of(POSITION))} "
                          f"as position"}
    return {"view": "sequence", "sides": (),
            "reason": "ranks: declares no vertex, set/element or position "
                      "rank, so there is no node set to draw"}


def node_ranks(kinds: dict[str, str] | None, ranks: list[str]) -> list[str]:
    """`ranks` without the ones declared `spatial` or `generational`."""
    if not kinds:
        return ranks
    return [r for r in ranks if kinds.get(r) not in (SPATIAL, GENERATIONAL)]


def is_spatial(kinds: dict[str, str] | None, rank: str) -> bool:
    return bool(kinds) and kinds.get(rank) == SPATIAL
