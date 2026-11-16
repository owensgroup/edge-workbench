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

## The workflow

An algorithm becomes a published page in six steps. Each step names who does
it; only the parts marked **you** need a person.

1. **Draft** (agent, with you). In Claude Code in this repository, ask for an
   EDGE tutorial and give one of: an algorithm's name, pseudocode, a program,
   or an existing tutorial (e.g. `edge-algorithms/_algorithms/<name>.md`).
   The `write-edge-tutorial` skill (`.claude/skills/write-edge-tutorial/`)
   writes the tutorial `.md` (with its `ranks:` block and meaning lines) and
   `einsum.edge` into `examples/<slug>/`, asking whenever something is
   unclear. **You** approve at two checkpoints: (A) the pseudocode, worked
   example and its expected answer; (B) the cascade.
2. **Verifier** (**you** choose). The skill offers the verifier kinds
   (`definition`, `library`, `certificate`, `different-algorithm`,
   `user-reference`); you pick one. It drafts `verifier.py` only for a
   library check or a wrapper around your own code, or if you ask it to.
3. **Approve** (**you**, checkpoint C), in your own terminal:
   ```
   python3 -m edge_workbench approve-verifier examples/<slug>
   ```
   This pins `verifier.py` and, once it is known, the tutorial's published
   answer in `verifier.lock`. Commit both. No agent can approve.
4. **Check** (agent):
   ```
   python3 -m edge_workbench check examples/<slug>
   ```
   Every stage lists all its problems, then stops. The builder and
   tutorial-data steps write a prompt; the agent answers it in the same
   session (or you paste it into a chat) and the reply is checked like
   anything else. A new tutorial's first published answer needs one more
   `approve-verifier`. Anything about the cascade, the example or the answer
   comes back to you with evidence. When every stage passes, `index.html` is
   written beside your files.
5. **Look**: open `examples/<slug>/index.html`.
6. **Publish** (agent or you):
   ```
   python3 -m edge_workbench publish examples/<slug>
   ```
   Runs `check` again and refuses unless it passes, copies the page to
   `edge-algorithms/assets/viz/<slug>/` (or `--site <dir>`), and adds the
   `viz:` link to the site's tutorial. `--with-tutorial` also replaces the
   site's tutorial with this one. Nothing is committed.

Without an agent: write the three files yourself (tutorial `.md`,
`einsum.edge`, `verifier.py`) and run steps 3-6, pasting the two prompts
into a chat. **[AUTHORING.md](AUTHORING.md) is the step-by-step guide.**

Other commands: `python3 -m edge_workbench verify-instance <dir> <k>` reruns
one random instance of the answer check.

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
