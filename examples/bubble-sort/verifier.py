"""Bubble sort verifier: Python's built-in sort, a trusted library routine."""

ANSWER_LABEL = "sorted array"
KIND = "library"
METHOD = "sorted"


def solve(instance):
    """The array in non-decreasing order."""
    n = instance["extent"]["N"]
    a = instance["tensors"]["A"]
    return sorted(a[str(k)] for k in range(n))


def answer(final, instance):
    """The final row of the last pass the cascade ran: Z_{i, J-1, n}."""
    n = instance["extent"]["N"]
    z = final.get("Z", {})
    return [z.get(f"{n - 2},{k}") for k in range(n)]


def random_instance(rng):
    """Values from -5 to 20, so 0 and negatives occur; duplicates allowed.
    (The empty value is +inf, so 0 is an ordinary value.)"""
    n = rng.randint(2, 7)
    values = [rng.randint(-5, 20) for _ in range(n)]
    if rng.random() < 0.5:
        values[rng.randrange(n)] = 0
    return {
        "extent": {"N": n, "M": n, "I": n - 1, "J": n - 1},
        "tensors": {"A": {str(k): v for k, v in enumerate(values)}},
    }
