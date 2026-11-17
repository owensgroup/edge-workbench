# -*- coding: utf-8 -*-
"""Ask a model to write the IR builder, and take its answer back.

WHY A MODEL WRITES THIS
-----------------------
`einsum.edge` has to become IR before anything can run, and the parser that
would do that mechanically is still being built in edge-core-ir. Until it
lands, a builder -- a Python script constructing `edge_ir` objects -- is
written per algorithm, and that is a translation a model does well when shown
two worked translations.

WHY THAT IS SAFE ENOUGH
-----------------------
The model's builder is never trusted for being plausible. What it produces
goes through, in order:

  * Layer 1 and Layer 2 -- the IR's own parser and validators
  * spec versus IR      -- output tensor, generation, every compute(merge),
                           every named operator and every declaration,
                           against einsum.edge
  * coverage            -- every Einsum ran
  * the author's verifier

The operator comparison is the one that matters most: a wrong merge operator
passed every other gate on max-flow, including the answer check.

The author pastes the prompt into a chat and pastes the reply back. No API
call happens anywhere in the workbench.
"""

from __future__ import annotations

import re
from pathlib import Path

from edge_workbench import spec_check
from edge_workbench.spec_surface import SURFACE_COMPUTE, SURFACE_MERGE

#: Upstream algorithms shown as worked translations, richest first. The
#: algorithm being built is never shown its own builder.
REFERENCES = ("max-flow", "bellman-ford", "bfs")
SHOWN = 2


def file_names(slug: str) -> dict[str, str]:
    stem = slug.replace("-", "_")
    return {
        "builder": f"build_{stem}_program.py",
        "functions": f"{stem}_functions.py",
        "registry": f"{stem}_registry",
    }


def _references(slug: str) -> list[tuple[str, dict[str, str]]]:
    root = spec_check.upstream()
    if root is None:
        return []
    out = []
    for name in REFERENCES:
        if name == slug:
            continue
        d = root / "examples" / "algorithms" / name
        edge = d / "einsum.edge"
        builders = sorted(d.glob("build_*_program.py"))
        if not (edge.exists() and builders):
            continue
        files = {"einsum.edge": edge.read_text(),
                 builders[0].name: builders[0].read_text()}
        for f in sorted(d.glob("*_functions.py")):
            files[f.name] = f.read_text()
        out.append((name, files))
        if len(out) == SHOWN:
            break
    return out


