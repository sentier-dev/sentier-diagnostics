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

from . import __version__, claims, fileformat, matrix, rule

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
    """What two builds of one state differ by, per indicator; not measured without `between`.
    It belongs to the state that was built twice (`state(..., noise=...)`), never to a step: a
    step and a run are compared with the noise of the two states they lie between (SPEC
    section 5.3). An indicator whose noise is None (`noise_of` found no pair to take it from) is
    left out: its noise was not measured, which is not the same as two identical builds."""
    if not between:
        return {"measured": False, "between": None, "by": None, "note": note}
    found = {k: v for k, v in (by or {}).items() if v is not None}
    return {"measured": True, "between": list(between), "by": found, "note": note}


#: Noise above this is large: it puts every smaller difference of its indicator "within
#: noise". The page and the summary say so; it is a defect to fix, not a width to absorb.
LARGE_NOISE = 1e-2


def noise_of(first: Mapping[str, float | None], second: Mapping[str, float | None], *,
             floor: float | Mapping[str, float]) -> float | None:  # fmt: skip
    """The noise of one indicator: the largest relative difference between two builds of one
    state, over the items whose results lie beyond the floor in both. `first` and `second`
    are `{item: result}`; `floor` is the floor of the indicator, or `{item: floor}` where
    items of several units have floors of their own (`rule.floors_of`). None where no pair
    lies beyond the floor: nothing was measured.

    A pair within the floor is left out because its relative difference says nothing: a
    residue of 4e-16 in one build and 0 in the other would make the noise 1.0.

    >>> noise_of({"a": 1.0, "b": 2.0, "c": 5.0}, {"a": 1.0, "b": 2.5}, floor=0.0)
    0.2
    >>> noise_of({"a": 1.0, "z": 4e-16}, {"a": 1.0, "z": 0.0}, floor=0.01)
    0.0
    >>> noise_of({"z": 4e-16}, {"z": 0.0}, floor=0.01) is None
    True
    """
    def beyond(item, value):
        level = floor.get(item, 0.0) if isinstance(floor, Mapping) else floor
        return rule.is_value(value) and abs(value) > level

    shared = [k for k in first if beyond(k, first[k]) and beyond(k, second.get(k))]
    if not shared:
        return None
    return max(rule.relative_difference(first[k], second[k]) for k in shared)


def step(id: str, label: str, *, kind: str, explained: bool = True, about: str | None = None,
         link: str | None = None, claim: dict | None = None, tolerance: dict | None = None,
         noise: dict | None = None) -> dict:  # fmt: skip
    """One step between two states, as `build` takes it. Its noise is that of its two states,
    worked out by `build`; a noise given here is refused, since it cannot say which state was
    built twice."""
    if noise is not None:
        raise ValueError(NOISE_ON_A_STEP.format(id=id))
    return {
        "id": id,
        "label": label,
        "about": about,
        "kind": kind,
        "explained": explained,
        "link": link,
        "claim": claim,
        "tolerance": tolerance,
    }


#: Why a step takes no noise of its own.
NOISE_ON_A_STEP = (
    "step {id!r}: noise belongs to the state that was built twice: give it to `chain.state`; "
    "a step is compared with the noise of its two states (SPEC section 5.3)"
)


def state(id: str, label: str, *, kind: str = "build", about: str | None = None,
          identity: Mapping[str, str | None] | None = None, join: Mapping | None = None,
          noise: dict | None = None) -> dict:  # fmt: skip
    """One state: a set of results. `kind` is "published" for the results its publisher released.

    `noise` is what two builds of this state differ by (`chain.noise`); without it the
    state's noise was not measured. A step, a run of steps and the whole way are compared with
    the sum of the noise of the two states they lie between, never with that of a state inside
    them. The published results have no builds: they are exact and take no noise.

    `identity` is a short table of texts (commit, release, machine); an entry whose value is
    None is left out, so that a writer can pass what it may not know.

    `join` is what the reader that made the state counted when it matched its rows to items:
    `{"compared": n, "unmatched": n, "ambiguous": n, "note": text or None}`.

    >>> state("b", "Build", identity={"commit": "0e1f5be", "machine": None})["identity"]
    {'commit': '0e1f5be'}
    """
    if kind == "published" and noise is not None:
        raise ValueError(f"state {id!r}: the published results have no builds and take no noise: they are exact")
    if join is not None:
        join = {"compared": join["compared"], "unmatched": join.get("unmatched", 0),
                "ambiguous": join.get("ambiguous", 0), "note": join.get("note")}  # fmt: skip
    return {"id": id, "label": label, "about": about, "kind": kind,
            "identity": {k: v for k, v in (identity or {}).items() if v is not None}, "join": join,
            "noise": noise}  # fmt: skip


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


