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
from dataclasses import dataclass, field
from pathlib import Path

from edge_workbench import spec_surface as ss
from edge_workbench import tutorial as tut

# Order matters: longer commands before their prefixes (\leq before \le).
_LATEX = [
    # Spacing first: `\ ` would otherwise eat the backslash of a `/\ ` this
    # table has just produced.
    (r"\,", " "), (r"\;", " "), (r"\ ", " "), (r"\!", ""), (r"\qquad", " "),
    (r"\quad", " "),
    # A multi-output statement's left-hand side, and a macro's `|->`.
    (r"\begin{pmatrix}", "("), (r"\end{pmatrix}", ")"), (r"\mapsto", "->"),
    (r"\alpha", "alpha"), (r"\beta", "beta"),
    (r"\_", "_"), (r"\ast", "*"),
    ("{-}", "-"), ("{+}", "+"),               # `N{-}1`: tight binary spacing
    (r"\textstyle", ""), (r"\displaystyle", ""),
    (r"\bigwedge", "/\\"), (r"\bigvee", "\\/"),
    (r"\cap", "∩"), (r"\cup", "∪"),
    (r"\wedge", " and "), (r"\land", " and "),   # in a case condition
    (r"\leftarrow", "<-"), (r"\rightarrow", "->"), (r"\to", "->"),
    (r"\left", ""), (r"\right", ""),          # sizing, and before \le below
    (r"\equiv", "=="), (r"\neq", "!="), (r"\geq", ">="), (r"\leq", "<="),
    (r"\ge", ">="), (r"\le", "<="),
    (r"\lll", "<<<"), (r"\ll", "<<"),
    (r"\min", "min"), (r"\max", "max"),
    (r"\cdot", "."), (r"\neg", "not "),
    (r"\lVert", "||"), (r"\rVert", "||"),
    (r"\lvert", "|"), (r"\rvert", "|"), (r"\vert", "|"),
    (r"\delta", "delta"), (r"\sigma", "sigma"), (r"^*", "*"),
    (r"\diamond", "<>"), (r"\infty", "inf"),
    (r"\lfloor", "floor("), (r"\rfloor", ")"),
    (r"\lbrace", "{"), (r"\rbrace", "}"), (r"\in", "in"),
]


