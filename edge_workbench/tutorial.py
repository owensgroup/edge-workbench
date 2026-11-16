# -*- coding: utf-8 -*-
"""Read what a tutorial's front matter states, and lay out its graph.

The author's words come from the front matter: the per-Einsum meanings under
each formula in `edge_expression_walkthrough`, and the tensor notes in
`problem_statement` (or a `tensor_notes` block). The worked example itself is
prose; the tutorial-data model step states it as an instance, quoting the
tutorial, and `check` verifies the quote.

Node positions are computed, not read: a tutorial states a graph, and where to
draw it is presentation. `layer_positions` puts vertices in columns by their
distance from the source, so the source sits on the left and the sink on the
right.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path



class TutorialError(RuntimeError):
    pass


def _block_scalar(text: str, key: str) -> str | None:
    """The body of a `key: |` block scalar, dedented.

    Hand-rolled rather than via a YAML library: the only thing needed from the
    front matter is one block, and a dependency here would have to be
    installed before this repository could build.
    """
    m = re.search(rf"^{re.escape(key)}:\s*\|\s*$", text, re.MULTILINE)
    if not m:
        return None
    lines = text[m.end():].splitlines()
    body: list[str] = []
    indent: int | None = None
    for line in lines[1:] if lines and not lines[0].strip() else lines:
        if not line.strip():
            body.append("")
            continue
        lead = len(line) - len(line.lstrip())
        if indent is None:
            indent = lead
        if lead < indent:
            break
        body.append(line[indent:])
    return "\n".join(body)


# ------------------------------------------------------------- layout ---

def layer_positions(n: int, edges: list[tuple[int, int, int]], source: int,
                    sink: int, width: int = 520, height: int = 300) -> dict:
    """Place vertices in columns by hop distance from the source.

    Derived rather than declared: a tutorial states a graph, and where to draw
    it is this tool's problem. The source lands on the left, the sink on the
    right, and everything else in between in the order the search reaches it,
    so flow reads left to right.
    """
    adj: dict[int, list[int]] = {v: [] for v in range(n)}
    for u, v, _ in edges:
        adj[u].append(v)

    depth = {source: 0}
    q = deque([source])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in depth:
                depth[v] = depth[u] + 1
                q.append(v)
    # Unreachable vertices still need somewhere to go.
    for v in range(n):
        depth.setdefault(v, max(depth.values(), default=0))
    # The sink belongs in the last column even if a short edge reaches it early.
    depth[sink] = max(depth.values())

    columns: dict[int, list[int]] = {}
    for v in sorted(depth, key=lambda x: (depth[x], x)):
        columns.setdefault(depth[v], []).append(v)

    last = max(columns)
    pos = {}
    for col, members in columns.items():
        x = 45 if last == 0 else 45 + (width - 90) * col / last
        for k, v in enumerate(members):
            y = height / 2 if len(members) == 1 else \
                55 + (height - 110) * k / (len(members) - 1)
            pos[str(v)] = [round(x), round(y)]
    return pos


WALKTHROUGH_KEY = "edge_expression_walkthrough"

#: `**Graph meaning:** ...`, with or without the bold, at the start of a line.
_MEANING = re.compile(
    r"^[ \t]*[*_]{0,2}(Graph|Einsum)\s+meaning:?[*_]{0,2}:?[ \t]*",
    re.MULTILINE | re.IGNORECASE)
_MATH = re.compile(
    r"\$\$(.+?)\$\$|\\\[(.+?)\\\]|\\\((.+?)\\\)|(?<!\$)\$([^$\n]+)\$(?!\$)",
    re.DOTALL)


def _meaning_text(text: str, start: int, stop: int) -> str:
    """One meaning: up to the paragraph's end, tidied, its quotation marks off."""
    body = re.split(r"\n[ \t]*\n", text[start:stop], maxsplit=1)[0]
    return " ".join(body.split()).strip("\"“”‘’'")


def read_walkthrough_meanings(tutorial: Path) -> list[dict]:
    """The `Graph meaning:` / `Einsum meaning:` lines the walkthrough gives.

    One entry per place they appear: `graph`, `einsum`, and `equations`, every
    formula before them, nearest first. Which Einsum that is takes einsum.edge,
    so `tutorial_vs_edge.authored_meanings` decides.
    """
    text = _block_scalar(Path(tutorial).read_text(), WALKTHROUGH_KEY) or ""
    marks = list(_MEANING.finditer(text))
    found: list[dict] = []
    floor = 0
    for i, mark in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        kind = mark.group(1).lower()
        # Two markers are a pair when nothing but the first one's paragraph
        # stands between them.
        gap = re.split(r"\n[ \t]*\n", text[marks[i - 1].end():mark.start()],
                       maxsplit=1) if i else []
        paired = bool(found) and kind not in found[-1] and (
            len(gap) < 2 or not gap[1].strip())
        if not paired:
            equations = [next(g for g in m.groups() if g is not None)
                         for m in _MATH.finditer(text, floor, mark.start())]
            found.append({"equations": equations[::-1]})
            floor = mark.end()
        found[-1][kind] = _meaning_text(text, mark.end(), stop)
    return found