def build(title: str, **given) -> dict:
    """A whole chain, counted, judged, attributed and checked: the file, without a matrix.
    The keywords are those of `_build`, whose docstring says what each one holds."""
    return _build(title, **given)[0]


def build_with_matrix(title: str, *, matrix_file: str = "matrix.json", **given) -> tuple[dict, dict]:
    """The file and its full matrix (`sentier_diagnostics.matrix`): every item with its
    results and codes, the worst first, in a second file named `matrix_file` that the file
    names. Only a local file of items has one."""
    data, found = _build(title, matrix_file=matrix_file, **given)
    return data, found


def _build(
    title: str,
    *,
    indicators: Iterable,
    states: list[dict],
    steps: list[dict],
    values: Mapping[str, Mapping[str, Mapping[str, float | None]]],
    units: Mapping[str, str | None] | None = None,
    names: Mapping[str, Mapping] | None = None,
    item_word: tuple[str, str] = ("item", "items"),
    indicator_word: tuple[str, str] | None = None,
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
    matrix_file: str | None = None,
) -> tuple[dict, dict | None]:
    """A whole chain, counted, judged, attributed and checked, and its matrix where
    `matrix_file` names one.

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
    - `matrix_file`: the name of the full matrix, for a local file of items; None for none.
    """
    if matrix_file is not None and (tier != "items" or audience != "local"):
        raise ValueError("only a local file of items has a matrix: a public file keeps the listed items only")
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
    # a claim names items of this chain: an id no state holds is a mistake, not a claim; and
    # it is judged here, so each list is in hand (`claim_lists=False` leaves them out of the file)
    for one in steps:
        for entry in (one.get("claim") or {}).get("scope", ()):
            if entry["items"] is None:
                raise ValueError(
                    f"step {one['id']!r}: an entry of its claim has no list of items in hand, so it would "
                    "cover nothing and a `must` would be met by default; give the list, and build with "
                    "claim_lists=False to keep it out of the file"
                )
            if entry["items"] != "*":
                unknown = set(entry["items"]) - set(items)
                if unknown:
                    shown = ", ".join(sorted(unknown)[:5]) + (", ..." if len(unknown) > 5 else "")
                    raise ValueError(
                        f"step {one['id']!r}: its claim names {len(unknown)} items no state holds ({shown})"
                    )

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

    # the states, normalised: each with its noise, measured or not
    out_states = []
    for s in states:
        out = {"id": s["id"], "label": s["label"], "about": s.get("about"),
               "kind": s.get("kind", "build"), "identity": dict(s.get("identity") or {}), "join": s.get("join")}  # fmt: skip
        if out["kind"] == "published":
            if s.get("noise") is not None:
                raise ValueError(f"state {s['id']!r}: the published results have no builds and take no noise: they are exact")
        else:
            out["noise"] = s.get("noise") or noise()
        out_states.append(out)

    # the steps, normalised
    out_steps = []
    for k, one in enumerate(steps):
        if one.get("noise") is not None:
            raise ValueError(NOISE_ON_A_STEP.format(id=one["id"]))
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
            "noise": fileformat.noise_of_states(out_states[k], out_states[k + 1]),
        })  # fmt: skip
    total_tolerance = max(s["tolerance"]["value"] for s in out_steps)
    total_noise = fileformat.noise_of_states(out_states[0], out_states[-1])["by"] or {}
    published_first = states[0].get("kind") == "published"

    def judged(k, indicator, item):
        """Class, direction, band and verdict of one item in one step (k) or the total (None)."""
        first, last = (order[0], order[-1]) if k is None else (order[k], order[k + 1])
        before, after = table[first][indicator].get(item), table[last][indicator].get(item)
        if k is None:
            level, tol = total_noise.get(indicator), total_tolerance
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
        not_attributable = spread = unexplained_moved = 0
        for item in items:
            kinds = [found[(k, indicator, item)][2] for k in range(len(out_steps))]
            if any(not s["explained"] and kinds[k] in rule.MOVES for k, s in enumerate(out_steps)):
                unexplained_moved += 1
            if found[(None, indicator, item)][2] not in rule.MOVES:
                continue
            series = [table[s][indicator].get(item) for s in order]
            if any(v is None for v in series):
                not_attributable += 1
                continue
            carrier = rule.largest_step(series, kinds)
            if carrier is None:
                spread += 1
            else:
                dominant[out_steps[carrier]["id"]] += 1
        attribution[indicator] = {"dominant": dominant, "not_attributable": not_attributable,
                                  "spread": spread, "unexplained_moved": unexplained_moved}  # fmt: skip

    # the items worth a look, the worst first
    def worth(item):
        for indicator in ids:
            for k in [*range(len(out_steps)), None]:
                _, _, kind, _, _, said = found[(k, indicator, item)]
                if kind not in rule.QUIET or said in claims.TO_LOOK_AT:
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

    def record_of(item):
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
        return record

    out_items = [record_of(item) for item in shown]

    data = {
        "format": fileformat.FORMAT,
        "tier": tier,
        "audience": audience,
        "title": title,
        "about": about,
        "item": {"one": item_word[0], "many": item_word[1]},
        **({"indicator": {"one": indicator_word[0], "many": indicator_word[1]}} if indicator_word else {}),
        "indicators": meta,
        "rule": {
            "floor_factor": floor_factor,
            "floors_from": order[0],
            "beyond": rule.BEYOND_FACTOR,
            "total_tolerance": total_tolerance,
            "total_noise": total_noise,
            "floors": floor_rows,
        },
        "states": out_states,
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
    if matrix_file is not None:
        data["matrix"] = {"file": matrix_file, "items": len(items)}
    errors = fileformat.errors(data)
    if errors:
        raise ValueError("not a diagnostics file: " + "; ".join(errors[:10]))
    if matrix_file is None:
        return data, None
    full = matrix.make(data, [record_of(item) for item in sorted(items, key=worst)])
    errors = matrix.errors(full) or matrix.against(full, data)
    if errors:
        raise ValueError("not a matrix of this file: " + "; ".join(errors[:10]))
    return data, full


#: Stands in for the list of items while the rest of a file is written. A file's texts hold
#: no control character, so no text can be written as this.
_ITEMS_HERE = "\x00items\x00"


def dumps(data: Mapping) -> str:
    """The text of a file: one line per listed item, so that a diff names the items. The keys
    keep their order, whatever it is.

    >>> dumps({"items": [{"id": "p"}], "steps": [{"items": []}]}).splitlines()[:3]
    ['{', ' "items": [', '  {"id": "p"}']
    """
    listed = data.get("items") or []
    head = json.dumps(dict(data) | {"items": _ITEMS_HERE}, indent=1, ensure_ascii=False, allow_nan=False)
    marker = json.dumps(_ITEMS_HERE)
    if head.count(marker) != 1:
        raise ValueError("a file holds the list of items once, at its top level")
    rows = ",\n".join("  " + json.dumps(i, ensure_ascii=False, allow_nan=False) for i in listed)
    head = head.replace(marker, f"[\n{rows}\n ]" if listed else "[]")
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
    data = fileformat.load_json(path)
    errors = fileformat.errors(data)
    if errors:
        raise ValueError(f"{path}: " + "; ".join(errors[:10]))
    return data
