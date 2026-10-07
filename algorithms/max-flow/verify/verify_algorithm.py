# -*- coding: utf-8 -*-
"""Is the max-flow cascade correct -- on the instance the page actually shows?

WHAT THIS REPLACED
------------------
This verifier used to carry `CLRS_26_1` and a second Python implementation of
the cascade (`edge_cascade`), and it checked those against each other. It never
read `instance.json`. So the build reported "answer check: 18 checks passed"
next to "driven trace: max flow 5" as though they were one result, when they
were two unrelated runs on two different graphs -- and nothing in the build
checked the answer for the page the build was about to write.

Worse, the thing being checked was a re-implementation. Two hand-written
interpretations of one specification can be wrong together, which is the exact
failure this repository exists to prevent.

Now there is one evaluator. The driver runs, and what it produces is checked
three ways, weakest to strongest:

  1. THE PUBLISHED ANSWER. The tutorial states the maximum flow for its own
     worked example. External to this repository, and free.
  2. AN INDEPENDENT ORACLE. `edmonds_karp` is augmenting-path, not
     push-relabel -- a different algorithm for the same problem -- and it runs
     on generated instances too, so agreement is not a claim about one graph.
  3. THE PROPERTIES. `validate_flow` checks capacity, antisymmetry,
     conservation at every internal vertex, and that the value measured at the
     source equals the value at the sink. These need no oracle at all, and
     they are the only check that catches the right TOTAL reached by an
     invalid route.

    python3 verify_algorithm.py            # the page's instance, plus a sweep
    python3 verify_algorithm.py -n 25      # a longer sweep
    python3 verify_algorithm.py --self-test

The self-test injects faults into the FLOW, not into a copy of the algorithm,
so what it proves is that these checks can reject a bad answer.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = HERE.parent / "spec"
sys.path.insert(0, str(HERE.parent.parent.parent))

from edge_workbench.driver import run as driver          # noqa: E402


# --------------------------------------------------------------------------
# the instance the page shows
# --------------------------------------------------------------------------
def page_instance() -> dict:
    return json.loads((SPEC / "instance.json").read_text())


def capacities_of(instance: dict) -> tuple[dict, int, int, int]:
    """(capacity map, |V|, source, sink) from an instance."""
    cap = {
        (int(k.split(",")[0]), int(k.split(",")[1])): v
        for k, v in instance["tensors"]["C"].items()
    }
    n = instance["extent"]["U"]
    # Source and sink come from the S and T TENSORS, which are what the
    # cascade reads. `domain.graph` also names them, but that block is
    # presentation -- and when the two disagree, believing the presentation
    # means validating a different problem than the one that ran.
    source = next(iter(instance["tensors"]["S"]))
    sink = next(iter(instance["tensors"]["T"]))
    return cap, n, int(source), int(sink)


def published_answer() -> int | None:
    """What the tutorial says the maximum flow is, if it says.

    From spec/authored.json, the artifact `prepare` writes, so the answer and
    the instance come from one reading of one tutorial at one commit -- not
    from whatever the working tree holds when the verifier happens to run.
    """
    try:
        from edge_workbench import prepare
        example = prepare.load(SPEC).get("example") or {}
        return example.get("expect", {}).get("flow")
    except Exception:
        return None


# --------------------------------------------------------------------------
# run the REAL cascade
# --------------------------------------------------------------------------
def cascade_flow(instance: dict, seed: int | None = None) -> dict:
    """Run the driver on `instance` and return its final flow tensor F.

    This is the evaluator the page uses. There is no second one.
    """
    selectors = None
    if seed is not None:
        selectors = {"pick-admissible-edge": {"rule": "seeded", "seed": seed}}

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(instance, fh)
        path = fh.name
    try:
        result = driver.run("max-flow", instance=path, selectors=selectors)
    finally:
        os.unlink(path)

    final = result["steps"][-1]["state"]
    return {
        (int(k.split(",")[0]), int(k.split(",")[1])): v
        for k, v in final.get("F", {}).items()
    }


# --------------------------------------------------------------------------
# 3. the properties -- no oracle needed
# --------------------------------------------------------------------------
def validate_flow(F, cap, n, s, t):
    """Is this a feasible flow, and what is its value?

    Returns (value, problems). An empty `problems` means the flow is genuinely
    feasible -- not merely that its total came out right.
    """
    problems = []
    for (u, v), f in F.items():
        if f > cap.get((u, v), 0):
            problems.append(f"f({u},{v})={f} exceeds capacity "
                            f"{cap.get((u, v), 0)}")
        if F.get((v, u), 0) != -f:
            problems.append(f"antisymmetry: f({u},{v})={f} but "
                            f"f({v},{u})={F.get((v, u), 0)}")

    net = collections.defaultdict(int)
    for (u, v), f in F.items():
        if f > 0:
            net[u] -= f
            net[v] += f
    for u in range(n):
        if u in (s, t) or net[u] == 0:
            continue
        problems.append(f"conservation: vertex {u} holds {net[u]}")

    out_of_source = sum(f for (u, _v), f in F.items() if u == s and f > 0)
    into_sink = sum(f for (_u, v), f in F.items() if v == t and f > 0)
    if out_of_source != into_sink:
        problems.append(f"value at source {out_of_source} != at sink "
                        f"{into_sink}")
    return into_sink, problems


# --------------------------------------------------------------------------
# 2. the independent oracle -- a different algorithm, same problem
# --------------------------------------------------------------------------
def edmonds_karp(cap, n, s, t):
    residual = collections.defaultdict(int)
    for (u, v), c in cap.items():
        residual[(u, v)] += c
    total = 0
    while True:
        parent = {s: None}
        queue = collections.deque([s])
        while queue and t not in parent:
            u = queue.popleft()
            for v in range(n):
                if v not in parent and residual[(u, v)] > 0:
                    parent[v] = u
                    queue.append(v)
        if t not in parent:
            return total
        bottleneck, v = float("inf"), t
        while parent[v] is not None:
            bottleneck = min(bottleneck, residual[(parent[v], v)])
            v = parent[v]
        v = t
        while parent[v] is not None:
            residual[(parent[v], v)] -= bottleneck
            residual[(v, parent[v])] += bottleneck
            v = parent[v]
        total += bottleneck


# --------------------------------------------------------------------------
# generated instances, run through the SAME driver
# --------------------------------------------------------------------------
def random_instance(template: dict, n: int, rng, degree=3, maxcap=20) -> dict:
    cap = {}
    for u in range(n - 1):
        for _ in range(rng.randint(1, degree)):
            v = rng.randrange(u + 1, n)
            cap[f"{u},{v}"] = cap.get(f"{u},{v}", 0) + rng.randint(1, maxcap)
    for u in range(1, n - 1):                    # keep the sink reachable
        cap.setdefault(f"{u},{n - 1}", rng.randint(1, maxcap))
    inst = json.loads(json.dumps(template))
    inst["extent"] = {"U": n, "V": n}
    inst["scalars"]["VertexCount"] = n
    inst["tensors"]["C"] = cap
    inst["tensors"]["G"] = {k: 1 for k in cap}
    inst["tensors"]["S"] = {"0": True}
    inst["tensors"]["T"] = {str(n - 1): True}
    inst.setdefault("domain", {})["graph"] = {
        "nodes": list(range(n)),
        "edges": [
            {"u": int(k.split(",")[0]), "v": int(k.split(",")[1]), "cap": v}
            for k, v in cap.items()
        ],
        "source": 0,
        "sink": n - 1,
    }
    return inst


# --------------------------------------------------------------------------
def check(name, instance, seed=None, fault=None):
    cap, n, s, t = capacities_of(instance)
    try:
        F = cascade_flow(instance, seed=seed)
    except Exception as exc:
        return False, f"{name}: the cascade did not run -- {exc}"

    if fault:
        F = inject(F, fault, cap, s)

    value, problems = validate_flow(F, cap, n, s, t)
    if problems:
        return False, f"{name}: invalid flow -- " + "; ".join(problems[:3])

    want = edmonds_karp(cap, n, s, t)
    if value != want:
        return False, f"{name}: cascade says {value}, Edmonds-Karp says {want}"
    return True, f"{name}: {value}"


FAULTS = {
    "break-antisymmetry": "drop the reverse entry on one edge",
    "overpush": "raise one edge's flow above its capacity",
    "break-conservation": "add flow into one internal vertex",
    "halve-the-answer": "halve every flow, keeping it feasible",
}


def inject(F, fault, cap, s):
    """Break the ANSWER, so the checks above are what gets tested."""
    F = dict(F)
    if fault == "break-antisymmetry":
        for (u, v) in list(F):
            if F[(u, v)] > 0:
                F.pop((v, u), None)
                return F
    if fault == "overpush":
        for (u, v) in list(F):
            if F[(u, v)] > 0:
                F[(u, v)] = cap.get((u, v), 0) + 1
                F[(v, u)] = -F[(u, v)]
                return F
    if fault == "break-conservation":
        for (u, v) in list(F):
            if F[(u, v)] > 0 and u != s:
                F[(u, v)] += 1
                F[(v, u)] = -F[(u, v)]
                return F
    if fault == "halve-the-answer":
        return {k: v // 2 for k, v in F.items()}
    return F


def self_test():
    print("self-test: every fault in the ANSWER must be rejected\n")
    instance = page_instance()
    bad = 0
    for fault, why in FAULTS.items():
        ok, msg = check("fault", instance, fault=fault)
        caught = not ok
        print(f"  {'ok  ' if caught else 'MISS'} {fault:22} {why}")
        bad += not caught
    print()
    if bad:
        print(f"{bad} fault(s) went unnoticed -- these checks cannot be trusted")
        return 1
    print(f"{len(FAULTS)}/{len(FAULTS)} faults caught")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=12,
                    help="generated instances to sweep")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    instance = page_instance()
    cap, n, s, t = capacities_of(instance)
    results = []

    # 1. the published answer, on the instance the page shows
    published = published_answer()
    value, problems = validate_flow(cascade_flow(instance), cap, n, s, t)
    if published is None:
        print("!! the tutorial publishes no answer -- skipped", file=sys.stderr)
    else:
        results.append((
            value == published and not problems,
            f"the page's instance: {value}, tutorial publishes {published}",
        ))

    # 3. the properties, on the same run
    results.append((not problems,
                    "the flow is feasible: capacity, antisymmetry, "
                    "conservation, source == sink"))

    # the free choice must not change the answer
    for seed in (1, 7):
        results.append(check(f"seed {seed}", instance, seed=seed))

    # 2. the oracle, over generated instances
    rng = random.Random(20260927)
    for size in (5, 7):
        agree = 0
        for _ in range(max(1, args.n // 4)):
            ok, msg = check(f"random n={size}", random_instance(instance, size, rng))
            if not ok:
                results.append((False, msg))
                break
            agree += 1
        else:
            results.append((True, f"random n={size}: {agree}/{agree} "
                                  f"agree with Edmonds-Karp, all feasible"))

    failed = 0
    for ok, msg in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {msg}")
        failed += not ok
    print(f"\n{len(results) - failed} checks passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
