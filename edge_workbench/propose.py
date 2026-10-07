# -*- coding: utf-8 -*-
"""Ask a model to fill what a tutorial does not state, and check that it did.

`prepare` reads what a tutorial states and names the gaps. This builds the
request that fills them, and merges the answer back under a provenance flag so
a reviewer knows which sentences a model wrote.

NO MODEL RUNS DURING A BUILD
----------------------------
This is an authoring step. Its output is committed, and the build reads the
committed artifact -- so a page is byte-reproducible, CI needs no network, and
nothing changes when nobody changed anything. A model in the build path would
give up all three.

EVERY MEANING MUST QUOTE ITS SOURCE
----------------------------------
The hard part of this task is not writing prose, it is ATTACHING prose to the
right Einsum. A tutorial's walkthrough is grouped by phase -- Preflow, Push,
Relabel -- and splitting six paragraphs across twenty-four Einsums is where a
plausible-looking answer goes wrong: every sentence is real, and some are on
the wrong step.

So the contract asks for a verbatim quotation from the tutorial alongside each
meaning, and `review` checks that the quotation is really there. A model that
invents a citation is caught by string comparison, which is the one thing that
needs no judgement at all. It does not prove the meaning is right -- it proves
the model was reading the tutorial rather than the algorithm's reputation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edge_workbench import prepare, review, tensor_facts

RESPONSE_SHAPE = """\
{
  "meanings": {
    "E01": {
      "text":  "one sentence: what this Einsum means FOR THE PROBLEM",
      "quote": "a verbatim span copied from the tutorial that supports it"
    }
  },
  "example": { ...only if the example gap was listed; see its own section... },
  "tensorNotes": { "TensorName": "what it is for" }
}"""

# What `review._check_example` will hold a matrix example to. Stated in the
# request because a model that has to guess the schema produces something
# plausible that the gate then rejects -- and the rejection reads as the
# model's failure rather than the request's.
EXAMPLE_CONTRACT = """
THE EXAMPLE

Take it from a worked example the tutorial ALREADY GIVES. Do not invent an
instance: the point of this field is that the answer can be checked against
something the author published, and an invented matrix checks nothing.

  "example": {
    "kind": "matrix",
    "rows": <int>, "columns": <int>,
    "matrix": [[1,0,0], ...],        // rows x columns, 1 where the row covers
    "expect": {
      "solutions": [[...], [...]]    // every solution the tutorial states,
                                     // as 0-based ROW indices
    }
  }

These are checked before anything runs: the matrix must be exactly `rows` by
`columns`, and every published solution must cover every column EXACTLY ONCE
against that matrix. A solution that does not is either a transcription slip
or the wrong example, and both are worth catching here rather than in a page.
"""


def instance_contract(program: dict, gen_rank: str = "I") -> str:
    """The example, stated in the PROGRAM's terms rather than the problem's.

    A graph example and a matrix example used to be two hand-written shapes,
    each translated into tensors by code that knew which algorithm it was
    serving -- `to_instance` wrote max-flow's G, C, S and T by name. Asking
    for the instance directly, keyed by the inputs the program actually reads,
    needs no translation and works for any algorithm: the program says what
    it needs, and `verifier.instance_problems` checks it got exactly that.
    """
    from edge_workbench import tensor_facts

    decls = {d["name"]: d for d in program.get("declarations", [])}
    rows, ranks = [], set()
    for name in tensor_facts.inputs(program, gen_rank):
        d = decls.get(name, {})
        rs = [r["name"] for r in d.get("ranks", []) if r["name"] != gen_rank]
        ranks |= set(rs)
        dtype = (d.get("data_type") or {}).get("name", "?")
        where = f"tensors.{name}  over {rs}" if rs else f"scalars.{name}"
        rows.append(f"    {where}  ({dtype}, empty = {d.get('empty_value')!r})")
    return f"""
THE EXAMPLE

Take it from a worked example the tutorial ALREADY GIVES. Do not invent one:
the point is that the answer can be checked against something the author
published. State it as the inputs this program reads -- exactly these, no
more, no fewer:

{chr(10).join(rows)}

  "example": {{
    "kind": "instance",
    "quote": "a verbatim span from the tutorial that states this example",
    "extent":  {{ {", ".join(f'"{r}": <int>' for r in sorted(ranks))} }},
    "scalars": {{ ... }},
    "tensors": {{ "Name": {{"0,1": value, ...}} }},
    "expect":  {{ "answer": <the answer the tutorial states for it> }}
  }}

Coordinates are 0-based integers joined by commas, in the tensor's rank
order. Omit entries equal to the empty value: an empty entry is absent.
"""


VIEW_CONTRACT = """
THE PICTURE (optional but wanted)

How the page should decorate the domain view. Name tensors from the program;
each is checked to exist with the right number of ranks.

  "view": {
    "nodeFill":   [ {"tensor": "<rank-1 boolean>", "color": "#d3f9d8",
                     "label": "what a filled node means"} ],
    "nodeLabels": [ {"tensor": "<rank-1>", "prefix": "d=", "empty": "∞",
                     "place": "above" | "below", "color": "#0b7285"} ],
    "edgeLabel":  {"tensor": "<rank-2>", "over": "<the rank-2 input>"}
  }

