# -*- coding: utf-8 -*-
"""A description for every tensor, from whichever source actually knows one.

The page shows a line about each tensor beside its grid. There were twenty-two
of them hand-written in the algorithm's `meta.py`, and they split cleanly in
two:

  THE TENSORS THE TUTORIAL DECLARES -- nine, for max-flow. The problem
  statement already describes each one in a uniform row, and that sentence is
  the author's. Read from the tutorial, not retyped.

  THE CASCADE INTERMEDIATES -- thirteen. `einsum.edge` declares them with
  ranks, data type and empty value, but gives them no prose at all, and the
  tutorial's problem statement does not mention them. So there is nothing to
  read; there is something to DERIVE. For an intermediate, what a reader
  actually wants to know is where it comes from and where it goes, and the
  program says exactly that: which Einsum writes it, which read it.

Deriving the second group is not a substitute for prose an author might write
-- it is better than the nothing that was there, and it cannot go stale.
"""

from __future__ import annotations

from typing import Any


def _projections(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("kind") == "input" and "proj" in node:
            out.append(node["proj"])
        for value in node.values():
            _projections(value, out)
    elif isinstance(node, list):
        for value in node:
            _projections(value, out)


def _type_phrase(decl: dict) -> str:
    name = (decl.get("data_type") or {}).get("name", "")
    empty = decl.get("empty_value")
    if isinstance(empty, bool):
        empty_text = str(empty).lower()
    elif isinstance(empty, str):
        empty_text = "+∞" if empty.lower() in ("inf", "infinity") else empty
    else:
        empty_text = str(empty)
    kind = {"bool": "Boolean", "int": "integer"}.get(name, name or "value")
    return f"{kind}, empty {empty_text}"


def derive(program: dict, cascade: dict, alias: dict | None = None) -> dict:
    """tensor -> where it comes from and where it goes, from the program."""
    alias = alias or cascade.get("displayNames", {})
    labels = cascade.get("labels", {})
    nodes = program["main_edge"]["cascade"]["einsums"]

    owner: dict[int, str] = {}
    for label, idx in labels.items():
        for i in (idx if isinstance(idx, list) else [idx]):
            owner[i] = label

    written: dict[str, list[str]] = {}
    read: dict[str, list[str]] = {}
    for i, einsum in enumerate(nodes):
        label = owner.get(i, f"node {i}")
        out = alias.get(einsum["output_tensor"], einsum["output_tensor"])
        if label not in written.setdefault(out, []):
            written[out].append(label)
        projections: list[dict] = []
        _projections(einsum["expression"], projections)
        for proj in projections:
            name = alias.get(proj["tensor"], proj["tensor"])
            if label not in read.setdefault(name, []):
                read[name].append(label)

    init = program.get("initialization", {}).get("einsums", [])
    init_label = cascade.get("initLabel", "init")
    for einsum in init:
        out = alias.get(einsum["output_tensor"], einsum["output_tensor"])
        if init_label not in written.setdefault(out, []):
            written[out].insert(0, init_label)

    declarations = {
        alias.get(d["name"], d["name"]): d
        for d in program.get("declarations", [])
    }

    notes: dict[str, str] = {}
    for name, decl in declarations.items():
        if not decl.get("ranks"):
            continue                      # a scalar literal, nothing to show
        produced = written.get(name, [])
        consumed = read.get(name, [])
        bits = [_type_phrase(decl)]
        if produced:
            bits.append("written by " + ", ".join(produced))
        else:
            bits.append("an input: the instance supplies it")
        if consumed:
            bits.append("read by " + ", ".join(consumed))
        else:
            bits.append("read by nothing in the cascade")
        notes[name] = "; ".join(bits)
    return notes


def combine(program: dict, cascade: dict, authored: dict,
            alias: dict | None = None) -> dict:
    """The author's sentence where there is one, the derived line otherwise.

    An authored description says what a tensor is FOR, which nothing can
    derive. A derived one says where it comes from and goes, which no one
    should have to type. Where both exist the author's leads and the derived
    line follows it, because the provenance is still worth having.
    """
    alias = alias or cascade.get("displayNames", {})
    derived = derive(program, cascade, alias)
    out: dict[str, str] = {}
    for name, line in derived.items():
        note = (authored.get(name) or "").strip().rstrip(".")
        out[name] = f"«{name}»  {note}. {line}." if note else \
            f"«{name}»  {line}."
    return out
