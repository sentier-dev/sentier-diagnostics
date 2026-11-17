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

**Ranges.** A run of consecutive steps, such as three fixes built one after another, is
compared too where the producer asks for it (`ranges`): the state before its first step
against the state after its last, judged as the whole way is (the largest tolerance of its
steps, no noise, no verdict). A page then shows any run of steps as one comparison of two
built states: what those steps did together, never a sum of steps it cannot see.

`build` writes the whole file and checks it (`fileformat.errors`); `write` stores it.
"""

from __future__ import annotations

import json
import warnings
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
    An indicator whose noise is None (`noise_of` found no pair to take it from) is left out:
    its noise was not measured, which is not the same as two identical builds."""
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
          identity: Mapping[str, str | None] | None = None, join: Mapping | None = None) -> dict:  # fmt: skip
    """One state: a set of results. `kind` is "published" for the results its publisher released.

    `identity` is a short table of texts (commit, release, machine); an entry whose value is
    None is left out, so that a writer can pass what it may not know.

    `join` is what the reader that made the state counted when it matched its rows to items:
    `{"compared": n, "unmatched": n, "ambiguous": n, "note": text or None}`.

    >>> state("b", "Build", identity={"commit": "0e1f5be", "machine": None})["identity"]
    {'commit': '0e1f5be'}
    """
    if join is not None:
        join = {"compared": join["compared"], "unmatched": join.get("unmatched", 0),
                "ambiguous": join.get("ambiguous", 0), "note": join.get("note")}  # fmt: skip
    return {"id": id, "label": label, "about": about, "kind": kind,
            "identity": {k: v for k, v in (identity or {}).items() if v is not None}, "join": join}  # fmt: skip


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


#: Without a choice, a chain of at most this many steps has every range, and a longer one none:
#: the ranges of n steps are n(n-1)/2 - 1, each a comparison of every item in every indicator.
AUTO_RANGES = 8


def ranges_within(steps: list[dict], first: str, last: str) -> list[tuple[str, str]]:
    """Every run of at least two consecutive steps from `first` to `last`, as `(first, last)`
    pairs: what `ranges` takes for the steps of one kind, such as the fixes of a build.

    >>> ranges_within([{"id": i} for i in "abcd"], "b", "d")
    [('b', 'c'), ('b', 'd'), ('c', 'd')]
    """
    ids = [s["id"] for s in steps]
    for one in (first, last):
        if one not in ids:
            raise ValueError(f"ranges within {first!r} and {last!r}: no step {one!r}")
    i, j = ids.index(first), ids.index(last)
    if j <= i:
        raise ValueError(f"ranges within {first!r} and {last!r}: the first step comes after the last")
    return [(ids[a], ids[b]) for a in range(i, j + 1) for b in range(a + 1, j + 1)]


