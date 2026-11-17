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

## Workflow

1. **Draft** with the `write-edge-tutorial` skill (`.claude/skills/write-edge-tutorial/`,
   plus its `rules.md`): from an algorithm's name, pseudocode, a program, or an
   existing tutorial (e.g. `~/Projects/edge-algorithms/_algorithms/<name>.md`,
   copied, never edited in place). It asks the author whenever something is
   unclear and stops at checkpoints A (pseudocode, worked example, expected
   answer) and B (the cascade).
2. **Check** loops until every stage passes. The builder and tutorial-data
   model steps write prompts under `workbench/prompts/`; the agent answers them
   in-session into `workbench/replies/`.
3. **Approve** (checkpoint C) once, when `check` ends with `… approval`; it
   pins `verifier.py` and the published answer in `verifier.lock`.
4. **Publish** to the site (`~/Projects/edge-algorithms`).

## Commands

- `python3 -m edge_workbench check examples/<alg>` — run every stage on one algorithm
- `python3 -m edge_workbench approve-verifier examples/<alg>` — a person approves (terminal);
  in-session: `... --confirm "<METHOD>" --sha <first 12 of sha256(verifier.py)>`, only right
  after showing the author the whole file; `.claude/settings.json` forces a permission
  prompt for it, and that click is the approval
- `python3 -m edge_workbench publish examples/<alg>` — reruns `check`, copies the page to
  `edge-algorithms/assets/viz/<alg>/`, adds `viz:` keys (`--with-tutorial`, `--site`)
- `python3 -m edge_workbench verify-instance examples/<alg> <k>` — rerun one random instance
- `npm test` — domain views, every example page, pytest (needs `npm install` for jsdom)
- edge-core-ir is found via `EDGE_IR_REPO`, a checkout beside this repo, or `~/Projects/edge-core-ir`

Examples (approved, except bubble-sort, which waits for its approval): bellman-ford, direction-optimizing-bfs (hybrid cascade,
α = 15, β = 18), maximum-flow, set-cover, breadth-first-search (port of the
site tutorial), bfs-from-name (CLRS §22.2, written by the skill), bubble-sort.

## Rules

- **The Einsums and the tutorial are the source of truth, not the IR.** If the
  IR disagrees with an Einsum, the IR is wrong.
- **Never change, split or re-express an author's Einsum** unless it is wrong
  and the user explicitly says so. Show parenthesized parts as labelled
  sub-steps, never as new helper tensors. List any unavoidable change.
- **edge-core-ir belongs to Toluwa.** Do not edit it; write gaps up in
  [docs/issues-for-edge-core-ir.md](docs/issues-for-edge-core-ir.md). Exception:
  issues 1, 2, 7, 8, 9, 10 and 11 are fixed locally, uncommitted, in her checkout.
- **Her evaluator is the only evaluator.** The page replays its trace; nothing
  in this repo evaluates Einsums, in Python or JS.
- **Fixes go in the tool, not in one page.** Every fix should help future algorithms.
- **No model or API calls in CI.** Model steps are author-run: `check` writes a
  prompt, and either the author pastes it into a chat or a local agent using
  the `write-edge-tutorial` skill answers it in-session. Either way the reply
  is checked like author input.
- **Verifier and approval.** Never edit `verifier.py` after approval, `verifier.lock`,
  or `~/.config/edge-workbench/`, and never use `EDGE_WORKBENCH_LEDGER` (project deny
  rules enforce this). The verifier is the author's choice of kind (`definition`,
  `library`, `certificate`, `different-algorithm`, `user-reference`); an agent drafts one
  only when the author asks. A never-approved verifier lets `check` run to the end and
  ask once; a changed one stops `check` at once.
- **Picture from the `ranks:` block** in the tutorial's front matter (closed vocabulary:
  `generational`, `vertex`, `set`/`element`, `position`, `spatial`); without it, inferred.
  `I` stays the generational rank (undecided for SpMV).
- **Delegate the hardest, highest-priority work to Fable subagents**
  (`model: "fable"`), with a self-contained brief; review their report and
  check their claims before relaying.
- **Do not commit or push.** Leave changes in the working tree.
- **Ask, don't assume.** Questions and brainstorming are answered in chat, not in files.

## References

`docs/references/` (git-ignored, local only):
- `EDGE.pdf` — the EDGE notation paper ("The EDGE Language: Extended General
  Einsums for Graph Algorithms"). Use its terms: generational (or iterative)
  rank, generation, cascade, iteration space, coordinate (an index along a
  rank). "Round" only in the paper's Populate sense (one point of the
  iteration space; Inset 4), never for a generation. No PDF tools are
  installed; extract text with a small zlib script if needed.
- `BFS_EEDS.pdf` — contents not yet described
- `DOBFS.pdf`, `BF.pdf` — Sanjana's write-ups of the DOBFS and Bellman-Ford tutorials,
  with Graph/Einsum meanings per Einsum. `DOBFS.pdf` predates the `Visited`/`NV`
  split; the current source is GraphEinsums `notebooks/zoo/tutorials/DO_BFS`.

Language semantics and parser gotchas: [.claude/rules/edge-semantics.md](.claude/rules/edge-semantics.md).
