---
name: write-edge-tutorial
description: Turn a named algorithm, pseudocode or a program into a complete EDGE tutorial for edge-workbench — problem statement, tensors, rank kinds, extended Einsums, a hand trace, the tutorial .md and einsum.edge — then run `python3 -m edge_workbench check`, answer its model steps in-session, and loop until the page passes, stopping at fixed checkpoints for the author. Use when someone wants an EDGE spec, Einsums or a tutorial written, converted or validated.
---

# From an algorithm to a passing EDGE page

You draft; the author decides. You write the Einsums, the tutorial and
`einsum.edge`, run `check`, and answer the prompts it writes. The author
signs off at three checkpoints and owns the verifier.

Read first, once: [AUTHORING.md](../../../AUTHORING.md) (the contract `check`
enforces), [rules.md](rules.md) (how to write Einsums that are right and that
the tool can run), and one passing example end to end —
[examples/bellman-ford/](../../../examples/bellman-ford/) is the shortest,
[examples/maximum-flow/](../../../examples/maximum-flow/) the richest. The
notation is the EDGE paper's (`docs/references/EDGE.pdf`); use its terms:
generational rank, generation, cascade, iteration space, coordinate.

## Why the checkpoints exist

If you write the Einsums, the example, its answer and the verifier, they will
share one misunderstanding and agree with each other. The page is only
trustworthy because some things do not come from you:

| anchor | who owns it |
|---|---|
| the problem and the pseudocode the cascade must follow | the author (checkpoint A) |
| the worked example's expected answer | the author, or the approved verifier's `solve` — never you alone |
| the cascade as approved | the author (checkpoint B) |
| `verifier.py`, `verifier.lock`, the approvals ledger | the author (checkpoint C); you never edit them |
| what the cascade computes | edge-core-ir's evaluator |

## Asking the author

This skill is a conversation. When something is unclear, ask; do not pick
an answer and carry on. Use the `AskUserQuestion` tool when it is available
(up to four questions at once, 2–4 options each, your recommendation first and
marked "(Recommended)", one line on what each option changes); otherwise ask
in chat as a short numbered list. Make each question stand on its own: the
author may see only the dialog.

**Always ask, never guess:**
- which variant and which source, for a named algorithm;
- any free choice or tie-break the pseudocode leaves open ("any" vs
  "smallest");
- an empty value whose choice changes which entries exist (a weight-0 edge, a
  height-0 vertex);
- what the answer is and where it is read from, when the source is not
  explicit;
- the worked example's expected answer, when the author or the source has not
  stated one;
