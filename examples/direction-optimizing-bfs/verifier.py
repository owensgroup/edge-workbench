"""DO-BFS verifier: Floyd-Warshall over unit edges, a different algorithm that
gives each vertex's distance from the source.

`pick-parent` is a free choice, so two runs may build different trees. Every
valid BFS tree gives the same depths, so depths are what is compared."""

ANSWER_LABEL = "depths"

INF = float("inf")


def solve(instance):
    """Distance in edges from the source, for every reachable vertex."""
    n = instance["extent"]["S"]
    edges = [tuple(int(x) for x in k.split(",")) for k in instance["tensors"]["G"]]
    dist = [[0 if u == v else INF for v in range(n)] for u in range(n)]
    for u, v in edges:
        if u != v:
            dist[u][v] = 1
    for k in range(n):
        for u in range(n):
            for v in range(n):
                dist[u][v] = min(dist[u][v], dist[u][k] + dist[k][v])
    source = int(instance["coordSets"]["root_id"][0])
    return {v: d for v, d in enumerate(dist[source]) if d != INF}


def answer(final, instance):
    """Depth of each vertex, by following Tree's parent links to the source.

    A vertex with two parents, a tree edge the graph lacks, or a walk that
    never reaches the source is not a BFS tree, so it reports no depths."""
    source = int(instance["coordSets"]["root_id"][0])
    parent = {}
    for key, on in final.get("Tree", {}).items():
        s, d = (int(x) for x in key.split(","))
        if not on:
            continue
        if d in parent:
            return {"not a tree": d}
        parent[d] = s
    edges = set(instance["tensors"]["G"])
    depths = {}
    for v in parent:
        at, steps = v, 0
        while at != source:
            if f"{parent.get(at)},{at}" not in edges or steps > len(parent):
                return {"not a tree": v}
            at, steps = parent[at], steps + 1
        depths[v] = steps
    return depths


def random_instance(rng):
    """Directed graphs with back edges, so a cycle reaches visited vertices,
    and sometimes an unreachable vertex."""
    n = rng.randint(4, 8)
    g = {}
    for u in range(n - 1):
        for v in rng.sample(range(u + 1, n), rng.randint(1, min(2, n - 1 - u))):
            g[f"{u},{v}"] = True
    for _ in range(rng.randint(1, 3)):
        v = rng.randrange(0, n - 1)
        u = rng.randrange(v + 1, n)
        g[f"{u},{v}"] = True
    return {
        "extent": {"S": n, "D": n},
        "tensors": {"G": g},
        "coordSets": {"root_id": ["0"]},
    }
