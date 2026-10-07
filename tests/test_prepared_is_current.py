"""The prepared artifacts must still be the tutorial's, and still be current.

WHAT THIS REPLACES
------------------
The build used to read the tutorial live. That made it depend on which branch
a sibling repository had checked out, and it showed: moving to a branch that
predated the tutorial's last edit silently downgraded the page to generic
captions and failed three oracle gates, for no reason to do with the
algorithm.

`python3 -m edge_workbench.prepare` reads the tutorial once and writes
`spec/authored.json`; the build consumes that and never opens the `.md`. The
cost of that trade is a new way to be wrong -- the artifact can fall behind
its source, silently, which is worse than the problem it solved because a
stale artifact still builds a clean-looking page.

So the artifact records the tutorial AND the commit it was read at, and these
tests are what make that record mean something:

  * the artifact exists and says where it came from;
  * the tutorial has not moved since -- and when it has, the message says so
    rather than leaving someone to wonder why the page looks old;
  * re-reading the same tutorial produces the same content, so the artifact
    is a faithful copy rather than something hand-edited.

The currency check needs the tutorial checkout and skips without it. That is
deliberate: a clean clone must still BUILD, and the build no longer needs the
tutorial at all. What it must not do is silently claim the artifact is fresh.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import prepare  # noqa: E402

SPECS = sorted((ROOT / "algorithms").glob("*/spec"))


def _ids(paths):
    return [p.parent.name for p in paths]


@pytest.fixture(params=SPECS, ids=_ids(SPECS))
def spec(request):
    return request.param


def _artifact(spec: Path) -> dict:
    data = prepare.load(spec)
    if not data:
        pytest.skip(f"{spec.parent.name} has no prepared artifact yet")
    return data


################################################################################
# the record exists and is honest
################################################################################


def test_the_artifact_says_where_it_came_from(spec):
    source = _artifact(spec).get("source") or {}
    assert source.get("tutorial"), (
        "an artifact with no recorded source cannot be checked against "
        "anything, which is the whole point of preparing it"
    )
    assert source.get("preparedOn"), "no date recorded"


def test_a_dirty_source_is_recorded_not_hidden(spec):
    """Preparing from an uncommitted edit is fine; pretending otherwise is not.

    It is normal while iterating. But an artifact prepared from a working-tree
    edit cannot be compared against any commit, so the flag is what tells a
    reviewer that the currency check below proves nothing for it.
    """
    source = _artifact(spec).get("source") or {}
    assert "dirty" in source, "the artifact does not say whether its source was clean"
    if source.get("dirty") or not source.get("sha"):
        pytest.skip(
            "prepared from an uncommitted or unversioned tutorial, so there "
            "is no commit to check against"
        )


################################################################################
# it is still current
################################################################################


def _tutorial_repo() -> Path | None:
    env = os.environ.get("EDGE_ALGORITHMS_REPO")
    if env:
        return Path(env)
    guess = ROOT.parent / "edge-algorithms"
    return guess if (guess / ".git").exists() else None


def test_the_tutorial_has_not_moved_since_it_was_prepared(spec):
    """The signal that says "re-run prepare".

    Compares the recorded commit against the tutorial's current last-touching
    commit. Skips when the tutorial checkout is absent, or when the artifact
    was prepared from an uncommitted edit -- in both cases there is nothing to
    compare, and saying so beats implying freshness.
    """
    data = _artifact(spec)
    source = data.get("source") or {}
    recorded = source.get("sha")
    if not recorded or source.get("dirty"):
        pytest.skip("prepared from an uncommitted or unversioned tutorial")

    repo = _tutorial_repo()
    if repo is None:
        pytest.skip("no edge-algorithms checkout; set EDGE_ALGORITHMS_REPO")

    rel = source["tutorial"]
    if not (repo / rel).exists():
        pytest.skip(f"{rel} is not present in {repo} on this branch")

    head = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%H", "--", rel],
        capture_output=True, text=True,
    ).stdout.strip()
    assert head == recorded, (
        f"{rel} has moved since spec/authored.json was prepared.\n"
        f"  prepared at : {recorded[:12]}\n"
        f"  tutorial at : {head[:12] or '(unknown)'}\n"
        f"Re-run: python3 -m edge_workbench.prepare "
        f"{repo / rel} --spec {spec.relative_to(ROOT)}"
    )


################################################################################
# it is a faithful copy
################################################################################


def test_re_reading_the_tutorial_reproduces_the_authors_fields(spec):
    """No hand edits, and no drift between reader and artifact.

    Validity is not enough on its own: a well-formed artifact can still be one
    somebody adjusted by hand, and then the recorded provenance is a claim
    about a file that no longer produced it.

    ONLY THE AUTHOR'S FIELDS. A field `propose` filled is by definition not
    something re-reading the tutorial reproduces -- that is the whole point of
    it having been a gap. Checking those too would mean every model-filled
    artifact fails this, which is how the check would get deleted instead of
    scoped. `provenance` is what says which is which, and this is the second
    thing that depends on it being recorded honestly.
    """
    data = _artifact(spec)
    source = data.get("source") or {}
    if source.get("dirty") or not source.get("sha"):
        pytest.skip("prepared from an uncommitted or unversioned tutorial")

    repo = _tutorial_repo()
    if repo is None or not (repo / source["tutorial"]).exists():
        pytest.skip("tutorial not available to re-read")

    from edge_workbench import review

    prov = data.get("provenance") or {}
    fresh = prepare.read_tutorial(repo / source["tutorial"])
    checked = 0
    for field in ("meanings", "tensorNotes"):
        if prov.get(field) != review.AUTHOR:
            continue
        checked += 1
        got = fresh.meanings if field == "meanings" else fresh.tensor_notes
        assert got == data.get(field, {}), (
            f"{field} in spec/authored.json is recorded as the AUTHOR's but "
            f"differs from what the tutorial now yields. Re-run prepare "
            f"rather than editing the artifact."
        )
    if not checked:
        pytest.skip("every readable field was filled by the model, not read")


def test_the_artifact_lists_its_gaps(spec):
    """What the tutorial did not state, so the model-assisted half knows.

    An artifact with no `gaps` key is from before that idea existed; an empty
    list is a positive claim that the tutorial said everything.
    """
    data = _artifact(spec)
    assert "gaps" in data, "no gap list: nothing says what still needs filling"
    assert isinstance(data["gaps"], list)


################################################################################
# the gate between "a model produced something" and "the build shows it"
################################################################################


def test_the_artifact_survives_review(spec):
    """Everything mechanically checkable about what fills the gaps.

    Not accuracy -- no test can say whether a meaning explains its Einsum
    well, and that is what review is for. These checks exist to make review
    CHEAP: they clear away coverage, relevance, soundness and provenance so a
    reviewer spends their attention on the prose.

    The relevance check is the interesting one, and it took two attempts. The
    obvious form -- "a meaning should mention a tensor its Einsum touches" --
    fired on four of max-flow's own correct meanings, because a good meaning
    describes the PROBLEM ("total flow arriving at each vertex") and names no
    tensor at all. A check that flags good writing is worse than no check.

    Inverted, it looks for a meaning naming a tensor belonging to some OTHER
    Einsum, which is real evidence of prose landing on the wrong step when a
    phase-grouped walkthrough is split per Einsum. Absence of evidence is not
    evidence; a contradiction is.

    THE GATE OPENS ONCE, AND NOT BEFORE
    -----------------------------------
    An algorithm is assembled in stages: a prepared artifact, then a program,
    then the filled gaps, then a page. In every window before the last one,
    `prepare` has correctly reported gaps that nothing has filled yet.
    Failing there would mean starting an algorithm breaks the suite, which
    teaches an author to skip the step rather than finish it.

    `meta.py` is the readiness marker, because it is what the renderer needs:
    an algorithm that has one is claiming a page can be built from it, and an
    unfilled gap then IS a failure -- a reader is about to be shown generic
    captions. An algorithm without one is still being assembled, and the gap
    list `prepare` printed is its status.

    The marker is deliberately NOT "has a program". set-cover has a program,
    a validated IR and a cascade that reproduces the tutorial's worked
    examples, and still has three unfilled gaps, because the model-assisted
    step has not run. That is a correct intermediate state, not a fault.
    """
    from edge_workbench import review

    data = _artifact(spec)
    if not (spec / "meta.py").exists():
        pytest.skip(
            f"{spec.parent.name} is not wired for rendering yet (no meta.py); "
            f"prepare's gap list is its status until it is"
        )
    program_files = sorted((spec).glob("*_program.json"))
    cascade_file = spec / "cascade.json"
    program = cascade = None
    if program_files and cascade_file.exists():
        program = json.loads(program_files[0].read_text())
        cascade = json.loads(cascade_file.read_text())

    findings = review.check(data, program, cascade)
    assert not findings, review.report(findings)
