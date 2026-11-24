# -*- coding: utf-8 -*-
"""Run a cascade with edge-core-ir's evaluator and get a trace back.

    trace = run()          # or run("some-algorithm"), run(spec_dir=...)

edge-core-ir's evaluator is the source of truth for EDGE semantics, so it is
the only thing that runs a cascade here. This module does not evaluate
anything: it hands the program and the instance to
`edge_ir.evaluator.evaluate`, records what the tensors held before and after
each Einsum it ran, and reshapes that into the steps the page shows.

There used to be a second evaluator in JavaScript, run here through `node` and
again in the browser. Two implementations of one semantics drift, and this
one did: every gap found in it had to be fixed by hand, and nothing checked
it against the reference. The page now renders what the reference computed.

The recording uses no private API of the evaluator's, but it does wrap
`evaluate_einsum` -- the one function the initialization and the cascade loop
call per Einsum -- for the duration of a run. An official per-Einsum hook in
edge-core-ir would replace that; see docs/issues-for-edge-core-ir.md.
"""

from __future__ import annotations

from edge_workbench.cascade_shape import flat_nodes, stopping_conditions  # noqa: F401

import importlib.util
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edge_workbench import paths


class DriverError(RuntimeError):
    pass


def run(algorithm: str | None = None, *, spec_dir: str | Path | None = None,
        program: str | None = None, instance: str | None = None,
        seed: int | None = None) -> dict:
    """Execute the cascade and return {generations, steps, executed}.

    `executed` is the IR-node tally -- node key to run count -- which
    `edge_workbench.coverage` checks against the specification.

    `instance` runs a different problem instance than the algorithm's own;
    the verifier uses it to sweep generated instances.

    `seed` runs under the evaluator's `ShuffledSchedule(seed)`, which is how a
    free choice (`select-any`, `pick-admissible-edge`) is explored: the
    evaluator decides those by visiting order.
    """
    from edge_workbench.spec_check import _import_edge_ir

    _import_edge_ir()
    from edge_ir.evaluator import evaluate
    from edge_ir.evaluator.errors import EvaluationError
    from edge_ir.evaluator.order import SequentialSchedule, ShuffledSchedule
    from edge_ir.ir.program import Program

    spec = Path(spec_dir) if spec_dir is not None else paths.spec(algorithm)
    prog_json = json.loads((Path(program) if program
                            else _program_file(spec)).read_text())
    cascade = json.loads((spec / "cascade.json").read_text())
    inst = json.loads(Path(instance).read_text() if instance
                      else (spec / "instance.json").read_text())

    parsed = Program.model_validate(prog_json)
    shape_env, inputs = host_inputs(prog_json, inst)
    coord_sets = {name: [tuple(int(c) for c in str(k).split(",")) if "," in str(k)
                         else int(k) for k in members]
                  for name, members in (inst.get("coordSets") or {}).items()}
    schedule = ShuffledSchedule(seed=seed) if seed is not None else SequentialSchedule()

    records: list[dict] = []
    schedule_note = ({"kind": "shuffled", "seed": seed} if seed is not None
                     else {"kind": "sequential"})
    try:
        with _recording(records):
            result = evaluate(
                parsed,
                inputs=inputs,
                shape_env=shape_env,
                functions=_registry(spec),
                schedule=schedule,
                coord_sets=coord_sets,
                max_iterations=int(cascade.get("maxGenerations", 500)),
            )
    except EvaluationError as e:
        raise DriverError(f"the cascade did not run.\n{type(e).__name__}: {e}") from e
    return _steps(prog_json, cascade, records, result, parsed, schedule_note)


# ------------------------------------------------------------- inputs ---

def host_inputs(program: dict, instance: dict) -> tuple[dict, dict]:
    """(shape_env, inputs) for `evaluate`, from an instance.json.

    Shapes: a declared rank's shape symbol (`|V|`) takes the instance's extent
    for that rank (`U: 4`). Tensors: coordinate strings become tuples.
    Scalars become zero-rank inputs.
    """
    extent = instance.get("extent", {})
    shape_env: dict[str, int] = {}
    for d in program.get("declarations", []):
        for r in d.get("ranks", []):
            shape = r.get("shape")
            if isinstance(shape, str) and r["name"] in extent:
                shape_env[shape] = int(extent[r["name"]])
    inputs: dict[str, dict] = {}
    for name, cells in (instance.get("tensors") or {}).items():
        inputs[name] = {
            tuple(int(c) for c in str(k).split(",")) if str(k) != "" else (): v
            for k, v in cells.items()
        }
    for name, value in (instance.get("scalars") or {}).items():
        inputs[name] = {(): value}
    return shape_env, inputs


