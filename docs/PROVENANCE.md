# Where what you see comes from

Every number on a generated page is produced by **executing the
specification**. Nothing is read from a recorded run.

```
algorithms/<alg>/
  spec/
    <program>.json   the IR: the algorithm, as Einsums
    instance.json    the input, and how to draw it: tensors, extents,
                     vertex positions, which tensor labels a node or an edge
    cascade.json     structure the IR does not carry: where the loop starts,
                     where the stopping condition is tested, which rule each
                     free choice uses, display aliases
    meta.py          LaTeX, per-Einsum prose, tensor groups, page title
    view.py          OPTIONAL. Phrasing for the few steps where the derived
                     caption reads badly, and what counts as an operation
  fixtures/          recorded traces: the second opinion, never an input
  reference/         hand-written implementations, same role
  verify/            the algorithm's own answer check
  tests/             what is specific to this algorithm
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

## Nothing in the tool knows an algorithm

`edge_workbench/` contains no tensor names, no Einsum labels, no `push` or
`relabel`, no CLRS. Everything it needs, it reads:

| it used to hard-code | it now reads |
|---|---|
| `EINSUM_IDX` for E01–E24 | `cascade.json`'s `setup` + `body` |
| `{Delta: "delta"}` in the interpreter | `cascade.json`'s `displayNames`, passed by the caller |
| `max_flow_program.json` | the one IR program in `spec/`, found not named |
| vertex positions, node and edge labels, fill colours | `instance.json`'s `domain` block |
| `GROUPS`, `STATEFUL`, the page title | `meta.py` |
| `flow-graph`, a renderer that knew about flow | a `graph` renderer driven by that `domain` block |
| `max flow = N` in the corner | `view.headline()`, as `{label, value}` |
| counting `push` and `relabel` by name | whatever operation kinds the trace declares |
| a max-flow verifier in `edge_workbench/verify/` | `algorithms/<alg>/verify/`, run if present |

The audit is mechanical: grep the tool for algorithm words and every hit is a
comment explaining a point, not code acting on it.

### What is still algorithm-shaped, and known to be

`algorithms/max-flow/tests/check_page.js` — 163 checks, most of which are
about the *viewer* (transport, before/after, empty-value labels, the execution
panel) and would serve any algorithm, and some of which are about push-relabel.
It lives under the algorithm because that is what it currently is. Splitting
the generic half into `tests/` is the next job, and until it is done the
second algorithm starts with no page checks.

## Vendoring

`spec/<program>.json` is copied from `edge-ir-interpreter`
(Apache-2.0, © Toluwanimi Odemuyiwa) rather than read across checkouts, so
this repo builds on its own. `tests/test_build_gate.py` checks the copy still
matches upstream whenever the sibling repo is present, so it cannot go stale
silently — which it did once before, and `AdmPost` was the consequence.
