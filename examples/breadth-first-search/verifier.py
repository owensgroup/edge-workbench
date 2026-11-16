"""BFS verifier: Floyd-Warshall over unit edges, a different algorithm that
gives each vertex's distance from the nearest source.

The tutorial's answer is "the union of the frontiers over all generations":
each vertex's depth is the value F gave it in the generation it entered the
frontier. F is overwritten every generation, so `answer` reads every step,
not just the final state."""

ANSWER_LABEL = "depths"
KIND = "different-algorithm"
METHOD = "Floyd-Warshall"

INF = float("inf")


def solve(instance):
    """Hops from the nearest source, for every reachable vertex."""
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
    sources = [int(s) for s in instance["coordSets"]["id"]]
    depths = {}
    for v in range(n):
        best = min(dist[s][v] for s in sources)
        if best != INF:
            depths[v] = best
    return depths


def answer(final, instance, steps):
    """Each vertex's depth: the smallest value F ever held for it."""
    depths = {}
    for step in steps:
        for key, value in step["state"].get("F", {}).items():
            v = int(key)
            if v not in depths or value < depths[v]:
                depths[v] = value
    return depths


def random_instance(rng):
    """Directed graphs with back edges, so a cycle reaches visited vertices;
    sometimes an unreachable vertex, and sometimes two sources."""
    n = rng.randint(4, 8)
    g = {}
    for u in range(n - 1):
        for v in rng.sample(range(u + 1, n), rng.randint(1, min(2, n - 1 - u))):
            g[f"{u},{v}"] = 1
    for _ in range(rng.randint(1, 3)):
        v = rng.randrange(0, n - 1)
        u = rng.randrange(v + 1, n)
        g[f"{u},{v}"] = 1
    if rng.random() < 0.3:
        # Cut every edge into the last vertex: it is unreachable.
        g = {k: w for k, w in g.items() if not k.endswith(f",{n - 1}")}
    sources = ["0"] + ([str(rng.randrange(1, n))] if rng.random() < 0.3 else [])
    return {
        "extent": {"S": n, "D": n},
        "tensors": {"G": g},
        "coordSets": {"id": sources},
    }
