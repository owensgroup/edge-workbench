# -*- coding: utf-8 -*-
"""Check an author's algorithm and build its page: `edge_workbench check DIR`.

THE AUTHOR'S SIDE OF THE WORKFLOW
---------------------------------
An author writes three files in one directory:

    <name>.md      the tutorial, as it will appear on the website
    einsum.edge    the cascade in EDGE's ASCII surface form
    verifier.py    an independent way to get the same answers
                   (contract: edge_workbench/verifier.py)

and runs

    python3 -m edge_workbench check DIR

as many times as it takes. Each run does everything it can, reports every
problem it found, and says exactly what to do next. Two steps need a model,
and the workbench never calls one: it writes a prompt file, the author pastes
it into a chat, saves the reply where it says, and runs `check` again. The
reply is then checked like anything else an author wrote.

When nothing is left to fix, `DIR/index.html` is written. Nothing is ever
written there while a check is failing.

Everything the workbench generates goes in `DIR/workbench/`.

THE STAGES
----------
    inputs        the three files exist, and the verifier meets its contract
    tutorial      the tutorial's cascade says what einsum.edge says
    builder       [model] einsum.edge -> a Python builder for the IR
    program       the builder runs; the IR is valid and matches einsum.edge
    tutorial data [model] per-Einsum meanings, the worked example, styling
    instance      the worked example supplies exactly the program's inputs
    page          coverage, the verifier, and index.html
"""

from __future__ import annotations

from edge_workbench.cascade_shape import flat_nodes, stopping_conditions  # noqa: F401

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from edge_workbench import (
    approval,
    builder_prompt,
    domain_shape,
    prepare,
    propose,
    rank_kinds,
    review,
    spec_check,
    tensor_facts,
    tutorial as tut,
    tutorial_vs_edge,
    verifier,
)
from edge_workbench.paths import ROOT
from edge_workbench.spec_surface import parse_declarations, parse_edge_file

WORK = "workbench"

#: Coordinate operators that rank their candidates, under every spelling
#: upstream registers. Mapping one of these to random would change the
#: algorithm -- Algorithm X's E01 pops the DEEPEST entry, not any entry.
RANKED = {name for e in ("min", "max") for k in ("val", "coord")
          for name in (f"select-{e}-{k}", f"select_{e}_{k}", f"{e}-{k}-1")}


# ------------------------------------------------------------- layout ----

@dataclass
class Author:
    """Where everything is, for one author directory."""

    dir: Path
    tutorial: Path
    slug: str

    @property
    def edge(self) -> Path:
        return self.dir / "einsum.edge"

    @property
    def verifier(self) -> Path:
        return self.dir / "verifier.py"

    @property
    def work(self) -> Path:
        return self.dir / WORK

    @property
    def spec(self) -> Path:
        return self.work / "spec"

    @property
    def prompts(self) -> Path:
        return self.work / "prompts"

    @property
    def replies(self) -> Path:
        return self.work / "replies"

    @property
    def names(self) -> dict[str, str]:
        return builder_prompt.file_names(self.slug)

    @property
    def program_file(self) -> Path:
        return self.spec / f"{self.slug.replace('-', '_')}_program.json"

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.dir))
        except ValueError:
            return str(p)


def locate(directory: Path, tutorial: Path | None = None) -> Author:
    """The author directory, and which tutorial in it is THE tutorial.

    `tutorial` overrides the search. It exists because a tutorial often cannot
    move: the website keeps its collection flat -- fifteen `.md` files in one
    `_algorithms/` directory -- so a per-algorithm author directory beside
    them has no tutorial of its own to find, and relocating the tutorial to
    get one would change how the site is built.

    With the override, `einsum.edge` and `verifier.py` live next to the
    tutorial they describe and the tutorial stays where the site wants it.
    Provenance is unaffected: `prepare` resolves the path and reads the git
    SHA from the real file, wherever it is.
    """
    d = Path(directory).resolve()
    if not d.is_dir():
        raise SystemExit(f"no directory {d}")
    if tutorial is not None:
        md = Path(tutorial).resolve()
        if not md.is_file():
            raise SystemExit(f"no tutorial at {md}")
        return Author(dir=d, tutorial=md, slug=md.stem.replace("_", "-"))
    mds = [p for p in sorted(d.glob("*.md")) if p.name.lower() != "readme.md"]
    with_expr = [p for p in mds if "edge_expression:" in p.read_text()]
    candidates = with_expr or mds
    if len(candidates) != 1:
        raise SystemExit(
            f"expected exactly one tutorial .md in {d}, found "
            f"{[p.name for p in candidates] or 'none'}. Name one with "
            f"--tutorial if the tutorial lives outside this directory.")
    md = candidates[0]
    return Author(dir=d, tutorial=md, slug=md.stem.replace("_", "-"))


# ------------------------------------------------------------- report ----

@dataclass
class Stage:
    name: str
    state: str = "ok"                    # ok | fail | waiting | skipped
    summary: str = ""
    findings: list[str] = field(default_factory=list)
    next: list[str] = field(default_factory=list)
    #: Problems held back until later in the run (the verifier's approval,
    #: asked for once, at the end, so it covers the published answer too).
    deferred: list[str] = field(default_factory=list)


