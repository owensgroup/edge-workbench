"""Construct the bubble-sort program in IR form, dump JSON to stdout.

Einsum IDs E01-E03 match einsum.edge line for line; the initialization is its
one `cases:` statement. The outer cascade iterates the pass rank i, the inner
cascade (einsum.edge's `- Begin inner cascade` ... `<><> : j == J`) the step
rank j.

einsum.edge writes `min(x, y)` and `max(x, y)` with no merge operator. They
are lowered as a Map with the intersect merge: a read that falls outside Z
(pass 0 has no previous pass, step 0 no previous step) is absent, so that arm
writes nothing there.
"""

from __future__ import annotations

from edge_ir.ir.actions import MapSpec
from edge_ir.ir.einsum import (
    CaseArm,
    Cases,
    Einsum,
    IterativeRankSpec,
    NestedCascade,
)
from edge_ir.ir.expr import (
    BinaryApp,
    InputTensor,
    RankArith,
    RankConstantLiteral,
    RankConstantShapeSym,
    RankVariable,
    TensorProjection,
)
from edge_ir.ir.op import BuiltinMergeOp, UserDefinedComputeOp
from edge_ir.ir.predicate import LogicalAnd, PredicateComparison
from edge_ir.ir.program import Initialization, MainEdge, Program
from edge_ir.ir.stopping import (
    Comparison,
    RankExpressionValue,
    StoppingCondition,
    TensorProjectionValue,
)
from edge_ir.ir.tensor import BuiltinDataType, RankDeclaration, TensorDeclaration

# The extent of the step rank J (einsum.edge: `J = N-1`), named after the rank
# so that `J-1` and `j == J` read as the specification writes them.
STEPS = "J"


def rv(name):
    return RankVariable(name=name)


def lit(value):
    return RankConstantLiteral(value=value)


def plus(rank, k):
    return RankArith(op="+" if k > 0 else "-", lhs=rank, rhs=lit(abs(k)))


LAST = plus(RankConstantShapeSym(name=STEPS), -1)  # J-1


def inp(tensor, *ranks):
    return InputTensor(proj=TensorProjection(tensor=tensor, ranks=list(ranks)))


def pick(op, left, right):
    """`min(x, y)` / `max(x, y)`: one Map, intersect merge."""
    return {
        "expression": BinaryApp(label=1, lhs=left, rhs=right),
        "specs": [
            MapSpec(
                label=1,
                compute_op=UserDefinedComputeOp(name=op),
                merge_op=BuiltinMergeOp(symbol="intersect"),
            )
        ],
    }


def where(op, rhs):
    return PredicateComparison(lhs=rv("n"), op=op, rhs=rhs)


def at_least(var, k):
    """`var : var >= k` in an output subscript: the Einsum runs only there."""
    return PredicateComparison(lhs=rv(var), op=">=", rhs=lit(k))


def z(out, arms, predicates=()):
    return Einsum(
        output_tensor="Z",
        output_ranks=list(out),
        expression=Cases(arms=arms),
        specs=[],
        predicates=list(predicates),
    )


def build_bubble_sort() -> Program:
    i, j, n = rv("i"), rv("j"), rv("n")
    init = z(
        [lit(0), lit(0), n],
        [
            CaseArm(
                **pick("min", inp("A", lit(0)), inp("A", lit(1))),
                where=where("==", lit(0)),
            ),
            CaseArm(
                **pick("max", inp("A", lit(0)), inp("A", lit(1))),
                where=where("==", lit(1)),
            ),
            CaseArm(expression=None),
        ],
    )
    running0 = inp("Z", lit(0), plus(j, -1), j)
    incoming0 = inp("A", plus(j, 1))
    # E01: Z_{0, j : j >= 1, n} = cases: ...   (pass 0, step j)
    pass0 = z(
        [lit(0), j, n],
        [
            CaseArm(expression=inp("Z", lit(0), plus(j, -1), n), where=where("<", j)),
            CaseArm(**pick("min", running0, incoming0), where=where("==", j)),
            CaseArm(**pick("max", running0, incoming0), where=where("==", plus(j, 1))),
            CaseArm(expression=None),
        ],
        predicates=[at_least("j", 1)],
    )
    prev0 = inp("Z", plus(i, -1), LAST, lit(0))
    prev1 = inp("Z", plus(i, -1), LAST, lit(1))
    # E02: Z_{i : i >= 1, 0, n} = cases: ...   (pass i, step 0)
    step0 = z(
        [i, lit(0), n],
        [
            CaseArm(**pick("min", prev0, prev1), where=where("==", lit(0))),
            CaseArm(**pick("max", prev0, prev1), where=where("==", lit(1))),
            CaseArm(
                expression=inp("Z", plus(i, -1), LAST, n), where=where(">=", lit(2))
            ),
        ],
        predicates=[at_least("i", 1)],
    )
    running = inp("Z", i, plus(j, -1), j)
    incoming = inp("Z", plus(i, -1), LAST, plus(j, 1))
    # E03: Z_{i : i >= 1, j : j >= 1, n} = cases: ...   (pass i, step j)
    sweep = z(
        [i, j, n],
        [
            CaseArm(expression=inp("Z", i, plus(j, -1), n), where=where("<", j)),
            CaseArm(**pick("min", running, incoming), where=where("==", j)),
            CaseArm(**pick("max", running, incoming), where=where("==", plus(j, 1))),
            CaseArm(
                expression=inp("Z", plus(i, -1), LAST, n), where=where(">", plus(j, 1))
            ),
        ],
        predicates=[LogicalAnd(operands=[at_least("i", 1), at_least("j", 1)])],
    )
    inner = NestedCascade(
        einsums=[pass0, step0, sweep],
        stopping_conditions=[
            StoppingCondition(
                rank_variable="j",
                predicate=Comparison(
                    lhs=RankExpressionValue(expr=j),
                    op="==",
                    rhs=RankExpressionValue(expr=RankConstantShapeSym(name=STEPS)),
                ),
            )
        ],
        iterative_rank=IterativeRankSpec(rank_variable="j"),
    )
    outer = NestedCascade(
        einsums=[inner],
        stopping_conditions=[
            StoppingCondition(
                rank_variable="i",
                predicate=Comparison(
                    lhs=TensorProjectionValue(
                        proj=TensorProjection(tensor="Z", ranks=[plus(i, 1), LAST])
                    ),
                    op="==",
                    rhs=TensorProjectionValue(
                        proj=TensorProjection(tensor="Z", ranks=[i, LAST])
                    ),
                ),
            )
        ],
        iterative_rank=IterativeRankSpec(rank_variable="i"),
    )
    integer = BuiltinDataType(name="int")
    return Program(
        declarations=[
            TensorDeclaration(
                name="A",
                ranks=[RankDeclaration(name="N", shape="|A|")],
                data_type=integer,
                empty_value=float("inf"),
            ),
            TensorDeclaration(
                name="Z",
                ranks=[
                    # The pass rank is declared with a shape, so the outer
                    # cascade is bounded by it: i in [0, I).
                    RankDeclaration(name="I", shape="I"),
                    RankDeclaration(name="J", shape=STEPS),
                    RankDeclaration(name="M", shape="N"),
                ],
                data_type=integer,
                empty_value=float("inf"),
            ),
        ],
        initialization=Initialization(einsums=[init]),
        main_edge=MainEdge(cascade=outer),
    )


if __name__ == "__main__":
    import sys

    sys.stdout.write(build_bubble_sort().model_dump_json(indent=2))