def _registry(spec: Path):
    """The algorithm's own operator registry, else the workbench's base one."""
    from edge_workbench.operators import base_registry

    for path in sorted(spec.glob("*_functions.py")):
        mod_spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(mod_spec)
        sys.modules[path.stem] = mod
        mod_spec.loader.exec_module(mod)
        for name in (path.stem.replace("_functions", "_registry"), "registry"):
            found = getattr(mod, name, None)
            if found is not None:
                return found() if callable(found) else found
    return base_registry()


# ---------------------------------------------------------- recording ---

def _items(tensor) -> dict:
    return {tuple(c): v for c, v in tensor.items()}


@contextmanager
def _recording(records: list[dict]):
    """Record tensors before and after every Einsum the evaluator runs."""
    from edge_ir.evaluator import cascade as ev_cascade
    from edge_ir.evaluator import program as ev_program

    original = ev_cascade.evaluate_einsum

    def recorded(einsum, *, env, pinned=None, schedule=None):
        before = _snapshot(env)
        with _watching_populate(einsum, env) as rounds:
            res = original(einsum, env=env, pinned=pinned, schedule=schedule)
        after = _snapshot(env)
        _finish_rounds(rounds, env.tensors[einsum.output_tensor])
        inner_map = _inner_map(einsum, res, env, pinned)
        written_gen = None
        if einsum.output_ranks:
            from edge_ir.evaluator.projection import evaluate_rank_expression

            try:
                written_gen = evaluate_rank_expression(
                    einsum.output_ranks[0], dict(pinned or {}),
                    shape_env=env.shape_env, registry=env.functions)
            except Exception:  # noqa: BLE001 -- not a generation subscript
                written_gen = None
        records.append({"einsum": einsum, "pinned": dict(pinned or {}),
                        "written_gen": written_gen,
                        "result": res, "before": before, "after": after,
                        "populate_rounds": rounds,
                        "inner_map": inner_map, "env": env})
        return res

    ev_cascade.evaluate_einsum = recorded
    ev_program.evaluate_einsum = recorded
    try:
        yield
    finally:
        ev_cascade.evaluate_einsum = original
        ev_program.evaluate_einsum = original


# ------------------------------------------------------ populate rounds ---

@dataclass
class PopulateRound:
    """What one round of Populate did (paper §6.6.1, Inset 4): one incoming
    Reduce Temporary element and the mutable fiber it belongs to.

    Recorded by watching the coordinate operator the evaluator calls once per
    round, through the registry the workbench supplies; edge-core-ir is not
    changed for it (docs/evaluator-needs.md). The evaluator still checks
    W ∩ (dom(S) ∪ D) = ∅ and raises on a violation, so a round recorded in
    an Einsum that returned passed that check.
    """

    point: tuple
    axes: tuple
    output_coord: tuple
    value: Any
    fiber_key: tuple
    mutable_positions: tuple
    locations: tuple
    pre_state: dict
    write_del: list = field(default_factory=list)
    deletes: list = field(default_factory=list)
    writes: dict = field(default_factory=dict)
    post_state: dict = field(default_factory=dict)
    constraint_checked: bool = False


@contextmanager
def _watching_populate(einsum, env):
    """Swap in a recording copy of this Einsum's coordinate operator while
    the evaluator runs it, and put the original back."""
    from edge_ir.evaluator.context import PopulateAction
    from edge_ir.ir.actions import PopulateSpec
    from edge_ir.udf import UdfCategory
    from edge_ir.udf.decl import UdfImpl

    rounds: list[PopulateRound] = []
    spec = next((s for s in einsum.specs if isinstance(s, PopulateSpec)), None)
    registry = env.functions
    if spec is None or not spec.rank_list or spec.coord_op is None or \
            not registry.has(UdfCategory.COORDINATE, spec.coord_op.name):
        yield rounds
        return
    name = spec.coord_op.name
    decl = registry.decl(UdfCategory.COORDINATE, name)
    inner = registry.impl(UdfCategory.COORDINATE, name)

    class Watched(UdfImpl):
        def call(self, *args, ctx=None):
            fiber, cs_z, dv_r = args
            out = list(inner.call(*args, ctx=ctx))
            rounds.append(PopulateRound(
                point=tuple(getattr(ctx, "point", ()) or ()),
                axes=tuple(getattr(ctx, "axes", ()) or ()),
                output_coord=tuple(cs_z),
                value=dv_r,
                fiber_key=tuple(getattr(ctx, "fiber_key", ()) or ()),
                mutable_positions=tuple(getattr(ctx, "mutable_positions", ())
                                        or ()),
                locations=tuple(e.coord for e in fiber),
                pre_state={e.coord: e.value for e in fiber if e.present},
                write_del=[(tuple(c), PopulateAction(a).value) for c, a in out],
            ))
            return out

    registry.register(decl, Watched(), allow_override=True)
    try:
        yield rounds
    finally:
        registry.register(decl, inner, allow_override=True)


