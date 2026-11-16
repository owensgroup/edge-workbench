# Design: goals, decisions and lessons

Status as of 2026-11-15. "Sanjana" marks decisions the project lead made;
"Claude" marks decisions made while building, accepted by her.

## What we are building

edge-workbench turns an EDGE algorithm into a page that has been checked and
can be stepped through. Its goals:

- **Teach.** Show exactly how each extended Einsum executes: the tensors, the
  iteration space, how each value is computed, the state before and after.
- **Verify.** Prove a cascade correct by running it on EDGE's reference
  interpreter and comparing the answers with an independent verifier.
- **Generalize.** Work for any tutorial, including algorithms that are not
  graphs, with as little human effort as possible.
- **Planned:** AI writes the EDGE spec; the workbench checks the AI's work and
  explains it to the author.

## Why

Tensor programs are hard to picture. Graph algorithms have many animations;
tensor execution has none. Specs written by people, and increasingly by AI,
contain errors that look correct. A spec that has been run and checked, shown
as its real trace, addresses both. The research direction is systems/PL, not
HCI: a language model as an untrusted compiler front end, kept honest by a
reference interpreter and differential testing.

## How it works

The author writes the program (`einsum.edge`), the explanation (the tutorial)
and an independent way to get the right answer (`verifier.py`). A model lowers
the program to IR, and is checked against the author's text rather than
trusted. edge-core-ir's evaluator runs the IR on the worked example and
records every step. The coverage gate and the verifier check that run, and
nothing is published if anything fails. The page only replays the recording.

```
inputs → tutorial → builder [model] → program → tutorial data [model] → instance → page
```

Planned: the human gives pseudocode, a small example with its expected answer,
and a choice of verifier; AI writes `einsum.edge` and the tutorial; Toluwa's
parser (in progress) replaces the model-written builder, so the AI step is
only at the start.

## What we have built

- The `check` pipeline above, with every model step paste-based (no API in CI).
- Four algorithms passing end to end: max-flow, set-cover, Bellman-Ford,
  direction-optimizing BFS (top-down). Bubble sort (case statements in a
  nested cascade) and DO-BFS bottom-up pass from scratch directories; bubble
  sort is a test fixture, not an example, until its verifier is approved.
- The page: per-Einsum drill-down, After Map / After Reduce grids, a
  before/after toggle, graph and bipartite views, typeset captions from the
  author's Graph and Einsum meanings.
- [AUTHORING.md](../AUTHORING.md), [issues-for-edge-core-ir.md](issues-for-edge-core-ir.md),
  and a draft `write-edge-tutorial` skill.

## Design decisions

