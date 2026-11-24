"""Occupancy ||T|| is allowed only in a stopping condition (Toluwa, 2026-11-19)."""
from pathlib import Path

from edge_workbench.tutorial_vs_edge import occupancy_outside_stopping, read_edge

EDGE = """- Tensors
F^{I, S} -> Boolean, empty = False
Done^{I} -> Boolean, empty = False
- Cascade
# E01: next frontier
F_{i+1, s} = F_{i, s} . F_{i, s} :: /\\ AND(∩)
# E02: frontier empty
Done_{i+1} = ||F_{i+1}|| == 0
<> : ||F_{i+1}|| == 0
"""


def test_an_einsum_using_occupancy_is_reported(tmp_path: Path) -> None:
    edge = tmp_path / "einsum.edge"
    edge.write_text(EDGE)
    found = occupancy_outside_stopping(read_edge(edge))
    assert len(found) == 1
    assert found[0].startswith("E02:")
    assert "only in a stopping condition" in found[0]


def test_occupancy_in_the_stopping_condition_is_fine(tmp_path: Path) -> None:
    edge = tmp_path / "einsum.edge"
    edge.write_text(EDGE.replace("Done_{i+1} = ||F_{i+1}|| == 0",
                                 "Done_{i+1} = F_{i+1, s} :: \\/_s OR(∪)"))
    assert occupancy_outside_stopping(read_edge(edge)) == []