MARK = {"ok": "✓", "fail": "✗", "waiting": "…", "skipped": "-"}


def report(a: Author, stages: list[Stage], wrote: bool) -> str:
    lines = [f"edge-workbench check: {a.slug}", ""]
    for s in stages:
        lines.append(f"  {MARK[s.state]} {s.name:<14} {s.summary}")
    for s in stages:
        if s.findings:
            lines += ["", f"{s.name}: {len(s.findings)} problem(s)"]
            lines += [f"  - {f}" for f in s.findings]
    todo = [n for s in stages for n in s.next]
    lines.append("")
    if wrote:
        lines.append(f"index.html written: {a.rel(a.dir / 'index.html')}")
    else:
        lines.append("index.html NOT written.")
    if todo:
        lines += ["", "NEXT:"] + [f"  {i}. {t}" for i, t in enumerate(todo, 1)]
    return "\n".join(lines)


# ------------------------------------------------------------- stages ----

def stage_inputs(a: Author, committed_only: bool = False) -> Stage:
    s = Stage("inputs")
    for p, what in ((a.edge, "einsum.edge"), (a.verifier, "verifier.py")):
        if not p.exists():
            s.findings.append(f"{what} is missing from {a.dir}")
    if a.edge.exists() and not parse_edge_file(a.edge):
        s.findings.append("einsum.edge has no labelled Einsums (`# E01: ...`)")
    if a.verifier.exists():
        # Two separate questions, both always asked: does the verifier meet
        # its contract, and has a person approved exactly this text?
        s.findings += verifier.contract_problems(a.verifier, a.slug)
        unapproved, todo = approval.problems(a.dir, committed_only)
        if s.findings:
            s.findings += unapproved
            s.next += todo
        elif unapproved and not (a.dir / approval.LOCK).exists():
            # The verifier meets its contract and has never been approved
            # (a lock that is forged, or a verifier changed since approval,
            # still stops here at once: that is the case to be loud about).
            # Nothing
            # before the instance stage runs it, so carry on: the author is
            # asked to approve once, at the end, when the tutorial's
            # published answer is known and can be pinned in the same lock.
            s.state = "waiting"
            s.deferred = unapproved
            s.summary = ("verifier.py meets its contract; approval is asked "
                         "for once, at the end, so it covers the published "
                         "answer too")
            return s
        else:
            s.findings += unapproved
            s.next += todo
    s.state = "fail" if s.findings else "ok"
    said = verifier.declared(a.verifier) if a.verifier.exists() else {}
    s.summary = (f"{a.tutorial.name}, einsum.edge, verifier.py "
                 f"({said.get('KIND')}: {said.get('METHOD')}; approved"
                 + (f"; ledger from ${approval.LEDGER_ENV}"
                    if approval.ledger_overridden() and not committed_only
                    else "") + ")"
                 if not s.findings else "see below")
    return s


def stage_tutorial(a: Author) -> Stage:
    s = Stage("tutorial")
    try:
        s.findings = tutorial_vs_edge.compare(a.tutorial, a.edge)
    except tut.TutorialError as e:
        s.findings = [str(e)]
    cascade_findings = len(s.findings)
    kinds = rank_kinds.read(a.tutorial)
    rank_findings = rank_kinds.problems(kinds, parse_declarations(a.edge))
    s.findings += rank_findings
    s.state = "fail" if s.findings else "ok"
    parts = []
    if cascade_findings:
        parts.append(f"{cascade_findings} disagreement(s) between the "
                     f"tutorial and einsum.edge")
    if rank_findings:
        parts.append(f"{len(rank_findings)} problem(s) in the `ranks:` block")
    s.summary = ("; ".join(parts) if parts
                 else "the tutorial's cascade matches einsum.edge"
                      + ("; ranks: declared" if kinds else ""))
    if cascade_findings:
        s.next.append(
            "Make the tutorial's `edge_expression` and einsum.edge agree. Both "
            "are sources of truth, so decide which one is wrong in each case.")
    if rank_findings:
        s.next.append(
            "Give every rank in einsum.edge one kind from the list, in the "
            "front matter's `ranks:` block (AUTHORING.md, \"The tutorial\").")
    return s


def _paste_instructions(prompt: Path, reply: Path, a: Author) -> list[str]:
    return [
        f"Open {a.rel(prompt)} and paste ALL of it into a Claude chat.",
        f"Copy the whole reply and save it as {a.rel(reply)}.",
        f"Run again: python3 -m edge_workbench check {a.dir}",
    ]


