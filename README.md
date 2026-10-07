# edge-workbench

Takes an EDGE algorithm specification and produces a **verified, explorable
page**: step through the cascade one Einsum at a time and watch each one
execute over its iteration space.

The page is built by **executing the specification**. There is no recorded
trace in this repository — not as an input, not as a fixture, not as
something to check against.

```
npm install          # jsdom, for the headless page checks
npm test             # build, then check
open build/max-flow/index.html
```

`node` and Python 3.10+. Nothing else: the IR is vendored, so a clean clone
builds without a sibling checkout.

## Checking your own tutorial

Write three files in one directory -- the tutorial `.md`, its cascade as
`einsum.edge`, and a `verifier.py` -- then run

```
python3 -m edge_workbench check path/to/that/directory
```

as many times as it takes. Each run lists every problem it found and what to
do next; two steps ask you to paste a prompt into a chat and save the reply.
When everything passes, `index.html` is written beside your files.

**[AUTHORING.md](AUTHORING.md) is the step-by-step guide.**

## Gates

Two run before the page is written, and there is no flag to skip them.

| gate | question |
|---|---|
| **coverage** | did every Einsum the author wrote actually execute? |
| **answer** | is what the run produced right? |

Coverage is the one that replaced comparing against a recording. Its failure
mode is silent: an Einsum that never runs produces no wrong value and raises
nothing, it just leaves a page whose step list looks complete. It works off
the driver's per-IR-node tally rather than the emitted steps, because the two
differ on purpose — initialization runs four Einsums and emits one step, and a
lowered `cases` runs three and emits one.

The answer check lives with the algorithm, in `algorithms/<alg>/verify/`,
because only the algorithm knows what right means. The tool just runs it.

`npm run gates` additionally validates every spec against the IR itself —
Layer 1, Layer 2, and that the committed program has not drifted from
whatever generates it. It needs a checkout of
[`edge-core-ir`](https://github.com/edge-einsums/edge-core-ir) and skips
without one:

```
EDGE_IR_REPO=~/Projects/edge-core-ir npm run gates
```

## Layout

```
edge_workbench/        the tool. Contains no algorithm.
  driver/    cascade.js, selectors.js, run.py
  render/    build_page.py, annotate.py, edge_interp.js
  coverage.py
  paths.py
algorithms/max-flow/
  spec/      IR program, instance, cascade structure, display metadata
  verify/    its own answer check, run by the build
  tests/     page checks
tests/       generic gates
```

Adding an algorithm is adding a directory. The tool reads the spec for the
Einsum mapping, the instance for the picture and `meta.py` for the prose — it
does not know what any of them compute.

## Free choices

A populate names a choice function the IR does not define. Some of those
choices are genuinely free and some are the algorithm, and mapping a free one
to a fixed rule would make the spec claim something it does not.

Max-flow's `pick-admissible-edge` is free — `1(pick-admissible-edge)` says ANY
admissible edge — so it runs seeded-random, seeded so a build is reproducible.
An unmapped name stops the cascade rather than being guessed at.
