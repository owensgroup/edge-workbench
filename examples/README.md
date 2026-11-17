# Worked examples

Four author directories, laid out exactly as [AUTHORING.md](../AUTHORING.md)
describes, that pass every check once their verifiers are approved:

```
python3 -m edge_workbench check examples/maximum-flow              # graph view, max flow 5
python3 -m edge_workbench check examples/set-cover                 # bipartite view, 2 solutions
python3 -m edge_workbench check examples/bellman-ford              # graph view
python3 -m edge_workbench check examples/direction-optimizing-bfs  # graph view, hybrid: both macros run
```

Each writes `index.html` into its directory. Only the inputs are committed;
everything `check` regenerates is ignored (see `.gitignore`).

| file | role | |
|---|---|---|
| `<name>.md` | the tutorial | author |
| `einsum.edge` | the cascade, labelled | author |
| `verifier.py` | independent answers (`KIND`, `METHOD`, `solve`, `answer`, `random_instance`, optional `certify`) | author |
| `verifier.lock` | the approved verifier and published answer | written by `approve-verifier`, run by a person |
| `workbench/spec/build_*_program.py`, `*_functions.py` | builder | model step 1, already checked |
| `workbench/spec/authored.json` | meanings, worked example, styling | model step 2, already checked |

Until a person has run `python3 -m edge_workbench approve-verifier
examples/<name>` and committed the lock, `check` stops at its first stage and
says so.

Because the model replies are committed, these run without a chat. To see
the model steps themselves, delete the builder and `authored.json` from a copy
and run `check` on it.

## Where these came from

Be aware of what is and is not the published material:

**maximum-flow**
- Tutorial: `edge-algorithms` `main`, with E03 and E13 rewritten to the
  notebook's form (`E_{1,v} = F_{1,u,v}`, `InPush_{i,v} = δ_{i,u,v}`). That
  edit is not yet committed upstream.
- `einsum.edge` and the builder: edge-core-ir's max-flow.
- Verifier: Edmonds-Karp (`different-algorithm`), plus `certify`: capacity,
  conservation and a saturated cut (max-flow min-cut) on the cascade's own F.

**set-cover** (Knuth's Algorithm X)
- Tutorial: `edge-algorithms` branch `add-set-cover-algorithm`, with **one
  change the author has not made**: E04 is split in two, because as written
  (`TPath = Path · d* :: ⋀ <(∩)`) it turns depths into `True` and the
  verifier rejects it on 10 of 14 instances:

  ```
  Keep_{i,r}  = Path_{i,r} · d*_i       :: ⋀ <(∩)
  TPath_{i,r} = Path_{i,r} · Keep_{i,r} :: ⋀ ←(∩)
  ```

  Everything after it is renumbered (E20 Einsums in all), and `Keep` is
  declared. The initialization is also changed, from the prose
  `S_0 = initial candidates at depth 1 ...` to `S_{0,r} = InitS_r`, with
  `InitS` a user-specified input; `Path_0 = empty` is dropped, since outputs
  start empty.
- Every Einsum lowers to exactly one IR Einsum (20 for 20), with no helper
  tensors. E02, E12, E13, E18 and E19 are written in the IR in the paper's
  parenthesized, labelled form, and the walkthrough steps through the labels.
  E13 (`‖ActiveCol‖ ≡ 0`) uses `Occupancy`, an expression node added locally
  to edge-core-ir for it.
- `einsum.edge`: a line-by-line transcription of that tutorial. It also
  declares the tensors the tutorial uses without declaring (`F`, `d*`,
  `TPath`, `NewPathEntry`, `Col`, `Row`) and the stack seed `InitS`.
- Verifier: brute-force subset search (`definition`).

**bellman-ford**
- Tutorial: `edge-algorithms` `main`.
- Verifier: Floyd-Warshall (`different-algorithm`).

**direction-optimizing-bfs**
- Tutorial: `edge-algorithms` `main`, with **one sentence added** to the
  "Switch thresholds" note: "The walkthrough of the hybrid cascade uses the
  default values from Beamer et al. (2012), $\alpha = 15$ and $\beta = 18$."
  The tutorial leaves the thresholds to the user; the defaults are Sanjana's
  choice. No Einsum is changed.
- `einsum.edge` transcribes the tutorial's **hybrid** cascade
  (`- Cascade: Hybrid`) and its two macros, TOP-DOWN and BOTTOM-UP, line for
  line. It also declares the tensors the hybrid uses without declaring
  (`Visited`, `NV`, `Nei`, `NeiNV`, `CandTree`, `Temp`, `MF`, `MU`, `NF`,
  `TB`, `BT`), with types and empty values that are choices, and the two
  thresholds under `- Constants`.
- The worked example (five vertices) runs top-down at generation 0, switches
  (2 frontier edges > 5 / 15), and runs bottom-up for generations 1 to 3.
  It never switches back, and nothing small can: that needs a frontier
  smaller than `|V| / 18`.
- `TMU_i / α` and `|V| / β` are written with no action, so they run with the
  paper's default pass-through merge (§7.3.4); see
  `docs/issues-for-edge-core-ir.md`, "For the DO-BFS tutorial".
- Verifier: Floyd-Warshall (`different-algorithm`), depths on unit edges,
  compared as depths rather than parents. It is the one approved for the
  top-down cascade, unchanged: the hybrid ends with the same `Tree`, and the
  published answer is the same.

The verifiers and the max-flow tutorial data were written by hand while the
workflow was being built, standing in for an author and a model. Both model
replies were applied from a chat for bellman-ford and direction-optimizing-bfs
(`workbench/replies/*.applied.*`); set-cover has only the tutorial-data reply
applied, and maximum-flow neither.