def _finish_rounds(rounds: list[PopulateRound], output) -> None:
    """D, W and each round's post-state, from what the operator returned.

    A round's post-state is the fiber the next round on the same fiber was
    handed, or, for the last one, that fiber in the Einsum's output. A write
    whose value equals the output's empty value leaves the location absent
    (a stored empty value is absent), so W shows the empty value there.
    """
    final = {tuple(c): v for c, v in output.items()}
    for k, r in enumerate(rounds):
        r.deletes = [c for c, a in r.write_del if a == "Delete"]
        nxt = next((q for q in rounds[k + 1:] if q.fiber_key == r.fiber_key),
                   None)
        r.post_state = (dict(nxt.pre_state) if nxt is not None else
                        {c: final[c] for c in r.locations if c in final})
        r.writes = {c: r.post_state.get(c, output.empty_value)
                    for c, a in r.write_del if a == "Write"}
        r.constraint_checked = True


# -------------------------------------------------------------- steps ---

def _gen_ranks(program: dict, gen: str) -> set[str]:
    """Tensors whose first rank is the generational one."""
    return {d["name"] for d in program.get("declarations", [])
            if d.get("ranks") and d["ranks"][0]["name"] == gen}


def _flat(snapshot: dict, gen_tensors: set[str], alias: dict,
          written: dict | None = None) -> dict:
    """{display name: {"u,v": value}}: each generational tensor at the latest
    generation WRITTEN so far (which may be empty -- an empty active set is
    how max-flow stops), the generation dropped from the key."""
    written = written or {}
    out: dict[str, dict] = {}
    for name, cells in snapshot.items():
        shown = alias.get(name, name)
        if name in gen_tensors:
            latest = written.get(name)
            if latest is None:
                latest = max((c[0] for c in cells), default=None)
            out[shown] = {",".join(str(x) for x in c[1:]): v
                          for c, v in cells.items() if c[0] == latest}
        else:
            out[shown] = {",".join(str(x) for x in c): v for c, v in cells.items()}
    return out


def _rank_text(rank: dict) -> str:
    from edge_workbench.spec_check import _rank_text as text

    return text(rank)


def _key(coord: tuple, gen_first: bool) -> str:
    return ",".join(str(x) for x in (coord[1:] if gen_first else coord))


def _snapshot(env) -> dict:
    """Every tensor, each value as its declaration says.

    A populate's `1` is pass-through, so set-cover's E17 carries a column count
    into `PickedCol`, which the tutorial declares Boolean. The evaluator does
    not enforce declared types, and a reader should not see a count in a
    Boolean tensor: there, a stored value just means true.
    """
    out = {}
    for name, tensor in env.tensors.items():
        cells = _items(tensor)
        decl = env.declarations.get(name)
        kind = getattr(getattr(decl, "data_type", None), "name", None)
        out[name] = ({c: v if isinstance(v, bool) else True
                      for c, v in cells.items()} if kind == "bool" else cells)
    return out


