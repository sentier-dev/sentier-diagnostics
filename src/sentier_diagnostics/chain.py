"""A chain of results, from the published ones to the current build, counted and attributed.

A chain is an ordered list of states (sets of results over the same items and
indicators) and the steps between each state and the next. The first state is usually
what its publisher released, the second the same database computed again by us (step 0,
the reproduction), and every later state one change further. A plain before/after
comparison is a chain of two states and one step.

Every step is counted with the one rule (`rule`), and judged against its claim where it
has one (`claims`). The whole way, first state against last, is counted too ("total").

**Attribution is exact.** For one item in one indicator the difference between the last
state and the first is the sum of the differences of the steps, because each step starts
where the one before ended. A step that no cause explains (`explained: false`: a rebuild
on another machine, or a change between two states that nobody named) keeps its share,
named as what nothing explains. Where an item has no result in one of the states, its
steps on either side of that state cannot be measured, and its total is counted as not
attributable instead of being split.

`build` writes the whole file and checks it (`fileformat.errors`); `write` stores it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import __version__, claims, fileformat, rule

FILE = "diagnostics.json"


def tolerance(value=None, basis=None, note=None) -> dict:
    """The tolerance of a step: below it, two results agree. Without a value, the default."""
    if value is None:
        return {
            "value": rule.DEFAULT_TOLERANCE,
            "basis": "default",
            "note": "one order of magnitude above the solver noise of two builds",
        }
    return {"value": float(value), "basis": basis or "declared", "note": note}


def noise(between=None, by=None, note=None) -> dict:
    """What two builds of one state differ by, per indicator; not measured without `between`."""
    if not between:
        return {"measured": False, "between": None, "by": None, "note": note}
    return {"measured": True, "between": list(between), "by": dict(by or {}), "note": note}


def noise_of(first: Mapping[str, float | None], second: Mapping[str, float | None]) -> float:
    """The noise of one indicator: the largest relative difference between two builds of one
    state, over the items both hold. `first` and `second` are `{item: result}`.

    >>> noise_of({"a": 1.0, "b": 2.0, "c": 5.0}, {"a": 1.0, "b": 2.5})
    0.2
    """
    shared = [k for k in first if rule.is_value(first[k]) and rule.is_value(second.get(k))]
    return max((rule.relative_difference(first[k], second[k]) for k in shared), default=0.0)


def step(id: str, label: str, *, kind: str, explained: bool = True, about: str | None = None,
         link: str | None = None, claim: dict | None = None, tolerance: dict | None = None,
         noise: dict | None = None) -> dict:  # fmt: skip
    """One step between two states, as `build` takes it."""
    return {
        "id": id,
        "label": label,
        "about": about,
        "kind": kind,
        "explained": explained,
        "link": link,
        "claim": claim,
        "tolerance": tolerance,
        "noise": noise,
    }


def state(id: str, label: str, *, kind: str = "build", about: str | None = None,
          identity: Mapping[str, str] | None = None, join: Mapping | None = None) -> dict:  # fmt: skip
    """One state: a set of results. `kind` is "published" for the results its publisher released.

    `join` is what the reader that made the state counted when it matched its rows to items:
    `{"compared": n, "unmatched": n, "ambiguous": n, "note": text or None}`.
    """
    if join is not None:
        join = {"compared": join["compared"], "unmatched": join.get("unmatched", 0),
                "ambiguous": join.get("ambiguous", 0), "note": join.get("note")}  # fmt: skip
    return {"id": id, "label": label, "about": about, "kind": kind,
            "identity": dict(identity or {}), "join": join}  # fmt: skip


def explanation(text: str, by: dict, *, step: str | None = None, indicator: str | None = None,
                item: str | None = None, link: str | None = None, doc: str | None = None,
                not_checked: str | None = None, finding: str = "reason") -> dict:  # fmt: skip
    """Why something moved, in words, with who wrote it (`claims.origin`). An explanation is
    a claim: it never changes a count, a class or a verdict.

    `finding` is "reason" when the text gives one, and "none found" when someone looked and
    found none. Where nothing is written, no one has said anything: a third state.
    """
    source = {"link": link, "doc": doc} if (link or doc) else None
    return {
        "about": {"step": step, "indicator": indicator, "item": item},
        "finding": finding,
        "text": text,
        "by": by,
        "source": source,
        "not_checked": not_checked,
    }


def _indicator(entry) -> dict:
    if isinstance(entry, Mapping):
        found = {k: entry.get(k) for k in ("id", "name", "short", "unit")}
    else:
        found = dict(zip(("id", "name", "short", "unit"), entry, strict=True))
    return found


def _values(values, states, indicators) -> dict:
    """The results as `{state: {indicator: {item: value}}}`, refusing what is not a result."""
    found = {}
    for one in states:
        by_indicator = values.get(one["id"])
        if by_indicator is None:
            raise ValueError(f"no results for the state {one['id']!r}")
        unknown = set(by_indicator) - set(indicators)
        if unknown:
            raise ValueError(f"state {one['id']!r} has results of an unknown indicator: {sorted(unknown)}")
        found[one["id"]] = {}
        for indicator in indicators:
            column = {}
            for item, value in (by_indicator.get(indicator) or {}).items():
                if not isinstance(item, str):
                    raise ValueError(f"an item id is not a text: {item!r}")
                if value is not None and not rule.is_value(value):
                    raise ValueError(
                        f"state {one['id']!r}, {indicator}, {item}: {value!r} is not a finite "
                        "number (a missing result is None, never zero and never NaN)"
                    )
                column[item] = None if value is None else float(value)
            found[one["id"]][indicator] = column
    return found


def build(
    title: str,
    *,
    indicators: Iterable,
    states: list[dict],
    steps: list[dict],
    values: Mapping[str, Mapping[str, Mapping[str, float | None]]],
    units: Mapping[str, str | None] | None = None,
    names: Mapping[str, Mapping] | None = None,
    item_word: tuple[str, str] = ("item", "items"),
    about: str | None = None,
    floors: Mapping[tuple[str, str | None], float] | None = None,
    floor_factor: float = rule.FLOOR_FACTOR,
    listed: int = 200,
    tier: str = "items",
    audience: str = "local",
    claim_lists: bool = True,
    explanations: Iterable[dict] = (),
    notes: Iterable[str] = (),
    breakdowns: Mapping[str, Mapping[str, str]] | None = None,
) -> dict:
    """A whole chain, counted, judged, attributed and checked.

    - `indicators`: `(id, name, short, unit)` or dicts with those keys.
    - `states`: `state(...)`, in order; `steps`: `step(...)`, one fewer than the states.
    - `values`: `{state id: {indicator id: {item id: result or None}}}`; an item absent from
      a state's indicator is missing there.
    - `units`: the reference unit of each item; floors are kept apart per unit.
    - `names`: `{item id: {"name", "place", "group"}}`.
    - `floors`: `{(indicator, unit): floor}` where the project sets them; otherwise each is
      `floor_factor` times the median size of the first state's results of that group.
    - `listed`: how many items go into the file with their results, the worst first.
    - `tier`: "items", or "counts" for a file that holds counts only and no item.
    - `claim_lists`: false to leave every claim's list of items out of the file (only its
      size, `reach`, is written). The verdicts are still worked out here; a reader of the
      file cannot work them out again, and the page says so. A file of counts holds no list.
    - `audience`: "local" (the default: for the people who made it) or "public" (its writer
      says it may be published). The tool checks only that it is one of the two.
    - `breakdowns`: `{item id: {step id or "total": file name}}`.
    """
    meta = [_indicator(i) for i in indicators]
    ids = [i["id"] for i in meta]
    if len(steps) != len(states) - 1:
        raise ValueError("a chain has one step fewer than it has states")
    units, names = dict(units or {}), dict(names or {})
    table = _values(values, states, ids)
    order = [s["id"] for s in states]
    items = sorted({item for s in order for i in ids for item in table[s][i]})
    for item in items:
        units.setdefault(item, None)

    # floors: one per indicator and reference unit, from the first state
    computed = rule.floors_of(table[order[0]], units, floor_factor)
    floor_table, floor_rows = {}, []
    for indicator in ids:
        for unit in sorted({units[item] for item in items}, key=lambda u: (u is None, u or "")):
            key = (indicator, unit)
            if floors is not None and key in floors:
                value, basis, n = float(floors[key]), "declared", 0
            else:
                value, n = computed.get(key, (0.0, 0))
                basis = "median" if n else "none"
            floor_table[key] = value
            floor_rows.append({"indicator": indicator, "unit": unit, "value": value,
                               "basis": basis, "n": n})  # fmt: skip

    # the steps, normalised
    out_steps = []
    for k, one in enumerate(steps):
        found_claim = one.get("claim")
        out_steps.append({
            "id": one["id"],
            "from": order[k],
            "to": order[k + 1],
            "label": one["label"],
            "about": one.get("about"),
            "kind": one["kind"],
            "explained": bool(one.get("explained", True)),
            "link": one.get("link"),
            "claim": claims.published(found_claim, tier == "items" and claim_lists) if found_claim else None,
            "tolerance": one.get("tolerance") or tolerance(),
            "noise": one.get("noise") or noise(),
        })  # fmt: skip
    total_tolerance = max(s["tolerance"]["value"] for s in out_steps)
    published_first = states[0].get("kind") == "published"

    def judged(k, indicator, item):
        """Class, direction, band and verdict of one item in one step (k) or the total (None)."""
        first, last = (order[0], order[-1]) if k is None else (order[k], order[k + 1])
        before, after = table[first][indicator].get(item), table[last][indicator].get(item)
        if k is None:
            level, tol = None, total_tolerance
        else:
            said = out_steps[k]["noise"]
            level = (said["by"] or {}).get(indicator) if said["measured"] else None
            tol = out_steps[k]["tolerance"]["value"]
        floor = floor_table[(indicator, units[item])]
        kind, way, where = rule.judge(before, after, floor=floor, tolerance=tol, noise=level)
        said_verdict = None
        if k is not None and steps[k].get("claim"):
            entries = claims.entries_for(steps[k]["claim"], indicator)
            covering = [e for e in entries if claims.covers(e, item, indicator)]
            said_verdict = claims.verdict(kind, before, after, way, covering)
        return before, after, kind, way, where, said_verdict

    # every pair, once
    found = {
        (k, indicator, item): judged(k, indicator, item)
        for k in [*range(len(out_steps)), None]
        for indicator in ids
        for item in items
    }

    def block(k, indicator):
        classes = dict.fromkeys(rule.CLASSES, 0)
        missing = dict.fromkeys(fileformat.MISSING_SIDES, 0)
        bands = dict.fromkeys(rule.BANDS, 0)
        ways = dict.fromkeys(rule.DIRECTIONS, 0)
        verdicts = dict.fromkeys(claims.VERDICTS, 0) if k is not None and steps[k].get("claim") else None
        closer = further = None
        if published_first and k not in (None, 0):
            closer = further = 0
        for item in items:
            before, after, kind, way, where, said = found[(k, indicator, item)]
            classes[kind] += 1
            if kind == rule.MISSING:
                missing["both" if before is None and after is None else "before" if before is None else "after"] += 1
            if where:
                bands[where] += 1
            if way:
                ways[way] += 1
            if verdicts is not None:
                verdicts[said] += 1
            if closer is not None and kind in rule.MOVES:
                reference = table[order[0]][indicator].get(item)
                if reference is not None:
                    was, now = abs(before - reference), abs(after - reference)
                    closer += now < was
                    further += now > was
        return {"pairs": len(items), "classes": classes, "missing": missing, "directions": ways, "bands": bands,
                "verdicts": verdicts, "closer": closer, "further": further}  # fmt: skip

    counts = {
        "steps": {s["id"]: {i: block(k, i) for i in ids} for k, s in enumerate(out_steps)},
        "total": {i: block(None, i) for i in ids},
    }

    # attribution: which step carries the largest share of each item's whole difference
    attribution = {}
    for indicator in ids:
        dominant = {s["id"]: 0 for s in out_steps}
        not_attributable = unexplained_moved = 0
        for item in items:
            if any(
                not s["explained"] and found[(k, indicator, item)][2] in rule.MOVES
                for k, s in enumerate(out_steps)
            ):
                unexplained_moved += 1
            if found[(None, indicator, item)][2] not in rule.MOVES:
                continue
            series = [table[s][indicator].get(item) for s in order]
            if any(v is None for v in series):
                not_attributable += 1
                continue
            deltas = [abs(series[k + 1] - series[k]) for k in range(len(out_steps))]
            dominant[out_steps[deltas.index(max(deltas))]["id"]] += 1
        attribution[indicator] = {"dominant": dominant, "not_attributable": not_attributable,
                                  "unexplained_moved": unexplained_moved}  # fmt: skip

    # the items worth a look, the worst first
    def worth(item):
        for indicator in ids:
            for k in [*range(len(out_steps)), None]:
                _, _, kind, _, _, said = found[(k, indicator, item)]
                if kind not in rule.QUIET or said == claims.NOT_MOVED:
                    return True
        return False

    def worst(item):
        keys = []
        for indicator in ids:
            for k in [*range(len(out_steps)), None]:
                before, after, kind, *_ = found[(k, indicator, item)]
                keys.append(rule.severity(before, after, kind))
        return (min(keys), item)

    qualifying = sorted((item for item in items if worth(item)), key=worst)
    shown = qualifying[: max(0, listed)] if tier == "items" else []
    breakdowns = breakdowns or {}
    any_claim = any(s.get("claim") for s in steps)
    out_items = []
    for item in shown:
        about_item = names.get(item) or {}
        record = {
            "id": item,
            "name": about_item.get("name") or item,
            "place": about_item.get("place"),
            "group": about_item.get("group"),
            "unit": units[item],
            "values": {i: [table[s][i].get(item) for s in order] for i in ids},
            "classes": {},
            "directions": {},
            "bands": {},
            "verdicts": {} if any_claim else None,
            "breakdowns": dict(breakdowns[item]) if item in breakdowns else None,
        }
        for indicator in ids:
            row = [found[(k, indicator, item)] for k in [*range(len(out_steps)), None]]
            record["classes"][indicator] = [r[2] for r in row]
            record["directions"][indicator] = [r[3] for r in row]
            record["bands"][indicator] = [r[4] for r in row]
            if any_claim:
                record["verdicts"][indicator] = [r[5] for r in row[:-1]]
        out_items.append(record)

    data = {
        "format": fileformat.FORMAT,
        "tier": tier,
        "audience": audience,
        "title": title,
        "about": about,
        "item": {"one": item_word[0], "many": item_word[1]},
        "indicators": meta,
        "rule": {
            "floor_factor": floor_factor,
            "floors_from": order[0],
            "beyond": rule.BEYOND_FACTOR,
            "total_tolerance": total_tolerance,
            "floors": floor_rows,
        },
        "states": [
            {"id": s["id"], "label": s["label"], "about": s.get("about"),
             "kind": s.get("kind", "build"), "identity": dict(s.get("identity") or {}),
             "join": s.get("join")}
            for s in states
        ],  # fmt: skip
        "steps": out_steps,
        "counts": counts,
        "attribution": attribution,
        "items": out_items,
        "items_count": {
            "all": len(items),
            "qualifying": len(qualifying),
            "listed": len(out_items),
            "not_listed": len(qualifying) - len(out_items),
        },
        "explanations": list(explanations),
        "notes": list(notes),
        "made_by": f"sentier-diagnostics {__version__}",
    }
    errors = fileformat.errors(data)
    if errors:
        raise ValueError("not a diagnostics file: " + "; ".join(errors[:10]))
    return data


def dumps(data: Mapping) -> str:
    """The text of a file: one line per listed item, so that a diff names the items."""
    listed = data.get("items") or []
    head = json.dumps(dict(data) | {"items": []}, indent=1, ensure_ascii=False, allow_nan=False)
    if listed:
        rows = ",\n".join("  " + json.dumps(i, ensure_ascii=False, allow_nan=False) for i in listed)
        opening, closing = head.rsplit('"items": []', 1)
        head = f'{opening}"items": [\n{rows}\n ]{closing}'
    return head + "\n"


def write(data: Mapping, path: Path) -> Path:
    """Write a file, checked first; refuse one larger than a page holds."""
    errors = fileformat.errors(data)
    if errors:
        raise ValueError("not a diagnostics file: " + "; ".join(errors[:10]))
    text = dumps(data)
    size = len(text.encode("utf-8"))
    if size > fileformat.MAX_BYTES:
        raise ValueError(
            f"the file would be {size} bytes, and a page holds {fileformat.MAX_BYTES} at most: "
            "list fewer items (`listed`)"
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read(path: Path) -> dict:
    """A file, read and checked; raises ValueError with every error found."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=_refuse)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot be read ({error})") from None
    errors = fileformat.errors(data)
    if errors:
        raise ValueError(f"{path}: " + "; ".join(errors[:10]))
    return data


def _refuse(constant):
    raise json.JSONDecodeError(f"{constant} is not a number a file may hold", constant, 0)
