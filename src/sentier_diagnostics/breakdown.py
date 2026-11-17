"""What the result of one item is made of, on both sides of a step: `sentier-diagnostics-breakdown/1`.

    {"format": "sentier-diagnostics-breakdown/1", "item": "p01", "from": "repro", "to": "fix-1",
     "indicators": {"x:climate": {
        "unit": "kg CO2 eq",
        "total": [0.52, 0.47],
        "parts": [{"label": "Fertiliser, nitrogen", "kind": "background process",
                   "values": [0.21, 0.16]}],
        "rest": [0.31, 0.31],
        "parts_not_listed": 14}}}

A part is whatever the result is made of: an elementary flow, a process of the
background, the item's own flows. Its two values are its contribution to the result
before and after, in the indicator's unit. Parts are chosen by the larger of their two
sizes, so that a part that is large on one side only is listed. What is not listed is
summed in `rest` and counted in `parts_not_listed`: the listed parts and the rest add up
to the total, and the check refuses a breakdown where they do not. Nothing is cut short
without saying so.

Whether a project may publish a breakdown is a question of its data's terms: it says
more about an inventory than a result does.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import rule
from .fileformat import MAX_ID, MAX_INDICATORS, MAX_WORD, is_count, is_text, text_errors

FORMAT = "sentier-diagnostics-breakdown/1"
MAX_PARTS = 200
#: The longest label of a part: a process's name, with its place.
MAX_PART_LABEL = 300
#: How closely the parts and the rest must add up to the total, relative to the largest
#: of the sizes involved: the sum of many products in floating point.
CLOSURE = 1e-9


def _adds_up(parts: Iterable[float], total: float) -> bool:
    parts = list(parts)
    size = max([abs(total), *map(abs, parts)], default=0.0)
    return abs(sum(parts) - total) <= CLOSURE * size


def errors(data) -> list[str]:
    """Everything wrong with a breakdown; nothing when a page can show it."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return [f"not a breakdown of format {FORMAT}"]
    found = [f"a key this format does not know: {k}" for k in sorted(set(data) - {"format", "item", "from", "to", "indicators"})]
    named = {k: data.get(k) for k in ("item", "from", "to")}
    found += [f"a breakdown names its item and the two states it compares: {e}"
              for e in text_errors("", named, dict.fromkeys(named, MAX_ID))]  # fmt: skip
    indicators = data.get("indicators")
    if not isinstance(indicators, dict) or not 0 < len(indicators) <= MAX_INDICATORS:
        return [*found, f"`indicators` is not a table of 1 to {MAX_INDICATORS}"]
    for key, entry in indicators.items():
        where = f"indicator {key!r}"
        if not is_text(key, MAX_ID) or not isinstance(entry, dict) or set(entry) != {"unit", "total", "parts", "rest", "parts_not_listed"}:
            found.append(f"{where}: not {{unit, total, parts, rest, parts_not_listed}}")
            continue
        pairs = [entry["total"], entry["rest"]]
        found += text_errors(where, entry, {"unit": MAX_WORD}, {"unit"})
        if not is_count(entry["parts_not_listed"]):
            found.append(f"{where}: `parts_not_listed` is not a count")
        parts = entry["parts"]
        if not isinstance(parts, list) or len(parts) > MAX_PARTS:
            found.append(f"{where}: `parts` is not a list of at most {MAX_PARTS}")
            continue
        if not all(isinstance(part, dict) and set(part) == {"label", "kind", "values"} for part in parts):
            found.append(f"{where}: a part is not {{label, kind, values}}")
            continue  # its sums cannot be read
        for n, part in enumerate(parts):
            found += text_errors(f"{where}, part {n}", part, {"label": MAX_PART_LABEL, "kind": MAX_WORD}, {"kind"})
        pairs += [part["values"] for part in parts]
        if not all(isinstance(p, list) and len(p) == 2 and all(rule.is_value(v) for v in p) for p in pairs):
            found.append(f"{where}: a total, rest or part is not [before, after] in finite numbers")
            continue
        if entry["rest"] != [0, 0] and entry["rest"] != [0.0, 0.0] and entry["parts_not_listed"] == 0:
            found.append(f"{where}: a rest without parts that are not listed")
        for side, name in ((0, "before"), (1, "after")):
            values = [p["values"][side] for p in parts] + [entry["rest"][side]]
            if not _adds_up(values, entry["total"][side]):
                found.append(f"{where}: the parts and the rest do not add up to the total {name}")
    return found