def _inner_map(einsum, res, env, pinned) -> dict | None:
    """The Map's values at each point, when a Reduce runs inside parentheses.

    Such a Reduce folds as the Einsum runs, so `map_tmp` holds the whole
    Einsum's value and not the Map's. The page must not evaluate anything, so
    the evaluator's own `map_action` is asked. None for every other Einsum:
    `map_tmp` already is the Map's result.
    """
    try:
        from edge_ir.evaluator.actions.map import (
            NestedReductions,
            find_nested_reductions,
            map_action,
        )
    except ImportError:          # local fix for issue 2, not upstream yet
        return None

    space = res.iteration_space
    specs = list(einsum.specs)
    nested = find_nested_reductions(einsum.expression, specs, space.axes)
    if not nested:
        return None
    inner = next(_anonymous(einsum.expression, nested))
    empty = env.declarations[einsum.output_tensor].empty_value
    where = f"Einsum writing {einsum.output_tensor!r}"
    dropped = set().union(*(axes for _, axes in nested.values()))
    keep = [k for k, axis in enumerate(space.axes) if axis not in dropped]
    groups: dict = {}
    for p in space.points:
        groups.setdefault(tuple(p[k] for k in keep), []).append(p)

    def cell(got) -> dict:
        return {"present": got.present,
                "value": got.value if got.present else None}

    out: dict = {}
    for group in groups.values():
        rep = group[0]
        # The anonymous tensor itself, as the enclosing expression sees it:
        # the Map's values with the Reduce already applied.
        reduced = cell(map_action(
            inner, space.point_map(rep), rep, axes=space.axes, specs=specs,
            output_empty=empty, env=env, where=where,
            nested=NestedReductions(by_anon=nested, group=group)))
        for p in group:
            got = map_action(inner.expression, space.point_map(p), p,
                             axes=space.axes, specs=specs, output_empty=empty,
                             env=env, where=where)
            out[p] = {**cell(got), "reduced": reduced}
    return out


def _anonymous(expr, wanted):
    """The anonymous tensors of `expr` named in `wanted`, by identity."""
    if id(expr) in wanted:
        yield expr
    for side in ("lhs", "rhs", "expression"):
        child = getattr(expr, side, None)
        if child is not None:
            yield from _anonymous(child, wanted)


def _rank_values(expr) -> list:
    """Every rank expression an Einsum reads as a value, left to right."""
    kind = getattr(expr, "kind", None)
    if kind == "rank_value":
        return [expr]
    if kind == "binary":
        return _rank_values(expr.lhs) + _rank_values(expr.rhs)
    if kind == "anonymous":
        return _rank_values(expr.expression)
    return []


