# Issues to raise on edge-core-ir

Gaps found while building walkthrough pages with edge-workbench. edge-core-ir's
evaluator is the source of truth for EDGE semantics, so each is written up for
Toluwa to decide. Issues 1, 2, 7, 8, 9, 10 and 11 are patched locally for now, so
that other tutorials are not held up; see "Local changes" below. Each section is meant to
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

## 8. Case statements (paper §5.9.1, Eq. 61; §7.3.8, Eq. 155)

**Where it came up:** bubble sort, every Einsum:

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
conditions are lost: nothing downstream can show or check them.

**What the paper says.** "EDGE supports the assignment of different
expressions in different regions of the iteration space, using case
statements ... Each branch of a case statement is itself a valid EDGE
expression, with its own modifier if needed. At each point in the iteration
space, [it] selects the appropriate sub-Einsum expression." §7.3.8: it "is
syntactic sugar": each branch is an Einsum into a temporary restricted to its
region, combined with `<<`; "EDGE allows any Boolean predicate as conditions
for each case."

**Local patch (the "middle path" of docs/cases.md).** `Einsum.expression` may
be `Cases(arms=[CaseArm(expression, specs, where, when)])`. An arm carries its
own expression and its own Map/Reduce specs; `where` is an `IterationPredicate`
over rank variables (cases.md Pattern 1), `when` a stopping-style `Predicate`
over tensor values (Pattern 2), both together their conjunction (Pattern 3),
neither `otherwise`; `expression=None` is an arm written `empty`. The evaluator
Maps and Reduces each arm as its own Einsum over the points it claims and
combines the arms' reduction temporaries before the Einsum's one Populate, so
the output is written once. `Cases` is not in the `Expression` union: it is
only the whole right-hand side.

**Questions.**

1. Order. cases.md Pattern 4 asks for an overlay-order convention. The patch
   says: arms are tested in written order and a point belongs to the first
   whose condition holds, so `otherwise` is what no earlier arm claimed. The
   paper's `T1 << T2` desugaring gives the same result for Eq. 61. Is
   first-match the intended rule?
