# edge-workbench

Takes an EDGE algorithm specification and produces a **verified, explorable
page**: step through the cascade one Einsum at a time, watch each one execute
over its iteration space, and see the result checked against something that
did not come from the same source.

The two halves matter equally. A visualisation nobody has verified is an
animation of a guess.

```
tutorial / IR spec  ─→  execute  ─→  verify  ─→  render
                          │           │
                          │           ├─ the author's own worked example
                          │           ├─ an independent oracle
                          │           └─ properties that need no oracle
                          └─ one trace, generated from the spec
```

## Quick start

```
git clone <this repo> && cd edge-workbench
npm install                 # jsdom, for the headless page checks
npm run build               # verify, then write build/max-flow/index.html
npm test                    # everything
```

`node` and Python 3.10+ are the only requirements. No pip install, no sibling
checkout — see *Provenance* below for why that is deliberate.

## Status

**Early, but the load-bearing piece is in.** The page is built by executing
the specification: the driver runs the IR over the instance and the trace it
produces is what you see. Nothing is rendered from a recorded run.

| | |
|---|---|
| ✅ | renderer, execution panel, 163-check regression suite |
| ✅ | single-Einsum interpreter with per-point provenance |
| ✅ | max-flow reproduces bit-for-bit in its new home |
| ✅ | **cascade driver** — runs a whole spec; reproduces the hand-written trace step for step |
| ✅ | selector registry (named choice functions with real semantics) |
| ✅ | agreement with the upstream reference evaluator, state cell by cell |
| ✅ | **the page is built from execution**, not from a recorded trace |
| ✅ | per-rank extents, `RankValue`, the loop derived from the generational rank |
| ⬜ | a non-graph domain view, and the page's grids at non-square extents |
| ⬜ | oracle registry, worked-example checker |
| ⬜ | tutorial `.md` → IR |

## The driver

`edge_workbench/driver/` runs a whole specification: seed the inputs, run the
initialization, run the body once per generation, test the stopping condition,
repeat. The trace is now a product of the spec rather than something a person
wrote, which is what makes the rest of the plan possible.

**It is checked against the hand-written trace, step for step** — same
Einsum, same generation, same output tensor, same full state after it.
Free choices are replayed from the recording so that a legitimate difference
in an unspecified choice cannot masquerade as agreement; a second mode then
runs with a real rule and checks the answer still comes out. `--self-test`
breaks the run three ways and requires the comparison to notice each one.

Two semantics turned out to matter, and the diff is what found them:

- **A step replaces its output; the nodes within a step accumulate.**
  `Adm_{i+1}` is defined entirely by the Einsum that writes it, so a
  coordinate it does not produce is empty — not whatever generation `i` had
  there. But a lowered `cases` is several IR nodes writing one tensor, and
  later arms must be able to blank what earlier ones wrote.
- **Aliases apply on write, not just on read.** The IR's `Delta` is the
  write-up's `delta`. The interpreter already aliased reads; without the same
  on writes the cascade silently splits into two tensors that never meet.

## Two second opinions

A single implementation cannot catch a wrong spec: a wrong spec executed by a
wrong interpreter produces a self-consistent wrong trace, and nothing notices.
So nothing here is checked only against itself.

**The hand-written push-relabel** (`algorithms/max-flow/reference/`) stopped
being the source of the trace and became a second opinion. It caught
`NeiLbl` inheriting the wrong empty value in the published spec. Max-flow is
the only algorithm that will ever have one of these.

**The reference evaluator** in `edge-core-ir` is the one every
algorithm will have: an independent execution of the same IR, by the IR's
author, in another language, with generation-indexed state rather than flat.
`tests/test_agrees_with_reference.py` runs both over the same program and
compares the loop-carried state cell by cell — a set derived from the program
rather than listed, so it follows the spec if the spec moves.

That pairing immediately found something: a lowered `cases` arm that computes
its output's empty value cannot clear what an earlier arm wrote, so max-flow's
residual graph carries capacity on edges the preflow saturated. It does not
change the answer — the source is never active, so the phantom residual is
never used — which is exactly why only a state comparison finds it. Written up
in `docs/DIVERGENCE_case_arms.md`, and asserted to its exact shape rather than
skipped.

### What the driver deliberately does not produce

`caption`, `expr` and `graphHighlight`. "Push 12 on (1,3)" is a sentence about
push-relabel, not a consequence of the spec, so it comes from display metadata
and the domain view. A driven trace matches a recorded one on semantic content
and nowhere else — which is exactly the content a second implementation could
disagree about.

## Provenance

Everything on a page comes from running the spec. The recorded trace and the
hand-written push-relabel in `algorithms/max-flow/{fixtures,reference}/` are
the *second opinion*: the build compares its driven trace against them and
refuses to write a page if they disagree. Three gates run before anything is
written, and there is no flag to skip them.

The IR and its reference evaluator live in **`edge-core-ir`** (public) and
`edge-ir-interpreter` (private, currently ahead). Nothing in the build path
touches either: a clean clone builds with `node` and nothing else, because the
IR is vendored. When a checkout is present, `npm run agree` compares the two
evaluators cell by cell — and first checks that upstream ships the *same
program* we vendored, because comparing two evaluators over two different
programs proves nothing. Today the public repo predates the E03/E13 rank
reordering, so that comparison skips with a message saying exactly which
Einsum differs.

`docs/PROVENANCE.md` has the full picture.

## Free choices

A populate names a choice function the IR does not define. Some of those
choices are genuinely free and some are the algorithm, and the difference
decides what a run should do with them.

Max-flow's `pick-admissible-edge` is free: `1(pick-admissible-edge)` says ANY
admissible edge. So the default is **seeded-random**, not a rule. A
deterministic rule would make the spec claim something it does not, and would
sample the legal executions with a bias — a bug that only appears on some
choices would never appear at all.

That freedom is measured rather than asserted: 27 different ways of choosing
(25 seeds plus the two coordinate rules) all reach the published maximum flow
of 23, all produce a feasible flow, and they take between 15 and 19 pushes to
get there. Same seed, same run, so a build is reproducible.

Algorithm X's `select-max-val` will not be free — it *is* the stack
discipline — and will be mapped to the registry rule of that name.

The one place a free choice gets pinned is a comparison between two
implementations, where otherwise every disagreement is legitimate and the
comparison says nothing. That pinning lives in the test doing the comparing,
not in the algorithm's spec.

## Layout

```
edge_workbench/          the tool. Contains no algorithm.
  driver/      cascade.js, selectors.js, run.py
  render/      build_page.py, annotate.py, edge_interp.js
  verify/      VERIFICATION.md -- the discipline
  paths.py     where things live
algorithms/
  max-flow/              one algorithm, entirely inside one directory
    spec/      IR program, instance, cascade structure, display metadata
    fixtures/  recorded traces: the second opinion, never an input
    reference/ hand-written implementations, same role
    verify/    its own answer check, run by the build if present
    tests/     page checks, agreement with the reference evaluator
tests/                   generic: driver comparison, interpreter oracle
```

Adding an algorithm is adding a directory. The tool reads the spec for the
Einsum mapping, the instance for the picture, `meta.py` for the prose — it
does not know what any of them compute.

## Related repos

| repo | role |
|---|---|
| `edge-ir-interpreter` | IR schema and validator. Upstream; its programs are vendored here, not read across checkouts. |
| `edge-algorithms` | the public website. Consumes pages this repo generates. |
| `GraphEinsums` | research notebooks and findings. Not a dependency. |
