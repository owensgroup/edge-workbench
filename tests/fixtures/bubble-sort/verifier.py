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
    """Positive values (0 is the empty value), duplicates allowed."""
    n = rng.randint(2, 7)
    values = [rng.randint(1, 20) for _ in range(n)]
    return {
        "extent": {"N": n, "M": n, "I": n - 1, "J": n - 1},
        "tensors": {"A": {str(k): v for k, v in enumerate(values)}},
    }