def stage_builder(a: Author) -> Stage:
    s = Stage("builder")
    a.spec.mkdir(parents=True, exist_ok=True)
    a.prompts.mkdir(parents=True, exist_ok=True)
    a.replies.mkdir(parents=True, exist_ok=True)
    reply = a.replies / "builder.md"
    builder = a.spec / a.names["builder"]

    if reply.exists():
        files, problems = builder_prompt.parse_reply(reply.read_text(), a.slug)
        if a.names["builder"] in files:
            for name, body in files.items():
                (a.spec / name).write_text(body)
            # A file from an older reply that this one omits would otherwise
            # survive and be read as part of it.
            for name in (a.names["functions"],):
                if name not in files and (a.spec / name).exists():
                    (a.spec / name).unlink()
            reply.rename(a.replies / "builder.applied.md")
            s.summary = f"applied {sorted(files)} from the model's reply"
        else:
            s.findings += problems
            s.state = "fail"
            s.summary = "the saved reply could not be read"
            s.next += _paste_instructions(a.prompts / "builder.txt", reply, a)
            return s

    if not builder.exists():
        prompt = a.prompts / "builder.txt"
        prompt.write_text(builder_prompt.build_prompt(
            a.slug, a.edge, a.tutorial))
        s.state = "waiting"
        s.summary = "needs a builder (model step)"
        s.next += _paste_instructions(prompt, reply, a)
        return s

    s.summary = s.summary or a.names["builder"]
    return s


def _run_builder(a: Author) -> tuple[dict | None, list[str]]:
    root = spec_check.upstream()
    if root is None:
        return None, ["edge-core-ir not found; set EDGE_IR_REPO"]
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join([str(root), str(ROOT), str(a.spec)]))
    r = subprocess.run([sys.executable, a.names["builder"]], cwd=a.spec,
                       capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-8:]
        return None, ["the builder does not run:\n      "
                      + "\n      ".join(tail)]
    try:
        program = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        return None, [f"the builder's output is not JSON: {e}"]
    return program, []


def derive_cascade(a: Author, program: dict) -> tuple[dict, list[str]]:
    """cascade.json, derived from einsum.edge and the IR. Nothing hand-written.

    labels        walk the spec's labels against the IR's nodes in order
    displayNames  where the IR had to rename a spec tensor (`delta` -> `Delta`)
    selectors     a ranking operator (`select-min-val`, ...) maps to itself:
                  it IS the algorithm. Any other `1(name)` is a free choice,
                  so seeded random: random is what "any" means, seeded so a
                  build is reproducible.
    """
    surface = parse_edge_file(a.edge)
    # The spelling the EINSUMS use wins: max-flow's einsum.edge declares
    # `Delta` and writes `delta_{i,u,v}`, and the page should show what the
    # cascade says.
    ir_names = {d["name"] for d in program.get("declarations", [])}
    alias = {}
    for e in surface.values():
        if e.output and e.output not in ir_names:
            # `d*` cannot be an IR name; the convention is `DStar`.
            want = e.output.lower().replace("*", "star")
            match = [n for n in ir_names if n.lower() == want]
            if match:
                alias[match[0]] = e.output

    labels, problems = spec_check.label_map(surface, program, alias)
    free = sorted({m for e in surface.values()
                   for m in re.findall(r"\b1\(([a-z][a-z0-9]*(?:-[a-z0-9]+)+)\)",
                                       e.text)})
    gen = next((r["name"] for d in program.get("declarations", [])
                for r in d.get("ranks", [])[:1] if r.get("shape") is None), "I")
    return {
        "_comment": ["GENERATED by edge_workbench check from einsum.edge and "
                     "the IR. Do not edit: re-run check."],
        "generationalRank": gen,
        # A walkthrough of hundreds of generations is not one anyone steps
        # through, and a cascade that never stops should fail in seconds.
        "maxGenerations": 500,
        "initLabel": "init",
        "stopLabel": "stop",
        "displayNames": alias,
        # The tutorial's `ranks:` block, verbatim (checked at the tutorial
        # stage). Absent when the tutorial declares none.
        **({"rankKinds": kinds} if (kinds := rank_kinds.read(a.tutorial))
           else {}),
        "labels": labels,
        # Multi-output case statements over macros: each is a conditional
        # cascade in the IR, not an Einsum, so it has no entry in `labels`.
        **({"conditionals": {c.label: {"conditional": k,
                                       "macros": [arm.macro for arm in c.arms]}
                             for k, c in enumerate(surface.conditionals)}}
           if surface.conditionals else {}),
        "selectors": {n: (n if n in RANKED else {"rule": "seeded", "seed": 0})
                      for n in free},
    }, problems


