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
   `cases` statement may lower to one node per arm). Never introduce a
   tensor the spec does not write. Where the IR needs steps, write them as
   labelled parenthesized parts of the same Einsum -- AnonymousTensor with
   BinaryApp labels, specs flat on the Einsum -- as max-flow's E06 and E11
   do. A unary on an expression is the paper's degenerate Map against 1
   (merge take_left, compute = the unary); ||T|| is `Occupancy`. Put a
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

6. Reply with each file in its own fenced block whose info string names it:

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
