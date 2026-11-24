# Bubble sort: notes for the tutorial's authors

What `examples/bubble-sort/` needed beyond the tutorial. The language
questions it raised are issues 8 and 10 in
[../issues-for-edge-core-ir.md](../issues-for-edge-core-ir.md).

## The ranges of the three Einsums (resolved)

The tutorial states the ranges of its three Einsums (`j ≥ 1`, `i ≥ 1`) only
in `▷` remarks, so as written all three run at every `(i, j)`. With
intersect merges the extra runs write nothing new or rewrite the same values,
so the answer was right, but pass 0 was rewritten in every pass.

**Resolved (Sanjana):** the ranges are written into the Einsums as
restrictions, the step tensor's empty value is `+∞`, and `∩` is kept for
`min`/`max`. The site's tutorial still has the remarks.

## `min(x, y)` arms and their merge

An arm written `min(Z_{0,j-1,j}, A_{j+1})` states no merge. With the paper's
default, pass-through, `max(Z_{0,j-1,j}, A_{j+1})` at `j = 0` reads the empty
`Z_{0,-1,0}` and writes `A_1` where the initialization wrote
`max(A_0, A_1)`. The example uses intersect and says so; issue 8, question 3,
asks what the shorthand should mean. Writing the arm with an action
(`x . y :: /\ min(∩)`) would settle it in the tutorial.