2. Is a node in the IR right, or should the parser desugar (cases.md "Open
   items")? Desugaring needs temporaries the author did not write.
3. An arm written as a function call, `min(x, y)`, states no merge operator.
   The paper's default for an omitted merge is pass-through. Bubble sort only
   works with intersect: with pass-through, `max(Z_{0,j-1,j}, A_{j+1})` at
   `j = 0` reads the empty `Z_{0,-1,0}` and writes `A_1` where the
   initialization wrote `max(A_0, A_1)`. The bubble-sort builder uses
   intersect and says so. What should the shorthand mean?
4. A condition may only mention the output's rank variables and the pinned
   iterative ranks; anything else raises. Is that the intended restriction?

**Blocks:** the bubble-sort walkthrough. Fixed locally for now (see the end
of this file).

---

## 9. Macros and conditional cascades (paper appendix B.8)

**Where it came up:** direction-optimizing BFS, hybrid:

```
(Tree_{i+1,s,d}, F_{i+1,d}, TopDown_{i+1}) =
    { TOP-DOWN(G_{s,d}, F_{i,s}, Tree_{i,s,d}, NV_{i,c}, MF_i, MU_i)   if TopDown_i ≡ True
    { BOTTOM-UP(G_{s,d}, F_{i,s}, Tree_{i,s,d}, NV_{i,c}, NF_i)        if TopDown_i ≡ False

▷ MACRO TOP-DOWN(TG_{s,d}, TF_{i,s}, ...) ↦ TTree_{i+1,s,d}, TF_{i+1,d}, TTopDown_{i+1}
    (a cascade of Einsums over the formal names)
```

**Problem.** The IR and the evaluator have neither (docs/TODO.md: "Still
open: ... case statements, macros/rank groups"). The statement above is a case
statement whose arms are cascade-form macro invocations: per generation, one
of two Einsum sequences runs.

**What the paper says.** "A macro is a named, parameterized Einsum template.
Invoking a macro expands it into one or more Einsums via lexical substitution
of its tensor and rank variable expression parameters." Assignment form and
cascade form "produce identical expansions"; "Since the arguments are rank
variable expressions (not just variables), substitutions such as a ↦ m+1 are
permitted"; "the caller is responsible for providing consistent subscripts".
The paper has no term for a case statement over cascades; the tutorial calls
it "a macro and a conditional cascade".

**Local patch.**

- Macros stay out of the evaluated IR, because they are lexical:
  `edge_ir/ir/macro.py` has `MacroDefinition(name, inputs, outputs, body)` and
  `expand(defn, inputs, outputs) -> list[Einsum]`, the substitution a lowering
  calls. A formal subscript written as a shift (`TF_{i+1,d}`) binds its
  variable through the shift; inconsistent subscripts raise. The inline form
  (a macro as an anonymous tensor) is not implemented. `Program` does not keep
  the definitions, since a new field would change every serialized program.
- A cascade entry may be `ConditionalCascade(arms=[ConditionalArm(when,
  einsums, macro)])`. The arms' conditions are read once, with the iterative
  rank bound to the current generation, before any arm runs; the first arm
  whose condition holds runs, and none if none holds. `macro` names where the
  arm's Einsums came from and has no effect on evaluation.
- `edge_ir.ir.einsum.flatten` numbers the Einsums depth first, and the
  single-assignment pass does not count two arms of one conditional cascade as
  two writes.

**Questions.**

1. Should the IR keep macro definitions and invocations (for tools, for
   rewrites), or is expansion at lowering right?
2. Is a conditional cascade one construct, or should the multi-output case
   statement desugar to one case statement per output (which evaluates each
   macro body once per output)?
3. `TTopDown_{i+1}` is declared an output of both macros but
   `TMF_i`/`TMU_i`/`TNF_i`, which the bodies also write, are listed as inputs.
   Is "inputs" meant to include tensors the macro writes?

**Blocks:** the DO-BFS hybrid walkthrough. Fixed locally for now in
edge-core-ir (see the end of this file); the walkthrough builds on that
patch. What the tutorial itself left open: "For the DO-BFS tutorial" below.

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
iterative rank ("That is a nested cascade, and NestedCascade is flat").
Running bubble sort also needed two readings the evaluator did not have.

**Local patch.**

- An entry of `NestedCascade.einsums` may itself be a `NestedCascade`, with
  its own stopping conditions and `iterative_rank`. It runs to its own end
  once per generation of the cascade around it, with the outer ranks bound.
- **The rank bounds the cascade.** Eq. 142: `RV_i = { i | i ∈ [0, I) ∧ ¬⋄(i) }`.
  When the tensor rank an iterative variable subscripts has a declared shape,
  a generation outside it does not run and the cascade ends
  (`stopped_by = "rank-exhausted"`). With `J ≡ N−1`, `⋄⋄ : j ≡ J` then ends
  the inner cascade after `j = J−1` without an empty generation `j = J`.
  An unbounded generational rank, which is every cascade before this patch,
  is unchanged.
- **A diamond that looks ahead of the body.** The body writes `Z_i`; the
  diamond reads `Z_{i+1}`. After generation `g` it cannot be decided at
  `i = g`, because `Z_{g+1}` is not written. The patch evaluates it at
  `i = g − (r − w)`, with `r` the largest shift of `i` the diamond's operands
  read and `w` the largest the body writes: the latest `i` whose operands
  exist. The tutorial's own trace agrees ("Pass 2 ... changes nothing, so
  ... `Z_{2,J−1} ≡ Z_{1,J−1}`, and the outer cascade halts"). When `r ≤ w`,
  which is every cascade before this patch, nothing changes.

**Questions.**

1. Is the look-ahead rule the intended timing (it extends Q5 of
   docs/stopping_condition_open_questions.md), or should bubble sort's body
   write `Z_{i+1}`?
2. The tutorial states the ranges of its three Einsums (`j ≥ 1`, `i ≥ 1`)
   only in `▷` remarks. As written, all three run at every `(i, j)`. With
   intersect merges (issue 8, question 3) the extra runs write nothing new or
   rewrite the same values, so the answer is right, but pass 0 is rewritten in
   every pass. Should the ranges be restrictions on the Einsums?
3. The single-assignment pass still knows one iterative rank, so bubble sort's
   three writes of `Z` are reported as overlapping (they are, as written).

**Blocks:** the bubble-sort walkthrough. Fixed locally for now (see the end
of this file).

---

## 11. What each round of Populate did, in the evaluation trace

**Where it came up:** the walkthrough page for an Einsum with a mutable rank,
e.g. max-flow E10 and set-cover E01:

```
PushCand_{i+1,u,v*} = Adm_{i,u,v} :: ⋘_{v*} 𝟙(pick-admissible-edge)
F_{i,r*} = S_{i,r} :: ⋘_{r*} 𝟙(select-max-val)
```

**Problem.** `populate_action` runs one round per Reduce Temporary element
(paper §6.6.1; Inset 4): it selects the mutable fiber, calls the coordinate
operator, checks the write-del set against the pre-state and applies it. None
of that is kept. `EinsumResult` has the Reduce Temporary and the caller can
see the output before and after the whole Einsum, so a page can show which
candidates went in and which coordinate came out, but not the order the
schedule offered them in, what the fiber held when each arrived, or what was
written and deleted. Relates to issue 5 (per-label values in the trace) and
issue 6 (a per-Einsum hook): all three ask the evaluator to keep what it
already computes.

**Request.** Optionally record, per round: the iteration-space point, the
incoming element (`cs^R`, `dv_r`), the fiber key and the fiber's locations
(`Loc`), the pre-state `S`, the write-del set, the delete set `D`, the write
set `W` with the value the compute operator produced, the fiber afterwards,
and that `W ∩ (dom(S) ∪ D) = ∅` was checked.

**Checked while doing this: Populate obeys Inset 4.** `_check_constraints`
runs before any delete or write is applied and reads the pre-state: a
coordinate marked Write that is occupied in the pre-state raises
`PopulateConstraintViolation` (a), as does one marked both Delete and Write
(b), and a location deleted in one round can be written by a later one (c).
The existing suite pinned only (a); `tests/test_populate_rounds.py` now pins
all three, including that deleting a location does not free it for a write in
the same round. Nothing in the semantics was changed. Two things the paper
does not ask for and the evaluator does not check, noted in case they should
be: a Delete of a location that is empty in the pre-state is accepted (it is
a no-op), and a write-del set need not have one element per fiber location
(`select-any` may append the incoming coordinate).

Fixed locally for now (see the end of this file).

---

## Local changes in edge-core-ir, for review

Uncommitted edits in edge-core-ir, all needing Toluwa's decision.

Made on 2026-11-16, at Sanjana's request (the page must show exactly how a
Populate executes). All 923 existing tests pass unchanged; 7 new ones:

- issue 11, Populate rounds in the trace: a `PopulateRound` dataclass and an
  optional `rounds=` list on `populate_action` in
  `edge_ir/evaluator/actions/populate.py`; `record_populate=False` on
  `evaluate_einsum` and `EinsumResult.populate_rounds` (None unless asked)
  in `edge_ir/evaluator/einsum.py`; `tests/test_populate_rounds.py`.
  Recording only: off by default, nothing computed differently, `evaluate`
  and `Program` untouched. edge-workbench turns it on from the wrapper it
  already puts around `evaluate_einsum` (issue 6).

Made on 2026-11-16, at Sanjana's request ("add the code to handle cases and
macros as local patches"). All 896 existing tests pass unchanged; 27 new ones:

- issue 8, case statements: `Cases` and `CaseArm` in `edge_ir/ir/einsum.py`
  (`Einsum.expression` admits `Cases`); `edge_ir/evaluator/einsum.py` splits
  Map-and-Reduce from Populate and evaluates a case statement arm by arm
  (`EinsumResult.arms`); the walkers in `edge_ir/analysis/iteration_space.py`,
  `edge_ir/evaluator/iteration.py` and `edge_ir/validator/udf_names.py` read
  arms; `tests/test_case_statement.py`.
- issue 9, macros and conditional cascades: `edge_ir/ir/macro.py` (new);
  `ConditionalCascade`, `ConditionalArm` and `flatten` in
  `edge_ir/ir/einsum.py`; `edge_ir/evaluator/cascade.py` runs a tree-shaped
  body; `edge_ir/validator/single_assignment.py` numbers Einsums as `flatten`
  does and skips pairs in different arms of one conditional cascade;
  `tests/test_conditional_cascade_and_macros.py`.
- issue 10, inner cascades: `NestedCascade.einsums` admits a `NestedCascade`;
  `edge_ir/evaluator/cascade.py` (`pinned` on `run_cascade`, `_rank_bound`,
  `_lookahead`) and `edge_ir/evaluator/stopping.py` (`should_stop(outer=)`);
  `tests/test_nested_cascade.py` and `tests/_bubble_sort_program.py`, the
  bubble-sort program, checked against the tutorial's step table.
- `schemas/program.schema.json` regenerated
  (`json.dumps(Program.model_json_schema(), indent=2)`).

Not changed: any example, any existing test, `Program`'s fields (so every
serialized program still round-trips), her docs.

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

