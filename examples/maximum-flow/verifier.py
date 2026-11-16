"""Max-flow verifier: Edmonds-Karp, a different algorithm for the same problem."""

import collections

ANSWER_LABEL = "max flow"
KIND = "different-algorithm"
METHOD = "Edmonds-Karp"


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


def certify(final, instance):
    """The cascade's own flow is a maximum flow, checked without solving.

    `answer` compares only the total leaving the source, so a flow that broke
    a capacity or conserved nothing could still match. This checks the whole
    final F (antisymmetric: F[u,v] = -F[v,u]):

      capacity      F[u,v] <= C[u,v] on every pair
      conservation  net flow into every vertex but s and t is 0
      optimality    t is unreachable from s in the residual graph, and the
                    cut that reachability defines has capacity equal to the
                    flow (max-flow min-cut), so no larger flow exists
    """
    cap, n, s, t = _problem(instance)
    flow = {tuple(int(x) for x in k.split(",")): v
            for k, v in final.get("F", {}).items()}
    f = lambda u, v: flow.get((u, v), 0)          # noqa: E731
    c = lambda u, v: cap.get((u, v), 0)           # noqa: E731
    wrong = []
    for u in range(n):
        for v in range(n):
            if f(u, v) != -f(v, u):
                wrong.append(f"F[{u},{v}] = {f(u, v)} but F[{v},{u}] = "
                             f"{f(v, u)}; flow must be antisymmetric")
            if f(u, v) > c(u, v):
                wrong.append(f"F[{u},{v}] = {f(u, v)} exceeds its capacity "
                             f"{c(u, v)}")
    for v in range(n):
        if v not in (s, t):
            net = sum(f(u, v) for u in range(n))
            if net != 0:
                wrong.append(f"vertex {v} keeps {net} units: flow is not "
                             f"conserved")
    reach, stack = {s}, [s]
    while stack:
        u = stack.pop()
        for v in range(n):
            if v not in reach and c(u, v) - f(u, v) > 0:
                reach.add(v)
                stack.append(v)
    if t in reach:
        wrong.append("the sink is still reachable in the residual graph, so "
                     "the flow is not maximum")
    value = sum(f(s, v) for v in range(n))
    cut = sum(c(u, v) for u in reach for v in range(n) if v not in reach)
    if t not in reach and cut != value:
        wrong.append(f"the residual cut has capacity {cut} but the flow is "
                     f"{value}")
    return wrong


def random_instance(rng):
    n = rng.randint(4, 8)
    cap = {}
    for u in range(n - 1):
        for _ in range(rng.randint(1, 3)):
            v = rng.randrange(u + 1, n)
            cap[f"{u},{v}"] = cap.get(f"{u},{v}", 0) + rng.randint(1, 20)
    if rng.random() < 0.25:
        # Now and then cut the sink off entirely: the maximum flow is 0, a
        # case nothing else here would generate.
        cap = {k: c for k, c in cap.items() if not k.endswith(f",{n - 1}")}
    else:
        for u in range(1, n - 1):             # keep the sink reachable
            cap.setdefault(f"{u},{n - 1}", rng.randint(1, 20))
    return {
        "extent": {"U": n, "V": n},
        "scalars": {"VertexCount": n},
        "tensors": {"C": cap, "S": {"0": True}, "T": {str(n - 1): True}},
    }
