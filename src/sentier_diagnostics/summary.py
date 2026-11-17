"""A short text of a diagnostics file, for a pull request, a log or a reader without a page."""

from __future__ import annotations

import re
from collections.abc import Mapping

from . import chain, claims, fileformat, rule

MOVES_ORDER = [k for k in rule.CLASSES if k in rule.MOVES]
#: The characters that make Markdown of a text where it stands in a line (GitHub's flavour
#: included: `|` adds a table column, `#12` links an issue, `$` starts maths). Each is
#: escaped with a backslash, which CommonMark allows before any ASCII punctuation.
_MARKUP = re.compile(r"([\\`*_\[\]<>#!|~&$])")


def _n(value) -> str:
    return f"{value:,}".replace(",", " ")


def md(text) -> str:
    r"""A text from a file as Markdown that shows it as it is: no table column, emphasis,
    link, markup or heading of its own, and an `@` that mentions nobody (a word joiner
    follows it). The summary is pasted into pull requests, where a mention notifies.

    >>> print(md("fix|x <b>[a](b)</b> *now*"))
    fix\|x \<b\>\[a\](b)\</b\> \*now\*
    >>> md("@team") == "@\u2060team"
    True
    """
    return _MARKUP.sub(r"\\\1", str(text)).replace("@", "@\u2060")


def noise_text(noise: Mapping, names: Mapping[str, str], ends: int | None = None) -> str:
    """What a noise says, with its size per indicator: a state's, measured between two of its
    builds, or that of a comparison, the sum of its two states' (`between` is null), measured
    at `ends` of its two ends. An indicator the noise holds no size for was not measured; a
    size above `chain.LARGE_NOISE` is called large.

    >>> noise_text({"measured": True, "between": ["a", "b"], "by": {"w": 0.0244, "c": 0.0}}, {"w": "Water", "c": "Climate", "t": "Tox"})
    'noise measured between a and b: Water 2.4 % (large), Climate identical; Tox not measured'
    >>> noise_text({"measured": True, "between": None, "by": {"w": 0.0244}}, {"w": "Water"}, ends=1)
    'noise of its two states, measured at 1 of 2 ends: Water 2.4 % (large)'
    """
    if not noise["measured"]:
        return "noise not measured"
    said = []
    for key, name in names.items():
        if key in noise["by"]:
            size = noise["by"][key]
            said.append(f"{name} identical" if size == 0 else
                        f"{name} {size * 100:.2g} %" + (" (large)" if size > chain.LARGE_NOISE else ""))  # fmt: skip
    absent = [name for key, name in names.items() if key not in noise["by"]]
    nothing = "no result beyond the floor in both builds" if noise["between"] else "no result beyond the floor where it was measured"
    if noise["between"] is None:
        between = "noise of its two states" + (f", measured at {ends} of 2 ends" if ends is not None and ends < 2 else "")
    else:
        between = f"noise measured between {md(noise['between'][0])} and {md(noise['between'][1])}"
    return between + ": " + (", ".join(said) or nothing) + (
        "; " + ", ".join(absent) + " not measured" if absent else ""
    )


