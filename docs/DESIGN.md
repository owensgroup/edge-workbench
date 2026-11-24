# Design: goals, decisions and lessons

Status as of 2026-11-16. "Sanjana" marks decisions the project lead made;
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
  direction-optimizing BFS (hybrid: two macros and a conditional cascade,
  both directions on the worked example). Bubble sort (case statements in a
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
| 4 | Gaps in the language become issues, never local patches (except issues 2, 7, 8, 9, 10; issue 1 was patched, then removed as not allowed; issue 11 moved into the workbench, 2026-11-19) | Semantics belong to whoever defines the language | Sanjana |
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
| 36 | A macro is a section of `einsum.edge` in formal names and a multi-output case statement is a labelled statement with no IR node; the label map follows each call's bindings; a constant the cascade reads (`- Constants`) is part of the program and must be stated by the tutorial; an operation written with no action runs with the paper's default pass-through merge | The DO-BFS page should show the hybrid, written as the tutorial writes it. Thresholds as inputs would have needed the approved verifier's instances to supply them. §7.3.4 says what an unwritten merge means, so nothing is invented | Sanjana (hybrid only; α = 15, β = 18); Claude (syntax, constants, merge reading) |
| 36 | One approval per new verifier, asked for at the end of `check`, covering the verifier and the published answer; approval may also be given in Claude Code: the agent shows the whole file and its sha, runs `approve-verifier --confirm METHOD --sha`, and `.claude/settings.json` forces a permission prompt for it and denies the agent writing the lock, the ledger or `EDGE_WORKBENCH_LEDGER` | Two approvals per tutorial confused the author; a terminal-only step broke the flow. The person's click stays the approval, the sha binds it to the file they read, and the lock records how it was given | Sanjana; mechanism Claude |
| 37 | A Populate with a mutable rank is shown round by round, from a record of each round (the driver watches the coordinate operator it hands the evaluator; an edge-core-ir patch, issue 11, until 2026-11-19): the fiber's pre-state, the candidates in the order the schedule offered them, the coordinate operator's write-del set, W, D, the check W ∩ (dom(S) ∪ D) = ∅ and the state after. The page looks rounds up and never decides what an operator keeps; a free choice is shown as free, with every eligible candidate and the schedule that put the held one first | The page showed a Populate as independent points and a result, which is how a Map executes, not a Populate. Working the rounds out in the page would be a second evaluator (3) | Sanjana (show exactly how it executes; the paper's Inset 4); Claude (recording, layout) |
| 38 | The users are outside authors working with an AI agent. The tool installs and runs without cloning this repository or edge-core-ir beside it; author directories live anywhere; the skill ships as an installable plugin | A sibling checkout and a skill inside this repository only work for us | Sanjana (2026-11-16) |
| 39 | The edge-core-ir patches go to Toluwa's main as one pull request per issue, smallest first (7, 2, 8, 9, 10; 1 was ruled not allowed and 11 moved into the workbench, 2026-11-19). Until each merges the workbench pins a commit, `check` refuses a different one, and every page names the unreviewed patches its run used | Toluwa has not seen the patches (2026-11-16); pages present their semantics as the reference's. An uncommitted tree cannot be reproduced by anyone else | Sanjana; pinning and the page line Claude |
| 40 | Wait for Toluwa's parser. The model-written builder stays behind one seam, `lower(einsum.edge) -> Program`, and gets no further investment; the workbench does not write its own lowering | The parser is close; a second front end would be thrown away | Sanjana |
| 41 | The one approval also pins the cascade (`einsum.edge`, declarations) and the worked example, not only the verifier and the published answer | "After checkpoint B the agent changes nothing without a yes" was a rule in the skill only; the agent is untrusted, so the tool enforces it | Sanjana; Claude (proposal) |
| 42 | Nothing *publishable* is written while a check fails. A watermarked draft page is, and when a random instance disagrees, a page for the smallest failing instance; `publish` refuses both. Replaces "nothing is written while a check is failing" (22) | A wrong spec is when the author most needs to see what it does | Sanjana; Claude (proposal) |
| 43 | For a tutorial written through the skill, the tutorial's `edge_expression` LaTeX is generated from `einsum.edge`. For a ported tutorial the two are still compared line by line (16). Narrows 2 | One source cannot drift; a port's LaTeX is its author's and stays | Sanjana; Claude (proposal) |
| 44 | An arm no instance exercises fails `check`, unless the author supplies an extra pinned instance that reaches it. Tightens 34 | A larger example does reach DO-BFS's switch back to top-down (Sanjana tried it); a page with a branch nothing ran is not verified | Sanjana; mechanism Claude |
| 45 | The site's CI is the publishing gate: edge-algorithms reruns `check --committed-only` on each pull request, with scipy and networkx installed, and a maintainer reviews the verifier there | An outside author's local approval protects them from their own agent, not the site from them | Sanjana; Claude (proposal) |
| 46 | The generational rank is read from the `ranks:` block (`generational`), with `I` as the fallback | Whether `I` stays fixed is undecided (SpMV); reading the declaration needs no decision | Claude; Sanjana undecided on `I` |
| 47 | The claim is "AI-written specs are verified", meaning tested: every Einsum ran, and the result agreed with an independent verifier on the worked example and on random instances. It is reported with a measured miss rate from a set of injected faults. "Prove" in the goals above means this | Agreement on a dozen small instances is evidence, not proof; without a miss rate the claim cannot be judged | Sanjana (claim); Claude (wording, miss rate) |
| 48 | The plain explanation of an algorithm is written once, in the tutorial (the idea, the worked example as a picture with its answer, numbered pseudocode, a name and a pseudocode line for each Einsum), and the page shows a short recap from the same fields. `check` requires them | Neither the tutorial nor the page says what the algorithm does before the tensors start; a reader arriving at either has no way in | Sanjana (asked for it); Claude (single source, fields) |
| 49 | Proposed, not yet agreed: a catalogue of maintainer-approved verifiers keyed by problem; a relabelling check (permute the coordinates of a `vertex` rank, expect the answer permuted the same way); `check --json` with a stable code per finding | A verifier the agent drafts is the least independent kind; hidden dependence on coordinate order passes every current check; the agent loop and the fault study both need findings as data | Claude |
| 50 | Proposed: which steps a page shows by default. The trace is never cut. The default tour is the first generation in full, the first step with each new *signature* (which Einsum and arm ran; empty output; a merge dropped something; a Reduce folded more than one value; a Populate had a real choice or deleted an entry; a value was overwritten; the stop condition held), the step that writes each final answer value, the last generation, and the moments the author names. Everything else folds into labelled, expandable bands, and the page says how many steps it shows of how many. `check` fails if an Einsum or an arm is missing from the tour. An algorithm with many Einsums per generation is stepped by pseudocode line, leading with loop-carried state; inside one Einsum, one point of each kind. Details under "Which steps to show" | Max-flow has 122 steps and set-cover 82. A cut-off or a sample hides behaviour; a model's choice cannot be checked; "something new happened" can be read off the trace, and it is the coverage gate's idea applied to the page | Claude; answers the open item on long pages |
| 51 | Proposed: no model step inside `check`. The worked example is structured data in the tutorial's front matter, written by the author or the agent, and its picture and prose are generated from it; the styling is derived (19). With the parser (40) nothing in `check` asks a model. Replaces 6, 7, 14 and 20 when the parser lands | The last model step extracts the example from prose and is checked by matching quotes. Without it `check` is deterministic, CI runs from sources alone, and no reply files are committed | Claude |
| 52 | Proposed: one home for a tutorial. The author directory (tutorial, `einsum.edge`, verifier, lock) lives in the site repository and the tool runs there; this repository keeps test fixtures only. One directory may hold several cascades that share a tutorial and a verifier. Revises 35 | `examples/` holds copies of the site's tutorials with differences "to carry back", which is "keeping copies in sync by hand" again. One directory per cascade makes DO-BFS three copies of one tutorial | Claude |
| 53 | Proposed: the trace is the artefact. `check` writes a versioned, hashed `trace.json` holding changes, not a snapshot of every tensor per Einsum; one shared viewer renders it; a single-file page remains as an export. Revises 22 | Every page inlines its own copy of the viewer (160 to 900 KB), so a viewer fix means re-running every algorithm. Snapshots will not hold for the larger instances arm coverage needs (44). A separate trace makes embedding (48) simple | Claude |
| 54 | Proposed: the site's CI runs outside authors' Python sandboxed and with no secrets; a maintainer's approval is a code-owner review on `verifier.py` and the lock; a `*_functions.py` may define only operators `einsum.edge` names | 45 makes the site execute strangers' verifiers. For an outside author the approval that matters is a maintainer's. An operator that implements the algorithm passes "no helper tensor" (15) | Claude |
| 55 | Proposed, for authors: a finding names a file and a line; one manifest (input hashes, stage results, tool and edge-core-ir versions) replaces renaming replies to `.applied` and `.rejected`, and unchanged stages are skipped; commands `new` (scaffold), `doctor` (environment), `serve` (rebuild and reload the draft on save); the tool, not the skill, stops a loop when one finding code recurs three times | Findings are sentences. Stage state lives in file names. The three-times rule is in the skill only, and the agent is untrusted | Claude |
| 56 | Proposed, verification breadth: every instance up to a tiny size (all graphs on three vertices) beside the random ones; and every change of the pinned edge-core-ir commit rebuilds all traces and reports which changed | Exhaustive tiny instances find more than twelve random ones and fail already minimal. The verified specs are a regression suite for edge-core-ir, which is something to offer Toluwa with the pull requests (39) | Claude |

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

## The page and the tutorial: review of 2026-11-16

Five pages (Bellman-Ford, set-cover, max-flow, DO-BFS, and Bellman-Ford at
phone width) and the site's home page and Bellman-Ford tutorial were rendered
and read as a newcomer would. The data on the page is sound and several ideas
work (hatched empties, read and write outlines, before/after, After Map /
After Reduce). What is wrong is that the page is written for someone who
built the tool. All of this section is Claude's review; nothing here is
decided except 48.

### Broken

| # | What | Where |
|---|---|---|
| B1 | DO-BFS draws six vertices stacked in one column with no visible edges: every position has the same x. The root is vertex 1 and vertex 0 is unused; the layout likely starts from 0 (not confirmed) | `author.make_instance`, `_layered` |
| B2 | At phone width the Einsum panel is off screen: the two columns never wrap, and the left one is a fixed 560px | page CSS |
| B3 | The verifier's method and "k of 12 agree" are nowhere on the page. `T["note"]` is computed and never rendered | `build_page.py` |
| B4 | Node labels (`d=1`, `e=3`) overlap nodes and edges | `domain_views.js` |
| B5 | The site-title link is `href="/"`, which breaks under a base URL | page template |
| B6 | The final answer appears only on the last step, in small green text | page template |
| B7 | The CSS has an orphaned rule body with no selector near the top, and the `h3` label style is repeated four times | page template |

### Words

- **Terminology drifts against our own rule.** "next iteration", "carry state
  across iterations", "improved this round". It is *generation* everywhere,
  and *round* only for a Populate.
- **Strings that describe the tool.** "Initializations are not cascade
  Einsums." (a greyed section on the first screen of every page); "16 points
  in the iteration space, each computed independently of the others; 2
  produced values".
- **Evaluator output shown as explanation.** The Populate panel: "write-del
  set: Write [1,3] (3 of 4 locations None)", "value from compute operator
  identity", Python's `None`. Correct, and unreadable before level 3 (below).
- **The legend.** One run-on sentence about empty values, and swatches for
  colours the page does not use (`negative` and `stored 0` on Bellman-Ford).
- **"Meaning" and "Einsum meaning"** do not say how they differ. The tutorial
  calls the first "Graph meaning".
- **Steps are called `E01`.** The tutorial already names them: Relax, Improve,
  Record, Update, Stop.
- **Undefined on the page:** `⋀ ⋁ ⋘ ∩ ∪ :: 𝟙`, rank, fiber, iteration space,
  generation, cascade, empty.
- The footer is filler.

### Look

- Labels at 9 to 11px, uppercase, letter-spaced, in light greys (`#aaa`,
  `#bbb`, `#c4c4c4`); body text at 13px.
- Eight accent colours (blue, orange, purple, teal, green, yellow, red,
  brown), each meaningful, with no key and no single meaning across panels.
- Five typefaces. Pills, tinted boxes and left-border callouts on most blocks.
- Two `▶` buttons side by side that do different things.
- Large empty areas; a blank spacer heading inside each tensor panel.
- Click targets of 23 by 19px; descriptions only on hover, so not on touch;
  several states shown by colour alone.
- MathJax and a webfont load from CDNs, so the "one self-contained file" is
  not self-contained offline.

### The site (edge-algorithms)

- **Nothing explains the algorithm plainly.** The tutorial opens with "Status
  Intro", then a problem statement listing tensors with ranks and empty
  values. No idea paragraph, no pseudocode. The summary line already says
  "expressed as a four-step extended Einsum iterated to a fixed point".
- **No picture of the worked example.** The graph is text
  (`0→1 (10), 0→2 (1) …`); the only drawing is in the walkthrough, behind a
  button that opens a new tab.
- **The meaning lines made the walkthrough repeat itself.** Each step has its
  paragraph, then a Graph meaning, then an Einsum meaning; for Update the
  Graph meaning is the paragraph's own sentence again. We asked for those
  lines, and as visible prose they cost the reader.
- **The hand trace is a static copy of the walkthrough,** written by hand and
  compared with nothing.
- **Headings are schema keys:** "Status Intro", "Working Example Part 1",
  "Working Example Part 2", "Other Notes".
- **Two visual systems.** The site: warm paper, teal accent, Source Sans at a
  readable size, 1000px. The page: grey, blue accent, 13px system font,
  1500px. Only the header matches.
- The home page describes itself by its implementation ("full LaTeX support
  via MathJax"), lists tutorials alphabetically with no starting point, and
  the layout hard-codes four walkthrough link slots. In the build looked at,
  2 of 15 tutorials link a walkthrough.

### The page's code

- `build_page.py` is 1,810 lines: a script that runs at import, driven by
  environment variables, holding the template, the CSS and the viewer's
  JavaScript as one Python string, with the coverage and answer gates inside
  it (phase 3).
- Comments in the template and the CSS tell the history of each decision
  ("It used to be ...", "Nobody pressed it"). History belongs in this file.

## Target design for the page and the tutorial

The order a newcomer needs: what problem, what example, what answer, what the
algorithm does in words, then the same thing as Einsums, then the tensors.

### One source: tutorial fields the page reads

`check` requires each of these (48). The page and the tutorial both render
them; neither restates them.

| Field | What | Checked how |
|---|---|---|
| `idea` | Two to four plain sentences: what the algorithm does and why it works. No notation | Present; no `$` |
| `example` picture | Not written: drawn from the worked example instance by the same view the page uses | Generated |
| expected answer | Already published by the tutorial; shown beside the picture | Pinned in the lock (27) |
| `pseudocode` | Numbered lines, the author's or the source's wording | Present; lines numbered |
| step `name` | One or two words per Einsum (Relax, Improve) | Every label has one |
| step `line` | The pseudocode line each Einsum implements | Every Einsum cites a line; every line is cited or marked "no Einsum" |
| `graph` / `einsum` meaning | As now, but stored per step as data, not as two extra paragraphs of prose | As now (11, 20) |
| trace table | Not written: generated from the evaluator's run | Generated |
| `example` instance | The worked example as data (extents, tensors, coordinate sets), not prose (51) | Supplies exactly the program's inputs, as now |
| `moments` | A few steps the author says matter: generation, step name, one sentence ("generation 1, Relax: vertex 1 improves from 10 to 2") (50) | Each one happens in the trace |

### The page

1. **Opens on an overview, not on step 1.** The idea, the picture of the
   example, the input in words, the answer, and one line of trust: "Checked
   against Floyd-Warshall on this example and 12 random graphs." Then Start.
   A returning reader collapses it once and it stays collapsed.
2. **Three levels, the first one open.**
   - Level 1: the step's name and pseudocode line, the picture, the Einsum,
     what changed.
   - Level 2: the operand grids and After Map / After Reduce.
   - Level 3: how one value is computed; Populate round by round (37).
   Nothing is removed; levels 2 and 3 open on demand and remember their state.
3. **Pseudocode beside the Einsum**, the current line highlighted, so "relax
   every edge" sits next to `N = G · D` at every step.
4. **What changed, as a line of data.** "D[1]: 10 → 2", read off the trace.
   A step that writes nothing says so, and a toggle skips such steps.
5. **The picture and the grids are one thing.** Pointing at a vertex lights
   its row and column in every grid; pointing at a cell lights its vertex or
   edge. This is the idea the whole notation rests on, and today the two
   halves of the screen do not refer to each other.
6. **The formula and the grids are one thing.** Each operand in the Einsum
   has the colour of its grid's outline; pointing at one lights the other.
7. **A notation key.** Each of `⋀ ⋁ ⋘ ∩ ∪ :: 𝟙` has a one-line definition
   on hover and on tap; one "EDGE in a minute" block shared with the site.
   A glossary of seven words: rank, coordinate, generation, cascade,
   iteration space, empty, fiber.
8. **Map, Reduce, Populate drawn the same way every time**: three fixed
   slots in a fixed order, the ones an Einsum does not use greyed out.
9. **Empty explained in the problem's words**, per tensor, from the
   author's tensor note: "hatched = not reached (∞)". Clicking an empty cell
   says why it is empty (which operand was absent under which merge), as
   clicking a value says how it was computed.
10. **Axes in words:** "from s", "to d", and the author's vertex labels,
    not `S:s\D:d`. A tutorial that numbers from 1 does not show a vertex 0.
11. **A timeline, not a bare slider:** generation boundaries marked, each
    step labelled with its name, the current generation named. Buttons:
    previous step, next step, play, next generation, each with a word.
12. **A legend of what this page uses**, one colour one meaning everywhere:
    read, written, changed, empty, and the algorithm's own states.
13. **Every step has an address** (`#step-7`), so the tutorial's text and an
    author's message can point at one.
14. **One visual system with the site:** its palette, its two typefaces,
    body text at 15 to 16px, labels no smaller than 12px and dark enough to
    read, one column below about 900px.
15. **A provenance line at the foot:** edge-core-ir commit, unreviewed
    patches used (39), verifier kind and method, instances agreed, approver.
16. **Every string rewritten for a reader**, in the paper's terms.
    Evaluator vocabulary only at level 3.

### Which steps to show (50)

Two problems with two answers. Neither removes a step from the trace.

**A long run: many generations of the same Einsums.** Show a step when it
does something the reader has not seen; fold the rest.

1. Each step gets a signature, read off the trace: the Einsum and the arm
   or macro; whether the output was empty; whether a merge dropped
   something; whether the Reduce folded more than one value; whether a
   Populate had more than one candidate in a fiber, or deleted a held entry;
   whether an existing value was overwritten; whether the stop condition
   held.
2. The default tour: the first generation in full; the first step with each
   new signature; the step that writes each final answer value; the last
   generation; the author's `moments`.
3. The rest folds into bands that say what they hold ("generations 4 to 17:
   same pattern, 9 cells of D changed") and open on demand.

**A complicated algorithm: many Einsums per generation.** Group, do not
filter.

1. Step by pseudocode line by default; a line's Einsums open beneath it.
2. Lead with the loop-carried tensors (`tensor_facts.stateful`);
   intermediates fold into their line.
3. Inside one Einsum, one point of each kind (computed, dropped by the
   merge, folded by the Reduce), not every point.

**Guards.**

- The page says what it hides: "showing 23 of 122 steps; the other 99
  repeat a pattern already shown".
- `check` fails if any Einsum or arm is missing from the default tour.
- A budget, not a cut-off. Over budget, keep in this order: first
  generation, arms, the author's moments, the stop. The number is set by the
  five-person test, not guessed.
- No model chooses steps. An author's `moments` are the only human
  judgement, and each is checked against the trace.
- The larger instance that reaches an arm (44) need not be the page's
  example: the page stays on the small one and shows the excerpt of the
  larger run where that arm first fires.

### The tutorial and the site

1. **Section order:** the idea; the worked example (picture, answer);
   pseudocode; EDGE in a minute; the cascade step by step; the full
   expression; then variants, complexity and notes, collapsed.
2. **Each step is one card:** name, pseudocode line, Einsum, what it does to
   the graph, what it does to the tensors. No third paragraph.
3. **The walkthrough sits in the tutorial**, where the worked example is,
   with a full-screen link. Open: the tutorials are mostly Toluwa's, so this
   needs her agreement. The fallback is a separate page that shares the
   fields and the visual system.
4. **The trace table is generated** from the run.
5. **Headings a reader would use**, not schema keys.
6. **A "Start here" page:** what EDGE is, how to read a tutorial, with BFS
   as the first; the home page ordered by difficulty and marking which
   tutorials have a walkthrough.

### How we will know

Five people who have not seen EDGE, three tasks on one page, no help:
say what the algorithm computes; say what one named step did to the graph;
say why one named cell is empty. Run it before the rebuild and after. This
is the only measure of "understandable" we have; everything above is a guess
until it is run.

## Build plan

For whoever builds this (Opus, with the hardest phases to Fable subagents,
per CLAUDE.md). Phases are in dependency order. Each ends with a test that
either passes or does not. Rules that hold throughout: the rules in
CLAUDE.md; no phase starts while another session has uncommitted work in the
files it touches; every phase that should not change a page proves it by
building all examples before and after and comparing the files.

**Needs a person before anything starts**
- Toluwa sees the patches (39). As of the evening of 2026-11-16 they are
  still uncommitted in her checkout.

(Done since the review: the populate-rounds work is committed, and
bubble-sort's verifier is approved.)

**Phase 0. Freeze**
1. Start from a clean, committed workbench.
2. Put the edge-core-ir patches on a branch, one commit per issue; open the
   pull requests in the order of 39.
3. Record the pinned commit in the workbench; `check` prints it and refuses
   a different one.
4. Fix `test_a_value_equal_to_empty_is_reported`: the instance check no
   longer reports a stored value equal to the empty value (lesson 2).
5. CI: `npm test` with `--committed-only`.

*Done when:* fresh clones of both repositories at the pinned commits pass
both suites.

**Phase 1. Installable (38)**
1. `edge-ir` as a pinned dependency; the sibling-checkout search becomes a
   development override.
2. Author directories anywhere; nothing assumes `examples/`.
3. The skill as an installable plugin.
4. Model-written Python (the builder, `*_functions.py`) is screened as the
   verifier is (30) before it runs, and runs with no network and a
   temporary working directory.
5. `new` scaffolds an author directory; `doctor` checks the environment
   (edge-core-ir commit, node, verifier libraries) (55).

*Done when:* a clean machine goes from install to a passing example with
neither repository cloned.

**Phase 2. One seam to edge-core-ir**
1. One adapter module is the only place that imports `edge_ir`; a test fails
   on any other import.
2. The `evaluate_einsum` wrapper becomes a per-Einsum callback (issue 6), on
   the patch branch.
3. The private helpers taken from her validator (`_can_meet`, `_RankKey`,
   ...) are reached only through the adapter.

*Done when:* every example page is identical before and after.

**Phase 3. Gates as stages; the renderer as a function**
1. Coverage and the answer check move out of `build_page.py` into stages
   that return data. No environment variables, no reading stdout.
2. `build_page.py` becomes a function from (trace, tutorial fields, facts)
   to HTML. Its template, CSS and JS become three files, inlined at build,
   so the output is still one file.
3. Every finding gets a stable code; `check --json`; one JSON line per
   finding per run in a log (49).
4. `author.py` splits into orchestration, instance derivation and report.
5. A finding names a file and a line: from the surface reader now, from the
   parser's source spans when it lands (55).
6. One manifest per author directory replaces the `.applied` / `.rejected`
   renames; a stage whose inputs are unchanged is skipped (55).
7. `check` stops and says so when one finding code recurs three runs
   running (55).
8. `trace.json` becomes a written, versioned, hashed artefact holding
   changes; the viewer reads it; the single-file page is built from the two
   (53). `serve` rebuilds and reloads on save (55).

*Done when:* pages identical before and after; tests assert on codes.

**Phase 4. Tutorial fields (48)**
1. Add the fields of "One source" to the tutorial schema and to
   AUTHORING.md.
2. `check` requires and checks them, with a code per failure.
3. Generate the example picture and the trace table from the run.
4. Meanings stored per step as data.
5. Add the fields to all seven examples, from each tutorial's own words;
   where a tutorial has no pseudocode, ask its author.
6. The worked example as an `example` instance block; its picture and its
   sentence generated; the tutorial-data model step removed (51).
7. The `moments` field, each checked against the trace (50).

*Done when:* all examples pass with the fields present, and removing any
one of them fails `check` with its code.

**Phase 5. The page**
Run the five-person test once on the current page first.
1. Fix B1 to B7.
2. The visual system (item 14) and the legend (12).
3. The overview, the three levels, the pseudocode pane, the change line
   (items 1 to 4).
4. Linking: picture to grids, formula to grids (5, 6).
5. The notation key and glossary; the fixed Map, Reduce, Populate slots;
   empty explained; axes in words (7 to 10).
6. The timeline and step addresses (11, 13); step signatures, the default
   tour, the bands and the tour gate in `check` ("Which steps to show", 50).
7. The provenance line (15).
8. Every string reviewed against "Words" above (16).
9. `tests/check_pages.js` grows a check per item: the overview is present,
   every step has a name and a line, no label under 12px, the page has no
   horizontal scroll at 390px, every glyph in a formula has a definition,
   the words "iteration" and "round" appear only where the paper allows.

*Done when:* the checks pass on every example, and the five-person test is
run again and its results are written under "What we learned".

**Phase 6. Understanding a failure (42)**
1. A watermarked draft page when a gate fails; `publish` refuses it.
2. On a disagreeing random instance: shrink it, build its page, open on the
   first step whose output differs from what the answer needs where that can
   be told, otherwise on the last step.
3. The failing gate and its finding code at the top of a draft.

*Done when:* a deliberately wrong merge in a copy of Bellman-Ford yields a
draft page on a failing instance of at most four vertices.

**Phase 7. Trust (41, 44, 45, 49)**
1. The lock covers the cascade and the worked example; one approval.
2. An unexercised arm fails; `- Instances` supplied by the author are
   pinned.
3. The relabelling check.
4. The verifier catalogue, each entry approved by a maintainer.
5. The site's CI job, sandboxed and with no secrets; code-owner review on
   `verifier.py` and the lock (54).
6. Every instance up to a tiny size, beside the random ones (56).
7. A functions file may define only operators `einsum.edge` names (54).
8. One test per attack: an Einsum edited after approval; a functions file
   that implements the algorithm inside one operator; an arm nothing runs;
   a lock copied from another example.

*Done when:* each attack fails `check` with its own code.

**Phase 8. The site**
Needs Toluwa's agreement on embedding (item 3 of "The tutorial and the
site"); without it, do the rest.
1. The shared "EDGE in a minute" include and glossary.
2. The layout renders the new fields, the step cards and the new section
   order; headings renamed.
3. The walkthrough embedded, or linked, per her answer.
4. "Start here", and the home page ordered.
5. `publish` writes whatever the layout needs and nothing else.
6. Author directories move to the site repository; this repository keeps
   fixtures (52). Several cascades in one directory, and the layout's four
   link slots become a list.
7. A change of the pinned edge-core-ir commit rebuilds every trace and
   reports which changed (56).

*Done when:* the site builds, every tutorial with a walkthrough shows the
idea, the picture and the pseudocode above the first Einsum, and the
generated trace table matches the page.

**Phase 9. Front end (40, 43)**
1. `lower()` with the builder behind it.
2. When the parser lands: run both, report differences as findings, then
   remove the builder and the model step.
3. Generate `edge_expression` for skill-written tutorials.
4. With no model step left (51), remove the prompt and reply files and the
   paste-into-a-chat path.

*Done when:* swapping the implementation changes no page.

**Phase 10. Generalise (46)**
1. The generational rank from `ranks:`.
2. SpMV, one dynamic program, one sort, each with the view it needs.

*Done when:* three non-graph pages pass with no algorithm-specific code.

**Phase 11. Evidence (47)**
1. A fault injector over passing specs: wrong merge, wrong compute, swapped
   rank, wrong empty value, dropped Einsum, `i` for `i+1`, a free choice
   made fixed.
2. For each fault, which gate caught it, from the log of phase 3; the miss
   rate.
3. The skill on a held-out list of algorithms: first-run pass rate, runs to
   pass, findings by code.

*Done when:* one table of fault class against catching gate, with the miss
rate, and one of the held-out runs.

**Phase 12. The skill and the documents**, last, against the finished tool.

## Open

- Toluwa's review of the patches (39) and her agreement on embedding the
  walkthrough in the tutorial.
- Whether `I` stays the fixed generational rank (46).
- Agreement on 49 to 56, which are proposals.
- Agreeing with Toluwa, now, that her parser reads `einsum.edge` as written
  here (`- Macro`, `- Constants`, `- Cascade:`) (40).
- Whether MathJax and the webfont are vendored into the page or loaded.
- Toluwa's parser, to replace the model-written builder.
- Decisions on the edge-core-ir issues; getting the local patches upstream.
- DO-BFS hybrid: the questions left for the tutorial (issues file, "For the
  DO-BFS tutorial"): the merge of the unwritten division, and a switch back
  to top-down that no small graph can take.
- Whether a remark such as `(j ≥ 1)` over an Einsum should restrict it
  (issue 10, question 2).
- The step budget for long pages (50 proposes how steps are chosen; the
  number waits for the five-person test).
- A non-graph algorithm, to test the sequence view.
- Rewriting the skill for AI-drafted specs.
- A set of AI-written specs with a count of which errors each check catches.