def latex_to_surface(line: str) -> str:
    """One LaTeX cascade line, in einsum.edge's ASCII vocabulary."""
    s = line.strip()
    s = s.replace("&", " ")              # alignment markers, anywhere
    s = re.sub(r"\\\\(\[[^\]]*\])?\s*$", "", s)        # trailing \\ or \\[4pt]
    s = re.sub(r"\\(?:text|texttt|mathbf|mathrm|mathit|textbf|operatorname|mathbin|mathrel)\{([^}]*)\}",
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
    latex: str = ""                   # the tutorial's own LaTeX, when read there

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
    initialization_latex: list[str] = field(default_factory=list)
    stopping_latex: list[str] = field(default_factory=list)
    definitions: list[str] = field(default_factory=list)
    macros: dict[str, "MacroSide"] = field(default_factory=dict)


@dataclass
class MacroSide:
    """One macro, from either side: its header and its body's Einsums."""

    header: str                       # `NAME(formals) -> outputs`, ASCII
    cascade: list[Line]
    latex: str = ""                   # the tutorial's header, when read there


# ------------------------------------------------------------- readers ---

def _clean_latex(line: str) -> str:
    """One aligned line as LaTeX that stands on its own: no `&`, no `\\\\`."""
    s = re.sub(r"\\\\(\[[^\]]*\])?\s*$", "", line.strip())
    return s.replace("&", " ").strip()


def _clean_cases(lines: list[str]) -> str:
    """A `cases` block keeps its inner `&`s; only the outer one goes."""
    head, body = "\n".join(lines).split(r"\begin{cases}", 1)
    return (head.replace("&", " ").strip() + r" \begin{cases}"
            + re.sub(r"\\\\(\[[^\]]*\])?\s*$", "", body.strip()))


#: `- Cascade: Bottom-Up` in einsum.edge: which of the tutorial's cascades
#: this file transcribes, when it is not the one in `edge_expression`.
_CASCADE_LINE = re.compile(r"^-\s*Cascade\s*:\s*(.+?)\s*$",
                           re.MULTILINE | re.IGNORECASE)
_HEADING = re.compile(
    r"\\triangleright\s*\\textbf\{Extended Einsums?\s*(?:—|--|-|:)\s*([^}]*)\}")


def selected_cascade(edge: Path) -> str | None:
    """The cascade einsum.edge says it transcribes, or None for the
    tutorial's `edge_expression`.

    A tutorial may give several cascades for one problem (DO-BFS: top-down in
    `edge_expression`, bottom-up and hybrid under Variants). A page shows one
    cascade, so an author directory is one cascade: einsum.edge names it with
    a `- Cascade: <name>` line, where <name> is what follows `Extended Einsum
    —` in that cascade's heading in the tutorial.
    """
    m = _CASCADE_LINE.search(Path(edge).read_text())
    return m.group(1) if m else None


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _named_block(md: Path, name: str) -> str:
    """The `$$ ... $$` block whose heading is `Extended Einsum — <name>`."""
    text = Path(md).read_text()
    blocks = [b for b in re.findall(r"\$\$(.*?)\$\$", text, re.DOTALL)
              if r"\begin{aligned}" in b]
    named = [(h.group(1).strip(), b) for b in blocks
             for h in [_HEADING.search(b)] if h and h.group(1).strip()]
    same = [b for n, b in named if _name_key(n) == _name_key(name)]
    # A cascade given in full declares its tensors; a sketch that reuses
    # another block's declarations is not one a page can be built from.
    full = [b for b in same if re.search(r"\\textbf\{Tensors\}", b)]
    if len(full) != 1:
        known = sorted({n for n, b in named
                        if re.search(r"\\textbf\{Tensors\}", b)})
        raise tut.TutorialError(
            f"einsum.edge says `- Cascade: {name}`, and {md.name} has "
            f"{len(full)} cascade(s) headed `Extended Einsum — {name}` that "
            f"declare their tensors. Cascades it gives in full: {known}.")
    return "\n".join(line.strip() for line in full[0].splitlines())


_MACRO_HEADING = re.compile(r"\\triangleright\s*\\textbf\{MACRO\}")


def _macro_blocks(md: Path, cascade: str) -> dict[str, MacroSide]:
    """name -> the `▷ MACRO NAME(formals) ↦ outputs` blocks that belong to
    one cascade: those the tutorial gives after that cascade's block and
    before its next cascade. A tutorial may define a macro of the same name
    again for a later cascade (DO-BFS's compact hybrid redefines both).

    A header may break before its `↦`; the body follows it.
    """
    out: dict[str, MacroSide] = {}
    text = Path(md).read_text()
    flat = lambda b: "".join(b.replace("$", "").split())      # noqa: E731
    blocks = [b for b in re.findall(r"\$\$(.*?)\$\$", text, re.DOTALL)
              if r"\begin{aligned}" in b]
    start = next((k for k, b in enumerate(blocks)
                  if flat(cascade) and flat(cascade) in flat(b)), None)
    if start is None:
        return out
    for block in blocks[start + 1:]:
        if _HEADING.search(block):
            break                              # the next cascade
        if not _MACRO_HEADING.search(block) or r"\triangleright" not in block:
            continue
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()
                 and not ln.strip().startswith((r"\begin{aligned}",
                                                r"\end{aligned}"))]
        head: list[str] = []
        while lines and (not head or r"\mapsto" not in " ".join(head)):
            head.append(lines.pop(0))
        tex = " ".join(_clean_latex(h) for h in head)
        header = latex_to_surface(_MACRO_HEADING.sub("", tex))
        name = re.match(r"\s*([A-Za-z][A-Za-z0-9-]*)", header)
        if not name:
            continue
        body = _read_block("\n".join(lines))
        out.setdefault(name.group(1), MacroSide(header, body.cascade, tex))
    return out