def _ranges(said, out_steps: list[dict]) -> list[dict]:
    """The ranges of a chain, as the file holds them, from what the producer asked for:
    "auto", "all", None, or `(first step id, last step id)` pairs."""
    ids = [s["id"] for s in out_steps]
    n = len(ids)
    if said == "auto":
        said = "all" if n <= AUTO_RANGES else None
        if said is None:
            # a chain that grows past the limit loses its ranges: never without a word
            warnings.warn(
                f"a chain of {n} steps has no ranges unless asked (more than {AUTO_RANGES} steps): "
                "pass ranges=\"all\", chain.ranges_within(steps, first, last) or (first, last) pairs, "
                "or ranges=None to say that none is wanted",
                stacklevel=4,
            )
    if said is None:
        return []
    if said == "all":
        pairs = [(a, b) for a in range(n) for b in range(a + 1, n) if (a, b) != (0, n - 1)]
    elif isinstance(said, str):
        raise ValueError(f"`ranges` is \"auto\", \"all\", None or a list of (first, last) step ids, not {said!r}")
    else:
        pairs = []
        for one in said:
            if not (isinstance(one, (list, tuple)) and len(one) == 2 and all(x in ids for x in one)):
                raise ValueError(f"a range is (first step id, last step id) of this chain, not {one!r}")
            a, b = ids.index(one[0]), ids.index(one[1])
            if b <= a:
                raise ValueError(f"range {one[0]}..{one[1]}: a range runs over at least two steps, the first first")
            if (a, b) == (0, n - 1):
                raise ValueError(f"range {one[0]}..{one[1]}: every step is the whole way, counted as the total")
            if (a, b) in pairs:
                raise ValueError(f"range {one[0]}..{one[1]} is asked for twice")
            pairs.append((a, b))
    return [
        {
            "id": f"{ids[a]}..{ids[b]}",
            "steps": ids[a : b + 1],
            "from": out_steps[a]["from"],
            "to": out_steps[b]["to"],
            "tolerance": max(s["tolerance"]["value"] for s in out_steps[a : b + 1]),
        }
        for a, b in pairs
    ]


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
    ranges="auto",
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
    - `ranges`: the runs of consecutive steps compared as one: "all" (every run of at least
      two steps but the whole way), a list of `(first step id, last step id)` pairs
      (`ranges_within` gives every run between two steps), None for none, or "auto" (the
      default): every run where the chain has at most `AUTO_RANGES` steps, else none.
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
    # a claim names items of this chain: an id no state holds is a mistake, not a claim
    for one in steps:
        for entry in (one.get("claim") or {}).get("scope", ()):
            if entry["items"] not in ("*", None):
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
    out_ranges = _ranges(ranges, out_steps)
    nsteps = len(out_steps)

    # every comparison, in the order an item lists them: each step, the whole way, each range;
    # as (first state, last state, tolerance, noise by indicator or None, claim or None)
    compared = []
    for k, one in enumerate(out_steps):
        said = one["noise"]
        by = (said["by"] or {}) if said["measured"] else None
        compared.append((order[k], order[k + 1], one["tolerance"]["value"], by, steps[k].get("claim")))
    compared.append((order[0], order[-1], total_tolerance, None, None))
    compared += [(r["from"], r["to"], r["tolerance"], None, None) for r in out_ranges]
    seen = {}  # a judgment is one of a few dozen: every pair refers to one of them

    def judged(c, indicator, item):
        """Class, direction, band and verdict of one item in one comparison."""
        first, last, tol, by, said_claim = compared[c]
        before, after = table[first][indicator].get(item), table[last][indicator].get(item)
        level = by.get(indicator) if by is not None else None
        floor = floor_table[(indicator, units[item])]
        kind, way, where = rule.judge(before, after, floor=floor, tolerance=tol, noise=level)
        said_verdict = None
        if said_claim:
            covering = [e for e in claims.entries_for(said_claim, indicator) if claims.covers(e, item, indicator)]
            said_verdict = claims.verdict(kind, before, after, way, covering)
        key = (kind, way, where, said_verdict)
        return seen.setdefault(key, key)

    # every pair, once: `found[(comparison, indicator)][n]` is the judgment of `items[n]`
    found = {(c, i): [judged(c, i, item) for item in items] for c in range(len(compared)) for i in ids}

    def ends(c, indicator, item):
        return table[compared[c][0]][indicator].get(item), table[compared[c][1]][indicator].get(item)

    def block(c, indicator):
        classes = dict.fromkeys(rule.CLASSES, 0)
        missing = dict.fromkeys(fileformat.MISSING_SIDES, 0)
        bands = dict.fromkeys(rule.BANDS, 0)
        ways = dict.fromkeys(rule.DIRECTIONS, 0)
        verdicts = dict.fromkeys(claims.VERDICTS, 0) if compared[c][4] else None
        closer = further = None
        if published_first and 0 < c < nsteps:
            closer = further = 0
        for n, item in enumerate(items):
            kind, way, where, said = found[(c, indicator)][n]
            before, after = ends(c, indicator, item)
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
        "total": {i: block(nsteps, i) for i in ids},
    }
    counts["ranges"] = {r["id"]: {i: block(nsteps + 1 + j, i) for i in ids} for j, r in enumerate(out_ranges)}

    # attribution: which step carries the largest share of each item's whole difference
    attribution = {}
    for indicator in ids:
        dominant = {s["id"]: 0 for s in out_steps}
        not_attributable = spread = unexplained_moved = 0
        for n, item in enumerate(items):
            kinds = [found[(k, indicator)][n][0] for k in range(nsteps)]
            if any(not s["explained"] and kinds[k] in rule.MOVES for k, s in enumerate(out_steps)):
                unexplained_moved += 1
            if found[(nsteps, indicator)][n][0] not in rule.MOVES:
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

    # the items worth a look, the worst first; a range counts as a step does
    at = {item: n for n, item in enumerate(items)}

    def worth(item):
        n = at[item]
        return any(
            found[(c, i)][n][0] not in rule.QUIET or found[(c, i)][n][3] == claims.NOT_MOVED
            for i in ids
            for c in range(len(compared))
        )

    ranks = {}

    def worst(item):
        if item not in ranks:
            n = at[item]
            ranks[item] = (
                min(rule.severity(*ends(c, i, item), found[(c, i)][n][0]) for i in ids for c in range(len(compared))),
                item,
            )
        return ranks[item]

    qualifying = sorted((item for item in items if worth(item)), key=worst)
    shown = qualifying[: max(0, listed)] if tier == "items" else []
    breakdowns = breakdowns or {}
    any_claim = any(s.get("claim") for s in steps)

    def record_of(item):
        n = at[item]
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
            row = [found[(c, indicator)][n] for c in range(len(compared))]
            record["classes"][indicator] = [r[0] for r in row]
            record["directions"][indicator] = [r[1] for r in row]
            record["bands"][indicator] = [r[2] for r in row]
            if any_claim:
                record["verdicts"][indicator] = [r[3] for r in row[:nsteps]]
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
            "floors": floor_rows,
        },
        "states": [
            {"id": s["id"], "label": s["label"], "about": s.get("about"),
             "kind": s.get("kind", "build"), "identity": dict(s.get("identity") or {}),
             "join": s.get("join")}
            for s in states
        ],  # fmt: skip
        "steps": out_steps,
        # [] where none was asked for: only a file made before ranges leaves the key out
        "ranges": out_ranges,
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