def _exec_record(rec: dict, node_json: dict, gen_tensors: set[str],
                 alias: dict) -> dict:
    """What the page's "how this value is computed" panel shows for one Einsum
    run: every iteration-space point, the operand cells it read, and what it
    produced -- all read off the evaluator's own result and the tensors before
    and after. Per-label values inside parentheses are not available from the
    evaluator yet (see docs/issues-for-edge-core-ir.md)."""
    from edge_ir.evaluator.iteration import input_projections
    from edge_ir.evaluator.projection import (
        einsum_projection,
        evaluate_rank_expression,
        project,
    )

    einsum, res, env = rec["einsum"], rec["result"], rec["env"]
    space = res.iteration_space
    out_name = einsum.output_tensor
    out_gen = out_name in gen_tensors
    before = rec["before"]
    decls = {d.name: d for d in env.declarations.values()}

    def read(proj, bound):
        coord = tuple(project(proj, bound, shape_env=env.shape_env,
                              registry=env.functions))
        cells = before.get(proj.tensor, {})
        present = coord in cells
        decl = decls.get(proj.tensor)
        empty = decl.empty_value if decl is not None else None
        if decl is not None and not decl.ranks:
            value = decl.value if decl.value is not None else cells.get((), empty)
            return {"tensor": alias.get(proj.tensor, proj.tensor), "coord": None,
                    "present": True, "value": value, "scalar": True}
        return {"tensor": alias.get(proj.tensor, proj.tensor),
                "coord": _key(coord, proj.tensor in gen_tensors),
                "ranks": [_rank_text(r.model_dump()) for r in proj.ranks],
                "present": present,
                "value": cells.get(coord) if present else None,
                "emptyValue": empty}

    # A case statement is evaluated arm by arm, each over the region of the
    # iteration space it claimed; every other Einsum is one "arm".
    is_cases = getattr(einsum.expression, "kind", None) == "cases"
    if is_cases:
        parts = [(k, arm.expression, res.arms[k])
                 for k, arm in enumerate(einsum.expression.arms)
                 if arm.expression is not None and res.arms[k] is not None]
    else:
        parts = [(None, einsum.expression, res)]

    points = []
    produced_keys = set()
    out_space = env.spaces.get(out_name)
    iter_vars: list[str] = []
    for arm_index, expression, res in parts:
        space = res.iteration_space
        iter_vars += [a for a in space.axes if a not in iter_vars]
        projections = list(input_projections(expression))
        rank_values = _rank_values(expression)
        for p in space.points:
            bound = space.point_map(p)
            proj = einsum_projection(list(einsum.output_ranks), bound, p,
                                     output_space=out_space,
                                     shape_env=env.shape_env,
                                     registry=env.functions)
            if not proj.defined:
                continue
            key = _key(tuple(proj.output_coord), out_gen)
            produced_keys.add(key)
            present = p in res.map_tmp
            points.append({
                "coord": key,
                "bind": {a: v for a, v in zip(space.axes, p)},
                "present": present,
                "value": res.map_tmp.get(p) if present else None,
                "prov": {"reads": [read(pr, bound) for pr in projections]
                         + [{"rank": _rank_text(rv.expr.model_dump()),
                             "scalar": True, "present": True,
                             "value": evaluate_rank_expression(
                                 rv.expr, bound, shape_env=env.shape_env,
                                 registry=env.functions)}
                            for rv in rank_values]},
            })
            if arm_index is not None:
                points[-1]["arm"] = arm_index
            if rec.get("inner_map") is not None:
                inner = rec["inner_map"][p]
                points[-1]["afterMap"] = {k: inner[k]
                                          for k in ("present", "value")}
                points[-1]["afterReduce"] = inner["reduced"]
    after_out = _flat({out_name: rec["after"].get(out_name, {})}, gen_tensors,
                      alias, {out_name: rec["written_gen"]})
    shown_out = alias.get(out_name, out_name)
    result = {k: v for k, v in after_out.get(shown_out, {}).items()
              if k in produced_keys}
    reduce_spec = next((s for s in node_json.get("specs", [])
                        if s.get("kind") == "reduce"), None)
    decl = decls.get(out_name)
    record_extra = {}
    if is_cases:
        from edge_workbench.cascade_shape import arm_condition

        literals = {d.name: d.value for d in decls.values()
                    if not d.ranks and d.value is not None}
        record_extra["arms"] = [
            {"condition": arm_condition(arm.model_dump(), literals),
             "empty": arm.expression is None,
             "points": (len(res_k.iteration_space)
                        if (res_k := rec["result"].arms[k]) is not None else 0)}
            for k, arm in enumerate(einsum.expression.arms)]
    return {
        **record_extra,
        "einsum": node_json,
        "output": shown_out,
        "iterVars": iter_vars,
        "points": points,
        "result": result,
        "reduceSpec": reduce_spec,
        "outEmpty": decl.empty_value if decl is not None else None,
    }