def stage_program(a: Author) -> tuple[Stage, dict | None, dict | None]:
    s = Stage("program")
    program, problems = _run_builder(a)
    cascade = None
    if program is not None:
        a.program_file.write_text(json.dumps(program, indent=1) + "\n")
        problems += spec_check.layer_one(program)
        problems += spec_check.operator_names(
            program, a.spec / a.names["functions"])
        cascade, label_problems = derive_cascade(a, program)
        problems += label_problems
        (a.spec / "cascade.json").write_text(json.dumps(cascade, indent=1) + "\n")
        if cascade["labels"]:
            problems += spec_check.single_assignment(program, a.edge, cascade)
            # A tensor the IR writes and einsum.edge never does is the
            # lowering re-expressing an Einsum. Einsums are shown as written:
            # sub-steps belong in labelled, parenthesized parts of the one
            # Einsum, never in a new named tensor.
            from edge_workbench.spec_surface import helper_tensors
            helpers = helper_tensors(parse_edge_file(a.edge), program,
                                     cascade["labels"], cascade["displayNames"])
            for h in sorted(helpers):
                problems.append(
                    f"the IR introduces {h}, a tensor einsum.edge never writes. "
                    f"Lower that Einsum as ONE IR Einsum, with its parts as "
                    f"labelled parenthesized sub-expressions, not as a new "
                    f"tensor.")
            problems += spec_check.spec_versus_ir(
                parse_edge_file(a.edge), parse_declarations(a.edge),
                program, cascade)
        from edge_workbench.spec_surface import parse_constants
        problems += spec_check.constants_versus_ir(
            parse_constants(a.edge), program)

    s.findings = problems
    if problems:
        s.state = "fail"
        s.summary = "the builder's program does not match einsum.edge"
        prompt = a.prompts / "builder.txt"
        prompt.write_text(builder_prompt.build_prompt(
            a.slug, a.edge, a.tutorial, findings=problems))
        s.next.append(
            "If einsum.edge is right, the builder is wrong: the prompt now "
            "lists these problems for the model to fix.")
        s.next += _paste_instructions(prompt, a.replies / "builder.md", a)
        return s, None, None
    n = len(flat_nodes(program))
    s.summary = (f"{len(cascade['labels'])} Einsums -> {n} IR nodes; valid IR; "
                 f"operators and declarations match einsum.edge")
    unread = tensor_facts.unused(program)
    if unread:
        s.summary += f"; declared but never read: {unread}"
    return s, program, cascade


def _example_quote(artifact: dict, md: Path) -> list[str]:
    ex = artifact.get("example") or {}
    if (artifact.get("provenance") or {}).get("example") != review.MODEL:
        return []
    quote = ex.get("quote")
    if not quote:
        return ["the example cites no `quote`, so nothing shows it came from "
                "the tutorial rather than being invented"]
    if review._flat(quote) not in review._flat(md.read_text()):
        return [f"the example's quote is not in the tutorial verbatim: "
                f"{quote[:80]!r}"]
    return []


def view_problems(view: dict | None, program: dict, cascade: dict) -> list[str]:
    """Every tensor the styling names exists, with the rank count its use needs."""
    if not view:
        return []
    gen = cascade.get("generationalRank", "I")
    alias = cascade.get("displayNames", {})
    ranks = {alias.get(d["name"], d["name"]):
             [r["name"] for r in d.get("ranks", []) if r["name"] != gen]
             for d in program.get("declarations", [])}
    out = []
    uses = ([("nodeFill", r, 1) for r in view.get("nodeFill") or []]
            + [("nodeLabels", r, 1) for r in view.get("nodeLabels") or []])
    if view.get("edgeLabel"):
        uses.append(("edgeLabel", view["edgeLabel"], 2))
        over = view["edgeLabel"].get("over")
        if over and over not in tensor_facts.inputs(program, gen):
            out.append(f"view.edgeLabel.over is {over!r}; it must name the "
                       f"rank-2 INPUT tensor the edges are drawn from")
    for where, rule, want in uses:
        name = (rule or {}).get("tensor")
        if name not in ranks:
            out.append(f"view.{where} names {name!r}, which the program does "
                       f"not declare")
        elif len(ranks[name]) != want:
            out.append(f"view.{where} uses {name}, which has "
                       f"{len(ranks[name])} rank(s); it needs {want}")
    return out


