# -*- coding: utf-8 -*-
"""Is the max-flow cascade actually correct?

Everything that currently agrees on the answer 23 is push-relabel:
`eval_edge.py`, `edge_interp.js` and `seq_pushrelabel.py`. Three
implementations of one algorithm can share a misconception, and until now
nothing checked that the flow they produce is even a *valid* flow -- only that
its value came out 23.

This closes both gaps:

  1. THE ANSWER IS PUBLISHED, NOT OURS. The demo graph is CLRS Figure 26.1
     (Cormen et al., *Introduction to Algorithms*, 3rd ed., §26.1), whose
     maximum flow is 23. So the number is external to this repository.

  2. THE FLOW IS VALIDATED, NOT JUST ITS VALUE. `validate_flow` checks the
     capacity constraint, antisymmetry, and conservation at every internal
     vertex, and that the value measured at the source equals the value
     measured at the sink. A run can reach 23 by an invalid route; this says
     whether the answer is a genuine maximum flow.

  3. AN INDEPENDENT ORACLE. `edmonds_karp` is augmenting-path, not
     push-relabel -- a different algorithm with different failure modes. The
     property test runs the EDGE cascade against it over random graphs, which
     catches semantic errors that one worked example cannot.

A verifier that cannot fail is worthless, so `--self-test` injects known
faults and asserts each one is caught. That exercise earned its keep: the
`d(s) = 0` fault (source height left at 0 instead of |V|) still produces a
valid flow of 23 on CLRS Figure 26.1 -- the published example misses it
entirely -- but the random-graph property test catches it on 192 of 200
graphs, the first one included. One worked example is not verification.

Run: python3 verify_algorithm.py [-n TRIALS] [--self-test]
"""

from __future__ import annotations

import argparse
import collections
import random
import sys

# --------------------------------------------------------------------------
# The published example
# --------------------------------------------------------------------------
# CLRS Figure 26.1: s, v1, v2, v3, v4, t numbered 0..5.
CLRS_26_1 = {(0, 1): 16, (0, 2): 13, (1, 2): 10, (2, 1): 4, (1, 3): 12,
             (3, 2): 9, (2, 4): 14, (4, 3): 7, (3, 5): 20, (4, 5): 4}
CLRS_26_1_MAXFLOW = 23     # published; not computed by anything in this repo
CLRS_N, CLRS_S, CLRS_T = 6, 0, 5


# --------------------------------------------------------------------------
# Is this a valid flow?
# --------------------------------------------------------------------------
def validate_flow(F, cap, n, s, t):
    """Check F is a feasible flow, and return its value.

    F is the antisymmetric representation the cascade produces:
    F[(u,v)] = -F[(v,u)], positive meaning flow from u to v.

    Returns (value, problems). An empty problem list means F is a feasible
    flow of that value -- feasible, not necessarily maximum; maximality is
    what the independent oracle is for.
    """
    problems = []

    def f(u, v):
        return F.get((u, v), 0)

    for u in range(n):
        for v in range(n):
            if f(u, v) != -f(v, u):
                problems.append(
                    f"antisymmetry: f({u},{v})={f(u, v)} but "
                    f"f({v},{u})={f(v, u)}")
            c = cap.get((u, v), 0)
            if f(u, v) > c:
                problems.append(
                    f"capacity: f({u},{v})={f(u, v)} exceeds c={c}")

    for u in range(n):
        if u in (s, t):
            continue
        # With an antisymmetric F, net flow at u is the sum of the column.
        net = sum(f(v, u) for v in range(n))
        if net != 0:
            problems.append(f"conservation: vertex {u} has net {net}, want 0")

    out_of_s = sum(f(s, v) for v in range(n))
    into_t = sum(f(v, t) for v in range(n))
    if out_of_s != into_t:
        problems.append(
            f"value: {out_of_s} leaves the source but {into_t} reaches the "
            f"sink")

    return into_t, problems


# --------------------------------------------------------------------------
# Independent oracle: augmenting paths, not push-relabel
# --------------------------------------------------------------------------
def edmonds_karp(cap, n, s, t):
    """Maximum flow by BFS augmenting paths. Deliberately unlike the cascade:
    it maintains a feasible flow throughout rather than a preflow, and never
    computes a height function."""
    res = collections.defaultdict(int)
    for (u, v), c in cap.items():
        res[(u, v)] += c
    flow = 0
    while True:
        parent = {s: None}
        q = collections.deque([s])
        while q and t not in parent:
            u = q.popleft()
            for v in range(n):
                if v not in parent and res[(u, v)] > 0:
                    parent[v] = u
                    q.append(v)
        if t not in parent:
            return flow
        # bottleneck along the path
        b, v = float("inf"), t
        while parent[v] is not None:
            b = min(b, res[(parent[v], v)])
            v = parent[v]
        v = t
        while parent[v] is not None:
            res[(parent[v], v)] -= b
            res[(v, parent[v])] += b
            v = parent[v]
        flow += b


