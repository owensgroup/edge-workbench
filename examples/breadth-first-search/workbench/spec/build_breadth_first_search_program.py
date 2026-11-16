"""Construct the depth-tracking BFS program in IR form; dump JSON to stdout.

Source: examples/breadth-first-search/einsum.edge (three Einsums, E01-E03,
and an occupancy stop). Literals in operand position (`0` and `True` in the
initialization, `0` in the stop) are zero-rank tensors with a `value` and
empty_value None, so they are always present.
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
    UnaryApp,
)
from edge_ir.ir.op import (
    BuiltinComputeOp,
    BuiltinMergeOp,
    BuiltinUnaryOp,
    UserDefinedComputeOp,
)
from edge_ir.ir.predicate import SetMembership
from edge_ir.ir.program import Initialization, MainEdge, Program
from edge_ir.ir.stopping import Comparison, PropertyApp, TensorProjectionValue
from edge_ir.ir.tensor import (
    BuiltinDataType,
    CoordSetName,
    RankDeclaration,
    TensorDeclaration,
)


def rv(name: str) -> RankVariable:
    return RankVariable(name=name)


def rc(value: int | str) -> RankConstantLiteral:
    return RankConstantLiteral(value=value)


def i_plus_one() -> RankArith:
    return RankArith(op="+", lhs=rv("i"), rhs=rc(1))


def proj(tensor: str, *ranks: Any) -> TensorProjection:
    return TensorProjection(tensor=tensor, ranks=list(ranks))


def inp(tensor: str, *ranks: Any) -> InputTensor:
    return InputTensor(proj=proj(tensor, *ranks))


def compute(name: str) -> BuiltinComputeOp | UserDefinedComputeOp:
    if name in {"+", "-", "*", "/"}:
        return BuiltinComputeOp(symbol=name)  # type: ignore[arg-type]
    return UserDefinedComputeOp(name=name)


def merge(name: str) -> BuiltinMergeOp:
    return BuiltinMergeOp(symbol=name)  # type: ignore[arg-type]


def map_spec(label, compute_name, merge_name, rank_list=None) -> MapSpec:
    return MapSpec(label=label, rank_list=rank_list,
                   compute_op=compute(compute_name), merge_op=merge(merge_name))


def reduce_spec(label, compute_name, merge_name, rank_list=None) -> ReduceSpec:
    return ReduceSpec(label=label, rank_list=rank_list,
                      compute_op=compute(compute_name), merge_op=merge(merge_name))


def decl(name, ranks, dtype, empty, value=None) -> TensorDeclaration:
    d = TensorDeclaration(
        name=name,
        ranks=[RankDeclaration(name=r, shape=s) for r, s in ranks],
        data_type=BuiltinDataType(name=dtype),  # type: ignore[arg-type]
        empty_value=empty,
    )
    return d.model_copy(update={"value": value}) if value is not None else d


def in_id(var: str) -> SetMembership:
    return SetMembership(member=rv(var), coord_set=CoordSetName(name="id"),
                         negated=False)


def build_breadth_first_search() -> Program:
    declarations = [
        decl("G", [("S", "|V|"), ("D", "|V|")], "int", 0),
        decl("F", [("I", None), ("S", "|V|")], "int", float("inf")),
        decl("T", [("I", None), ("D", "|V|")], "int", float("inf")),
        decl("P", [("I", None), ("D", "|V|")], "bool", False),
        # Literals: always present (empty None), each carrying its value.
        decl("Lit_0", [], "int", None, value=0),
        decl("Lit_True", [], "bool", None, value=True),
    ]

    init = Initialization(einsums=[
        # F_{0, s : s in id} = 0
        Einsum(output_tensor="F", output_ranks=[rc(0), rv("s")],
               expression=inp("Lit_0"), specs=[], predicates=[in_id("s")]),
        # P_{0, d : d in id} = True
        Einsum(output_tensor="P", output_ranks=[rc(0), rv("d")],
               expression=inp("Lit_True"), specs=[], predicates=[in_id("d")]),
    ])

    einsums = [
        # E01: T_{i,d} = G_{s,d} . F_{i,s} :: /\_s +(∩) \/_s ANY(∪)
        Einsum(
            output_tensor="T",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("G", rv("s"), rv("d")),
                                 rhs=inp("F", rv("i"), rv("s"))),
            specs=[map_spec(1, "+", "intersect", ["s"]),
                   reduce_spec(1, "ANY", "union", ["s"])],
        ),
        # E02: F_{i+1,d} = T_{i,d} . not P_{i,d} :: /\_d <-(∩)
        Einsum(
            output_tensor="F",
            output_ranks=[i_plus_one(), rv("d")],
            expression=BinaryApp(
                label=1,
                lhs=inp("T", rv("i"), rv("d")),
                rhs=UnaryApp(op=BuiltinUnaryOp(symbol="not"),
                             operand=inp("P", rv("i"), rv("d"))),
            ),
            specs=[map_spec(1, "take_left", "intersect", ["d"])],
        ),
        # E03: P_{i+1,d} = P_{i,d} . F_{i+1,d} :: /\_d OR(∪)
        Einsum(
            output_tensor="P",
            output_ranks=[i_plus_one(), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("P", rv("i"), rv("d")),
                                 rhs=inp("F", i_plus_one(), rv("d"))),
            specs=[map_spec(1, "OR", "union", ["d"])],
        ),
    ]

    # <> : ||F_{i+1}|| == 0
    stop = StoppingCondition(
        rank_variable="i",
        predicate=Comparison(
            lhs=PropertyApp(name="occupancy", pinned_rank_variables=["i"],
                            operands=[proj("F", i_plus_one())]),
            op="==",
            rhs=TensorProjectionValue(proj=proj("Lit_0")),
        ),
    )

    return Program(
        declarations=declarations,
        initialization=init,
        main_edge=MainEdge(cascade=NestedCascade(einsums=einsums,
                                                 stopping_conditions=[stop])),
    )


if __name__ == "__main__":
    sys.stdout.write(build_breadth_first_search().model_dump_json(indent=2))
