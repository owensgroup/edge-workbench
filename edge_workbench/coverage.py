# -*- coding: utf-8 -*-
"""Did every line of the specification actually run?

This is the gate that replaced comparing against a recorded trace. A trace
proves a run matched a run someone did before. It says nothing about whether
the specification in front of you was executed -- and the failure that
matters most here is silent: an Einsum that never runs produces no wrong
value, raises nothing, and leaves a page that looks complete. The reader sees
a cascade of 24 steps and has no way to tell that three of them were
decoration.

So the build refuses to write a page unless every Einsum the author wrote
executed at least once, and every node the IR holds is accounted for by
something the author wrote.

THREE DISTINCT THINGS, WHICH ARE EASY TO CONFLATE
-------------------------------------------------
1. Every IR node is MAPPED. `cascade.json`'s labels turn written Einsums into
   IR node indices, and one written Einsum may lower to several nodes (E04 is
   a three-arm `cases`). A node no label claims is a node the page can never
   show, whatever it computes.
2. Every written Einsum EXECUTED. Mapping is static; this is dynamic. A label
   can be mapped correctly and still never run -- a body Einsum in a cascade
   that stops at generation 0, say.
3. Every initialization Einsum EXECUTED. Same question, different section.

(1) without (2) is the trap: the label map looks complete, the build is
green, and an Einsum sat out the whole run.

ARMS: WHAT "EXECUTED" MEANS WHEN THE SPECIFICATION BRANCHES
-----------------------------------------------------------
Two constructs make part of what the author wrote conditional:

  * a case statement gives one Einsum several arms, each over a region of
    its iteration space (`... if n = j+1`). An arm whose region is empty in
    every run of the Einsum computed nothing;
  * a conditional cascade runs ONE of several Einsum sequences per
    generation (`TOP-DOWN(...) if TopDown_i == True`). The Einsums of an arm
    the run never takes did not run.

A worked example is small, and the tutorial's author chose it: a BFS on six
vertices may never switch direction. Failing the build for that would ask the
author to change the example to suit the tool. Passing it silently would
bring back the failure this gate exists for. So:

  * everything outside an arm must execute on the worked example, as before;
  * an arm must be exercised by the worked example OR by at least one of the
    verifier's random instances -- the same instances whose answers are
    checked, so an arm counted here is an arm whose result was verified;
  * an arm the worked example never reaches is named on the coverage line
    and marked on the page, so a reader is not shown it as something that
    happened.

An arm written `empty` computes nothing and is not counted.
"""

from __future__ import annotations

from edge_workbench.cascade_shape import flat_nodes, stopping_conditions  # noqa: F401

from dataclasses import dataclass, field


@dataclass
class Coverage:
    """What ran, what did not, and enough detail to say why it matters."""

    executions: dict[str, int] = field(default_factory=dict)
    """Written Einsum label -> how many times it ran."""

    unmapped_nodes: list[int] = field(default_factory=list)
    never_executed: list[str] = field(default_factory=list)
    init_expected: int = 0
    init_executed: int = 0
    node_count: int = 0

    not_on_example: list[str] = field(default_factory=list)
    """Arms the worked example never reached, as the report names them:
    `E03 case 4 (n > j+1)`, `E09 (BOTTOM-UP arm)`."""

    unexercised: list[str] = field(default_factory=list)
    """Of those, the ones no random instance reached either. Fatal."""

    arm_keys: list[str] = field(default_factory=list)
    """Tally keys behind `not_on_example`, in the same order."""

    @property
    def needs_instances(self) -> bool:
        """True when random instances have to be consulted for some arm."""
        return bool(self.not_on_example)

    @property
    def ok(self) -> bool:
        return (
            not self.unmapped_nodes
            and not self.never_executed
            and not self.unexercised
            and self.init_executed >= self.init_expected
        )

    def summary(self) -> str:
        ran = len(self.executions)
        total = sum(self.executions.values())
        text = (
            f"{ran} written Einsums over {self.node_count} IR nodes, "
            f"{total} executions, {self.init_executed}/{self.init_expected} "
            f"initialization"
        )
        if self.not_on_example:
            text += (f"; not reached on the worked example, exercised by a "
                     f"random instance: {', '.join(self.not_on_example)}")
        return text

    def report(self) -> str:
        lines = []
        if self.unmapped_nodes:
            lines.append(
                f"  IR nodes no label claims: {self.unmapped_nodes}\n"
                f"    Nothing can render these, so nothing can review them. "
                f"Add them to `labels` in cascade.json -- as a LIST on an "
                f"existing label if they are arms of one written Einsum."
            )
        if self.never_executed:
            lines.append(
                f"  written Einsums that never ran: {self.never_executed}\n"
                f"    These are mapped but dead. Either the cascade never "
                f"reaches them, or the stopping condition fires before they "
                f"run. A page showing them as steps would be showing work "
                f"that did not happen."
            )
        if self.unexercised:
            lines.append(
                f"  arms nothing exercised: {self.unexercised}\n"
                f"    Neither the worked example nor any of the verifier's "
                f"random instances reaches these. An arm no run takes is "
                f"specification nobody has checked: make `random_instance` "
                f"produce an instance that takes it."
            )
        if self.init_executed < self.init_expected:
            lines.append(
                f"  initialization: {self.init_executed} of "
                f"{self.init_expected} Einsums ran"
            )
        return "\n".join(lines)