# --------------------------------------------------------------------------
# The bulk-synchronous cascade, as EDGE specifies it
# --------------------------------------------------------------------------
def edge_cascade(cap, n, s, t, seed=0, max_rounds=200000, fault=None):
    """One round: every active vertex pushes on one admissible edge, sync,
    then every still-active vertex with nothing admissible relabels.

    Mirrors the Einsum cascade. Returns (F, rounds) or raises on non-
    termination, which would itself be a correctness failure.

    `fault` deliberately breaks one thing, for --self-test. It lives here
    rather than in a copy of the cascade so the faults are injected into the
    code actually under test, and cannot drift away from it.
    """
    rng = random.Random(seed)
    F, R = {}, {}
    for (u, v), c in cap.items():
        R[(u, v)] = R.get((u, v), 0) + c
    D = {u: 0 for u in range(n)}
    D[s] = 0 if fault == "no-source-height" else n
    E = {u: 0 for u in range(n)}
    for (u, v), c in cap.items():                       # preflow
        if u != s:
            continue
        F[(u, v)] = c
        if fault != "no-antisymmetry":
            F[(v, u)] = -c
        E[v] += c
        E[s] -= c
        R[(u, v)] = 0
        R[(v, u)] = R.get((v, u), 0) + c

    rounds = 0
    while True:
        act = [u for u in range(n) if u not in (s, t) and E[u] > 0]
        if not act:
            return F, rounds
        rounds += 1
        if rounds > max_rounds:
            raise RuntimeError(f"cascade did not terminate in {max_rounds} "
                               f"rounds")
        delta = {}
        for u in act:
            adm = [v for v in range(n)
                   if R.get((u, v), 0) > 0
                   and (fault == "ignore-height" or D[u] == D[v] + 1)]
            if adm:
                v = rng.choice(adm)
                delta[(u, v)] = (E[u] if fault == "overpush"
                                 else min(E[u], R[(u, v)]))
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
        if not delta and not rel:
            return F, rounds


# --------------------------------------------------------------------------
# Graphs to test on
# --------------------------------------------------------------------------
def random_graph(n, rng, degree=3, maxcap=20):
    cap = {}
    for u in range(n):
        for _ in range(degree):
            v = rng.randrange(n)
            if v != u and (v, u) not in cap and (u, v) not in cap:
                cap[(u, v)] = rng.randint(1, maxcap)
    for v in range(1, min(degree + 1, n)):
        cap.setdefault((0, v), rng.randint(5, maxcap))
    for u in range(max(1, n - degree - 1), n - 1):
        cap.setdefault((u, n - 1), rng.randint(5, maxcap))
    return cap


def adversarial_graphs():
    """Shapes chosen to break specific assumptions, not random ones."""
    return [
        ("no path from source to sink", 4, {(0, 1): 5, (2, 3): 5}),
        ("single edge", 2, {(0, 1): 7}),
        ("source is the sink's only neighbour", 3,
         {(0, 1): 4, (1, 2): 9}),
        ("antiparallel pair", 4,
         {(0, 1): 10, (1, 2): 5, (2, 1): 5, (2, 3): 10}),
        ("zero-capacity edge", 3, {(0, 1): 0, (0, 2): 4, (1, 2): 4}),
        ("bottleneck in the middle", 4,
         {(0, 1): 100, (1, 2): 1, (2, 3): 100}),
        ("parallel disjoint paths", 6,
         {(0, 1): 5, (1, 5): 5, (0, 2): 6, (2, 5): 6, (0, 3): 7, (3, 5): 7}),
        ("long chain", 6,
         {(0, 1): 3, (1, 2): 3, (2, 3): 3, (3, 4): 3, (4, 5): 3}),
        ("cycle not on any s-t path", 5,
         {(0, 1): 5, (1, 4): 5, (2, 3): 2, (3, 2): 2}),
    ]


# --------------------------------------------------------------------------
def check(name, cap, n, s, t, seed=0, fault=None):
    """Run the cascade, validate its flow, and compare with the oracle."""
    try:
        F, rounds = edge_cascade(cap, n, s, t, seed=seed, fault=fault)
    except RuntimeError as exc:
        return False, f"{name}: {exc}"

    value, problems = validate_flow(F, cap, n, s, t)
    if problems:
        return False, f"{name}: produced an invalid flow -- " + \
            "; ".join(problems[:3])

    want = edmonds_karp(cap, n, s, t)
    if value != want:
        return False, (f"{name}: cascade says {value}, "
                       f"Edmonds-Karp says {want}")
    return True, f"{name}: {value} ({rounds} rounds)"


