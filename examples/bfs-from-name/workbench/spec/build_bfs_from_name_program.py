"""Construct the CLRS BFS (depths and parents) program in IR form; dump JSON.

Source: examples/bfs-from-name/einsum.edge, E01-E07 and an occupancy stop.
Literals in operand position are zero-rank tensors with a `value` and
empty_value None, so they are always present.
"""

from __future__ import annotations

import sys
from typing import Any

from edge_ir.ir.actions import MapSpec, PopulateSpec, ReduceSpec
from edge_ir.ir.einsum import Einsum, NestedCascade, StoppingCondition
from edge_ir.ir.expr import (
    AnonymousTensor,
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
    CoordinateOp,
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


def in_source(var: str) -> SetMembership:
    return SetMembership(member=rv(var), coord_set=CoordSetName(name="source"),
                         negated=False)


V = "|V|"


def build_bfs_from_name() -> Program:
    inf = float("inf")
    declarations = [
        decl("G", [("S", V), ("D", V)], "int", 0),
        decl("F", [("I", None), ("S", V)], "int", inf),
        decl("T", [("I", None), ("D", V)], "int", inf),
        decl("P", [("I", None), ("D", V)], "bool", False),
        decl("ParentCand", [("I", None), ("S", V), ("D", V)], "int", 0),
        decl("NewParent", [("I", None), ("S", V), ("D", V)], "int", 0),
        decl("Parent", [("I", None), ("S", V), ("D", V)], "int", 0),
        decl("Depth", [("I", None), ("D", V)], "int", inf),
        # Literals: always present (empty None), each carrying its value.
        decl("Lit_0", [], "int", None, value=0),
        decl("Lit_True", [], "bool", None, value=True),
        decl("One", [], "int", None, value=1),
    ]

    init = Initialization(einsums=[
        # F_{0, s : s in source} = 0
        Einsum(output_tensor="F", output_ranks=[rc(0), rv("s")],
               expression=inp("Lit_0"), specs=[], predicates=[in_source("s")]),
        # P_{0, d : d in source} = True
        Einsum(output_tensor="P", output_ranks=[rc(0), rv("d")],
               expression=inp("Lit_True"), specs=[],
               predicates=[in_source("d")]),
        # Depth_{0, d : d in source} = 0
        Einsum(output_tensor="Depth", output_ranks=[rc(0), rv("d")],
               expression=inp("Lit_0"), specs=[], predicates=[in_source("d")]),
    ])

    einsums = [
        # E01: T_{i,d} = G_{s,d} . F_{i,s} :: /\_s +(∩) \/_s min(∪)
        Einsum(
            output_tensor="T",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("G", rv("s"), rv("d")),
                                 rhs=inp("F", rv("i"), rv("s"))),
            specs=[map_spec(1, "+", "intersect", ["s"]),
                   reduce_spec(1, "min", "union", ["s"])],
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
        # E03: ParentCand_{i,s,d} = (G_{s,d} .^1 F_{i,s})_{i,s,d} .^2 F_{i+1,d}
        #      :: /\^1 <-(∩) /\^2 <-(∩)
        Einsum(
            output_tensor="ParentCand",
            output_ranks=[rv("i"), rv("s"), rv("d")],
            expression=BinaryApp(
                label=2,
                lhs=AnonymousTensor(
                    expression=BinaryApp(label=1,
                                         lhs=inp("G", rv("s"), rv("d")),
                                         rhs=inp("F", rv("i"), rv("s"))),
                    ranks=[rv("i"), rv("s"), rv("d")],
                ),
                rhs=inp("F", i_plus_one(), rv("d")),
            ),
            specs=[map_spec(1, "take_left", "intersect"),
                   map_spec(2, "take_left", "intersect")],
        ),
        # E04: NewParent_{i,s*,d} = ParentCand_{i,s,d} :: <<<_{s*} 1(pick-parent)
        #      Populate attaches to a binary in the IR: a transparent
        #      take_left(take_left) Map against One passes ParentCand through.
        Einsum(
            output_tensor="NewParent",
            output_ranks=[rv("i"), rv("s"), rv("d")],
            expression=BinaryApp(label=1,
                                 lhs=inp("ParentCand", rv("i"), rv("s"), rv("d")),
                                 rhs=inp("One")),
            specs=[
                map_spec(1, "take_left", "take_left"),
                PopulateSpec(label=1, rank_list=["s"],
                             compute_op=compute("identity"),
                             coord_op=CoordinateOp(name="pick-parent")),
            ],
        ),
        # E05: Parent_{i+1,s,d} = Parent_{i,s,d} . NewParent_{i,s,d} :: /\_d <<(∪)
        Einsum(
            output_tensor="Parent",
            output_ranks=[i_plus_one(), rv("s"), rv("d")],
            expression=BinaryApp(label=1,
                                 lhs=inp("Parent", rv("i"), rv("s"), rv("d")),
                                 rhs=inp("NewParent", rv("i"), rv("s"), rv("d"))),
            specs=[map_spec(1, "update", "union", ["d"])],
        ),
        # E06: P_{i+1,d} = P_{i,d} . F_{i+1,d} :: /\_d OR(∪)
        Einsum(
            output_tensor="P",
            output_ranks=[i_plus_one(), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("P", rv("i"), rv("d")),
                                 rhs=inp("F", i_plus_one(), rv("d"))),
            specs=[map_spec(1, "OR", "union", ["d"])],
        ),
        # E07: Depth_{i+1,d} = Depth_{i,d} . F_{i+1,d} :: /\_d <<(∪)
        Einsum(
            output_tensor="Depth",
            output_ranks=[i_plus_one(), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("Depth", rv("i"), rv("d")),
                                 rhs=inp("F", i_plus_one(), rv("d"))),
            specs=[map_spec(1, "update", "union", ["d"])],
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
    sys.stdout.write(build_bfs_from_name().model_dump_json(indent=2))
