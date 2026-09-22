# -*- coding: utf-8 -*-
"""The textbook push-relabel, transcribed from the notebook's pseudocode.

This is the reference the EDGE cascade is raced against. It is deliberately a
*literal* transcription of `PushRelabel(G, s, t)` in
`Push_Relabel_Max_Flow.ipynb` -- one operation per step, no queue discipline,
no batching:

    while there exists an active vertex v:
        if there is an admissible edge (v, w):  push
        else:                                   relabel

The point of the comparison is that nobody parallelised anything here or
there. The same algorithm written in EDGE came out bulk-synchronous because
Einsums evaluate every point of their iteration space independently; written
as a while-loop it comes out one-operation-at-a-time. So the two traces have
to be the same algorithm, and this file must not quietly improve on it.

Selection rule: the pseudocode says only "there exists an active vertex", so
any rule is a faithful reading. We take the lowest-numbered active vertex --
deterministic, and it makes no claim the pseudocode does not. That vertex
choice is the ONE thing that differs from the parallel run; the edge choice is
held identical (see SEED below) so the comparison isolates it.

Emits a trace in the shared schema (see TRACE_SCHEMA.md), so the viewer draws
it with the same graph renderer as the EDGE trace.
"""

import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))

# `pick-admissible-edge` may choose any admissible edge. The parallel
# evaluator (eval_edge.py) chooses at random from a seeded generator; this
# side does the same, with the same seed, so the ONLY difference between the
# two runs in compare mode is the vertex selector. Holding the edge rule
# fixed is what makes the comparison about parallelism rather than about two
# unrelated scheduling choices.
SEED = int(os.environ.get("SEED", "0"))

N = 6
S = 0
T = 5
CAP = {(0, 1): 16, (0, 2): 13, (1, 2): 10, (2, 1): 4, (1, 3): 12,
       (3, 2): 9, (2, 4): 14, (4, 3): 7, (3, 5): 20, (4, 5): 4}


def k(*c):
    return ",".join(map(str, c))


def run():
    rng = random.Random(SEED)
    # --- initialization, straight from the pseudocode -------------------
    F = {}                       # f(u,v), antisymmetric
    R = {}                       # r(u,v), residual
    for (u, v), c in CAP.items():
        R[(u, v)] = c
        R.setdefault((v, u), 0)
    D = {u: 0 for u in range(N)}
    E = {u: 0 for u in range(N)}
    D[S] = N

    for (u, v), c in CAP.items():
        if u != S:
            continue
        F[(u, v)] = c
        F[(v, u)] = -c
        R[(u, v)] = 0
        R[(v, u)] = R.get((v, u), 0) + c
        E[v] += c
        E[S] -= c

    steps = []

    def active():
        return [u for u in range(N)
                if u not in (S, T) and E.get(u, 0) > 0]

    def snapshot():
        act = {k(u): True for u in active()}
        return {
            "C": {k(u, v): c for (u, v), c in CAP.items()},
            "S": {k(S): True},
            "T": {k(T): True},
            "F": {k(u, v): f for (u, v), f in F.items() if f != 0},
            "R": {k(u, v): r for (u, v), r in R.items() if r != 0},
            "E": {k(u): e for u, e in E.items() if e != 0},
            "D": dict((k(u), d) for u, d in D.items()),
            "Act": act,
        }

    def rec(kind, caption, hl, actor=None, target=None, delta=None):
        steps.append({
            "id": len(steps),
            "round": len(steps),          # one operation per round
            "opKind": kind,
            "actor": actor,
            "target": target,
            "delta": delta,
            "caption": caption,
            "graphHighlight": hl,
            "state": snapshot(),
        })

    rec("init",
        "Saturate every edge out of the source, set d(s) = |V|.",
        {"nodes": [S], "edges": [[S, v] for (u, v) in CAP if u == S]})

    ops = {"push": 0, "relabel": 0}
    guard = 0
    while True:
        guard += 1
        if guard > 10000:
            raise RuntimeError("did not terminate")
        act = active()
        if not act:
            break
        # The pseudocode says only "there exists an active vertex", so any rule
        # is a faithful reading. Lowest-numbered is deterministic and claims
        # nothing the pseudocode does not. THIS is the serialisation point --
        # the one thing that differs from the parallel run.
        v = min(act)

        adm = [w for w in range(N)
               if R.get((v, w), 0) > 0 and D[v] == D[w] + 1]
        if adm:
            w = rng.choice(sorted(adm))    # same rule as the parallel side
            excess, resid = E[v], R[(v, w)]
            delta = min(excess, resid)
            F[(v, w)] = F.get((v, w), 0) + delta
            F[(w, v)] = F.get((w, v), 0) - delta
            R[(v, w)] -= delta
            R[(w, v)] = R.get((w, v), 0) + delta
            E[v] -= delta
            E[w] += delta
            ops["push"] += 1
            rec("push",
                f"Push {delta} from {v} to {w} — "
                f"min(excess {excess}, residual {resid}).",
                {"nodes": [v], "edges": [[v, w]]}, v, w, delta)
        else:
            nb = [D[w] for w in range(N) if R.get((v, w), 0) > 0]
            old = D[v]
            D[v] = 1 + min(nb)
            ops["relabel"] += 1
            rec("relabel",
                f"Vertex {v} has excess but no admissible edge: "
                f"raise d({v}) from {old} to {D[v]}.",
                {"nodes": [v], "edges": []}, v, None, None)

    maxflow = sum(F.get((v, T), 0) for v in range(N))
    rec("done", f"No vertex has excess. Maximum flow = {maxflow}.",
        {"nodes": [T], "edges": []})

    return {
        # ---- shared trace header ----------------------------------------
        "algorithm": "max-flow",
        "variant": "sequential",
        "label": "Sequential — the pseudocode",
        "sublabel": "one push or relabel per step",
        "domainView": "graph",
        "rounds": len(steps) - 2,          # exclude init and done
        "operations": ops["push"] + ops["relabel"],
        "opCounts": ops,
        "maxFlow": maxflow, "headline": {"label": "max flow", "value": maxflow},
        "graph": {
            "nodes": list(range(N)),
            "source": S,
            "sink": T,
            "edges": [{"u": u, "v": v, "cap": c} for (u, v), c in CAP.items()],
        },
        "steps": steps,
    }


if __name__ == "__main__":
    tr = run()
    out = os.path.join(HERE, "maxflow_seq_trace.json")
    with open(out, "w") as fh:
        json.dump(tr, fh)
    print(f"{out}: {len(tr['steps'])} steps, "
          f"{tr['operations']} operations "
          f"({tr['opCounts']['push']} pushes, {tr['opCounts']['relabel']} relabels), "
          f"max flow {tr['maxFlow']}")