#: `- $$G^{U \\equiv ...} \\to \\text{integer}$$, `empty` $$= 0$$, the graph structure.`
_TENSOR_ROW = re.compile(
    r"^\s*-\s+\$\$([A-Za-z][A-Za-z0-9_]*)\^", re.MULTILINE
)


def read_tensor_notes(tutorial: Path) -> dict[str, str]:
    """tensor -> the trailing prose the tutorial's problem statement gives it.

    The problem statement already describes every tensor it declares, in a
    uniform row: name, ranks, data type, empty value, then a sentence. That
    sentence is what the page shows when a reader hovers a grid, and it was
    being retyped into the algorithm's `meta.py`.

    Only the tensors the problem statement declares are here -- nine, for
    max-flow. The cascade intermediates are declared in `einsum.edge` with
    ranks and empty values but no prose, so their descriptions are generated
    from the program instead; see `edge_workbench/render/tensor_notes.py`.
    """
    text = Path(tutorial).read_text()
    block = _block_scalar(text, "problem_statement")
    if block is None:
        return {}

    # Count the rows that LOOK like tensor declarations, so a row this
    # parser cannot read is reported rather than skipped. Reading 3 of 9 and
    # saying nothing is how a check quietly starts checking less -- which is
    # exactly what happened when a tutorial stated its rows without empty
    # values and this returned a third of them without complaint.
    seen = len(_TENSOR_ROW.findall(block))

    notes: dict[str, str] = {}
    for raw in re.split(r"\n(?=\s*-\s+\$\$)", block):
        m = _TENSOR_ROW.match(raw)
        if not m:
            continue
        # The row is
        #   - $$NAME^{ranks} \to \text{TYPE}$$, `empty` $$= X$$, DESCRIPTION
        # and the empty value sits either inside the math (`$$= 0$$`) or just
        # after it (`$$=$$ False`). Splitting on the last `$$` is wrong,
        # because a description may contain its own math -- F's does.
        # The row is
        #   - $$NAME^{ranks} \to \text{TYPE}$$[, `empty` $$= X$$], DESCRIPTION
        # and the empty value is OPTIONAL: older tutorials state the type and
        # go straight to the description. Splitting on the last `$$` is wrong
        # either way, because a description may contain its own math -- F's
        # does.
        m2 = re.search(
            r"`empty`\s*\$\$[^$]*\$\$\s*(?:(?:False|True|[-+\w.]+)\s*)?,\s*",
            raw,
        )
        if m2:
            tail = raw[m2.end():]
        else:
            # No empty value: the description follows the type's closing $$.
            m3 = re.search(r"\\to\s*\\text\{[^}]*\}\s*\$\$\s*,\s*", raw)
            if not m3:
                continue
            tail = raw[m3.end():]
        tail = tail.replace("\n", " ").strip()
        tail = re.sub(r"\s+", " ", tail).rstrip(".").strip()
        if tail:
            notes[m.group(1)] = tail

    if len(notes) < seen:
        missed = seen - len(notes)
        raise TutorialError(
            f"{tutorial}: the problem statement has {seen} tensor rows but "
            f"{missed} could not be read. The row format has probably changed;"
            f" reading the rest and saying nothing would hide it.\n"
            f"  parsed: {sorted(notes)}"
        )
    return notes


def read_all_tensor_notes(tutorial: Path) -> dict[str, str]:
    """Every tensor description the tutorial gives, from both of its sources.

    `problem_statement` describes the tensors the PROBLEM has -- the author
    writes those for a reader, in prose, and they are already there.
    `tensor_notes` describes the cascade intermediates, which the problem
    statement does not mention because they are not part of the problem.

    Two sources rather than one because the two are genuinely different kinds
    of thing, and merging them into the tutorial's prose would put
    implementation detail in a problem statement.
    """
    notes = read_tensor_notes(tutorial)
    block = _block_scalar(Path(tutorial).read_text(), "tensor_notes")
    if block:
        try:
            extra = json.loads(block)
        except json.JSONDecodeError as e:
            raise TutorialError(
                f"{tutorial}'s `tensor_notes` block is not valid JSON: {e}"
            ) from e
        notes.update({k: v for k, v in extra.items()
                      if not k.startswith("_")})
    return notes
