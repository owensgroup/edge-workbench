# edge-workbench

Turns an EDGE algorithm tutorial into a verified, explorable page. The author
writes three files (tutorial `.md`, `einsum.edge`, `verifier.py`); `check`
checks them against each other, runs the cascade with edge-core-ir's
evaluator, checks the answers, and writes one static `index.html`.
[AUTHORING.md](AUTHORING.md) is the author's guide.

## Goals

- **Teach:** show exactly how each Einsum executes on a worked example.
- **Verify:** run on the reference interpreter and check against an
  independent verifier before anything is published.
- **Generalize:** any tutorial, including non-graph algorithms, with minimal
  human effort.
- **Planned:** AI writes the spec; the workbench checks and explains it. The
  research aim is systems/PL (an untrusted AI front end kept honest by a
  reference interpreter), not HCI.

Why, how it works, every design decision and whose it was, and what we
learned: [docs/DESIGN.md](docs/DESIGN.md).

## Commands

- `python3 -m edge_workbench check examples/<alg>` — run every stage on one algorithm
- `npm test` — build and check every example and page (needs `npm install` for jsdom)
- edge-core-ir is found via `EDGE_IR_REPO`, a checkout beside this repo, or `~/Projects/edge-core-ir`

## Rules

- **The Einsums and the tutorial are the source of truth, not the IR.** If the
  IR disagrees with an Einsum, the IR is wrong.
- **Never change, split or re-express an author's Einsum** unless it is wrong
  and the user explicitly says so. Show parenthesized parts as labelled
  sub-steps, never as new helper tensors. List any unavoidable change.
- **edge-core-ir belongs to Toluwa.** Do not edit it; write gaps up in
  [docs/issues-for-edge-core-ir.md](docs/issues-for-edge-core-ir.md). Exception:
  issues 1, 2 and 7 are fixed locally, uncommitted, in her checkout.
- **Her evaluator is the only evaluator.** The page replays its trace; nothing
  in this repo evaluates Einsums, in Python or JS.
- **Fixes go in the tool, not in one page.** Every fix should help future algorithms.
- **No model or API calls in CI.** Model steps are author-run: `check` writes a
  prompt, the author pastes it into a chat, and the reply is checked like
  author input.
- **Do not commit or push.** Leave changes in the working tree.
- **Ask, don't assume.** Questions and brainstorming are answered in chat, not in files.

## References

`docs/references/` (git-ignored, local only):
- `2404.11591v2.pdf` — the EDGE notation paper
- `3649812.pdf` — Crichton & Krishnamurthi, "Profiling Programming Language Learning" (OOPSLA 2024)
- `DOBFS.pdf`, `BF.pdf` — Sanjana's write-ups of the DOBFS and Bellman-Ford tutorials,
  with Graph/Einsum meanings per Einsum. `DOBFS.pdf` predates the `Visited`/`NV`
  split; the current source is GraphEinsums `notebooks/zoo/tutorials/DO_BFS`.

Language semantics and parser gotchas: [.claude/rules/edge-semantics.md](.claude/rules/edge-semantics.md).