def build_prompt(slug: str, edge: Path, tutorial: Path,
                 findings: list[str] | None = None) -> str:
    names = file_names(slug)
    refs = _references(slug)
    ref_text = "\n\n".join(
        f"=== WORKED TRANSLATION: {name} ===\n" + "\n\n".join(
            f"--- {fname} ---\n{body}" for fname, body in files.items())
        for name, files in refs
    ) or "(edge-core-ir not found, so no worked translations are included)"

    compute = ", ".join(f"{k} -> {v}" for k, v in SURFACE_COMPUTE.items())
    merge = ", ".join(f"{k} -> {v}" for k, v in SURFACE_MERGE.items())

    retry = ""
    if findings:
        retry = (
            "\nYOUR PREVIOUS BUILDER WAS REJECTED. Fix exactly these, and "
            "change nothing else:\n"
            + "\n".join(f"  - {f}" for f in findings) + "\n")

    return f"""\
You are translating an EDGE specification (einsum.edge) into a Python script
that builds the same program as edge-core-ir IR objects (`edge_ir`). Your
script will be run, and its output checked mechanically against einsum.edge,
so faithfulness matters more than anything else.
{retry}
WHAT TO PRODUCE

1. `{names['builder']}` -- REQUIRED. Constructs an `edge_ir.ir.program.Program`
   and, under `if __name__ == "__main__":`, writes
   `program.model_dump_json(indent=2)` to stdout. It must run with only
   edge-core-ir on the path.

2. `{names['functions']}` -- ONLY IF the spec names an operator the default
   registry does not have (a hyphenated name like `pick-admissible-edge`).
   Define `{names['registry']}()` returning the default registry plus those
   names, as the max-flow translation below does. Alias an existing
   implementation where the spec's meaning matches one; `1(name)` in a
   populate means ANY candidate, which is `select-any`.

RULES -- each one is checked

1. einsum.edge is the source of truth. Do not "fix" the algorithm. If the IR
   cannot express something exactly, express the closest thing and say so in a
   comment at that Einsum; never silently change meaning.

2. Each labelled Einsum (`# E01: ...`) lowers to ONE IR Einsum writing that
   Einsum's output tensor with the same output ranks, in label order (a
   `cases` statement is one Einsum too: rule 7). Never introduce a
   tensor the spec does not write. Where the IR needs steps, write them as
   labelled parenthesized parts of the same Einsum -- AnonymousTensor with
   BinaryApp labels, specs flat on the Einsum -- as max-flow's E06 and E11
   do. A unary on an expression is the paper's degenerate Map against 1
   (merge take_left, compute = the unary); ||T|| is `Occupancy`; a shape
   read as a value, like `|R|`, is
   `RankValue(expr=RankConstantShapeSym(name="|R|"))`, never a new input
   tensor. Put a
   `# E07` comment above each Einsum.

3. Every `compute(merge)` pair the spec writes after `::` must appear on that
   Einsum's IR nodes as a Map (`/\\`) or Reduce (`\\/`) spec, with these names:
     compute: {compute}
     merge:   {merge}
   The merge operator decides WHERE a value exists. Getting it wrong changes
   the algorithm while usually leaving small examples with the right answer,
   which is why this is compared structurally.

4. Named operators (hyphenated) appear exactly where the spec writes them and
   nowhere else. Do not invent a name to fill a slot.

5. Declare every tensor einsum.edge declares, with the same ranks, data type
   and empty value. IR tensor names must match ^[A-Z][A-Za-z0-9_]*$; if the
   spec writes a lower-case name (`delta`), capitalise it (`Delta`) and
   nothing else.

6. Case statements, inner cascades, macros and conditional cascades have
   IR of their own (local patches in this edge-core-ir checkout; none of the
   worked translations below uses them, so follow this rule exactly).

   CASES. `Z_{{...}} = cases:` followed by one arm per line,
   `<expression> if <condition>` or `<expression> otherwise`, is ONE Einsum
   whose `expression` is `Cases(arms=[CaseArm(...), ...])`, arms in the
   order written (the first arm whose condition holds claims a point):
     from edge_ir.ir.einsum import CaseArm, Cases
     CaseArm(expression=<the arm's expression tree>,
             specs=[<the arm's own Map/Reduce specs; labels start at 1 per arm>],
             where=<condition on rank variables>, when=<condition on tensor values>)
   - a condition on rank variables (`n = j+1`, `u != s`) is `where`: an
     `edge_ir.ir.predicate.PredicateComparison(lhs, op, rhs)` over rank
     expressions, joined with `LogicalAnd(operands=[...])` for `and`;
   - a condition on a tensor's value (`TopDown_i == True`) is `when`: an
     `edge_ir.ir.stopping.Comparison` of two `TensorProjectionValue`s (a
     literal is a zero-rank `Lit_...` declaration carrying `value`);
   - `otherwise` is an arm with neither; an arm written `empty` has
     `expression=None` (its region gets no value);
   - an arm written as a function call, `min(X_..., Y_...)`, is a Map:
     `BinaryApp(label=1, lhs=X, rhs=Y)` with a MapSpec whose compute is the
     function. The spec states no merge for it: use `intersect`, and say so
     in a comment at that Einsum;
   - the Einsum's own `specs` stay `[]` unless the statement has a populate.
   A `cases:` in the Initializations section is an initialization Einsum
   built the same way.

   INNER CASCADES. The Einsums between `- Begin inner cascade` and the
   `<><> : ...` line that ends it are ONE entry of the enclosing cascade's
   `einsums` list: a `NestedCascade(einsums=[...], stopping_conditions=[the
   <><> condition], iterative_rank=IterativeRankSpec(rank_variable=...))`.
   Give the outer cascade its `iterative_rank` too. A stopping condition on
   a rank variable (`j == J`) compares two `RankExpressionValue`s; a rank's
   shape read as a coordinate (`J-1`) is
   `RankArith(RankConstantShapeSym(name=<that rank's declared shape>) - 1)`.
   Declare a rank with the shape the spec gives it (`I = N-1` has shape
   "N-1"), the generational rank included when the spec gives it one.

   MACROS AND CONDITIONAL CASCADES. A `- Macro NAME(inputs) -> outputs`
   section is a template: build it once as
   `edge_ir.ir.macro.MacroDefinition(name, inputs, outputs, body)`, its body
   written exactly as the section writes it (formal names and all, one
   Einsum per label, in label order), and get an invocation's Einsums from
   `edge_ir.ir.macro.expand(defn, actual_inputs, actual_outputs)`. A
   labelled multi-output statement
     (Out1_{{...}}, Out2_{{...}}) = cases:
         NAME-A(args...)   if <condition>
         NAME-B(args...)   if <condition>
   is ONE entry of the cascade's `einsums` list, and no Einsum of its own:
   `ConditionalCascade(arms=[ConditionalArm(when=<condition>,
   einsums=expand(...), macro="NAME-A"), ...])`, arms in the order written.
   A formal parameter the macro body WRITES but its header does not list as
   an output is still bound by the call (pass it in `inputs`). Declare only
   the ACTUAL tensors (the ones einsum.edge declares); a formal name is
   never a declaration. An arm must hold exactly the expansion: the check
   matches each label of the macro's body to the expanded Einsum that
   writes what the call binds its output to.

   CONSTANTS. A line of the `- Constants` section, `alpha = 15`, is a
   zero-rank declaration carrying that value, named with a capital
   (`Alpha`): `TensorDeclaration(name="Alpha", ranks=[], data_type=...,
   empty_value=None, value=15)`. Read it as `InputTensor`. It is not an
   input: nothing supplies it.

   AN OPERATION WITH NO ACTION. `TB_i = X_i . (Y_i / alpha) :: /\ >(∩)`
   writes two operations and one action. The actions after `::` belong to
   the `.` operations, in order. An operation written with its own glyph
   inside the expression (`/`, `+`, `-`, `*`) and no action states a compute
   and no merge: lower it as a labelled Map with that compute and the
   paper's default merge, `pass_through` ("If a particular operation label
   does not contain a Merge operator, the EDGE machinery applies the Compute
   operator to every point in the iteration space", section 7.3.4), and say
   so in a comment at that Einsum.

7. Reply with each file in its own fenced block whose info string names it:

```python file={names['builder']}
...
```

{ref_text}

=== THE SPECIFICATION TO TRANSLATE: einsum.edge ===
{Path(edge).read_text()}

=== THE TUTORIAL IT COMES FROM (context only; einsum.edge wins) ===
{Path(tutorial).read_text()}
"""


