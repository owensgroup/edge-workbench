# What moved, what stayed, and why

The split is between **tooling** and **findings**. Tooling is what runs on
someone else's algorithm; findings are what we learned about max-flow. They
have different lifecycles and different readers, so they live in different
repos.

`GraphEinsums` is **untouched** by this move — everything here is a copy, and
its build still works. Nothing is deleted there until the cascade driver lands
and this repo has earned the job.

## Moved (copied) here

| from `…/maxflow/viz/` | to | why it is tooling |
|---|---|---|
| `edge_interp.js` | `edge_workbench/render/` | evaluates an Einsum from the IR. Knows nothing about flow. |
| `build_viz.py` | `edge_workbench/render/build_page.py` | the renderer. The graph pane is behind a registry; the rest is generic. |
| `check_viz.js` | `tests/check_page.js` | 163 checks. The regression suite is the asset. |
| `verify_interp.js` | `tests/` | replays the interpreter against a trace. |
| `verify_algorithm.py` | `edge_workbench/verify/` | oracle + property + fault-injection pattern, to be generalised into the oracle registry. |
| `VERIFICATION.md` | `edge_workbench/verify/` | the discipline. It is the argument that uploaded tutorials can be trusted. |

## Moved here as fixtures, not as tooling

| file | role now |
|---|---|
| `maxflow_edge_trace.json` | **the golden trace.** 222 steps. When the interpreter is promoted to a cascade driver, the acceptance test is a diff against this. |
| `maxflow_seq_trace.json` | the textbook pseudocode's trace, for compare mode. |
| `scaling.json` | measured, not computed at build time. |
| `max_flow_program.json` | the IR. Vendored from `edge-ir-interpreter`, deliberately — the build must not depend on a sibling checkout. |
| `meta.py` | display metadata: LaTeX, rank names, hover text. |
| `eval_edge.py`, `seq_pushrelabel.py` | **reference implementations.** Demoted from "source of the trace" to "second opinion". See below. |

## Stayed in GraphEinsums

The notebooks, the tutorial zoo, and the three max-flow cascades *as content* —
`SEQUENTIAL_CASCADE.md`, `CASCADE_DIFF.html`, `PRESENTATION.md`, `viz-seq/`,
`viz-direct/`, `IR_ASSESSMENT.md`. Those are findings about one algorithm. They
are not things anyone would run on their own tutorial.

## Why the reference implementations came along

The obvious move is to delete them: the whole point of promoting the
interpreter is that the trace stops being hand-written. But the hand-written
evaluator does two jobs, and only one of them should end.

1. **Source of the trace.** This ends. That is the point.
2. **Independent second opinion.** This continues, as a test fixture.

Two implementations that must agree is what caught a real bug in the published
spec: `NeiLbl`, `MinNeiLbl` and `NewD` were declared with `empty = 0` when they
hold heights and should have been `+∞`. A single implementation cannot catch
that class at all — a wrong spec executed by a driver produces a
self-consistent wrong trace, and nothing notices.

Future algorithms will not have a second implementation, and that is an
accepted risk for them. It is not a risk worth taking for the one algorithm
where the second path already exists and costs nothing to keep.

## The one deliberate change in the move

Every lifted file used to find its neighbours with `os.path.join(HERE, …)` in
a single flat directory. That became two ideas — `paths.TOOL` for workbench
files and `paths.algorithm(name)` for one algorithm's spec and fixtures — plus
`EDGE_WORKBENCH_ALG` / `EDGE_WORKBENCH_ALG_DIR` so a tutorial can be checked
from outside the repo without copying itself in first.

That is the only change. `tests/test_move_is_faithful.py` proves it: the page
generated here is byte-for-byte the page GraphEinsums generates. Delete that
test once the driver lands and the two legitimately diverge.
