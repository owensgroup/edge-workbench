# -*- coding: utf-8 -*-
"""Turn a driven trace into a trace a page can render.

The driver produces semantics: which Einsum, which generation, which tensor it
wrote, and the state afterwards. A page needs three more things per step —
a caption, a highlight for the domain view, and the LaTeX of the Einsum — and
none of those are consequences of the spec. They are how the algorithm is
*presented*.

Before this existed they came from a hand-written implementation of each
algorithm, which is precisely what stopped any of this generalising. So they
come from three places now, in order of how much they have to know:

    meta.py       per-Einsum, static: LaTeX, what it means on the graph
    generic       per-step, derived: WHAT CHANGED, which is the highlight and
                  a serviceable caption for any algorithm at all
    view.py       per-step, optional: nicer phrasing for the few Einsums where
                  "delta 1,2 = 4" is worse than "push 4 along 1 -> 2"

An algorithm that supplies no view module still gets a working page. That is
the point: the generic path has to be good enough to stand alone, or the
first tutorial someone uploads will not render.
"""

from __future__ import annotations

from typing import Any


def changed_cells(state: dict, prev: dict, tensor: str) -> dict:
    """Cells of `tensor` this step wrote, against the step before it."""
    now = (state or {}).get(tensor, {}) or {}
    was = (prev or {}).get(tensor, {}) or {}
    out = {}
    for coord, value in now.items():
        if was.get(coord) != value:
            out[coord] = value
    return out


def generic_highlight(changed: dict) -> dict:
    """What changed, as nodes and edges.

    A rank-1 coordinate is a vertex and a rank-2 coordinate is an edge, so the
    cells a step wrote map straight onto the picture with no knowledge of the
    algorithm. This reproduces the hand-written highlights on every step that
    had one and adds them on steps that did not.
    """
    nodes, edges = [], []
    for coord in changed:
        if coord == "":
            continue          # a rank-0 tensor (a flag, a depth): no place to light
        parts = coord.split(",")
        if len(parts) == 1:
            nodes.append(int(parts[0]))
        elif len(parts) == 2:
            edges.append([int(parts[0]), int(parts[1])])
    return {"nodes": nodes, "edges": edges}


def generic_caption(tensor: str, changed: dict, limit: int = 6) -> str:
    """What changed, as prose. Honest rather than fluent.

    Deliberately says the tensor and the cells rather than inventing a verb:
    "delta 1,2 = 4" is true of any algorithm, where "push 4" is true of one.
    An algorithm that wants the verb supplies it in its view module.
    """
    if not changed:
        return ""
    items = list(changed.items())[:limit]
    body = "; ".join(f"{c} = {_fmt(v)}" for c, v in items)
    more = "" if len(changed) <= limit else f" (+{len(changed) - limit} more)"
    return f"{tensor}  {body}{more}"


def _fmt(v: Any) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def annotate(trace: dict, meta: Any, view: Any = None,
             latex: dict | None = None) -> dict:
    """Add caption, highlight and display metadata to every step, in place.

    `latex` is label -> formula, rendered from the IR by
    `edge_workbench.render.latex`. It is passed in rather than read off the
    algorithm's `meta` module because a formula that a human types next to a
    program is a formula that can contradict it.
    """
    steps = trace["steps"]
    prev = None
    for step in steps:
        label = step["einsum"]
        out = step.get("output")
        changed = changed_cells(step["state"], prev, out) if out else {}

        step["latex"] = (latex or {}).get(label, "")
        graph_meaning, einsum_meaning = (
            getattr(meta, "MEANING", {}).get(label) or ("", ""))
        step["graphMeaning"] = graph_meaning
        step["einsumMeaning"] = einsum_meaning

        caption = None
        highlight = None
        if view is not None:
            if hasattr(view, "caption"):
                caption = view.caption(label, step, prev, changed)
            if hasattr(view, "highlight"):
                highlight = view.highlight(label, step, prev, changed)

        step["caption"] = (
            caption if caption is not None
            else generic_caption(out, changed) if out else "")
        step["graphHighlight"] = (
            highlight if highlight is not None else generic_highlight(changed))
        # `expr` is what the page falls back to when MathJax has not loaded.
        step["expr"] = step["latex"] or label
        prev = step["state"]
    return trace
