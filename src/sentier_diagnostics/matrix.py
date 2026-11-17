"""The full matrix of a local file, `sentier-diagnostics-matrix/1`: every item, not only the
listed ones.

A diagnostics file lists the items worth a look, the worst first, up to `listed` (200 by
default), so that it stays small enough for a page to hold. A project looking at its own
build wants every item: the matrix is that, in a second file the page loads after it has
drawn. It is compact (one row per item, the indicators and states named once) and it holds
only what the rule gives: the results, and one code per pair for its class and direction,
and per step with a claim one code for its verdict. A result equal to the one of the state
before it, in the same indicator, is written `"="`: most steps of a chain of fixes leave most
results as they were, and a chain of 16 states would otherwise hold every number 16 times.

Only a local file may name a matrix (`"matrix": {"file": ..., "items": n}`); a public file
keeps the listed items only. `errors(m)` checks the shape; `against(m, data)` works every
code out again from the results and the diagnostics file's own rule, and holds the file's
counts, attribution and `items_count` to what the matrix holds: with every item at hand,
they must match exactly.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from . import claims, fileformat, rule

FORMAT = "sentier-diagnostics-matrix/1"
FAMILY = "sentier-diagnostics-matrix/"
KEYS = {"format", "of", "items", "values", "classes", "verdicts"}
OF_KEYS = {"title", "states", "indicators", "steps"}

#: A result written as the same number as the state before it, in the same indicator.
SAME = "="

#: A matrix is loaded after the page is drawn, not held inside it: it may be larger.
MAX_BYTES = 64 * 1024 * 1024
MAX_ITEMS = 200_000

#: One character per pair: its class, and for a pair that moved its direction (upper case
#: up, lower case down).
CODES = {
    (rule.AGREES, None): "=",
    (rule.WITHIN_NOISE, None): "~",
    (rule.NEAR_ZERO, None): "0",
    (rule.MISSING, None): "-",
    (rule.DIFFERS, rule.UP): "D",
    (rule.DIFFERS, rule.DOWN): "d",
    (rule.BEYOND, rule.UP): "B",
    (rule.BEYOND, rule.DOWN): "b",
    (rule.ZERO_REFERENCE, rule.UP): "R",
    (rule.ZERO_REFERENCE, rule.DOWN): "r",
    (rule.ZERO_RESULT, rule.UP): "T",
    (rule.ZERO_RESULT, rule.DOWN): "t",
    (rule.SIGN_CHANGE, rule.UP): "S",
    (rule.SIGN_CHANGE, rule.DOWN): "s",
}
DECODE = {code: pair for pair, code in CODES.items()}

#: One character per pair and step with a claim: its verdict. "." for a step without one.
VERDICT_CODES = {
    claims.AS_CLAIMED: "a",
    claims.OFF_CLAIM: "o",
    claims.NOT_CLAIMED: "n",
    claims.NOT_MOVED: "c",
    claims.NOISE: "~",
    claims.UNCHANGED: "=",
    claims.NOT_JUDGED: "?",
}
NO_CLAIM = "."
VERDICT_DECODE = {code: verdict for verdict, code in VERDICT_CODES.items()}


def code_of(kind: str, way: str | None) -> str:
    """The code of a class and direction.

    >>> code_of("differs", "up"), code_of("agrees", None), code_of("sign change", "down")
    ('D', '=', 's')
    """
    return CODES[(kind, way)]


def _same(a, b) -> bool:
    """Two results that are the same number, bit for bit (0.0 and -0.0 are not)."""
    return a is not None and b is not None and float(a).hex() == float(b).hex()


def compact(values: list) -> list:
    """One indicator's results over the states, each equal to the one before it as `SAME`.

    >>> compact([1.5, 1.5, None, None, 2.0, 2.0, -0.0, 0.0])
    [1.5, '=', None, None, 2.0, '=', -0.0, 0.0]
    """
    return [SAME if n and _same(v, values[n - 1]) else v for n, v in enumerate(values)]


def expand(values: list, nstates: int) -> list:
    """The results of one item, every `SAME` written out again; raises ValueError where one
    stands first in its indicator or after a missing result.

    >>> expand([1.5, "=", None, 2.0], 2)
    [1.5, 1.5, None, 2.0]
    """
    out = []
    for n, v in enumerate(values):
        if v == SAME:
            if n % nstates == 0 or out[-1] is None:
                raise ValueError("`=` stands first in an indicator, or after a missing result")
            v = out[-1]
        out.append(v)
    return out


def make(data: Mapping, rows: list[dict]) -> dict:
    """A matrix of a diagnostics file from its rows, as `chain.build_with_matrix` gives them:
    `{id, name, place, group, unit, values: {indicator: [per state]}, classes, directions,
    verdicts}` with classes, directions and verdicts per indicator as the file lists them."""
    ids = [i["id"] for i in data["indicators"]]
    steps = data["steps"]
    out = {
        "format": FORMAT,
        "of": {
            "title": data["title"],
            "states": [s["id"] for s in data["states"]],
            "indicators": ids,
            "steps": [s["id"] for s in steps],
        },
        "items": [],
        "values": [],
        "classes": [],
        "verdicts": [] if any(s["claim"] for s in steps) else None,
    }
    for row in rows:
        out["items"].append([row["id"], row["name"], row["place"], row["group"], row["unit"]])
        out["values"].append([v for i in ids for v in compact(row["values"][i])])
        out["classes"].append(
            "".join(
                code_of(kind, way) for i in ids for kind, way in zip(row["classes"][i], row["directions"][i])
            )
        )
        if out["verdicts"] is not None:
            out["verdicts"].append(
                "".join(
                    NO_CLAIM if said is None else VERDICT_CODES[said]
                    for i in ids
                    for said in row["verdicts"][i]
                )
            )
    return out


def dumps(m: Mapping) -> str:
    """The text of a matrix: one line per item, so that a diff names the items."""
    head = {k: v for k, v in m.items() if k not in ("items", "values", "classes", "verdicts")}
    lines = [json.dumps(head, ensure_ascii=False, allow_nan=False)[:-1] + ","]
    for key in ("items", "values", "classes", "verdicts"):
        rows = m[key]
        if rows is None:
            lines.append(f' "{key}": null' + ("," if key != "verdicts" else ""))
            continue
        body = ",\n".join(
            "  " + json.dumps(r, ensure_ascii=False, allow_nan=False, separators=(",", ":")) for r in rows
        )
        lines.append(f' "{key}": [\n{body}\n ]' + ("," if key != "verdicts" else ""))
    return "\n".join(lines) + "\n}\n"


def write(m: Mapping, path) -> Path:
    """Write a matrix, its shape checked first; refuse one larger than a page loads."""
    found = errors(m)
    if found:
        raise ValueError("not a matrix: " + "; ".join(found[:10]))
    text = dumps(m)
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        raise ValueError(f"the matrix would be {size} bytes, and a page loads {MAX_BYTES} at most")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read(path, data: Mapping) -> dict:
    """A matrix, read and checked against its checked diagnostics file; raises ValueError
    with every error found."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"{path}: larger than {MAX_BYTES} bytes")
    m = fileformat.load_json(path)
    found = errors(m) or against(m, data)
    if found:
        raise ValueError(f"{path}: " + "; ".join(found[:10]))
    return m