| # | Decision | Why | Whose |
|---|---|---|---|
| 1 | The purpose is teaching: exact tensors, the iteration space | Tensor execution is what's hard to picture | Sanjana |
| 2 | The spec and the tutorial are the truth, not the IR | The IR is still changing; the author's intent is fixed | Sanjana |
| 3 | The language owner's interpreter is the only evaluator | A second evaluator drifted and needed hand-fixes | Sanjana |
| 4 | Gaps in the language become issues, never local patches (except issues 1, 2, 7, 8, 9, 10) | Semantics belong to whoever defines the language | Sanjana |
| 5 | An independent verifier is required, preferably a different algorithm | A second copy of the same method shares its mistakes | Sanjana; "different algorithm" Claude |
| 6 | A model fills toolchain gaps (builder, missing meanings) until they're built | Avoids building a whole compiler first | Sanjana |
| 7 | Author-run, no API in CI: pasted into a chat, or answered in-session by a local agent with the skill (see 32) | Cost and control; the public repo stays clean | Sanjana |
| 8 | Never change an author's Einsum; show sub-steps as labelled parts | The page must teach what the author wrote | Sanjana |
| 9 | Fixes must be generic | The goal is robustness for future algorithms | Sanjana |
| 10 | Free choices stay free (random), never fixed to "lowest index" | Fixing them changes what the spec claims | Sanjana; seeded randomness Claude |
| 11 | Captions come from the author's meaning lines, no word limit | Generated prose was accurate but confusing | Sanjana |
| 12 | After Map / After Reduce grids only when Map and Reduce combine | Readers misread Map-then-Reduce without the middle state | Sanjana |
| 13 | Staged pipeline; each stage lists every problem, then stops | Authors fix everything in one pass | Claude |
| 14 | Model replies are checked like author input; failures rewrite the prompt | The model is untrusted; the loop needs no extra tooling | Claude |
| 15 | One IR Einsum per written Einsum, no tensor the author didn't write | A builder invented helper tensors unnoticed | Claude, after Sanjana's objection |
| 16 | The tutorial's cascade is compared line by line with `einsum.edge` | Tutorial, notebook and spec had drifted | Claude |
| 17 | Coverage gate: every written Einsum must execute | An Einsum that never runs fails silently | Sanjana; per-IR-node counting Claude |
| 18 | Answer check on the worked example, the published answer and random instances | The worked example passes too easily | Claude |
| 19 | The picture type is decided from tensor ranks, in code | It's a fact about the data, not a guess | Claude |
| 20 | The worked example comes from the tutorial; model text must quote it | Every model sentence can be checked against the author's | Sanjana (source); Claude (quoting) |
| 21 | Ranking operators are part of the algorithm; unknown names stop the run | Guessing an operator would change the algorithm | Claude |
| 22 | One static `index.html`; replies saved so reruns are free | Easy to host and review | Claude |
| 23 | ~~The authoring skill guides; the author writes the Einsums~~ Superseded by 32 | Teaching, not ghost-writing | Sanjana |
| 24 | Forging a verifier approval need only take a deliberate, visible, out-of-repo act; no server | Stops "fix the check by editing the verifier" without infrastructure | Sanjana |
| 25 | In the AI flow the user chooses the verifier from a catalogue of kinds; if none fits it is built from source the user supplies (`user-reference`), and is approved like any other | The verifier must not come from the AI that wrote the spec | Sanjana |
| 26 | A verifier may import networkx, scipy, numpy and computational stdlib only; libraries need not be installed | A trusted library is the most independent verifier there is | Sanjana |
| 27 | The tutorial's published answer is pinned with the verifier; changing it needs the same approval | Otherwise the expected answer is the cheap thing to edit | Sanjana |
| 28 | What is compared is whatever the tutorial states as its answer (reached set vs visit order) | The tutorial is the claim being checked | Sanjana |
| 29 | `verifier.lock` (hash of verifier.py and of the published answer, KIND, METHOD, approver) must be HEAD's or in a ledger under `~/.config`; `approve-verifier` needs a terminal and the METHOD typed; `--committed-only` for tests | Implements 24 and 27 | Claude |
| 30 | The verifier is one file, read as text before it is imported: import allowlist, no `open`/`eval`/`exec`, `solve` and `answer`/`certify` share no route | Makes the hash cover the whole verifier; keeps the two answers independent | Claude |
| 31 | 12 random instances, instance k seeded by `slug:k`; gates on determinism, size, diversity and an `answer` that reads the cascade; all `solve` results computed before any cascade runs; the page line reports `k/12 agree` | A generator that makes one easy instance twelve times proves nothing | Claude |
| 32 | The skill drafts everything from a named algorithm, pseudocode or a program, answers `check`'s model steps in-session and runs `check` in a loop; it asks the author whenever something is unclear, and stops at three checkpoints: (A) pseudocode, worked example and its expected answer; (B) the cascade; (C) the verifier, which the author chooses and approves in their own terminal. After B the agent may not change an Einsum, the example or its answer without a yes, and never touches the verifier, lock or ledger | One agent writing the spec, example, answer and verifier would share one misunderstanding and agree with itself; the anchors it cannot control are the evaluator, the approved verifier, its random instances and the author's checkpoints | Sanjana; checkpoints Claude |
| 33 | `cases`, conditional cascades with macro expansion, and inner cascades are local patches to edge-core-ir (issues 8, 9, 10): a case statement is one IR Einsum with arms, a conditional cascade one cascade entry, IR nodes numbered depth first | Bubble sort and DO-BFS could not run; lowering a case statement to one Einsum per arm wrote a slice several times and lost the conditions | Sanjana (patch locally); Claude (design) |
| 34 | An arm of a case statement or of a conditional cascade must be exercised by the worked example or by one of the verifier's random instances; one the example never reaches is named on the coverage line and the page | The author's example is small and not ours to change, but an arm nothing runs is unchecked specification | Claude |
| 35 | One author directory, and one page, per cascade; `einsum.edge` names a cascade other than `edge_expression` with `- Cascade: <name>` | A tutorial may give several cascades (DO-BFS has three) and a page replays one run | Claude; open question for Sanjana |

## What worked

- **The independent verifier with random instances.** It caught errors every
  structural check passed: exact cover's `TPath`, missing vertices in
  Bellman-Ford, the `¬` before the reduce in DOBFS.
- **One evaluator, with the page replaying its trace.** It replaced a second
  evaluator that kept drifting.
- **Checking the model's output exactly like author input.**
- **The coverage gate.**
- **Authors' meanings over generated prose.**
- **Showing intermediate states** (After Map / After Reduce).

## What didn't work

- **A handwritten trace, then a separate JS evaluator.** Both drifted from the
  real semantics.
- **Letting the model restructure Einsums.** The set-cover builder split them
  into helper tensors without saying so.
- **Word limits on captions.** Length was never the problem.
- **Keeping copies in sync by hand.** Notebook, tutorial, site, `einsum.edge`
  and PDF all diverged.
- **Local patches to edge-core-ir.** They unblock us but are fragile:
  uncommitted, and lost when her code updates.
- **Acting beyond the request** (unreported Einsum changes, building a skill
  that was only meant as a planned step). Hence: ask, don't assume.

## What we learned

1. Running a spec finds mistakes structural checks miss; the independent
   verifier is the core of the system.
2. Empty values are the most common trap: a stored value equal to the empty
   value is absent.
3. Free choices are hidden claims: "any" versus "smallest" changes what a spec says.
4. Turning a notation into a running page tests the notation itself (occupancy
   in an Einsum, a Reduce inside parentheses, `¬` on an expression).
5. If AI writes the spec, the only independent checks left are the
   interpreter, the verifier and the human's stated intent. The verifier must
   not come from the same AI, and the AI must never edit it.
6. The publishable result is the checking loop for AI-written specs, measured
   on a set of real specs; the page is how people use it, not the claim.

## Open

- Toluwa's parser, to replace the model-written builder.
- Decisions on the edge-core-ir issues; getting the local patches upstream.
- DO-BFS hybrid: macros in `einsum.edge`, and the tutorial's missing α, β and
  declarations (issues file, "For the DO-BFS tutorial").
- Whether a remark such as `(j ≥ 1)` over an Einsum should restrict it
  (issue 10, question 2).
- Choosing which steps to show on long pages (DOBFS has 34).
- A non-graph algorithm, to test the sequence view.
- Rewriting the skill for AI-drafted specs.
- A set of AI-written specs with a count of which errors each check catches.
