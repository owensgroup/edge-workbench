# -*- coding: utf-8 -*-
"""Does the tutorial's cascade say the same thing as the author's einsum.edge?

WHY THIS EXISTS
---------------
An author now hands the workbench two descriptions of one algorithm: the
tutorial, which readers see, and `einsum.edge`, which the IR is built from and
checked against. The page's formulas are rendered from the IR. So if the two
disagree, the page shows a cascade the tutorial beside it does not contain,
and the check that the IR matches `einsum.edge` makes that look trustworthy.

Both are sources of truth. Neither may silently win, so a disagreement is a
finding, and the author decides which one is wrong.

WHAT IS COMPARED
----------------
The tutorial writes LaTeX; `einsum.edge` writes ASCII. Glyphs are normalised
to the ASCII surface (`\\bigwedge` -> `/\\`, `\\cap` -> `∩`, `\\leftarrow` ->
`<-`, ...) and then both sides go through the same readers in
`spec_surface`. Compared:

  * declarations   ranks, data type and empty value of every tensor the
                   TUTORIAL declares (intermediates declared only in
                   einsum.edge are the house convention, not a finding)
  * initialization each line, whitespace ignored
  * cascade        in order: output tensor, generation, operand tensors,
                   every `compute(merge)` and every named operator
  * stopping       the condition, whitespace ignored

A glyph this table has not learned is kept verbatim, so it shows up as a
disagreement rather than being dropped. A half-reader that quietly skips what
it cannot read would be worse than none.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from edge_workbench import spec_surface as ss
from edge_workbench import tutorial as tut

# Order matters: longer commands before their prefixes (\leq before \le).
_LATEX = [
    # Spacing first: `\ ` would otherwise eat the backslash of a `/\ ` this
    # table has just produced.
    (r"\,", " "), (r"\;", " "), (r"\ ", " "), (r"\!", ""), (r"\quad", " "),
    (r"\_", "_"), (r"\ast", "*"),
    (r"\textstyle", ""), (r"\displaystyle", ""),
    (r"\bigwedge", "/\\"), (r"\bigvee", "\\/"),
    (r"\cap", "∩"), (r"\cup", "∪"),
    (r"\leftarrow", "<-"), (r"\rightarrow", "->"), (r"\to", "->"),
    (r"\left", ""), (r"\right", ""),          # sizing, and before \le below
    (r"\equiv", "=="), (r"\neq", "!="), (r"\geq", ">="), (r"\leq", "<="),
    (r"\ge", ">="), (r"\le", "<="),
    (r"\lll", "<<<"), (r"\ll", "<<"),
    (r"\min", "min"), (r"\max", "max"),
    (r"\cdot", "."), (r"\neg", "not "),
    (r"\lVert", "||"), (r"\rVert", "||"),
    (r"\lvert", "|"), (r"\rvert", "|"), (r"\vert", "|"),
    (r"\delta", "delta"), (r"^*", "*"),
    (r"\diamond", "<>"), (r"\infty", "inf"),
    (r"\lfloor", "floor("), (r"\rfloor", ")"),
    (r"\lbrace", "{"), (r"\rbrace", "}"), (r"\in", "in"),
]


def latex_to_surface(line: str) -> str:
    """One LaTeX cascade line, in einsum.edge's ASCII vocabulary."""
    s = line.strip()
    s = s.replace("&", " ")              # alignment markers, anywhere
    s = re.sub(r"\\\\(\[[^\]]*\])?\s*$", "", s)        # trailing \\ or \\[4pt]
    s = re.sub(r"\\(?:text|texttt|mathbf|mathrm|textbf|operatorname|mathbin|mathrel)\{([^}]*)\}",
               r"\1", s)
    for cmd, repl in _LATEX:
        s = s.replace(cmd, repl)
    # A rank written with its value, `F_{i \equiv 1,u,v}`, is `F_{1,u,v}`.
    s = re.sub(r"\b[a-z]\s*==\s*(?=\d)", "", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Line:
    """One statement of a cascade, from either side."""

    text: str
    label: str | None = None          # einsum.edge's E-number, when known

    @property
    def einsum(self) -> ss.SurfaceEinsum:
        return ss._analyse(self.label or "?", self.text)

    def key(self) -> tuple[str, str]:
        e = self.einsum
        gen = e.output_ranks[0].replace(" ", "") if e.output_ranks else ""
        return (e.output.lower(), gen)

    def name(self) -> str:
        e = self.einsum
        head = f"{e.output}_{{{', '.join(e.output_ranks)}}}"
        return f"{self.label} {head}" if self.label else head


@dataclass
class Sides:
    declarations: dict[str, ss.SurfaceDeclaration]
    initialization: list[str]
    cascade: list[Line]
    stopping: list[str]


# ------------------------------------------------------------- readers ---

def read_tutorial(md: Path) -> Sides:
    block = tut._block_scalar(Path(md).read_text(), "edge_expression")
    if block is None:
        raise tut.TutorialError(f"{md} has no `edge_expression:` block")

    section = "cascade"
    decls: dict[str, ss.SurfaceDeclaration] = {}
    init: list[str] = []
    cascade: list[Line] = []
    stop: list[str] = []

    pending: list[str] = []          # a `cases` block spans several lines
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("$$") or line.startswith(r"\begin{aligned}") \
                or line.startswith(r"\end{aligned}"):
            continue
        if r"\triangleright" in line:
            low = line.lower()
            section = ("tensors" if "tensors" in low else
                       "init" if "initiali" in low else "cascade")
            continue
        if pending or r"\begin{cases}" in line or line.rstrip().endswith("="):
            pending.append(line)
            if r"\end{cases}" in line:
                cascade.append(Line(_cases(pending)))
                pending = []
            continue

        text = latex_to_surface(line)
        if not text:
            continue
        if text.startswith("<>"):
            stop.append(text)
        elif section == "tensors":
            m = ss.DECL_RE.match(text.replace("empty=", "empty = "))
            if m:
                name, ranks, dtype, empty = m.groups()
                decls[name] = ss.SurfaceDeclaration(
                    name=name,
                    ranks=tuple(r.split("=")[0].strip()
                                for r in ranks.split(",")),
                    data_type=dtype.lower(), empty=empty)
        elif section == "init":
            init.append(text)
        elif ss.HEAD_RE.match(text):
            # Only lines that write a tensor. A definition such as the stamp
            # function `\sigma(depth, r) = ...` is not part of the cascade.
            cascade.append(Line(text))
    return Sides(decls, init, cascade, stop)


def _cases(lines: list[str]) -> str:
    """A LaTeX `cases` block, as one line naming only its output."""
    head = latex_to_surface(lines[0].split(r"\begin{cases}")[0])
    return f"{head} cases"


def read_edge(path: Path) -> Sides:
    text = Path(path).read_text()
    decls = ss.parse_declarations(path)
    surface = ss.parse_edge_file(path)

    init: list[str] = []
    stop: list[str] = []
    section = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if raw.strip().startswith("- "):
            low = raw.lower()
            section = ("init" if "initiali" in low else
                       "cascade" if "einsum" in low else "tensors")
            continue
        if not line:
            continue
        if line.startswith("<>"):
            stop.append(line)
        elif section == "init" and "=" in line:
            init.append(line)

    cascade = []
    for label in sorted(surface):
        e = surface[label]
        body = e.text
        if "cases" in body:
            body = body.split("cases")[0] + "cases"
        cascade.append(Line(body, label))
    return Sides(decls, init, cascade, stop)


# ------------------------------------------------------------- compare ---

def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s).replace("||", "|")