def read_tutorial(md: Path, which: str | None = None) -> Sides:
    if which:
        block = _named_block(Path(md), which)
    else:
        block = tut._block_scalar(Path(md).read_text(), "edge_expression")
    if block is None:
        raise tut.TutorialError(f"{md} has no `edge_expression:` block")
    sides = _read_block(block)
    # The macros this cascade calls are written in blocks of their own.
    called = {c.macro for ln in sides.cascade
              for c in map(ss._call, ss.case_arms(ln.text))
              if ss.CONDITIONAL_RE.match(ln.text)}
    if called:
        given = _macro_blocks(Path(md), block)
        sides.macros = {n: m for n, m in given.items() if n in called}
    return sides


def _read_block(block: str) -> Sides:
    """One aligned block: its declarations, initialization, Einsums, stops."""

    section = "cascade"
    decls: dict[str, ss.SurfaceDeclaration] = {}
    init: list[str] = []
    cascade: list[Line] = []
    stop: list[str] = []
    init_tex: list[str] = []
    stop_tex: list[str] = []
    defs: list[str] = []

    # A long Einsum breaks before its `::`, and the action list is still it.
    lines: list[str] = []
    for raw in block.splitlines():
        if raw.strip().startswith("::") and lines:
            lines[-1] += " " + raw.strip()
        else:
            lines.append(raw)

    pending: list[str] = []          # a `cases` block spans several lines
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("$$") or line.startswith(r"\begin{aligned}") \
                or line.startswith(r"\end{aligned}"):
            continue
        if line.lstrip("& ").startswith(r"\diamond"):
            # A stopping condition may carry a trailing remark:
            # `\diamond\diamond : j \equiv J \qquad \triangleright end inner cascade`.
            line = re.split(r"\\q?quad\s*\\triangleright|\\triangleright", line)[0]
        if r"\triangleright" in line:
            low = line.lower()
            section = ("tensors" if "tensors" in low else
                       "init" if "initiali" in low else "cascade")
            continue
        if pending or r"\begin{cases}" in line or line.rstrip().endswith("=") \
                or r"\begin{pmatrix}" in line:
            pending.append(line)
            if r"\end{cases}" in line:
                if section == "init":
                    init.append(_cases(pending))
                    init_tex.append(_clean_cases(pending))
                else:
                    cascade.append(Line(_cases(pending),
                                        latex=_clean_cases(pending)))
                pending = []
            continue

        text = latex_to_surface(line)
        if not text:
            continue
        if text.startswith("<>"):
            stop.append(text)
            stop_tex.append(_clean_latex(line))
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
            # A line may hold several statements, `A = x,\quad B = y`.
            for piece in re.split(r",\s*\\q?quad\s*", _clean_latex(line)):
                piece_text = latex_to_surface(piece)
                if not piece_text or "user-specified" in piece_text:
                    continue                  # an input, not an assignment
                init.append(piece_text)
                init_tex.append(piece)
        elif ss.HEAD_RE.match(text) or ss.CONDITIONAL_RE.match(text):
            # Only lines that write a tensor. A definition such as the stamp
            # function `\sigma(depth, r) = ...` is not part of the cascade,
            # but it is what the cascade's `\sigma(...)` means.
            cascade.append(Line(text, latex=_clean_latex(line)))
        elif re.match(r"\\?[A-Za-z]+\s*\(.*\)\s*=", _clean_latex(line)):
            defs.append(_clean_latex(line))
    return Sides(decls, init, cascade, stop, init_tex, stop_tex, defs)


