# Issues to raise on edge-core-ir

Gaps found while building walkthrough pages with edge-workbench. edge-core-ir's
evaluator is the source of truth for EDGE semantics, so each is written up for
Toluwa to decide. Issues 1, 2 and 7 are patched locally for now, so that other
tutorials are not held up; see "Local changes" below. Each section is meant to
be pasted as one GitHub issue.

---

## 1. Occupancy `‖T‖` inside an Einsum

**Where it came up:** exact cover (set-cover tutorial), E13:

```
Success_{i+1} = ‖ActiveCol_{i+1}‖ ≡ 0
```

**Problem.** The IR has occupancy only in stopping conditions
(`stopping.PropertyApp(name="occupancy")`). An Einsum cannot use it, so E13
cannot be written as one Einsum. The only lowering today is an OR-reduction
into a named intermediate followed by a negation, which changes the Einsum the
author wrote.

**Question.** Should the expression tree admit occupancy (count of non-empty
entries of a projection, its given subscripts read at the current point, its
free ranks counted) as a value that is always present? A count of 0 would be a
value, not an absence.

**Blocks:** the set-cover walkthrough. Fixed locally for now (see the end of this file).

---

## 2. A reduction inside parentheses (paper §7.3.2, Eq. 143)

**Where it came up:** exact cover, E18:

```
Candidates_{i+1,r} = (A_{r,c} ·¹ PickedCol_{i+1,c})_{i+1,r} ·² ActiveRow_{i+1,r}
                     :: ⋀¹ ←(∩)  ⋁¹_c ANY(∪)  ⋀² ←(∩)
```

This is the shape of the paper's own anonymous-tensor example, Eq. 143
(BFS gather and filter in one Einsum). The Reduce on label 1 contracts `c`
inside the parentheses, before label 2 uses the result.

**Problem.** The IR accepts it (specs are flat per Einsum and labels may sit
inside an `AnonymousTensor`), but the evaluator refuses it:
`UnsupportedConstructError: ... would be reduced away inside the parentheses
... Split the inner expression into its own Einsum`. Splitting introduces a
named intermediate the author did not write.

**What the paper says.**

- Example 4, Eq. 19: `Z_{m,n} = (A_{k,m} ·¹ B_{k,n})_{m,n} ·² C_{m,n} :: ⋀¹ ×  ⋁¹ +  ⋀² +`.
  "the Reduce action applies to the implicit, temporary anonymous tensor
  created by the first operation label". An implementation may build that
  partial tensor and "reduce the k rank before applying the second operation
  label". So Map, Reduce on its label, then a further Map, is valid in one
  Einsum.
- §7.3.3, Eq. 144-145: to mask after reducing `G` alone, "we would need to
  specify a cascade of Einsums". That Einsum has no Map to label, so the Reduce
  has nowhere to attach. It does not rule out Eq. 19's form.
- The spec form above is the labelled one. The tutorial writes E18 with a `::`
  inside the parentheses, which is its shorthand: the grammar has one action
  list per Einsum, with labels pointing into the expression.

**Why the level matters (a minimal case).**

```
Z_m = (A_{m,k} ·¹ X_k)_m ·² W_m :: ⋀¹ *(∩)  ⋁¹_k +(∪)  ⋀² +(∩)
A = {(0,0): 1, (0,1): 2},  X = {0: 10, 1: 20},  W = {0: 5}
```

Reduced inside the parentheses: `1·10 + 2·20 + 5 = 55`. Reduced at the output
instead: `60` (W added once per k).

**Request.** Evaluate a Reduce spec whose label is inside an anonymous tensor
over the axes that tensor drops, at that level.

**Blocks:** the set-cover walkthrough. Fixed locally for now (see the end of this file).

---

## 3. A unary applied to a parenthesized expression

**Where it came up:** exact cover, E02:

```
d*_i = ⌊F_{i,r} / |R|⌋ :: ⋁ max(∪)
```

**Problem.** `UnaryApp.operand` is typed `InputTensor`, so `floor` cannot
wrap `F / |R|`. The paper defines a unary as a degenerate Map against 1 with a
take-left merge (§5.5, Eq. 30), which would give
`((F_{i,r} ·¹ |R|)_{i,r} ·² 1) :: ⋀¹ /(∩) ⋀² ⌊⌋(←) ⋁²_r max(∪)` — but that
needs `floor` registered as a map compute operator, which the default registry
deliberately does not do.

**Question.** Is the degenerate-Map form the intended encoding (with a
map-compute `floor`), or should the IR allow a unary on an expression?

---

## 4. Tie-breaking in `select-min-val`

