"""Approvals for tests: temp directories and a throwaway ledger only.

Nothing here can approve a real verifier. `approve_in_tmp` writes a lock and
records it in a ledger the test owns (EDGE_WORKBENCH_LEDGER); a run that uses
such a ledger says so on its `inputs` line. `trust_committed_copy` is for
tests that copy an example out of the repository: the copy has no git
history, so the test first requires the EXAMPLE's approval to be the
committed one, and only then lets the copy's identical lock count.
"""

from __future__ import annotations

import json
from pathlib import Path

from edge_workbench import approval, verifier


def _record(lock_file: Path, ledger: Path) -> None:
    try:
        data = json.loads(ledger.read_text())
    except (OSError, json.JSONDecodeError):
        data = {"approvals": []}
    data["approvals"].append(
        {"lock_sha256": approval.sha256(lock_file.read_bytes())})
    ledger.write_text(json.dumps(data))


def approve_in_tmp(directory: Path, ledger: Path) -> Path:
    """What approve-verifier writes, for a directory a test made."""
    directory = Path(directory)
    said = verifier.declared(directory / "verifier.py")
    stated, answer = approval.published_answer(directory)
    lock = {
        "verifier_sha256": approval.sha256(
            (directory / "verifier.py").read_bytes()),
        "published_answer_sha256":
            approval.answer_hash(answer) if stated else None,
        "kind": said.get("KIND"), "method": said.get("METHOD"),
        "approver": "a test", "date": "2026-01-01",
    }
    lock_file = directory / approval.LOCK
    lock_file.write_text(json.dumps(lock, indent=1) + "\n")
    _record(lock_file, ledger)
    return lock_file


def trust_committed_copy(example: Path, copy: Path, ledger: Path) -> None:
    """Fail unless `example`'s approval is committed; then trust its copy."""
    found, todo = approval.problems(example, committed_only=True)
    assert not found, "\n".join(
        [f"{example.name}: its verifier has no committed approval."]
        + found + ["NEXT:"] + todo)
    _record(copy / approval.LOCK, ledger)
