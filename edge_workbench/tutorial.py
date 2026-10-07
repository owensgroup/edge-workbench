# -*- coding: utf-8 -*-
"""Read a tutorial's worked example, and turn it into an instance.

WHY THIS EXISTS
---------------
The instance the page ran used to be a file in this repository, written by
hand, describing a graph that appeared nowhere else. The tutorial on the
website described a *different* graph in its worked example. So the page
showed a careful walkthrough of a problem the page's own prose never
mentioned, and nothing connected the two.

This closes that. The tutorial's worked example is the instance. A visualiser
runs the example the page describes, and the answer the page publishes for it
becomes something the build can check.

THE CONTRACT
------------
A tutorial carries a `working_example_data` key in its front matter, holding
JSON:

    working_example_data: |
      {
        "vertices": 4, "source": 0, "sink": 3,
        "capacities": [[0, 1, 3], [0, 2, 2], ...],
        "expect": {"flow": 5, "generations": 4, "pushes": {...}}
      }

JSON inside a YAML block scalar, so Jekyll parses the front matter as usual
and this module needs no YAML parser -- which matters, because a clean clone
of this repository builds with `node` and Python and nothing installed.

`expect` is the part that makes this more than convenience. It is the answer
the page publishes, so checking a run against it checks the tool against the
author rather than against itself.

WHAT IS DERIVED, AND WHY
------------------------
Node positions are computed, not read. A tutorial states a graph; where to
draw it is presentation, and asking an author for pixel coordinates would put
a layout in every tutorial that wants a picture. Vertices are placed in
columns by their distance from the source, which puts the source on the left,
the sink on the right, and the flow left-to-right -- the reading most people
already have for a flow network.
"""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

KEY = "working_example_data"
MEANINGS_KEY = "einsum_meanings"


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


def read_example(tutorial: Path) -> dict:
    """The worked example a tutorial publishes, as data."""
    text = Path(tutorial).read_text()
    block = _block_scalar(text, KEY)
    if block is None:
        raise TutorialError(
            f"{tutorial} has no `{KEY}:` block, so there is no worked example "
            f"to run. Add one to the front matter:\n"
            f"    {KEY}: |\n"
            f'      {{"vertices": N, "source": s, "sink": t,\n'
            f'       "capacities": [[u, v, cap], ...],\n'
            f'       "expect": {{"flow": F}}}}'
        )
    try:
        data = json.loads(block)
    except json.JSONDecodeError as e:
        raise TutorialError(
            f"{tutorial}'s `{KEY}` block is not valid JSON: {e}"
        ) from e

    # Required fields depend on the SHAPE of the problem. A matrix example
    # has no source or sink, and demanding them would force a tutorial to
    # describe its problem as something it is not.
    required = {
        "graph": ("vertices", "source", "sink", "capacities"),
        "matrix": ("matrix",),
    }[data.get("kind", "graph")]
    for field in required:
        if field not in data:
            raise TutorialError(
                f"{tutorial}'s `{KEY}` is kind "
                f"{data.get('kind', 'graph')!r} and is missing {field!r}"
            )
    return data


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


# ----------------------------------------------------------- instance ---

