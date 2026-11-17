"""A short text of a diagnostics file, for a pull request, a log or a reader without a page."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from . import chain, claims, fileformat, rule

MOVES_ORDER = [k for k in rule.CLASSES if k in rule.MOVES]
#: The characters that make Markdown of a text where it stands in a line: emphasis, code,
#: a link, HTML, an entity, a table column (`|`). Each is escaped with a backslash, which
#: CommonMark allows before any ASCII punctuation.
_MARKUP = re.compile(r"([\\`*_\[\]<>#!|~&$])")
#: What starts a block where a text starts a line, or follows a list's `- `: a list (`-`,
#: `+`, `1.`, `1)`), a rule (`---`) or a heading's underline (`===`). Escaped the same way.
_START = re.compile(r"^(?:([-+=])|(\d{1,9})(?=[.)]))")
#: What GitHub reads in the text Markdown has already shown, where a backslash no longer
#: counts: a mention (`@`), an issue (`#1`, `GH-1`, `/issues/1`), an emoji (`:x:`), a link
#: (`https:`, `mailto:`, `www.`) and maths (`$`). A word joiner (U+2060), which shows as
#: nothing, follows each and breaks it.
_JOIN = re.compile(r"([:#@]|/(?=\d)|(?i:www)(?=\.)|(?i:gh)(?=-\d))")


def _n(value) -> str:
    return f"{value:,}".replace(",", " ")


def _exact(value: float) -> str:
    """A number with every digit, as the page writes one (`exactText`): the shortest that
    reads back as the same float, positional from 1e-6 up to 1e21 as JavaScript writes it,
    and beyond with `e` and the minus sign, never `1e-05` or `1e+21`.

    >>> [_exact(v) for v in (1e-05, 0.0005, 1e-07, 2.5, 10.0, 0.1, 123456.75, 1e21, -1.5e300, 0.0)]
    ['0.00001', '0.0005', '1e−7', '2.5', '10', '0.1', '123456.75', '1e21', '−1.5e300', '0']
    """
    if value == 0:
        return "0"
    exact = Decimal(repr(abs(float(value)))).normalize()
    digits = "".join(map(str, exact.as_tuple().digits))
    point = exact.adjusted() + 1  # where the point stands after the first digit
    if -6 < point <= 21:
        if len(digits) <= point:
            text = digits + "0" * (point - len(digits))
        elif point > 0:
            text = digits[:point] + "." + digits[point:]
        else:
            text = "0." + "0" * -point + digits
    else:
        text = digits[0] + ("." + digits[1:] if len(digits) > 1 else "") + f"e{point - 1}"
    return ("\u2212" if value < 0 else "") + text.replace("-", "\u2212")


def _rounded(value: float, digits: int) -> Decimal:
    """`value` at `digits` significant digits, as the page's `toPrecision` rounds it: from
    its exact binary value, and a half away from zero, where Python's format rounds a half
    to even (1234.5 is 1235 on the page).

    >>> _rounded(1234.5, 4), _rounded(-1234.5, 4), _rounded(9.9995, 4), _rounded(0.0, 4)
    (Decimal('1235'), Decimal('-1235'), Decimal('9.999'), Decimal('0'))
    """
    exact = Decimal(value)
    if not exact:
        return exact
    return exact.quantize(Decimal(1).scaleb(exact.adjusted() - digits + 1), rounding=ROUND_HALF_UP)


def _short(value: float, digits: int) -> str:
    """A number at `digits` significant digits, as the page's `formatNumber` writes one at
    four: no trailing zero, and a power of ten below 0.001 and from 1e4 on, chosen by the
    number as it is written (`1e−5` and `1.2e4`, never `1e-05`, `1.2e+04` or `12000`).

    >>> [_short(v, 2) for v in (120.0, 0.5, 2.44, 1e-05, 12345.0, 0.00099996, 9999.5)]
    ['120', '0.5', '2.4', '1e−5', '1.2e4', '0.001', '1e4']
    """
    shown = _rounded(value, digits)
    if not shown:
        return "0"
    if Decimal("0.001") <= abs(shown) < 10000:
        return _exact(float(shown))
    kept = "".join(map(str, shown.as_tuple().digits)).rstrip("0") or "0"
    mantissa = kept[0] + ("." + kept[1:] if len(kept) > 1 else "")
    return ("\u2212" if value < 0 else "") + f"{mantissa}e{shown.adjusted()}".replace("-", "\u2212")


def _percent(size: float) -> str:
    """A noise in percent, at two significant digits, written as `_short` writes them. A
    noise called large (above `chain.LARGE_NOISE`) reads above 1 %: at more digits, up to
    six, where two round it onto 1 %, and "just over 1" where six still do.

    >>> [_percent(s) for s in (0.0244, 1.2, 0.005, 1e-07, 0.0104, 0.0100001, 0.010000000000000002, 0.01)]
    ['2.4', '120', '0.5', '1e−5', '1.04', '1.00001', 'just over 1', '1']
    """
    bound = chain.LARGE_NOISE * 100
    for digits in range(2, 7):
        if size <= chain.LARGE_NOISE or _rounded(size * 100, digits) > Decimal(bound):
            return _short(size * 100, digits)
    return f"just over {_exact(bound)}"


def md(text) -> str:
    r"""A text from a file as Markdown that shows it as it is, on GitHub too: no table
    column, emphasis, link, list, rule, code, maths, emoji or heading of its own, no issue
    it refers to and nobody it mentions. The summary is pasted into pull requests, where a
    mention notifies and a reference marks the issue. Leading spaces stay, as no-break
    spaces (four would make code).

    A commit's hash is left whole: GitHub links it to that commit of the repository it is
    pasted in, a target the file cannot choose, and a hash is copied to be used. The word
    joiners go with a copied text.

    >>> print(md("fix|x <b>[a](b)</b> *now*"))
    fix\|x \<b\>\[a\](b)\</b\> \*now\*
    >>> print(md("- 1. ---"), md("12) a"), md("2026 was"))
    \- 1. --- 12\) a 2026 was
    >>> md("@team #1 $x$ https://a.org") == "@\u2060team \\#\u20601 \u2060\\$x\u2060\\$ https:\u2060//a.org"
    True
    """
    text = str(text)
    lead = len(text) - len(text.lstrip(" "))
    text = _JOIN.sub("\\1\u2060", "\u00a0" * lead + text[lead:]).replace("$", "\u2060$")
    text = _MARKUP.sub(r"\\\1", text)
    return _START.sub(lambda m: "\\" + m.group(1) if m.group(1) else m.group(2) + "\\", text)


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
                        f"{name} {_percent(size)} %" + (" (large)" if size > chain.LARGE_NOISE else ""))  # fmt: skip
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
            "| Step | Kind | Explained | Values moved | Missing before | Missing after | As claimed | Off claim | Not claimed | Claimed, not moved | Claimed, not judged |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]  # fmt: skip
    for number, step in enumerate(data["steps"], fileformat.first_step(data)):
        blocks = data["counts"]["steps"][step["id"]].values()
        moved = sum(b["classes"][k] for b in blocks for k in rule.MOVES)
        # a result missing on both sides is missing before and missing after
        gone_before = sum(b["missing"]["before"] + b["missing"]["both"] for b in blocks)
        gone_after = sum(b["missing"]["after"] + b["missing"]["both"] for b in blocks)
        if step["claim"]:
            verdicts = [sum(b["verdicts"][v] for b in blocks) for v in
                        (claims.AS_CLAIMED, claims.OFF_CLAIM, claims.NOT_CLAIMED, claims.NOT_MOVED, claims.OPEN)]  # fmt: skip
            said = [_n(v) for v in verdicts]
        else:
            said = ["no claim", "", "", "", ""]
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
        out.append(f"- {labels[step['id']]}: tolerance {_exact(tol['value'])} ({tol['basis']}); {said}")
    if by_state:
        total = fileformat.noise_of_states(order[0], order[-1])
        out.append(f"- The whole way: tolerance {_exact(data['rule']['total_tolerance'])}; "
                   f"{noise_text(total, names, ends(order[0], order[-1], total))}")  # fmt: skip
    floors = data["rule"]["floors"]
    out.append(
        f"- Floors: {len(floors)}, one per {word['one']} and reference unit, "
        f"{_exact(data['rule']['floor_factor'])} of the median size in {md(states[data['rule']['floors_from']]['label'])}"
        f" ({sum(1 for f in floors if f['basis'] == 'declared')} declared, "
        f"{sum(1 for f in floors if f['basis'] == 'none')} without a result to take one from)."
    )
    out.append(f"- Beyond 10x: one size more than {_exact(data['rule']['beyond'])} times the other.")
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
