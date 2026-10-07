# -*- coding: utf-8 -*-
"""The checks between a specification and its IR, as functions that report.

These started life as pytest tests over the algorithms committed here
(`tests/test_ir_matches_the_spec.py`, `tests/test_spec_is_valid_ir.py`). An
author running the workbench on their own tutorial has no test suite -- they
have one command -- so the same checks live here as plain functions returning
findings, and the command prints them.

Every function returns a list of strings. Empty means clean. None of them
raises on a finding: an author fixing a spec wants every problem at once, not
the first one followed by a re-run to discover the second.

Authority runs one way: `einsum.edge` is the specification, and a
disagreement is reported as the IR being wrong.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from edge_workbench.spec_surface import (
    COMPUTE_ALIASES,
    SurfaceDeclaration,
    SurfaceEinsum,
    derive_labels,
    helper_tensors,
    normalise_empty,
    parse_specs,
)


# ------------------------------------------------------------- edge_ir ---

def upstream() -> Path | None:
    """Where edge-core-ir is, or None.

    The IR's own classes are needed to run a builder and to validate what it
    produced. `EDGE_IR_REPO` wins; then an edge-core-ir checkout beside this
    repository (the layout AUTHORING.md describes); then
    `~/Projects/edge-core-ir`; an importable `edge_ir` only last.

    An installed `edge_ir` comes last because more than one repository
    ships a package by that name -- edge-ir-interpreter's editable install
    shadowed edge-core-ir here, so builders were validated against a
    different copy of the IR than the test suites used.
    """
    named = os.environ.get("EDGE_IR_REPO")
    if named:
        return Path(named).expanduser()
    for guess in (Path(__file__).resolve().parents[2] / "edge-core-ir",
                  Path.home() / "Projects" / "edge-core-ir"):
        if (guess / "edge_ir" / "ir").is_dir():
            return guess
    spec = importlib.util.find_spec("edge_ir")
    if spec and spec.origin:
        return Path(spec.origin).resolve().parent.parent
    return None


def _import_edge_ir() -> None:
    root = upstream()
    if root is None:
        raise RuntimeError(
            "edge-core-ir not found. Clone it and either `pip install -e` it "
            "or set EDGE_IR_REPO to the checkout."
        )
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


# ------------------------------------------------------- layer 1 and 2 ---

def layer_one(program: dict) -> list[str]:
    """The IR's own parser accepts the program."""
    _import_edge_ir()
    from pydantic import ValidationError

    from edge_ir.ir.program import Program

    try:
        Program.model_validate(program)
    except ValidationError as e:
        # Grouped by (kind, field): 49 raw errors were 4 real mistakes once,
        # and the raw list buries that.
        seen: dict[tuple[str, str], tuple[int, str]] = {}
        for err in e.errors():
            key = (err["type"], str(err["loc"][-1] if err["loc"] else "?"))
            n, where = seen.get(key, (0, ".".join(str(x) for x in err["loc"])))
            seen[key] = (n + 1, where)
        return [
            f"not valid IR: {n}x {kind} at {field} (e.g. {where})"
            for (kind, field), (n, where) in sorted(
                seen.items(), key=lambda kv: -kv[1][0])
        ]
    return []


def _surface_key(text: str):
    """One output rank as einsum.edge writes it, in upstream's terms.

    `i+1` -> the advancing variable plus one; `1` -> a constant; `u : u = s`
    -> the variable `u` (predicates are not read, exactly as upstream's pass
    does not read them); `v*` -> `v`; `|V|` -> a shape constant.
    """
    from edge_ir.validator.single_assignment import _CONST, _OPAQUE, _VAR, _RankKey
    import re as _re

    t = text.split(":", 1)[0].replace(" ", "").replace("*", "")
    if _re.fullmatch(r"-?\d+", t):
        return _RankKey(_CONST, t, 0)
    if _re.fullmatch(r"\|[^|]+\|", t):
        return _RankKey(_CONST, t, 0)
    m = _re.fullmatch(r"([a-z][A-Za-z0-9]*)(?:([+-])(\d+))?", t)
    if m:
        off = int(m.group(3) or 0) * (-1 if m.group(2) == "-" else 1)
        return _RankKey(_VAR, m.group(1), off)
    return _RankKey(_OPAQUE, t, 0)


def spec_write_sites(edge: Path) -> list[tuple[str, str, tuple]]:
    """(where, tensor, rank keys) for every write einsum.edge makes.

    Initialization lines first, then each labelled Einsum once -- a `cases`
    statement is ONE write, however many IR nodes it lowers to.
    """
    from edge_workbench import spec_surface as ss
    from edge_workbench.tutorial_vs_edge import read_edge

    sites = []
    for k, line in enumerate(read_edge(edge).initialization):
        m = ss.HEAD_RE.match(line)
        if m:
            ranks = ss._split_ranks(m.group(2), m.group(3))
            sites.append((f"initialization line {k + 1}", m.group(1),
                          tuple(_surface_key(r) for r in ranks)))
    for label, e in sorted(ss.parse_edge_file(edge).items()):
        sites.append((label, e.output,
                      tuple(_surface_key(r) for r in e.output_ranks)))
    return sites


