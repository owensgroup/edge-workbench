"""Construct the hybrid (direction-optimizing) DO-BFS program in IR form, dump
JSON to stdout.

Labels E01-E21 match einsum.edge line for line. E03 is the multi-output case
statement: one ConditionalCascade whose arms are the two macros, expanded.
`n` in the initialization is the source vertex: the host supplies it as the
coordinate set root_id.
"""

from __future__ import annotations

import sys
from typing import Any

from edge_ir.ir.actions import MapSpec, PopulateSpec, ReduceSpec
from edge_ir.ir.einsum import (
    ConditionalArm,
    ConditionalCascade,
    Einsum,
    NestedCascade,
    StoppingCondition,
)
from edge_ir.ir.expr import (
    AnonymousTensor,
    BinaryApp,
    InputTensor,
    RankArith,
    RankConstantLiteral,
    RankConstantShapeSym,
    RankValue,
    RankVariable,
    TensorProjection,
    UnaryApp,
)
from edge_workbench.macro import MacroDefinition, expand
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


def rc(value: int) -> RankConstantLiteral:
    return RankConstantLiteral(value=value)


def nxt() -> RankArith:
    return RankArith(op="+", lhs=rv("i"), rhs=rc(1))


def proj(tensor: str, *ranks: Any) -> TensorProjection:
    return TensorProjection(tensor=tensor, ranks=list(ranks))


def inp(tensor: str, *ranks: Any) -> InputTensor:
    return InputTensor(proj=proj(tensor, *ranks))


def compute(name: str) -> BuiltinComputeOp | UserDefinedComputeOp:
    if name in {"+", "-", "*", "/"}:
        return BuiltinComputeOp(symbol=name)  # type: ignore[arg-type]
    return UserDefinedComputeOp(name=name)


def map_spec(label: int, c: str, m: str) -> MapSpec:
    return MapSpec(label=label, compute_op=compute(c),
                   merge_op=BuiltinMergeOp(symbol=m))  # type: ignore[arg-type]


def reduce_spec(label: int, c: str, m: str, ranks: list[str]) -> ReduceSpec:
    return ReduceSpec(label=label, rank_list=ranks, compute_op=compute(c),
                      merge_op=BuiltinMergeOp(symbol=m))  # type: ignore[arg-type]


def decl(name: str, ranks: list[tuple[str, str | None]], dtype: str = "bool",
         empty: Any = False) -> TensorDeclaration:
    return TensorDeclaration(
        name=name,
        ranks=[RankDeclaration(name=r, shape=s) for r, s in ranks],
        data_type=BuiltinDataType(name=dtype),
        empty_value=empty,
    )


def literal(name: str, dtype: str, value: Any) -> TensorDeclaration:
    return TensorDeclaration(name=name, ranks=[],
                             data_type=BuiltinDataType(name=dtype),
                             empty_value=None, value=value)


def source() -> list[SetMembership]:
    return [SetMembership(member=rv("n"), coord_set=CoordSetName(name="root_id"),
                          negated=False)]


def reduce_only(tensor: str, ranks: list[Any], operand: InputTensor,
                c: str, over: list[str]) -> Einsum:
    """`Out = X :: \/ c(∪)`. The IR attaches a Reduce to a BinaryApp, so a
    transparent take_left(take_left) Map against True carries it."""
    return Einsum(
        output_tensor=tensor, output_ranks=ranks,
        expression=BinaryApp(label=1, lhs=operand, rhs=inp("Lit_True")),
        specs=[map_spec(1, "take_left", "take_left"),
               reduce_spec(1, c, "union", over)],
    )


def pick_parent(operand: InputTensor) -> Einsum:
    """Temp_{i, s*, d} = X_{i, s, d} :: <<<_{s*} 1(pick-parent)"""
    return Einsum(
        output_tensor="Temp",
        output_ranks=[rv("i"), rv("s"), rv("d")],
        expression=BinaryApp(label=1, lhs=operand, rhs=inp("Lit_True")),
        specs=[map_spec(1, "take_left", "take_left"),
               PopulateSpec(label=1, rank_list=["s"],
                            compute_op=compute("identity"),
                            coord_op=CoordinateOp(name="pick-parent"))],
    )


I, S, D, C = rv("i"), rv("s"), rv("d"), rv("c")