def _ops(line: Line) -> Counter:
    specs = ss.parse_specs(line.text)
    return Counter((s.action, s.label, s.compute, s.merge) for s in specs)


def _fmt_ops(c: Counter) -> str:
    if not c:
        return "(none)"
    quant = {"map": "/\\", "reduce": "\\/"}
    return " ".join(
        quant[a] + (f"^{lb}" if lb else "") + f" {comp}({merge})"
        for (a, lb, comp, merge) in sorted(c, key=lambda t: (t[1] or 0, t[0])))


def compare(md: Path, edge: Path) -> list[str]:
    """Every way the tutorial and einsum.edge disagree. Empty means agree."""
    t, e = read_tutorial(md), read_edge(edge)
    out: list[str] = []

    for name, td in sorted(t.declarations.items()):
        ed = e.declarations.get(name)
        if ed is None:
            out.append(f"tensor {name}: declared in the tutorial, not in "
                       f"einsum.edge")
            continue
        if td.ranks != ed.ranks:
            out.append(f"tensor {name}: tutorial ranks {list(td.ranks)}, "
                       f"einsum.edge ranks {list(ed.ranks)}")
        if td.data_type[:3] != ed.data_type[:3]:
            out.append(f"tensor {name}: tutorial type {td.data_type}, "
                       f"einsum.edge type {ed.data_type}")
        if ss.normalise_empty(td.empty) != ss.normalise_empty(ed.empty):
            out.append(f"tensor {name}: tutorial empty = {td.empty}, "
                       f"einsum.edge empty = {ed.empty}")

    ti, ei = [_flat(x) for x in t.initialization], [_flat(x) for x in e.initialization]
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(a=ti, b=ei).get_opcodes():
        if op == "equal":
            continue
        out.append(
            "initialization: tutorial has "
            f"{t.initialization[a1:a2] or '(nothing)'}, einsum.edge has "
            f"{e.initialization[b1:b2] or '(nothing)'}")

    tk = [ln.key() for ln in t.cascade]
    ek = [ln.key() for ln in e.cascade]
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(
            a=tk, b=ek, autojunk=False).get_opcodes():
        if op == "equal":
            for tl, el in zip(t.cascade[a1:a2], e.cascade[b1:b2]):
                out += _compare_line(tl, el)
            continue
        tutorial_side = [ln.name() for ln in t.cascade[a1:a2]]
        edge_side = [ln.name() for ln in e.cascade[b1:b2]]
        if op == "delete":
            out.append(f"cascade: the tutorial writes {tutorial_side}, which "
                       f"einsum.edge does not have")
        elif op == "insert":
            out.append(f"cascade: einsum.edge writes {edge_side}, which the "
                       f"tutorial does not have")
        else:
            out.append(f"cascade: where einsum.edge writes {edge_side}, the "
                       f"tutorial writes {tutorial_side}")

    if [_flat(x) for x in t.stopping] != [_flat(x) for x in e.stopping]:
        out.append(f"stopping condition: tutorial {t.stopping}, einsum.edge "
                   f"{e.stopping}")
    return out


