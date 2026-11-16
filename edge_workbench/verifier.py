# -*- coding: utf-8 -*-
"""Run an author's verifier against the cascade.

THE CONTRACT
------------
`verifier.py` sits beside the tutorial. It is ONE file (it may not import a
sibling module), and it must define:

    ANSWER_LABEL = "max flow"            # what the page calls the answer
    KIND   = "different-algorithm"       # one of KINDS, below
    METHOD = "Edmonds-Karp"              # what `solve` is, by name

    def solve(instance: dict):
        '''The answer, computed by a route that is NOT this cascade.'''

    def answer(final: dict, instance: dict):
        '''The answer, read off the cascade's final tensors.'''

    def random_instance(rng: random.Random) -> dict:
        '''A fresh problem, in the same shape as instance.json.'''

and, required when KIND == "certificate", optional otherwise:

    def certify(final: dict, instance: dict) -> list[str]:
        '''Everything wrong with the cascade's result; [] when it is valid.'''

`answer` and `certify` may take a third parameter, `steps`: every step of the
run, each with `einsum`, `output` and `state`. That is for answers the final
state cannot show -- exact cover's solutions are found one per success along
the way, and the search ends with the stack empty.

`instance` is the same dict the cascade runs on: `extent`, `scalars`,
`tensors` keyed by coordinate strings (`"0,1": 3`), and `coordSets` for the
named coordinate sets an Einsum is restricted to (`"root_id": ["0"]`). `final` is the state after
the last step: tensor name -> {coordinate string: value}, with the
generational rank already dropped.

Answers are compared after normalising sets and tuples to sorted lists, so a
set of solutions compares equal however it was built.

WHAT IS COMPARED is whatever the tutorial states as its answer. If the
tutorial publishes the set of vertices a DFS reaches, `solve` and `answer`
return that set; if it publishes the visit order, they return the order.

WHAT THE TOOL ENFORCES
----------------------
Before the file is imported (read as text, so nothing in it has run):

  * every required name is there, with the right number of parameters;
  * KIND is one of KINDS and METHOD is a non-empty string, both literals;
  * imports come from ALLOWED_STDLIB or LIBRARIES only. `random` and `time`
    are refused (the generator must use the `rng` it is given), and so are
    `edge_ir` and `edge_workbench` (the verifier must not be the cascade);
  * no `open`, `eval`, `exec`, `__import__`;
  * `solve` does not reach `answer` or `certify`, nor they `solve`: the
    independent answer and the reading of the cascade share no route.

Then, on N_RANDOM instances, instance k made from
`random.Random(f"{slug}:{k}")` so any one of them can be made again alone:

  * `random_instance` is deterministic: the same seed gives the same instance;
  * extents are 1..MAX_EXTENT, so the page-sized evaluator finishes;
  * the instances differ: at least MIN_DISTINCT distinct ones, MIN_SHAPES
    different extents, MIN_ANSWERS different `solve` answers;
  * `answer` reads the cascade: on an empty final state it must not already
    agree with `solve` on every instance.

An instance with no solution is a fine instance. How many have the answer an
empty run would give ("trivial") is reported, not refused.

`edge_workbench/approval.py` is the other half: who wrote the verifier, and
whether it has changed since a person approved it.

WHAT THIS CANNOT CATCH
----------------------
An answer check only sees answers. In exact cover, replacing the S heuristic
(`select-min-val`) with `select-max-val` changes the search, not the result,
and no verifier can see it. That is what the operator comparison against
einsum.edge is for; this is the other half.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import json
import random
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edge_workbench import tensor_facts
from edge_workbench.driver import run as driver

#: What `solve` is, relative to the cascade. The catalogue an author (or an
#: AI agent's user) chooses from.
KINDS = {
    "definition": "checks the problem's definition directly, by enumeration "
                  "(every subset, every path)",
    "library": "calls a trusted library's implementation (networkx, scipy)",
    "certificate": "`certify` checks that the cascade's own result is valid "
                   "(a flow that conserves, a cover that covers)",
    "different-algorithm": "a different algorithm for the same problem, "
                           "written here",
    "user-reference": "a reference implementation supplied by the user; "
                      "METHOD names where it came from",
}

#: Standard-library modules a verifier may import: computation only.
ALLOWED_STDLIB = {
    "math", "cmath", "itertools", "collections", "heapq", "functools",
    "fractions", "bisect", "operator", "statistics", "decimal", "numbers",
    "copy", "dataclasses", "enum", "typing", "string", "re", "array",
    "__future__",
}
#: Trusted libraries. They need not be installed; a verifier that imports
#: one on a machine without it is told what to install.
LIBRARIES = {"networkx", "scipy", "numpy"}
REFUSED_IMPORTS = {
    "random": "use the `rng` passed to random_instance, so instance k can "
              "be made again from its seed",
    "time": "a verifier that reads the clock is not reproducible",
    "edge_ir": "the verifier must not use the evaluator it is checking",
    "edge_workbench": "the verifier must not use the tool that is checking it",
}
REFUSED_NAMES = {"open", "eval", "exec", "compile", "__import__", "input",
                 "breakpoint", "__builtins__", "__loader__", "__spec__",
                 "globals", "__subclasses__", "__globals__"}

N_RANDOM = 12
MAX_EXTENT = 12
MIN_DISTINCT = 10
MIN_SHAPES = 2
MIN_ANSWERS = 3
INSTANCE_KEYS = {"extent", "tensors", "scalars", "coordSets"}


class VerifierError(RuntimeError):
    pass


# -------------------------------------------------- read as text first ---

def _literal(tree: ast.Module, name: str):
    """A module-level `NAME = <string literal>`, or None."""
    found = None
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign) else
                   [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            v = node.value
            found = (v.value if isinstance(v, ast.Constant)
                     and isinstance(v.value, str) else ...)
    return found


def declared(path: Path) -> dict:
    """ANSWER_LABEL, KIND and METHOD as written, without importing."""
    try:
        tree = ast.parse(Path(path).read_text())
    except (SyntaxError, OSError):
        return {}
    out = {}
    for name in ("ANSWER_LABEL", "KIND", "METHOD"):
        v = _literal(tree, name)
        if isinstance(v, str):
            out[name] = v
    return out


def _positional(fn: ast.FunctionDef) -> int | None:
    a = fn.args
    if a.vararg or a.kwarg or a.kwonlyargs:
        return None
    return len(a.posonlyargs) + len(a.args)


def _import_problems(tree: ast.Module, name: str) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = ["." * node.level + (node.module or "")]
        else:
            continue
        for full in mods:
            top = full.split(".")[0]
            if full.startswith("."):
                out.append(f"{name} line {node.lineno}: relative import "
                           f"`{full}`. The verifier is one file.")
            elif top in REFUSED_IMPORTS:
                out.append(f"{name} line {node.lineno}: imports `{top}`: "
                           f"{REFUSED_IMPORTS[top]}.")
            elif top not in ALLOWED_STDLIB and top not in LIBRARIES:
                out.append(
                    f"{name} line {node.lineno}: imports `{top}`, which is "
                    f"not allowed. A verifier may import "
                    f"{', '.join(sorted(LIBRARIES))} and these standard "
                    f"modules: {', '.join(sorted(ALLOWED_STDLIB - {'__future__'}))}.")
    return out


def _reach(tree: ast.Module) -> dict[str, set[str]]:
    """Module-level name -> every module-level name it can reach."""
    uses: dict[str, set[str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        else:
            continue
        seen = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        for n in names:
            uses.setdefault(n, set()).update(seen - {n})
    out = {}
    for start in uses:
        reached, todo = set(), [start]
        while todo:
            for nxt in uses.get(todo.pop(), ()):
                if nxt in uses and nxt not in reached:
                    reached.add(nxt)
                    todo.append(nxt)
        out[start] = reached
    return out


def static_problems(path: Path) -> list[str]:
    """Everything wrong with verifier.py that reading it can show.

    Nothing in the file runs here, which is the point: a verifier that
    imports the evaluator, or opens a file, is refused before it can.
    """
    path = Path(path)
    name = path.name
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        return [f"{name} is not valid Python: line {e.lineno}: {e.msg}"]
    out = _import_problems(tree, name)
    for node in ast.walk(tree):
        bad = (node.id if isinstance(node, ast.Name) else
               node.attr if isinstance(node, ast.Attribute) else None)
        if bad in REFUSED_NAMES:
            out.append(f"{name} line {node.lineno}: uses `{bad}`. A verifier "
                       f"computes from its arguments only: no files, no "
                       f"dynamic code.")

    label = _literal(tree, "ANSWER_LABEL")
    if not isinstance(label, str):
        out.append(f"{name} must set ANSWER_LABEL to a string, the name the "
                   f"page shows beside the answer")
    kind = _literal(tree, "KIND")
    if not isinstance(kind, str) or kind not in KINDS:
        got = "is missing" if kind is None else (
            f"is {kind!r}" if isinstance(kind, str) else "is not a string literal")
        out.append(f"{name} must set KIND to one of "
                   f"{', '.join(repr(k) for k in KINDS)}; it {got}")
    method = _literal(tree, "METHOD")
    if not isinstance(method, str) or not method.strip():
        out.append(f"{name} must set METHOD to a string literal naming what "
                   f"`solve` is (\"Edmonds-Karp\", \"networkx.maximum_flow\", "
                   f"\"subset enumeration\")")

    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    wanted = {"solve": (1,), "answer": (2, 3), "random_instance": (1,)}
    if kind == "certificate" or "certify" in funcs:
        wanted["certify"] = (2, 3)
    said = {"solve": "solve(instance)", "answer": "answer(final, instance[, steps])",
            "random_instance": "random_instance(rng)",
            "certify": "certify(final, instance[, steps])"}
    for fn, arity in wanted.items():
        if fn not in funcs:
            why = (" (required when KIND is 'certificate')"
                   if fn == "certify" else "")
            out.append(f"{name} must define {said[fn]}{why}")
        elif _positional(funcs[fn]) not in arity:
            out.append(f"{name}: {fn} must be written {said[fn]}, with "
                       f"exactly those parameters")

    reach = _reach(tree)
    readers = [f for f in ("answer", "certify") if f in funcs]
    for r in readers:
        if r in reach.get("solve", ()):
            out.append(f"{name}: solve reaches {r}. The independent answer "
                       f"must not be computed from the reading of the cascade.")
        if "solve" in reach.get(r, ()):
            out.append(f"{name}: {r} reaches solve. What is read off the "
                       f"cascade must not come from the independent answer.")
    return out


# ------------------------------------------------------------- import ---

def load(path: Path):
    """Import verifier.py, after reading it. Its directory is NOT put on
    sys.path: the file is the whole verifier, which is what makes a hash of
    it mean something."""
    path = Path(path)
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError as e:
        raise VerifierError(
            f"{path.name} is not valid Python: line {e.lineno}: {e.msg}") from e
    refused = _import_problems(tree, path.name)
    if refused:
        raise VerifierError("; ".join(refused))
    spec = importlib.util.spec_from_file_location("author_verifier", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ModuleNotFoundError as e:
        top = (e.name or "").split(".")[0]
        if top in LIBRARIES:
            raise VerifierError(
                f"{path.name} uses {top}, which is not installed here. "
                f"Install it: python3 -m pip install {top}") from e
        raise
    missing = [n for n in ("solve", "answer") if not callable(getattr(mod, n, None))]
    if missing:
        raise VerifierError(
            f"{path.name} must define {missing}. See the contract in "
            f"edge_workbench/verifier.py.")
    return mod


def _call(fn, final: dict, instance: dict, steps: list):
    """Call `answer` or `certify`, with the steps if it asks for them."""
    if len(inspect.signature(fn).parameters) >= 3:
        return limited(fn, final, instance, steps)
    return limited(fn, final, instance)


#: Seconds one call to random_instance, solve, answer or certify may take.
#: Instances are capped at extent 12, so anything slower is a verifier that
#: hangs (an unbounded search, an infinite loop), and a hang would otherwise
#: stop `check` with no message at all.
CALL_LIMIT = 30


class TookTooLong(Exception):
    pass


def limited(fn, *args):
    """`fn(*args)`, stopped with TookTooLong after CALL_LIMIT seconds.

    Uses SIGALRM, so the limit applies on Unix in the main thread (how `check`
    runs the verifier: as its own process). Elsewhere the call runs unlimited.
    """
    import signal
    import threading
    if (not hasattr(signal, "setitimer")
            or threading.current_thread() is not threading.main_thread()):
        return fn(*args)

    def stop(*_):
        raise TookTooLong(
            f"{getattr(fn, '__name__', 'the call')} took longer than "
            f"{CALL_LIMIT} s; keep instances small and the method bounded")

    old = signal.signal(signal.SIGALRM, stop)
    signal.setitimer(signal.ITIMER_REAL, CALL_LIMIT)
    try:
        return fn(*args)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def _canon(value: Any) -> str:
    return json.dumps(normalise(value), sort_keys=True)


def _shape_problems(inst: Any) -> list[str]:
    if not isinstance(inst, dict):
        return [f"returned {type(inst).__name__}, not a dict"]
    out = []
    extra = sorted(set(inst) - INSTANCE_KEYS)
    if extra:
        out.append(f"has keys {extra}; an instance holds only "
                   f"{sorted(INSTANCE_KEYS)}")
    extent = inst.get("extent")
    if not isinstance(extent, dict) or not extent:
        out.append("has no `extent`")
    else:
        for r, n in extent.items():
            if type(n) is not int or not 1 <= n <= MAX_EXTENT:
                out.append(f"extent {r} = {n!r}; extents must be whole "
                           f"numbers from 1 to {MAX_EXTENT}")
    tensors = inst.get("tensors")
    if not isinstance(tensors, dict):
        out.append("has no `tensors`")
    elif any(not isinstance(v, dict) for v in tensors.values()):
        out.append("every tensor must map coordinate strings to values")
    return out


@dataclass
class Sample:
    """The N_RANDOM instances a verifier makes, and what `solve` says."""

    slug: str
    instances: list = field(default_factory=list)    # dict, or None if unusable
    wants: list = field(default_factory=list)        # normalised, or None
    problems: list[str] = field(default_factory=list)
    trivial: int = 0

    @property
    def usable(self) -> list[int]:
        return [k for k, i in enumerate(self.instances) if i is not None]


def rng_for(slug: str, k: int) -> random.Random:
    return random.Random(f"{slug}:{k}")


def sample(mod, slug: str, n: int = N_RANDOM) -> Sample:
    """Make instance 0..n-1 and solve each, before any cascade runs.

    `solve` gets a deep copy, so nothing it does to its argument reaches the
    instance the cascade is given.
    """
    s = Sample(slug)
    gen = getattr(mod, "random_instance", None)
    for k in range(n):
        s.instances.append(None)
        s.wants.append(None)
        if gen is None:
            continue
        try:
            inst = limited(gen, rng_for(slug, k))
            again = limited(gen, rng_for(slug, k))
            text = json.dumps(inst, sort_keys=True)
        except Exception as e:                       # noqa: BLE001
            s.problems.append(f"random instance {k}: random_instance raised "
                              f"{type(e).__name__}: {e}")
            continue
        try:
            same = json.dumps(again, sort_keys=True) == text
        except Exception:                            # noqa: BLE001
            same = False
        if not same:
            s.problems.append(
                f"random instance {k}: random_instance is not deterministic. "
                f"Two calls with the same seed gave different instances; "
                f"draw everything from the `rng` argument and keep no state "
                f"between calls.")
            continue
        bad = _shape_problems(inst)
        if bad:
            s.problems.append(f"random instance {k} " + "; ".join(bad[:3]))
            continue
        s.instances[k] = inst
        try:
            s.wants[k] = normalise(limited(mod.solve, copy.deepcopy(inst)))
            json.dumps(s.wants[k], sort_keys=True)
        except Exception as e:                       # noqa: BLE001
            s.problems.append(f"random instance {k}: solve raised "
                              f"{type(e).__name__}: {e}")
            s.instances[k] = None
            continue
        try:
            blank = normalise(_call(mod.answer, {}, copy.deepcopy(inst), []))
        except Exception:                            # noqa: BLE001
            blank = ...                 # it needed the state: not trivial
        if blank is not ... and blank == s.wants[k]:
            s.trivial += 1
    return s


def dry_run_problems(mod, slug: str, n: int = N_RANDOM) -> tuple[list[str], Sample]:
    """The rules that need the verifier to run, but not the cascade."""
    s = sample(mod, slug, n)
    out = list(s.problems)
    if out:
        return out, s
    texts = {json.dumps(i, sort_keys=True) for i in s.instances}
    shapes = {json.dumps(i["extent"], sort_keys=True) for i in s.instances}
    answers = {json.dumps(w, sort_keys=True) for w in s.wants}
    floor = min(MIN_DISTINCT, n)
    if len(texts) < floor:
        out.append(f"random_instance made only {len(texts)} different "
                   f"instances in {n}; at least {floor} must differ")
    if len(shapes) < min(MIN_SHAPES, n):
        out.append(f"every random instance has the same extent "
                   f"{s.instances[0]['extent']}; vary the size")
    if len(answers) < min(MIN_ANSWERS, n):
        out.append(f"solve gave only {len(answers)} different answer(s) over "
                   f"{n} random instances; at least {min(MIN_ANSWERS, n)} are "
                   f"needed, or a cascade that always answers the same passes")
    if s.trivial == n:
        out.append(f"answer() already agrees with solve() on all {n} random "
                   f"instances when given an EMPTY final state, so it is not "
                   f"reading the cascade (or every instance has the trivial "
                   f"answer)")
    return out, s


def contract_problems(path: Path, slug: str | None = None) -> list[str]:
    """Static problems; then, only if there are none, dry-run problems."""
    return inspect_verifier(path, slug)[0]


def inspect_verifier(path: Path, slug: str | None = None
                     ) -> tuple[list[str], Sample | None]:
    path = Path(path)
    out = static_problems(path)
    if out:
        return out, None
    try:
        mod = load(path)
    except VerifierError as e:
        return [str(e)], None
    except Exception as e:                       # noqa: BLE001
        return [f"{path.name} does not import: {type(e).__name__}: {e}"], None
    return dry_run_problems(mod, slug or path.resolve().parent.name)


def random_instance_problems(path: Path, slug: str, program: dict,
                             gen_rank: str = "I") -> list[str]:
    """Do the random instances supply what the program reads?"""
    try:
        s = sample(load(path), slug)
    except Exception as e:                       # noqa: BLE001
        return [f"{Path(path).name} does not import: {type(e).__name__}: {e}"]
    out = []
    for k in s.usable:
        problems = instance_problems(s.instances[k], program, gen_rank)
        if problems:
            out.append(f"random instance {k} is malformed: "
                       + "; ".join(problems[:3]))
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
        # A stored value equal to the empty value IS absent, so this cell is
        # silently not there. A weight-0 edge against `G empty = 0` is the
        # case: the run is simply on a different problem.
        empty = decl.get("empty_value")
        same = [c for c, v in cells.items() if empty is not None
                and type(v) is type(empty) and v == empty]
        if same:
            out.append(f"{name}{same[:3]} equals {name}'s empty value "
                       f"({empty!r}), so the cascade reads it as absent, not "
                       f"as {empty!r}. Change the data, or the declared empty "
                       f"value if {empty!r} must be a real value.")
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

    sets_needed = tensor_facts.coord_sets(program)
    sets = instance.get("coordSets") or {}
    for name in sorted(set(sets_needed) - set(sets)):
        out.append(f"coordinate set {name} is not supplied (under `coordSets`). "
                   f"The cascade restricts an Einsum to it.")
    for name in sorted(set(sets) - set(sets_needed)):
        out.append(f"coordinate set {name} is supplied but the program names "
                   f"no such set")
    for name, members in sorted(sets.items()):
        rank = sets_needed.get(name)
        if not isinstance(members, list):
            out.append(f"coordinate set {name} must be a list of coordinates")
            continue
        for m in members:
            try:
                ok = rank not in extent or 0 <= int(m) < int(extent[rank])
            except ValueError:
                out.append(f"{name} member {m!r} is not an integer coordinate")
                break
            if not ok:
                out.append(f"{name} member {m} is outside rank {rank}'s "
                           f"extent {extent[rank]}")
                break
    return out


# ------------------------------------------------------------- running ---

def free_choices(cascade: dict) -> list[str]:
    """Selector names the cascade maps to seeded random: the free choices."""
    return sorted(n for n, rule in (cascade.get("selectors") or {}).items()
                  if isinstance(rule, dict) and rule.get("rule") == "seeded")


def read_answer(mod, run: dict, instance: dict):
    """Call the author's `answer`, with the steps if it asks for them."""
    return _call(mod.answer, run["steps"][-1]["state"], instance, run["steps"])


