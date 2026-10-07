# -*- coding: utf-8 -*-
"""Run an author's verifier against the cascade.

THE CONTRACT
------------
An author supplies `verifier.py` beside their tutorial. It must define:

    ANSWER_LABEL = "max flow"

    def solve(instance: dict):
        '''The answer, computed by an algorithm that is NOT this cascade.'''

    def answer(final: dict, instance: dict):
        '''The answer, read off the cascade's final tensors.'''

`answer` may take a third parameter, `steps`: every step of the run, each
with `einsum`, `output` and `state`. That is for answers the final state
cannot show -- exact cover's solutions are found one per success along the
way, and the search ends with the stack empty.

and may define:

    def random_instance(rng: random.Random) -> dict:
        '''A fresh problem, in the same shape as instance.json.'''

`instance` is the same dict the cascade runs on: `extent`, `scalars`, and
`tensors` keyed by coordinate strings (`"0,1": 3`). `final` is the state after
the last step: tensor name -> {coordinate string: value}, with the
generational rank already dropped.

`solve` should be a DIFFERENT algorithm for the same problem where one exists
-- Edmonds-Karp for push-relabel. A second implementation of the same method
shares the author's misunderstandings of it.

Answers are compared after normalising sets and tuples to sorted lists, so a
set of solutions compares equal however it was built.

WHAT THIS CANNOT CATCH
----------------------
An answer check only sees answers. In exact cover, replacing the S heuristic
(`select-min-val`) with `select-max-val` changes the search, not the result,
and no verifier can see it. That is what the operator comparison against
einsum.edge is for; this is the other half.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
import tempfile
from pathlib import Path
from typing import Any

from edge_workbench import tensor_facts
from edge_workbench.driver import run as driver


class VerifierError(RuntimeError):
    pass


def load(path: Path):
    path = Path(path)
    spec = importlib.util.spec_from_file_location("author_verifier", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(mod)
    missing = [n for n in ("solve", "answer") if not callable(getattr(mod, n, None))]
    if missing:
        raise VerifierError(
            f"{path.name} must define {missing}. See the contract in "
            f"edge_workbench/verifier.py.")
    return mod


def contract_problems(path: Path) -> list[str]:
    try:
        mod = load(path)
    except VerifierError as e:
        return [str(e)]
    except Exception as e:                       # noqa: BLE001
        return [f"{Path(path).name} does not import: {type(e).__name__}: {e}"]
    out = []
    if not isinstance(getattr(mod, "ANSWER_LABEL", None), str):
        out.append(f"{Path(path).name} should set ANSWER_LABEL, the name the "
                   f"page shows beside the answer")
    return out


def normalise(value: Any) -> Any:
    if isinstance(value, (set, frozenset)):
        return sorted((normalise(v) for v in value), key=json.dumps)
    if isinstance(value, (list, tuple)):
        return [normalise(v) for v in value]
    if isinstance(value, dict):
        return {str(k): normalise(v) for k, v in value.items()}
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


# ------------------------------------------------------------ instances ---

def instance_problems(instance: dict, program: dict,
                      gen_rank: str = "I") -> list[str]:
    """Does this instance supply exactly what the program reads?

    The program decides what an instance must hold, not the example: every
    tensor the cascade reads and nothing writes is an input, and every input
    has to arrive from here. Checked before running, because a missing input
    does not fail -- it reads as empty, and the cascade runs a different
    problem than the one the author published.
    """
    out: list[str] = []
    decls = {d["name"]: d for d in program.get("declarations", [])}
    needed = set(tensor_facts.inputs(program, gen_rank))
    tensors = instance.get("tensors") or {}
    scalars = instance.get("scalars") or {}
    extent = instance.get("extent") or {}

    supplied = set(tensors) | set(scalars)
    for name in sorted(needed - supplied):
        out.append(f"input {name} is not supplied. The cascade reads it and "
                   f"nothing writes it.")
    for name in sorted(supplied - needed):
        why = ("is not declared" if name not in decls else
               "is written by the cascade" if name not in
               tensor_facts.unused(program) else "is declared but never read")
        out.append(f"{name} is supplied but is not an input: it {why}")

    for name, cells in sorted(tensors.items()):
        decl = decls.get(name)
        if decl is None:
            continue
        ranks = [r["name"] for r in decl.get("ranks", [])
                 if r["name"] != gen_rank]
        if not ranks:
            out.append(f"{name} has no ranks; supply it under `scalars`")
            continue
        for r in ranks:
            if r not in extent:
                out.append(f"no extent for rank {r} (needed by {name})")
        if not isinstance(cells, dict):
            out.append(f"{name} must map coordinate strings to values")
            continue
        for coord in cells:
            parts = str(coord).split(",")
            if len(parts) != len(ranks):
                out.append(f"{name}[{coord}] has {len(parts)} coordinates; "
                           f"{name} is over {ranks}")
                break
            try:
                bad = [p for p, r in zip(parts, ranks)
                       if r in extent and not 0 <= int(p) < int(extent[r])]
            except ValueError:
                out.append(f"{name}[{coord}] is not an integer coordinate")
                break
            if bad:
                out.append(f"{name}[{coord}] is outside the extent "
                           f"{ {r: extent.get(r) for r in ranks} }")
                break

    for name in sorted(set(scalars) & set(decls)):
        if decls[name].get("ranks"):
            out.append(f"{name} has ranks; supply it under `tensors`")
    return out


# ------------------------------------------------------------- running ---

def free_choices(cascade: dict) -> list[str]:
    """Selector names the cascade maps to seeded random: the free choices."""
    return sorted(n for n, rule in (cascade.get("selectors") or {}).items()
                  if isinstance(rule, dict) and rule.get("rule") == "seeded")


def read_answer(mod, run: dict, instance: dict):
    """Call the author's `answer`, with the steps if it asks for them."""
    import inspect

    final = run["steps"][-1]["state"]
    if len(inspect.signature(mod.answer).parameters) >= 3:
        return mod.answer(final, instance, run["steps"])
    return mod.answer(final, instance)