# ---------------------------------------------------------------- reply ---

_FENCE = re.compile(r"^```(?P<info>[^\n]*)\n(?P<body>.*?)\n```[ \t]*$",
                    re.DOTALL | re.MULTILINE)
_NAME = re.compile(r"([A-Za-z0-9_\-]+\.(?:py|json))")


def parse_reply(text: str, slug: str) -> tuple[dict[str, str], list[str]]:
    """{file name: contents} from a pasted reply, and any problems.

    A file is named by its fence's info string (```python file=x.py) or, as
    chats often render it, by a heading or bold line just above the fence.
    Only the three file names the prompt asks for are accepted, so a reply
    cannot drop arbitrary files into the spec directory.
    """
    names = file_names(slug)
    allowed = {names["builder"], names["functions"]}
    files: dict[str, str] = {}
    problems: list[str] = []
    for m in _FENCE.finditer(text):
        # The line above the fence, for replies that name a file in a heading
        # or bold line. Back-to-back fences have no such line, which is fine:
        # their info strings carry the name.
        above = text[:m.start()].rstrip("\n").rsplit("\n", 1)[-1]
        found = _NAME.search(m.group("info")) or (
            None if above.startswith("```") else _NAME.search(above))
        if not found:
            continue
        name = found.group(1)
        if name not in allowed:
            problems.append(f"ignored a block named {name}; expected one of "
                            f"{sorted(allowed)}")
            continue
        files[name] = m.group("body") + "\n"
    if names["builder"] not in files:
        problems.insert(0, f"no `{names['builder']}` block found. Paste the "
                           f"whole reply, including the ``` fences.")
    return files, problems