def _mapped_indices(labels: dict) -> dict[int, str]:
    """IR node index -> the written Einsum that claims it."""
    owner: dict[int, str] = {}
    for label, value in labels.items():
        for idx in value if isinstance(value, list) else [value]:
            owner[int(idx)] = label
    return owner


def arm_key(node: int, arm: int) -> str:
    """The tally key for one arm of a case statement."""
    return f"{node}#arm{arm}"


def measure(program: dict, cascade: dict, executed: dict,
            elsewhere: dict | None = None) -> Coverage:
    """Compare what the spec contains against what the run actually ran.

    `program` is the IR, `cascade` the label map, and `executed` the driver's
    own per-IR-node tally from this run -- not a recording, and not inferred
    from the emitted steps.

    That distinction is the whole design. Steps are a presentation choice:
    initialization runs four Einsums and emits one step, and a lowered
    `cases` runs three and emits one. Counting steps would call those covered
    while three quarters of the nodes sat idle.

    `elsewhere` is the same tally summed over the verifier's random
    instances; it is consulted only for arms (see the module docstring), and
    None means it has not been collected yet.
    """
    from edge_workbench import cascade_shape as shape

    nodes = flat_nodes(program)
    init = program.get("initialization", {}).get("einsums", [])
    labels = cascade.get("labels", {})
    owner = _mapped_indices(labels)

    ran = {str(k) for k, n in executed.items() if n}

    # Roll the per-node tally up to the labels the author wrote, so the
    # report speaks in the spec's own names. A label counts as executed only
    # if EVERY node it lowered to ran -- an unexecuted `cases` arm is a piece
    # of the written Einsum that did not happen.
    placed = shape.placement(program)
    literals = shape.literal_values(program)

    def count(tally: dict | None, key) -> int:
        tally = tally or {}
        return tally.get(key, tally.get(str(key), 0))

    executions: dict[str, int] = {}
    never: list[str] = []
    pending: list[tuple[str, str]] = []      # (tally key, how to name it)
    for label, value in labels.items():
        idxs = value if isinstance(value, list) else [value]
        counts = [count(executed, i) for i in idxs]
        executions[label] = min(counts) if counts else 0
        for i, n in zip(idxs, counts):
            in_arm = placed[i]["arms"] if i < len(placed) else []
            if not n:
                if in_arm:
                    arm = in_arm[-1]
                    what = (f"{arm['macro']} arm" if arm.get("macro")
                            else f"arm {arm['arm'] + 1} of {arm['of']}")
                    pending.append((str(i), f"{label} ({what})"))
                elif label not in never:
                    never.append(label)
                continue
            # The Einsum ran; each of its case arms must have claimed a point.
            for k, arm in enumerate(shape.arms(nodes[i])):
                if arm.get("expression") is None:
                    continue
                if not count(executed, arm_key(i, k)):
                    cond = shape.arm_condition(arm, literals) or "otherwise"
                    pending.append((arm_key(i, k),
                                    f"{label} case {k + 1} ({cond})"))

    unexercised = ([name for key, name in pending
                    if not count(elsewhere, key)]
                   if elsewhere is not None else [])
    return Coverage(
        executions=dict(sorted(executions.items())),
        unmapped_nodes=[i for i in range(len(nodes)) if i not in owner],
        never_executed=sorted(never),
        init_expected=len(init),
        init_executed=sum(1 for k in range(len(init)) if f"init:{k}" in ran),
        node_count=len(nodes),
        not_on_example=[name for _, name in pending],
        arm_keys=[key for key, _ in pending],
        unexercised=unexercised,
    )
