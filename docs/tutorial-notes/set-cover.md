# Set cover (exact cover): notes for the tutorial's authors

Proposed changes to Toluwa's tutorial (`edge-algorithms/_algorithms/set_cover.md`)
and to `examples/set-cover/`. These are questions about the cascade, not gaps
in the IR or the evaluator; the language questions it raised are issues 1, 2,
3, 4 and 7 in [../issues-for-edge-core-ir.md](../issues-for-edge-core-ir.md).

## E13 cannot use occupancy (open, 2026-11-19)

E13 is `Success_{i+1} = ‖ActiveCol_{i+1}‖ ≡ 0`. Toluwa decided occupancy is
allowed only in a stopping condition (issue 1), so `check` now rejects E13 and
the example does not build. Proposed, waiting for Sanjana's yes:

```
AnyActive^{I} -> Boolean, empty = False          # new tensor

# E13: some column still to cover
AnyActive_{i+1} = ActiveCol_{i+1, c} :: \/_c OR(∪)
# E14: every column covered
Success_{i+1} = not AnyActive_{i+1}
```

Later Einsums shift by one. Run on the evaluator in a scratch copy of the
exact-cover builder, it finds the same two solutions on Working Example 1
(`{0, 1, 3}`, `{2, 3}`). It relies on a reduce over no present values writing
nothing (issue 7) and on `¬` of an empty Boolean being `True`. The site's
tutorial has the same E13; the change goes there too, with Toluwa's agreement.

## Compute the starting stack with Einsums instead of an input

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

## PickedCol is declared Boolean but holds a count

E17 is `PickedCol_{i+1,c*} = ActiveCounts_{i+1,c} :: ⋘_{c*} 𝟙(select-min-val)`.
A populate's `𝟙` is pass-through (paper §5.8), so the column's count goes into
`PickedCol`, which the tutorial declares Boolean. Nothing depends on the number:
E18 uses only its presence. The walkthrough records a Boolean tensor's values as
`true`, so a reader sees what the declaration says; the Einsum is unchanged.

**Resolved (2026-11-15).** The declaration is now `integer, empty = 0`, the
same empty value as `ActiveCounts`, in the example's tutorial and `einsum.edge`.
E17 is unchanged. `edge-core-ir` does not enforce declared types, so nothing
had flagged this.
