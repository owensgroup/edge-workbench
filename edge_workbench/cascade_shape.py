# -*- coding: utf-8 -*-
"""The shape of a program's cascade: a tree, read as a list.

A cascade's body used to be a flat list of Einsums. With edge-core-ir's local
patches for `cases`, conditional cascades and inner cascades (issues 8, 9 and
10 in docs/issues-for-edge-core-ir.md) an entry may also be

    {"kind": "conditional", "arms": [{"when": ..., "einsums": [...], "macro": ...}]}
    {"einsums": [...], "stopping_conditions": [...], "iterative_rank": ...}

Everything in the workbench that numbers IR nodes -- the label map, coverage,
the driver's tally, the formulas -- numbers them the same way: depth first,
in written order, exactly as `edge_ir.ir.einsum.flatten` does. This module is
that numbering for the JSON form, plus what the tree says about each node.
A flat program is its own flattening, so nothing changes for one.
"""

from __future__ import annotations


def _is_einsum(entry: dict) -> bool:
    return "output_tensor" in entry


def body(program: dict) -> list:
    return program["main_edge"]["cascade"]["einsums"]


def flat_nodes(program: dict) -> list[dict]:
    """Every Einsum of the cascade, depth first, in written order."""
    out: list[dict] = []

    def walk(entries: list) -> None:
        for entry in entries:
            if _is_einsum(entry):
                out.append(entry)
            elif entry.get("kind") == "conditional":
                for arm in entry.get("arms", []):
                    walk(arm.get("einsums", []))
            else:
                walk(entry.get("einsums", []))

    walk(body(program))
    return out


def placement(program: dict) -> list[dict]:
    """Where each flat node sits in the tree, by flat index.

    `arms`     the conditional-cascade arms around it, outermost first, as
               {"conditional": n, "arm": k, "of": how many arms, "macro": name}
    `ranks`    the iterative rank variables of the cascades around it,
               outermost first (`["i"]`, or `["i", "j"]` in an inner cascade)
    """
    out: list[dict] = []
    counter = [0]

    def rank_of(cascade: dict, default: str | None) -> str | None:
        spec = cascade.get("iterative_rank")
        if spec:
            return spec["rank_variable"]
        stops = cascade.get("stopping_conditions") or []
        return stops[0]["rank_variable"] if stops else default

    def walk(entries: list, arms: tuple, ranks: tuple) -> None:
        for entry in entries:
            if _is_einsum(entry):
                out.append({"arms": list(arms), "ranks": list(ranks)})
            elif entry.get("kind") == "conditional":
                number = counter[0]
                counter[0] += 1
                branches = entry.get("arms", [])
                for k, arm in enumerate(branches):
                    walk(arm.get("einsums", []),
                         arms + ({"conditional": number, "arm": k,
                                  "of": len(branches),
                                  "macro": arm.get("macro")},), ranks)
            else:
                inner = rank_of(entry, None)
                walk(entry.get("einsums", []), arms,
                     ranks + ((inner,) if inner else ()))

    top = program["main_edge"]["cascade"]
    outer = rank_of(top, "i")
    walk(body(program), (), (outer,) if outer else ())
    return out


def inner_cascades(program: dict) -> list[dict]:
    """Every inner cascade, outermost first, depth first."""
    out: list[dict] = []

    def walk(entries: list) -> None:
        for entry in entries:
            if _is_einsum(entry):
                continue
            if entry.get("kind") == "conditional":
                for arm in entry.get("arms", []):
                    walk(arm.get("einsums", []))
            else:
                out.append(entry)
                walk(entry.get("einsums", []))

    walk(body(program))
    return out


def stopping_conditions(program: dict) -> list[dict]:
    """Every diamond: the outer cascade's first, then each inner cascade's."""
    top = program["main_edge"]["cascade"]
    out = list(top.get("stopping_conditions") or [])
    for inner in inner_cascades(program):
        out += inner.get("stopping_conditions") or []
    return out


