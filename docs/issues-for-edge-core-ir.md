# Issues to raise on edge-core-ir

Questions about EDGE's semantics that came up while running tutorials on
edge-core-ir's evaluator, written up for Toluwa to decide. Each section is
meant to be pasted as one GitHub issue.

**Scope.** Only what the language means belongs here. edge-core-ir should not
grow because the workbench needs something: anything the walkthrough page
needs (trace detail, hooks, recordings, operator names for free choices) is
built in the workbench, around the evaluator, and listed in
[evaluator-needs.md](evaluator-needs.md). Questions about one tutorial's
cascade are in [tutorial-notes/](tutorial-notes/). Issue numbers are stable,
because code and other docs cite them.

Issues 2, 7, 8, 9 and 10 are patched on edge-core-ir's branch
`fixes_for_edge_workbench` so that tutorials are not held up; see "Local
changes" at the end. Toluwa has not reviewed them.

| # | question | status |
|---|---|---|
| 1 | Occupancy inside an Einsum | **decided: not allowed** |
| 2 | A Reduce inside parentheses | patched; open |
| 3 | A unary on a parenthesized expression | open |
| 4 | Tie-breaking in `select-min-val` | open |
| 5 | Per-label values in the trace | moved to the workbench |
| 6 | A per-Einsum hook | moved to the workbench |
| 7 | A Reduce over an empty fiber | patched; open |
| 8 | Case statements | patched; open |
| 9 | Conditional cascades (and macros) | patched; open |
| 10 | Inner cascades, and when a cascade ends | patched; open |
| 11 | Populate rounds in the trace | moved to the workbench |

---

## 1. Occupancy `‖T‖` inside an Einsum

**Decided (Toluwa, 2026-11-19): not allowed.** Occupancy belongs only in a
stopping condition (paper Eq. 39d; edge-core-ir D5). The local patch is
removed from edge-core-ir and the workbench, and `check` reports an Einsum
that uses `||T||`. Set-cover's E13 is being rewritten without it
([tutorial-notes/set-cover.md](tutorial-notes/set-cover.md)).

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
inside an `AnonymousTensor`, D9), but the evaluator refuses it:
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

**Why the level matters (a minimal case).**

```
Z_m = (A_{m,k} ·¹ X_k)_m ·² W_m :: ⋀¹ *(∩)  ⋁¹_k +(∪)  ⋀² +(∩)
A = {(0,0): 1, (0,1): 2},  X = {0: 10, 1: 20},  W = {0: 5}
```

Reduced inside the parentheses: `1·10 + 2·20 + 5 = 55`. Reduced at the output
instead: `60` (W added once per k).

**Request.** Evaluate a Reduce spec whose label is inside an anonymous tensor
over the axes that tensor drops, at that level.

---

## 3. A unary applied to a parenthesized expression

**Where it came up:** exact cover, E02: `d*_i = ⌊F_{i,r} / |R|⌋ :: ⋁ max(∪)`.

**Problem.** `UnaryApp.operand` is typed `InputTensor`, so `floor` cannot
wrap `F / |R|`. The paper defines a unary as a degenerate Map against 1 with a
take-left merge (§5.5, Eq. 30), which would give
`((F_{i,r} ·¹ |R|)_{i,r} ·² 1) :: ⋀¹ /(∩) ⋀² ⌊⌋(←) ⋁²_r max(∪)`, but that
needs `floor` as a map compute operator.

**Question.** Is the degenerate-Map form the intended encoding, or should the
IR allow a unary on an expression?

---

## 4. Tie-breaking in `select-min-val`

