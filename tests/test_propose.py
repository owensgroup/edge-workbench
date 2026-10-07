"""The model-assisted half, and the one check on it that cannot be argued with.

`prepare` reads what a tutorial states. `propose` asks a model for the rest.
That second half is where this repository's whole premise is at risk: a model
writing about max-flow can produce six fluent paragraphs about push-relabel
without reading the tutorial at all, and every one of them will look right to
a reviewer who also knows push-relabel.

The defence is the citation. Each model-written meaning carries a span the
model claims to have copied from the tutorial, and `review.check_quotes`
verifies the span is really there by string comparison. These tests are about
that check -- above all, that it FAILS when it should, because a citation
check that accepts anything is worse than none: it manufactures confidence.

What is deliberately NOT tested, because it cannot be: whether a quotation
supports the meaning beside it. A model can cite a real sentence and write
something unrelated. That is a reviewer's job, and putting the quotation next
to the prose is what makes that job quick.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import prepare, propose, review  # noqa: E402

TUTORIAL = """\
# Exact cover

**Choose.** A row enters the partial solution when it is the first row
covering the least-covered column.

**Reduce.** Choosing a row deletes every column it covers, and every other
row meeting those columns.
"""


@pytest.fixture
def tutorial(tmp_path) -> Path:
    md = tmp_path / "set_cover.md"
    md.write_text(TUTORIAL)
    return md


@pytest.fixture
def artifact() -> dict:
    return {
        "source": {"tutorial": "set_cover.md", "dirty": False},
        "provenance": {},
        "example": None,
        "meanings": {},
        "tensorNotes": {},
        "gaps": ["meanings: no `einsum_meanings` block.",
                 "example: no `working_example_data` block."],
    }


################################################################################
# the request
################################################################################


def test_the_prompt_carries_the_tutorial_and_the_gaps(tutorial, artifact):
    """A request that omits either asks the model to guess.

    The gaps are the point: without them the model decides for itself what is
    missing, and it will fill things the author already wrote.
    """
    prompt = propose.build_prompt(tutorial, artifact)
    assert "least-covered column" in prompt, "the tutorial is not in the request"
    for gap in artifact["gaps"]:
        assert gap in prompt, f"the request never mentions the gap {gap!r}"
    assert "verbatim" in prompt.lower(), (
        "the request must state the citation rule, or the answer will not "
        "carry citations and every meaning will fail review"
    )


################################################################################
# the answer
################################################################################


def test_applying_an_answer_records_that_a_model_wrote_it(tutorial, artifact):
    """Provenance is not bookkeeping -- it changes how the prose is read.

    A reviewer who knows `meanings` came from a model reads every sentence.
    A reviewer told nothing reads them like the author's and skims.
    """
    merged = propose.apply(artifact, {
        "meanings": {"E01": {"text": "Pick the most constrained column.",
                             "quote": "the first row covering the least-covered column"}},
    }, tutorial)

    assert merged["provenance"]["meanings"] == review.MODEL
    assert merged["meanings"]["E01"] == "Pick the most constrained column."
    assert merged["quotes"]["E01"], "the citation was dropped on merge"


def test_the_author_s_own_fields_are_not_relabelled(tutorial, artifact):
    """Filling one gap must not claim authorship of everything else."""
    artifact["tensorNotes"] = {"Matrix": "the incidence matrix"}
    artifact["provenance"]["tensorNotes"] = review.AUTHOR

    merged = propose.apply(artifact, {
        "meanings": {"E01": {"text": "x" * 20, "quote": "a" * 20}},
    }, tutorial)
    assert merged["provenance"]["tensorNotes"] == review.AUTHOR


def test_filling_a_gap_removes_it(tutorial, artifact):
    """Otherwise `review` reports gaps forever and the gate never opens."""
    merged = propose.apply(artifact, {
        "meanings": {"E01": {"text": "x" * 20}},
        "example": {"kind": "matrix", "matrix": [[1]]},
    }, tutorial)
    assert merged["gaps"] == []


################################################################################
# the citation check -- it must FAIL
################################################################################


def _with_quote(quote: str) -> dict:
    return {
        "provenance": {"meanings": review.MODEL},
        "meanings": {"E01": "Pick the most constrained column."},
        "quotes": {"E01": quote},
    }


def test_a_real_quotation_passes_even_re_wrapped(tutorial):
    """A model will not reproduce the markdown's line breaks.

    Rejecting a true citation over a newline would teach an author to delete
    the check rather than fix anything, so whitespace is collapsed first.
    """
    findings = review.check_quotes(
        _with_quote("the first row covering\n   the LEAST-covered column"),
        tutorial)
    assert not findings, review.report(findings)


def test_an_invented_quotation_is_caught(tutorial):
    """The failure this whole mechanism exists for.

    This sentence is entirely plausible about exact cover, and is not in the
    tutorial. A model that wrote from what it knows rather than from what it
    read produces exactly this.
    """
    findings = review.check_quotes(
        _with_quote("choose the column with the fewest ones to minimise "
                    "branching"),
        tutorial)
    assert findings, (
        "an invented citation passed. The citation check is the only "
        "judgement-free check here; if it accepts anything, it manufactures "
        "confidence rather than providing it."
    )
    assert "NOT in the tutorial" in str(findings[0])


def test_a_reworded_quotation_is_caught(tutorial):
    """Verbatim means verbatim.

    A paraphrase cannot be checked -- and a model that paraphrases its own
    citation is doing the thing the citation was meant to detect, one step
    further back.
    """
    findings = review.check_quotes(
        _with_quote("a row covering the least covered column is chosen first"),
        tutorial)
    assert findings


def test_a_meaning_citing_nothing_is_caught(tutorial):
    findings = review.check_quotes({
        "provenance": {"meanings": review.MODEL},
        "meanings": {"E01": "Pick the most constrained column.",
                     "E02": "Delete the covered columns."},
        "quotes": {"E01": "the first row covering the least-covered column"},
    }, tutorial)
    assert any("cite nothing" in str(f) for f in findings)
    assert any("E02" in str(f) for f in findings)


def test_an_ambiguous_quotation_is_not_a_citation(tutorial):
    """A citation must identify ONE passage, and "a row" identifies several.

    This was a minimum length, which is the wrong test in both directions: it
    rejected E02's "extracts the depth" -- eighteen characters, and the only
    occurrence in the whole tutorial -- while a long enough boilerplate phrase
    would have passed. Occurring exactly once is the property that was wanted.
    """
    findings = review.check_quotes(_with_quote("a row"), tutorial)
    assert findings
    assert "appears 2 times" in str(findings[0])


def test_a_short_but_unique_quotation_is_accepted(tutorial):
    """The case the length rule got wrong. Short is not the same as vague."""
    assert not review.check_quotes(_with_quote("deletes every column"), tutorial)


def test_the_author_s_own_meanings_are_not_asked_for_citations(tutorial):
    """The author wrote the tutorial. Making them quote it is nonsense."""
    assert not review.check_quotes({
        "provenance": {"meanings": review.AUTHOR},
        "meanings": {"E01": "anything at all"},
    }, tutorial)


################################################################################
# citation order -- the check that actually catches misattribution
################################################################################


def test_citations_in_cascade_order_are_not_flagged(tutorial):
    """The clean case. A check that fires on correct input is worse than none."""
    assert not review.check_citation_order({"quotes": {
        "E01": "A row enters the partial solution when it is the first row",
        "E02": "Choosing a row deletes every column it covers",
    }}, tutorial, ["E01", "E02"])


def test_two_meanings_attached_to_each_other_s_einsum_are_caught(tutorial):
    """The dominant failure of splitting a phase-grouped walkthrough.

    The relevance check in `review` catches this 0 times out of 276 on
    max-flow's real meanings, because good prose names no tensors. Citation
    order catches all 276 -- by arithmetic on character offsets, understanding
    nothing.
    """
    findings = review.check_citation_order({"quotes": {
        "E01": "Choosing a row deletes every column it covers",
        "E02": "A row enters the partial solution when it is the first row",
    }}, tutorial, ["E01", "E02"])
    assert findings, (
        "a swapped pair passed. This is the check that exists specifically "
        "for misattribution; if it misses, nothing catches it."
    )
    assert "read them as a pair" in str(findings[0])


def test_order_is_not_checked_when_there_is_nothing_to_order(tutorial):
    """One citation cannot be out of order, and must not read as clean-and-checked."""
    assert not review.check_citation_order(
        {"quotes": {"E01": "Choosing a row deletes every column it covers"}},
        tutorial, ["E01"])


def test_an_unverifiable_citation_is_reported_not_assumed_good(artifact):
    """No tutorial to check against means the check did not run.

    Silently passing here would be the worst outcome: the gate reports clean
    while proving nothing, which is how a stale or invented artifact reaches a
    reader.
    """
    findings = review.check_quotes(
        _with_quote("a" * 30), Path("/nonexistent/tutorial.md"))
    assert any("cannot verify" in str(f) for f in findings)
