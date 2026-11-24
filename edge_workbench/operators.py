"""Operators the workbench registers on top of edge-core-ir's default registry.

edge-core-ir ships the operators EDGE defines. These are the workbench's own
readings, registered through the UDF registry the evaluator already takes
(`evaluate(..., functions=...)`), so edge-core-ir does not grow for them
(docs/evaluator-needs.md):

- ``select-any``: what a free populate (``1(pick-admissible-edge)``,
  ``1(pick-parent)``) runs as. The first arrival into an empty fiber is
  written and nothing displaces it, so the operator is a pure function of the
  fiber it is handed and the SCHEDULE decides which candidate wins. Under the
  sequential schedule a run is reproducible; the answer check also runs
  shuffled schedules, and every one must give the same answer.
- ``floor``: a unary, round toward minus infinity. It fixes every integer, so
  it maps an integer empty value to itself (``maps_empty_to_empty``).

An algorithm's ``*_functions.py`` starts from :func:`base_registry` and adds
its own names, e.g. an alias of ``select-any`` for its free choice.
"""

from __future__ import annotations

import math
from typing import Any

SELECT_ANY = "select-any"


def select_any(fiber: Any, red_coord: Any, red_value: Any, *, ctx: Any) -> Any:
    """Keep one coordinate, any one: the first arrival wins."""
    from edge_ir.evaluator.context import PopulateAction

    del red_value, ctx
    if any(entry.present for entry in fiber):
        # Something is held already: keep exactly it, touch nothing else.
        return [(entry.coord, PopulateAction.NONE) for entry in fiber]
    actions = [(entry.coord, PopulateAction.WRITE if entry.coord == red_coord
                else PopulateAction.NONE) for entry in fiber]
    # An assignment-style fiber may not enumerate the incoming coordinate.
    if all(coord != red_coord for coord, _ in actions):
        actions.append((red_coord, PopulateAction.WRITE))
    return actions


def floor(value: Any) -> Any:
    return math.floor(value)


def base_registry():
    """edge-core-ir's default registry plus ``select-any`` and ``floor``."""
    import edge_ir.evaluator  # noqa: F401  (must precede edge_ir.udf)
    from edge_ir.udf import UdfCategory, default_registry

    registry = default_registry()
    for name in (SELECT_ANY, "select_any"):
        if not registry.has(UdfCategory.COORDINATE, name):
            registry.register_python(
                name, UdfCategory.COORDINATE, select_any, arity=3,
                wants_context=True,
                doc="keep one coordinate, any one; the schedule decides which")
    if not registry.has(UdfCategory.UNARY, "floor"):
        registry.register_python(
            "floor", UdfCategory.UNARY, floor, arity=1,
            maps_empty_to_empty=True, doc="round toward minus infinity")
    return registry


def alias(registry, name: str, existing: str = SELECT_ANY, doc: str = ""):
    """Register ``name`` as another name for the coordinate operator
    ``existing`` (default ``select-any``), and return the registry."""
    from edge_ir.udf import UdfCategory, UdfDecl

    decl = registry.decl(UdfCategory.COORDINATE, existing)
    registry.register(
        UdfDecl(name=name, category=UdfCategory.COORDINATE, arity=decl.arity,
                wants_context=decl.wants_context,
                doc=doc or f"alias of {existing}"),
        registry.impl(UdfCategory.COORDINATE, existing))
    return registry
