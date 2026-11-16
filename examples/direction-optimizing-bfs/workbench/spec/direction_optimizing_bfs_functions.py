"""`pick-parent` is select-any: the spec writes 1(pick-parent) with no ranking,
and any parent in the frontier makes a valid BFS tree."""

from __future__ import annotations

import edge_ir.evaluator  # noqa: F401  (must precede edge_ir.udf)
from edge_ir.udf import FunctionRegistry, UdfCategory, UdfDecl, default_registry


def direction_optimizing_bfs_registry() -> FunctionRegistry:
    registry = default_registry()
    decl = registry.decl(UdfCategory.COORDINATE, "select-any")
    registry.register(
        UdfDecl(name="pick-parent", category=UdfCategory.COORDINATE,
                arity=decl.arity, wants_context=decl.wants_context,
                doc="E06 coordinate op: keep one parent per child, any one."),
        registry.impl(UdfCategory.COORDINATE, "select-any"),
    )
    return registry