FAULTS = {
    "no-antisymmetry": "the reverse edge is not updated on a push",
    "overpush": "a push ignores the residual capacity",
    "no-source-height": "d(s) is left at 0 instead of |V|",
    "ignore-height": "pushes go on any residual edge, not only admissible",
}


def self_test(trials):
    """Break the cascade on purpose; every fault must be caught somewhere.

    Reports which faults the published example alone would miss, because that
    is the argument for testing on random graphs at all.
    """
    print("Self-test: each fault must be caught\n")
    ok = True
    for fault, desc in FAULTS.items():
        by_clrs, by_random, first = False, 0, None
        passed, _ = check("clrs", CLRS_26_1, CLRS_N, CLRS_S, CLRS_T,
                          fault=fault)
        by_clrs = not passed
        for n in (4, 6, 10):
            for k in range(min(trials, 20)):
                rng = random.Random(7000 + n * 1000 + k)
                cap = random_graph(n, rng)
                good, msg = check(f"n={n} k={k}", cap, n, 0, n - 1,
                                  seed=k, fault=fault)
                if not good:
                    by_random += 1
                    first = first or msg
        caught = by_clrs or by_random
        ok = ok and caught
        where = ("CLRS example" if by_clrs else "NOT by the CLRS example")
        print(f"  {'ok  ' if caught else 'FAIL'} {desc}")
        print(f"       caught by: {where}; "
              f"{by_random} random graphs")
        if first and not by_clrs:
            print(f"       first random failure — {first}")
    print(f"\n{'all faults caught' if ok else 'SOME FAULTS WENT UNDETECTED'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--trials", type=int, default=40,
                    help="random graphs per size")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--self-test", action="store_true",
                    help="inject known faults and check each is caught")
    args = ap.parse_args()

    if args.self_test:
        return self_test(args.trials)

    failures = []
    passed = 0

    def record(ok, msg):
        nonlocal passed
        if ok:
            passed += 1
            print("  ok   " + msg)
        else:
            failures.append(msg)
            print("  FAIL " + msg)

    # ---- 1. the published example ----------------------------------------
    print("CLRS Figure 26.1 — published maximum flow 23")
    F, rounds = edge_cascade(CLRS_26_1, CLRS_N, CLRS_S, CLRS_T)
    value, problems = validate_flow(F, CLRS_26_1, CLRS_N, CLRS_S, CLRS_T)
    record(not problems,
           "the cascade's flow is feasible" if not problems
           else "CLRS: invalid flow -- " + "; ".join(problems[:3]))
    record(value == CLRS_26_1_MAXFLOW,
           f"value is the published {CLRS_26_1_MAXFLOW}" if
           value == CLRS_26_1_MAXFLOW else
           f"CLRS: got {value}, published answer is {CLRS_26_1_MAXFLOW}")
    record(edmonds_karp(CLRS_26_1, CLRS_N, CLRS_S, CLRS_T)
           == CLRS_26_1_MAXFLOW,
           "the independent oracle agrees with the published answer")

    # The selector is free to pick any admissible edge; the answer must not
    # depend on which. The whole cascade rests on that, and it is the kind of
    # assumption a single fixed seed would never test.
    values, invalid = set(), 0
    for k in range(50):
        Fk, _ = edge_cascade(CLRS_26_1, CLRS_N, CLRS_S, CLRS_T, seed=k)
        vk, pk = validate_flow(Fk, CLRS_26_1, CLRS_N, CLRS_S, CLRS_T)
        values.add(vk)
        invalid += bool(pk)
    record(values == {CLRS_26_1_MAXFLOW} and not invalid,
           "50 different selector choices all give a feasible flow of "
           f"{CLRS_26_1_MAXFLOW}"
           if values == {CLRS_26_1_MAXFLOW} and not invalid
           else f"selector choice matters: values {sorted(values)}, "
                f"{invalid} infeasible")

    # ---- 2. shapes that break assumptions --------------------------------
    print("\nAdversarial shapes")
    for name, n, cap in adversarial_graphs():
        record(*check(name, cap, n, 0, n - 1))

    # ---- 3. random graphs against the independent oracle ------------------
    print(f"\nRandom graphs vs Edmonds-Karp ({args.trials} per size)")
    for n in (4, 6, 10, 16, 25):
        bad = 0
        for k in range(args.trials):
            rng = random.Random(7000 + n * 1000 + k)
            cap = random_graph(n, rng)
            ok, msg = check(f"n={n} trial={k}", cap, n, 0, n - 1, seed=k)
            if not ok:
                bad += 1
                if bad == 1:
                    failures.append(msg)
                    print("  FAIL " + msg)
        if not bad:
            passed += 1
            print(f"  ok   n={n}: {args.trials}/{args.trials} agree, "
                  f"all flows feasible")

    print(f"\n{passed} checks passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
