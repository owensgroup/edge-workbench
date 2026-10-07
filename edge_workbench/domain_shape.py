# -*- coding: utf-8 -*-
"""Which picture an algorithm wants, decided from its tensors.

A rank-2 tensor is always a graph on its two rank sets -- that is what an
adjacency matrix is. When the two ranks are the SAME vertex set you get the
directed graph max-flow and BFS draw; when they are DIFFERENT sets you get a
bipartite graph, which is what exact cover is: rows are sets, columns are
elements, and an exact cover picks rows so every column has degree one.

So `graph` and `bipartite` are one renderer over two layouts, not two
renderers. What is not a graph is an algorithm with no rank-2 tensor at all --
bubble sort over a single rank -- which wants a sequence.

TELLING THE TWO GRAPH CASES APART
---------------------------------
"Two rank names" is not the signal: max-flow declares `U` and `V` and they are
the same six vertices. Two signals that do work, and the first is decisive:

  1. WHERE THE RANK-1 TENSORS LIVE. Max-flow's twelve rank-1 tensors are all
     over `U` -- not one over `V` -- because a vertex property is a property
     of a vertex, whichever position it is read in. Exact cover has rank-1
     tensors over BOTH `R` (SelRow, ActiveRow, Candidates) and `C` (CovCol,
     ActiveCol, RowCounts), because rows and columns are different things with
     different properties.

  2. THE EXTENTS. Different extents prove different sets. Equal extents prove
     nothing -- a 4x4 exact-cover matrix is still bipartite -- which is why
     this is the weaker signal and only used to confirm.

Neither signal is a guess about intent, and an author who disagrees can say so
in `domain.json`; this decides the default, not the answer.
"""

from __future__ import annotations

from collections import Counter

from edge_workbench import tensor_facts

GRAPH = "graph"
BIPARTITE = "bipartite"
SEQUENCE = "sequence"


def classify(program: dict, instance: dict | None = None,
             gen_rank: str = "I") -> dict:
    """The view this program wants, and why.

    Returns `{"view", "sides", "reason"}`. `sides` names the rank on each side
    of a bipartite picture, left first, in declaration order; it is empty for
    the other views.
    """
    sides_of = tensor_facts.rank_sides(program, gen_rank)
    ranks = tensor_facts.node_ranks(program, gen_rank)
    extents = tensor_facts.extents_of(instance or {})

    pairs = {v for v in sides_of.values() if len(v) == 2}
    singles = Counter(v[0] for v in sides_of.values() if len(v) == 1)

    if not pairs:
        return {
            "view": SEQUENCE,
            "sides": (),
            "reason": (
                f"no tensor is indexed by two ranks, so there are no edges to "
                f"draw; {len(singles)} rank(s) of positions"
            ),
        }

    decorated = [r for r in ranks if singles.get(r)]
    if len(decorated) >= 2:
        left, right = decorated[0], decorated[1]
        detail = (f"rank-1 tensors live on both {left} ({singles[left]}) and "
                  f"{right} ({singles[right]}), so they are different sets")
        if extents.get(left) != extents.get(right):
            detail += (f"; extents differ ({extents.get(left)} vs "
                       f"{extents.get(right)})")
        return {"view": BIPARTITE, "sides": (left, right), "reason": detail}

    only = decorated[0] if decorated else (ranks[0] if ranks else "?")
    return {
        "view": GRAPH,
        "sides": (),
        "reason": (
            f"every rank-1 tensor is over {only}, so the two ranks of a "
            f"rank-2 tensor index the same set"
        ),
    }


def bipartite_positions(left_n: int, right_n: int, left: str, right: str,
                        width: int = 520, height: int = 320) -> dict:
    """Two columns, left rank down one side and right rank down the other.

    Node ids are SIDE-QUALIFIED -- `R:0`, `C:0` -- because row 0 and column 0
    are different nodes that share an index. A flat id list cannot express
    that, and a renderer keying `positions[0]` would put a column marking on a
    row.
    """
    pos: dict[str, list[int]] = {}
    for side, count, x in ((left, left_n, 70), (right, right_n, width - 70)):
        for k in range(count):
            y = (height / 2 if count == 1
                 else 45 + (height - 90) * k / (count - 1))
            pos[f"{side}:{k}"] = [x, round(y)]
    return pos


def qualify(side: str, index: object) -> str:
    """The id a bipartite node goes by."""
    return f"{side}:{index}"


def disagreement(named: str | None, program: dict, instance: dict | None = None,
                 gen_rank: str = "I", where: str = "the spec") -> list[str]:
    """Report a declared view that contradicts the one the program implies.

    `classify` is authoritative -- it reads where the rank-1 tensors live,
    which is a fact about the program rather than an opinion about it. So the
    question is never which to use; it is whether to say anything when the two
    differ.

    SAYING SOMETHING IS FREE AND NOT SAYING IT HIDES TWO BUGS. `author.py`
    builds instance.json by merging an author's or model's styling keys over
    the derived domain and then forcing `view` to the derived value, which is
    the right outcome and a silent one. A contradiction there means either the
    model misread the algorithm or `classify` is wrong, and both are worth
    knowing: the first is a prompt problem, the second is a bug in a
    derivation that eleven other things trust.

    Returns findings, not an exception, so a caller can decide. `author.py`
    folds them into a stage; `build_page` treats them as fatal, because by
    the time it runs there is no stage left to report them to -- it is about
    to write a page whose every rank-1 marking would land on the wrong node
    set.
    """
    if not named:
        return []
    shape = classify(program, instance, gen_rank)
    if named == shape["view"]:
        return []
    return [
        f"{where} names the {named!r} view but the program implies "
        f"{shape['view']!r}: {shape['reason']}. If {named!r} is right then "
        f"domain_shape.classify is wrong and should be fixed, not overridden."
    ]