**Where it came up:** exact cover, E17 (Knuth's column choice):
`PickedCol_{i+1,c*} = ActiveCounts_{i+1,c} :: ⋘_{c*} 𝟙(select-min-val)`.

**Current behaviour.** Ties are broken by the smallest coordinate (key
`(value, coord)`), so the result does not depend on the schedule.

**Question.** When any minimum is correct (Algorithm X takes any column with
the fewest rows), should `select-min-val` keep the first arrival among tied
minima, so the schedule decides, or should a separate operator express that?

---

## 5. Per-label values in the evaluation trace

Moved: a walkthrough-page need, not a language question. See
[evaluator-needs.md](evaluator-needs.md).

## 6. A per-Einsum hook in the evaluator

Moved: the workbench wraps `evaluate_einsum` itself. See
[evaluator-needs.md](evaluator-needs.md).

---

## 7. A Reduce over an empty fiber writes the identity

**Where it came up:** exact cover, E02, on an instance with no solution (a
column no row covers, so `S_0` is empty).

**Behaviour.** No point of the Map is present. The Reduce still visits every
point of the iteration space, and its state starts at `max`'s identity,
`-inf`. Because `-inf` is not the output's empty value (0), the state counts
as present, the union merge keeps it, and `d*_0 = -inf` is written; the run
then fails downstream.

**Question.** Should a Reduce whose fiber has no present Map value leave the
output empty (the identity is only the seed of a fold that has something to
fold), rather than write the identity?

---

## 8. Case statements (paper §5.9.1, Eq. 61; §7.3.8, Eq. 155)

**Where it came up:** bubble sort, every Einsum, e.g.

```
Z_{0,j,n} = { Z_{0,j-1,n}                 n < j
            { min(Z_{0,j-1,j}, A_{j+1})   n = j
            { max(Z_{0,j-1,j}, A_{j+1})   n = j+1
            { empty                       o/w
```

and max-flow E04, whose builder lowers its three arms to three Einsums
writing one slice of `R`, relying on later-overwrites-earlier (docs/TODO.md,
"single assignment").

**Problem.** The IR has no case statement (docs/TODO.md, "Language
features"; docs/cases.md asks whether `CaseExpression` should be a node). A
lowering to one Einsum per arm writes the output several times, and the
conditions are lost.

**What the paper says.** "Each branch of a case statement is itself a valid
EDGE expression, with its own modifier if needed. At each point in the
iteration space, [it] selects the appropriate sub-Einsum expression." §7.3.8:
it "is syntactic sugar": each branch is an Einsum into a temporary restricted
to its region, combined with `<<`; "EDGE allows any Boolean predicate as
conditions for each case."

**Local patch (the "middle path" of docs/cases.md).** `Einsum.expression` may
be `Cases(arms=[CaseArm(expression, specs, where, when)])`. An arm carries its
own expression and Map/Reduce specs; `where` is an `IterationPredicate` over
rank variables (cases.md Pattern 1), `when` a stopping-style `Predicate` over
tensor values (Pattern 2), both their conjunction (Pattern 3), neither
`otherwise`; `expression=None` is an arm written `empty`. Each arm is Mapped
and Reduced over the points it claims, and the arms' reduction temporaries are
combined before the Einsum's one Populate, so the output is written once.

**Questions.**

1. **Order.** The patch tests arms in written order and a point belongs to
   the first whose condition holds. cases.md Pattern 4 overlays the arms with
   `<<`, where a later arm overwrites an earlier one. The two agree when the
   conditions are disjoint (Eq. 61, bubble sort) and differ when they
   overlap. Which is intended?
2. Is a node in the IR right, or should the parser desugar (cases.md "Open
   items")? Desugaring needs temporaries the author did not write.
3. An arm written as a function call, `min(x, y)`, states no merge. The
   paper's default for an omitted merge is pass-through, which gives bubble
   sort a wrong value at `j = 0`; intersect gives the right one. What should
   the shorthand mean?
4. A condition may only mention the output's rank variables and the pinned
   iterative ranks. Is that the intended restriction?

---

## 9. Conditional cascades and macros (paper appendix B.8)

**Where it came up:** direction-optimizing BFS, hybrid:

```
(Tree_{i+1,s,d}, F_{i+1,d}, TopDown_{i+1}) =
    { TOP-DOWN(G_{s,d}, F_{i,s}, Tree_{i,s,d}, NV_{i,c}, MF_i, MU_i)   if TopDown_i ≡ True
    { BOTTOM-UP(G_{s,d}, F_{i,s}, Tree_{i,s,d}, NV_{i,c}, NF_i)        if TopDown_i ≡ False
```

A case statement whose arms are macro invocations in cascade form: per
generation, one of two Einsum sequences runs.

**What the paper says.** "A macro is a named, parameterized Einsum template.
Invoking a macro expands it into one or more Einsums via lexical substitution
of its tensor and rank variable expression parameters." The paper has no term
for a case statement over cascades.

**Macros are not an edge-core-ir question.** They are lexical, and the IR is
the desugared form (D3), so expansion is a front end's job; the workbench's
builder does it (`edge_workbench/macro.py`, moved out of edge-core-ir on
2026-11-19).

**What the expansion needs: a conditional cascade.** Local patch: a cascade
entry may be `ConditionalCascade(arms=[ConditionalArm(when, einsums, macro)])`.
The arms' conditions are read once per generation, before any arm runs; the
first arm whose condition holds runs, and none if none holds. `flatten`
numbers Einsums depth first, and the single-assignment pass does not count
two arms of one conditional cascade as two writes.

**Question.** Is a conditional cascade one construct, or should the
multi-output case statement desugar to one case statement per output (which
evaluates each macro body once per output)?

---

## 10. Inner cascades, and when a cascade ends (paper §7.3.1, Eq. 142; B.3)

**Where it came up:** bubble sort:

```
▷ Begin outer cascade (passes)   i = 0
  ▷ Begin inner cascade (steps)
  Z_{0,j,n} = ...      Z_{i,0,n} = ...      Z_{i,j,n} = ...
  ⋄⋄ : j ≡ J
⋄ : Z_{i+1,J-1} ≡ Z_{i,J-1}
```

**Problem.** `NestedCascade` is flat, and the evaluator refuses a second
iterative rank.

**Local patch.**

- An entry of `NestedCascade.einsums` may itself be a `NestedCascade`, with
  its own stopping conditions and `iterative_rank`. It runs to its own end
  once per generation of the cascade around it, with the outer ranks bound.
- **The rank bounds the cascade.** Eq. 142: `RV_i = { i | i ∈ [0, I) ∧ ¬⋄(i) }`.
  When the rank an iterative variable subscripts has a declared shape, a
  generation outside it does not run and the cascade ends. An unbounded
  generational rank, every cascade before this patch, is unchanged.
- **A diamond that looks ahead of the body.** The body writes `Z_i`; the
  diamond reads `Z_{i+1}`, which is not written after generation `g`. The
  patch evaluates it at `i = g − (r − w)`, with `r` the largest shift of `i`
  the diamond reads and `w` the largest the body writes. When `r ≤ w`, every
  cascade before this patch, nothing changes.

**Questions.**

1. Is the look-ahead rule the intended timing (it extends Q5 of
   docs/stopping_condition_open_questions.md), or should the body write
   `Z_{i+1}`?
2. The single-assignment pass knows one iterative rank, so the three writes
   of `Z` are reported as overlapping. Should it learn inner ranks?

---

## 11. What each round of Populate did, in the evaluation trace

Moved: recording, not semantics. See [evaluator-needs.md](evaluator-needs.md).
While building it we checked that Populate obeys Inset 4's three conditions;
edge-core-ir's `tests/test_populate_rounds.py` pins them, and can be offered
on its own. Two things the paper does not ask for and the evaluator does not
check: a Delete of a location empty in the pre-state is accepted (a no-op),
and a write-del set need not have one element per fiber location.

---

## Local changes in edge-core-ir

On branch `fixes_for_edge_workbench`. None changes an existing test or
`Program`'s fields, so every serialized program still round-trips.

**Language patches, for Toluwa's review (one pull request per issue):**

- issue 2: `edge_ir/evaluator/einsum.py` groups the points behind each outer
  point, and the anonymous tensor in `edge_ir/evaluator/actions/map.py` folds
  them with the existing `reduce_action`; `tests/test_nested_reduction.py`.
- issue 7: `edge_ir/evaluator/actions/reduce.py` writes an output coordinate
  only when at least one present Map value was folded into it;
  `tests/test_reduce_empty_fiber.py`.
- issue 8: `Cases` and `CaseArm` in `edge_ir/ir/einsum.py`;
  `edge_ir/evaluator/einsum.py` evaluates arm by arm (`EinsumResult.arms`);
  the walkers in `analysis/iteration_space.py`, `evaluator/iteration.py` and
  `validator/udf_names.py` read arms; `tests/test_case_statement.py`.
- issue 9: `ConditionalCascade`, `ConditionalArm` and `flatten` in
  `edge_ir/ir/einsum.py`; `edge_ir/evaluator/cascade.py` runs a tree-shaped
  body; `validator/single_assignment.py` numbers Einsums as `flatten` does;
  `tests/test_conditional_cascade.py`.
- issue 10: `NestedCascade.einsums` admits a `NestedCascade`;
  `edge_ir/evaluator/cascade.py` and `edge_ir/evaluator/stopping.py`
  (`should_stop(outer=)`); `tests/test_nested_cascade.py`.
- `schemas/program.schema.json` regenerated.

**Offered separately:** `edge_ir/validator/udf_names.py`, a pass checking that
every operator a program names is registered (her Layer 2 plan, VAL-2).

**Taken back out on 2026-11-19** (workbench needs, now built in the
workbench; see [evaluator-needs.md](evaluator-needs.md)): issue 11's populate
recording (`edge_ir/evaluator/actions/populate.py` is back to Toluwa's);
`select-any` and `floor` (`edge_ir/udf/builtins.py` is back to Toluwa's; the
max-flow example defines its own `pick-admissible-edge`); `edge_ir/ir/macro.py`;
`examples/algorithms/exact-cover/`. Inset 4's three conditions stay pinned by
`tests/test_populate_inset4.py`, which tests existing behaviour.

**Removed:** issue 1's `Occupancy` node (2026-11-19, not allowed).

**Max-flow** (`examples/algorithms/max-flow/` and its tests): Sanjana's fixes
to her example (E06 seeds `Act_1`, E17 writes `AdmPost`), from the group
repo; algorithm work, not a language change.