def _cases(lines: list[str]) -> str:
    """A LaTeX `cases` block in einsum.edge's one-line form:
    `Z_{0, j, n} = cases: <expr> if <cond> ; ... ; <expr> otherwise`."""
    text = "\n".join(lines)
    head_tex, _, body = text.partition(r"\begin{cases}")
    head = latex_to_surface(" ".join(head_tex.split()))
    body = body.split(r"\end{cases}")[0]
    arms = []
    for row in re.split(r"\\\\(?:\[[^\]]*\])?", body):
        if not row.strip():
            continue
        expr_tex, _, cond_tex = row.partition("&")
        expr = latex_to_surface(" ".join(expr_tex.split()))
        cond = latex_to_surface(" ".join(cond_tex.split()))
        cond = re.sub(r"^if\b\s*", "", cond).strip()
        if cond in ("o/w", "otherwise", ""):
            arms.append(f"{expr} otherwise")
        else:
            arms.append(f"{expr} if {cond}")
    return f"{head} cases: " + ss.ARM_SEP.join(arms)


def read_edge(path: Path) -> Sides:
    text = Path(path).read_text()
    decls = ss.parse_declarations(path)
    surface = ss.parse_edge_file(path)

    init: list[str] = []
    stop: list[str] = []
    section = None
    block: list[str] | None = None        # a `cases` block in the init section
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if block is not None:
            if line and raw[:1].isspace():
                block.append(line)
                continue
            init.append(ss.join_statement(block))
            block = None
        if raw.strip().startswith("- "):
            low = raw.lower()
            section = ("init" if "initiali" in low else
                       "cascade" if "einsum" in low or "cascade" in low
                       or "macro" in low else "tensors")
            continue
        if not line:
            continue
        if line.startswith("<>"):
            stop.append(line)
        elif section == "init" and re.search(r"=\s*cases\s*:?\s*$", line):
            block = [line]
        elif section == "init" and "=" in line:
            init.append(line)
    if block is not None:
        init.append(ss.join_statement(block))

    # The cascade's own statements: its Einsums and its multi-output case
    # statements, in label order. A macro's body is compared with the
    # tutorial's macro of the same name.
    own = {label: e.text for label, e in surface.items() if not e.macro}
    own.update({c.label: c.text for c in surface.conditionals})
    cascade = [Line(own[label], label) for label in sorted(own)]
    macros = {name: MacroSide(re.sub(r"(?i)^macro\s+", "", m.text),
                              [Line(surface[lb].text, lb)
                                       for lb in m.labels])
              for name, m in surface.macros.items()}
    return Sides(decls, init, cascade, stop, macros=macros)


# ------------------------------------------------------------- compare ---

def _flat(s: str) -> str:
    s = re.sub(r"\s+", "", s).replace("||", "|")
    if ss.is_cases(s):
        # Inside a case statement `=` and `==` are the same comparison, and
        # the colon after `cases` is optional.
        s = s.replace("==", "=").replace("cases:", "cases")
    return s


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


def _labelled(t: Sides, e: Sides) -> list[tuple[Line, str]]:
    """The tutorial's cascade lines, each with its einsum.edge E-number."""
    matcher = difflib.SequenceMatcher(a=[ln.key() for ln in t.cascade],
                                      b=[ln.key() for ln in e.cascade],
                                      autojunk=False)
    out = []
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            out += [(tl, el.label) for tl, el in
                    zip(t.cascade[a1:a2], e.cascade[b1:b2])]
    return out


def _key_of(latex: str) -> tuple[str, str] | None:
    """The tensor and generation a formula writes, or None if it writes none."""
    text = (_cases([latex]) if r"\begin{cases}" in latex
            else latex_to_surface(latex))
    return Line(text).key() if ss.HEAD_RE.match(text) else None


def _label_of(latex: str, t: Sides, labelled: list[tuple[Line, str]]) -> str | None:
    """Which Einsum a formula from the walkthrough is, or None."""
    text = latex_to_surface(latex)
    if text.startswith("<>"):
        return "stop"
    flat = _flat(text)
    for line, label in labelled:
        if _flat(line.text) == flat:
            return label
    if flat in {_flat(s) for s in t.initialization}:
        return "init"
    key = _key_of(latex)
    if key is None:
        return None
    # Written a little differently from `edge_expression`: its output says.
    same = [label for line, label in labelled if line.key() == key]
    if len(same) == 1:
        return same[0]
    if not same and key in {_key_of(s) for s in t.initialization_latex}:
        return "init"
    return None


