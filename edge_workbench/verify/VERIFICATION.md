# Are the cascades correct?

Each tutorial has a `verify_algorithm.py` that answers this for its own
algorithm. They follow the same four-part discipline, so adding a new
algorithm to the zoo means writing one file to the same shape.

```
maxflow/viz/verify_algorithm.py     18 checks
Bellman_Ford/verify_algorithm.py    22 checks
DO_BFS/verify_algorithm.py          20 checks
```

Run any of them directly, or with `--self-test` to confirm they can still
fail. `maxflow/viz/build_viz.py` runs its verifier before writing the viz.

## The discipline

**1. The trusted answer comes from outside.** Max-flow uses CLRS Figure 26.1,
whose maximum flow of 23 is published. Bellman–Ford and DO-BFS use their own
tutorials' worked examples, which pins the prose and the cascade together —
if someone edits one, the check fails.

**2. The result is validated, not just compared.** A number matching an oracle
is weaker than it looks. So:

| | what is checked |
|---|---|
| max-flow | capacity, antisymmetry, conservation at internal vertices, source value = sink value |
| Bellman–Ford | every edge relaxed, **and** every finite distance witnessed by a real path |
| DO-BFS | every parent is a real neighbour exactly one level up; every reachable vertex has one |

The second Bellman–Ford condition matters: tight relaxation alone is satisfied
by all-zero distances on a non-negative graph.

**3. The oracle is a different algorithm.** Three implementations of the same
algorithm can share a misconception.

| | oracle | why it is independent |
|---|---|---|
| max-flow | Edmonds–Karp | augmenting paths, not preflow; no height function |
| Bellman–Ford | Dijkstra, and brute-force path enumeration | one is greedy, the other assumes nothing about how shortest paths are found |
| DO-BFS | plain queue BFS | shares no structure with push, pull or the hybrid |

**4. Free choices must not change the answer.** Every cascade has something
the spec deliberately leaves open, and each verifier checks that it really is
free:

- max-flow — `pick-admissible-edge`: 50 selector choices, same feasible flow
- DO-BFS — `pick-parent`: 30 parent choices, same levels; and the α/β switch
  point swept across five settings
- DO-BFS — top-down, bottom-up and hybrid must agree on every graph

## Why `--self-test` exists

A verifier that cannot fail is worthless, so each one injects known faults and
asserts every fault is caught. This is not ceremony — it changed what the
verifiers do.

**Max-flow.** Of four faults, three are caught by the CLRS example. The fourth
— `d(s) = 0`, source height left at 0 instead of `|V|` — still produces a
*valid* flow of 23 on that graph. The random-graph property test catches it on
192 of 200 graphs, the first included. This is the concrete argument for
property testing over worked examples.

**DO-BFS.** Two faults initially went uncaught. One was a broken injection
(fixed). The other, forcing the hybrid never to switch direction, is *not a
correctness bug at all* — it is a performance choice, and the verifier was
right to pass it. That case moved to an "invariants" group asserting it must
**not** change the answer, which is a stronger statement than deleting it
would have been.

## Adding an algorithm

1. Transcribe the cascade into a runnable form in the verifier — bulk-
   synchronous, mirroring the Einsums.
2. Pin the tutorial's worked example.
3. Write a validator for what a correct result *is*, not just what it equals.
4. Pick an oracle with different structure.
5. List the spec's free choices and assert they are free.
6. Inject faults; if one is not caught, ask whether it is really a fault
   before adding a check for it.
