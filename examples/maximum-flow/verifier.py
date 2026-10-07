"""Max-flow verifier: Edmonds-Karp, a different algorithm for the same problem."""

import collections

ANSWER_LABEL = "max flow"


def _problem(instance):
    cap = {tuple(int(x) for x in k.split(",")): v
           for k, v in instance["tensors"]["C"].items()}
    n = instance["extent"]["U"]
    s = int(next(iter(instance["tensors"]["S"])))
    t = int(next(iter(instance["tensors"]["T"])))
    return cap, n, s, t


def solve(instance):
    cap, n, s, t = _problem(instance)
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


def answer(final, instance):
    """Flow leaving the source, read off the cascade's final F."""
    _, _, s, _ = _problem(instance)
    return sum(v for k, v in final.get("F", {}).items()
               if int(k.split(",")[0]) == s)


def random_instance(rng):
    n = rng.randint(4, 8)
    cap = {}
    for u in range(n - 1):
        for _ in range(rng.randint(1, 3)):
            v = rng.randrange(u + 1, n)
            cap[f"{u},{v}"] = cap.get(f"{u},{v}", 0) + rng.randint(1, 20)
    for u in range(1, n - 1):                 # keep the sink reachable
        cap.setdefault(f"{u},{n - 1}", rng.randint(1, 20))
    return {
        "extent": {"U": n, "V": n},
        "scalars": {"VertexCount": n},
        "tensors": {"C": cap, "S": {"0": True}, "T": {str(n - 1): True}},
    }
