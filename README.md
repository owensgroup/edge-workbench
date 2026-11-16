# edge-workbench

Takes an EDGE algorithm specification and produces a **verified, explorable
page**: step through the cascade one Einsum at a time and watch each one
execute over its iteration space.

The page is built by **executing the specification with edge-core-ir's
evaluator**, which is the source of truth for EDGE semantics. The workbench
records what that evaluator computed and the page renders it; nothing is
evaluated a second time, in the browser or anywhere else.

```
npm install                                  # jsdom, for the headless page checks
python3 -m edge_workbench check examples/maximum-flow   # writes examples/maximum-flow/index.html
npm test                                     # domain views, every example page, pytest
```

Python 3.10+ and an [`edge-core-ir`](https://github.com/edge-einsums/edge-core-ir)
checkout beside this one (or `EDGE_IR_REPO` pointing at it). `node` is needed
only for the headless page checks.

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

The answer check is the author's `verifier.py`, because only the algorithm
knows what right means; the tool runs it on the worked example, the published
answer and 12 random instances. A person approves each verifier with
`python3 -m edge_workbench approve-verifier <dir>` (AUTHORING.md), and `check`
refuses one that has changed since.

`check` also validates the program against the IR (Layer 1 and Layer 2) and
against einsum.edge. `npm run gates` runs the test suite; the tests that need
an [`edge-core-ir`](https://github.com/edge-einsums/edge-core-ir) checkout or
generated example files skip without them.

## Layout

```
edge_workbench/        the tool. Contains no algorithm.
  author.py    `check`: every stage, in order
  driver/      run.py: runs edge-core-ir's evaluator and records the trace
  render/      build_page.py, annotate.py, display.js (glyphs only; no evaluation)
  verifier.py, approval.py    the verifier contract and its approval
  rank_kinds.py, domain_shape.py    which picture a program gets
examples/<alg>/        tutorial .md, einsum.edge, verifier.py (+ verifier.lock);
                       `check` writes workbench/ and index.html beside them
tests/                 generic gates
```

Adding an algorithm is adding a directory with those three files. The tool
does not know what any algorithm computes.

## Free choices

A populate names a choice function the IR does not define. Some of those
choices are genuinely free and some are the algorithm, and mapping a free one
to a fixed rule would make the spec claim something it does not.

Max-flow's `pick-admissible-edge` is free — `1(pick-admissible-edge)` says ANY
admissible edge — so it runs seeded-random, seeded so a build is reproducible.
An unmapped name stops the cascade rather than being guessed at.