def is_cases(node: dict) -> bool:
    return (node.get("expression") or {}).get("kind") == "cases"


def arms(node: dict) -> list[dict]:
    """The arms of a `cases` Einsum; [] for any other."""
    return (node["expression"].get("arms") or []) if is_cases(node) else []


def expressions(node: dict) -> list[dict]:
    """The expression trees an Einsum evaluates: one, or one per `cases` arm
    (an arm written `empty` has none)."""
    if is_cases(node):
        return [a["expression"] for a in arms(node) if a.get("expression")]
    return [node["expression"]] if node.get("expression") else []


def all_specs(node: dict) -> list[dict]:
    """The Einsum's specs, with every `cases` arm's own."""
    out = list(node.get("specs") or [])
    for arm in arms(node):
        out += arm.get("specs") or []
    return out


# ------------------------------------------------------------ conditions ---

def rank_text(rank: dict) -> str:
    kind = rank.get("kind")
    if kind == "var":
        return rank["name"]
    if kind == "literal":
        return str(rank["value"])
    if kind == "shape_sym":
        return rank["name"]
    if kind == "arith":
        return f"{rank_text(rank['lhs'])}{rank['op']}{rank_text(rank['rhs'])}"
    if kind == "func":
        return f"{rank['func_name']}({', '.join(rank_text(a) for a in rank['args'])})"
    return "?"


def _value_text(node: dict, literals: dict) -> str:
    kind = node.get("kind")
    if kind == "tensor_value":
        proj = node["proj"]
        if proj["tensor"] in literals:
            return str(literals[proj["tensor"]])
        ranks = ", ".join(rank_text(r) for r in proj.get("ranks", []))
        return proj["tensor"] + (f"_{{{ranks}}}" if ranks else "")
    if kind == "rank_value":
        return rank_text(node["expr"])
    if kind == "property_app":
        inner = ", ".join(
            p["tensor"] + "_{" + ", ".join(rank_text(r) for r in p["ranks"]) + "}"
            for p in node.get("operands", []))
        return f"||{inner}||"
    return "?"


def predicate_text(pred: dict | None, literals: dict | None = None) -> str:
    """A condition as einsum.edge writes it: `n = j+1`, `u = s and v != s`,
    `TopDown_i == True`. `literals` maps a literal declaration to its value."""
    literals = literals or {}
    if not pred:
        return ""
    kind = pred.get("kind")
    if kind == "comparison":
        if "kind" in pred["lhs"] and pred["lhs"]["kind"] in (
                "tensor_value", "rank_value", "property_app"):
            return (f"{_value_text(pred['lhs'], literals)} {pred['op']} "
                    f"{_value_text(pred['rhs'], literals)}")
        op = "=" if pred["op"] == "==" else pred["op"]
        return f"{rank_text(pred['lhs'])} {op} {rank_text(pred['rhs'])}"
    if kind == "and":
        return " and ".join(predicate_text(o, literals) for o in pred["operands"])
    if kind == "or":
        return " or ".join(predicate_text(o, literals) for o in pred["operands"])
    if kind == "not":
        return f"not ({predicate_text(pred['operand'], literals)})"
    if kind == "set_membership":
        cs = pred.get("coord_set") or {}
        word = "not in" if pred.get("negated") else "in"
        return f"{rank_text(pred['member'])} {word} {cs.get('name', '?')}"
    if kind == "diamond_boolean_app":
        return pred.get("name", "?") + "(...)"
    return "?"


def literal_values(program: dict) -> dict:
    """Zero-rank declarations carrying a literal value: name -> value."""
    return {d["name"]: d["value"] for d in program.get("declarations", [])
            if not d.get("ranks") and d.get("value") is not None}


def arm_condition(arm: dict, literals: dict | None = None) -> str:
    """A case arm's condition as written; "" for `otherwise`."""
    parts = [predicate_text(arm.get(k), literals) for k in ("where", "when")]
    return " and ".join(p for p in parts if p)