- a rank whose kind is not obvious (a DP table's axes, a location);
- anything that would change an approved Einsum, the example or its answer;
- which verifier kind to use.

**Do not ask** what a file, the paper, AUTHORING.md or `check` can answer:
look it up. Batch questions at the end of a phase rather than one at a time,
except when the answer changes what you write next. Record each answer in one
line in the change log, so the report shows what the author decided.

The three checkpoints are questions too: show what is being approved, then
ask "approve / change something", with the changes to discuss as options
where you can foresee them.

## Hard rules

- **Never edit `verifier.py`, `verifier.lock` or anything under
  `~/.config/edge-workbench/`**, never set `EDGE_WORKBENCH_LEDGER`, and never
  run `approve-verifier` (it needs the author's own terminal). If `check`
  says the verifier is unapproved or changed, stop and tell the author.
- **After checkpoint B, an Einsum, a declaration, the worked example or its
  expected answer changes only with the author's yes.** Show the line, the
  failing evidence and the proposed change; wait.
- **Never edit edge-core-ir.** A gap in the language is a finding for
  `docs/issues-for-edge-core-ir.md`, reported to the author, not worked around
  with a helper tensor or an invented operator.
- **Free choices stay free.** Where the pseudocode says "some"/"any", do not
  pick "smallest"; ask if unsure.
- Do not commit or push.

## Phase 1 — Intake and the pseudocode

The author gives one of:
- **a well-known algorithm by name** — ask which variant and which source
  (textbook, paper, a page); write numbered pseudocode from that source and
  cite it. Do not write it from memory without saying so.
- **pseudocode** — keep the author's wording and numbering.
- **a program** — extract numbered pseudocode from it and cite line ranges.
- **an existing tutorial** (e.g. `edge-algorithms/_algorithms/<name>.md`) —
  see "Porting an existing tutorial" below; it skips most of Phases 1–4.

Then agree with the author, as short answers:
1. Initialization, loop body, stopping condition, and where the answer is read.
2. Every free choice ("while some v has e(v) > 0" never says which v) and
   every branch ("if some w … else …"). A free choice becomes a populate; a
   branch needs its test answered before either arm writes.
3. The worked example: the smallest instance that exercises every step and
   the case that separates this algorithm from a naive one (Bellman-Ford's
   re-relaxation, BFS's shared child). Prefer one the author or the source
   publishes.
4. **Its expected answer, stated by the author or the source.** If neither
   gives one, mark it "to be computed by the verifier" and do not publish a
   number of your own.

**Checkpoint A:** show the pseudocode, the example and its expected answer;
get an explicit yes. Everything after is judged against this, not against
what the algorithm "usually" does.

## Phase 2 — Tensors, empty values, rank kinds

For every piece of data in the pseudocode, inputs and intermediates alike:
name, ranks with extents (`S = |V|`), type, empty value. Which rank is
generational (usually `I`, with no shape). Then each rank's kind for the
`ranks:` block: `generational`, `vertex`, `set`/`element`, `position`,
`spatial` (AUTHORING.md). No other word.

Choose every empty value on purpose; see rules.md. State each one to the
author with its reason in one line.

## Phase 3 — The cascade

One Einsum per pseudocode step, in order, initialization first, the stop
condition `⋄ :` last. Follow rules.md. For each Einsum keep a one-line noun
phrase (it becomes the `# E01:` comment) and a note of which pseudocode line
it implements.

Before showing it, check it yourself against rules.md's expressibility list:
anything the IR cannot run as one IR Einsum is a finding now, not a surprise
at the program stage.

**Checkpoint B:** show the cascade in LaTeX, each Einsum beside its
pseudocode line, plus the declarations, the empty values and the `ranks:`
block. Get an explicit yes.

## Phase 4 — Hand trace

Walk the worked example one generation and one Einsum at a time, writing the
non-empty entries of each output as a table (it becomes
`working_example_part2`). Stop at the first entry that disagrees with the
pseudocode's behaviour; that is a bug in the cascade or in the trace, and
fixing an approved Einsum needs the author's yes. The final state must give
the checkpoint-A answer.

## Phase 5 — The files

In one directory `<slug>/` (copy the layout of an example):

- **`<slug>.md`** — front matter keys: `title`, `authors`, `summary`, `tags`,
  `ranks`, `status_intro`, `problem_statement` (declarations and the
  empty-is-absent sentence), `working_example_part1` (the instance and its
  expected answer), `working_example_part2` (the trace),
  `edge_expression_walkthrough`, `edge_expression`, `other_notes`,
  `complexity_costs`, `related_notes`. Under each formula in the walkthrough,
  after it:

  ```
  **Graph meaning:** what this step does to the graph or data.

  **Einsum meaning:** what the Einsum does, in tensor terms.
  ```

  Write meanings for initialization and the stop line too. Sentences belong
  here; `einsum.edge` gets only noun phrases.
- **`einsum.edge`** — the same cascade in ASCII (AUTHORING.md §2), line for
  line with `edge_expression`: every tensor declared (inputs too), every
  Einsum labelled `# E01:` … in order. `check` compares the two Einsum by
  Einsum.

## Porting an existing tutorial

The tutorial's Einsums were already written and reviewed by its author, so
they count as approved: you transcribe, you do not redesign.

1. **Copy, do not move.** Make `<slug>/` and copy the tutorial in as
   `<slug>.md`. Never edit the original (it belongs to the site repo); every
   change goes into the copy and is listed in the report as a diff to carry
   back.
2. **Read it whole**: problem statement, declarations, worked example,
   `edge_expression`, walkthrough.
3. **Checkpoint A, short form:** state the worked example and the answer the
   tutorial publishes for it, quoting the tutorial. If it publishes none, ask
   the author for one (or mark it "to be computed by the verifier").
4. **Transcribe `einsum.edge`** line for line from `edge_expression`
   (AUTHORING.md §2): every tensor declared (add undeclared inputs and say so),
   every Einsum labelled in order, comments as noun phrases. List anything you
   could not transcribe.
5. **Check it against rules.md**, and trace the worked example by hand as in
   Phase 4. A rule violation, an expressibility limit or a trace that
   disagrees with the published answer is a finding: show the evidence and
   ask before changing any Einsum. That is checkpoint B for a port; with no
   findings, say so and continue.
6. **Add what the workbench needs and the tutorial lacks**, to the copy only:
   the `ranks:` block (ask if a kind is unclear); a `**Graph meaning:**` and
   `**Einsum meaning:**` pair under each formula in the walkthrough that has
   none, written from the tutorial's own prose; the expected answer in
   `working_example_part1` if it was only implicit. Show the author what you
   added.
7. Continue with Phase 6.

## Phase 6 — The verifier (the author's)

Offer the kinds in AUTHORING.md (`definition`, `library`, `certificate`,
`different-algorithm`, `user-reference`) with one line each on what it would
compare for this algorithm, and recommend one — a library oracle or brute
force over small instances is the most independent. The author chooses.

- `library` or `user-reference`: you may draft the file — a thin wrapper
  around networkx/scipy, or around the author's own code — following the
  contract in AUTHORING.md. Tell the author it is a draft they must read.
- any other kind: the author writes it; you explain the contract.

What it compares is what the tutorial states as the answer; where a free
choice allows several valid final states, compare what they all share
(depths, not parents).

**Checkpoint C:** the author runs, in their own terminal,
`python3 -m edge_workbench approve-verifier <dir>`, which shows the whole
file. Do not continue until they say it is done.

## Phase 7 — Run `check`, and answer its model steps

```
python3 -m edge_workbench check <dir>
```

Each run lists every problem, then stops. Loop:

- **builder** / **tutorial data** waiting: `check` has written a prompt under
  `<dir>/workbench/prompts/` and names the reply file in **NEXT**. Read the
  whole prompt and answer it yourself, in this session, saving exactly the
  reply it asks for (`workbench/replies/builder.md`,
  `workbench/replies/tutorial-data.json`). The tool checks your reply exactly
  as it would a pasted one. The example you state must quote the tutorial.
- **a rejected reply**: the prompt is rewritten with the problems; answer
  again. These are yours to fix freely.
- **anything about the cascade, the example, or its answer** (program stage
  mismatches you cannot fix in the builder, coverage, answer check): diagnose
  first — trace the failing instance by hand as in Phase 4 — then bring the
  author the evidence and a proposed change. Do not change it yourself.
- **inputs: verifier not approved / changed**: stop; checkpoint C.
- The same finding three times in a row: stop and report what you tried.

Keep a change log as you go: every file you changed to get a pass, and why,
one line each.

## Phase 8 — Report

When `index.html` is written: the page's answer and how many random
instances agreed; every free choice and how it ran; the change log; any
finding raised for edge-core-ir; anything you flagged that the author left as
is.
