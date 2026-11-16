"""The one operator this cascade names that the default registry lacks.

E04 `NewParent_{i,s*,d} = ParentCand_{i,s,d} :: <<<_{s*} 1(pick-parent)`:
the pseudocode (CLRS 22.2) takes as parent whichever neighbour one level up
the queue reaches first, which depends on adjacency order, so the choice is
free. `pick-parent` is therefore `select-any`.
"""

from __future__ import annotations

import edge_ir.evaluator  # noqa: F401  (must precede edge_ir.udf)
from edge_ir.udf import FunctionRegistry, UdfCategory, UdfDecl, default_registry


def bfs_from_name_registry() -> FunctionRegistry:
    registry = default_registry()
    decl = registry.decl(UdfCategory.COORDINATE, "select-any")
    registry.register(
        UdfDecl(name="pick-parent", category=UdfCategory.COORDINATE,
                arity=decl.arity, wants_context=decl.wants_context,
                doc="E04: any candidate parent; alias of select-any."),
        registry.impl(UdfCategory.COORDINATE, "select-any"),
    )
    return registry
