# What the workbench needs from the evaluator

edge-core-ir's job is EDGE's semantics. What the walkthrough page needs on
top of that is the workbench's to build, around the evaluator, not inside it
(Sanjana, 2026-11-19). The rule stays: nothing here evaluates an Einsum; it
only watches edge-core-ir's evaluator do it. These were issues 5, 6 and 11
in [issues-for-edge-core-ir.md](issues-for-edge-core-ir.md), and the
local edits listed at the end.

## Tensors between Einsums (was issue 6)

The page needs the tensors just before and just after every Einsum.
`evaluate` returns only the final tensors and an `EinsumResult` per Einsum.

**How the workbench gets it.** `driver/run.py` wraps `evaluate_einsum` for
the duration of a run, under the name `edge_ir.evaluator.cascade` and
`edge_ir.evaluator.program` call it by.

**Risk.** It depends on that internal call. If edge-core-ir renames it, the
driver breaks loudly, not silently: the tests in `tests/test_examples_pass.py`
fail. Worth a hook upstream only if Toluwa wants one for her own tools.

## Per-label values inside a parenthesized Einsum (was issue 5)

The "how this value is computed" panel would show, for an Einsum like
max-flow E11, `(E ·¹ R) ·² PushCand :: ⋀¹ min(∩) ⋀² ←(∩)`, what label 1
produced at each point before label 2 used it. `EinsumResult` keeps only the
final Map value and the Reduce result.

**Not built.** Options that keep the evaluator unchanged: wrap the compute
operators the workbench registers, as for Populate below, and record each
call with its label; or show only operands and result, as today.

## What each round of Populate did (was issue 11)

The page shows each round of a Populate with a mutable rank (paper §6.6.1,
Inset 4): the incoming element, the fiber's pre-state, the write-del set,
the delete and write sets, and the fiber afterwards.

**How the workbench gets it** (since 2026-11-19; before that, an
edge-core-ir patch). `populate_action` calls
`coord_impl.call(fiber, cs_z, dv_r, ctx=ctx)` once per round, and the
workbench supplies the registry `coord_impl` comes from. For each Einsum with
a mutable rank, `driver/run.py` (`_watching_populate`) swaps in a recording
copy of its coordinate operator through the registry's public `register(...,
allow_override=True)`, and puts the original back afterwards. It records
`cs^R`, `dv_r`, the point, the fiber's locations and pre-state, and the
write-del set; `_finish_rounds` derives `D` and `W` from that set and each
round's post-state from the next round's fiber (or the Einsum's output). The
`W ∩ (dom(S) ∪ D) = ∅` check stays the evaluator's: a violation raises there,
so a recorded round of an Einsum that returned passed it.

Checked when it moved: on every populate step of the six building examples,
sequential and shuffled, the page data is byte-identical to the patch's; on
`select-min-val`/`select-max-val` fixtures with ties and a pre-filled fiber,
every field of every round is identical (12 of 12 runs, in a one-off
comparison). `tests/test_populate_recording.py` pins the recording from now
on (`select-min-val` round by round, `select-any` under shuffled schedules).

## Local edits in edge-core-ir that moved here (2026-11-19)

Made in edge-core-ir for the workbench's sake, and taken back out of its
`fixes_for_edge_workbench` branch.

| edit that was in edge-core-ir | where it is now |
|---|---|
| issue 11's populate recording | coordinate-operator wrapper, above |
| `select-any` and unary `floor` in `edge_ir/udf/builtins.py`; `pick-admissible-edge` as an alias | `edge_workbench/operators.py` (`base_registry()`, `alias()`), which every example's `*_functions.py` starts from; a free populate name is the workbench's reading, not EDGE's. edge-core-ir's max-flow example defines its own `pick-admissible-edge`. |
| `edge_ir/ir/macro.py` (macro expansion) | `edge_workbench/macro.py`, used by the builder: a macro is lexical substitution (paper B.8), and edge-core-ir's IR is the desugared form (its D3), so expansion is a front end's job. The conditional cascade it expands into stays an edge-core-ir question (issue 9). |
| `examples/algorithms/exact-cover/` | removed; `examples/set-cover/` is the workbench's copy, and issue 2 keeps its two small-program tests |

Kept in edge-core-ir: `edge_ir/validator/udf_names.py` (checks every operator
a program names is registered). It is on her own plan (Layer 2 validator,
VAL-2), not a workbench need.
