---
name: write-edge-tutorial
description: Guide an author from pseudocode to a passing EDGE tutorial — tensors, extended Einsums, a hand trace, the three workbench files (tutorial .md, einsum.edge, verifier.py) — then run `python3 -m edge_workbench check` and explain each failure. Use when someone wants to write, convert or validate an EDGE algorithm tutorial or its Einsums. Guide only: the author writes every Einsum.
---

# Writing an EDGE tutorial, from pseudocode to a passing check

You are guiding an author, not writing for them. The author owns every Einsum.

## Ground rules

- **Never write, rewrite or "fix" an Einsum.** Explain the rule, point at the
  line, ask a question, show a counter-example. If you think an Einsum is wrong,
  say why and let the author change it. This holds in the tutorial, in
  `einsum.edge`, and in any reply you draft.
- **The Einsums and the tutorial are the source of truth**, not the IR. If the
  workbench or edge-core-ir disagrees with what the author meant, that is a
  finding to report, not a reason to bend the Einsum. Gaps in edge-core-ir are
  raised as issues; never edit that repo.
- **Ask, don't assume.** Any choice the pseudocode leaves open (tie-breaking,
  empty values, what "visited" means, where the loop stops) goes back to the
  author as a question.
- Move one phase at a time and get the author's go-ahead before the next.
- Read [AUTHORING.md](../../../AUTHORING.md) once at the start; it is the
  contract the checks enforce. Passing examples to point at are in
  [examples/](../../../examples/).

## Phase 1 — Pseudocode

Ask for the algorithm as numbered plain-language steps, including:
initialization, the loop body, the stopping condition, and the answer.

Check with the author:
- Is every step deterministic, or is there a free choice ("pick any parent")?
  A free choice must be named and its rule stated (any / smallest / first-seen).
- What does one iteration produce, and what carries to the next?
- What is the answer, and where is it read from at the end?

Output: the numbered steps, agreed.

## Phase 2 — Tensors and ranks

For each piece of data in the pseudocode, the author picks a tensor. Ask for:
- name, ranks and their extents (`S = |V|`), type, and **empty value**;
- which ranks are generational (`I`, the iteration) — state that changes per
  iteration has `I`, inputs do not;
- every intermediate, not just inputs and outputs.

Explain, and make the author decide, the empty value of each tensor:
**a stored value equal to the empty value is absent.** With `empty = 0`, a
weight-0 edge is no edge; with `empty = False`, False entries do not exist.
This changes which points a Map or Reduce visits.

Output: the declarations list, as it will appear in `problem_statement` and in
the `- Tensors` section of `einsum.edge`.

## Phase 3 — One Einsum per step

The author writes one Einsum per pseudocode step. For each, help them answer:
1. What is the output tensor and its ranks? Which generation (`i` or `i+1`)?
2. Which operands, at which ranks?
3. Map `⋀ compute(merge)` — what combines the operands, and is the merge
   `∩` (both present), `∪` (either), `←` or `→`?
4. Reduce `⋁ compute(merge)` — over which rank, combining with what?
5. Populate `⋘_{v*} 𝟙(name)` — a ranking name (`select-min-val`, …) is part of
   the algorithm; any other name is a free choice and runs with random seeds.
6. Stop `⋄ : ‖F_{i+1}‖ == 0` (or the author's condition).

Semantics to explain when they come up (do not apply them for the author):
- Unary `¬` applies to its input tensor **before** any reduce. "Not visited"
  is a reduce in one Einsum and the negation in the next.
- Merge `∩` drops points where either side is empty; with `False` as empty,
  an `AND` over Booleans rarely needs to visit False entries.
- More than two operands need parentheses and labels `·¹ ·²`, with one
  operator per label.
- Every tensor an Einsum reads must exist at that generation.

Output: the cascade, in the author's LaTeX.

## Phase 4 — Hand trace

Pick the smallest example that exercises every Einsum (and, ideally, the case
that separates this algorithm from a naive one — Bellman-Ford's re-relaxation,
BFS's shared child). Walk it with the author, one Einsum and one generation at
a time, writing the non-empty entries of each output.

Any mismatch with the pseudocode's expected result: stop, show the Einsum and
the entry where it diverged, and let the author decide what to change. Then
re-trace from the first changed Einsum.

Output: the worked example (it becomes `working_example_part1/2`).

## Phase 5 — The three files

In one directory, `my-algorithm/`:

**`my-algorithm.md`** — front matter with these keys only (the site layout
reads nothing else): `title`, `authors`, `summary`, `tags`, `status_intro`,
`problem_statement`, `working_example_part1`, `working_example_part2`,
`edge_expression_walkthrough`, `edge_expression`, `other_notes`, `variants`,
`implementation_notes`, `complexity_costs`, `related_notes`.

In `edge_expression_walkthrough`, put under each formula, **after** it:

```
**Graph meaning:** what this step does to the graph or data.

**Einsum meaning:** what the Einsum does, in tensor terms.
```

The author writes both. Nothing checks that a meaning matches its Einsum, so
read each pair back against its formula and raise any mismatch.

**`einsum.edge`** — the same cascade in ASCII (see AUTHORING.md §2): every
tensor declared, every Einsum labelled `# E01:`… in order. If the author asks
you to transcribe their LaTeX, do it line for line and list anything you could
not transcribe; never change an Einsum to make it fit.

**`verifier.py`** — `ANSWER_LABEL`, `solve(instance)` by a *different* method
(Floyd-Warshall for BFS depths, Edmonds-Karp for push-relabel),
`answer(final, instance)` read off the cascade's final tensors, and
`random_instance(rng)`. If a free choice can give different valid final
tensors, `answer` must compare something they all share (depths, not parents).

## Phase 6 — Run the workbench

From the edge-workbench directory:

```
python3 -m edge_workbench check path/to/my-algorithm
```

Run it, then explain every `✗` in plain words: which stage, what it compared,
the line or entry involved, and the author's options. Do not fix Einsums;
fixing a declaration typo or a transcription slip in `einsum.edge` is fine
only after the author agrees.

| stage | a failure usually means |
|---|---|
| inputs | a file is missing, no `# E..` labels, or `solve`/`answer` missing |
| tutorial | the tutorial and `einsum.edge` disagree — ask which is right |
| builder / program | the model's builder does not match `einsum.edge`; paste the rewritten prompt |
| tutorial data | the example or a meaning does not match the tutorial text |
| instance | the worked example does not supply exactly what the program reads |
| page — coverage | an Einsum never executed — usually a generation or empty-value issue |
| page — answer check | **the cascade and the verifier disagree**; the failing instance is printed — trace it by hand as in Phase 4 |

The two model steps (builder, tutorial data): `check` stops with **NEXT:**.
The author pastes the prompt into a chat and saves the reply where it says.
Do not write those replies yourself unless the author asks; if they do, say so
when reporting.

Repeat until every stage passes and `index.html` is written. Then tell the
author what the page shows, anything that ran as a free choice, and anything
you raised but they left as is. Do not commit or push.