**Where it came up:** exact cover, E17 (Knuth's column choice):

```
PickedCol_{i+1,c*} = ActiveCounts_{i+1,c} :: ⋘_{c*} 𝟙(select-min-val)
```

**Current behaviour.** Ties are broken by the smallest coordinate (key
`(value, coord)`).

**Question.** For Algorithm X any column with the fewest rows is correct, so
the choice among tied minima is free, like `pick-admissible-edge`. Should
`select-min-val` keep ties by first arrival (so the schedule decides, and a
shuffled schedule explores them), or should a separate operator express that?
In Working Example 1, C0 and C1 tie at i = 0; the sequential order gives C0
either way.

---

## 5. Per-label values in the evaluation trace

**Where it came up:** the walkthrough page's "how this value is computed"
panel, for parenthesized Einsums (e.g. max-flow E11:
`δ = (E ·¹ R) ·² PushCand :: ⋀¹ min(∩) ⋀² ←(∩)`).

**Problem.** `EinsumResult` records each point's final Map value (`map_tmp`)
and the Reduce result (`red_tmp`), but not the value or presence at each
label inside the expression. The page needs those to show a parenthesized
Einsum step by step.

**Request.** Optionally record, per point, each `BinaryApp` label's operand
presence, merge decision and computed value (and each unary's), e.g. behind a
`trace_labels=True` flag on `evaluate`.

---

## 6. A per-Einsum hook in the evaluator

**Where it came up:** edge-workbench builds its walkthrough page from the
evaluator's run: for every Einsum it needs the tensors just before and just
after (the step-by-step state, and the operand cells each point read).

**Problem.** `evaluate` returns the final tensors and an `EinsumResult` per
Einsum, but not the tensors between Einsums. edge-workbench gets them today
by wrapping `evaluate_einsum` for the duration of a run (the name
`edge_ir.evaluator.cascade` and `edge_ir.evaluator.program` call it by), which
works but depends on that internal call.

**Request.** An optional callback on `evaluate`, e.g.
`on_einsum(einsum, pinned, env, result)` called after each Einsum, or a flag
that records per-Einsum snapshots in the trace.

---

## 7. A Reduce over an empty fiber writes the identity

**Where it came up:** exact cover, E02, on an instance with no solution (a
column no row covers, so `InitS` and `S_0` are empty):

```
d*_i = ⌊F_{i,r} / |R|⌋ :: ⋁ max(∪)
```

**Behaviour.** `F_0` is empty, so no point of the Map is present. The Reduce
still visits every point of the iteration space (`r` over all rows), and its
state starts at `max`'s identity, `-inf`. Because `-inf` is not `d*`'s empty
value (0), the state counts as present, the union merge keeps it, and
`d*_0 = -inf` is written. `floor(-inf)` then raises `OverflowError`; with the
floor guarded instead, the `-inf` reaches E19's `σ(d*_i + 1, r)` and the run
does not stop.

**Question.** Should a Reduce whose fiber has no present Map value leave the
output empty (the identity is only the seed of a fold that has something to
fold), rather than write the identity?

**Blocks:** set-cover's verifier (random instance 1, which has no cover).
Fixed locally for now (see the end of this file).

---

## Local changes in edge-core-ir, for review

Uncommitted edits in edge-core-ir, all needing Toluwa's decision.

Made on 2026-10-26, with the user's go-ahead, so other tutorials are not held
up while issues 1, 2 and 7 wait upstream:

- issue 1, occupancy inside an Einsum: an `Occupancy` expression node in
  `edge_ir/ir/expr.py`, evaluated in `edge_ir/evaluator/actions/map.py` with
  the same slice the stopping condition's occupancy counts; its subscripts
  are read by `edge_ir/analysis/iteration_space.py`; `schemas/program.schema.json`
  regenerated; `tests/test_occupancy_expression.py`.
- issue 2, a reduction inside parentheses: `edge_ir/evaluator/einsum.py`
  groups the points behind each outer point, and the anonymous tensor in
  `edge_ir/evaluator/actions/map.py` folds them with the existing
  `reduce_action`; `tests/test_nested_reduction.py`, and the docstring of
  the refusal test in `tests/test_evaluator_semantics.py`.
- issue 7, a Reduce over an empty fiber: `edge_ir/evaluator/actions/reduce.py`
  writes an output coordinate only when at least one present Map value was
  folded into it; `tests/test_reduce_empty_fiber.py`. Every existing test
  still passes.

Made before the "raise an issue, don't edit" rule:

- `edge_ir/udf/builtins.py`: `select-any` (first arrival wins; the schedule
  decides) and a unary `floor`. Max-flow's `pick-admissible-edge` is an alias
  of `select-any`.
- `edge_ir/validator/udf_names.py`, plus its export in
  `edge_ir/validator/__init__.py`: a pass checking every operator a program
  names is registered.
- `examples/algorithms/exact-cover/`: an exact-cover builder and functions.
  The builder now depends on items 1 and 2 above and does not build.
- `examples/algorithms/max-flow/`: edits to the builder, `einsum.edge`,
  `einsum.md`, functions, program JSON, `CHANGES.md` and `metadata.md`, with
  matching test edits in `tests/test_max_flow_artifact.py` and
  `tests/test_evaluator_acceptance.py`.

---

## For the set-cover tutorial, not edge-core-ir

Proposed changes to Toluwa's tutorial (`_algorithms/set_cover.md`). These are
questions about the cascade, not gaps in the IR or the evaluator.

### Compute the starting stack with Einsums instead of an input

**Today.** The tutorial's initialization is prose: `S_{0,r}` = "initial
candidates at depth 1 (first column branch choices)". Each worked example gives
its own `S_0`. To run the cascade, the walkthrough supplies that as an input,
`S_{0,r} = InitS_r`, and explains it in hand-written setup steps.

**Problem.** Choosing the first column is part of Algorithm X, not something a
user supplies, and it is the same branching step the cascade already does. The
rule currently lives in three places, none of them checked by the evaluator:
the tutorial's sentence, the page's setup text (Working Example 1 only), and
`random_instance` in `examples/set-cover/verifier.py`.

**Proposal.** The branch step of E15-E19, run once at generation 0 with every
row and column active and the stamp at depth 1:

```
RowCounts_{0, c}  = A_{r, c} . Row_r :: /\ <-(∩) \/ +(∪)
PickedCol_{0, c*} = RowCounts_{0, c} :: <<<_{c*} 1(select-min-val)
Candidates_{0, r} = A_{r, c} . PickedCol_{0, c} :: /\ <-(∩) \/ ANY(∪)
S_{0, r}          = Candidates_{0, r} . sigma(1, r) :: /\ ->(∩)
```

These four lines are new: they are not in the tutorial. They were written from
its prose by adapting E15, E17, E18 and E19. They replace `InitS`, and add no
tensors, since all three intermediates are already written by the cascade.
E01-E20 are unchanged.

**What was tested.** On Working Example 1, run through the evaluator: counts
C0: 2, C1: 2, C2: 1; picks C2; candidate R3; `S_0 = {R3: 7}`. The rest of the
run was unchanged, and the answer check passed (14 of 14). The lines were then
taken back out; the page uses `InitS`.

Checked by a separate calculation, not by running the cascade:

| example | tutorial's `S_0` | the rule |
|---|---|---|
| 1. Three columns | `{R3: 7}` | matches |
| 2. Wikipedia | `{A: 6, B: 7}` | matches; columns 0, 1, 2, 4, 5 tie at 2 and `select-min-val` takes the lowest |
| 3. Four queens | `{16, 17, 18, 19}` | matches only with the mask below |

**Questions.**

1. Should the initialization be written as Einsums at all, or stay prose?
2. Working Example 3: the diagonal (secondary) columns have fewer rows, so the
   lines above would pick column 8. Restricting the count to primary columns
   picks column 0 and gives the tutorial's `S_0`. Example 3 already changes
   `ActiveCounts` and `Success` this way, so is the same `IsPrimary` mask
   right here, for example on `RowCounts_{0, c}`?
3. A column no row covers: its count stays empty, so `select-min-val` picks a
   different column and the search runs and finds no cover. The old `InitS`
   rule gave an empty stack instead. The answer is the same, but is the longer
   run acceptable? E17 already behaves this way mid-search.

### PickedCol is declared Boolean but holds a count

E17 is `PickedCol_{i+1,c*} = ActiveCounts_{i+1,c} :: ⋘_{c*} 𝟙(select-min-val)`.
A populate's `𝟙` is pass-through (paper §5.8), so the column's count goes into
`PickedCol`, which the tutorial declares Boolean. Nothing depends on the number:
E18 uses only its presence. The walkthrough records a Boolean tensor's values as
`true`, so a reader sees what the declaration says; the Einsum is unchanged.

**Resolved (2026-11-15).** The declaration is now `integer, empty = 0`, the
same empty value as `ActiveCounts`, in the example's tutorial and `einsum.edge`.
E17 is unchanged. `edge-core-ir` does not enforce declared types, so nothing
had flagged this.
