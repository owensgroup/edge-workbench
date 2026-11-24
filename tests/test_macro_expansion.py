"""Macro expansion (paper appendix B.8), the workbench's front end.

Moved from edge-core-ir on 2026-11-19: a macro is lexical substitution, and
edge-core-ir's IR is the desugared form (its D3), so expanding one is a front
end's job. The conditional cascade the expansion feeds stays in edge-core-ir.
"""

from __future__ import annotations

from edge_workbench.spec_check import _import_edge_ir

_import_edge_ir()

import pytest
from edge_ir.ir.actions import MapSpec, ReduceSpec
from edge_ir.ir.einsum import (
    Einsum,
)
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

from edge_workbench.macro import MacroDefinition, MacroExpansionError, expand


def rv(name):
    return RankVariable(name=name)


def lit(value):
    return RankConstantLiteral(value=value)


def nxt(name="i"):
    return RankArith(op="+", lhs=rv(name), rhs=lit(1))


def proj(tensor, *ranks):
    return TensorProjection(tensor=tensor, ranks=list(ranks))


def inp(tensor, *ranks):
    return InputTensor(proj=proj(tensor, *ranks))


def op(name):
    if name in "+-*/":
        return BuiltinComputeOp(symbol=name)
    return UserDefinedComputeOp(name=name)


def map_(compute, merge, label=1):
    return MapSpec(
        label=label, compute_op=op(compute), merge_op=BuiltinMergeOp(symbol=merge)
    )


def reduce_(compute, ranks, label=1):
    return ReduceSpec(
        label=label,
        rank_list=ranks,
        compute_op=op(compute),
        merge_op=BuiltinMergeOp(symbol="union"),
    )


def einsum(tensor, ranks, lhs, rhs, *specs):
    return Einsum(
        output_tensor=tensor,
        output_ranks=list(ranks),
        expression=BinaryApp(label=1, lhs=lhs, rhs=rhs),
        specs=list(specs),
    )


def negated(tensor, *ranks):
    return UnaryApp(op=BuiltinUnaryOp(symbol="not"), operand=inp(tensor, *ranks))


################################################################################
# Macro expansion
################################################################################


def gemm() -> MacroDefinition:
    """MACRO GEMM(TA_{a,c}, TB_{c,b}) -> T_{a,b} :  T_{a,b} = TA_{a,c} x TB_{c,b}"""
    a, b, c = rv("a"), rv("b"), rv("c")
    return MacroDefinition(
        name="GEMM",
        inputs=[proj("TA", a, c), proj("TB", c, b)],
        outputs=[proj("T", a, b)],
        body=[
            einsum(
                "T",
                [a, b],
                inp("TA", a, c),
                inp("TB", c, b),
                map_("*", "intersect"),
                reduce_("+", ["c"]),
            )
        ],
    )


def test_assignment_form_substitutes_tensors_and_rank_variables() -> None:
    """Z_{m,n} = GEMM(A_{m,k}, B_{k,n}): TA -> A, a,c -> m,k; TB -> B; T -> Z."""
    m, k, n = rv("m"), rv("k"), rv("n")
    (expanded,) = expand(gemm(), [proj("A", m, k), proj("B", k, n)], [proj("Z", m, n)])
    assert expanded == einsum(
        "Z",
        [m, n],
        inp("A", m, k),
        inp("B", k, n),
        map_("*", "intersect"),
        reduce_("+", ["k"]),
    )


def test_an_argument_may_be_a_rank_variable_expression() -> None:
    """The paper's own example, GEMM(A_{m+1,k}, B_{k,n})_{m,n}: "TA becomes A;
    rank variables a, c become m+1, k". Here the output is given as Z_{m+1,n},
    the consistent subscript for the rank variable the two parameters share."""
    k, n = rv("k"), rv("n")
    (expanded,) = expand(
        gemm(), [proj("A", nxt("m"), k), proj("B", k, n)], [proj("Z", nxt("m"), n)]
    )
    assert expanded.output_ranks == [nxt("m"), n]
    assert expanded.expression.lhs == inp("A", nxt("m"), k)


def test_inconsistent_subscripts_across_parameters_are_refused() -> None:
    m, k, n = rv("m"), rv("k"), rv("n")
    with pytest.raises(MacroExpansionError, match="inconsistently"):
        expand(gemm(), [proj("A", nxt("m"), k), proj("B", k, n)], [proj("Z", m, n)])
    with pytest.raises(MacroExpansionError, match="invoked with 1"):
        expand(gemm(), [proj("A", m, k)], [proj("Z", m, n)])


def test_a_shifted_formal_binds_its_variable_through_the_shift() -> None:
    """MACRO STEP(TX_{i,v}) -> TX_{i+1,v}, invoked as X_{g,v} = STEP(X_{g-1,v})."""
    i, v, g = rv("i"), rv("v"), rv("g")
    step = MacroDefinition(
        name="STEP",
        inputs=[proj("TX", i, v)],
        outputs=[proj("TX", nxt(), v)],
        body=[
            Einsum(
                output_tensor="TX",
                output_ranks=[nxt(), v],
                expression=inp("TX", i, v),
                specs=[],
            )
        ],
    )
    previous = RankArith(op="-", lhs=g, rhs=lit(1))
    (expanded,) = expand(step, [proj("X", previous, v)], [proj("X", g, v)])
    assert expanded.output_tensor == "X"
    assert expanded.output_ranks == [g, v]  # (g-1)+1
    assert expanded.expression == inp("X", previous, v)
