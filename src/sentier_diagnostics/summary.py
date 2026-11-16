"""A short text of a diagnostics file, for a pull request, a log or a reader without a page."""

from __future__ import annotations

from collections.abc import Mapping

from . import claims, rule

MOVES_ORDER = [k for k in rule.CLASSES if k in rule.MOVES]


def _n(value) -> str:
    return f"{value:,}".replace(",", " ")


def text(data: Mapping) -> str:
    """The summary as Markdown: the states, every step with what it moved and how that holds
    against its claim, the whole way per indicator with its attribution, and what the file
    leaves out."""
    states = {s["id"]: s for s in data["states"]}
    names = {i["id"]: i["short"] or i["name"] for i in data["indicators"]}
    count = data["items_count"]
    many = data["item"]["many"]
    out = [f"# {data['title']}", ""]
    if data["audience"] == "local":
        out += ["**Local file: its writer has not said that it may be published.**", ""]
    if data.get("about"):
        out += [data["about"], ""]
    out.append("States: " + " → ".join(s["label"] for s in data["states"]))
    for state in data["states"]:
        join = state["join"]
        if join:
            out.append(
                f"Read into {state['label']}: {_n(join['compared'])} compared, {_n(join['unmatched'])} "
                f"unmatched, {_n(join['ambiguous'])} ambiguous." + (f" {join['note']}" if join["note"] else "")
            )
    out.append(
        f"{_n(count['all'])} {many}, {len(data['indicators'])} indicators. "
        + (
            "This file holds counts only."
            if data["tier"] == "counts"
            else f"{_n(count['listed'])} of the {_n(count['qualifying'])} {many} worth a look are listed"
            + (f"; {_n(count['not_listed'])} are not." if count["not_listed"] else ".")
        )
    )
    out += ["", "## Steps", "",
            "| Step | Kind | Explained | Values moved | Missing before | Missing after | As claimed | Off claim | Not claimed | Claimed, not moved |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]  # fmt: skip
    for number, step in enumerate(data["steps"]):
        blocks = data["counts"]["steps"][step["id"]].values()
        moved = sum(b["classes"][k] for b in blocks for k in rule.MOVES)
        gone_before = sum(b["missing"]["before"] + b["missing"]["both"] for b in blocks)
        gone_after = sum(b["missing"]["after"] for b in blocks)
        if step["claim"]:
            verdicts = [sum(b["verdicts"][v] for b in blocks) for v in
                        (claims.AS_CLAIMED, claims.OFF_CLAIM, claims.NOT_CLAIMED, claims.NOT_MOVED)]  # fmt: skip
            said = [_n(v) for v in verdicts]
        else:
            said = ["no claim", "", "", ""]
        out.append(
            f"| {number}. {step['label']} | {step['kind']} | {'yes' if step['explained'] else '**no: nothing explains it**'} "
            f"| {_n(moved)} | {_n(gone_before)} | {_n(gone_after)} | " + " | ".join(said) + " |"
        )
    first, last = data["states"][0]["label"], data["states"][-1]["label"]
    out += ["", f"## The whole way: {first} → {last}", ""]
    header = ["Indicator", *[k for k in rule.CLASSES], "Largest step", "Not attributable", "Moved by what nothing explains"]
    out.append("| " + " | ".join(header) + " |")
    out.append("|---|" + "---:|" * (len(header) - 1))
    steps = {s["id"]: s for s in data["steps"]}
    for indicator in data["indicators"]:
        key = indicator["id"]
        classes = data["counts"]["total"][key]["classes"]
        said = data["attribution"][key]
        ranked = sorted(said["dominant"].items(), key=lambda kv: -kv[1])
        largest = ", ".join(f"{steps[s]['label']} ({_n(n)})" for s, n in ranked if n) or "none"
        out.append(
            f"| {names[key]} | " + " | ".join(_n(classes[k]) for k in rule.CLASSES)
            + f" | {largest} | {_n(said['not_attributable'])} | {_n(said['unexplained_moved'])} |"
        )
    out += ["", "## Rule", ""]
    for step in data["steps"]:
        tol = step["tolerance"]
        noise = step["noise"]
        out.append(
            f"- {step['label']}: tolerance {tol['value']:g} ({tol['basis']})"
            + (f"; noise measured between {noise['between'][0]} and {noise['between'][1]}" if noise["measured"] else "; noise not measured")
        )
    floors = data["rule"]["floors"]
    out.append(
        f"- Floors: {len(floors)}, one per indicator and reference unit, "
        f"{data['rule']['floor_factor']:g} of the median size in {states[data['rule']['floors_from']]['label']}"
        f" ({sum(1 for f in floors if f['basis'] == 'declared')} declared, "
        f"{sum(1 for f in floors if f['basis'] == 'none')} without a result to take one from)."
    )
    out.append(f"- Beyond 10x: one size more than {data['rule']['beyond']:g} times the other.")
    if data["explanations"]:
        kinds = {}
        for one in data["explanations"]:
            kinds[one["by"]["kind"]] = kinds.get(one["by"]["kind"], 0) + 1
        none_found = sum(1 for one in data["explanations"] if one["finding"] == "none found")
        out += ["", "Explanations: " + ", ".join(f"{n} by {k}" for k, n in sorted(kinds.items()))
                + (f"; {none_found} say that someone looked and found no reason" if none_found else "")
                + ". An explanation is a claim; it changes no count."]  # fmt: skip
    for note in data["notes"]:
        out += ["", note]
    return "\n".join(out) + "\n"