# The macros' declared outputs, shared by both headers:
#   -> TTree_{i+1, s, d}, TF_{i+1, d}, TTopDown_{i+1}
FORMAL_OUT = [proj("TTree", nxt(), S, D), proj("TF", nxt(), D),
              proj("TTopDown", nxt())]


def top_down() -> MacroDefinition:
    """- Macro TOP-DOWN(TG_{s, d}, TF_{i, s}, TTree_{i, s, d}, TNV_{i, c},
                        TMF_i, TMU_i) -> TTree_{i+1, s, d}, TF_{i+1, d}, TTopDown_{i+1}"""
    body = [
        # E04: Nei_{i, d} = TG_{s, d} . TF_{i, s} :: /\ AND(∩) \/ OR(∪)
        Einsum(
            output_tensor="Nei", output_ranks=[I, D],
            expression=BinaryApp(label=1, lhs=inp("TG", S, D),
                                 rhs=inp("TF", I, S)),
            specs=[map_spec(1, "AND", "intersect"),
                   reduce_spec(1, "OR", "union", ["s"])],
        ),
        # E05: NeiNV_{i, d} = Nei_{i, d} . TNV_{i, d} :: /\ AND(∩)
        Einsum(
            output_tensor="NeiNV", output_ranks=[I, D],
            expression=BinaryApp(label=1, lhs=inp("Nei", I, D),
                                 rhs=inp("TNV", I, D)),
            specs=[map_spec(1, "AND", "intersect")],
        ),
        # E06: CandTree_{i, s, d} = (TG_{s, d} . TF_{i, s})_{i, s, d} . NeiNV_{i, d}
        #      :: /\ AND(∩) /\ AND(∩)
        Einsum(
            output_tensor="CandTree", output_ranks=[I, S, D],
            expression=BinaryApp(
                label=2,
                lhs=AnonymousTensor(
                    expression=BinaryApp(label=1, lhs=inp("TG", S, D),
                                         rhs=inp("TF", I, S)),
                    ranks=[I, S, D]),
                rhs=inp("NeiNV", I, D)),
            specs=[map_spec(1, "AND", "intersect"),
                   map_spec(2, "AND", "intersect")],
        ),
        # E07: Temp_{i, s*, d} = CandTree_{i, s, d} :: <<<_{s*} 1(pick-parent)
        pick_parent(inp("CandTree", I, S, D)),
        # E08: TTree_{i+1, s, d} = TTree_{i, s, d} . Temp_{i, s, d} :: /\ OR(∪)
        Einsum(
            output_tensor="TTree", output_ranks=[nxt(), S, D],
            expression=BinaryApp(label=1, lhs=inp("TTree", I, S, D),
                                 rhs=inp("Temp", I, S, D)),
            specs=[map_spec(1, "OR", "union")],
        ),
        # E09: TF_{i+1, d} = NeiNV_{i, d}
        Einsum(output_tensor="TF", output_ranks=[nxt(), D],
               expression=inp("NeiNV", I, D), specs=[]),
        # E10: TMF_i = TG_{s, d} . TF_{i, s} :: /\ AND(∩) \/ +(∪)
        Einsum(
            output_tensor="TMF", output_ranks=[I],
            expression=BinaryApp(label=1, lhs=inp("TG", S, D),
                                 rhs=inp("TF", I, S)),
            specs=[map_spec(1, "AND", "intersect"),
                   reduce_spec(1, "+", "union", ["s", "d"])],
        ),
        # E11: TMU_i = TG_{s, d} . TNV_{i, d} :: /\ AND(∩) \/ +(∪)
        Einsum(
            output_tensor="TMU", output_ranks=[I],
            expression=BinaryApp(label=1, lhs=inp("TG", S, D),
                                 rhs=inp("TNV", I, D)),
            specs=[map_spec(1, "AND", "intersect"),
                   reduce_spec(1, "+", "union", ["s", "d"])],
        ),
        # E12: TB_i = TMF_i . (TMU_i / alpha) :: /\ >(∩)
        #      The written action `/\ >(∩)` is the `.` operation's (label 2).
        #      The division has no action, so it states no merge: lowered as
        #      Map label 1 with the paper's default merge, pass_through
        #      (section 7.3.4: "If a particular operation label does not
        #      contain a Merge operator, the EDGE machinery applies the
        #      Compute operator to every point in the iteration space").
        Einsum(
            output_tensor="TB", output_ranks=[I],
            expression=BinaryApp(
                label=2,
                lhs=inp("TMF", I),
                rhs=AnonymousTensor(
                    expression=BinaryApp(label=1, lhs=inp("TMU", I),
                                         rhs=inp("Alpha")),
                    ranks=[I])),
            specs=[map_spec(1, "/", "pass_through"),
                   map_spec(2, "gt", "intersect")],
        ),
        # E13: TTopDown_{i+1} = not TB_i
        Einsum(output_tensor="TTopDown", output_ranks=[nxt()],
               expression=UnaryApp(op=BuiltinUnaryOp(symbol="not"),
                                   operand=inp("TB", I)),
               specs=[]),
    ]
    return MacroDefinition(
        name="TOP-DOWN",
        inputs=[proj("TG", S, D), proj("TF", I, S), proj("TTree", I, S, D),
                proj("TNV", I, C), proj("TMF", I), proj("TMU", I)],
        outputs=FORMAL_OUT, body=body)


