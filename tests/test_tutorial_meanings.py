# -*- coding: utf-8 -*-
"""Meanings an author writes under each Einsum reach the page as written."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edge_workbench import author, spec_check, tutorial as tut, tutorial_vs_edge  # noqa: E402

EXAMPLE = ROOT / "examples" / "bellman-ford"

E01 = ("**Relax.** $N_{i,d} = G_{s,d} \\cdot D_{i,s} :: \\bigwedge_s +(\\cap)"
       "\\ \\bigvee_s \\min(\\cup)$.")
STOP = "**Stop.** $\\diamond : D_{i+1} \\equiv D_i$."


def _tutorial(tmp_path: Path, *notes: tuple[str, str]) -> Path:
    """Bellman-Ford with paragraphs added after the walkthrough's formulas."""
    shutil.copytree(EXAMPLE, tmp_path / "bellman-ford")
    md = tmp_path / "bellman-ford" / "bellman-ford.md"
    text = re.sub(r"\n  \*\*(Graph|Einsum) meaning:\*\*.*?\n(?=\n|\S)", "\n",
                  md.read_text(), flags=re.DOTALL)
    for after, note in notes:
        assert after in text
        i = text.index(after)
        end = min(text.index(mark, i) for mark in ("\n\n", "\nedge_expression:"))
        text = text[:end] + "\n\n" + note + text[end:]
    md.write_text(text)
    return md


def _read(md: Path) -> dict:
    return tutorial_vs_edge.authored_meanings(md, md.parent / "einsum.edge")


def test_a_pair_lands_on_the_einsum_above_it(tmp_path):
    md = _tutorial(tmp_path, (E01, (
        "  **Graph meaning:** \"Try relaxing every edge into $d$, and keep the\n"
        "  minimum candidate distance.\"\n\n"
        "  **Einsum meaning:** For each destination $d$, take the minimum\n"
        "  over all $s$.\n\n"
        "  **On Map:** this paragraph is not a meaning.")))
    assert _read(md) == {"E01": {
        "graph": "Try relaxing every edge into $d$, and keep the minimum "
                 "candidate distance.",
        "einsum": "For each destination $d$, take the minimum over all $s$."}}


def test_the_stop_line_can_be_explained(tmp_path):
    md = _tutorial(tmp_path, (STOP, "  Graph meaning: No edge improves any distance."))
    assert _read(md) == {"stop": {"graph": "No edge improves any distance."}}


def test_a_tutorial_without_them_reads_as_empty(tmp_path):
    assert _read(_tutorial(tmp_path)) == {}


def test_the_bellman_ford_tutorial_explains_every_einsum():
    assert sorted(_read(EXAMPLE / "bellman-ford.md")) == ["E01", "E02", "E03", "E04"]


def test_a_meaning_after_no_einsum_is_refused(tmp_path):
    md = _tutorial(tmp_path, ("status_intro: |",
                              "  placeholder"))
    text = md.read_text().replace(
        "edge_expression_walkthrough: |\n",
        "edge_expression_walkthrough: |\n  Graph meaning: lost.\n\n", 1)
    md.write_text(text)
    with pytest.raises(tut.TutorialError, match="cannot be placed"):
        _read(md)


def test_explaining_an_einsum_twice_is_refused(tmp_path):
    md = _tutorial(tmp_path, (E01, ("  Graph meaning: one.\n\n"
                                    "  Again, $" + E01.split("$")[1] + "$\n\n"
                                    "  Graph meaning: two.")))
    with pytest.raises(tut.TutorialError, match="twice"):
        _read(md)


def _page_steps(path: Path) -> dict:
    text = path.read_text()
    data = text[text.index("{", text.index("const T={")):]
    steps = json.JSONDecoder().raw_decode(data)[0]["steps"]
    return {s["einsum"]: s for s in reversed(steps)}


def test_the_page_prefers_the_tutorial_and_keeps_the_rest(tmp_path):
    if spec_check.upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    md = _tutorial(tmp_path, (E01, (
        "  **Graph meaning:** Try relaxing every edge into $d$.\n\n"
        "  **Einsum meaning:** Take the minimum over all $s$.")))
    assert author.main(["check", str(md.parent)]) == 0
    steps = _page_steps(md.parent / "index.html")
    assert steps["E01"]["graphMeaning"] == "Try relaxing every edge into $d$."
    assert steps["E01"]["einsumMeaning"] == "Take the minimum over all $s$."
    assert re.match(r"For each d of C, check", steps["E02"]["einsumMeaning"])


def test_only_the_unexplained_einsums_go_to_the_model(tmp_path):
    if spec_check.upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    md = _tutorial(tmp_path, (E01, "  **Graph meaning:** Try every edge."))
    spec = md.parent / "workbench" / "spec" / "authored.json"
    artifact = json.loads(spec.read_text())
    del artifact["meanings"]["E02"]
    spec.write_text(json.dumps(artifact))
    assert author.main(["check", str(md.parent)]) != 0
    prompt = (md.parent / "workbench" / "prompts" / "tutorial-data.txt").read_text()
    assert "meanings: nothing for E02" in prompt
