"""`pick-parent` is select-any: the spec writes 1(pick-parent) with no ranking,
and any parent in the frontier makes a valid BFS tree."""

from __future__ import annotations

from edge_workbench.operators import alias, base_registry


def direction_optimizing_bfs_registry():
    return alias(base_registry(), "pick-parent",
                 doc="E07, E16 coordinate op: keep one parent per child, any one.")