def _populate_record(rec: dict, node_json: dict, gen_tensors: set[str],
                     alias: dict, cascade: dict, schedule: dict | None) -> dict | None:
    """What each round of a Populate with a mutable rank did, as the
    driver recorded it (`PopulateRound`): nothing here is computed, only
    renamed for the page.

    A round (paper, Inset 4) is one point of the iteration space at which
    Populate runs: one incoming Reduce Temporary element and the mutable
    fiber it belongs to. Per round: the fiber's pre-state S, the write set W
    (with the value the compute operator produced), the delete set D, the
    fiber afterwards, and whether the evaluator checked W ∩ (dom(S) ∪ D) = ∅
    against the pre-state. `Loc`, every location of a fiber, is listed once
    per fiber. None when the evaluator recorded no rounds (assignment, or an
    edge-core-ir without the recording).
    """
    rounds = rec.get("populate_rounds")
    if not rounds:
        return None
    einsum = rec["einsum"]
    gen_first = einsum.output_tensor in gen_tensors
    spec = next((s for s in node_json.get("specs", [])
                 if s.get("kind") == "populate"), {})
    name = (spec.get("coord_op") or {}).get("name")
    rule = (cascade.get("selectors") or {}).get(name)

    def key(coord) -> str:
        return _key(tuple(coord), gen_first)

    # A value in a tensor declared Boolean is shown as true, as `_snapshot`
    # shows it; the incoming element's own value is kept as recorded, since a
    # ranking operator ranks by it.
    decl = rec["env"].declarations.get(einsum.output_tensor)
    boolean = getattr(getattr(decl, "data_type", None), "name", None) == "bool"

    def cells(state: dict) -> dict:
        return {key(c): (v if isinstance(v, bool) or not boolean else True)
                for c, v in state.items()}

    fibers: dict[str, dict] = {}
    out = []
    for r in rounds:
        # The fiber is named by its first location with the mutable
        # coordinates starred, in the output's own rank order.
        mutable = set(r.mutable_positions)
        shown = ["*" if k in mutable else str(c)
                 for k, c in enumerate(r.locations[0])]
        fk = ",".join(shown[1:] if gen_first else shown)
        fibers.setdefault(fk, {"loc": [key(c) for c in r.locations],
                               "rounds": []})
        fibers[fk]["rounds"].append(len(out))
        acted = [[key(c), a] for c, a in r.write_del if a != "None"]
        out.append({
            "point": dict(zip(r.axes, r.point)),
            "coord": key(r.output_coord),
            "value": r.value,
            "fiber": fk,
            "pre": cells(r.pre_state),
            "writeDel": acted,
            "writeDelSize": len(r.write_del),
            "W": cells(r.writes),
            "D": [key(c) for c in r.deletes],
            "post": cells(r.post_state),
            "checked": bool(r.constraint_checked),
        })
    ranks = [_rank_text(x) for x in node_json.get("output_ranks", [])]
    positions = sorted(rounds[0].mutable_positions)
    return {
        "operator": name,
        "compute": (spec.get("compute_op") or {}).get("name")
        or (spec.get("compute_op") or {}).get("symbol"),
        "mutable": [ranks[k] for k in positions if k < len(ranks)],
        # A ranking operator is the algorithm's; any other name is a free
        # choice, run as select-any: the schedule's order decides.
        "free": isinstance(rule, dict) and rule.get("rule") == "seeded",
        "schedule": schedule or {"kind": "sequential"},
        "fibers": fibers,
        "rounds": out,
    }


