"""Exact-cover verifier: brute-force subset enumeration, not Algorithm X."""
from itertools import combinations

ANSWER_LABEL = "solutions"


def _matrix(instance):
    rows, cols = instance["extent"]["R"], instance["extent"]["C"]
    cover = {r: set() for r in range(rows)}
    for k in instance["tensors"]["A"]:
        r, c = (int(x) for x in k.split(","))
        cover[r].add(c)
    return rows, cols, cover


def solve(instance):
    """Every set of rows covering each column exactly once."""
    rows, cols, cover = _matrix(instance)
    found = []
    for n in range(1, rows + 1):
        for pick in combinations(range(rows), n):
            got = [c for r in pick for c in cover[r]]
            if sorted(got) == list(range(cols)):
                found.append(list(pick))
    return sorted(found)


def answer(final, instance, steps):
    """Each success writes Sol; the solutions are every Sol the run wrote."""
    found = {tuple(sorted(int(k) for k in s["state"]["Sol"]))
             for s in steps if s.get("output") == "Sol" and s["state"].get("Sol")}
    return sorted(list(t) for t in found)


def random_instance(rng):
    rows, cols = rng.randint(4, 8), rng.randint(3, 5)
    a = {}
    for r in range(rows):
        for c in rng.sample(range(cols), rng.randint(1, 2)):
            a[f"{r},{c}"] = True
    # The seed: rows covering the column with fewest rows, at depth 1,
    # stamped sigma(1, r) = |R| + r. Ties go to the lowest column.
    counts = [sum(1 for k in a if int(k.split(",")[1]) == c) for c in range(cols)]
    first = min(range(cols), key=lambda c: (counts[c], c))
    init = {str(r): rows + r for r in range(rows) if f"{r},{first}" in a}
    return {
        "extent": {"R": rows, "C": cols},
        "scalars": {"RowCount": rows},
        "tensors": {"A": a, "Col": {str(c): True for c in range(cols)},
                    "Row": {str(r): True for r in range(rows)}, "InitS": init},
    }
