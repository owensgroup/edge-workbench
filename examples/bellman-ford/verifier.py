"""Bellman-Ford verifier: Floyd-Warshall, a different algorithm for the same
problem (it also allows negative edges, as long as there is no negative cycle)."""

ANSWER_LABEL = "distances"
KIND = "different-algorithm"
METHOD = "Floyd-Warshall"

INF = float("inf")


def _problem(instance):
    n = instance["extent"]["S"]
    weight = {tuple(int(x) for x in k.split(",")): w
              for k, w in instance["tensors"]["G"].items()}
    sources = [int(k) for k in instance["coordSets"]["root_id"]]
    return n, weight, sources


def solve(instance):
    """Shortest distance from a source, for every reachable vertex."""
    n, weight, sources = _problem(instance)
    dist = [[0 if u == v else weight.get((u, v), INF) for v in range(n)]
            for u in range(n)]
    for k in range(n):
        for u in range(n):
            for v in range(n):
                if dist[u][k] + dist[k][v] < dist[u][v]:
                    dist[u][v] = dist[u][k] + dist[k][v]
    best = {v: min(dist[s][v] for s in sources) for v in range(n)}
    return {v: d for v, d in best.items() if d != INF}


def answer(final, instance):
    """The cascade's final distances; unreached vertices stay empty (inf)."""
    return {int(k): v for k, v in final.get("D", {}).items() if v != INF}


def random_instance(rng):
    """Forward edges may be negative; back edges are heavy enough that no
    cycle is negative, which the cascade assumes. Weight-0 edges are
    included: G is declared `empty = inf`, so a weight-0 edge is a real
    entry."""
    n = rng.randint(4, 8)
    g = {}
    for u in range(n - 1):
        for v in rng.sample(range(u + 1, n), rng.randint(1, min(2, n - 1 - u))):
            g[f"{u},{v}"] = rng.randint(-5, 20)
    for _ in range(rng.randint(0, 2)):
        v = rng.randrange(0, n - 1)
        u = rng.randrange(v + 1, n)
        g[f"{u},{v}"] = rng.randint(5 * n + 1, 6 * n)
    return {
        "extent": {"S": n, "D": n},
        "tensors": {"G": g},
        "coordSets": {"root_id": ["0"]},
    }