def _steps(program: dict, cascade: dict, records: list[dict], result,
           parsed=None, schedule: dict | None = None) -> dict:
    """The run as the page's steps, one per written Einsum executed.

    A record is matched to its IR node by identity, not by position: with a
    conditional cascade or an inner cascade (edge-core-ir local patches) a
    generation does not run every node, or runs some of them many times, so
    "the k-th record of generation g" names nothing.
    """
    from edge_workbench.cascade_shape import flat_nodes, placement

    gen = cascade.get("generationalRank", "I")
    gen_tensors = _gen_ranks(program, gen)
    alias = cascade.get("displayNames", {}) or {}
    init_nodes = program.get("initialization", {}).get("einsums", [])
    body = flat_nodes(program)
    where = placement(program)
    owner: dict[int, str] = {}
    for label, idx in (cascade.get("labels") or {}).items():
        for k in (idx if isinstance(idx, list) else [idx]):
            owner[int(k)] = label

    executed: dict[str, int] = {}
    steps: list[dict] = []
    n_init = len(init_nodes)

    written: dict[str, Any] = {}
    for rec in records:
        name = rec["einsum"].output_tensor
        if name in gen_tensors and isinstance(rec["written_gen"], int):
            written[name] = rec["written_gen"]
        rec["written"] = dict(written)

    init_recs, body_recs = records[:n_init], records[n_init:]
    for k, _ in enumerate(init_recs):
        executed[f"init:{k}"] = executed.get(f"init:{k}", 0) + 1
    last = init_recs[-1]["after"] if init_recs else (
        body_recs[0]["before"] if body_recs else {})
    steps.append({"id": 0, "einsum": cascade.get("initLabel", "init"),
                  "iteration": None, "output": None,
                  "state": _flat(last, gen_tensors, alias,
                                 init_recs[-1]["written"] if init_recs else None)})

    # Which flat node each record ran. Without the parsed program (an older
    # caller) the body is flat and records come in node order per generation.
    if parsed is not None:
        from edge_ir.ir.einsum import flatten

        index_of = {id(e): k for k, e in enumerate(flatten(parsed.main_edge.cascade))}
        node_of = [index_of[id(rec["einsum"])] for rec in body_recs]
    else:
        node_of = [k % len(body) for k in range(len(body_recs))]

    outer = (where[0]["ranks"][0] if where and where[0]["ranks"]
             else gen.lower())
    generations = result.trace.generations
    # A multi-output case statement over macros is not an Einsum, so nothing
    # records it; the step that shows WHICH macro a generation ran is made
    # here, before the first Einsum of the arm, with the state as the
    # condition saw it.
    from edge_workbench.cascade_shape import (arm_condition, conditionals,
                                              literal_values)
    statement = {v["conditional"]: label for label, v in
                 (cascade.get("conditionals") or {}).items()}
    branches = conditionals(program)
    literals = literal_values(program)
    chosen: set = set()
    k = 0
    while k < len(body_recs):
        for arm in where[node_of[k]]["arms"]:
            at = (arm["conditional"],
                  tuple(sorted(body_recs[k]["pinned"].items())))
            if arm["conditional"] not in statement or at in chosen:
                continue
            chosen.add(at)
            pinned = body_recs[k]["pinned"]
            before = (body_recs[k - 1]["written"] if k else
                      init_recs[-1]["written"] if init_recs else None)
            taken = branches[arm["conditional"]]["arms"][arm["arm"]]
            steps.append({
                "id": len(steps), "einsum": statement[arm["conditional"]],
                "iteration": pinned.get(outer,
                                        next(iter(pinned.values()), None)),
                "output": None,
                "state": _flat(body_recs[k]["before"], gen_tensors, alias,
                               before),
                "arm": arm,
                "choice": {"macro": arm.get("macro"), "arm": arm["arm"],
                           "of": arm["of"],
                           "condition": arm_condition(taken, literals)}})
        label = owner.get(node_of[k], f"node{node_of[k]}")
        j = k
        # One written Einsum lowered to several consecutive IR nodes (an
        # older lowering of `cases`) is one step: its last node's state.
        while (j + 1 < len(body_recs) and owner.get(node_of[j + 1]) == label
               and node_of[j + 1] == node_of[j] + 1
               and body_recs[j + 1]["pinned"] == body_recs[k]["pinned"]):
            j += 1
        for n in range(k, j + 1):
            key = str(node_of[n])
            executed[key] = executed.get(key, 0) + 1
            # A case statement's arms: one tally each, counting the runs in
            # which the arm claimed at least one point (coverage.arm_key).
            for a, arm in enumerate(getattr(body_recs[n]["result"], "arms", [])
                                    or []):
                if arm is not None and len(arm.iteration_space):
                    key = f"{node_of[n]}#arm{a}"
                    executed[key] = executed.get(key, 0) + 1
        rec = body_recs[j]
        out = rec["einsum"].output_tensor
        pinned = rec["pinned"]
        step = {"id": len(steps), "einsum": label,
                "iteration": pinned.get(outer,
                                        next(iter(pinned.values()), None)),
                "output": alias.get(out, out),
                "state": _flat(rec["after"], gen_tensors, alias,
                               rec["written"])}
        inner = {v: c for v, c in pinned.items() if v != outer}
        if inner:
            # The generations of the inner cascades this Einsum ran in.
            step["inner"] = inner
        arms = where[node_of[j]]["arms"]
        if arms:
            # Which arm of a conditional cascade this is, so the page can say
            # which one this generation took.
            step["arm"] = arms[-1]
        if j == k:
            step["exec"] = _exec_record(rec, body[node_of[k]], gen_tensors, alias)
            populate = _populate_record(rec, body[node_of[k]], gen_tensors,
                                        alias, cascade, schedule)
            if populate:
                step["populate"] = populate
        steps.append(step)
        k = j + 1

    final = body_recs[-1]["after"] if body_recs else last
    steps.append({"id": len(steps), "einsum": cascade.get("stopLabel", "stop"),
                  "iteration": (steps[-1]["iteration"] if len(steps) > 1
                                else None),
                  "output": None,
                  "state": _flat(final, gen_tensors, alias,
                                 body_recs[-1]["written"] if body_recs else None)})
    return {"generations": generations, "steps": steps, "executed": executed}


def _program_file(spec: Path) -> Path:
    """The IR program in an algorithm's spec directory.

    Matched by the `*_program.json` convention; exactly one is required,
    because two would make the choice silent.
    """
    candidates = sorted(spec.glob("*_program.json"))
    if len(candidates) != 1:
        raise DriverError(
            f"expected exactly one *_program.json in {spec}, found "
            f"{[p.name for p in candidates]}. The IR program is identified by "
            f"the `_program.json` suffix; other files in spec/ are the "
            f"algorithm's own."
        )
    return candidates[0]
