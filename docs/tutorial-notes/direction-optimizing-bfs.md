# Direction-optimizing BFS: notes for the tutorial's authors

Questions about the DO-BFS tutorial (`edge-algorithms/_algorithms/`) and what
`examples/direction-optimizing-bfs/` needed to run it. None of these is a gap
in edge-core-ir; the language questions it raised are issue 9 in
[../issues-for-edge-core-ir.md](../issues-for-edge-core-ir.md).

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
6. **Macro inputs that the body writes.** `TTopDown_{i+1}` is declared an
   output of both macros, but `TMF_i`/`TMU_i`/`TNF_i`, which the bodies also
   write, are listed as inputs. Should they be outputs?

The bottom-up cascade has none of these problems and builds on its own: its
`einsum.edge` would name it with `- Cascade: Bottom-Up`.