def to_instance(example: dict, *, domain: dict | None = None) -> dict:
    """The instance a driver can run, from the example a tutorial publishes.

    Dispatches on the SHAPE of the problem, because different problems are
    stated differently and forcing one shape on all of them would mean
    tutorials describing a matrix as a list of edges.

      graph   (default) vertices, a source, a sink, capacities
      matrix            rows, columns and a boolean incidence matrix

    A matrix is drawn as a BIPARTITE graph -- rows on one side, columns on
    the other, an edge wherever the matrix has an entry -- which for exact
    cover is not a reinterpretation but the standard formulation: rows are
    sets, columns are elements, and a cover picks rows so every column has
    degree one.
    """
    if example.get("kind") == "matrix":
        return _matrix_instance(example, domain=domain)
    n = int(example["vertices"])
    source = int(example["source"])
    sink = int(example["sink"])
    edges = [(int(u), int(v), int(c)) for u, v, c in example["capacities"]]

    cap = {f"{u},{v}": c for u, v, c in edges}
    instance: dict[str, Any] = {
        "extent": {"U": n, "V": n},
        "scalars": {"VertexCount": n},
        "tensors": {
            # G is the adjacency the cascade never reads -- C carries the
            # capacities -- but the IR declares it as an input, and an input
            # present on one side only reads as a disagreement about the
            # algorithm when it is a disagreement about setup.
            "G": {k: 1 for k in cap},
            "C": cap,
            "S": {str(source): True},
            "T": {str(sink): True},
        },
        "domain": {
            "view": "graph",
            "graph": {
                "nodes": list(range(n)),
                "edges": [{"u": u, "v": v, "cap": c} for u, v, c in edges],
                "source": source,
                "sink": sink,
            },
            "positions": layer_positions(n, edges, source, sink),
        },
    }
    if domain:
        instance["domain"].update(domain)
    return instance


def read_meanings(tutorial: Path) -> dict[str, str]:
    """label -> what that Einsum means for the problem, from the tutorial.

    The author's half of each explanation. The other half -- what the Einsum
    does over its iteration space -- is generated from the IR by
    `edge_workbench/render/action_prose.py`, because the program already says
    it and restating it by hand is how a restatement drifts.

    Returns {} when the tutorial has no such block, so a tutorial that has not
    been migrated still builds a page; the coverage gate is what turns the
    absence into a failure.
    """
    block = _block_scalar(Path(tutorial).read_text(), MEANINGS_KEY)
    if block is None:
        return {}
    try:
        data = json.loads(block)
    except json.JSONDecodeError as e:
        raise TutorialError(
            f"{tutorial}'s `{MEANINGS_KEY}` block is not valid JSON: {e}"
        ) from e
    return {k: v for k, v in data.items() if not k.startswith("_")}


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


def _matrix_instance(example: dict, *, domain: dict | None = None) -> dict:
    """A rows-by-columns instance, drawn as a bipartite graph.

    Node ids are side-qualified (`R:0`, `C:0`) because row 0 and column 0 are
    different nodes that share an index; the tensor itself is still keyed by
    the bare pair, `"0,2"`, the way every rank-2 tensor is.
    """
    from edge_workbench import domain_shape

    matrix = example["matrix"]
    rows = int(example.get("rows", len(matrix)))
    cols = int(example.get("columns", len(matrix[0]) if matrix else 0))
    row_rank = example.get("rowRank", "R")
    col_rank = example.get("colRank", "C")
    tensor = example.get("tensor", "A")

    cells = {
        f"{r},{c}": True
        for r, line in enumerate(matrix)
        for c, v in enumerate(line)
        if v
    }
    edges = [
        {"u": domain_shape.qualify(row_rank, k.split(",")[0]),
         "v": domain_shape.qualify(col_rank, k.split(",")[1])}
        for k in cells
    ]
    nodes = ([domain_shape.qualify(row_rank, r) for r in range(rows)]
             + [domain_shape.qualify(col_rank, c) for c in range(cols)])

    instance: dict[str, Any] = {
        "extent": {row_rank: rows, col_rank: cols},
        "scalars": dict(example.get("scalars", {})),
        "tensors": {tensor: cells},
        "domain": {
            "view": domain_shape.BIPARTITE,
            "graph": {
                "nodes": nodes,
                "edges": edges,
                "sides": {"left": row_rank, "right": col_rank},
            },
            "positions": domain_shape.bipartite_positions(
                rows, cols, row_rank, col_rank),
        },
    }
    if domain:
        instance["domain"].update(domain)
        instance["domain"]["view"] = domain_shape.BIPARTITE
    return instance
