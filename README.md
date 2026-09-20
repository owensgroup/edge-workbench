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
npm test          # build, interpreter oracle, 163 page checks, driver, self-test
```

| | |
|---|---|
| ✅ | renderer, execution panel, 163-check regression suite |
| ✅ | single-Einsum interpreter with per-point provenance |
| ✅ | max-flow reproduces bit-for-bit in its new home |
| ✅ | **cascade driver** — runs a whole spec; reproduces the 236-step hand-written trace |
| ✅ | selector registry (named choice functions with real semantics) |
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

The hand-written evaluator was not deleted. It stopped being the *source* of
the trace and became a *second opinion*: two independent implementations that
must agree. That architecture caught a real bug in the published spec
(`NeiLbl` inheriting the wrong empty value), and a single implementation
cannot catch that class at all — a wrong spec and a wrong interpreter produce
a self-consistent wrong trace, and nothing notices.

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