def _is_row(row) -> bool:
    return (
        isinstance(row, list)
        and len(row) == 5
        and fileformat.is_text(row[0], fileformat.MAX_ID)
        and fileformat.is_text(row[1], 300)
        and fileformat.is_optional(row[2], 60)
        and fileformat.is_optional(row[3], fileformat.MAX_LABEL)
        and fileformat.is_optional(row[4], fileformat.MAX_WORD)
    )


def errors(m) -> list[str]:
    """Everything wrong with the shape of a matrix; nothing for one a page can load. It never
    raises: a value it cannot read is a fault like any other."""
    try:
        return _errors(m)
    except Exception:  # noqa: BLE001 - a backstop: the checks above it name the faults they know
        return [fileformat.STOPPED]


def _errors(m) -> list[str]:
    if not isinstance(m, Mapping):
        return ["not a matrix: not an object"]
    said = m.get("format")
    if said != FORMAT:
        if isinstance(said, str) and said.startswith(FAMILY):
            return [f"format {said!r}: this reader knows {FORMAT} only"]
        return [f"not a matrix of format {FORMAT}"]
    found = [f"a key this format does not know: {k}" for k in sorted(set(m) - KEYS)]
    found += [f"a key this format requires: {k}" for k in sorted(KEYS - set(m))]
    if found:
        return found
    of = m["of"]
    if not (
        isinstance(of, dict)
        and set(of) == OF_KEYS
        and fileformat.is_text(of["title"], 120)
        and all(isinstance(of[k], list) and all(fileformat.is_text(x, fileformat.MAX_ID) for x in of[k])
                for k in ("states", "indicators", "steps"))
    ):  # fmt: skip
        return ["`of` is not {title, states, indicators, steps}"]
    nstates, nind, nsteps = len(of["states"]), len(of["indicators"]), len(of["steps"])
    if nsteps != nstates - 1 or not nind:
        return ["`of`: one step fewer than states, and at least one indicator"]
    items = m["items"]
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        return [f"`items` is not a list of at most {MAX_ITEMS} items"]
    n = len(items)
    for key in ("values", "classes"):
        if not isinstance(m[key], list) or len(m[key]) != n:
            found.append(f"`{key}` is not one row per item")
    has_claims = m["verdicts"] is not None
    if has_claims and (not isinstance(m["verdicts"], list) or len(m["verdicts"]) != n):
        found.append("`verdicts` is not one row per item, or null")
    if found:
        return found
    seen = set()
    for at, row in enumerate(items):
        if not _is_row(row):
            return [f"item {at}: not [id, name, place, group, unit]"]
        if row[0] in seen:
            found.append(f"item {row[0]!r} is in the matrix twice")
        seen.add(row[0])
        values = m["values"][at]
        if not (isinstance(values, list) and len(values) == nind * nstates
                and all(v is None or v == SAME or rule.is_value(v) for v in values)):  # fmt: skip
            return [f"item {row[0]!r}: not one finite number, `=` or null per indicator and state"]
        try:
            expand(values, nstates)
        except ValueError as error:
            return [f"item {row[0]!r}: {error}"]
        codes = m["classes"][at]
        if not (
            isinstance(codes, str) and len(codes) == nind * (nsteps + 1) and all(c in DECODE for c in codes)
        ):
            return [f"item {row[0]!r}: not one class code per indicator, step and the whole way"]
        if has_claims:
            said = m["verdicts"][at]
            if not (isinstance(said, str) and len(said) == nind * nsteps
                    and all(c in VERDICT_DECODE or c == NO_CLAIM for c in said)):  # fmt: skip
                return [f"item {row[0]!r}: not one verdict code per indicator and step"]
    return found


