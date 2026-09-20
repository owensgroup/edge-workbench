# -*- coding: utf-8 -*-
"""Measure how the two runs scale, and write scaling.json.

Six vertices cannot make the parallelism case: the demo graph reaches a peak
of three concurrent operations, so the parallel run is only about 2.4x
shallower. The interesting claim is that the gap *grows* with the graph, and
that it is a depth reduction rather than a work reduction. This runs both
algorithms over random graphs of increasing size to check exactly that.

Both simulators here are stripped down -- no trace, just counters -- because
this is measurement, not animation. The push-relabel logic mirrors
`seq_pushrelabel.py` and `eval_edge.py`; if either of those changes in a way
that alters operation counts, this should be re-run.

Every pair is asserted to agree on the max flow, so a scaling row can never
report a speedup over a run that computed the wrong answer.
"""

import json, os, random, statistics

HERE = os.path.dirname(os.path.abspath(__file__))

SIZES = [6, 10, 20, 40, 80, 150, 300]
TRIALS = 9
DEGREE = 3


def make_graph(n, rng):
    cap = {}
    for u in range(n):
        for _ in range(DEGREE):
            v = rng.randrange(n)
            if v != u and (v, u) not in cap and (u, v) not in cap:
                cap[(u, v)] = rng.randint(1, 20)
    for v in range(1, min(DEGREE + 1, n)):
        cap.setdefault((0, v), rng.randint(5, 20))
    for u in range(max(1, n - DEGREE - 1), n - 1):
        cap.setdefault((u, n - 1), rng.randint(5, 20))
    return cap


def _init(cap, n, s):
    F, R = {}, {}
    for (u, v), c in cap.items():
        R[(u, v)] = R.get((u, v), 0) + c
    D = {u: 0 for u in range(n)}
    D[s] = n
    E = {u: 0 for u in range(n)}
    for (u, v), c in cap.items():
        if u == s:
            F[(u, v)] = c
            F[(v, u)] = -c
            E[v] += c
            E[s] -= c
            R[(u, v)] = 0
            R[(v, u)] = R.get((v, u), 0) + c
    return F, R, D, E


def sequential(cap, n, s, t):
    """One operation per round -- the notebook's pseudocode."""
    F, R, D, E = _init(cap, n, s)
    ops = 0
    while True:
        act = [u for u in range(n) if u not in (s, t) and E[u] > 0]
        if not act:
            break
        v = min(act)
        ops += 1
        adm = [w for w in range(n)
               if R.get((v, w), 0) > 0 and D[v] == D[w] + 1]
        if adm:
            w = min(adm)
            d = min(E[v], R[(v, w)])
            F[(v, w)] = F.get((v, w), 0) + d
            F[(w, v)] = F.get((w, v), 0) - d
            R[(v, w)] -= d
            R[(w, v)] = R.get((w, v), 0) + d
            E[v] -= d
            E[w] += d
        else:
            D[v] = 1 + min(D[w] for w in range(n) if R.get((v, w), 0) > 0)
    return {"rounds": ops, "operations": ops, "peak": 1,
            "flow": sum(F.get((v, t), 0) for v in range(n))}


def parallel(cap, n, s, t, seed):
    """One bulk-synchronous round: all pushes, sync, all relabels."""
    rng = random.Random(seed)
    F, R, D, E = _init(cap, n, s)
    rounds = ops = peak = 0
    while True:
        act = [u for u in range(n) if u not in (s, t) and E[u] > 0]
        if not act:
            break
        rounds += 1
        delta = {}
        for u in act:
            adm = [v for v in range(n)
                   if R.get((u, v), 0) > 0 and D[u] == D[v] + 1]
            if adm:
                v = rng.choice(adm)
                delta[(u, v)] = min(E[u], R[(u, v)])
        for (u, v), d in delta.items():
            F[(u, v)] = F.get((u, v), 0) + d
            F[(v, u)] = F.get((v, u), 0) - d
            R[(u, v)] -= d
            R[(v, u)] = R.get((v, u), 0) + d
            E[u] -= d
            E[v] += d
        act2 = [u for u in range(n) if u not in (s, t) and E[u] > 0]
        rel = {}
        for u in act2:
            if not any(R.get((u, v), 0) > 0 and D[u] == D[v] + 1
                       for v in range(n)):
                nb = [D[v] for v in range(n) if R.get((u, v), 0) > 0]
                if nb:
                    rel[u] = 1 + min(nb)
        D.update(rel)
        ops += len(delta) + len(rel)
        peak = max(peak, len(delta), len(rel))
        if not delta and not rel:
            break
    return {"rounds": rounds, "operations": ops, "peak": peak,
            "flow": sum(F.get((v, t), 0) for v in range(n))}


def main():
    rows = []
    for n in SIZES:
        seq_r, par_r, seq_o, par_o, peaks, ratios = [], [], [], [], [], []
        for tri in range(TRIALS):
            rng = random.Random(1000 + tri)
            cap = make_graph(n, rng)
            a = sequential(cap, n, 0, n - 1)
            b = parallel(cap, n, 0, n - 1, seed=tri)
            assert a["flow"] == b["flow"], (
                f"n={n} trial={tri}: sequential got {a['flow']}, "
                f"parallel got {b['flow']} -- a scaling row must never "
                f"compare runs that disagree on the answer")
            seq_r.append(a["rounds"]); par_r.append(b["rounds"])
            seq_o.append(a["operations"]); par_o.append(b["operations"])
            peaks.append(b["peak"])
            ratios.append(a["rounds"] / b["rounds"])
        rows.append({
            "n": n,
            "edges": len(cap),
            "seqRounds": round(statistics.mean(seq_r)),
            "parRounds": round(statistics.mean(par_r)),
            "seqOps": round(statistics.mean(seq_o)),
            "parOps": round(statistics.mean(par_o)),
            "peak": round(statistics.mean(peaks), 1),
            "ratio": round(statistics.mean(ratios), 2),
            "ratioLo": round(min(ratios), 2),
            "ratioHi": round(max(ratios), 2),
        })
        r = rows[-1]
        print(f"n={n:<4} edges={r['edges']:<4} "
              f"seq {r['seqRounds']:>6} rounds / {r['seqOps']:>6} ops   "
              f"par {r['parRounds']:>5} rounds / {r['parOps']:>6} ops   "
              f"peak {r['peak']:>4}   depth x{r['ratio']} "
              f"({r['ratioLo']}-{r['ratioHi']})")

    out = {
        "trials": TRIALS,
        "degree": DEGREE,
        "note": ("Random graphs, average of %d trials per size. Both runs are "
                 "asserted to reach the same maximum flow." % TRIALS),
        "rows": rows,
    }
    path = os.path.join(HERE, "scaling.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("\nwrote", path)


if __name__ == "__main__":
    main()
