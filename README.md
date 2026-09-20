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

**Early.** Right now this repo holds the tooling lifted out of
`GraphEinsums/notebooks/zoo/tutorials/maxflow/viz/`, unchanged, with max-flow
as the fixture that proves it still works. The next step is the one that makes
the rest possible.

| | |
|---|---|
| ✅ | renderer, execution panel, 163-check regression suite |
| ✅ | single-Einsum interpreter with per-point provenance |
| ✅ | max-flow reproduces bit-for-bit in its new home |
| ⬜ | **cascade driver** — execute a whole spec, not one Einsum at a time |
| ⬜ | selector registry (named choice functions with real semantics) |
| ⬜ | per-rank extents (today the viewer assumes one global `N`) |
| ⬜ | oracle registry, worked-example checker |
| ⬜ | tutorial `.md` → IR |

## The thing that has to change next

Today the trace is produced by a **hand-written reference implementation** of
each algorithm, and the interpreter only re-evaluates *one* Einsum against a
state that trace already recorded. That is why this does not yet generalise:
every new algorithm would need its own hand-written evaluator.

So the interpreter gets promoted to a **cascade driver** — initialisation,
loop body, stopping condition, next generation — and the trace becomes a
product of the spec.

Max-flow is the right place to do that, because there is already a 222-step
trace to check against. The acceptance test is a diff, not an opinion.

The hand-written evaluator does not get deleted. It stops being the *source*
of the trace and becomes a *second opinion*: two independent implementations
that must agree. That architecture is what caught a real bug in the published
spec (`NeiLbl` inheriting the wrong empty value), and a single implementation
cannot catch that class at all — a wrong spec and a wrong interpreter produce
a self-consistent wrong trace, and nothing notices.

## Layout

```
edge_workbench/
  driver/      execute a cascade          (next)
  registry/    selectors, oracles, views  (next)
  render/      page generation            (lifted, works)
  verify/      checks and the discipline  (lifted, works)
algorithms/
  max-flow/
    spec/      IR program + display metadata
    fixtures/  the golden trace, and the traces it is compared against
tests/         headless page checks, interpreter oracle
```

## Related repos

| repo | role |
|---|---|
| `edge-ir-interpreter` | IR schema and validator. Upstream; its programs are vendored here, not read across checkouts. |
| `edge-algorithms` | the public website. Consumes pages this repo generates. |
| `GraphEinsums` | research notebooks and findings. Not a dependency. |