def stage_tutorial_data(a: Author, program: dict, cascade: dict) -> tuple[Stage, dict | None]:
    s = Stage("tutorial data")
    artifact_path = a.spec / prepare.ARTIFACT
    if not artifact_path.exists():
        try:
            prepare.write(a.tutorial, a.spec)
        except tut.TutorialError as e:
            s.state, s.summary, s.findings = "fail", "tutorial unreadable", [str(e)]
            return s, None
    artifact = prepare.load(a.spec)
    reply = a.replies / "tutorial-data.json"
    # A multi-output case statement is explained like an Einsum.
    labels = sorted(set(cascade.get("labels") or {})
                    | set(cascade.get("conditionals") or {}))

    # The author's own meanings are read on every run, so an edit to the
    # tutorial reaches the page with no model step.
    try:
        told = tutorial_vs_edge.authored_meanings(a.tutorial, a.edge)
    except tut.TutorialError as e:
        s.state, s.summary, s.findings = "fail", "a meaning has no Einsum", [str(e)]
        return s, None
    if told != (artifact.get("tutorialMeanings") or {}):
        artifact = {k: v for k, v in artifact.items() if k != "tutorialMeanings"}
        if told:
            artifact["tutorialMeanings"] = told
        artifact_path.write_text(json.dumps(artifact, indent=1,
                                            ensure_ascii=False) + "\n")

    if reply.exists():
        try:
            response = json.loads(_unfence(reply.read_text()))
        except json.JSONDecodeError as e:
            s.state = "fail"
            s.findings = [f"{a.rel(reply)} is not JSON: {e}"]
            s.summary = "the saved reply could not be read"
            return s, None
        merged = propose.apply(artifact, response, a.tutorial)
        findings = review.check(merged, program, cascade)
        findings += review.check_quotes(merged, a.tutorial)
        findings += review.check_citation_order(merged, a.tutorial, labels)
        problems = [str(f) for f in findings]
        problems += _example_quote(merged, a.tutorial)
        ex = merged.get("example") or {}
        if ex.get("kind") == "instance":
            problems += [f"example: {p}" for p in verifier.instance_problems(
                ex, program, cascade.get("generationalRank", "I"))]
        problems += view_problems(merged.get("view"), program, cascade)
        if problems:
            s.state = "fail"
            s.findings = problems
            s.summary = "the model's reply was rejected; nothing was applied"
            reply.rename(a.replies / "tutorial-data.rejected.json")
            s.next.append("Paste the problems above into the same chat, ask "
                          "for a corrected JSON reply, and save it as "
                          f"{a.rel(reply)}; or re-run the prompt from scratch.")
            s.next.append(f"Run again: python3 -m edge_workbench check {a.dir}")
            return s, None
        artifact_path.write_text(json.dumps(merged, indent=1,
                                            ensure_ascii=False) + "\n")
        reply.rename(a.replies / "tutorial-data.applied.json")
        artifact = merged

    # A blank Meaning on these two steps is easy to miss: ask for them.
    have = prepare.explained(artifact)
    conds = stopping_conditions(program)
    untold = [k for k in labels if k not in have] + [
        k for k, needed in (("init", program.get("initialization", {})
                             .get("einsums")), ("stop", conds))
        if needed and k not in have
        and k not in (artifact.get("unstated") or [])]
    others = [g for g in artifact.get("gaps") or []
              if not g.startswith("meanings")]
    if untold:
        others.append(f"meanings: nothing for {', '.join(untold)}")
    artifact = dict(artifact, gaps=others)

    missing_view = "view" not in artifact
    if artifact.get("gaps") or missing_view:
        prompt = a.prompts / "tutorial-data.txt"
        if missing_view and not artifact.get("gaps"):
            artifact = dict(artifact, gaps=["view: no styling for the picture"])
        prompt.write_text(propose.build_prompt(
            a.tutorial, artifact, program, cascade, want_view=missing_view))
        s.state = "waiting"
        gaps = [g.split(":")[0] for g in artifact.get("gaps") or []]
        s.summary = f"needs {', '.join(gaps)} (model step)"
        s.next += _paste_instructions(prompt, reply, a)
        return s, None

    who = artifact.get("provenance") or {}
    s.summary = (f"{len(have)} meanings ({len(told)} from the tutorial), example, "
                 f"styling (" + ", ".join(f"{k}: {v}" for k, v in sorted(who.items()))
                 + ")")
    return s, artifact


def _unfence(text: str) -> str:
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    return m.group(1) if m else text


# ----------------------------------------------------------- instance ----

def make_instance(artifact: dict, program: dict, cascade: dict) -> dict:
    """instance.json: the worked example, plus how to draw it.

    The example supplies tensors in the program's own terms; the picture is
    derived from them. Which view comes from `domain_shape.classify`; the
    edges are the rank-2 input; node placement is computed. Nothing here
    knows which algorithm it is drawing.
    """
    ex = artifact["example"]
    gen = cascade.get("generationalRank", "I")
    inst = {k: ex.get(k, {}) for k in ("extent", "scalars", "tensors")}
    if ex.get("coordSets"):
        inst["coordSets"] = ex["coordSets"]
    if "expect" in ex:
        inst["expect"] = ex["expect"]

    kinds = cascade.get("rankKinds")
    shape = domain_shape.classify(program, inst, gen, kinds)
    decls = {d["name"]: d for d in program.get("declarations", [])}

    def over(name):
        return [r["name"] for r in decls.get(name, {}).get("ranks", [])
                if r["name"] != gen]

    tensors = inst.get("tensors", {})
    # A tensor over a node rank and a `spatial` rank (A*'s L_{S, XY}) gives
    # each vertex's location; it is not the edge tensor.
    placing = next((n for n in tensor_facts.inputs(program, gen)
                    if len(over(n)) == 2 and n in tensors
                    and rank_kinds.is_spatial(kinds, over(n)[1])), None)
    pair = next((n for n in tensor_facts.inputs(program, gen)
                 if len(over(n)) == 2 and n in tensors
                 and not any(rank_kinds.is_spatial(kinds, r)
                             for r in over(n))), None)
    domain: dict = {"view": shape["view"]}
    extent = inst.get("extent", {})

    if shape["view"] == domain_shape.BIPARTITE:
        left, right = shape["sides"]
        q = domain_shape.qualify
        edges = []
        if pair:
            a_rank, b_rank = over(pair)
            for k, v in tensors[pair].items():
                i, j = k.split(",")
                u, w = (q(a_rank, i), q(b_rank, j))
                edges.append({"u": u, "v": w, pair: v})
        domain["graph"] = {
            "nodes": [q(left, i) for i in range(extent.get(left, 0))]
                     + [q(right, i) for i in range(extent.get(right, 0))],
            "edges": edges,
            "sides": {"left": left, "right": right},
        }
        domain["positions"] = domain_shape.bipartite_positions(
            extent.get(left, 0), extent.get(right, 0), left, right)
    elif shape["view"] == domain_shape.GRAPH:
        rank = _node_rank(program, gen, kinds, rank_kinds.VERTEX)
        n = int(extent.get(rank, 0))
        edges = []
        if pair:
            for k, v in tensors[pair].items():
                u, w = (int(x) for x in k.split(","))
                edges.append({"u": u, "v": w, pair: v})
        # Lay out from the first node a rank-1 boolean input marks (a source,
        # a start vertex) when there is one; the last such mark goes on the
        # right. Otherwise from node 0.
        marks = [int(next(iter(tensors[x]))) for x in tensor_facts.inputs(program, gen)
                 if len(over(x)) == 1 and tensors.get(x)
                 and len(tensors[x]) == 1]
        start = marks[0] if marks else 0
        end = marks[-1] if len(marks) > 1 else None
        domain["graph"] = {"nodes": list(range(n)), "edges": edges}
        domain["positions"] = (_placed(n, tensors[placing]) if placing
                               else _layered(n, edges, start, end))
    else:
        rank = _node_rank(program, gen, kinds, rank_kinds.POSITION) or "?"
        domain["graph"] = {"nodes": list(range(int(extent.get(rank, 0)))),
                           "edges": []}
        domain["positions"] = {}

    supplied = artifact.get("view") or {}
    domain.update({k: v for k, v in supplied.items()})
    # The derived view wins. It used to win silently; a contradiction is now
    # reported by stage_instance, because it means either the model misread
    # the algorithm or `classify` is wrong.
    domain["view"] = shape["view"]
    inst["domain"] = domain
    inst["_comment"] = ["GENERATED by edge_workbench check from the worked "
                        "example in authored.json. Do not edit."]
    return inst


