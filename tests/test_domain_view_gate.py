"""A declared domain view must not contradict the one the program implies.

WHY THIS IS A GATE AND NOT A PREFERENCE
---------------------------------------
`domain_shape.classify` reads where the rank-1 tensors live, which is a fact
about the program. Max-flow's twelve are all over `U`, so the two ranks of a
rank-2 tensor index the same set and the picture is a graph. Exact cover's
split 17 on `R` and 6 on `C`, so they are different sets and the picture is
bipartite.

Get it wrong and the page does not look broken -- it looks fine and is wrong.
Every rank-1 marking is read at the other rank's index, so a column's
shading lands on a row. That is worse than a missing picture, which is why a
contradiction fails rather than warns.

THE ASYMMETRY IS DELIBERATE. Saying nothing is allowed: an algorithm that
declares no view takes the derived one. What is not allowed is declaring one
that the program contradicts.

ONE IMPLEMENTATION, TWO CALLERS
-------------------------------
`domain_shape.disagreement` is the only place the comparison lives.
`author.py` folds its findings into the instance stage, where there is still
a stage to report to; `build_page` treats them as fatal, because by then it
is about to write the page. These tests cover the helper and both callers,
because a shared helper is easy to wire up so that one caller silently never
calls it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import domain_shape  # noqa: E402

SPECS = sorted(p for p in (ROOT / "algorithms").glob("*/spec")
               if any(p.glob("*_program.json")))

# What each algorithm's program implies, and why. Pinned rather than computed,
# so a change to `classify` that silently reclassifies an algorithm fails here
# instead of quietly redrawing a page.
EXPECTED = {"max-flow": "graph", "set-cover": "bipartite"}


@pytest.fixture(params=SPECS, ids=[p.parent.name for p in SPECS])
def spec(request):
    return request.param


def _load(spec: Path):
    program = json.loads(next(spec.glob("*_program.json")).read_text())
    instance = None
    if (spec / "instance.json").exists():
        instance = json.loads((spec / "instance.json").read_text())
    return program, instance


def test_the_program_implies_the_view_we_expect(spec):
    program, instance = _load(spec)
    name = spec.parent.name
    if name not in EXPECTED:
        pytest.skip(f"no pinned expectation for {name}")
    shape = domain_shape.classify(program, instance)
    assert shape["view"] == EXPECTED[name], (
        f"{name} now classifies as {shape['view']!r}, not "
        f"{EXPECTED[name]!r}: {shape['reason']}"
    )
    assert shape["reason"], "a classification with no reason cannot be reviewed"


def test_declaring_nothing_is_allowed(spec):
    """An algorithm may decline to declare a view and take the derived one."""
    program, instance = _load(spec)
    assert domain_shape.disagreement(None, program, instance) == []


def test_declaring_the_right_view_is_allowed(spec):
    program, instance = _load(spec)
    shape = domain_shape.classify(program, instance)
    assert domain_shape.disagreement(shape["view"], program, instance) == []


def test_declaring_a_contradicting_view_is_caught(spec):
    """The case the gate exists for, in both directions.

    Checked against the OTHER view rather than a made-up string, because a
    typo'd view name would be caught by the renderer anyway. The dangerous
    input is a real view that happens to be the wrong one.
    """
    program, instance = _load(spec)
    shape = domain_shape.classify(program, instance)
    wrong = (domain_shape.BIPARTITE if shape["view"] != domain_shape.BIPARTITE
             else domain_shape.GRAPH)
    findings = domain_shape.disagreement(wrong, program, instance)
    assert findings, f"declaring {wrong!r} was not caught"
    assert shape["reason"] in findings[0], (
        "the finding must carry the reason, or a reader cannot tell whether "
        "the declaration or the derivation is the thing that is wrong"
    )


################################################################################
# both callers must actually call it
################################################################################


def test_build_page_calls_the_helper():
    """Wiring, not logic. A gate nobody calls is not a gate.

    Checked by source inspection rather than by running a build, because a
    build needs a rendering-ready algorithm and this is a fact about the
    module regardless of which algorithms exist.
    """
    src = (ROOT / "edge_workbench" / "render" / "build_page.py").read_text()
    assert "domain_shape.disagreement(" in src, (
        "build_page no longer consults domain_shape.disagreement, so a "
        "hand-written spec can declare any view it likes"
    )
    assert "sys.exit(1)" in src.split("domain_shape.disagreement(")[1][:400], (
        "build_page finds the disagreement but does not stop; it is about to "
        "write a page whose rank-1 markings land on the wrong node set"
    )


def test_author_calls_the_helper():
    """The same, for the authoring pipeline's instance stage.

    `author.py` merges an author's or model's styling over the derived domain
    and then forces `view` to the derived value. That is the right outcome and
    it used to be a silent one -- a contradiction means either the model
    misread the algorithm or `classify` is wrong, and the second would be a
    bug in something eleven other derivations trust.
    """
    src = (ROOT / "edge_workbench" / "author.py").read_text()
    assert "domain_shape.disagreement(" in src, (
        "author.py imposes the derived view without reporting that the "
        "supplied one disagreed"
    )
    stage = src[src.index("def stage_instance("):]
    assert "domain_shape.disagreement(" in stage[:900], (
        "the call is not in stage_instance, so its findings are not attached "
        "to a stage and will not reach the author's report"
    )