def authored_meanings(md: Path, edge: Path) -> dict:
    """label -> {"graph": ..., "einsum": ...}, as the walkthrough states them.

    Each pair sits under its formula. The nearest formula that is an Einsum of
    this cascade is the one it explains, so an aside such as `$f(v,s) = -c$`
    between the two does not move it.
    """
    if selected_cascade(edge):
        # The walkthrough explains the `edge_expression` cascade. Another
        # cascade's meanings are prose around it, which the tutorial-data
        # step quotes; nothing is read from the walkthrough for it.
        return {}
    t, e = read_tutorial(md), read_edge(edge)
    labelled = _labelled(t, e)
    out: dict = {}
    for entry in tut.read_walkthrough_meanings(md):
        said = {k: entry[k] for k in ("graph", "einsum") if k in entry}
        label = next((found for found in (_label_of(x, t, labelled)
                                          for x in entry["equations"]) if found),
                     None)
        if label is None:
            shown = next(iter(said.values()))
            raise tut.TutorialError(
                f"the walkthrough's meaning {shown[:60]!r} does not follow a "
                f"formula from `edge_expression`, so it cannot be placed. Put "
                f"it right after the Einsum it explains.")
        if label in out and set(out[label]) & set(said):
            raise tut.TutorialError(
                f"the walkthrough explains {label} twice; keep one.")
        out.setdefault(label, {}).update(said)
    return out


def written_forms(md: Path, edge: Path) -> dict:
    """The formulas as the author wrote them, for the page to show.

    The IR is a lowering: it has no sigma, and it spells shorthand out in
    labelled parts, so a formula drawn from it is not the Einsum the author
    wrote. The tutorial's LaTeX is, and `compare` has already held it to
    einsum.edge. Keys are E-numbers, plus `init`, `stop` and `definitions`.
    """
    t, e = read_tutorial(md, selected_cascade(edge)), read_edge(edge)
    out: dict = {"definitions": t.definitions}
    for tl, label in _labelled(t, e):
        if tl.latex:
            out[label] = tl.latex
    for name in sorted(set(t.macros) & set(e.macros)):
        tm, em = t.macros[name], e.macros[name]
        for tl, label in _labelled(Sides({}, [], tm.cascade, []),
                                   Sides({}, [], em.cascade, [])):
            if tl.latex:
                out[label] = tl.latex
        out.setdefault("macros", {})[name] = tm.latex
    if len(t.initialization_latex) == 1:
        out["init"] = t.initialization_latex[0]
    elif t.initialization_latex:
        out["init"] = (r"\begin{array}{l} "
                       + r" \\ ".join(t.initialization_latex)
                       + r" \end{array}")
    if t.stopping_latex:
        out["stop"] = " ".join(t.stopping_latex)
    return out


def compare(md: Path, edge: Path) -> list[str]:
    """Every way the tutorial and einsum.edge disagree. Empty means agree."""
    t, e = read_tutorial(md, selected_cascade(edge)), read_edge(edge)
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

    out += _compare_cascades(t.cascade, e.cascade, "cascade")

    for name in sorted(set(t.macros) | set(e.macros)):
        tm, em = t.macros.get(name), e.macros.get(name)
        if em is None:
            out.append(f"macro {name}: the tutorial's cascade calls it, and "
                       f"einsum.edge has no `- Macro {name}(...)` section")
            continue
        if tm is None:
            out.append(f"macro {name}: einsum.edge has a section for it; the "
                       f"tutorial's cascade does not call a macro of that "
                       f"name, or gives no `MACRO {name}` block")
            continue
        if _flat(tm.header) != _flat(em.header):
            out.append(f"macro {name}: the headers differ -- tutorial "
                       f"`{tm.header}`, einsum.edge `{em.header}`")
        out += _compare_cascades(tm.cascade, em.cascade, f"macro {name}")

    if [_flat(x) for x in t.stopping] != [_flat(x) for x in e.stopping]:
        out.append(f"stopping condition: tutorial {t.stopping}, einsum.edge "
                   f"{e.stopping}")
    out += _constants(md, edge)
    return out


