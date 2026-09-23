# Algorithm X: a probe, not an algorithm

This directory is **not a working Algorithm X**. It is the thinnest spec that
makes the tool actually run, written to find out where the tool breaks on a
non-graph algorithm with two differently-sized ranks. Seven of the cascade's
eighteen Einsums are here; `Path`, the stack update and the relabel-equivalent
are not, so it does not terminate and does not compute an exact cover.

Nothing here should be trusted as a specification. When Algorithm X is done
properly this directory gets replaced, not extended.

Run it with:

```
EDGE_WORKBENCH_ALG=algorithm-x python3 edge_workbench/render/build_page.py
```

## What it found, in the order the tool hits it

| # | where | what happens |
|---|---|---|
| 1 | `paths.default()` | a second algorithm makes every command ambiguous; `npm test` stops working until `EDGE_WORKBENCH_ALG` is set |
| 2 | `cascade.js` `extentOf` | **`R`=4, `C`=3 is refused.** The interpreter assumes one global `N`. Clear message, planted earlier. |
| 3 | — | forcing `R`=`C`=4 gets past it, which is how the rest of this list was found |
| 4 | `selectors.js` | the selector is keyed on the populate's **compute** op (`identity`), not its **coordinate** op (`select-max-val`). Upstream's registry separates the two categories; this does not. |
| 5 | `edge_interp.js` | `any_of` is not a known compute op |
| 6 | `edge_interp.js` | **an unknown operator is swallowed.** `ge` raises inside `evalNode`, the per-point `try/catch` turns the point into *absent*, and the cascade runs to the generation cap producing empty tensors. No diagnostic reaches the author. |
| 7 | `verify_interp.js` | still opens `maxflow_edge_trace.json` by name, and reports the absence as *"the interpreter disagrees with the trace"* |
| 8 | the renderer | `domainView: "matrix"` has no renderer; the pane blanks (by design) but there is nothing to see |
| 9 | `orient()` | `AXIS_OF_VAR` knows only `u` and `v`, so every `R`- and `C`-ranked 1-D tensor draws vertically; a 2-D grid is `N × N`, so `A` would be drawn 4×4 instead of 4×3 |

## What worked

- the **driver ran** a non-graph cascade end to end once the operators existed;
- `annotate.py`'s generic path produced usable captions and highlights from
  state alone with **no view module at all** (`F  3 = 7`, highlight on node 3);
- the empty-value build gate accepted the declarations;
- the selector registry already knows `select-max-val` and `select-min-val` —
  the only problem was which name it was looked up by;
- `meta.py`, `GROUPS`, `STATEFUL`, `TITLE` were read without complaint;
- **max-flow still passes everything** with the probe present.

## Ranked by what it would cost to fix

1. **Swallowed operator errors** (6). Cheap, and the worst of these: a tool
   that exists to catch authors' mistakes currently hides them behind an empty
   result and a generation-cap timeout. Should name the operator and stop.
2. **Selector keyed on the wrong op** (4). Cheap. Look up the coordinate op,
   fall back to the compute op, and say which when neither is mapped.
3. **Missing operators** (5). Cheap and mechanical: `ge`, `le`, `ne`, `any_of`,
   `floordiv`. Better taken from upstream's registry than invented here.
4. **Per-rank extents** (2, 9). The real work. Touches `extentOf`, `orient`,
   `miniGrid`, `block` and a chunk of the page checks.
5. **A matrix domain view** (8). Self-contained new renderer, but only worth
   building once 4 is done, since it needs non-square grids.
6. **Multi-algorithm ergonomics** (1) and the hard-coded trace name (7). Small.

## Not reached

`σ(depth, r) = depth · |R| + r` — a **value computed from a rank coordinate**.
The probe omits every Einsum that needs it, because it is not clear the IR can
express it at all. That question is for Toluwa, and it blocks the stack
discipline, which is most of Algorithm X.
