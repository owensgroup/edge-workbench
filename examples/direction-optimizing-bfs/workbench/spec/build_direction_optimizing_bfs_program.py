"""Construct the top-down DO-BFS program in IR form, dump JSON to stdout.

Einsum IDs E01-E08 match einsum.edge line for line. `n` in the initialization
is the source vertex: the host supplies it as the coordinate set root_id.
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


def rc(value: int) -> RankConstantLiteral:
    return RankConstantLiteral(value=value)


def i_plus_one() -> RankArith:
    return RankArith(op="+", lhs=rv("i"), rhs=rc(1))


def proj(tensor: str, *ranks: Any) -> TensorProjection:
    return TensorProjection(tensor=tensor, ranks=list(ranks))


def inp(tensor: str, *ranks: Any) -> InputTensor:
    return InputTensor(proj=proj(tensor, *ranks))


def compute(name: str) -> UserDefinedComputeOp:
    return UserDefinedComputeOp(name=name)


def map_spec(label: int, c: str, m: str, ranks: list[str]) -> MapSpec:
    return MapSpec(label=label, rank_list=ranks, compute_op=compute(c),
                   merge_op=BuiltinMergeOp(symbol=m))


def reduce_spec(label: int, c: str, m: str, ranks: list[str]) -> ReduceSpec:
    return ReduceSpec(label=label, rank_list=ranks, compute_op=compute(c),
                      merge_op=BuiltinMergeOp(symbol=m))


def decl(name: str, ranks: list[tuple[str, str | None]]) -> TensorDeclaration:
    return TensorDeclaration(
        name=name,
        ranks=[RankDeclaration(name=r, shape=s) for r, s in ranks],
        data_type=BuiltinDataType(name="bool"),
        empty_value=False,
    )


def literal(name: str, dtype: str, value: Any) -> TensorDeclaration:
    return TensorDeclaration(name=name, ranks=[],
                             data_type=BuiltinDataType(name=dtype),
                             empty_value=None, value=value)


def source(*member: RankVariable) -> list[SetMembership]:
    return [SetMembership(member=rv("n"), coord_set=CoordSetName(name="root_id"),
                          negated=False)]


def build_direction_optimizing_bfs() -> Program:
    vertex = "|V|"
    declarations = [
        decl("G", [("S", vertex), ("D", vertex)]),
        decl("F", [("I", None), ("S", vertex)]),
        decl("Tree", [("I", None), ("S", vertex), ("D", vertex)]),
        decl("Nei", [("I", None), ("D", vertex)]),
        decl("Visited", [("I", None), ("D", vertex)]),
        decl("NV", [("I", None), ("D", vertex)]),
        decl("NeiNV", [("I", None), ("D", vertex)]),
        decl("CandTree", [("I", None), ("S", vertex), ("D", vertex)]),
        decl("Temp", [("I", None), ("S", vertex), ("D", vertex)]),
        literal("Lit_True", "bool", True),
        literal("Lit_0", "int", 0),
    ]

    # F_{i,s} = False and Tree_{i,s,d} = False are the declared empty values,
    # so no Einsum writes them.
    init = Initialization(einsums=[
        Einsum(output_tensor="F", output_ranks=[rc(0), rv("n")],
               expression=inp("Lit_True"), specs=[], predicates=source()),
        Einsum(output_tensor="Tree", output_ranks=[rc(0), rv("n"), rv("n")],
               expression=inp("Lit_True"), specs=[], predicates=source()),
    ])

    einsums = [
        # E01: Nei_{i, d} = G_{s, d} . F_{i, s} :: /\_s AND(∩) \/_s OR(∪)
        Einsum(
            output_tensor="Nei",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("G", rv("s"), rv("d")),
                                 rhs=inp("F", rv("i"), rv("s"))),
            specs=[map_spec(1, "AND", "intersect", ["s"]),
                   reduce_spec(1, "OR", "union", ["s"])],
        ),
        # E02: Visited_{i, c} = Tree_{i, p, c} :: \/_p OR(∪)
        #      The IR attaches a Reduce to a BinaryApp, so a transparent
        #      take_left(take_left) Map against True carries it.
        Einsum(
            output_tensor="Visited",
            output_ranks=[rv("i"), rv("c")],
            expression=BinaryApp(label=1, lhs=inp("Tree", rv("i"), rv("p"), rv("c")),
                                 rhs=inp("Lit_True")),
            specs=[map_spec(1, "take_left", "take_left", []),
                   reduce_spec(1, "OR", "union", ["p"])],
        ),
        # E03: NV_{i, c} = not Visited_{i, c}
        Einsum(
            output_tensor="NV",
            output_ranks=[rv("i"), rv("c")],
            expression=UnaryApp(op=BuiltinUnaryOp(symbol="not"),
                                operand=inp("Visited", rv("i"), rv("c"))),
            specs=[],
        ),
        # E04: NeiNV_{i, d} = Nei_{i, d} . NV_{i, d} :: /\_d AND(∩)
        Einsum(
            output_tensor="NeiNV",
            output_ranks=[rv("i"), rv("d")],
            expression=BinaryApp(label=1, lhs=inp("Nei", rv("i"), rv("d")),
                                 rhs=inp("NV", rv("i"), rv("d"))),
            specs=[map_spec(1, "AND", "intersect", ["d"])],
        ),
        # E05: CandTree_{i, s, d} = (G_{s, d} . F_{i, s})_{i, s, d} . NeiNV_{i, d}
        #      :: /\ AND(∩) /\ AND(∩)
        Einsum(
            output_tensor="CandTree",
            output_ranks=[rv("i"), rv("s"), rv("d")],
            expression=BinaryApp(
                label=2,
                lhs=AnonymousTensor(
                    expression=BinaryApp(label=1, lhs=inp("G", rv("s"), rv("d")),
                                         rhs=inp("F", rv("i"), rv("s"))),
                    ranks=[rv("i"), rv("s"), rv("d")],
                ),
                rhs=inp("NeiNV", rv("i"), rv("d")),
            ),
            specs=[map_spec(1, "AND", "intersect", ["s"]),
                   map_spec(2, "AND", "intersect", ["d"])],
        ),
        # E06: Temp_{i, s*, d} = CandTree_{i, s, d} :: <<<_{s*} 1(pick-parent)
        Einsum(
            output_tensor="Temp",
            output_ranks=[rv("i"), rv("s"), rv("d")],
            expression=BinaryApp(label=1,
                                 lhs=inp("CandTree", rv("i"), rv("s"), rv("d")),
                                 rhs=inp("Lit_True")),
            specs=[map_spec(1, "take_left", "take_left", []),
                   PopulateSpec(label=1, rank_list=["s"],
                                compute_op=compute("identity"),
                                coord_op=CoordinateOp(name="pick-parent"))],
        ),
        # E07: Tree_{i+1, s, d} = Tree_{i, s, d} . Temp_{i, s, d} :: /\_d OR(∪)
        Einsum(
            output_tensor="Tree",
            output_ranks=[i_plus_one(), rv("s"), rv("d")],
            expression=BinaryApp(label=1,
                                 lhs=inp("Tree", rv("i"), rv("s"), rv("d")),
                                 rhs=inp("Temp", rv("i"), rv("s"), rv("d"))),
            specs=[map_spec(1, "OR", "union", ["d"])],
        ),
        # E08: F_{i+1, d} = NeiNV_{i, d}
        Einsum(
            output_tensor="F",
            output_ranks=[i_plus_one(), rv("d")],
            expression=inp("NeiNV", rv("i"), rv("d")),
            specs=[],
        ),
    ]

    # <> : ||F_{i+1}|| == 0
    stopping = StoppingCondition(
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
                                                 stopping_conditions=[stopping])),
    )


if __name__ == "__main__":
    sys.stdout.write(build_direction_optimizing_bfs().model_dump_json(indent=2))