def bottom_up() -> MacroDefinition:
    """- Macro BOTTOM-UP(TG_{s, d}, TF_{i, s}, TTree_{i, s, d}, TNV_{i, c},
                         TNF_i) -> TTree_{i+1, s, d}, TF_{i+1, d}, TTopDown_{i+1}"""
    body = [
        # E14: CandParents_{i, s, d} = TG_{s, d} . TNV_{i, d} :: /\ AND(∩)
        Einsum(
            output_tensor="CandParents", output_ranks=[I, S, D],
            expression=BinaryApp(label=1, lhs=inp("TG", S, D),
                                 rhs=inp("TNV", I, D)),
            specs=[map_spec(1, "AND", "intersect")],
        ),
        # E15: InF_{i, s, d} = CandParents_{i, s, d} . TF_{i, s} :: /\ AND(∩)
        Einsum(
            output_tensor="InF", output_ranks=[I, S, D],
            expression=BinaryApp(label=1, lhs=inp("CandParents", I, S, D),
                                 rhs=inp("TF", I, S)),
            specs=[map_spec(1, "AND", "intersect")],
        ),
        # E16: Temp_{i, s*, d} = InF_{i, s, d} :: <<<_{s*} 1(pick-parent)
        pick_parent(inp("InF", I, S, D)),
        # E17: TTree_{i+1, s, d} = Temp_{i, s, d} . TTree_{i, s, d} :: /\ OR(∪)
        Einsum(
            output_tensor="TTree", output_ranks=[nxt(), S, D],
            expression=BinaryApp(label=1, lhs=inp("Temp", I, S, D),
                                 rhs=inp("TTree", I, S, D)),
            specs=[map_spec(1, "OR", "union")],
        ),
        # E18: TF_{i+1, d} = InF_{i, s, d} :: \/ OR(∪)
        reduce_only("TF", [nxt(), D], inp("InF", I, S, D), "OR", ["s"]),
        # E19: TNF_i = TF_{i, s} :: \/ +(∪)
        reduce_only("TNF", [I], inp("TF", I, S), "+", ["s"]),
        # E20: BT_i = TNF_i . (|V| / beta) :: /\ <(∩)
        #      As E12: the written action is the `.` operation's (label 2);
        #      the division states no merge, so pass_through (paper 7.3.4).
        #      |V| is a shape read as a value.
        Einsum(
            output_tensor="BT", output_ranks=[I],
            expression=BinaryApp(
                label=2,
                lhs=inp("TNF", I),
                rhs=AnonymousTensor(
                    expression=BinaryApp(
                        label=1,
                        lhs=RankValue(expr=RankConstantShapeSym(name="|V|")),
                        rhs=inp("Beta")),
                    ranks=[I])),
            specs=[map_spec(1, "/", "pass_through"),
                   map_spec(2, "lt", "intersect")],
        ),
        # E21: TTopDown_{i+1} = BT_i
        Einsum(output_tensor="TTopDown", output_ranks=[nxt()],
               expression=inp("BT", I), specs=[]),
    ]
    return MacroDefinition(
        name="BOTTOM-UP",
        inputs=[proj("TG", S, D), proj("TF", I, S), proj("TTree", I, S, D),
                proj("TNV", I, C), proj("TNF", I)],
        outputs=FORMAL_OUT, body=body)


