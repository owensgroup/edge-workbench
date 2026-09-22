"""Our driver and the reference evaluator must agree, tensor for tensor.

`edge-ir-interpreter` ships a reference evaluator: an independent execution
of the same IR, written by the IR's author against the semantics chapter, in
a different language, with a different state representation (generation-
indexed coordinates rather than a flat current-generation state). It is the
authority on what a program means -- "if the chapter and this code disagree,
this code is wrong".

That makes it the second opinion this repo needs. Max-flow has a hand-written
push-relabel implementation to check against; no future algorithm will. What
every algorithm WILL have is this evaluator, so the pairing that has to keep
working is ours-against-upstream.

THE FREE CHOICE IS PINNED, AND ONLY HERE
----------------------------------------
`pick-admissible-edge` is seeded-random in `cascade.json`, because the Einsum
says ANY admissible edge and a deterministic rule would make the spec claim
otherwise. But two implementations cannot be compared while both are free to
choose differently -- every disagreement would be legitimate and the test
would say nothing. So this file pins OUR side to `select-min-coord`, which is
what upstream's `max_flow_functions.py` registers for the same operator, and
the comparison then measures only what it is supposed to.

That pinning is a test fixture. It is not what the algorithm does, and it is
deliberately not in `cascade.json`.

The two differ deliberately and the comparison has to allow for it:

  - it keeps every generation of every tensor; we keep the current one;
  - it keys cells by coordinate tuples, we key them by "u,v" strings;
  - it runs the whole cascade to the stopping condition and reports state;
    we also record a step per Einsum, which it has no equivalent of.

WHICH TENSORS ARE COMPARED, AND WHY NOT ALL OF THEM
---------------------------------------------------
The cascade stops mid-round -- the stopping condition is tested after E06, so
the last generation is short. Under the reference's generation-indexed view
the Einsums that did not run simply never wrote generation 13, so `Rel_13`
does not exist. Under our flat view `Rel` still holds what round 12 put there,
because nothing overwrote it. Neither is wrong; they are answers to different
questions, and comparing them would only measure where the loop was cut.

So the comparison is over the **loop-carried state**: the tensors some Einsum
reads at plain generation `i`, whose previous generation is therefore part of
the algorithm's state rather than scratch within a round. That set is derived
from the program, not listed here, so it follows the spec if the spec moves.
On max-flow it comes out as F, E, R, D and Act -- which is exactly the state
the viewer calls generational -- plus every non-iterative tensor.

What is NOT allowed to differ is that state, cell for cell -- with one known
exception, `R`, documented in `docs/DIVERGENCE_case_arms.md` and asserted
exactly below so that a change in its shape fails rather than passes.

    EDGE_IR_REPO=~/Projects/edge-ir-interpreter pytest tests/test_agrees_with_reference.py

Skips when the upstream checkout is not present -- the vendored IR means this
repo builds without it, and a missing sibling should not look like a failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
ALG = Path(__file__).resolve().parents[1].name
SPEC = ROOT / "algorithms" / ALG / "spec"
UPSTREAM = Path(os.environ.get(
    "EDGE_IR_REPO", str(Path.home() / "Projects/edge-ir-interpreter")))


def _require_upstream():
    if not (UPSTREAM / "edge_ir/evaluator/__init__.py").exists():
        pytest.skip(f"no reference evaluator at {UPSTREAM}")
    sys.path.insert(0, str(UPSTREAM))
    sys.path.insert(0, str(UPSTREAM / "test-algorithms/max-flow"))


def _instance():
    return json.loads((SPEC / "instance.json").read_text())


def _program():
    _require_upstream()
    from build_max_flow_program import build_max_flow
    return build_max_flow()


def _coord(key: str) -> tuple:
    """"1,3" -> (1, 3); "" -> ()."""
    return tuple(int(p) for p in key.split(",")) if key else ()


def _run_reference():
    """Drive the cascade with the reference evaluator."""
    _require_upstream()
    import edge_ir.evaluator  # noqa: F401  (must precede edge_ir.udf)
    from edge_ir.evaluator import evaluate
    from build_max_flow_program import build_max_flow
    from max_flow_functions import max_flow_registry

    inst = _instance()
    n = inst["scalars"]["VertexCount"]
    tensors = inst["tensors"]
    inputs = {
        "G": {_coord(k): 1 for k in tensors["C"]},
        "C": {_coord(k): v for k, v in tensors["C"].items()},
        "S": {_coord(k): v for k, v in tensors["S"].items()},
        "T": {_coord(k): v for k, v in tensors["T"].items()},
        "VertexCount": {(): n},
    }
    return evaluate(
        build_max_flow(),
        inputs=inputs,
        shape_env={"|V|": n},
        functions=max_flow_registry(),
        max_iterations=50 * n * n,
    )


def _run_ours():
    """Drive the same cascade with this repo's driver, via node."""
    script = r"""
const fs=require("fs");
const R=process.env.EW_ROOT;
const {runCascade}=require(R+"/edge_workbench/driver/cascade.js");
const rd=(p)=>JSON.parse(fs.readFileSync(p,"utf8"));
const S=R+"/algorithms/max-flow/spec";
const cascade=rd(S+"/cascade.json");
// Pin the free choice to the rule upstream registers, so the comparison is
// about the evaluators and not about which admissible edge each one fancied.
cascade.selectors={"pick-admissible-edge": process.env.EW_RULE};
const r=runCascade(rd(S+"/max_flow_program.json"), rd(S+"/instance.json"),
                   cascade, {});
const last=r.steps[r.steps.length-1];
process.stdout.write(JSON.stringify({generations:r.generations, state:last.state}));
"""
    p = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, cwd=ROOT,
        env=dict(os.environ, EW_ROOT=str(ROOT), EW_RULE=PINNED_RULE),
    )
    assert p.returncode == 0, "our driver failed:\n" + p.stdout + p.stderr
    return json.loads(p.stdout)


