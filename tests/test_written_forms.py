"""The page shows each Einsum as the author wrote it, not as the IR lowers it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import tutorial_vs_edge as tve  # noqa: E402
from edge_workbench.spec_surface import parse_edge_file  # noqa: E402

EXAMPLES = {"maximum-flow": "maximum-flow.md", "set-cover": "set_cover.md",
            "bellman-ford": "bellman-ford.md",
            "direction-optimizing-bfs": "direction-optimizing-bfs.md"}


def _written(name):
    d = ROOT / "examples" / name
    return tve.written_forms(d / EXAMPLES[name], d / "einsum.edge")


@pytest.mark.parametrize("name", EXAMPLES)
def test_every_einsum_has_its_written_form(name):
    labels = set(parse_edge_file(ROOT / "examples" / name / "einsum.edge"))
    written = _written(name)
    assert labels <= set(written)
    assert written["init"] and written["stop"]


def test_a_function_stays_a_function_and_its_definition_is_kept():
    written = _written("set-cover")
    assert r"\sigma(d^\ast_i + 1, r)" in written["E19"]
    assert len(written["definitions"]) == 1
    assert written["definitions"][0].startswith(r"\sigma(")


def test_alignment_marks_are_gone_but_a_cases_block_keeps_its_own():
    written = _written("maximum-flow")
    assert "&" not in written["E05"]
    assert r"\begin{cases}" in written["E04"] and "&" in written["E04"]


def test_what_the_ir_dropped_is_back():
    written = _written("bellman-ford")
    assert r"\bigwedge_s" in written["E01"]
    assert "root" in written["init"]


def test_a_shape_is_read_as_a_shape_not_an_invented_input():
    """|R| is the tutorial's symbol. No RowCount tensor stands in for it."""
    import json
    spec = ROOT / "examples" / "set-cover" / "workbench" / "spec"
    program = json.loads((spec / "set_cover_program.json").read_text())
    assert "RowCount" not in {d["name"] for d in program["declarations"]}
    assert '"shape_sym"' in json.dumps(program["main_edge"])


def test_set_cover_starts_from_its_input():
    written = _written("set-cover")
    assert r"\mathrm{InitS}_r" in written["init"]
    assert not [k for k in written if k.startswith("S")]
