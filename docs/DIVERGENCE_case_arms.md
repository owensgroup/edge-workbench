# A lowered `cases` arm cannot clear what an earlier arm wrote

**Found:** 2026-09-22, by running this repo's driver and the reference
evaluator in `edge-ir-interpreter` over the same max-flow program and
comparing the loop-carried state cell by cell.

**Affects:** `R`, max-flow, `E04`. Does not change the answer.

**For:** Toluwa — this is a question about the IR's semantics, not a bug
report against the evaluator alone.

## What happens

E04 in the write-up is one Einsum with three arms:

```
R_{1,u,v} = ⎧ 0        u = s
            ⎨ C_{v,u}  v = s ∧ u ≠ s
            ⎩ C_{u,v}  otherwise
```

`build_max_flow_program.py` lowers it to three IR Einsums emitted in **reverse
priority** — otherwise, then `v = s`, then `u = s` — relying on later
assignments overwriting earlier ones. That comment is explicit: "later einsums
overwrite earlier ones, so the arms are emitted in REVERSE priority."

The `u = s` arm computes `0`. `R`'s empty value is `0`. So under
`value == empty ⟹ absent`, that arm is asking for the source's row to be
**cleared**: the preflow saturated every edge out of `s`, so there is no
residual there.

The reference evaluator treats an assignment as only ever adding values, so
writing the empty value writes nothing, and the `otherwise` arm's capacities
stay put:

```
reference   R_1[0,1] = 16   R_1[0,2] = 13     ( == C[0,1], C[0,2] )
this repo   R_1[0,1] = —    R_1[0,2] = —      ( cleared, as the spec says )
```

The difference persists to the end of the run: `R_13[0,2]` is 19 upstream
(13 + the 6 units that returned to the source) and 6 here.

## Why it has not shown up before

It does not change the answer. `D[s] = |V|` holds from initialization, so the
source is never active, so nothing ever pushes along the phantom residual. The
acceptance test in `tests/test_evaluator_acceptance.py` checks the flow — value,
feasibility, conservation, antisymmetry — and the flow is correct.

That is the general shape of the risk: a wrong intermediate that the algorithm
happens never to read. Only a state-level comparison against a second
implementation finds it, which is what this repo now runs.

## Which reading is right

The write-up's is not ambiguous: `R_{1,s,v} = 0` means the residual out of the
source is zero. `R` is supposed to *be* the residual graph, and upstream's `R`
is not one — it reports capacity on saturated edges.

So either:

1. **An assignment replaces the fiber it writes.** Writing the empty value
   clears the cell. This is what this repo's driver does, and what makes the
   lowering comment ("later einsums overwrite earlier ones") true as written.

2. **Case arms are lowered with disjoint predicates** instead of relying on
   overwrite order. Each arm restricts its own domain — `u = s`, `v = s ∧ u ≠ s`,
   `u ≠ s ∧ v ≠ s` — so no arm ever needs to blank another's work, and both
   semantics agree because they never overlap.

(2) is the more conservative fix and probably the better one: it makes the
lowering independent of assignment semantics entirely, and it removes a
silent dependence on emission order that a reader of the IR cannot see. It
also means the single-assignment validator has something real to check —
under (2) each cell of `R_1` is written exactly once.

(1) is a larger change and cuts against "an assignment only adds values",
which is the rule `AdmPost` was introduced to work around. Worth noting that
`AdmPost` and this are the same question from two directions: one is a tensor
that needed splitting because assignments accumulate across generations, the
other is a tensor that needs clearing because arms accumulate within one.

## How it is pinned here

`tests/test_agrees_with_reference.py` does not skip `R`. It asserts the
divergence has exactly this shape: the two agree on every row except the
source's, and the reference's surplus there is exactly the capacities the
`u = s` arm should have cleared. If upstream fixes it, that assertion fails
and the exception gets deleted. If it changes shape, that assertion fails and
we look again.
