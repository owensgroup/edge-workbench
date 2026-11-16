# -*- coding: utf-8 -*-
"""Put a checked page on the site: `python3 -m edge_workbench publish <dir>`.

The site (edge-algorithms) serves each walkthrough at `assets/viz/<slug>/`
and links it from the tutorial's front matter (`viz:`, `viz_label:`,
`viz_note:`). The page's own links already assume that location.

PUBLISHING RUNS `check` FIRST. A page is only ever copied from a run that
passed every gate in this invocation, so nothing stale or unverified reaches
the site, whatever is lying in the directory.

The tutorial on the site belongs to the site. By default it only gains the
three `viz` keys (if it has none); the workbench copy of the tutorial is
compared with it and any difference is reported, because a port adds a
`ranks:` block and meaning lines that the site does not have yet. Pass
`--with-tutorial` to replace the site's tutorial with the workbench copy
(its `viz` keys are kept). Nothing is committed or pushed.
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
from pathlib import Path

#: Where the site lives when --site is not given.
ENV_SITE = "EDGE_WORKBENCH_SITE"

VIZ_LABEL = "Open the interactive walkthrough"
VIZ_NOTE = ("step one Einsum at a time on the worked example and watch it "
            "execute — every point of its iteration space, and how each value "
            "is computed")


def default_site() -> Path:
    if os.environ.get(ENV_SITE):
        return Path(os.environ[ENV_SITE]).expanduser()
    from edge_workbench.paths import ROOT
    return ROOT.parent / "edge-algorithms"


def _front_matter_has(text: str, key: str) -> bool:
    end = text.find("\n---", 3) if text.startswith("---") else -1
    head = text[:end] if end > 0 else ""
    return re.search(rf"^{re.escape(key)}:", head, re.MULTILINE) is not None


def with_viz_keys(text: str, slug: str) -> str:
    """`text` with viz keys added after `tags:` (or `title:`), if it has none."""
    if _front_matter_has(text, "viz"):
        return text
    keys = (f"viz: /assets/viz/{slug}/\n"
            f"viz_label: {VIZ_LABEL}\n"
            f"viz_note: {VIZ_NOTE}\n")
    for anchor in ("tags", "title"):
        m = re.search(rf"^{anchor}:.*\n", text, re.MULTILINE)
        if m:
            return text[:m.end()] + keys + text[m.end():]
    raise ValueError("the tutorial has no front matter `title:` to put the "
                     "viz keys after")


def _viz_lines(text: str) -> list[str]:
    return [l for l in text.splitlines(keepends=True)
            if re.match(r"viz(_\w+)?:", l)]


def publish(directory: Path, site: Path | None = None,
            tutorial: Path | None = None, with_tutorial: bool = False,
            committed_only: bool = False) -> int:
    from edge_workbench import author

    site = Path(site) if site else default_site()
    algorithms = site / "_algorithms"
    if not algorithms.is_dir():
        print(f"not published: {site} has no _algorithms/ directory; pass "
              f"--site or set {ENV_SITE}")
        return 2

    rc = author.check(directory, tutorial, committed_only)
    if rc != 0:
        print("\nnot published: `check` did not pass.")
        return rc

    a = author.locate(directory, tutorial)
    page = a.dir / "index.html"
    dest = site / "assets" / "viz" / a.slug / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(page, dest)
    print(f"\npublished     : {dest}")

    ours = a.tutorial.read_text()
    site_md = algorithms / f"{a.slug}.md"
    if not site_md.exists():
        site_md.write_text(with_viz_keys(ours, a.slug))
        print(f"tutorial      : new on the site, {site_md}")
    elif a.tutorial.resolve() == site_md.resolve():
        site_md.write_text(with_viz_keys(ours, a.slug))
        print(f"tutorial      : checked in place; viz keys "
              f"{'present' if _front_matter_has(ours, 'viz') else 'added'}")
    else:
        theirs = site_md.read_text()
        if with_tutorial:
            # Keep the site's own viz keys (a page may have several), then
            # add ours if it had none.
            keep = _viz_lines(theirs)
            body = ours
            if keep and not _front_matter_has(body, "viz"):
                m = re.search(r"^(tags|title):.*\n", body, re.MULTILINE)
                body = body[:m.end()] + "".join(keep) + body[m.end():]
            site_md.write_text(with_viz_keys(body, a.slug))
            print(f"tutorial      : replaced {site_md} with {a.tutorial.name}")
        else:
            linked = with_viz_keys(theirs, a.slug)
            if linked != theirs:
                site_md.write_text(linked)
            print(f"tutorial      : {site_md} "
                  f"{'gained viz keys' if linked != theirs else 'already links a page'}")
            diff = [l for l in difflib.unified_diff(
                [l for l in theirs.splitlines(keepends=True)
                 if not re.match(r"viz(_\w+)?:", l)],
                [l for l in ours.splitlines(keepends=True)
                 if not re.match(r"viz(_\w+)?:", l)],
                "site", "workbench", n=0)
                    if l.startswith(("+", "-"))
                    and not l.startswith(("+++", "---"))]
            if diff:
                print(f"                the workbench tutorial differs from "
                      f"the site's in {len(diff)} line(s) (a ranks: block, "
                      f"meaning lines, ...). Carry them back by hand, or "
                      f"publish again with --with-tutorial.")
    print("Nothing was committed. Review and commit in the site repository.")
    return 0