def final_state(spec_dir: Path, instance: dict | None = None,
                seed: int | None = None, cascade: dict | None = None) -> dict:
    selectors = None
    if seed is not None and cascade is not None:
        selectors = dict(cascade.get("selectors") or {})
        for name in free_choices(cascade):
            selectors[name] = {"rule": "seeded", "seed": seed}
    if instance is None:
        r = driver.run(spec_dir=spec_dir, selectors=selectors)
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(instance, fh)
        try:
            r = driver.run(spec_dir=spec_dir, instance=fh.name,
                           selectors=selectors)
        finally:
            Path(fh.name).unlink(missing_ok=True)
    return r


def check(spec_dir: Path, verifier_path: Path, n: int = 12,
          seeds: int = 3, log=print) -> tuple[int, list[str]]:
    """(checks passed, failures). Prints one line per instance via `log`."""
    spec_dir = Path(spec_dir)
    mod = load(verifier_path)
    program = json.loads(driver._program_file(spec_dir).read_text())
    cascade = json.loads((spec_dir / "cascade.json").read_text())
    page = json.loads((spec_dir / "instance.json").read_text())
    free = free_choices(cascade)
    failures: list[str] = []
    passed = 0

    def one(name: str, inst: dict | None, actual_inst: dict, seed=None):
        nonlocal passed
        try:
            got = normalise(read_answer(
                mod, final_state(spec_dir, inst, seed, cascade), actual_inst))
        except driver.DriverError as e:
            failures.append(f"{name}: the cascade did not run: {e}")
            return None
        want = normalise(mod.solve(actual_inst))
        if got == want:
            passed += 1
        else:
            failures.append(f"{name}: cascade answered {got!r}, "
                            f"verifier.solve answered {want!r}")
        return got

    # The page's own instance, under several free choices: the answer must
    # not depend on them, or the choice was not free.
    for s in (range(seeds) if free else [None]):
        tag = f" (free-choice seed {s})" if s is not None else ""
        got = one(f"worked example{tag}", None, page, s)
        log(f"  worked example{tag}: {got!r}")

    expect = (page.get("expect") or {})
    if "answer" in expect:
        got = normalise(read_answer(mod, final_state(spec_dir), page))
        if got == normalise(expect["answer"]):
            passed += 1
            log(f"  published answer: {expect['answer']!r} matches")
        else:
            failures.append(f"the tutorial publishes {expect['answer']!r} "
                            f"for its worked example; the cascade answered "
                            f"{got!r}")

    gen = getattr(mod, "random_instance", None)
    if gen is None:
        log("  !! verifier.py has no random_instance(): only the worked "
            "example was checked")
    else:
        rng = random.Random(0)
        for k in range(n):
            inst = gen(rng)
            problems = instance_problems(inst, program,
                                         cascade.get("generationalRank", "I"))
            if problems:
                failures.append(f"random instance {k} is malformed: "
                                + "; ".join(problems[:3]))
                continue
            one(f"random instance {k}", inst, inst,
                rng.randrange(1 << 30) if free else None)
        log(f"  {n} random instances checked")
    return passed, failures


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="edge_workbench.verifier")
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--verifier", type=Path, required=True)
    ap.add_argument("-n", type=int, default=12)
    args = ap.parse_args(argv)
    passed, failures = check(args.spec, args.verifier, args.n)
    for f in failures:
        print(f"  FAIL {f}")
    print(f"{passed} checks passed" + (f", {len(failures)} FAILED"
                                       if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