def final_state(spec_dir: Path, instance: dict | None = None,
                seed: int | None = None, cascade: dict | None = None) -> dict:
    # A seed runs the evaluator's ShuffledSchedule, which is how every free
    # choice is explored; it only matters when the cascade has one.
    if not (cascade and free_choices(cascade)):
        seed = None
    if instance is None:
        r = driver.run(spec_dir=spec_dir, seed=seed)
    else:
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as fh:
            json.dump(instance, fh)
        try:
            r = driver.run(spec_dir=spec_dir, instance=fh.name, seed=seed)
        finally:
            Path(fh.name).unlink(missing_ok=True)
    return r


@dataclass
class Result:
    passed: int = 0
    failures: list[str] = field(default_factory=list)
    random_total: int = 0
    random_run: int = 0
    random_agree: int = 0
    trivial: int = 0
    note: str = ""

    def summary(self) -> str:
        """One line, the random instances first: it is the line `check`
        shows, and "12 checked" must never be said of fewer."""
        if not self.random_total:
            rand = "random instances: none"
        else:
            rand = (f"random instances: {self.random_agree}/"
                    f"{self.random_total} agree")
            extra = [f"{self.trivial} trivial"] if self.trivial else []
            if self.random_run < self.random_total:
                extra.append(f"only {self.random_run} ran")
            if extra:
                rand += f" ({', '.join(extra)})"
        return (f"{rand}; {self.passed} checks passed"
                + (f", {len(self.failures)} FAILED" if self.failures else ""))


