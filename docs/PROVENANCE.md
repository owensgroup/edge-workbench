# Where what you see comes from

Every number on a generated page is produced by **executing the
specification**. Nothing is read from a recorded run.

```
algorithms/<alg>/spec/
  <program>.json   the IR: the algorithm, as Einsums
  instance.json    the input: capacities, source, sink, extents
  cascade.json     structure the IR does not carry: where the loop starts,
                   where the stopping condition is tested, which rule each
                   free choice uses
  meta.py          LaTeX and per-Einsum prose
  view.py          OPTIONAL. Domain view, and phrasing for the few steps
                   where the derived caption reads badly
        │
        ▼
edge_workbench/driver/cascade.js      executes it, one Einsum at a time
        │  {generations, steps:[{einsum, iteration, output, state}]}
        ▼
edge_workbench/render/annotate.py     LaTeX, captions, highlights
        │
        ▼
edge_workbench/render/build_page.py   one self-contained index.html
```

## What is NOT an input

`algorithms/<alg>/fixtures/*.json` and `algorithms/<alg>/reference/*.py`.

Those are the **second opinion**: a hand-written implementation of
push-relabel and the 236-step trace it produces. The build compares its driven
trace against that recording and refuses to write a page if they disagree.
They are how the execution is checked, not where the page comes from.

This distinction used to be the other way round, and it mattered: while the
page was rendered from the hand-written trace, "the visualisation shows what
the specification does" was an article of faith. Now the only way to change
what the page shows is to change the spec, the instance, or the presentation.

## Three gates, all before the page is written

| gate | what it would catch |
|---|---|
| `verify_interp.js` | the einsum interpreter disagreeing with the recorded trace — wrong merge tables, transposed operands, empty-value mistakes |
| `verify_algorithm.py` | the answer being wrong, against an independent Edmonds–Karp, with property tests and fault injection |
| `drive_and_compare.js` | the **driven** trace disagreeing with the hand-written one, step for step, plus a 27-way sweep of the free choice |

A failure in any of them aborts the build. There is no flag to skip them.

## The optional fourth opinion

`tests/test_agrees_with_reference.py` runs the cascade through the reference
evaluator in `edge-ir-interpreter` and compares the loop-carried state cell by
cell. That repo is **private**, so this is a test and never a build step: a
clean clone builds with `node` and nothing else. When the sibling checkout is
present, set `EDGE_IR_REPO` and the comparison runs; when it is not, it skips.

## Vendoring

`spec/<program>.json` is copied from `edge-ir-interpreter`
(Apache-2.0, © Toluwanimi Odemuyiwa) rather than read across checkouts, so
this repo builds on its own. `tests/test_build_gate.py` checks the copy still
matches upstream whenever the sibling repo is present, so it cannot go stale
silently — which it did once before, and `AdmPost` was the consequence.