def text(data: Mapping) -> str:
    """The summary as Markdown: the states, every step with what it moved and how that holds
    against its claim, the whole way per indicator with its attribution, and what the file
    leaves out."""
    states = {s["id"]: s for s in data["states"]}
    # every text of the file goes through `md`: it is shown, never read as Markdown
    names = {i["id"]: md(i["short"] or i["name"]) for i in data["indicators"]}
    labels = {s["id"]: md(s["label"]) for s in data["steps"]}
    count = data["items_count"]
    many = md(data["item"]["many"])
    word = {k: md(v) for k, v in fileformat.indicator_word(data).items()}
    indicators = word["one"] if len(data["indicators"]) == 1 else word["many"]
    out = [f"# {md(data['title'])}", ""]
    if data["audience"] == "local":
        out += ["**Local file: its writer has not said that it may be published.**", ""]
    if data.get("about"):
        out += [md(data["about"]), ""]
    out.append("States: " + " → ".join(md(s["label"]) for s in data["states"]))
    for state in data["states"]:
        join = state["join"]
        if join:
            out.append(
                f"Read into {md(state['label'])}: {_n(join['compared'])} compared, {_n(join['unmatched'])} "
                f"unmatched, {_n(join['ambiguous'])} ambiguous." + (f" {md(join['note'])}" if join["note"] else "")
            )
    out.append(
        f"{_n(count['all'])} {many}, {len(data['indicators'])} {indicators}. "
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
    for number, step in enumerate(data["steps"], fileformat.first_step(data)):
        blocks = data["counts"]["steps"][step["id"]].values()
        moved = sum(b["classes"][k] for b in blocks for k in rule.MOVES)
        # a result missing on both sides is missing before and missing after
        gone_before = sum(b["missing"]["before"] + b["missing"]["both"] for b in blocks)
        gone_after = sum(b["missing"]["after"] + b["missing"]["both"] for b in blocks)
        if step["claim"]:
            verdicts = [sum(b["verdicts"][v] for b in blocks) for v in
                        (claims.AS_CLAIMED, claims.OFF_CLAIM, claims.NOT_CLAIMED, claims.NOT_MOVED)]  # fmt: skip
            said = [_n(v) for v in verdicts]
        else:
            said = ["no claim", "", "", ""]
        out.append(
            f"| {number}. {labels[step['id']]} | {md(step['kind'])} | {'yes' if step['explained'] else '**no: nothing explains it**'} "
            f"| {_n(moved)} | {_n(gone_before)} | {_n(gone_after)} | " + " | ".join(said) + " |"
        )
    if data["states"][0]["kind"] == "published":
        blocks = data["counts"]["steps"][data["steps"][0]["id"]].values()
        residual = sum(b["classes"][k] for b in blocks for k in rule.MOVES)
        said = "1 value is" if residual == 1 else f"{_n(residual)} values are"
        out += ["", f"Step 0: {said} not reproduced within its tolerance. That is the "
                "residual the chain starts from, not a regression."]
    first, last = md(data["states"][0]["label"]), md(data["states"][-1]["label"])
    out += ["", f"## The whole way: {first} → {last}", ""]
    header = [word["one"][:1].upper() + word["one"][1:], *rule.CLASSES, "Largest step", "Spread over steps", "Not attributable",
              "Moved by what nothing explains"]  # fmt: skip
    out.append("| " + " | ".join(header) + " |")
    out.append("|---|" + "---:|" * (len(header) - 1))
    for indicator in data["indicators"]:
        key = indicator["id"]
        classes = data["counts"]["total"][key]["classes"]
        said = data["attribution"][key]
        ranked = sorted(said["dominant"].items(), key=lambda kv: -kv[1])
        largest = ", ".join(f"{labels[s]} ({_n(n)})" for s, n in ranked if n) or "none"
        out.append(
            f"| {names[key]} | " + " | ".join(_n(classes[k]) for k in rule.CLASSES)
            + f" | {largest} | {_n(said['spread'])} | {_n(said['not_attributable'])} | {_n(said['unexplained_moved'])} |"
        )
    out += ["", "## Rule", ""]
    by_state = fileformat.states_carry_noise(data)
    order = data["states"]

    def ends(first, last, noise):
        """At how many of the two ends the noise was measured: the fewest over its indicators,
        or, where it holds none (nothing beyond the floor), the ends that measured at all. The
        published results count, being exact."""
        keys = noise["by"] or {}
        if not keys:
            return sum(1 for one in (first, last) if one["kind"] == "published" or one["noise"]["measured"])
        return min(fileformat.ends_known(first, last, key) for key in keys)

    if by_state:
        for one in order:
            said = "exact: the published results have no builds" if one["kind"] == "published" else noise_text(one["noise"], names)
            out.append(f"- {md(one['label'])}: {said}")
    for k, step in enumerate(data["steps"]):
        tol = step["tolerance"]
        said = noise_text(step["noise"], names, ends(order[k], order[k + 1], step["noise"]) if by_state else None)
        out.append(f"- {labels[step['id']]}: tolerance {tol['value']:g} ({tol['basis']}); {said}")
    if by_state:
        total = fileformat.noise_of_states(order[0], order[-1])
        out.append(f"- The whole way: tolerance {data['rule']['total_tolerance']:g}; "
                   f"{noise_text(total, names, ends(order[0], order[-1], total))}")  # fmt: skip
    floors = data["rule"]["floors"]
    out.append(
        f"- Floors: {len(floors)}, one per {word['one']} and reference unit, "
        f"{data['rule']['floor_factor']:g} of the median size in {md(states[data['rule']['floors_from']]['label'])}"
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
        out += ["", md(note)]
    return "\n".join(out) + "\n"