def check(spec_dir: Path, verifier_path: Path, n: int = N_RANDOM,
          seeds: int = 3, log=print, slug: str | None = None,
          only: int | None = None) -> Result:
    """Compare the cascade with the verifier. One line per instance via `log`.

    `only` reruns one random instance, alone, and prints it: instance k is
    made from its own seed, so it is the same instance it was in the full run.
    """
    spec_dir = Path(spec_dir)
    verifier_path = Path(verifier_path)
    slug = slug or verifier_path.resolve().parent.name
    mod = load(verifier_path)
    program = json.loads(driver._program_file(spec_dir).read_text())
    cascade = json.loads((spec_dir / "cascade.json").read_text())
    page = json.loads((spec_dir / "instance.json").read_text())
    gen_rank = cascade.get("generationalRank", "I")
    free = free_choices(cascade)
    res = Result()
    certify = getattr(mod, "certify", None)

    # Every independent answer is computed first, on copies, before any
    # cascade runs: nothing a run leaves behind can reach `solve`.
    drawn = sample(mod, slug, n)
    res.failures += drawn.problems
    res.random_total, res.trivial = n, drawn.trivial
    try:
        page_want = normalise(limited(mod.solve, copy.deepcopy(page)))
    except Exception as e:                           # noqa: BLE001
        res.failures.append(f"worked example: solve raised "
                            f"{type(e).__name__}: {e}")
        log("  " + res.summary())
        return res
    stuck: list[str] = []          # one failure to run says enough

    def one(name: str, inst: dict | None, actual: dict, want, seed=None):
        """True if the cascade ran and agreed; None if it did not run."""
        try:
            run = final_state(spec_dir, inst, seed, cascade)
        except driver.DriverError as e:
            res.failures.append(f"{name}: the cascade did not run: {e}")
            stuck.append(name)
            return None, None
        try:
            got = normalise(read_answer(mod, run, copy.deepcopy(actual)))
        except Exception as e:                       # noqa: BLE001
            res.failures.append(f"{name}: answer raised {type(e).__name__}: {e}")
            return False, None
        ok = got == want
        if not ok:
            res.failures.append(f"{name}: cascade answered {got!r}, "
                                f"verifier.solve answered {want!r}")
        if certify is not None:
            try:
                wrong = list(_call(certify, run["steps"][-1]["state"],
                                   copy.deepcopy(actual), run["steps"]) or [])
            except Exception as e:                   # noqa: BLE001
                wrong = [f"certify raised {type(e).__name__}: {e}"]
            if wrong:
                ok = False
                res.failures.append(f"{name}: the cascade's result is not "
                                    f"valid: " + "; ".join(map(str, wrong[:3])))
        if ok:
            res.passed += 1
        return ok, got

    if only is None:
        # The page's own instance, under several free choices: the answer
        # must not depend on them, or the choice was not free.
        for s in (range(seeds) if free else [None]):
            tag = f" (free-choice seed {s})" if s is not None else ""
            _, got = one(f"worked example{tag}", None, page, page_want, s)
            log(f"  worked example{tag}: {got!r}")

        expect = (page.get("expect") or {})
        if "answer" in expect and not stuck:
            got = normalise(read_answer(mod, final_state(spec_dir), page))
            if got == normalise(expect["answer"]):
                res.passed += 1
                log(f"  published answer: {expect['answer']!r} matches")
            else:
                res.failures.append(
                    f"the tutorial publishes {expect['answer']!r} for its "
                    f"worked example; the cascade answered {got!r}")

    for k in ([only] if only is not None else range(n)):
        if stuck:
            break
        inst = drawn.instances[k] if 0 <= k < n else None
        if inst is None:
            if only is not None:
                log(f"  random instance {k} could not be made")
            continue
        problems = instance_problems(inst, program, gen_rank)
        if problems:
            res.failures.append(f"random instance {k} is malformed: "
                                + "; ".join(problems[:3]))
            continue
        seed = (random.Random(f"{slug}:{k}:free").randrange(1 << 30)
                if free else None)
        res.random_run += 1
        ok, got = one(f"random instance {k}", inst, inst, drawn.wants[k], seed)
        if ok:
            res.random_agree += 1
        if only is not None:
            log(f"  random instance {k} (seed {slug}:{k}):")
            log("    " + json.dumps(inst, sort_keys=True))
            log(f"    solve:   {drawn.wants[k]!r}")
            log(f"    cascade: {got!r}")
        elif not ok:
            log(f"  random instance {k} FAILED. Run it alone with "
                f"--instance {k}")
    if only is not None:
        res.random_total = 1
        res.trivial = 0
    return res


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="edge_workbench.verifier")
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--verifier", type=Path, required=True)
    ap.add_argument("--slug", default=None,
                    help="seeds the random instances; the tutorial's name")
    ap.add_argument("--instance", type=int, default=None, metavar="K",
                    help="rerun random instance K alone and print it")
    ap.add_argument("-n", type=int, default=N_RANDOM)
    args = ap.parse_args(argv)
    try:
        res = check(args.spec, args.verifier, args.n, slug=args.slug,
                    only=args.instance)
    except VerifierError as e:
        print(f"  FAIL {e}")
        print("0 checks passed, 1 FAILED")
        return 1
    for f in res.failures:
        print(f"  FAIL {f}")
    print(res.summary())
    return 1 if res.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
