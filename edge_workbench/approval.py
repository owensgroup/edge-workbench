# -*- coding: utf-8 -*-
"""Has a person approved this verifier, and has it changed since?

WHY
---
The verifier is what the cascade is checked against. If whoever wrote the
cascade can also edit the verifier, a failing check can be made to pass by
changing the wrong file -- and when an AI agent writes the cascade, that is
the cheapest way for it to "pass". So the verifier is pinned:

    verifier.lock   beside verifier.py, committed. Holds the sha256 of
                    verifier.py, the hash of the answer the tutorial
                    publishes for its worked example, KIND, METHOD, who
                    approved and when.

`check` passes its inputs stage only if

    1. verifier.py's hash is the one in verifier.lock, AND
    2. verifier.lock is the committed one (identical to HEAD's), OR its hash
       is in the approvals ledger on this machine.

and passes its instance stage only if the published answer's hash is the one
in the lock. The ledger is `~/.config/edge-workbench/approved.json`, outside
every repository; only `approve-verifier` writes it, and that command refuses
to run unless a person is at a terminal and types the METHOD's name.

WHAT THIS IS, AND IS NOT
------------------------
The bar is that forging an approval takes a deliberate, visible, out-of-repo
act (Sanjana's decision): editing a file under ~/.config, committing, or
pointing EDGE_WORKBENCH_LEDGER somewhere else. None of those can happen by
accident while "fixing a failing check", and each one shows. It is not
tamper-proof against someone who sets out to forge it; nothing local is.

`--committed-only` ignores the ledger. Tests and CI use it: there, only an
approval that was committed counts.
"""

from __future__ import annotations

import difflib
import getpass
import hashlib
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from edge_workbench import verifier

LOCK = "verifier.lock"
LEDGER_ENV = "EDGE_WORKBENCH_LEDGER"
ARTIFACT = "authored.json"            # where the published answer is kept

AGENT_STOP = ("An AI agent must stop here and report this; it must not edit "
              "verifier.py or verifier.lock.")


def ledger_path() -> Path:
    override = os.environ.get(LEDGER_ENV)
    if override:
        return Path(override)
    return Path.home() / ".config" / "edge-workbench" / "approved.json"


def ledger_overridden() -> bool:
    return bool(os.environ.get(LEDGER_ENV))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def answer_hash(answer) -> str:
    """Hash of a published answer, as the answer check compares it."""
    return sha256(json.dumps(verifier.normalise(answer), sort_keys=True).encode())


def published_answer(directory: Path) -> tuple[bool, object]:
    """(is one stated, the answer) from the checked tutorial data."""
    path = Path(directory) / "workbench" / "spec" / ARTIFACT
    try:
        expect = (json.loads(path.read_text()).get("example") or {}).get("expect") or {}
    except (OSError, json.JSONDecodeError, AttributeError):
        return False, None
    return ("answer" in expect), expect.get("answer")


# --------------------------------------------------------------- state ---