def _overlaps(sites, iteration) -> dict[str, list[str]]:
    from edge_ir.validator.single_assignment import _can_meet

    out: dict[str, list[str]] = {}
    for n, (w1, t1, r1) in enumerate(sites):
        for w2, t2, r2 in sites[n + 1:]:
            if t1 != t2 or len(r1) != len(r2):
                continue
            if all(_can_meet(a, b, iteration) for a, b in zip(r1, r2)):
                out.setdefault(t1, []).append(f"{w1} and {w2}")
    return out


def single_assignment(program: dict, edge: Path, cascade: dict) -> list[str]:
    """The IR's single-assignment findings are exactly the specification's.

    Upstream's pass reports two writes of the same slice. Some of those are
    the author's -- max-flow writes `F_{1,u,v}` in the cascade and `F_{i+1,u,v}`
    every round, so `F` is reported, and that is how the algorithm is written.
    Such findings used to be listed by hand, with reasons, in
    known_ir_violations.json -- a waiver file written by whoever wrote the
    builder, excusing that builder's own findings.

    They do not need to be listed: einsum.edge says where every tensor is
    written, so the same pass run over the SPECIFICATION's writes says which
    findings to expect. The IR must have exactly those. An extra one means the
    lowering writes a slice twice where the author wrote it once; a missing
    one means the lowering lost a write.

    The arms of one `cases` statement lower to several IR nodes writing the
    same slice; that is the lowering's, not the author's, so those pairs are
    not counted. Any other Einsum written twice is.
    """
    _import_edge_ir()
    from edge_ir.ir.program import Program
    from edge_ir.validator.single_assignment import (
        _Iteration,
        check_single_assignment,
    )

    try:
        parsed = Program.model_validate(program)
    except Exception:
        return []                                  # layer_one reports it
    iteration = _Iteration("i", 0)
    expected = _overlaps(spec_write_sites(edge), iteration)

    from edge_workbench.spec_surface import parse_edge_file

    is_cases = {lb: "cases" in e.text for lb, e in parse_edge_file(edge).items()}
    label_of = {}
    for label, idx in (cascade.get("labels") or {}).items():
        for k in (idx if isinstance(idx, list) else [idx]):
            label_of[f"cascade[{k}]"] = label
    alias = cascade.get("displayNames") or {}
    actual: dict[str, list[str]] = {}
    for v in check_single_assignment(parsed):
        l1, l2 = label_of.get(v.first.path), label_of.get(v.second.path)
        if l1 is not None and l1 == l2 and is_cases.get(l1):
            continue                               # the arms of one `cases`
        name = alias.get(v.tensor, v.tensor)
        actual.setdefault(name, []).append(str(v))

    out = []
    for t in sorted(set(actual) - set(expected)):
        out.append(f"the IR writes a slice of {t} twice where einsum.edge writes "
                   f"it once: {actual[t][0]}")
    for t in sorted(set(expected) - set(actual)):
        out.append(f"einsum.edge writes {t} at {expected[t][0]}, overlapping "
                   f"slices, but the IR does not -- a write was lost")
    return out


def operator_names(program: dict, functions_py: Path | None) -> list[str]:
    """Every operator the program names is implemented somewhere."""
    _import_edge_ir()
    from edge_ir.ir.program import Program
    from edge_ir.udf.builtins import default_registry

    try:
        from edge_ir.validator import check_udf_names
    except ImportError:
        return []                  # this upstream predates the pass
    try:
        parsed = Program.model_validate(program)
    except Exception:
        return []

    registry = default_registry()
    if functions_py is not None and functions_py.exists():
        registry = _registry_from(functions_py) or registry
    return [f"operator not implemented: {f}"
            for f in check_udf_names(parsed, registry)]