def mode_is(name: str) -> Comparison:
    """`TopDown_i == True` / `TopDown_i == False`"""
    return Comparison(lhs=TensorProjectionValue(proj=proj("TopDown", I)),
                      op="==",
                      rhs=TensorProjectionValue(proj=proj(name)))


def build_direction_optimizing_bfs() -> Program:
    vertex = "|V|"
    gen = ("I", None)
    declarations = [
        decl("G", [("S", vertex), ("D", vertex)]),
        decl("F", [gen, ("S", vertex)]),
        decl("Tree", [gen, ("S", vertex), ("D", vertex)]),
        decl("CandParents", [gen, ("S", vertex), ("D", vertex)]),
        decl("InF", [gen, ("S", vertex), ("D", vertex)]),
        decl("TopDown", [gen]),
        decl("Visited", [gen, ("D", vertex)]),
        decl("NV", [gen, ("D", vertex)]),
        decl("Nei", [gen, ("D", vertex)]),
        decl("NeiNV", [gen, ("D", vertex)]),
        decl("CandTree", [gen, ("S", vertex), ("D", vertex)]),
        decl("Temp", [gen, ("S", vertex), ("D", vertex)]),
        decl("MF", [gen], "int", 0),
        decl("MU", [gen], "int", 0),
        decl("NF", [gen], "int", 0),
        decl("TB", [gen]),
        decl("BT", [gen]),
        # - Constants: alpha = 15, beta = 18
        literal("Alpha", "int", 15),
        literal("Beta", "int", 18),
        literal("Lit_True", "bool", True),
        literal("Lit_False", "bool", False),
        literal("Lit_0", "int", 0),
    ]

    # F, Tree, CandParents and InF = False are the declared empty values, so
    # no Einsum writes them.
    init = Initialization(einsums=[
        Einsum(output_tensor="F", output_ranks=[rc(0), rv("n")],
               expression=inp("Lit_True"), specs=[], predicates=source()),
        Einsum(output_tensor="Tree", output_ranks=[rc(0), rv("n"), rv("n")],
               expression=inp("Lit_True"), specs=[], predicates=source()),
        Einsum(output_tensor="TopDown", output_ranks=[rc(0)],
               expression=inp("Lit_True"), specs=[]),
    ])

    # The call's subscripts, as E03 writes them.
    actual_out = [proj("Tree", nxt(), S, D), proj("F", nxt(), D),
                  proj("TopDown", nxt())]
    shared = [proj("G", S, D), proj("F", I, S), proj("Tree", I, S, D),
              proj("NV", I, C)]

    einsums = [
        # E01: Visited_{i, c} = Tree_{i, p, c} :: \/ OR(∪)
        reduce_only("Visited", [I, C], inp("Tree", I, rv("p"), C), "OR", ["p"]),
        # E02: NV_{i, c} = not Visited_{i, c}
        Einsum(output_tensor="NV", output_ranks=[I, C],
               expression=UnaryApp(op=BuiltinUnaryOp(symbol="not"),
                                   operand=inp("Visited", I, C)),
               specs=[]),
        # E03: (Tree_{i+1, s, d}, F_{i+1, d}, TopDown_{i+1}) = cases:
        #          TOP-DOWN(G_{s, d}, F_{i, s}, Tree_{i, s, d}, NV_{i, c}, MF_i, MU_i)  if TopDown_i == True
        #          BOTTOM-UP(G_{s, d}, F_{i, s}, Tree_{i, s, d}, NV_{i, c}, NF_i)       if TopDown_i == False
        ConditionalCascade(arms=[
            ConditionalArm(
                when=mode_is("Lit_True"),
                einsums=expand(top_down(),
                               shared + [proj("MF", I), proj("MU", I)],
                               actual_out),
                macro="TOP-DOWN"),
            ConditionalArm(
                when=mode_is("Lit_False"),
                einsums=expand(bottom_up(), shared + [proj("NF", I)],
                               actual_out),
                macro="BOTTOM-UP"),
        ]),
    ]

    # <> : ||F_{i+1}|| == 0
    stopping = StoppingCondition(
        rank_variable="i",
        predicate=Comparison(
            lhs=PropertyApp(name="occupancy", pinned_rank_variables=["i"],
                            operands=[proj("F", nxt())]),
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
