# -*- coding: utf-8 -*-
"""Check a prepared artifact whose gaps a model filled.

`prepare` reads what a tutorial states and names what it does not. Something
then fills those gaps -- today a person, shortly a model reading the same
tutorial. Either way the result arrives as prose and data that nothing has
checked, and it goes on to decide what a reader is told an algorithm does.

So this is the gate between "a model produced something plausible" and "the
build will show it to people".

WHAT CAN AND CANNOT BE CHECKED
------------------------------
Not accuracy. No test can tell whether "an edge is downhill when d(u) = d(v)+1"
is a good explanation of E08. That is review, and review is the point -- these
checks exist to make review CHEAP, by clearing away everything mechanical so
a reviewer spends attention on the prose rather than on whether the keys line
up.

What can be checked, and is:

  COVERAGE      every Einsum has a meaning, every gap is addressed. A model
                that quietly skipped six Einsums looks exactly like one that
                did the job, until someone counts.

  RELEVANCE     a meaning for E17 that never mentions `AdmPost`, or
                admissibility, or anything E17 touches, is about some other
                Einsum. This is the dominant failure of splitting
                phase-grouped prose per Einsum: the sentences are all real,
                and some are attached to the wrong step. Cheap to catch,
                because the IR says exactly which tensors an Einsum reads and
                writes.

  SOUNDNESS     an example that claims solutions can be checked against its
                own matrix without running anything. For exact cover: do the
                claimed rows actually cover every column exactly once?

  PROVENANCE    which fields a model wrote. A reviewer who knows that
                `meanings` is model-written and `example` is the author's
                reads them with different eyes, and that is a better use of
                their time than reading both the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

MODEL = "model"
AUTHOR = "author"


@dataclass(frozen=True)
class Finding:
    """One thing wrong, and which field it is wrong in."""

    field: str
    detail: str

    def __str__(self) -> str:
        return f"{self.field}: {self.detail}"


# ---------------------------------------------------------------- helpers --

def _projections(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("kind") == "input" and "proj" in node:
            out.append(node["proj"])
        if node.get("kind") == "occupancy" and "operand" in node:
            out.append(node["operand"])
        for value in node.values():
            _projections(value, out)
    elif isinstance(node, list):
        for value in node:
            _projections(value, out)


def tensors_touched(program: dict, cascade: dict) -> dict[str, set[str]]:
    """label -> every tensor that Einsum writes or reads.

    Aliases are applied so prose saying `delta` matches an IR writing `Delta`.

    ZERO-RANK SCALARS ARE EXCLUDED. `Zero`, `One`, `FalseConst`, `MinIdentity`
    are how the IR encodes literals in operand position; no author writes
    prose about them, and `One` matches the English word "one" in any sentence
    that uses it -- which is how a check starts flagging correct writing.
    """
    alias = cascade.get("displayNames", {})
    scalars = {
        d["name"] for d in program.get("declarations", [])
        if not d.get("ranks")
    }
    nodes = program["main_edge"]["cascade"]["einsums"]
    out: dict[str, set[str]] = {}
    for label, idx in (cascade.get("labels") or {}).items():
        names: set[str] = set()
        for i in (idx if isinstance(idx, list) else [idx]):
            einsum = nodes[i]
            if einsum["output_tensor"] not in scalars:
                names.add(alias.get(einsum["output_tensor"],
                                    einsum["output_tensor"]))
            projections: list[dict] = []
            _projections(einsum["expression"], projections)
            for proj in projections:
                if proj["tensor"] in scalars:
                    continue
                names.add(alias.get(proj["tensor"], proj["tensor"]))
        out[label] = names
    return out


def _named(text: str, names: set[str]) -> set[str]:
    """Which of these tensors the prose names, as whole words.

    Only names of three characters or more. `D`, `E`, `F` and `R` match
    ordinary prose constantly, and a signal that fires on every sentence is
    not a signal.
    """
    low = text.lower()
    return {
        n for n in names
        if len(n) >= 3 and re.search(rf"\b{re.escape(n.lower())}\b", low)
    }


# ----------------------------------------------------------------- checks --

def check(artifact: dict, program: dict | None = None,
          cascade: dict | None = None) -> list[Finding]:
    """Everything mechanically checkable about a filled-in artifact."""
    findings: list[Finding] = []

    gaps = artifact.get("gaps")
    if gaps:
        findings.append(Finding(
            "gaps",
            f"{len(gaps)} gap(s) still unfilled: "
            + "; ".join(g.split(":")[0] for g in gaps)
        ))

    findings += _check_example(artifact.get("example"))
    if program and cascade:
        findings += _check_meanings(artifact, program, cascade)
    findings += _check_provenance(artifact)
    return findings


def _check_example(example: dict | None) -> list[Finding]:
    if not example:
        return [Finding("example", "absent, so nothing can be run or checked")]

    out: list[Finding] = []
    kind = example.get("kind", "graph")

    if kind == "matrix":
        matrix = example.get("matrix") or []
        rows = example.get("rows", len(matrix))
        cols = example.get("columns", len(matrix[0]) if matrix else 0)
        if len(matrix) != rows:
            out.append(Finding("example",
                               f"declares {rows} rows but the matrix has "
                               f"{len(matrix)}"))
        bad = [i for i, line in enumerate(matrix) if len(line) != cols]
        if bad:
            out.append(Finding("example",
                               f"rows {bad} are not {cols} columns wide"))

        # Solutions can be checked against the matrix, with no run at all.
        for rowset in (example.get("expect") or {}).get("solutions", []):
            covered: list[int] = []
            for r in rowset:
                if r >= len(matrix):
                    out.append(Finding("example",
                                       f"solution names row {r}, which does "
                                       f"not exist"))
                    break
                covered += [c for c, v in enumerate(matrix[r]) if v]
            else:
                if sorted(covered) != list(range(cols)):
                    out.append(Finding(
                        "example",
                        f"rows {rowset} are published as a solution but cover "
                        f"{sorted(covered)}, not every column exactly once"
                    ))
    elif kind == "instance":
        # Stated in the program's own inputs. Whether they are the RIGHT
        # inputs needs the program, so `verifier.instance_problems` does
        # that; here only the shape.
        for field in ("extent", "tensors"):
            if not isinstance(example.get(field), dict):
                out.append(Finding("example", f"missing {field!r}"))
        if "answer" not in (example.get("expect") or {}):
            out.append(Finding(
                "example",
                "no `expect.answer`: the tutorial's published answer is what "
                "the run is checked against"))
    elif kind == "graph":
        for field in ("vertices", "source", "sink", "capacities"):
            if field not in example:
                out.append(Finding("example", f"missing {field!r}"))
    else:
        out.append(Finding("example", f"unknown kind {kind!r}"))

    if not (example.get("expect") or {}):
        out.append(Finding(
            "example",
            "no `expect`: the example can be run but its answer cannot be "
            "checked against anything the author published"
        ))
    return out


def _check_meanings(artifact: dict, program: dict,
                    cascade: dict) -> list[Finding]:
    meanings = artifact.get("meanings") or {}
    touched = tensors_touched(program, cascade)
    labels = set(cascade.get("labels") or {})

    out: list[Finding] = []
    missing = sorted(labels - set(meanings))
    if missing:
        out.append(Finding("meanings",
                           f"no meaning for {missing}"))

    extra = sorted(set(meanings) - labels - {"init", "stop"})
    if extra:
        out.append(Finding("meanings",
                           f"meanings for {extra}, which are not Einsums in "
                           f"this cascade"))

    for label in sorted(labels & set(meanings)):
        text = meanings[label]
        if len(text.strip()) < 15:
            out.append(Finding("meanings",
                               f"{label}'s meaning is too short to say "
                               f"anything: {text!r}"))
    return out


# THE TENSOR-NAME RELEVANCE CHECK IS GONE. Its record, in full:
#
#   Attempt 1, "a meaning should NAME a tensor its Einsum touches": fired on
#   four of max-flow's own correct meanings, because a good meaning describes
#   the problem ("total flow arriving at each vertex") and names no tensor.
#
#   Attempt 2, inverted, "a meaning naming a tensor belonging to some OTHER
#   Einsum": survived longer because it fired on nothing. Then it was
#   measured. Swapping each of the 276 pairs of max-flow's 24 meanings and
#   re-running produced 0 findings -- every pair. Same reason as attempt 1: if
#   good prose names no tensors, there is nothing to contradict.
#
#   Then it met exact cover, whose tensors include `Row` and `Path`, and
#   produced ELEVEN findings on an answer whose every meaning was correct --
#   because "row" and "path" are the English words this algorithm is about.
#   Excluding them by name would have been the third patch on an idea with a
#   measured true-positive rate of zero.
#
# A check with no measured true positives and eleven false positives is worse
# than no check: it trains a reader to skim the findings list, which is where
# the real ones will be. `check_citation_order` is the replacement, and it is
# honest about its own reach.


def _check_provenance(artifact: dict) -> list[Finding]:
    prov = artifact.get("provenance") or {}
    filled = [f for f in ("example", "meanings", "tensorNotes")
              if artifact.get(f)]
    unstated = [f for f in filled if f not in prov]
    if unstated:
        return [Finding(
            "provenance",
            f"{unstated} do not say whether an author or a model wrote them. "
            f"A reviewer reads those differently, and cannot here."
        )]
    return []


################################################################################
# the citation check
################################################################################

def _flat(text: str) -> str:
    """Collapse whitespace, so a re-wrapped quotation still matches.

    A model copying from a markdown file will not reproduce its line breaks,
    and failing a true citation over a newline would teach an author to delete
    the check rather than fix anything.
    """
    return re.sub(r"\s+", " ", text).strip().lower()


def check_quotes(artifact: dict, tutorial) -> list[Finding]:
    """Every model-written meaning must quote the tutorial, verbatim.

    THIS IS THE ONLY CHECK HERE THAT NEEDS NO JUDGEMENT AT ALL. Everything
    else in this module is a heuristic that can be argued with. A quotation
    either appears in the tutorial or it does not, and `in` decides.

    What it catches is the failure that matters: a model writing a meaning
    from what it knows about push-relabel rather than from what THIS tutorial
    says. That answer looks excellent -- fluent, correct about the algorithm
    in general, and wrong about the specification in front of it. Demanding a
    citation makes the difference visible, because prose recalled rather than
    read cannot produce a span that is actually on the page.

    It does NOT check that the quotation supports the meaning. A model can
    quote a real sentence and write something unrelated beside it. That is
    what a human reviewer is for -- and having the quotation sitting next to
    the meaning is exactly what makes that reading fast.
    """
    from pathlib import Path

    prov = artifact.get("provenance") or {}
    if prov.get("meanings") != MODEL:
        return []

    meanings = artifact.get("meanings") or {}
    quotes = artifact.get("quotes") or {}

    out: list[Finding] = []
    uncited = sorted(set(meanings) - set(quotes))
    if uncited:
        out.append(Finding(
            "quotes",
            f"{len(uncited)} model-written meaning(s) cite nothing: "
            f"{uncited[:6]}{'...' if len(uncited) > 6 else ''}. Prose with no "
            f"span behind it may be recalled rather than read."
        ))

    if tutorial is None or not Path(tutorial).exists():
        out.append(Finding(
            "quotes",
            f"cannot verify citations: no tutorial at {tutorial}"
        ))
        return out

    haystack = _flat(Path(tutorial).read_text())
    for label in sorted(quotes):
        quote = quotes[label]
        found = haystack.count(_flat(quote))
        # UNIQUENESS, NOT LENGTH, is what makes a citation locate something.
        # This was a 20-character minimum, which rejected E02's "extracts the
        # depth" -- a phrase that occurs exactly once in the tutorial and
        # names its Einsum precisely. Length was a proxy for "specific
        # enough"; occurring once is the thing itself.
        if found > 1:
            out.append(Finding(
                "quotes",
                f"{label} cites {quote!r}, which appears {found} times in the "
                f"tutorial, so it does not identify a passage"
            ))
        elif found == 0:
            out.append(Finding(
                "quotes",
                f"{label} cites a span that is NOT in the tutorial: "
                f"{quote[:80]!r}. Either it was reworded -- citations must be "
                f"verbatim -- or the meaning was written from memory."
            ))
    return out


def check_citation_order(artifact: dict, tutorial, labels: list[str] | None = None,
                         narrative: str = "edge_expression_walkthrough",
                         ) -> list[Finding]:
    """Citations should advance through the tutorial as the cascade advances.

    WHY THIS EXISTS: THE RELEVANCE CHECK CATCHES NOTHING
    ----------------------------------------------------
    `_check_meanings` flags a meaning naming a tensor that belongs to a
    different Einsum. Measured against max-flow's own 24 meanings, swapping
    any two of them and re-running gives 0 findings out of 276 pairs -- every
    single one. The reason is the same one that made the check get inverted in
    the first place: a good meaning describes the problem and names no tensor
    at all, so there is nothing for a tensor-name heuristic to contradict.

    A check with a measured detection rate of zero should not be presented as
    a defence, and misattribution is the dominant failure mode of splitting a
    phase-grouped walkthrough across two dozen Einsums. So this is the one
    that is actually meant to catch it.

    THE SIGNAL
    ----------
    A tutorial's walkthrough runs in the order the algorithm runs, and so does
    the cascade. So the character offset of E07's citation should fall before
    E08's. Swap two meanings and their citations swap with them, inverting a
    pair of offsets -- visible by arithmetic, with no understanding of the
    prose required at all.

    MEASURED TWICE, and the second number is the honest one.

    On a synthetic 24-phase walkthrough written entirely in algorithm order:
    276 of 276 pairwise swaps caught. That figure flattered the check, because
    the fixture was one narrative region and a real tutorial is not.

    On exact cover's actual model-written answer, 19 meanings citing three
    different sections: 109 of 171 pairwise swaps caught, and 7 of the 9
    adjacent swaps among the labels the check covers. Adjacent swaps are the
    ones that matter -- what a model plausibly gets wrong and a reader is
    least likely to notice.

    Both numbers beat the 0/276 of the tensor-name check above, which is the
    comparison that decided this replaced it. Neither is a guarantee.

    IT ONLY APPLIES INSIDE ONE NARRATIVE REGION, AND THAT IS A REAL LIMIT
    --------------------------------------------------------------------
    A tutorial is not one narrative. This one has nine top-level sections, and
    a good answer cites several of them: the walkthrough for the action steps,
    the tensor-declaration list for the state tensors, the intro for the
    overview. Run globally, the check produced five findings on an answer
    whose every meaning was correct, purely because citations moved between
    regions.

    Worse, ONE region is not a narrative at all. `problem_statement` lists the
    tensors in declaration order, so E19 -- which runs last -- cites `S`,
    listed first because S is the first tensor. There is no cascade order in a
    declaration list to be consistent with.

    So the check is scoped to the region named by `narrative`, and citations
    landing anywhere else are not compared. That gives up most of the coverage
    the 276/276 figure suggests: here it orders ten of nineteen meanings. It
    keeps the part that is sound, and a check that is sound on a third of the
    labels beats one that cries wolf on all of them.

    Overlapping spans are skipped too. E05 cites "append the new choice" and
    E06 cites "then append the new choice" -- the same clause, legitimately,
    since E06 is what performs the append. The second starts five characters
    earlier only because it includes the "then", which is a substring artefact
    and not a statement about order.

    It is a REPORT, not a proof: an inversion means "read this pair", not
    "this is wrong". The value is telling a reviewer WHICH two to look at.
    """
    from pathlib import Path

    quotes = artifact.get("quotes") or {}
    if len(quotes) < 2 or tutorial is None or not Path(tutorial).exists():
        return []

    haystack = _flat(Path(tutorial).read_text())
    lo, hi = _region(haystack, narrative)
    order = labels or sorted(quotes)

    placed: list[tuple[str, int, int]] = []
    for label in order:
        if label not in quotes:
            continue
        flat = _flat(quotes[label])
        at = haystack.find(flat)
        if lo <= at < hi:            # misses are check_quotes' business
            placed.append((label, at, at + len(flat)))

    out: list[Finding] = []
    for (a_lab, a_at, a_end), (b_lab, b_at, b_end) in zip(placed, placed[1:]):
        if max(a_at, b_at) < min(a_end, b_end):
            continue                 # the same clause; see the docstring
        if b_at < a_at:
            out.append(Finding(
                "quotes",
                f"{a_lab} cites a passage that comes AFTER {b_lab}'s in the "
                f"{narrative}, though {a_lab} runs first. Either that section "
                f"doubles back, or these two meanings are attached to each "
                f"other's Einsum -- read them as a pair."
            ))
    return out


def _region(haystack: str, key: str) -> tuple[int, int]:
    """The span of one top-level section of a tutorial's frontmatter.

    Sections are `key: |` at the top level of the YAML, and in the flattened
    text they appear in order, so a section runs until the next one starts. A
    key that is absent yields the whole document, which makes the order check
    behave as it did before regions existed rather than silently checking
    nothing.
    """
    starts = [(m.start(), m.group(1))
              for m in re.finditer(r"(?:^|(?<= ))([a-z_]+): \|", haystack)]
    for i, (at, name) in enumerate(starts):
        if name == key:
            return at, (starts[i + 1][0] if i + 1 < len(starts) else len(haystack))
    return 0, len(haystack)


def report(findings: list[Finding]) -> str:
    if not findings:
        return "nothing mechanically wrong; the prose still needs reading"
    lines = [f"{len(findings)} finding(s):"]
    lines += [f"  {f}" for f in findings]
    return "\n".join(lines)