def against(m: Mapping, data: Mapping) -> list[str]:
    """Everything a checked matrix and its checked diagnostics file disagree on. Every code
    is worked out again with the file's floors, tolerances and noise, and, where a claim's
    lists are in the file, every verdict; the file's counts, attribution and `items_count`
    must be what the matrix holds, exactly."""
    try:
        return _against(m, data)
    except Exception:  # noqa: BLE001 - a backstop, as in `errors`
        return [fileformat.STOPPED]


def _against(m: Mapping, data: Mapping) -> list[str]:
    found = []
    named = data.get("matrix")
    if not named:
        return ["the diagnostics file names no matrix"]
    ids = [i["id"] for i in data["indicators"]]
    order = [s["id"] for s in data["states"]]
    steps = data["steps"]
    of = {"title": data["title"], "states": order, "indicators": ids, "steps": [s["id"] for s in steps]}
    if m["of"] != of:
        return ["it is the matrix of another file: its title, states, indicators or steps differ"]
    n = len(m["items"])
    if named["items"] != n:
        found.append(f"the diagnostics file says {named['items']} items, the matrix holds {n}")
    if data["items_count"]["all"] != n:
        found.append(f"the diagnostics file counts {data['items_count']['all']} items, the matrix holds {n}")
    nstates, nsteps = len(order), len(steps)
    floors = {(f["indicator"], f["unit"]): f["value"] for f in data["rule"]["floors"]}
    published_first = data["states"][0]["kind"] == "published"
    listed = {item["id"]: item for item in data["items"]}

    # what the counts and attribution must be, counted from every item
    def empty(k):
        return {
            "pairs": 0,
            "classes": dict.fromkeys(rule.CLASSES, 0),
            "missing": dict.fromkeys(fileformat.MISSING_SIDES, 0),
            "directions": dict.fromkeys(rule.DIRECTIONS, 0),
            "bands": dict.fromkeys(rule.BANDS, 0),
            "verdicts": dict.fromkeys(claims.VERDICTS, 0) if k is not None and steps[k]["claim"] else None,
            "closer": 0 if published_first and k not in (None, 0) else None,
            "further": 0 if published_first and k not in (None, 0) else None,
        }

    counted = {(k, i): empty(k) for k in [*range(nsteps), None] for i in ids}
    attributed = {
        i: {
            "dominant": {s["id"]: 0 for s in steps},
            "not_attributable": 0,
            "spread": 0,
            "unexplained_moved": 0,
        }
        for i in ids
    }
    qualifying = 0
    for at, (item_id, name, place, group, unit) in enumerate(m["items"]):
        where = f"item {item_id!r}"
        flat, codes = expand(m["values"][at], nstates), m["classes"][at]
        said_verdicts = m["verdicts"][at] if m["verdicts"] is not None else None
        worth = False
        values_of = {}
        for x, indicator in enumerate(ids):
            values = flat[x * nstates : (x + 1) * nstates]
            values_of[indicator] = values
            floor = floors.get((indicator, unit))
            if floor is None:
                return [f"{where}, {indicator}: the file holds no floor for unit {unit!r}"]
            kinds = []
            for k in [*range(nsteps), None]:
                at_k = nsteps if k is None else k
                before, after = (values[0], values[-1]) if k is None else (values[k], values[k + 1])
                if k is None:
                    tol, level = data["rule"]["total_tolerance"], fileformat.total_noise_level(data, indicator)
                else:
                    tol = steps[k]["tolerance"]["value"]
                    noise = steps[k]["noise"]
                    level = (noise["by"] or {}).get(indicator) if noise["measured"] else None
                kind, way, band = rule.judge(before, after, floor=floor, tolerance=tol, noise=level)
                code = codes[x * (nsteps + 1) + at_k]
                if code != code_of(kind, way):
                    step_name = "the whole way" if k is None else steps[k]["id"]
                    return [
                        f"{where}, {indicator}, {step_name}: written as {DECODE[code]}, the rule gives {kind}/{way}"
                    ]
                kinds.append(kind)
                block = counted[(k, indicator)]
                block["pairs"] += 1
                block["classes"][kind] += 1
                if kind == rule.MISSING:
                    side = (
                        "both"
                        if before is None and after is None
                        else "before"
                        if before is None
                        else "after"
                    )
                    block["missing"][side] += 1
                if way:
                    block["directions"][way] += 1
                if band:
                    block["bands"][band] += 1
                if block["closer"] is not None and kind in rule.MOVES and values[0] is not None:
                    was, now = abs(before - values[0]), abs(after - values[0])
                    block["closer"] += now < was
                    block["further"] += now > was
                worth = worth or kind not in rule.QUIET
                if k is None:
                    continue
                step_claim = steps[k]["claim"]
                vcode = said_verdicts[x * nsteps + k] if said_verdicts is not None else NO_CLAIM
                if step_claim is None:
                    if vcode != NO_CLAIM:
                        return [f"{where}, {indicator}, {steps[k]['id']}: a verdict without a claim"]
                    continue
                said = VERDICT_DECODE.get(vcode)
                if said is None or said not in fileformat.ALLOWED_VERDICTS[kind]:
                    return [f"{where}, {indicator}, {steps[k]['id']}: {kind!r} cannot be {said!r}"]
                if claims.judgeable(step_claim):
                    covering = [
                        e
                        for e in claims.entries_for(step_claim, indicator)
                        if claims.covers(e, item_id, indicator)
                    ]
                    again = claims.verdict(kind, before, after, way, covering)
                    if again != said:
                        return [
                            f"{where}, {indicator}, {steps[k]['id']}: written {said!r}, the claim gives {again!r}"
                        ]
                block["verdicts"][said] += 1
                worth = worth or said == claims.NOT_MOVED
            # attribution, as `chain.build` makes it
            one = attributed[indicator]
            if any(not s["explained"] and kinds[j] in rule.MOVES for j, s in enumerate(steps)):
                one["unexplained_moved"] += 1
            if kinds[nsteps] in rule.MOVES:
                if any(v is None for v in values):
                    one["not_attributable"] += 1
                else:
                    carrier = rule.largest_step(values, kinds[:nsteps])
                    if carrier is None:
                        one["spread"] += 1
                    else:
                        one["dominant"][steps[carrier]["id"]] += 1
        qualifying += worth
        if item_id in listed:
            item = listed[item_id]
            if [item["name"], item["place"], item["group"], item["unit"]] != [name, place, group, unit]:
                found.append(f"{where}: its name, place, group or unit differ from the diagnostics file")
            if item["values"] != values_of:
                found.append(f"{where}: its results differ from the diagnostics file")
    missing_listed = set(listed) - {row[0] for row in m["items"]}
    if missing_listed:
        found.append(f"{len(missing_listed)} listed items are not in the matrix")
    if data["items_count"]["qualifying"] != qualifying:
        found.append(
            f"the diagnostics file counts {data['items_count']['qualifying']} items worth a look, "
            f"the matrix holds {qualifying}"
        )
    for (k, indicator), block in counted.items():
        name = fileformat.TOTAL if k is None else steps[k]["id"]
        written = (
            data["counts"][fileformat.TOTAL][indicator]
            if k is None
            else data["counts"]["steps"][name][indicator]
        )
        for key in block:
            if block[key] != written[key]:
                found.append(f"counts of {name!r} in {indicator!r}: `{key}` is not what the matrix holds")
    for indicator in ids:
        if attributed[indicator] != data["attribution"][indicator]:
            found.append(f"attribution in {indicator!r} is not what the matrix holds")
    return found
