# Worked examples

Two author directories, laid out exactly as [AUTHORING.md](../AUTHORING.md)
describes, that pass every check:

```
python3 -m edge_workbench check examples/maximum-flow     # graph view, max flow 5
python3 -m edge_workbench check examples/set-cover        # bipartite view, 2 solutions
```

Each writes `index.html` into its directory. Only the inputs are committed;
everything `check` regenerates is ignored (see `.gitignore`).

| file | role | | 
|---|---|---|
| `<name>.md` | the tutorial | author |
| `einsum.edge` | the cascade, labelled | author |
| `verifier.py` | independent answers | author |
| `workbench/spec/build_*_program.py`, `*_functions.py` | builder | model step 1, already checked |
| `workbench/spec/authored.json` | meanings, worked example, styling | model step 2, already checked |

Because the two model replies are committed, these run without a chat. To see
the model steps themselves, delete the builder and `authored.json` from a copy
and run `check` on it.

## Where these came from

Be aware of what is and is not the published material:

**maximum-flow**
- Tutorial: `edge-algorithms` `main`, with E03 and E13 rewritten to the
  notebook's form (`E_{1,v} = F_{1,u,v}`, `InPush_{i,v} = δ_{i,u,v}`). That
  edit is not yet committed upstream.
- `einsum.edge` and the builder: edge-core-ir's max-flow.
- Verifier: Edmonds-Karp.

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
- Verifier: brute-force subset search.

The verifiers and the max-flow tutorial data were written by hand while the
workflow was being built, standing in for an author and a model. Neither
model step has yet been run end to end from a fresh chat.
