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
"""

from __future__ import annotations

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

    @property
    def ok(self) -> bool:
        return (
            not self.unmapped_nodes
            and not self.never_executed
            and self.init_executed >= self.init_expected
        )

    def summary(self) -> str:
        ran = len(self.executions)
        total = sum(self.executions.values())
        return (
            f"{ran} written Einsums over {self.node_count} IR nodes, "
            f"{total} executions, {self.init_executed}/{self.init_expected} "
            f"initialization"
        )

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


def measure(program: dict, cascade: dict, executed: dict) -> Coverage:
    """Compare what the spec contains against what the run actually ran.

    `program` is the IR, `cascade` the label map, and `executed` the driver's
    own per-IR-node tally from this run -- not a recording, and not inferred
    from the emitted steps.

    That distinction is the whole design. Steps are a presentation choice:
    initialization runs four Einsums and emits one step, and a lowered
    `cases` runs three and emits one. Counting steps would call those covered
    while three quarters of the nodes sat idle.
    """
    nodes = program["main_edge"]["cascade"]["einsums"]
    init = program.get("initialization", {}).get("einsums", [])
    labels = cascade.get("labels", {})
    owner = _mapped_indices(labels)

    ran = {str(k) for k, n in executed.items() if n}

    # Roll the per-node tally up to the labels the author wrote, so the
    # report speaks in the spec's own names. A label counts as executed only
    # if EVERY node it lowered to ran -- an unexecuted `cases` arm is a piece
    # of the written Einsum that did not happen.
    executions: dict[str, int] = {}
    never: list[str] = []
    for label, value in labels.items():
        idxs = value if isinstance(value, list) else [value]
        counts = [executed.get(i, executed.get(str(i), 0)) for i in idxs]
        if not all(counts):
            never.append(label)
        executions[label] = min(counts) if counts else 0

    return Coverage(
        executions=dict(sorted(executions.items())),
        unmapped_nodes=[i for i in range(len(nodes)) if i not in owner],
        never_executed=sorted(never),
        init_expected=len(init),
        init_executed=sum(1 for k in range(len(init)) if f"init:{k}" in ran),
        node_count=len(nodes),
    )
