"""The verifier's contract and its approval, each failing with its own words.

Every directory here is a temp directory and every ledger a throwaway file
named by EDGE_WORKBENCH_LEDGER; nothing touches a real approval.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from approval_fixture import approve_in_tmp  # noqa: E402
from edge_workbench import approval, author, spec_check, verifier  # noqa: E402

GOOD = '''
ANSWER_LABEL = "total"
KIND = "definition"
METHOD = "direct sum"


def solve(instance):
    return sum(instance["tensors"]["X"].values())


def answer(final, instance):
    return sum(final.get("Y", {}).values())


def random_instance(rng):
    n = rng.randint(2, 6)
    return {"extent": {"N": n},
            "tensors": {"X": {str(i): rng.randint(1, 9) for i in range(n)}}}
'''


@pytest.fixture
def ledger(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "ledger" / "approved.json"
    path.parent.mkdir()
    monkeypatch.setenv(approval.LEDGER_ENV, str(path))
    return path


def _dir(tmp_path: Path, text: str = GOOD) -> Path:
    d = tmp_path / "toy"
    d.mkdir()
    (d / "verifier.py").write_text(text)
    return d


def _problems(tmp_path: Path, text: str) -> str:
    return "\n".join(verifier.contract_problems(
        _dir(tmp_path, text) / "verifier.py", "toy"))


# ------------------------------------------------------------ contract ---

def test_a_verifier_that_meets_the_contract_has_no_problems(tmp_path):
    assert _problems(tmp_path, GOOD) == ""


def test_a_missing_random_instance_is_reported(tmp_path):
    text = GOOD[:GOOD.index("def random_instance")]
    assert "must define random_instance(rng)" in _problems(tmp_path, text)


def test_random_instance_takes_exactly_the_rng(tmp_path):
    text = GOOD.replace("def random_instance(rng):",
                        "def random_instance(rng, size=4):")
    assert "random_instance must be written random_instance(rng)" in _problems(
        tmp_path, text)


def test_kind_and_method_are_required(tmp_path):
    found = _problems(tmp_path, GOOD.replace('KIND = "definition"', "")
                      .replace('METHOD = "direct sum"', 'METHOD = ""'))
    assert "must set KIND to one of" in found and "it is missing" in found
    assert "must set METHOD" in found
    (tmp_path / "b").mkdir()
    assert "it is 'oracle'" in _problems(
        tmp_path / "b", GOOD.replace('"definition"', '"oracle"'))


def test_a_certificate_needs_certify(tmp_path):
    found = _problems(tmp_path, GOOD.replace('"definition"', '"certificate"'))
    assert "certify(final, instance[, steps]) (required when KIND" in found


def test_a_user_reference_is_a_kind(tmp_path):
    assert _problems(tmp_path, GOOD.replace('"definition"', '"user-reference"')
                     .replace("direct sum", "the user's sum.py")) == ""


@pytest.mark.parametrize("line, said", [
    ("import os", "imports `os`, which is not allowed"),
    ("import random", "imports `random`: use the `rng` passed"),
    ("import time", "imports `time`"),
    ("from edge_ir.evaluator import evaluate", "imports `edge_ir`"),
    ("import edge_workbench.driver", "imports `edge_workbench`"),
    ("import helper_beside_me", "imports `helper_beside_me`, which is not"),
    ("from . import helper", "relative import"),
])
def test_a_banned_import_is_refused_before_it_runs(tmp_path, line, said):
    marker = tmp_path / "it-ran"
    text = (f"{line}\nimport pathlib\n"
            f"pathlib.Path({str(marker)!r}).write_text('x')\n" + GOOD)
    d = _dir(tmp_path, text)
    (d / "helper_beside_me.py").write_text("X = 1\n")
    assert said in "\n".join(verifier.contract_problems(d / "verifier.py", "toy"))
    with pytest.raises(verifier.VerifierError):
        verifier.load(d / "verifier.py")
    assert not marker.exists(), "the verifier was imported before being read"


def test_open_eval_and_exec_are_refused(tmp_path):
    found = _problems(tmp_path, GOOD + "\nDATA = open('x').read()\n"
                                       "Y = eval('1')\n")
    assert "uses `open`" in found and "uses `eval`" in found


def test_trusted_libraries_may_be_imported(tmp_path):
    text = "import numpy\nimport scipy.sparse\nimport networkx as nx\n" + GOOD
    d = _dir(tmp_path, text)
    assert verifier.static_problems(d / "verifier.py") == []


def test_a_library_that_is_not_installed_says_what_to_install(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "LIBRARIES", {"not_installed_anywhere_xyz"})
    found = _problems(tmp_path, "import not_installed_anywhere_xyz\n" + GOOD)
    assert ("not installed here. Install it: python3 -m pip install "
            "not_installed_anywhere_xyz") in found


def test_solve_must_not_reach_answer(tmp_path):
    text = GOOD.replace('return sum(instance["tensors"]["X"].values())',
                        'return _via(instance)') + (
        "\ndef _via(instance):\n    return answer({}, instance)\n")
    assert "solve reaches answer" in _problems(tmp_path, text)
    back = GOOD.replace('return sum(final.get("Y", {}).values())',
                        "return solve(instance)")
    (tmp_path / "b").mkdir()
    assert "answer reaches solve" in _problems(tmp_path / "b", back)


def test_a_nondeterministic_generator_is_reported(tmp_path):
    text = GOOD.replace("    n = rng.randint(2, 6)",
                        "    _CALLS.append(1)\n"
                        "    n = 2 + len(_CALLS) % 5") + "\n_CALLS = []\n"
    assert "random_instance is not deterministic" in _problems(tmp_path, text)


def test_a_constant_answer_is_reported(tmp_path):
    """`solve` that always says the same lets a cascade that does too pass."""
    text = GOOD.replace('return sum(instance["tensors"]["X"].values())',
                        "return 7")
    assert "solve gave only 1 different answer(s)" in _problems(tmp_path, text)


def test_an_answer_that_does_not_read_the_cascade_is_reported(tmp_path):
    text = GOOD.replace('return sum(final.get("Y", {}).values())',
                        'return sum(instance["tensors"]["X"].values())')
    assert "EMPTY final state" in _problems(tmp_path, text)


def test_instances_must_vary_and_stay_small(tmp_path):
    same = GOOD.replace("n = rng.randint(2, 6)", "n = 4")
    assert "same extent" in _problems(tmp_path, same)
    (tmp_path / "b").mkdir()
    big = GOOD.replace("n = rng.randint(2, 6)", "n = rng.randint(20, 30)")
    assert "extents must be whole numbers from 1 to 12" in _problems(
        tmp_path / "b", big)


def test_an_exception_in_solve_or_the_generator_is_reported(tmp_path):
    text = GOOD.replace("    n = rng.randint(2, 6)", "    n = 1 // 0")
    assert "random_instance raised ZeroDivisionError" in _problems(tmp_path, text)
    (tmp_path / "b").mkdir()
    text = GOOD.replace('return sum(instance["tensors"]["X"].values())',
                        'return instance["nope"]')
    assert "solve raised KeyError" in _problems(tmp_path / "b", text)


def test_a_solve_that_never_returns_is_stopped_and_named(tmp_path, monkeypatch):
    monkeypatch.setattr(verifier, "CALL_LIMIT", 0.2)
    text = GOOD.replace('return sum(instance["tensors"]["X"].values())',
                        'while True:\n        pass')
    assert "solve raised TookTooLong: solve took longer than" in _problems(
        tmp_path, text)


def test_instance_k_can_be_made_again_alone(tmp_path):
    mod = verifier.load(_dir(tmp_path) / "verifier.py")
    drawn = verifier.sample(mod, "toy")
    assert mod.random_instance(verifier.rng_for("toy", 7)) == drawn.instances[7]
    assert drawn.instances != verifier.sample(mod, "other").instances


def test_the_summary_never_claims_more_than_ran():
    res = verifier.Result(passed=5, random_total=12, random_run=4,
                          random_agree=4, failures=["x"])
    assert res.summary() == ("random instances: 4/12 agree (only 4 ran); "
                             "5 checks passed, 1 FAILED")


# ------------------------------------------------------------ approval ---

def _said(directory: Path, committed_only: bool = False) -> str:
    found, todo = approval.problems(directory, committed_only)
    if found:
        assert any("approve-verifier" in t or "Commit" in t for t in todo)
    return "\n".join(found + todo)


def test_a_verifier_nobody_approved_fails_and_says_what_to_run(tmp_path, ledger):
    d = _dir(tmp_path)
    said = _said(d)
    assert "has never been approved" in said
    assert f"python3 -m edge_workbench approve-verifier {d}" in said
    assert ("An AI agent must stop here and report this; it must not edit "
            "verifier.py or verifier.lock.") in said


def test_an_approved_verifier_passes(tmp_path, ledger):
    d = _dir(tmp_path)
    approve_in_tmp(d, ledger)
    assert _said(d) == ""


def test_a_forged_lock_fails(tmp_path, ledger):
    """The right hash in a lock nobody approved is not an approval."""
    d = _dir(tmp_path)
    (d / "verifier.lock").write_text(json.dumps({
        "verifier_sha256": approval.sha256((d / "verifier.py").read_bytes()),
        "published_answer_sha256": None, "kind": "definition",
        "method": "direct sum", "approver": "Sanjana", "date": "2026-11-16"}))
    said = _said(d)
    assert "was not written by approve-verifier" in said
    assert "must not edit verifier.py or verifier.lock" in said


def test_an_edited_lock_fails(tmp_path, ledger):
    d = _dir(tmp_path)
    lock = approve_in_tmp(d, ledger)
    lock.write_text(lock.read_text().replace("direct sum", "something else"))
    assert "was not written by approve-verifier" in _said(d)


def test_an_edited_verifier_fails(tmp_path, ledger):
    d = _dir(tmp_path)
    approve_in_tmp(d, ledger)
    with (d / "verifier.py").open("a") as fh:
        fh.write("\n# one harmless-looking change\n")
    said = _said(d)
    assert "verifier.py has changed since it was approved" in said
    assert "approved by a test on 2026-01-01 as definition / direct sum" in said
    assert "approve-verifier" in said


def test_a_changed_published_answer_fails(tmp_path, ledger):
    d = _dir(tmp_path)
    spec = d / "workbench" / "spec"
    spec.mkdir(parents=True)
    (spec / "authored.json").write_text(json.dumps(
        {"example": {"expect": {"answer": 5}}}))
    approve_in_tmp(d, ledger)
    assert approval.answer_problems(d, True, 5) == ([], [])
    assert approval.answer_problems(d, True, 5.0) == ([], [])
    found, todo = approval.answer_problems(d, True, 6)
    assert "published answer has changed since the verifier was approved" in found[0]
    assert any("approve-verifier" in t for t in todo)
    assert "no longer does" in approval.answer_problems(d, False, None)[0][0]


def test_an_answer_first_published_after_approval_needs_approval(tmp_path, ledger):
    d = _dir(tmp_path)
    approve_in_tmp(d, ledger)
    found, _ = approval.answer_problems(d, True, 5)
    assert "is new since the verifier was approved" in found[0]


def _git(d: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(d), "-c", "user.name=t",
                    "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


def test_committed_only_counts_only_a_committed_lock(tmp_path, ledger):
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH")
    d = _dir(tmp_path)
    approve_in_tmp(d, ledger)
    assert _said(d) == ""
    assert "--committed-only" in _said(d, committed_only=True)
    _git(d, "init", "-q")
    _git(d, "add", "verifier.py", "verifier.lock")
    _git(d, "commit", "-q", "-m", "approved")
    assert _said(d, committed_only=True) == ""
    ledger.unlink()                      # committed: no ledger needed at all
    assert _said(d) == ""
    with (d / "verifier.py").open("a") as fh:
        fh.write("\n# changed after the commit\n")
    assert "has changed since it was approved" in _said(d, committed_only=True)


def test_approving_needs_a_person_at_a_terminal(tmp_path, ledger, capsys):
    d = _dir(tmp_path)
    assert approval.approve(d, "toy") == 2
    assert "must be run by a person, in a terminal" in capsys.readouterr().err
    assert not (d / "verifier.lock").exists()
    assert not ledger.exists()


def _review(d: Path, typed: str) -> tuple[int, str]:
    import io
    out = io.StringIO()
    return approval._review(d, "toy", lambda prompt: typed, out), out.getvalue()


def test_the_review_shows_the_file_then_the_diff_and_wants_the_method(
        tmp_path, ledger):
    d = _dir(tmp_path)
    code, shown = _review(d, "yes")
    assert code == 1 and "Not approved" in shown
    assert not (d / "verifier.lock").exists() and not ledger.exists()

    code, shown = _review(d, "direct sum")
    assert code == 0
    assert "this is the whole file" in shown and "def solve(instance):" in shown
    assert "KIND    definition" in shown and "METHOD  direct sum" in shown
    assert "published answer is not known yet" in shown
    assert _said(d) == ""
    assert json.loads((d / "verifier.lock").read_text())["method"] == "direct sum"

    with (d / "verifier.py").open("a") as fh:
        fh.write("\n# a later edit\n")
    assert "has changed since it was approved" in _said(d)
    code, shown = _review(d, "direct sum")
    assert code == 0 and "Changes since it was last approved" in shown
    assert "+# a later edit" in shown and "def solve" not in shown
    assert _said(d) == ""


def test_a_verifier_that_breaks_its_contract_cannot_be_approved(tmp_path, ledger):
    d = _dir(tmp_path, "import os\n" + GOOD)
    code, shown = _review(d, "direct sum")
    assert code == 1 and "imports `os`" in shown and "Fix these first" in shown
    assert not (d / "verifier.lock").exists()


# ---------------------------------------------------------- end to end ---

def _example(tmp_path: Path, ledger: Path) -> Path:
    if spec_check.upstream() is None:
        pytest.skip("no edge-core-ir checkout")
    d = tmp_path / "bellman-ford"
    shutil.copytree(ROOT / "examples" / "bellman-ford", d,
                    ignore=shutil.ignore_patterns("verifier.lock"))
    approve_in_tmp(d, ledger)
    return d


def test_check_stops_at_inputs_when_the_verifier_was_edited(tmp_path, ledger, capsys):
    d = _example(tmp_path, ledger)
    with (d / "verifier.py").open("a") as fh:
        fh.write("\n# edited to make a failing check pass\n")
    assert author.main(["check", str(d)]) != 0
    out = capsys.readouterr().out
    assert "✗ inputs" in out
    assert "verifier.py has changed since it was approved" in out
    assert f"approve-verifier {d}" in out
    assert "An AI agent must stop here" in out
    assert not (d / "index.html").exists()


def test_a_never_approved_verifier_is_asked_for_once_at_the_end(
        tmp_path, ledger, capsys):
    d = _example(tmp_path, ledger)
    (d / approval.LOCK).unlink()
    assert author.main(["check", str(d)]) != 0
    out = capsys.readouterr().out
    assert "… inputs" in out and "… approval" in out
    assert "✓ instance" in out
    assert "covers verifier.py" in out and "published answer" in out
    assert f"approve-verifier {d}" in out
    assert not (d / "index.html").exists()


def test_check_stops_at_instance_when_the_published_answer_changed(
        tmp_path, ledger, capsys):
    d = _example(tmp_path, ledger)
    artifact = d / "workbench" / "spec" / "authored.json"
    data = json.loads(artifact.read_text())
    data["example"]["expect"]["answer"]["1"] = 99
    artifact.write_text(json.dumps(data))
    assert author.main(["check", str(d)]) != 0
    out = capsys.readouterr().out
    assert "✓ inputs" in out and "✗ instance" in out
    assert "published answer has changed since the verifier was approved" in out
    assert "An AI agent must stop here" in out


# ------------------------------------------------- in-session approval ---

def test_confirm_needs_the_sha_of_the_file_that_was_shown(tmp_path, ledger,
                                                         capsys):
    d = _dir(tmp_path)
    assert approval.approve(d, "toy", confirm="direct sum",
                            sha="0" * 12) == 1
    assert "not the file that was shown" in capsys.readouterr().err
    assert not (d / approval.LOCK).exists()
    assert approval.approve(d, "toy", confirm="direct sum", sha="abc") == 2


def test_confirm_with_the_right_sha_and_method_approves(tmp_path, ledger):
    d = _dir(tmp_path)
    sha = approval.sha256((d / "verifier.py").read_bytes())
    assert approval.approve(d, "toy", confirm="wrong method", sha=sha) == 1
    assert not (d / approval.LOCK).exists()
    assert approval.approve(d, "toy", confirm="direct sum", sha=sha[:12]) == 0
    lock = json.loads((d / approval.LOCK).read_text())
    assert lock["how"] == "confirmed in Claude Code"
    assert approval.problems(d) == ([], [])