## For the DO-BFS tutorial, not edge-core-ir

The hybrid cascade (Variants, "Hybrid (Direction-Optimizing)") now builds:
`examples/direction-optimizing-bfs/` is the hybrid, and its page runs both
macros (top-down at generation 0, bottom-up from generation 1). What it took,
and what is still a question for the tutorial's authors.

**Resolved, by a decision or in the tool.**

1. **Values for α and β.** Sanjana: "we can set some default from beamers
   paper - α = 15 and β = 18". They are written under `- Constants` in
   `einsum.edge` and lowered to zero-rank declarations carrying the value, so
   they are part of the program, not inputs: an input would have to be
   supplied by every instance, the verifier's random ones included, and the
   approved verifier does not know about them. `check` requires the tutorial
   to state each value; the example's copy of the tutorial has one added
   sentence saying so ("Switch thresholds" note). The published tutorial does
   not have it.
2. **Undeclared tensors.** `einsum.edge` declares `Visited`, `NV`, `Nei`,
   `NeiNV`, `CandTree`, `Temp` (Boolean, empty False), `MF`, `MU`, `NF`
   (integer, empty 0) and `TB`, `BT` (Boolean, empty False) under a comment
   saying those are choices, not the tutorial's.
3. **Unlabelled arithmetic.** `TB_i = TMF_i · (TMU_i / α) :: ⋀ >(∩)` has two
   operations and one action. The action is read as the `·`'s. The division
   states a compute and no merge, and the paper says what that means
   (§7.3.4): "Merge/Coordinate operators are optional, while Compute
   operators must be specified. If a particular operation label does not
   contain a Merge operator, the EDGE machinery applies the Compute operator
   to every point in the iteration space (default pass-through Merge)". So
   the builder lowers `/` as a labelled Map with merge `pass_through`, in
   both `TMU_i / α` and `|V| / β`, and says so at the Einsum. No Einsum was
   changed.