def build(item: str, before_state: str, after_state: str,
          indicators: Mapping[str, tuple[str | None, Iterable[tuple[str, str | None, float, float]]]],
          *, top: int = 20) -> dict:  # fmt: skip
    """A breakdown, checked. `indicators` is `{indicator: (unit, parts)}`, every part
    `(label, kind, before, after)`; the `top` largest by the larger of their two sizes are
    listed and the others summed into the rest."""
    out = {}
    for key, (unit, parts) in indicators.items():
        parts = [(label, kind, float(b), float(a)) for label, kind, b, a in parts]
        ranked = sorted(range(len(parts)), key=lambda i: (-max(abs(parts[i][2]), abs(parts[i][3])), i))
        chosen, left = ranked[:top], ranked[top:]
        out[key] = {
            "unit": unit,
            "total": [sum(p[2] for p in parts), sum(p[3] for p in parts)],
            "parts": [
                {"label": parts[i][0], "kind": parts[i][1], "values": [parts[i][2], parts[i][3]]}
                for i in chosen
            ],
            "rest": [sum(parts[i][2] for i in left), sum(parts[i][3] for i in left)],
            "parts_not_listed": len(left),
        }
    data = {"format": FORMAT, "item": item, "from": before_state, "to": after_state, "indicators": out}
    found = errors(data)
    if found:
        raise ValueError("not a breakdown: " + "; ".join(found))
    return data


def write(data: Mapping, path: Path) -> Path:
    found = errors(data)
    if found:
        raise ValueError("not a breakdown: " + "; ".join(found))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return path


def compares(diagnostics: Mapping, key: str) -> tuple[str, str]:
    """The two states a step of a diagnostics file compares, or the first and the last for
    the whole way (`"total"`)."""
    if key == "total":
        return diagnostics["states"][0]["id"], diagnostics["states"][-1]["id"]
    step = next(s for s in diagnostics["steps"] if s["id"] == key)
    return step["from"], step["to"]


def namings(diagnostics: Mapping) -> list[tuple[str, str, str]]:
    """Every breakdown a diagnostics file names: `(file name, item, step or "total")`."""
    return [
        (name, item["id"], key)
        for item in diagnostics["items"]
        for key, name in sorted((item["breakdowns"] or {}).items())
    ]


def against(data: Mapping, diagnostics: Mapping, named_by: tuple[str, str] | None = None) -> list[str]:
    """Whether a breakdown agrees with a diagnostics file: it is the breakdown of the item
    and step that name it (`named_by`, `(item, step or "total")`), and the totals of both
    sides are the item's results in the two states it compares."""
    if named_by is not None:
        item_id, key = named_by
        want = compares(diagnostics, key)
        if (data["item"], data["from"], data["to"]) != (item_id, *want):
            said = (
                f"named by {item_id!r} for {key!r}, which compares {want[0]!r} with {want[1]!r}, "
                f"it is the breakdown of {data['item']!r} from {data['from']!r} to {data['to']!r}"
            )
            return [said]
    states = [s["id"] for s in diagnostics["states"]]
    if data["from"] not in states or data["to"] not in states:
        return [f"breakdown of {data['item']!r}: compares states the file does not hold"]
    item = next((i for i in diagnostics["items"] if i["id"] == data["item"]), None)
    if item is None:
        return [f"breakdown of {data['item']!r}: the file does not list this item"]
    found = []
    first, second = states.index(data["from"]), states.index(data["to"])
    for key, entry in data["indicators"].items():
        if key not in item["values"]:
            found.append(f"breakdown of {data['item']!r}: an indicator the file does not hold, {key!r}")
            continue
        for side, at in ((0, first), (1, second)):
            result = item["values"][key][at]
            total = entry["total"][side]
            if result is None or not _adds_up([total], result):
                found.append(
                    f"breakdown of {data['item']!r}, {key}: its total {total!r} is not the "
                    f"item's result {result!r} in state {states[at]!r}"
                )
    return found
