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

## Status

**Early, but the load-bearing piece is in.** The tooling was lifted out of
`GraphEinsums/notebooks/zoo/tutorials/maxflow/viz/` and the interpreter has
been promoted to a cascade driver, so a trace is now produced *from a spec*
rather than from a hand-written implementation of the algorithm.

```
npm test          # build, interpreter oracle, page checks, driver, self-test,
                  # and agreement with the reference evaluator
```

| | |
|---|---|
| ✅ | renderer, execution panel, 163-check regression suite |
| ✅ | single-Einsum interpreter with per-point provenance |
| ✅ | max-flow reproduces bit-for-bit in its new home |
| ✅ | **cascade driver** — runs a whole spec; reproduces the 236-step hand-written trace |
| ✅ | selector registry (named choice functions with real semantics) |
| ✅ | agreement with the upstream reference evaluator, state cell by cell |
| ⬜ | per-rank extents (today the viewer assumes one global `N`) |
| ⬜ | oracle registry, worked-example checker |
| ⬜ | tutorial `.md` → IR |

## The driver

`edge_workbench/driver/` runs a whole specification: seed the inputs, run the
initialization, run the body once per generation, test the stopping condition,
repeat. The trace is now a product of the spec rather than something a person
wrote, which is what makes the rest of the plan possible.

**It is checked against the hand-written trace, step for step.** All 236 —
same Einsum, same generation, same output tensor, same full state after it.
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

**The reference evaluator** in `edge-ir-interpreter` is the one every
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

## Layout

```
edge_workbench/
  driver/      cascade.js, selectors.js   (runs a spec)
  registry/    oracles, domain views      (next)
  render/      page generation, edge_interp.js
  verify/      checks and the discipline
algorithms/
  max-flow/
    spec/      IR program, instance, cascade structure, display metadata
    fixtures/  the golden trace, and the traces it is compared against
    reference/ the hand-written implementations, kept as a second opinion
tests/         headless page checks, interpreter oracle
```

## Related repos

| repo | role |
|---|---|
| `edge-ir-interpreter` | IR schema and validator. Upstream; its programs are vendored here, not read across checkouts. |
| `edge-algorithms` | the public website. Consumes pages this repo generates. |
| `GraphEinsums` | research notebooks and findings. Not a dependency. |
