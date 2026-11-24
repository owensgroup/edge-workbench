"""The one operator this cascade names that the default registry lacks.

E04 `NewParent_{i,s*,d} = ParentCand_{i,s,d} :: <<<_{s*} 1(pick-parent)`:
the pseudocode (CLRS 22.2) takes as parent whichever neighbour one level up
the queue reaches first, which depends on adjacency order, so the choice is
free. `pick-parent` is therefore `select-any`.
"""

from __future__ import annotations

from edge_workbench.operators import alias, base_registry


def bfs_from_name_registry():
    return alias(base_registry(), "pick-parent",
                 doc="E04: any candidate parent; alias of select-any.")