4. **The tool.** `einsum.edge` has a `- Macro NAME(inputs) -> outputs`
   section, a labelled multi-output case statement and a `- Constants`
   section (AUTHORING.md); the tutorial reader reads the `MACRO` blocks that
   follow the selected cascade; the label map follows each call's bindings
   from formal names to actual ones; the IR's conditional cascade is checked
   against the statement arm by arm.

**Still questions for the tutorial.**

1. **Is pass-through what the authors mean for the division?** With
   `MU` empty (no edge into a Not Visited vertex) pass-through computes
   `0 / α = 0`, which equals the anonymous tensor's empty value, so `TB` is
   empty and the mode stays top-down; an intersect would give the same
   result here. The two differ only for an empty value that is not `/`'s
   zero. Writing the action (`⋀¹ /(·) ⋀² >(∩)`) would remove the question.
   Set-cover's builder lowered its unwritten `/` with intersect, before this
   rule was written down; nothing was changed there.
2. **`BT` can never be True on a small graph.** `BT_i = TNF_i · (|V| / β) ::
   ⋀ <(∩)` asks for a frontier smaller than `|V| / 18`. A running bottom-up
   step has at least one frontier vertex, so the switch back to top-down
   needs `|V| > 18`; the worked example has 5 vertices and the verifier's
   random instances at most 8 (the contract caps extents at 12). Both macros
   run, but the `BT ≡ True` row of the tutorial's mode table is never
   exercised. A β below `|V|` for the worked example, or a larger example,
   would show it.
3. **`TMU` counts edges into Not Visited vertices** (`TG_{s,d} · TNV_{i,d}`),
   and the tutorial calls it "the sum of degrees of Not Visited vertices".
   On a directed graph those are in-degrees; Beamer's `m_u` is edges to check
   from unexplored vertices. Is in-degree intended?
4. **`TB` and `BT`.** `TB` carries the formal `T` prefix by accident of its
   name (top-to-bottom) and `BT` does not; neither is a parameter. They are
   read as ordinary tensors of the enclosing cascade, as the paper's "a
   tensor the body names that is not a parameter" would be.
5. **The tutorial defines TOP-DOWN and BOTTOM-UP twice**, once for the hybrid
   and once for the compact hybrid, under the same names. The reader takes
   the blocks that follow the selected cascade.
6. Issue 9's question 3 stands: `TMF`, `TMU` and `TNF` are listed as macro
   inputs and written by the bodies.

The bottom-up cascade has none of these problems and builds on its own: its
`einsum.edge` would name it with `- Cascade: Bottom-Up`.

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
