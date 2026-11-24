"""Populate, round by round (paper Inset 4), as the driver records it.

The workbench records each round by wrapping the coordinate operator it
hands the evaluator (`driver/run.py`, `_watching_populate`), so edge-core-ir
is not changed for it (docs/evaluator-needs.md). Moved from edge-core-ir's
`tests/test_populate_rounds.py` on 2026-11-19, with the recording now ours.
"""

from __future__ import annotations

from edge_workbench.spec_check import _import_edge_ir

_import_edge_ir()

from edge_ir.evaluator import build_environment, evaluate_einsum  # noqa: E402
from edge_ir.evaluator.order import ShuffledSchedule  # noqa: E402
from edge_ir.ir.actions import PopulateSpec  # noqa: E402
from edge_ir.ir.einsum import Einsum, NestedCascade  # noqa: E402
from edge_ir.ir.expr import InputTensor, RankVariable, TensorProjection  # noqa: E402
from edge_ir.ir.op import CoordinateOp, UserDefinedComputeOp  # noqa: E402
from edge_ir.ir.program import Initialization, MainEdge, Program  # noqa: E402
from edge_ir.ir.tensor import BuiltinDataType, RankDeclaration, TensorDeclaration  # noqa: E402

from edge_workbench.driver.run import _finish_rounds, _watching_populate  # noqa: E402
from edge_workbench.operators import base_registry  # noqa: E402

SHAPE = 5
A = {(0,): 7, (1,): 3, (2,): 9, (3,): 3}


def _decl(name):
    return TensorDeclaration(name=name, ranks=[RankDeclaration(name="M", shape=SHAPE)],
                             data_type=BuiltinDataType(name="int"), empty_value=0)


def _setup(coord_op, a, *, mutable=True):
    """``Z_{m*} = A_m :: populate_{m*} 1(coord_op)`` over one fiber."""
    einsum = Einsum(
        output_tensor="Z",
        output_ranks=[RankVariable(name="m")],
        expression=InputTensor(proj=TensorProjection(tensor="A", ranks=[RankVariable(name="m")])),
        specs=[PopulateSpec(rank_list=["m"], compute_op=UserDefinedComputeOp(name="identity"),
                            coord_op=CoordinateOp(name=coord_op))] if mutable else [],
    )
    program = Program(declarations=[_decl("Z"), _decl("A")],
                      initialization=Initialization(einsums=[]),
                      main_edge=MainEdge(cascade=NestedCascade(einsums=[einsum])))
    env = build_environment(program, inputs={"A": a}, shape_env={},
                            functions=base_registry())
    return einsum, env


def _record(einsum, env, schedule=None):
    with _watching_populate(einsum, env) as rounds:
        evaluate_einsum(einsum, env=env, schedule=schedule)
    _finish_rounds(rounds, env.tensors["Z"])
    return rounds


def _holds(r):
    w, d, dom = set(r.writes), set(r.deletes), set(r.pre_state)
    return not (w & (dom | d))


def test_recording_changes_nothing_and_restores_the_operator():
    einsum, env = _setup("select-min-val", A)
    evaluate_einsum(einsum, env=env)
    einsum2, env2 = _setup("select-min-val", A)
    from edge_ir.udf import UdfCategory

    before = env2.functions.impl(UdfCategory.COORDINATE, "select-min-val")
    assert _record(einsum2, env2)
    assert env2.functions.impl(UdfCategory.COORDINATE, "select-min-val") is before
    assert dict(env.tensors["Z"].items()) == dict(env2.tensors["Z"].items())


def test_assignment_records_no_rounds():
    einsum, env = _setup("select-min-val", A, mutable=False)
    assert _record(einsum, env) == []


def test_select_min_val_round_by_round():
    einsum, env = _setup("select-min-val", A)
    rounds = _record(einsum, env)
    assert [r.output_coord for r in rounds] == [(0,), (1,), (2,), (3,)]
    assert [r.value for r in rounds] == [7, 3, 9, 3]
    assert all(r.fiber_key == () and len(r.locations) == SHAPE for r in rounds)
    first, second, third, fourth = rounds
    assert (first.pre_state, first.writes, first.deletes) == ({}, {(0,): 7}, [])
    assert first.post_state == {(0,): 7}
    assert second.pre_state == {(0,): 7}
    assert (second.writes, second.deletes) == ({(1,): 3}, [(0,)])
    assert second.post_state == {(1,): 3}
    assert (third.writes, third.deletes, third.post_state) == ({}, [], {(1,): 3})
    # A tie on the value is broken by the smaller coordinate (issue 4).
    assert (fourth.writes, fourth.deletes, fourth.post_state) == ({}, [], {(1,): 3})
    for before, after in zip(rounds, rounds[1:]):
        assert after.pre_state == before.post_state
    assert all(r.constraint_checked and _holds(r) for r in rounds)
    assert dict(env.tensors["Z"].items()) == rounds[-1].post_state
    assert all(len(r.write_del) == SHAPE for r in rounds)


def test_select_any_keeps_the_first_arrival_of_the_schedule():
    kept = set()
    for seed in range(8):
        einsum, env = _setup("select-any", A)
        rounds = _record(einsum, env, ShuffledSchedule(seed=seed))
        assert sorted(r.output_coord for r in rounds) == sorted(A)
        assert rounds[0].writes == {rounds[0].output_coord: rounds[0].value}
        for r in rounds[1:]:
            assert (r.writes, r.deletes) == ({}, [])
            assert r.pre_state == rounds[0].post_state == r.post_state
        assert all(r.constraint_checked and _holds(r) for r in rounds)
        kept.add(rounds[0].output_coord)
    assert len(kept) > 1
