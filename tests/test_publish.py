"""`publish`: only a passing check reaches the site, and the site's tutorial
gains a link without losing anything of its own."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from edge_workbench import author, publish  # noqa: E402

TUTORIAL = "---\ntitle: Toy\ntags: [toy]\nstatus_intro: |\n  hi\n---\n"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "_algorithms").mkdir(parents=True)
    work = tmp_path / "toy"
    work.mkdir()
    (work / "toy.md").write_text(TUTORIAL)
    passed = {"rc": 0}

    def fake_check(directory, tutorial=None, committed_only=False):
        if passed["rc"] == 0:
            (Path(directory) / "index.html").write_text("<p>page</p>")
        return passed["rc"]

    monkeypatch.setattr(author, "check", fake_check)
    return site, work, passed


def test_a_failing_check_publishes_nothing(setup):
    site, work, passed = setup
    passed["rc"] = 1
    (work / "index.html").write_text("stale")
    assert publish.publish(work, site) == 1
    assert not (site / "assets").exists()


def test_a_new_algorithm_gets_its_page_and_tutorial(setup):
    site, work, _ = setup
    assert publish.publish(work, site) == 0
    assert (site / "assets/viz/toy/index.html").read_text() == "<p>page</p>"
    md = (site / "_algorithms/toy.md").read_text()
    assert "viz: /assets/viz/toy/\n" in md
    assert md.index("tags:") < md.index("viz:") < md.index("status_intro:")


def test_the_sites_tutorial_only_gains_a_link_by_default(setup, capsys):
    site, work, _ = setup
    site_md = site / "_algorithms/toy.md"
    site_md.write_text(TUTORIAL.replace("hi", "the site's own words"))
    (work / "toy.md").write_text(TUTORIAL.replace("tags: [toy]\n",
                                                  "tags: [toy]\nranks:\n  I: generational\n"))
    assert publish.publish(work, site) == 0
    md = site_md.read_text()
    assert "the site's own words" in md and "ranks:" not in md
    assert "viz: /assets/viz/toy/" in md
    assert "differs from the site's" in capsys.readouterr().out


def test_with_tutorial_replaces_it_and_keeps_existing_viz_keys(setup):
    site, work, _ = setup
    site_md = site / "_algorithms/toy.md"
    site_md.write_text(TUTORIAL.replace(
        "tags: [toy]\n", "tags: [toy]\nviz: /assets/viz/toy/\nviz_alt: /x/\n"))
    (work / "toy.md").write_text(TUTORIAL.replace("hi", "new words"))
    assert publish.publish(work, site, with_tutorial=True) == 0
    md = site_md.read_text()
    assert "new words" in md and "viz_alt: /x/" in md
    assert md.count("viz: /assets/viz/toy/") == 1


def test_a_missing_site_is_refused(tmp_path):
    assert publish.publish(tmp_path, tmp_path / "nowhere") == 2