def _node_rank(program, gen, kinds, want):
    """The rank whose coordinates are the picture's nodes.

    With a `ranks:` block, the first rank declared `want`; without one, the
    first rank any tensor is indexed by, as before. Never a `spatial` rank.
    """
    ranks = rank_kinds.node_ranks(kinds, tensor_facts.node_ranks(program, gen))
    if kinds:
        ranks = [r for r in ranks if kinds.get(r) == want] or ranks
    return ranks[0] if ranks else None


def _placed(n, coords, width=520, height=320, pad=45):
    """Positions from a vertex-by-coordinate tensor, scaled to the canvas.

    Keys are `"v,k"`: coordinate k of vertex v; the first two coordinates are
    x and y. y is flipped so a larger y is drawn higher, as on a map. A vertex
    the tensor does not place goes on the bottom edge rather than vanishing.
    """
    pts: dict[int, list[float]] = {}
    for key, val in coords.items():
        v, k = (int(x) for x in key.split(","))
        if k < 2:
            pts.setdefault(v, [0.0, 0.0])[k] = float(val)
    if not pts:
        return {}
    xs = [p[0] for p in pts.values()]
    ys = [p[1] for p in pts.values()]
    sx = (width - 2 * pad) / ((max(xs) - min(xs)) or 1)
    sy = (height - 2 * pad) / ((max(ys) - min(ys)) or 1)
    out = {}
    for v in range(n):
        if v in pts:
            x, y = pts[v]
            out[v] = [round(pad + (x - min(xs)) * sx),
                      round(height - pad - (y - min(ys)) * sy)]
        else:
            out[v] = [round(pad + v * (width - 2 * pad) / max(n - 1, 1)),
                      height - pad // 2]
    return out


def _layered(n, edges, start, end):
    triples = [(e["u"], e["v"], 0) for e in edges]
    sink = end if end is not None else _farthest(n, triples, start)
    return tut.layer_positions(n, triples, start, sink)


def _farthest(n, triples, start):
    from collections import deque
    adj = {v: [] for v in range(n)}
    for u, v, _ in triples:
        adj.setdefault(u, []).append(v)
    seen, q, last = {start}, deque([start]), start
    while q:
        last = q.popleft()
        for v in adj.get(last, []):
            if v not in seen:
                seen.add(v)
                q.append(v)
    return last


def write_meta(a: Author, program: dict, cascade: dict) -> None:
    """meta.py: title, breadcrumb, and which tensors get a permanent grid.

    GROUPS is derived. Persistent grids go to the tensors without the
    generational rank that something reads (the problem and its fixed
    derived masks), and to the loop-carried state. Intermediates are shown
    by the execution panel at the moment they exist.
    """
    gen = cascade.get("generationalRank", "I")
    facts = tensor_facts.all_facts(program, cascade)
    alias = cascade.get("displayNames", {})
    unread = set(tensor_facts.unused(program))
    static1, static2, state1, state2 = [], [], [], []
    for d in program.get("declarations", []):
        name = d["name"]
        ranks = [r["name"] for r in d.get("ranks", []) if r["name"] != gen]
        if not ranks or name in unread or len(ranks) > 2:
            continue
        has_gen = any(r["name"] == gen for r in d.get("ranks", []))
        shown = alias.get(name, name)
        if not has_gen:
            (static1 if len(ranks) == 1 else static2).append(shown)
        elif name in facts["stateful"]:
            (state1 if len(ranks) == 1 else state2).append(shown)

    title = _front_matter(a.tutorial, "title") or a.slug
    groups = {"static1": static1, "static2": static2,
              "state1": state1, "state2": state2}
    # The crumb's anchor is built OUTSIDE the f-string: an f-string
    # expression may not contain a backslash before Python 3.12, and the
    # escaped quotes in the href are backslashes. On 3.10 this is a
    # SyntaxError at import, so it takes the whole test suite down at
    # collection rather than failing one test.
    # Relative, because the site may live under a base URL (edge-algorithms
    # is served at /edge-algorithms) and a walkthrough always sits at
    # assets/viz/<name>/, three levels below the site root.
    crumb = f'<a href="../../../algorithms/{a.slug}/">{title}</a>'
    (a.spec / "meta.py").write_text(
        "# GENERATED by edge_workbench check. Do not edit: re-run check.\n"
        f"TITLE = {json.dumps(title + ' — tensor view', ensure_ascii=False)}\n"
        f"CRUMB = {json.dumps(crumb, ensure_ascii=False)}\n"
        f"GROUPS = {json.dumps(groups)}\n")


def _front_matter(md: Path, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*(.+)$", md.read_text(), re.MULTILINE)
    return m.group(1).strip().strip("'\"") if m else None


def stage_instance(a: Author, artifact: dict, program: dict,
                   cascade: dict) -> Stage:
    s = Stage("instance")
    inst = make_instance(artifact, program, cascade)
    gen = cascade.get("generationalRank", "I")
    s.findings = verifier.instance_problems(inst, program, gen)
    s.findings += domain_shape.disagreement(
        (artifact.get("view") or {}).get("view"), program, inst, gen,
        where="the tutorial-data reply's `view`",
        kinds=cascade.get("rankKinds"))
    kinds_note = domain_shape.declared_vs_inferred(
        cascade.get("rankKinds"), program, inst, gen)
    (a.spec / "instance.json").write_text(json.dumps(inst, indent=1) + "\n")
    write_meta(a, program, cascade)
    # The verifier's half of this stage: its random instances supply what
    # the program reads, and the published answer is the approved one.
    s.findings += verifier.random_instance_problems(a.verifier, a.slug,
                                                    program, gen)
    expect = inst.get("expect") or {}
    changed, todo = approval.answer_problems(a.dir, "answer" in expect,
                                             expect.get("answer"))
    s.findings += changed
    s.next += todo
    s.state = "fail" if s.findings else "ok"
    s.summary = (f"{inst['domain']['view']} view; supplies "
                 f"{sorted(set(inst.get('tensors', {})) | set(inst.get('scalars', {})) | set(inst.get('coordSets', {})))}")
    if kinds_note:
        s.summary += f"; note: {kinds_note}"
    return s


def stage_page(a: Author) -> tuple[Stage, bool]:
    s = Stage("page")
    (a.spec / "written.json").write_text(json.dumps(
        tutorial_vs_edge.written_forms(a.tutorial, a.edge), indent=1,
        ensure_ascii=False) + "\n")
    env = dict(os.environ,
               EDGE_WORKBENCH_ALG=a.slug,
               EDGE_WORKBENCH_ALG_DIR=str(a.work),
               EDGE_WORKBENCH_OUT=str(a.work / "build"),
               EDGE_WORKBENCH_VERIFIER=str(a.verifier))
    r = subprocess.run(
        [sys.executable, str(ROOT / "edge_workbench/render/build_page.py")],
        capture_output=True, text=True, env=env, cwd=ROOT, timeout=600)
    out = (r.stdout + r.stderr).strip().splitlines()
    built = a.work / "build" / "index.html"
    if r.returncode != 0 or not built.exists():
        s.state = "fail"
        s.summary = "a build gate failed"
        unknown = sorted(set(re.findall(
            r"no \w+ function named '([\w-]+)' is registered", "\n".join(out))))
        if unknown:
            # edge-core-ir's evaluator runs the cascade; an operator it
            # cannot find is missing from both its default registry and the
            # algorithm's own *_functions.py.
            s.findings = [
                f"operator {n!r} is not registered: edge-core-ir's evaluator "
                f"has no implementation for it, and {a.names['functions']} "
                f"does not add one." for n in unknown]
        else:
            s.findings = out[-25:]
        return s, False
    shutil.copyfile(built, a.dir / "index.html")
    gates = [ln for ln in out if re.match(
        r"^(coverage|meanings|answer check|domain view|driven trace)\s*:", ln)]
    s.summary = "; ".join(ln.split(":", 1)[0].strip() + ":" +
                          ln.split(":", 1)[1].strip()[:60] for ln in gates)
    return s, True


# ---------------------------------------------------------------- run ----

def check(directory: Path, tutorial: Path | None = None,
          committed_only: bool = False) -> int:
    a = locate(directory, tutorial)
    # A stale page must never sit beside a failing check, looking current.
    stale = a.dir / "index.html"
    stages: list[Stage] = []

    inputs = stage_inputs(a, committed_only)
    stages.append(inputs)
    if inputs.state == "fail":
        return _finish(a, stages, stale)

    stages.append(stage_tutorial(a))
    builder = stage_builder(a)
    stages.append(builder)
    if builder.state != "ok":
        return _finish(a, stages, stale)

    program_stage, program, cascade = stage_program(a)
    stages.append(program_stage)
    if program is None:
        return _finish(a, stages, stale)

    data_stage, artifact = stage_tutorial_data(a, program, cascade)
    stages.append(data_stage)
    if artifact is None:
        return _finish(a, stages, stale)

    inst_stage = stage_instance(a, artifact, program, cascade)
    stages.append(inst_stage)
    if inputs.state == "waiting":
        stages.append(stage_approval(a, inputs, artifact,
                                     failing=any(s.state == "fail"
                                                 for s in stages)))
        return _finish(a, stages, stale)
    if any(s.state == "fail" for s in stages):
        stages.append(Stage("page", "skipped",
                            "not built while a check above is failing"))
        return _finish(a, stages, stale)

    page, wrote = stage_page(a)
    stages.append(page)
    return _finish(a, stages, stale, wrote)


def stage_approval(a: Author, inputs: Stage, artifact: dict,
                   failing: bool) -> Stage:
    """The one approval a new or changed verifier needs, asked for last.

    Everything that does not depend on the verifier has run, so the
    tutorial's published answer is known and `approve-verifier` pins both in
    one lock. If another stage is failing, fixing it may change the answer,
    so that comes first.
    """
    s = Stage("approval", "waiting" if not failing else "skipped")
    answer = ((artifact.get("example") or {}).get("expect") or {}).get("answer")
    if failing:
        s.summary = ("waits until the stages above pass: fixing them may "
                     "change the published answer")
        return s
    s.summary = "needs one approval: the verifier and the published answer"
    s.findings = inputs.deferred + [
        f"Approving now covers verifier.py ({verifier.declared(a.verifier).get('KIND')}: "
        f"{verifier.declared(a.verifier).get('METHOD')}) and the tutorial's "
        f"published answer {answer!r} together."]
    s.next = approval._next(a.dir)
    return s


def _finish(a: Author, stages: list[Stage], stale: Path, wrote=False) -> int:
    if not wrote and stale.exists():
        stale.unlink()
    print(report(a, stages, wrote))
    return 0 if wrote else 1


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="python3 -m edge_workbench",
        description="Check an EDGE tutorial and build its page.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="run every check; build index.html if "
                                     "they all pass")
    c.add_argument("dir", type=Path,
                   help="directory holding the tutorial .md, einsum.edge "
                        "and verifier.py")
    c.add_argument("--tutorial", type=Path, default=None,
                   help="the tutorial .md, when it does not live in DIR "
                        "(a site collection is often one flat directory)")
    c.add_argument("--committed-only", action="store_true",
                   help="count only a committed verifier.lock as approval, "
                        "not approvals recorded on this machine (tests, CI)")
    v = sub.add_parser("approve-verifier",
                       help="a person approves verifier.py as it is now; "
                            "interactive, needs a terminal")
    v.add_argument("dir", type=Path)
    v.add_argument("--tutorial", type=Path, default=None)
    v.add_argument("--confirm", default=None, metavar="METHOD",
                   help="approve without a terminal: the METHOD, as allowed "
                        "by the person at Claude Code's permission prompt")
    v.add_argument("--sha", default=None,
                   help="with --confirm: the start of the verifier.py hash "
                        "the person was shown")
    k = sub.add_parser("verify-instance",
                       help="rerun one random instance of the answer check "
                            "and print it")
    k.add_argument("dir", type=Path)
    k.add_argument("k", type=int, help="which random instance, from 0")
    k.add_argument("--tutorial", type=Path, default=None)
    p = sub.add_parser("publish",
                       help="run check, then copy index.html into the site "
                            "and link it from the tutorial")
    p.add_argument("dir", type=Path)
    p.add_argument("--tutorial", type=Path, default=None)
    p.add_argument("--site", type=Path, default=None,
                   help="the site checkout (default: $EDGE_WORKBENCH_SITE, "
                        "else edge-algorithms beside this repository)")
    p.add_argument("--with-tutorial", action="store_true",
                   help="also replace the site's tutorial with this one")
    p.add_argument("--committed-only", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "publish":
        from edge_workbench import publish
        return publish.publish(args.dir, args.site, args.tutorial,
                               args.with_tutorial, args.committed_only)
    if args.cmd == "approve-verifier":
        a = locate(args.dir, args.tutorial)
        return approval.approve(a.dir, a.slug, confirm=args.confirm,
                                sha=args.sha)
    if args.cmd == "verify-instance":
        a = locate(args.dir, args.tutorial)
        if not (a.spec / "instance.json").exists():
            raise SystemExit(f"run `python3 -m edge_workbench check {a.dir}` "
                             f"first: there is no program to run yet")
        return verifier.main(["--spec", str(a.spec), "--verifier",
                              str(a.verifier), "--slug", a.slug,
                              "--instance", str(args.k)])
    return check(args.dir, args.tutorial, args.committed_only)