def _compare_cascades(tc: list[Line], ec: list[Line], what: str) -> list[str]:
    """Two lists of statements, in order, statement by statement."""
    out: list[str] = []
    tk = [ln.key() for ln in tc]
    ek = [ln.key() for ln in ec]
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(
            a=tk, b=ek, autojunk=False).get_opcodes():
        if op == "equal":
            for tl, el in zip(tc[a1:a2], ec[b1:b2]):
                out += _compare_line(tl, el)
            continue
        tutorial_side = [ln.name() for ln in tc[a1:a2]]
        edge_side = [ln.name() for ln in ec[b1:b2]]
        if op == "delete":
            out.append(f"{what}: the tutorial writes {tutorial_side}, which "
                       f"einsum.edge does not have")
        elif op == "insert":
            out.append(f"{what}: einsum.edge writes {edge_side}, which the "
                       f"tutorial does not have")
        else:
            out.append(f"{what}: where einsum.edge writes {edge_side}, the "
                       f"tutorial writes {tutorial_side}")
    return out


def _constants(md: Path, edge: Path) -> list[str]:
    """Every `- Constants` value is one the tutorial states.

    A constant is not in the tutorial's cascade (if it were it would be an
    initialization), so it is held to the prose: `alpha = 15` needs the
    tutorial to say `\\alpha = 15` somewhere. A value nobody published is a
    choice made in einsum.edge, and the page would run on it unannounced.
    """
    out = []
    said = re.sub(r"\s+", "", latex_to_surface(
        Path(md).read_text().replace("$", " ")))
    for name, value in ss.parse_constants(edge).items():
        if f"{name}={value}" not in said:
            out.append(f"constant {name}: einsum.edge sets {name} = {value}; "
                       f"the tutorial does not state that value. Say it in "
                       f"the tutorial (`\\{name} = {value}`) or remove it.")
    return out


def _operands(text: str) -> Counter:
    """Tensors read on the right-hand side, lower-cased.

    Any name carrying a subscript, whatever its case: einsum.edge writes
    `delta`, and `spec_surface`'s capitalised-name reader would miss it.
    """
    rhs = text.split("=", 1)[1] if "=" in text else text
    rhs = rhs.split("::", 1)[0]
    return Counter(m.lower() for m in re.findall(r"\b([A-Za-z][A-Za-z0-9]*)_", rhs))


def _compare_cases(t: Line, e: Line, where: str) -> list[str]:
    """Two case statements, arm by arm: expression and condition."""
    ta, ea = ss.case_arms(t.text), ss.case_arms(e.text)
    if [a.key() for a in ta] == [a.key() for a in ea]:
        return []
    out = []
    if len(ta) != len(ea):
        out.append(f"{where}: the tutorial's case statement has {len(ta)} "
                   f"arm(s), einsum.edge's has {len(ea)}")
    for k, (x, y) in enumerate(zip(ta, ea), 1):
        if x.key() != y.key():
            def show(a):
                return f"`{a.expr}` " + (f"if {a.cond}" if a.cond else "otherwise")
            out.append(f"{where}: arm {k} differs -- tutorial {show(x)}, "
                       f"einsum.edge {show(y)}")
    return out


def _compare_line(t: Line, e: Line) -> list[str]:
    out = []
    te, ee = t.einsum, e.einsum
    where = e.name()
    if ss.is_cases(t.text) or ss.is_cases(e.text):
        if te.output != ee.output:
            out.append(f"{where}: tutorial names the output {te.output}")
        if [r.replace(" ", "").replace("*", "") for r in te.output_ranks] != \
                [r.replace(" ", "").replace("*", "") for r in ee.output_ranks]:
            out.append(f"{where}: tutorial writes ranks "
                       f"{list(te.output_ranks)}, einsum.edge "
                       f"{list(ee.output_ranks)}")
        if ss.is_cases(t.text) != ss.is_cases(e.text):
            out.append(f"{where}: one side writes a case statement and the "
                       f"other does not")
        return out + _compare_cases(t, e, where)
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