Order nodeFill by priority: the first rule that matches a node wins. Prefer
the two or three tensors a reader of the walkthrough watches change.
`over` names the rank-2 INPUT the edges are drawn from, and shows each label
as tensor/input -- flow over capacity, for instance.
"""


def build_prompt(tutorial: Path, artifact: dict, program: dict | None = None,
                 cascade: dict | None = None, want_view: bool = False) -> str:
    """The request: the tutorial, the gaps, and what the IR already knows."""
    text = Path(tutorial).read_text()
    gaps = artifact.get("gaps") or []

    facts_block = ""
    if program and cascade:
        touched = review.tensors_touched(program, cascade)
        facts = tensor_facts.all_facts(program, cascade)
        lines = [
            f"  {label}: writes/reads {', '.join(sorted(names))}"
            for label, names in sorted(touched.items())
        ]
        facts_block = (
            "\nWHAT THE PROGRAM ALREADY SAYS (do not restate this; it is\n"
            "generated separately, and a meaning that repeats it is wasted):\n"
            + "\n".join(lines)
            + f"\n\n  loop-carried tensors: {', '.join(sorted(facts['stateful']))}\n"
        )

    example_block = ""
    if any(g.startswith("example") for g in gaps):
        example_block = (instance_contract(
            program, (cascade or {}).get("generationalRank", "I"))
            if program else EXAMPLE_CONTRACT)
    if want_view:
        example_block += VIEW_CONTRACT

    return f"""\
You are filling gaps in the machine-readable form of an EDGE algorithm
tutorial. Everything you write will be shown to readers beside a visualisation
of the algorithm, so accuracy matters more than fluency.

THE GAPS TO FILL
{chr(10).join('  - ' + g for g in gaps) or '  (none)'}
{facts_block}
RULES

1. Every meaning is ONE sentence saying what the Einsum means FOR THE PROBLEM
   -- "an edge is downhill when d(u) = d(v)+1" -- not what it does
   mechanically. The mechanical description is generated from the program and
   shown next to yours; repeating it wastes the reader's attention.

2. Every meaning MUST carry a `quote`: a span copied VERBATIM from the
   tutorial below that supports it. This is checked by string comparison. If
   the tutorial does not say enough about an Einsum to quote, say so by
   omitting that entry rather than inventing support.

3. Do not attribute prose to the wrong Einsum. The walkthrough is grouped by
   phase; each phase covers several Einsums, and which sentence belongs to
   which is the judgement being asked of you.

4. Answer with JSON only, in this shape:

{RESPONSE_SHAPE}
{example_block}
THE TUTORIAL
--------------------------------------------------------------------------
{text}
--------------------------------------------------------------------------
"""


# ----------------------------------------------------------------- apply --

def apply(artifact: dict, response: dict, tutorial: Path | None = None) -> dict:
    """Merge a model's answer into the artifact, marked as the model's.

    Quotations are kept, not discarded, so the check that they are real can be
    re-run later -- and so a reviewer can see what each sentence was based on
    without going back to the tutorial.
    """
    out = dict(artifact)
    prov = dict(out.get("provenance") or {})

    meanings = dict(out.get("meanings") or {})
    quotes = dict(out.get("quotes") or {})
    for label, value in (response.get("meanings") or {}).items():
        if isinstance(value, dict):
            meanings[label] = value.get("text", "")
            if value.get("quote"):
                quotes[label] = value["quote"]
        else:
            meanings[label] = value
    if meanings != (out.get("meanings") or {}):
        out["meanings"] = meanings
        prov["meanings"] = review.MODEL
    if quotes:
        out["quotes"] = quotes

    for field in ("example", "tensorNotes", "view"):
        if response.get(field):
            merged = response[field]
            if field == "tensorNotes":
                merged = {**(out.get(field) or {}), **response[field]}
            out[field] = merged
            prov[field] = review.MODEL

    out["provenance"] = prov
    out["gaps"] = _remaining_gaps(out)
    return out


def _remaining_gaps(artifact: dict) -> list[str]:
    gaps = []
    if not artifact.get("example"):
        gaps.append("example: still absent")
    if not artifact.get("meanings"):
        gaps.append("meanings: still absent")
    return gaps


# ------------------------------------------------------------------- cli --

def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        prog="edge_workbench.propose",
        description="Build the model request, or apply its answer.",
    )
    ap.add_argument("tutorial", type=Path)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--emit-prompt", type=Path,
                    help="write the request here instead of calling anything")
    ap.add_argument("--apply", type=Path,
                    help="a model's JSON answer, to merge into the artifact")
    args = ap.parse_args(argv)

    artifact = prepare.load(args.spec)
    if not artifact:
        print(f"no prepared artifact in {args.spec}; run "
              f"`python3 -m edge_workbench.prepare` first")
        return 1

    program = cascade = None
    programs = sorted(args.spec.glob("*_program.json"))
    if programs and (args.spec / "cascade.json").exists():
        program = json.loads(programs[0].read_text())
        cascade = json.loads((args.spec / "cascade.json").read_text())

    if args.apply:
        response = json.loads(args.apply.read_text())
        merged = apply(artifact, response, args.tutorial)
        labels = sorted(cascade.get("labels") or {}) if cascade else None
        findings = review.check(merged, program, cascade)
        findings += review.check_quotes(merged, args.tutorial)
        findings += review.check_citation_order(merged, args.tutorial, labels)
        print(review.report(findings))
        if findings:
            print("\nNOT applied. Fix the answer and re-run.")
            return 1
        (args.spec / prepare.ARTIFACT).write_text(
            json.dumps(merged, indent=1, ensure_ascii=False) + "\n")
        print(f"applied to {args.spec / prepare.ARTIFACT}")
        return 0

    prompt = build_prompt(args.tutorial, artifact, program, cascade)
    if args.emit_prompt:
        args.emit_prompt.write_text(prompt)
        print(f"wrote {args.emit_prompt} ({len(prompt)} chars, "
              f"{len(artifact.get('gaps') or [])} gap(s))")
    else:
        print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
