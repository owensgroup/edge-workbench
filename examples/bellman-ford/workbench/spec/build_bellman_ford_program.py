"""Construct the Bellman-Ford (SSSP) program in IR form, dump JSON to stdout.

Einsum IDs E01-E04 match einsum.edge line for line. Each is one IR Einsum
writing the tensor the spec writes; no intermediate is introduced.

The spec names no hyphenated operator, so the default registry covers it and
there is no functions file.
"""

from __future__ import annotations

import sys
from typing import Any

from edge_ir.ir.actions import MapSpec, ReduceSpec
from edge_ir.ir.einsum import Einsum, NestedCascade, StoppingCondition
from edge_ir.ir.expr import (
    BinaryApp,
    InputTensor,
    RankArith,
    RankConstantLiteral,
    RankVariable,
    TensorProjection,
)
from edge_ir.ir.op import BuiltinComputeOp, BuiltinMergeOp, UserDefinedComputeOp
from edge_ir.ir.predicate import SetMembership
from edge_ir.ir.program import Initialization, MainEdge, Program
from edge_ir.ir.stopping import Comparison, TensorProjectionValue
from edge_ir.ir.tensor import (
    BuiltinDataType,
    CoordSetName,
    RankDeclaration,
    TensorDeclaration,
)


def rv(name: str) -> RankVariable:
    return RankVariable(name=name)


def rc(value: int) -> RankConstantLiteral:
    return RankConstantLiteral(value=value)


def i_plus_one() -> RankArith:
    return RankArith(op="+", lhs=rv("i"), rhs=rc(1))


def proj(tensor: str, *ranks: Any) -> TensorProjection:
    return TensorProjection(tensor=tensor, ranks=list(ranks))


def inp(tensor: str, *ranks: Any) -> InputTensor:
    return InputTensor(proj=proj(tensor, *ranks))


def compute(name: str) -> BuiltinComputeOp | UserDefinedComputeOp:
    if name in {"+", "-", "*", "/"}:
        return BuiltinComputeOp(symbol=name)
    return UserDefinedComputeOp(name=name)


def map_spec(label: int, c: str, m: str, ranks: list[str]) -> MapSpec:
    return MapSpec(label=label, rank_list=ranks, compute_op=compute(c),
                   merge_op=BuiltinMergeOp(symbol=m))


def reduce_spec(label: int, c: str, m: str, ranks: list[str]) -> ReduceSpec:
    return ReduceSpec(label=label, rank_list=ranks, compute_op=compute(c),
                      merge_op=BuiltinMergeOp(symbol=m))


def decl(name: str, ranks: list[tuple[str, str | None]], dtype: str,
         empty: Any) -> TensorDeclaration:
    return TensorDeclaration(
        name=name,
        ranks=[RankDeclaration(name=r, shape=s) for r, s in ranks],
        data_type=BuiltinDataType(name=dtype),
        empty_value=empty,
    )


def build_bellman_ford() -> Program:
    inf = float("inf")
    declarations = [
        decl("G", [("S", "|V|"), ("D", "|V|")], "int", inf),
        decl("C", [("I", None), ("S", "|V|")], "bool", False),
        decl("N", [("I", None), ("D", "|V|")], "int", inf),
        decl("NewlyRelaxed", [("I", None), ("D", "|V|")], "int", inf),
        decl("D", [("I", None), ("S", "|V|")], "int", inf),
        # The literal 0 of the initialization, as a zero-rank tensor.
        TensorDeclaration(name="Lit_0", ranks=[],
                          data_type=BuiltinDataType(name="int"),
                          empty_value=None, value=0),
    ]

    # D_{0, s : s in root_id} = 0 -- root_id is a host-supplied coordinate
    # set over rank S.
    init = Initialization(einsums=[
        Einsum(
            output_tensor="D",
            output_ranks=[rc(0), rv("s")],
            expression=inp("Lit_0"),
            specs=[],
            predicates=[SetMembership(member=rv("s"),
                                      coord_set=CoordSetName(name="root_id"),
                                      negated=False)],
        ),
    ])

    einsums = [
        # E01: N_{i, d} = G_{s, d} . D_{i, s} :: /\_s +(∩) \/_s min(∪)
        Einsum(
            output_tensor="N",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("G", rv("s"), rv("d")),
                                 rhs=inp("D", rv("i"), rv("s"))),
            specs=[map_spec(1, "+", "intersect", ["s"]),
                   reduce_spec(1, "min", "union", ["s"])],
        ),
        # E02: C_{i, d} = N_{i, d} . D_{i, d} :: /\_d <(∪)
        Einsum(
            output_tensor="C",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("N", rv("i"), rv("d")),
                                 rhs=inp("D", rv("i"), rv("d"))),
            specs=[map_spec(1, "lt", "union", ["d"])],
        ),
        # E03: NewlyRelaxed_{i, d} = C_{i, d} . N_{i, d} :: /\_d ->(∩)
        Einsum(
            output_tensor="NewlyRelaxed",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("C", rv("i"), rv("d")),
                                 rhs=inp("N", rv("i"), rv("d"))),
            specs=[map_spec(1, "take_right", "intersect", ["d"])],
        ),
        # E04: D_{i+1, d} = D_{i, d} . NewlyRelaxed_{i, d} :: /\_d <<(∪)
        Einsum(
            output_tensor="D",
            output_ranks=[i_plus_one(), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("D", rv("i"), rv("d")),
                                 rhs=inp("NewlyRelaxed", rv("i"), rv("d"))),
            specs=[map_spec(1, "update", "union", ["d"])],
        ),
    ]

    # <> : D_{i+1} == D_i -- convergence, every point equal.
    stopping = StoppingCondition(
        rank_variable="i",
        predicate=Comparison(
            lhs=TensorProjectionValue(proj=proj("D", i_plus_one())),
            op="==",
            rhs=TensorProjectionValue(proj=proj("D", rv("i"))),
        ),
    )

    return Program(
        declarations=declarations,
        initialization=init,
        main_edge=MainEdge(cascade=NestedCascade(einsums=einsums,
                                                 stopping_conditions=[stopping])),
    )


if __name__ == "__main__":
    sys.stdout.write(build_bellman_ford().model_dump_json(indent=2))