def _registry_from(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    preferred = path.stem.replace("_functions", "_registry")
    if hasattr(mod, preferred):
        found = getattr(mod, preferred)
        return found() if callable(found) else found
    if hasattr(mod, "registry"):
        found = mod.registry
        return found() if callable(found) else found
    return None


# ------------------------------------------------------ spec versus IR ---

def _rank_text(rank: dict) -> str:
    kind = rank.get("kind")
    if kind == "var":
        return rank["name"]
    if kind == "literal":
        return str(rank["value"])
    if kind == "arith":
        return f"{_rank_text(rank['lhs'])}{rank['op']}{_rank_text(rank['rhs'])}"
    return "?"


def _udf_names(node: Any) -> set[str]:
    found: set[str] = set()

    def walk(n):
        if isinstance(n, dict):
            if n.get("kind") == "user_defined" and "name" in n:
                found.add(n["name"])
            if isinstance(n.get("coord_op"), dict):
                found.add(n["coord_op"].get("name", ""))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return {f for f in found if f}


def _ir_specs(node: dict) -> list[tuple[str, str, str]]:
    out = []
    for spec in node.get("specs", []):
        if spec.get("kind") not in ("map", "reduce"):
            continue
        compute = spec.get("compute_op") or {}
        merge = spec.get("merge_op") or {}
        name = compute.get("symbol") or compute.get("name") or "?"
        out.append((spec["kind"], COMPUTE_ALIASES.get(name, name),
                    merge.get("symbol") or merge.get("name") or "?"))
    return out


def spec_versus_ir(surface: dict[str, SurfaceEinsum],
                   declared: dict[str, SurfaceDeclaration],
                   program: dict, cascade: dict) -> list[str]:
    """Everything the specification states that the IR could get wrong.

    Per labelled Einsum: the output tensor, the generation it writes, the
    named operators in both directions, and every `compute(merge)` pair the
    spec writes. Per tensor: ranks, data type and empty value.

    The operator comparison is the one that makes a model-written builder
    safe to accept. Swapping one merge from intersect to union passed every
    other gate on max-flow, including the answer check.
    """
    out: list[str] = []
    alias = cascade.get("displayNames", {})
    labels = cascade.get("labels", {})
    nodes = program["main_edge"]["cascade"]["einsums"]

    def nodes_for(label):
        idx = labels[label]
        return [nodes[i] for i in (idx if isinstance(idx, list) else [idx])]

    unmapped = sorted(set(surface) - set(labels))
    if unmapped:
        out.append(f"einsum.edge labels with no IR node: {unmapped}. The "
                   f"builder either skipped them or wrote something that does "
                   f"not correspond to them.")

    for label, e in sorted(surface.items()):
        if label not in labels:
            continue
        lowered = nodes_for(label)
        where = f"{label} ({e.text[:70]}{'...' if len(e.text) > 70 else ''})"

        # The label's own write is the last node; any before it are helpers
        # the lowering introduced, which write tensors the spec does not.
        for node in lowered[-1:]:
            written = alias.get(node["output_tensor"], node["output_tensor"])
            if written != e.output:
                out.append(f"{where}: spec writes {e.output}, IR writes "
                           f"{written}")
            if e.output_ranks and node.get("output_ranks"):
                want = e.output_ranks[0].replace(" ", "")
                got = _rank_text(node["output_ranks"][0]).replace(" ", "")
                if got != want:
                    out.append(f"{where}: spec writes generation {want}, IR "
                               f"writes {got}")

        used: set[str] = set()
        for node in lowered:
            used |= _udf_names(node)
        hyphenated = {n for n in used if "-" in n}
        invented = hyphenated - set(e.named_ops)
        if invented:
            out.append(f"{where}: IR names {sorted(invented)}, which the spec "
                       f"does not")
        missing = set(e.named_ops) - used
        if missing:
            out.append(f"{where}: spec names {sorted(missing)}, which the IR "
                       f"does not use")

        lowered_specs = [t for node in lowered for t in _ir_specs(node)]
        for want in parse_specs(e.text):
            triple = (want.action, want.compute, want.merge)
            if triple not in lowered_specs:
                same_merge = any(a == want.action and m == want.merge
                                 for a, _, m in lowered_specs)
                why = ("The compute decides what value is written."
                       if same_merge else
                       "The merge decides where a value exists, so this "
                       "changes the algorithm.")
                out.append(
                    f"{where}: spec writes {want.compute}({want.merge}) as a "
                    f"{want.action}; IR has {lowered_specs}. {why}")

    helpers = helper_tensors(surface, program, labels, alias)
    for decl in program.get("declarations", []):
        name = decl["name"]
        spec = declared.get(name) or declared.get(alias.get(name, name))
        if spec is None:
            if decl.get("ranks") and name not in helpers:
                out.append(f"{name} is declared in the IR with ranks but not "
                           f"in einsum.edge")
            continue
        ir_ranks = tuple(r["name"] for r in decl.get("ranks", []))
        if ir_ranks != spec.ranks:
            out.append(f"{name}: spec ranks {list(spec.ranks)}, IR ranks "
                       f"{list(ir_ranks)}")
        if normalise_empty(decl.get("empty_value")) != normalise_empty(spec.empty):
            out.append(f"{name}: spec empty = {spec.empty}, IR empty = "
                       f"{decl.get('empty_value')!r}. `value == empty => "
                       f"absent`, so this changes which entries exist.")
        ir_type = (decl.get("data_type") or {}).get("name", "").lower()
        if not ir_type.startswith(spec.data_type[:3]):
            out.append(f"{name}: spec type {spec.data_type}, IR type "
                       f"{ir_type!r}")
    return out


def label_map(surface: dict, program: dict, alias: dict) -> tuple[dict, list[str]]:
    """The label map, derived, or a finding saying why it could not be."""
    labels = derive_labels(surface, program, alias)
    if labels:
        return labels, []
    return {}, [
        "could not match the IR's Einsums to einsum.edge's labels in order. "
        "Each labelled Einsum must lower to one or more CONSECUTIVE IR nodes "
        "writing the same tensor with the same output ranks."
    ]


def load_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None