def _git(directory: Path, *args: str) -> bytes | None:
    try:
        r = subprocess.run(["git", "-C", str(directory), *args],
                           capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def committed(directory: Path, name: str) -> bytes | None:
    """HEAD's version of a file in `directory`, or None."""
    return _git(Path(directory), "show", f"HEAD:./{name}")


def _ledger() -> dict:
    try:
        data = json.loads(ledger_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {"approvals": []}
    if not isinstance(data, dict) or not isinstance(data.get("approvals"), list):
        return {"approvals": []}
    return data


def _in_ledger(lock_hash: str) -> bool:
    return any(isinstance(e, dict) and e.get("lock_sha256") == lock_hash
               for e in _ledger()["approvals"])


def read_lock(directory: Path) -> dict | None:
    try:
        lock = json.loads((Path(directory) / LOCK).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(lock, dict) or not isinstance(
            lock.get("verifier_sha256"), str):
        return None
    return lock


def _next(directory: Path) -> list[str]:
    return [
        "A person reads verifier.py and, if it is the verifier they chose, "
        "approves it in a terminal: "
        f"python3 -m edge_workbench approve-verifier {directory}",
        AGENT_STOP,
        f"Commit verifier.py and {LOCK} together, then run again: "
        f"python3 -m edge_workbench check {directory}",
    ]


def _who(lock: dict) -> str:
    return (f"approved by {lock.get('approver', '?')} on "
            f"{lock.get('date', '?')} as {lock.get('kind', '?')} / "
            f"{lock.get('method', '?')}")


def problems(directory: Path, committed_only: bool = False
             ) -> tuple[list[str], list[str]]:
    """(what is wrong with the approval, what to do). Both empty if approved."""
    directory = Path(directory)
    lock_file = directory / LOCK
    source = directory / "verifier.py"
    if not source.exists():
        return [], []                       # reported as a missing input
    if not lock_file.exists():
        return ([f"verifier.py has never been approved: there is no {LOCK} "
                 f"beside it. Nothing is checked against a verifier no "
                 f"person has approved."], _next(directory))
    raw = lock_file.read_bytes()
    lock = read_lock(directory)
    is_head = committed(directory, LOCK) == raw
    known = is_head or (not committed_only and _in_ledger(sha256(raw)))
    if lock is None or not known:
        if committed_only and not is_head and _in_ledger(sha256(raw)):
            why = (f"{LOCK} is approved on this machine but is not the "
                   f"committed one, and --committed-only counts only a "
                   f"committed approval. Commit verifier.py and {LOCK}.")
            return [why], [f"Commit verifier.py and {LOCK} together, then "
                           f"run again."]
        return ([f"{LOCK} was not written by approve-verifier: it is neither "
                 f"the committed {LOCK} nor an approval recorded on this "
                 f"machine"
                 + (" (--committed-only: only the committed one counts)"
                    if committed_only else "")
                 + ". A lock written or edited by hand approves nothing."],
                _next(directory))
    if sha256(source.read_bytes()) != lock["verifier_sha256"]:
        return ([f"verifier.py has changed since it was approved "
                 f"({_who(lock)}). The approval was of the earlier text."],
                _next(directory))
    return [], []


def answer_problems(directory: Path, stated: bool, answer
                    ) -> tuple[list[str], list[str]]:
    """Is the tutorial's published answer the one that was approved?"""
    lock = read_lock(directory)
    if lock is None:
        return [], []                       # the inputs stage already said so
    pinned = lock.get("published_answer_sha256")
    now = answer_hash(answer) if stated else None
    if pinned == now:
        return [], []
    if pinned is None:
        what = (f"the tutorial's published answer ({answer!r}) was not known "
                f"when the verifier was approved, so nobody has approved it")
    elif now is None:
        what = ("the tutorial published an answer when the verifier was "
                "approved, and no longer does")
    else:
        what = (f"the tutorial's published answer has changed since the "
                f"verifier was approved; it is now {answer!r}")
    return ([what + f" ({_who(lock)}). The published answer is pinned with "
             f"the verifier: changing either needs a person's approval."],
            _next(directory))


# ------------------------------------------------------------- approve ---

def _approved_text(old_hash: str | None, directory: Path) -> str | None:
    """The verifier text that was last approved, if it can still be found."""
    if not old_hash:
        return None
    kept = ledger_path().parent / "approved-text" / f"{old_hash}.py"
    for data in (kept.read_bytes() if kept.exists() else None,
                 committed(directory, "verifier.py")):
        if data is not None and sha256(data) == old_hash:
            return data.decode("utf-8", "replace")
    return None


def _approver(directory: Path) -> str:
    name = _git(directory, "config", "user.name")
    return (name.decode().strip() if name else "") or getpass.getuser()


def approve(directory: Path, slug: str, out=None) -> int:
    """Interactive. Shows what is being approved and writes the lock.

    Refuses without a terminal on both ends: this is the one step that must
    be a person's, so it cannot be piped, scripted or run by an agent's tool.
    """
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("approve-verifier must be run by a person, in a terminal: "
              "standard input and output must both be a terminal.\n"
              + AGENT_STOP, file=sys.stderr)
        return 2
    return _review(directory, slug, input, out or sys.stdout)


def _review(directory: Path, slug: str, ask, out) -> int:
    """Everything after the terminal check. Reached only through `approve`,
    and by the tests, which hand it a temp directory and a throwaway ledger."""
    directory = Path(directory).resolve()
    source = directory / "verifier.py"

    def say(text: str = "") -> None:
        print(text, file=out)

    if not source.exists():
        say(f"no verifier.py in {directory}")
        return 1

    text = source.read_text()
    said = verifier.declared(source)
    old = read_lock(directory)
    before = _approved_text(old and old.get("verifier_sha256"), directory)

    say(f"Approving {source}")
    say()
    if before is None:
        say("No earlier approved text was found; this is the whole file:")
        say()
        for i, line in enumerate(text.splitlines(), 1):
            say(f"  {i:>4}  {line}")
    elif before == text:
        say("verifier.py is unchanged since it was last approved.")
    else:
        say(f"Changes since it was last approved ({_who(old)}):")
        say()
        for line in difflib.unified_diff(
                before.splitlines(), text.splitlines(),
                "approved", "now", lineterm=""):
            say("  " + line)
    say()

    static = verifier.static_problems(source)
    found, drawn = (static, None) if static else verifier.inspect_verifier(
        source, slug)
    stated, answer = published_answer(directory)
    kind = said.get("KIND")
    say(f"  KIND    {kind}"
        + (f": {verifier.KINDS[kind]}" if kind in verifier.KINDS else ""))
    say(f"  METHOD  {said.get('METHOD')}")
    say(f"  answer  {said.get('ANSWER_LABEL')}")
    if stated:
        say(f"  the tutorial publishes, for its worked example: {answer!r}")
        if old and old.get("published_answer_sha256") not in (
                None, answer_hash(answer)):
            say("      !! this differs from the answer approved last time")
    else:
        say("  the tutorial's published answer is not known yet (the "
            "tutorial-data step\n  has not run). `check` will ask for "
            "approval once more when it is.")
    say()
    if found:
        say(f"verifier.py does not meet its contract ({len(found)} problem(s)):")
        for f in found:
            say(f"  - {f}")
        say()
        say("Not approved. Fix these first.")
        return 1
    say("  contract: every static check passes")
    if drawn is not None:
        say(f"  random instances: {len(drawn.usable)} made, deterministic, "
            f"{drawn.trivial} with the answer an empty run would give")
    say()

    method = said["METHOD"]
    say("Approve this only if it is the verifier YOU chose or supplied, and "
        "the answer above\nis the one your tutorial states.")
    try:
        typed = ask("Type the METHOD shown above to approve, or anything "
                      "else to cancel: ")
    except (EOFError, KeyboardInterrupt):
        typed = ""
    if typed.strip() != method.strip():
        say("Not approved. Nothing was written.")
        return 1

    raw = source.read_bytes()
    if raw.decode("utf-8", "replace") != text:
        say("verifier.py changed while you were reading it. Not approved.")
        return 1
    lock = {
        "_comment": "Written by `python3 -m edge_workbench approve-verifier`. "
                    "Commit it with verifier.py. A lock edited by hand fails "
                    "the check.",
        "verifier_sha256": sha256(raw),
        "published_answer_sha256": answer_hash(answer) if stated else None,
        "kind": kind,
        "method": method,
        "approver": _approver(directory),
        "date": date.today().isoformat(),
    }
    lock_bytes = (json.dumps(lock, indent=1, ensure_ascii=False) + "\n").encode()
    (directory / LOCK).write_bytes(lock_bytes)

    ledger_file = ledger_path()
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger = _ledger()
    ledger["approvals"].append({
        "lock_sha256": sha256(lock_bytes),
        "verifier_sha256": lock["verifier_sha256"],
        "directory": str(directory),
        "approver": lock["approver"],
        "date": lock["date"],
    })
    ledger_file.write_text(json.dumps(ledger, indent=1) + "\n")
    kept = ledger_file.parent / "approved-text"
    kept.mkdir(exist_ok=True)
    (kept / f"{lock['verifier_sha256']}.py").write_bytes(raw)

    say(f"Approved. Wrote {directory / LOCK} and recorded it in {ledger_file}.")
    say(f"Commit verifier.py and {LOCK} together.")
    return 0
