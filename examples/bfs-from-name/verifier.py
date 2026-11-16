"""BFS (depths and parents) verifier.

solve: Floyd-Warshall over unit edges gives each reachable vertex's distance
from the nearest source -- a different algorithm from the cascade.

The parent is a free choice (any neighbour one level up), so parents are not
compared with a fixed answer. `certify` checks that the cascade's Parent is a
valid BFS tree for its own Depth: every reached non-source vertex has exactly
one parent, along a real edge, exactly one level up; sources and unreached
vertices have none."""

ANSWER_LABEL = "depths"
KIND = "different-algorithm"
METHOD = "Floyd-Warshall"

INF = float("inf")


def solve(instance):
    n = instance["extent"]["S"]
    edges = [tuple(int(x) for x in k.split(","))
             for k in instance["tensors"]["G"]]
    dist = [[0 if u == v else INF for v in range(n)] for u in range(n)]
    for u, v in edges:
        if u != v:
            dist[u][v] = 1
    for k in range(n):
        for u in range(n):
            for v in range(n):
                dist[u][v] = min(dist[u][v], dist[u][k] + dist[k][v])
    sources = [int(s) for s in instance["coordSets"]["source"]]
    out = {}
    for v in range(n):
        best = min(dist[s][v] for s in sources)
        if best != INF:
            out[v] = best
    return out


def answer(final, instance):
    """The cascade's Depth tensor."""
    return {int(k): v for k, v in final.get("Depth", {}).items()}


def certify(final, instance):
    depth = {int(k): v for k, v in final.get("Depth", {}).items()}
    edges = set(instance["tensors"]["G"])
    sources = {int(s) for s in instance["coordSets"]["source"]}
    parents = {}
    wrong = []
    for key in final.get("Parent", {}):
        s, d = (int(x) for x in key.split(","))
        parents.setdefault(d, []).append(s)
    for d, ps in sorted(parents.items()):
        if len(ps) != 1:
            wrong.append(f"vertex {d} has {len(ps)} parents: {sorted(ps)}")
            continue
        s = ps[0]
        if f"{s},{d}" not in edges:
            wrong.append(f"parent edge {s}->{d} is not in the graph")
        if d in sources or d not in depth:
            wrong.append(f"vertex {d} has a parent but is a source or "
                         f"unreached")
        elif depth.get(s) is None or depth[s] + 1 != depth[d]:
            wrong.append(f"parent {s} of {d} is not one level up "
                         f"({depth.get(s)} vs {depth[d]})")
    for d in depth:
        if d not in sources and d not in parents:
            wrong.append(f"reached vertex {d} has no parent")
    return wrong


def random_instance(rng):
    """Undirected graphs (edges stored both ways), several equal-depth
    parents common; sometimes an unreachable vertex or a second source."""
    n = rng.randint(4, 8)
    g = {}
    for u in range(n - 1):
        for v in rng.sample(range(u + 1, n), rng.randint(1, min(2, n - 1 - u))):
            g[f"{u},{v}"] = g[f"{v},{u}"] = 1
    if rng.random() < 0.3:
        g = {k: w for k, w in g.items()
             if str(n - 1) not in k.split(",")}
    sources = ["0"] + ([str(rng.randrange(1, n))] if rng.random() < 0.3 else [])
    return {
        "extent": {"S": n, "D": n},
        "tensors": {"G": g},
        "coordSets": {"source": sources},
    }