def _operands(text: str) -> Counter:
    """Tensors read on the right-hand side, lower-cased.

    Any name carrying a subscript, whatever its case: einsum.edge writes
    `delta`, and `spec_surface`'s capitalised-name reader would miss it.
    """
    rhs = text.split("=", 1)[1] if "=" in text else text
    rhs = rhs.split("::", 1)[0]
    return Counter(m.lower() for m in re.findall(r"\b([A-Za-z][A-Za-z0-9]*)_", rhs))


def _compare_line(t: Line, e: Line) -> list[str]:
    out = []
    te, ee = t.einsum, e.einsum
    where = e.name()
    if te.output != ee.output:
        out.append(f"{where}: tutorial names the output {te.output}")
    if [r.replace(" ", "").replace("*", "") for r in te.output_ranks] != \
            [r.replace(" ", "").replace("*", "") for r in ee.output_ranks]:
        out.append(f"{where}: tutorial writes ranks {list(te.output_ranks)}, "
                   f"einsum.edge {list(ee.output_ranks)}")
    to, eo = _operands(t.text), _operands(e.text)
    if to != eo:
        out.append(f"{where}: operands differ -- tutorial reads "
                   f"{sorted(to.elements())}, einsum.edge reads "
                   f"{sorted(eo.elements())}")
    tops, eops = _ops(t), _ops(e)
    if tops != eops:
        out.append(f"{where}: operators differ -- tutorial {_fmt_ops(tops)}, "
                   f"einsum.edge {_fmt_ops(eops)}")
    if set(te.named_ops) != set(ee.named_ops):
        out.append(f"{where}: named operators differ -- tutorial "
                   f"{sorted(te.named_ops)}, einsum.edge {sorted(ee.named_ops)}")
    return out
