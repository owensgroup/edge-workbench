# Writing Einsums that are right and that edge-workbench can run

Distilled from the agents that wrote max-flow, set-cover, Bellman-Ford and
DOBFS. Each rule says why; where a rule is a current tool limit rather than
the notation, it says so, because those may change.

## Faithfulness

- **The pseudocode decides.** Settle every design question by re-reading it,
  not by what the algorithm "usually" does. "While some v has e(v) > 0"
  never says which v: that is nondeterminism the algorithm has, so it is a
  populate, not a schedule hidden in prose.
- **A branch needs its test first.** "If some w has r(v,w) > 0 and
  d(v) = d(w)+1 … else …" means the cascade answers the admissibility
  question before either arm writes.
- **The trace settles encodings.** When the notation leaves an encoding open
  (does `TPath` carry depths or Booleans?), the worked example's step table
  decides it. A spec with a trace is checkable; one without is a guess.

## Empty values

- **A stored value equal to the empty value is absent.** This is the most
  load-bearing rule in the notation. With `empty = 0`, a weight-0 edge is no
  edge; with `empty = False`, False entries do not exist.
- **Let the empty value be the guard.** `R` with `empty = 0` IS the
  `r(u,v) > 0` test; `E` with `empty = 0` IS `e(v) > 0`. Choosing empties well
  replaces explicit predicates.
- **Prefer an empty value that is the identity of the operator that reads
  it.** `+∞` is min's identity: an empty neighbour label reduces to `+∞`, the
  new distance stays empty, and `<<` keeps the old one, with no second gate.
  `−1` would also avoid a collision, but the reader must then prove the empty
  never propagates.
- **Pick each one deliberately, and say why.** Bellman-Ford's `G` is
  `empty = inf` so that a weight-0 edge exists. Max-flow's height `D` read
  through `∩` drops height-0 vertices if `empty = 0`.
- Init lines that assign the empty value write nothing.

## Shape of the cascade

- **One pseudocode step per Einsum, and one IR Einsum per written Einsum.**
  The tool rejects a lowering that invents a tensor the spec does not write.
  A Map with a Reduce in one Einsum is fine (Bellman-Ford's E01,
  `⋀_s +(∩) ⋁_s min(∪)`); what to avoid is fusing two pseudocode steps.
- **When an operator would be ambiguous, split the Einsum** so each uses a
  defined operator (set-cover's `Keep` then `TPath`), rather than inventing a
  compound one ("take-left-if-less"). Compose defined operators, as the paper
  does.
- **Write the tutorial's shape, not the IR's.** Use parentheses and labels
  `·¹ ·²` only where the Einsum genuinely has more than two operands or a
  nested part (paper §7.3.2); never add them because the IR lowering needs
  them. The builder does the lowering.
- **A unary (`¬`) applies to its input tensor before any reduce.** "Not
  visited" is a reduce in one Einsum (`Visited`) and the negation in the next
  (`NV`).
- **Every tensor an Einsum reads must exist at that generation** (`i` vs
  `i+1`), and a tensor is written once per generation.
- **Stop condition last** (`⋄ :`), and check what it is tested on: max-flow
  must test `Act`, not `E`, because the source keeps a negative excess
  forever.
- **Declare every input** the cascade reads but never writes — the rank
  universes too (set-cover's `Col`, `Row`, `InitS`).

## Populate

- A populate `⋘_{v*} 𝟙(name)` selects coordinates. If the choice is part of
  the algorithm, use a ranking operator (`select-min-val`, `select-max-val`,
  …) — Knuth's column choice is `select-min-val`. If the pseudocode leaves it
  free, name it after the choice (`pick-admissible-edge`,
  `select-any-vertex`); `check` runs it under several random schedules and
  requires the same answer from each.
- Do not invent a populate where the pseudocode has no choice.

## Names and comments

- **Tensors are noun phrases a graph-algorithms reader understands**:
  `PushCand`, `MinNeiLbl`, `NeiNV`, `CandTree` — not `SW`, `MinD`.
- **`einsum.edge` comments are labels, the tutorial holds the sentences.** One
  noun phrase per Einsum; add a "why" only when it is a trap ("saturated edges
  are empty, so the intersect skips them").

## What the IR and evaluator can run today

Check each Einsum against this before checkpoint B. The issue numbers are in
`docs/issues-for-edge-core-ir.md`.

- **Operators**: only names the registry has (edge-core-ir
  `edge_ir/udf/builtins.py`); an unknown name stops `check`. Look a name up,
  per category (compute, merge, coordinate, unary), before using it.
- **A unary takes only a named tensor**, not a parenthesized expression
  (issue 3): `⌊F / |R|⌋` needs the degenerate-Map form or a split.
- **No `cases` and no macros**: DOBFS bottom-up and hybrid, and bubble sort,
  cannot run yet. Say so at checkpoint B rather than lowering around it.
- **Patched locally, not yet upstream**: occupancy `‖T‖` inside an Einsum
  (issue 1), a reduce inside parentheses (issue 2), a reduce over an empty
  fiber writing nothing (issue 7). They run on this machine; mention their use
  in the report.
- **Generations are capped at 500** per run.
- **Coordinates start at 0**; a tutorial that numbers vertices from 1 shows an
  unused vertex 0.

## The tutorial ↔ einsum.edge pairing

`check` compares them Einsum by Einsum. The tutorial parser accepts
`\mathit{...}`, a `::` on the next line, and `<user-specified>` init lines; if
an Einsum is missing from the parsed cascade, suspect formatting first.