def _at_generation(result, tensor: str, iterative: bool, generation: int) -> dict:
    """One generation of a tensor from the reference's result.

    The generation is the cascade's FINAL one, the same for every tensor --
    not each tensor's own maximum. Those differ: a tensor the last round did
    not write is simply absent at that generation, and taking its own maximum
    would silently compare a state from an earlier round.
    """
    cells = dict(result[tensor].items())
    if not iterative:
        return cells
    return {c[1:]: v for c, v in cells.items() if c[0] == generation}


#: What upstream's max_flow_functions.py aliases `select-one-admissible-v` to.
#: Both sides make the same choices under it, so any remaining difference is
#: real. See the header: this is a fixture, not the algorithm.
PINNED_RULE = "select-min-coord"


# The names this repo shows a tensor under, where they differ from the IR's.
DISPLAY = json.loads((SPEC / "cascade.json").read_text()).get("displayNames", {})


def _loop_carried(program_json: dict) -> set:
    """Tensors written at generation `i+1` AND read at plain generation `i`.

    Both halves are needed. Read-at-`i` alone catches every scratch tensor
    too, because a tensor written and read inside one round is also read at
    `i` -- Lbl, Adm, delta and the push totals all look carried under that
    test and none of them are. Requiring a write at `i+1` as well says the
    NEXT round is the reader, which is what makes a value state rather than
    scratch.

    On max-flow this derives {F, E, R, D, Act} from the program.
    """
    einsums = program_json["main_edge"]["cascade"]["einsums"]

    def is_next_gen(rank):
        return (rank.get("kind") == "arith" and rank.get("op") == "+"
                and rank.get("lhs", {}).get("name") == "i"
                and rank.get("rhs", {}).get("value") == 1)

    written_next = {
        e["output_tensor"] for e in einsums
        if e["output_ranks"] and is_next_gen(e["output_ranks"][0])
    }

    read_this = set()

    def walk(node):
        if isinstance(node, dict):
            proj = node.get("proj")
            if isinstance(proj, dict) and proj.get("ranks"):
                first = proj["ranks"][0]
                if first.get("kind") == "var" and first.get("name") == "i":
                    read_this.add(proj["tensor"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(einsums)
    return written_next & read_this


def _r_differs_only_on_the_source_row(theirs, mine):
    """The one known disagreement, pinned to its exact shape.

    E04 lowers a three-arm `cases` to three Einsums that overwrite each other
    in reverse priority. The `u = s` arm computes 0, which is R's empty value,
    so it must CLEAR what the `otherwise` arm wrote -- the preflow saturated
    every edge out of the source, so there is no residual there.

    The reference evaluator treats an assignment as only ever adding values,
    so writing the empty value writes nothing and the capacities stay. Its
    `R_1[s,v]` is `C[s,v]` where the spec says 0.

    It does not change max-flow's answer: `D[s] = |V|` keeps the source
    permanently inactive, so the phantom residual is never pushed along. That
    is exactly why only a state-level comparison finds it.

    Asserted precisely rather than skipped: if upstream fixes it this fails
    and we delete the exception; if it changes shape this fails and we look.
    """
    source_row = lambda d: {k: v for k, v in d.items() if k[0] == 0}  # noqa: E731
    others = lambda d: {k: v for k, v in d.items() if k[0] != 0}      # noqa: E731
    assert others(theirs) == others(mine), (
        "R was expected to differ only on the source's row; it differs "
        f"elsewhere too: reference {others(theirs)} vs ours {others(mine)}"
    )
    capacities = {
        _coord(k): v
        for k, v in _instance()["tensors"]["C"].items()
        if k.startswith("0,")
    }
    theirs_src, mine_src = source_row(theirs), source_row(mine)
    surplus = {k: v - mine_src.get(k, 0) for k, v in theirs_src.items()}
    assert surplus == capacities, (
        "the reference's surplus on the source row was expected to be exactly "
        f"the capacities the `u = s` arm should have cleared; got {surplus} "
        f"against capacities {capacities}"
    )


KNOWN_DIVERGENCE = {"R": _r_differs_only_on_the_source_row}


def test_the_two_evaluators_agree_on_every_tensor():
    ref = _run_reference()
    ours = _run_ours()["state"]

    program = _program()
    program_json = json.loads((SPEC / "max_flow_program.json").read_text())
    carried = _loop_carried(program_json)
    final = ref.trace.generations

    compared = []
    mismatches = []
    for decl in program.declarations:
        name = decl.name
        if not decl.ranks:
            continue                      # scalars: inputs, not results
        iterative = decl.ranks[0].name == "I"
        if iterative and name not in carried:
            continue                      # per-round scratch; see the header
        compared.append(name)
        theirs = _at_generation(ref, name, iterative, final)
        mine = ours.get(DISPLAY.get(name, name), {})
        mine_keyed = {_coord(k): v for k, v in mine.items()}
        # Both sides drop cells holding the empty value, but booleans reach
        # the two differently: ours stores `true`, theirs stores True.
        theirs_n = {k: (bool(v) if isinstance(v, bool) else v)
                    for k, v in theirs.items()}
        mine_n = {k: (bool(v) if isinstance(v, bool) else v)
                  for k, v in mine_keyed.items()}
        if name in KNOWN_DIVERGENCE:
            KNOWN_DIVERGENCE[name](theirs_n, mine_n)
            continue
        if theirs_n != mine_n:
            only_ref = {k: v for k, v in theirs_n.items() if mine_n.get(k) != v}
            only_us = {k: v for k, v in mine_n.items() if theirs_n.get(k) != v}
            mismatches.append(
                f"  {name}: reference-only {dict(list(only_ref.items())[:4])}, "
                f"ours-only {dict(list(only_us.items())[:4])}"
            )

    assert not mismatches, (
        "our driver and the reference evaluator disagree:\n" + "\n".join(mismatches)
    )
    # A comparison over nothing would also report no mismatches.
    assert {"F", "E", "R", "D"} <= set(compared), (
        f"expected the carried state to be compared; got {sorted(compared)}"
    )
    # ...and not everything, or the "scratch is excluded" reasoning above is
    # not actually being applied.
    assert "Lbl" not in compared and "Delta" not in compared, sorted(compared)


def test_the_pinned_rule_is_the_one_upstream_registers():
    """If upstream changes its rule, pinning to ours stops being a pin.

    The comparison is only meaningful while both sides make the same choices.
    That is a fact about upstream's registry, so read it rather than trusting
    the comment above.
    """
    _require_upstream()
    from max_flow_functions import SELECT_ONE_ADMISSIBLE_V, max_flow_registry
    from edge_ir.udf import UdfCategory

    reg = max_flow_registry()
    theirs = reg.impl(UdfCategory.COORDINATE, SELECT_ONE_ADMISSIBLE_V)
    canonical = reg.impl(UdfCategory.COORDINATE, PINNED_RULE)
    assert theirs is canonical, (
        f"upstream aliases {SELECT_ONE_ADMISSIBLE_V} to something other than "
        f"{PINNED_RULE}; the comparison is no longer pinning both sides to "
        f"the same choice."
    )


def test_both_reach_the_published_maximum_flow():
    """Agreeing on a wrong answer would still be agreeing."""
    ref = _run_reference()
    excess = _at_generation(ref, "E", True, ref.trace.generations)
    assert excess.get((5,), 0) == 23
    ours = _run_ours()["state"]
    out_of_source = sum(v for k, v in ours.get("F", {}).items()
                        if k.split(",")[0] == "0")
    assert out_of_source == 23
