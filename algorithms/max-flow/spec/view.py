# -*- coding: utf-8 -*-
"""How max-flow is presented: the domain view, and phrasing worth the words.

Everything here is OPTIONAL. Delete this file and the page still builds —
`edge_workbench/render/annotate.py` derives a highlight and a caption from
what each step changed, for any algorithm, knowing nothing about flow. This
module exists only where the generic answer is worse than a specific one:
"delta  1,2 = 4" is true and dull; "push 4 along 1 → 2" is what the reader is
actually looking at.

Nothing in here may affect the numbers. It reads state and returns strings.
"""

from __future__ import annotations

#: Which renderer in the page's DOMAIN_VIEWS draws the left-hand pane.
DOMAIN_VIEW = "flow-graph"

#: Source and sink, for the pieces of phrasing that need to name them. Read
#: from the instance rather than hard-coded, so a second instance works.
SOURCE, SINK = 0, 5


def graph(instance: dict) -> dict:
    """The picture the domain view draws, from the instance."""
    return instance["domain"]["graph"]


def headline(final_state: dict) -> dict:
    """The number the page puts in the corner when the run finishes.

    Net flow out of the source. Computed from the final state rather than
    carried through from a reference implementation, so it is a fact about
    the run being shown.
    """
    flow = final_state.get("F", {}) or {}
    value = sum(v for c, v in flow.items()
                if int(c.split(",")[0]) == SOURCE)
    return {"maxFlow": value}


def caption(label: str, step: dict, prev: dict | None, changed: dict):
    """Phrasing for the handful of steps where the generic one reads badly.

    Returning None means "use the generic caption", which is the answer for
    most steps: the Einsum's own meaning is already on screen, so restating
    it per step adds nothing.
    """
    state = step["state"]

    if label == "E11":                                    # delta: the pushes
        if not changed:
            return "nothing to push"
        return "; ".join(
            f"push {_n(v)} along {c.replace(',', ' → ')}"
            for c, v in sorted(changed.items()))

    if label == "E24":                                    # D: the relabels
        if not changed:
            return "no relabel"
        return "; ".join(f"h({c}) → {_n(v)}" for c, v in sorted(changed.items()))

    if label == "E06":                                    # Act
        active = sorted(int(c) for c in state.get("Act", {}))
        return (f"active vertices (internal, holding excess): {active}"
                if active else "no vertex is active — the flow is maximum")

    if label == "E10":                                    # the selector
        chosen = sorted(state.get("PushCand", {}))
        return ("one admissible edge chosen per vertex: "
                + ", ".join(c.replace(",", " → ") for c in chosen)
                if chosen else "no admissible edge to choose from")

    if label == "stop":
        return "no vertex is holding excess any more, so the flow is maximum"

    return None


def highlight(label: str, step: dict, prev: dict | None, changed: dict):
    """Returning None means "highlight whatever changed", which is usually right.

    The one case worth overriding is the stopping condition: nothing changed,
    so the generic highlight is empty, and an empty highlight on the last step
    reads as though the page broke.
    """
    if label == "stop":
        return {"nodes": [SINK], "edges": []}
    return None


def rounds(trace: dict) -> dict:
    """Per-round highlights for compare mode.

    Compare mode shows the state at the END of a round, so one step's
    highlight is the wrong thing: the last step of a round is E24, which marks
    relabelled vertices and no edges, so pushes would never show. A
    bulk-synchronous round happened all at once, so its highlight is
    everything the round touched.
    """
    out: dict = {}
    for step in trace["steps"]:
        r = step.get("iteration")
        if r is None:
            continue
        entry = out.setdefault(r, {"nodes": [], "edges": []})
        if step["einsum"] == "E11":
            for c in step["state"].get("delta", {}):
                u, v = c.split(",")
                entry["edges"].append([int(u), int(v)])
        if step["einsum"] == "E23":
            for c in step["state"].get("NewD", {}):
                entry["nodes"].append(int(c))
    return out


def operations(step: dict) -> tuple:
    """(opKind, concurrency) for compare mode, or (None, 0).

    An operation is a vertex actually doing something this round, which is
    what the sequential side counts too.
    """
    if step["einsum"] == "E10":
        return "push", len(step["state"].get("PushCand", {}))
    if step["einsum"] == "E20":
        return "relabel", len(step["state"].get("Rel", {}))
    return None, 0


def _n(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v
