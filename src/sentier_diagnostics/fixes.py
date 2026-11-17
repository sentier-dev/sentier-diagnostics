"""Fixes against one base, `sentier-diagnostics-fixes/1` (SPEC 16).

A chain measures each step with every earlier step applied, so a step's difference belongs
to its place in the order. A fixes file measures each fix on its own against one state of
a chain, the base: a fix has one effect, whichever set it joins and in whatever order. A
reader may then choose any set of fixes; its result is the base plus the sum of their
effects, labelled:

    built       one fix, or a set the producer built (`built`)
    exact       interactions were checked, and no two of its fixes are a listed pair
    estimated   otherwise: drawn, and marked on every cell and count

A set has no verdict: each claim is judged in its own fix, against the base. A set's
tolerance is the largest of its fixes'; its noise is the sum of their noise, with the
number of fixes whose noise was measured, never read as none.

`errors(f)` checks a file on its own: its shape, every fix's counts and verdicts worked out
again from its effect and the base, the pairs of fixes that can interact, and every built
set where the file calls its fixes independent: the built results must agree with the sum.
`against(f, data, full)` holds it to its diagnostics file and that file's matrix;
`beside(f, folder)` finds them next to it, as `sentier-diagnostics check` does.

`build(...)` makes a file from a checked diagnostics file, its matrix and the results built
with each fix; `label`, `compose` and `counts` give what a page draws for a chosen set.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from . import __version__, chain, claims, fileformat, matrix, rule

FORMAT = "sentier-diagnostics-fixes/1"
FAMILY = "sentier-diagnostics-fixes/"
KEYS = {
    "format", "of", "title", "about", "item", "indicators", "rule", "items", "base", "fixes",
    "interactions", "built", "notes", "made_by",
}  # fmt: skip
#: A key a file may leave out, as in the diagnostics file.
OPTIONAL_KEYS = {"indicator"}
OF_KEYS = {"file", "title", "base"}
#: The rule of the diagnostics file, without the chain's own total tolerance.
RULE_KEYS = fileformat.RULE_KEYS - {"total_tolerance"}
FIX_KEYS = {"id", "label", "about", "kind", "explained", "link", "claim", "tolerance", "noise", "effect",
            "counts"}  # fmt: skip
INTERACTION_KEYS = {"checked", "method", "by", "pairs"}
PAIR_KEYS = {"fixes", "reason", "largest"}
BUILT_KEYS = {"id", "label", "fixes", "results", "noise"}

MAX_FIXES, MAX_BUILT = 1000, 500
MAX_ITEMS, MAX_BYTES = matrix.MAX_ITEMS, matrix.MAX_BYTES

BUILT, EXACT, ESTIMATED = "built", "exact", "estimated"
LABELS = (BUILT, EXACT, ESTIMATED)

#: The shape of an identifier of a model (a UUID, or 32 hexadecimal digits). The reasons of
#: interactions say what two fixes share in words, never by the model's identifiers (SPEC 16.6).
IDENTIFIER = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b|\b[0-9a-fA-F]{32}\b"
)


# ------------------------------------------------------------------------ making a file


def fix(id: str, label: str, *, kind: str, explained: bool = True, about: str | None = None,
        link: str | None = None, claim: dict | None = None, tolerance: dict | None = None,
        noise: dict | None = None) -> dict:  # fmt: skip
    """One fix, as `build` takes it: what a step has (`chain.step`), measured against the base."""
    return chain.step(id, label, kind=kind, explained=explained, about=about, link=link, claim=claim,
                      tolerance=tolerance, noise=noise)  # fmt: skip


def interactions(checked: bool = False, *, method: str | None = None, by: dict | None = None,
                 pairs: Iterable[tuple] = ()) -> dict:  # fmt: skip
    """The check of pairs: `checked` true where every pair was examined, false where none was.
    `pairs` are `(fix, fix, reason)` or `(fix, fix, reason, largest)`, every pair that can
    interact, each once; `largest` is the measured size of its cross term, None where it was
    not measured."""
    out = []
    for a, b, reason, *largest in pairs:
        out.append({"fixes": [a, b], "reason": reason, "largest": largest[0] if largest else None})
    return {"checked": checked, "method": method, "by": by, "pairs": out}


def built_set(id: str, label: str, fixes: Iterable[str], results: Mapping, noise: dict | None = None) -> dict:
    """A set the producer built: `results` are `{indicator: {item: result or None}}`, an item
    left out being the base result."""
    return {"id": id, "label": label, "fixes": list(fixes), "results": results, "noise": noise or chain.noise()}


def build(
    title: str,
    *,
    data: Mapping,
    full: Mapping,
    base: str,
    fixes: list[dict],
    results: Mapping[str, Mapping],
    interactions: dict | None = None,
    built: Iterable[dict] = (),
    file: str = chain.FILE,
    about: str | None = None,
    notes: Iterable[str] = (),
) -> dict:
    """A fixes file, counted and checked.

    - `data` and `full`: the checked diagnostics file and its matrix; the items and the base
      results come from the matrix, in its order.
    - `base`: the id of the state every fix was measured against.
    - `fixes`: `fix(...)`, in the order the page lists them.
    - `results`: `{fix id: {indicator: {item: result or None}}}`, built with that fix alone.
      An item left out is the base result; one written equal to it is left out too.
    - `interactions`: `interactions(...)`; not checked where it is None.
    - `built`: `built_set(...)`.
    - `file`: the name of the diagnostics file beside it.
    """
    ids = [i["id"] for i in data["indicators"]]
    states = [s["id"] for s in data["states"]]
    if base not in states:
        raise ValueError(f"the base {base!r} is no state of {data['title']!r}")
    at, nstates = states.index(base), len(states)
    rows = [list(r) for r in full["items"]]
    index = {r[0]: k for k, r in enumerate(rows)}
    base_values = {ind: [v[x * nstates + at] for v in full["values"]] for x, ind in enumerate(ids)}

    def sparse(given: Mapping, where: str) -> dict:
        unknown = set(given) - set(ids)
        if unknown:
            raise ValueError(f"{where}: results of an indicator the file does not hold: {sorted(unknown)}")
        out = {}
        for ind in ids:
            entries = []
            for item, value in (given.get(ind) or {}).items():
                if item not in index:
                    raise ValueError(f"{where}: {item!r} is no item of the base")
                if value is not None and not rule.is_value(value):
                    raise ValueError(f"{where}, {ind}, {item}: {value!r} is not a finite number or None")
                value = None if value is None else float(value)
                if value != base_values[ind][index[item]]:
                    entries.append([index[item], value])
            out[ind] = sorted(entries)
        return out

    known = {one["id"] for one in fixes}
    unknown = set(results) - known
    if unknown:
        raise ValueError(f"results of fixes that are not given: {sorted(unknown)}")
    f = {
        "format": FORMAT,
        "of": {"file": file, "title": data["title"], "base": base},
        "title": title,
        "about": about,
        "item": dict(data["item"]),
        **({"indicator": dict(data["indicator"])} if data.get("indicator") else {}),
        "indicators": [dict(i) for i in data["indicators"]],
        "rule": {k: data["rule"][k] for k in sorted(RULE_KEYS)},
        "items": rows,
        "base": base_values,
        "fixes": [],
        "interactions": interactions or globals()["interactions"](),
        "built": [],
        "notes": list(notes),
        "made_by": f"sentier-diagnostics {__version__}",
    }
    for one in fixes:
        found_claim = one.get("claim")
        f["fixes"].append({
            "id": one["id"],
            "label": one["label"],
            "about": one.get("about"),
            "kind": one["kind"],
            "explained": bool(one.get("explained", True)),
            "link": one.get("link"),
            "claim": claims.published(found_claim, True) if found_claim else None,
            "tolerance": one.get("tolerance") or chain.tolerance(),
            "noise": one.get("noise") or chain.noise(),
            "effect": sparse(results.get(one["id"]) or {}, f"fix {one['id']!r}"),
            "counts": None,
        })  # fmt: skip
    for one in built:
        f["built"].append({
            "id": one["id"],
            "label": one["label"],
            "fixes": list(one["fixes"]),
            "results": sparse(one["results"], f"built set {one['id']!r}"),
            "noise": one.get("noise") or chain.noise(),
        })  # fmt: skip
    base_ctx = _Base(f)
    for one in f["fixes"]:
        one["counts"] = _fix_counts(base_ctx, one, _columns(one["effect"]))
    found = errors(f) or against(f, data, full)
    if found:
        raise ValueError("not a fixes file: " + "; ".join(found[:10]))
    return f


# ------------------------------------------------------------------------ text and files


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def dumps(f: Mapping) -> str:
    """The text of a fixes file: one line per item, per base column, per fix and per built set,
    so that a diff names them."""
    parts = []
    for key, value in f.items():
        if key in ("items", "fixes", "built") and value:
            text = "[\n" + ",\n".join("  " + _compact(v) for v in value) + "\n ]"
        elif key == "base" and value:
            text = "{\n" + ",\n".join(f"  {_compact(k)}:{_compact(v)}" for k, v in value.items()) + "\n }"
        else:
            text = json.dumps(value, ensure_ascii=False, allow_nan=False)
        parts.append(f" {_compact(key)}: {text}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def write(f: Mapping, path) -> Path:
    """Write a fixes file, checked first; refuse one larger than a page loads."""
    found = errors(f)
    if found:
        raise ValueError("not a fixes file: " + "; ".join(found[:10]))
    text = dumps(f)
    size = len(text.encode("utf-8"))
    if size > MAX_BYTES:
        raise ValueError(f"the fixes file would be {size} bytes, and a page loads {MAX_BYTES} at most")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read(path) -> dict:
    """A fixes file, read and checked, with the diagnostics file (and its matrix) beside it;
    raises ValueError with every error found."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"{path}: larger than {MAX_BYTES} bytes")
    f = fileformat.load_json(path)
    found = errors(f) or beside(f, path.parent)
    if found:
        raise ValueError(f"{path}: " + "; ".join(found[:10]))
    return f


def beside(f: Mapping, folder) -> list[str]:
    """Everything a checked fixes file and the diagnostics file it names, in `folder`,
    disagree on; that file's matrix is used where it is there too."""
    path = Path(folder) / f["of"]["file"]
    if not path.is_file():
        return [f"`of` names the diagnostics file {f['of']['file']}, which is not beside it"]
    try:
        data = fileformat.load_json(path)
    except ValueError as error:
        return [str(error)]
    if fileformat.errors(data):
        return [f"{f['of']['file']} is not a diagnostics file a page shows: check it on its own"]
    full = None
    named = data.get("matrix")
    if named and (path.parent / named["file"]).is_file():
        try:
            full = matrix.read(path.parent / named["file"], data)
        except ValueError as error:
            return [str(error)]
    return against(f, data, full)


def entries_of(f: Mapping) -> list[tuple[str, int]]:
    """How many entries each fix's effect holds, the largest first: what the file's size is
    made of. A fix to something every item uses holds about one entry per item and indicator."""
    found = [(one["id"], sum(len(v) for v in one["effect"].values())) for one in f["fixes"]]
    return sorted(found, key=lambda x: (-x[1], x[0]))


def size_note(f: Mapping) -> str:
    """One line on what a checked file holds, for `sentier-diagnostics check`."""
    found = entries_of(f)
    total = sum(n for _, n in found) + sum(len(v) for b in f["built"] for v in b["results"].values())
    largest = ", ".join(f"{name!r} {n}" for name, n in found[:3])
    return (f"{len(found)} fixes and {len(f['built'])} built sets hold {total} entries over "
            f"{len(f['items'])} items; the largest fixes: {largest}")  # fmt: skip


# ------------------------------------------------------------------------ the base, worked out once


class _Base:
    """What every fix of a checked file is judged against: the base results, the floor of
    every item, and the class of every item against itself (agrees, near zero or missing)."""

    def __init__(self, f: Mapping):
        self.ids = [i["id"] for i in f["indicators"]]
        self.items = [r[0] for r in f["items"]]
        self.index = {item: k for k, item in enumerate(self.items)}
        table = {(x["indicator"], x["unit"]): x["value"] for x in f["rule"]["floors"]}
        self.floor = {ind: [table[(ind, r[4])] for r in f["items"]] for ind in self.ids}
        self.values = f["base"]
        self.kinds = {
            ind: [rule.classify(v, v, floor=fl) for v, fl in zip(self.values[ind], self.floor[ind])]
            for ind in self.ids
        }
        self.tally = {}
        for ind in self.ids:
            tally = dict.fromkeys((rule.AGREES, rule.NEAR_ZERO, rule.MISSING), 0)
            for kind in self.kinds[ind]:
                tally[kind] += 1
            self.tally[ind] = tally


def _columns(sparse: Mapping) -> dict[str, dict[int, float | None]]:
    """`{indicator: [[item index, result], ...]}` as `{indicator: {item index: result}}`."""
    return {ind: {k: v for k, v in entries} for ind, entries in sparse.items()}


def _level(noise: Mapping, indicator: str) -> float | None:
    return (noise["by"] or {}).get(indicator) if noise["measured"] else None


def _side(before, after) -> str:
    return "both" if before is None and after is None else "before" if before is None else "after"


def _block(base: _Base, ind: str, changed: Mapping[int, float | None], tolerance: float,
           noise: float | None, claim: Mapping | None) -> dict:  # fmt: skip
    """The counts of one indicator: every item, the base against the base with `changed`
    applied, judged by the rule with `tolerance` and `noise`, and against `claim` where there
    is one. Only the changed items are judged one by one: every other pair is the base
    against itself, counted from the base's own classes."""
    classes = dict.fromkeys(rule.CLASSES, 0)
    missing = dict.fromkeys(fileformat.MISSING_SIDES, 0)
    ways = dict.fromkeys(rule.DIRECTIONS, 0)
    bands = dict.fromkeys(rule.BANDS, 0)
    verdicts = dict.fromkeys(claims.VERDICTS, 0) if claim is not None else None
    values, floors, kinds = base.values[ind], base.floor[ind], base.kinds[ind]
    for kind, n in base.tally[ind].items():
        classes[kind] += n
    missing["both"] += base.tally[ind][rule.MISSING]
    entries = []
    if claim is not None:
        entries = [(e, None if e["items"] == "*" else set(e["items"])) for e in claims.entries_for(claim, ind)]
    for k, after in changed.items():
        before, was = values[k], kinds[k]
        classes[was] -= 1
        if was == rule.MISSING:
            missing["both"] -= 1
        kind, way, band = rule.judge(before, after, floor=floors[k], tolerance=tolerance, noise=noise)
        classes[kind] += 1
        if kind == rule.MISSING:
            missing[_side(before, after)] += 1
        if way:
            ways[way] += 1
        if band:
            bands[band] += 1
        if verdicts is not None:
            item = base.items[k]
            covering = [e for e, listed in entries if listed is None or item in listed]
            verdicts[claims.verdict(kind, before, after, way, covering)] += 1
    if verdicts is not None:
        # the pairs no change touched: the base against itself
        musts = [listed for e, listed in entries if e["expect"] == claims.MUST]
        every = any(listed is None for listed in musts)
        must_items = set() if every else {base.index[i] for listed in musts for i in listed}
        for kind in (rule.AGREES, rule.NEAR_ZERO, rule.MISSING):
            untouched = base.tally[ind][kind] - sum(1 for k in changed if kinds[k] == kind)
            if kind == rule.MISSING:
                verdicts[claims.NOT_JUDGED] += untouched
                continue
            held = untouched if every else sum(1 for k in must_items if kinds[k] == kind and k not in changed)
            verdicts[claims.NOT_MOVED] += held
            verdicts[claims.UNCHANGED if kind == rule.AGREES else claims.NOT_JUDGED] += untouched - held
    return {"pairs": len(values), "classes": classes, "missing": missing, "directions": ways, "bands": bands,
            "verdicts": verdicts, "closer": None, "further": None}  # fmt: skip


def _fix_counts(base: _Base, one: Mapping, effect: Mapping[str, Mapping[int, float | None]]) -> dict:
    """A fix's counts: the base against the base with its effect, with its own tolerance,
    noise and claim."""
    tol = one["tolerance"]["value"]
    return {ind: _block(base, ind, effect[ind], tol, _level(one["noise"], ind), one["claim"]) for ind in base.ids}


def _sum(before: float | None, results: list[float | None]) -> tuple[float | None, bool]:
    """The result of a set at one item: the base plus the effects of the fixes that change it,
    and whether a sum could be formed. A fix without a result leaves none; a base without a
    result leaves nothing to add two fixes' differences to.

    >>> _sum(1.0, [1.5]), _sum(1.0, [1.5, 2.0]), _sum(1.0, [1.5, None]), _sum(None, [1.0, 2.0])
    ((1.5, True), (2.5, True), (None, True), (None, False))
    """
    if len(results) == 1:
        return results[0], True
    if any(r is None for r in results):
        return None, True
    if before is None:
        return None, False
    return before + sum(r - before for r in results), True


def _summed(base: _Base, effects: list[Mapping], ind: str) -> dict[int, tuple[float | None, bool]]:
    """The items the chosen fixes change in one indicator, with the set's result at each."""
    touched: dict[int, list] = {}
    for effect in effects:
        for k, value in effect[ind].items():
            touched.setdefault(k, []).append(value)
    return {k: _sum(base.values[ind][k], found) for k, found in touched.items()}


# ------------------------------------------------------------------------ a chosen set


def _chosen(f: Mapping, ids: Iterable[str]) -> list[dict]:
    order = {one["id"]: k for k, one in enumerate(f["fixes"])}
    ids = list(ids)
    if not ids:
        raise ValueError("a set holds at least one fix")
    for one in ids:
        if one not in order:
            raise ValueError(f"the file holds no fix {one!r}")
    if len(set(ids)) != len(ids):
        raise ValueError("a set holds each fix once")
    return [f["fixes"][k] for k in sorted(order[i] for i in ids)]


def held_pairs(f: Mapping, ids: Iterable[str]) -> list[dict]:
    """The listed pairs of a set: two of its fixes that can interact, with the reason."""
    chosen = {one["id"] for one in _chosen(f, ids)}
    return [p for p in f["interactions"]["pairs"] if set(p["fixes"]) <= chosen]


def built_of(f: Mapping, ids: Iterable[str]) -> dict | None:
    """The built set that holds exactly these fixes, or None."""
    chosen = {one["id"] for one in _chosen(f, ids)}
    return next((b for b in f["built"] if set(b["fixes"]) == chosen), None)


def label(f: Mapping, ids: Iterable[str]) -> str:
    """Built, exact or estimated (SPEC 16.5)."""
    chosen = _chosen(f, ids)
    if len(chosen) == 1 or built_of(f, ids) is not None:
        return BUILT
    if f["interactions"]["checked"] and not held_pairs(f, ids):
        return EXACT
    return ESTIMATED


def pair_terms(f: Mapping, ids: Iterable[str]) -> dict:
    """How far an estimated set may lie from its sum, to first order: `{value, measured,
    pairs}`, the value being the sum of the measured sizes of the listed pairs it holds, and
    None where some were not measured (a pair not measured is never a pair of size 0)."""
    held = held_pairs(f, ids)
    sizes = [p["largest"] for p in held if p["largest"] is not None]
    value = sum(sizes) if len(sizes) == len(held) else None
    return {"value": value, "measured": len(sizes), "pairs": len(held)}


def tolerance_of(f: Mapping, ids: Iterable[str]) -> float:
    """The tolerance of a set: the largest of its fixes'."""
    return max(one["tolerance"]["value"] for one in _chosen(f, ids))


def noise_of(f: Mapping, ids: Iterable[str]) -> dict[str, dict]:
    """The noise of a set, per indicator: `{value, measured, fixes}`, the value being the sum
    of the noise of the fixes whose noise was measured there, and None where none was: not
    measured is never none."""
    chosen = _chosen(f, ids)
    out = {}
    for ind in (i["id"] for i in f["indicators"]):
        levels = [lv for lv in (_level(one["noise"], ind) for one in chosen) if lv is not None]
        out[ind] = {"value": sum(levels) if levels else None, "measured": len(levels), "fixes": len(chosen)}
    return out


def _changed(f: Mapping, base: _Base, ids) -> tuple[dict, dict]:
    """The items a set changes, per indicator, with its result at each; and the items where
    no sum can be formed (a missing base under two fixes or more)."""
    chosen = _chosen(f, ids)
    found = built_of(f, ids)
    if len(chosen) == 1 or found is not None:
        source = chosen[0]["effect"] if found is None else found["results"]
        return _columns(source), {ind: [] for ind in base.ids}
    effects = [_columns(one["effect"]) for one in chosen]
    changed, cannot = {}, {}
    for ind in base.ids:
        cells = _summed(base, effects, ind)
        changed[ind] = {k: v for k, (v, _) in cells.items()}
        cannot[ind] = sorted(k for k, (_, ok) in cells.items() if not ok)
    return changed, cannot


def compose(f: Mapping, ids: Iterable[str]) -> dict:
    """What a page draws for a set: its fixes in the order of the file (each with its own
    claim and counts), its label, the listed pairs it holds, its tolerance and noise, and its
    result for every item, `{indicator: [result or None, ...]}` in the order of `items`.
    `cannot_add` names, per indicator, the item indices whose result is None because the base
    has none to add two fixes' differences to, so that it reads apart from a missing result.
    A set has no verdict."""
    chosen = _chosen(f, ids)
    names = [one["id"] for one in chosen]
    base = _Base(f)
    changed, cannot = _changed(f, base, names)
    results = {}
    for ind in base.ids:
        column = list(base.values[ind])
        for k, value in changed[ind].items():
            column[k] = value
        results[ind] = column
    return {
        "fixes": [{k: one[k] for k in ("id", "label", "claim", "counts")} for one in chosen],
        "label": label(f, names),
        "pairs": held_pairs(f, names),
        "pair_terms": pair_terms(f, names),
        "tolerance": tolerance_of(f, names),
        "noise": noise_of(f, names),
        "results": results,
        "cannot_add": cannot,
    }


def counts(f: Mapping, ids: Iterable[str]) -> dict:
    """The counts of a set against the base, per indicator, with its label beside them: an
    estimated set's counts are estimates ("estimated: 153 would differ"). No verdicts."""
    names = [one["id"] for one in _chosen(f, ids)]
    base = _Base(f)
    changed, _ = _changed(f, base, names)
    tol, noise = tolerance_of(f, names), noise_of(f, names)
    return {
        "label": label(f, names),
        "by": {ind: _block(base, ind, changed[ind], tol, noise[ind]["value"], None) for ind in base.ids},
    }


# ------------------------------------------------------------------------ the check


def errors(f) -> list[str]:
    """Everything wrong with a fixes file on its own; nothing for one a page can load. It
    never raises: a value it cannot read is a fault like any other."""
    found: list[str] = []
    try:
        return _errors(f, found)
    except Exception as error:  # noqa: BLE001 - the backstop of a check that must not raise
        return [*found, f"{fileformat.STOPPED} ({type(error).__name__}: {str(error)[:200]})"]


def _errors(f, found: list[str]) -> list[str]:
    if not isinstance(f, Mapping):
        return ["not a fixes file: not an object"]
    said = f.get("format")
    if said != FORMAT:
        if isinstance(said, str) and said.startswith(FAMILY):
            return [f"format {said!r}: this reader knows {FORMAT} only"]
        return [f"not a fixes file of format {FORMAT}"]
    found += [f"a key this format does not know: {key}" for key in sorted(set(f) - KEYS - OPTIONAL_KEYS)]
    found += [f"a key this format requires: {key}" for key in sorted(KEYS - set(f))]
    if found:
        return found
    of = f["of"]
    if not (
        isinstance(of, dict)
        and set(of) == OF_KEYS
        and isinstance(of["file"], str)
        and fileformat.FILE_NAME.fullmatch(of["file"])
        and fileformat.is_text(of["title"], 120)
        and fileformat.is_text(of["base"], fileformat.MAX_ID)
    ):
        found.append("`of` is not {file, title, base}: a file name, that file's title and a state's id")
    if not fileformat.is_text(f["title"], 120) or not fileformat.is_optional(f["about"]):
        found.append("`title` is not a short text, or `about` not a text")
    for key in ("item", "indicator"):
        word = f.get(key)
        if (word is not None or key == "item") and not (
            isinstance(word, dict) and set(word) == {"one", "many"}
            and all(fileformat.is_text(w, 30) for w in word.values())
        ):  # fmt: skip
            found.append(f"`{key}` is not {{one, many}}")
    if not fileformat.is_text(f["made_by"], 60):
        found.append("`made_by` is not a short text")
    notes = f["notes"]
    if not isinstance(notes, list) or len(notes) > fileformat.MAX_NOTES or not all(map(fileformat.is_text, notes)):
        found.append(f"`notes` is not a list of at most {fileformat.MAX_NOTES} texts")
    indicators = fileformat._indicators(f, found)
    floors = _rule(f, found, indicators)
    if not indicators or floors is None or not _items(f, found, indicators, floors):
        return found
    n = len(f["items"])
    said_base = f["base"]
    if not (
        isinstance(said_base, dict)
        and set(said_base) == set(indicators)
        and all(isinstance(said_base[i], list) and len(said_base[i]) == n
                and all(v is None or rule.is_value(v) for v in said_base[i]) for i in indicators)
    ):  # fmt: skip
        found.append("`base` is not one result or null per item, for every indicator")
    if found:
        return found  # nothing can be judged against a base that cannot be read
    base = _Base(f)
    effects = _fixes(f, found, base)
    if effects is None:
        return found
    pairs = _interactions(f, found, effects)
    if pairs is not None:
        _built(f, found, base, effects, pairs)
    return found


def _rule(f, found, indicators) -> dict | None:
    said = f["rule"]
    if not isinstance(said, dict) or set(said) != RULE_KEYS:
        found.append(f"`rule` is not {{{', '.join(sorted(RULE_KEYS))}}}")
        return None
    if not fileformat.is_share(said["floor_factor"]):
        found.append("`rule`: the floor factor is not a share")
    if not fileformat.is_text(said["floors_from"], fileformat.MAX_ID):
        found.append("`rule`: the floors come from a state, named by its id")
    if said["beyond"] != rule.BEYOND_FACTOR:
        found.append(f"`rule.beyond` is {rule.BEYOND_FACTOR:g}: one rule for every file")
    if not isinstance(said["floors"], list):
        found.append("`rule.floors` is not a list")
        return None
    table = {}
    for one in said["floors"]:
        if not (
            isinstance(one, dict)
            and set(one) == fileformat.FLOOR_KEYS
            and one["indicator"] in indicators
            and fileformat.is_optional(one["unit"], fileformat.MAX_WORD)
            and fileformat.is_share(one["value"])
            and one["basis"] in fileformat.FLOOR_BASES
            and fileformat.is_count(one["n"])
        ):
            found.append("a floor is not {indicator, unit, value, basis, n} of a known indicator")
            return None
        key = (one["indicator"], one["unit"])
        if key in table:
            found.append(f"two floors for {one['indicator']!r} in unit {one['unit']!r}")
        table[key] = one["value"]
    return table


def _items(f, found, indicators, floors) -> bool:
    rows = f["items"]
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ITEMS:
        found.append(f"`items` is not a list of 1 to {MAX_ITEMS} items")
        return False
    seen = set()
    for at, row in enumerate(rows):
        if not matrix._is_row(row):
            found.append(f"item {at}: not [id, name, place, group, unit]")
            return False
        if row[0] in seen:
            found.append(f"item {row[0]!r} is in the file twice")
            return False
        seen.add(row[0])
    units = {row[4] for row in rows}
    for ind in indicators:
        for unit in sorted(units, key=lambda u: (u is None, u or "")):
            if (ind, unit) not in floors:
                found.append(f"no floor for {ind!r} in unit {unit!r}")
                return False
    return True


def _sparse(said, where: str, base: _Base, found: list[str]) -> dict | None:
    """An effect, or the results of a built set: per indicator, the items whose result is not
    the base result, `[[item index, result or null], ...]`."""
    if not isinstance(said, dict) or set(said) != set(base.ids):
        found.append(f"{where}: not one list per indicator of the file")
        return None
    n = len(base.items)
    out = {}
    for ind in base.ids:
        entries = said[ind]
        if not isinstance(entries, list) or len(entries) > n:
            found.append(f"{where}, {ind}: not a list of at most one entry per item")
            return None
        column = {}
        for entry in entries:
            if not (
                isinstance(entry, list)
                and len(entry) == 2
                and fileformat.is_count(entry[0])
                and (entry[1] is None or rule.is_value(entry[1]))
            ):
                found.append(f"{where}, {ind}: an entry is not [item index, result or null]")
                return None
            k, value = entry
            if k >= n:
                found.append(f"{where}, {ind}: names item {k}, and the file holds {n}")
                return None
            if k in column:
                found.append(f"{where}, {ind}: holds item {base.items[k]!r} twice")
                return None
            if value == base.values[ind][k]:
                found.append(f"{where}, {ind}: item {base.items[k]!r} is written with the base result, as if it changed")
                return None
            column[k] = value
        out[ind] = column
    return out


def _noise_errors(noise, where: str, indicators) -> list[str]:
    if not (
        isinstance(noise, dict)
        and set(noise) == {"measured", "between", "by", "note"}
        and isinstance(noise["measured"], bool)
        and fileformat.is_optional(noise["note"])
    ):
        return [f"{where}: `noise` is not {{measured, between, by, note}}"]
    if noise["measured"]:
        if not (
            isinstance(noise["between"], list)
            and len(noise["between"]) == 2
            and all(fileformat.is_text(n, fileformat.MAX_LABEL) for n in noise["between"])
            and isinstance(noise["by"], dict)
            and set(noise["by"]) <= set(indicators)
            and all(fileformat.is_share(v) for v in noise["by"].values())
        ):
            return [f"{where}: measured noise names the two builds and a size per indicator"]
    elif noise["between"] is not None or noise["by"] is not None:
        return [f"{where}: noise that was not measured has no builds and no sizes"]
    return []


def _fixes(f, found, base: _Base) -> dict | None:
    """Every fix, its counts and verdicts worked out again; its effect, by id."""
    said = f["fixes"]
    if not isinstance(said, list) or not 0 < len(said) <= MAX_FIXES:
        found.append(f"`fixes` is not a list of 1 to {MAX_FIXES} fixes")
        return None
    effects = {}
    for one in said:
        if not isinstance(one, dict) or set(one) != FIX_KEYS or not fileformat.is_text(one["id"], fileformat.MAX_ID):
            found.append(f"a fix is not {{{', '.join(sorted(FIX_KEYS))}}}")
            return None
        where = f"fix {one['id']!r}"
        if one["id"] in effects:
            found.append(f"two fixes have the id {one['id']!r}")
            return None
        if not fileformat.is_text(one["label"], fileformat.MAX_LABEL) or not fileformat.is_optional(one["about"]):
            found.append(f"{where}: `label` or `about` is not a text")
        if not fileformat.is_text(one["kind"], fileformat.MAX_WORD) or not isinstance(one["explained"], bool):
            found.append(f"{where}: a fix has a `kind` and says whether a cause explains it")
        if not fileformat.is_link(one["link"]):
            found.append(f"{where}: `link` is not an https address")
        if one["claim"] is not None:
            shape = fileformat.claim_errors(one["claim"], where, base.ids, "items")
            if shape:
                found += shape
                return None
            if any(e["items"] is None for e in one["claim"]["scope"]):
                found.append(f"{where}: a fix's claim names its items: a page works out each item's verdict from it")
                return None
            unknown = {i for e in one["claim"]["scope"] if e["items"] != "*" for i in e["items"]} - set(base.index)
            if unknown:
                found.append(f"{where}: its claim names {len(unknown)} items the file does not hold")
                return None
        tol = one["tolerance"]
        if not (
            isinstance(tol, dict)
            and set(tol) == {"value", "basis", "note"}
            and fileformat.is_share(tol["value"])
            and tol["basis"] in fileformat.TOLERANCE_BASES
            and fileformat.is_optional(tol["note"])
        ):
            found.append(f"{where}: `tolerance` is not {{value, basis, note}}")
            return None
        noise = _noise_errors(one["noise"], where, base.ids)
        if noise:
            found += noise
            return None
        effect = _sparse(one["effect"], f"{where}: its effect", base, found)
        if effect is None:
            return None
        effects[one["id"]] = effect
        written = one["counts"]
        if not isinstance(written, dict) or set(written) != set(base.ids):
            found.append(f"{where}: `counts` is not one block per indicator")
            return None
        shape = [e for ind in base.ids for e in fileformat._block(written[ind], f"{where}, counts of {ind!r}", one)]
        shape += [f"{where}, counts of {ind!r}: `{key}` is null: a fix has no published results to come closer to"
                  for ind in base.ids for key in ("closer", "further") if written[ind][key] is not None]  # fmt: skip
        if shape:
            found += shape
            continue
        again = _fix_counts(base, one, effect)
        for ind in base.ids:
            for key, value in again[ind].items():
                if written[ind][key] != value:
                    found.append(f"{where}, counts of {ind!r}: `{key}` is not what its effect and the base give")
    return effects


def _interactions(f, found, effects: Mapping) -> set[frozenset] | None:
    """The pairs of fixes that can interact, each once, as sets of two ids."""
    said = f["interactions"]
    if not (
        isinstance(said, dict)
        and set(said) == INTERACTION_KEYS
        and isinstance(said["checked"], bool)
        and isinstance(said["pairs"], list)
    ):
        found.append("`interactions` is not {checked, method, by, pairs}")
        return None
    if said["checked"]:
        if not fileformat.is_text(said["method"]):
            found.append("`interactions`: a check says what it did (`method`)")
        elif IDENTIFIER.search(said["method"]):
            found.append("`interactions.method` holds an identifier of the model: say it in words")
        if said["by"] is None:
            found.append("`interactions`: a check says who or what ran it (`by`)")
        else:
            found += fileformat.origin_errors(said["by"], "`interactions`")
    else:
        if said["method"] is not None or said["by"] is not None:
            found.append("`interactions`: no check ran, so it has no `method` and no `by`")
        if said["pairs"]:
            found.append(
                "`interactions`: pairs are listed and `checked` is false: a pair that is not listed would "
                "read as cleared"
            )
            return None
    if len(said["pairs"]) > MAX_FIXES * (MAX_FIXES - 1) // 2:
        found.append("`interactions.pairs` lists more pairs than fixes can make")
        return None
    pairs: set[frozenset] = set()
    for one in said["pairs"]:
        if not isinstance(one, dict) or set(one) != PAIR_KEYS:
            found.append(
                "a pair is not {fixes, reason, largest}: it says why in words, not what in the model they share"
            )
            return None
        named = one["fixes"]
        if not (isinstance(named, list) and len(named) == 2 and all(isinstance(x, str) for x in named)):
            found.append("a pair does not name two fixes")
            return None
        where = f"the pair {named[0]!r} and {named[1]!r}"
        unknown = [x for x in named if x not in effects]
        if unknown:
            found.append(f"{where}: the file holds no fix {unknown[0]!r}")
            continue
        if named[0] == named[1]:
            found.append(f"{where}: names one fix twice")
            continue
        if one["largest"] is not None and not fileformat.is_share(one["largest"]):
            found.append(f"{where}: `largest` is not a share, or null where it was not measured")
        if not fileformat.is_text(one["reason"], 300):
            found.append(f"{where}: its reason is not a short text")
        elif IDENTIFIER.search(one["reason"]):
            found.append(f"{where}: its reason holds an identifier of the model: say what they share in words")
        key = frozenset(named)
        if key in pairs:
            found.append(f"{where}: is listed twice")
        pairs.add(key)
    return pairs


def _sizes(f) -> dict[frozenset, float]:
    """The measured size of every listed pair that has one."""
    return {frozenset(p["fixes"]): p["largest"] for p in f["interactions"]["pairs"] if p["largest"] is not None}


def _built(f, found, base: _Base, effects: Mapping, pairs: set[frozenset]) -> None:
    said = f["built"]
    if not isinstance(said, list) or len(said) > MAX_BUILT:
        found.append(f"`built` is not a list of at most {MAX_BUILT} sets")
        return
    checked = f["interactions"]["checked"]
    sizes = _sizes(f)
    by_id = {one["id"]: one for one in f["fixes"]}
    ids, sets = set(), set()
    for one in said:
        if not isinstance(one, dict) or set(one) != BUILT_KEYS or not fileformat.is_text(one["id"], fileformat.MAX_ID):
            found.append(f"a built set is not {{{', '.join(sorted(BUILT_KEYS))}}}")
            return
        where = f"built set {one['id']!r}"
        if one["id"] in ids:
            found.append(f"two built sets have the id {one['id']!r}")
        ids.add(one["id"])
        if not fileformat.is_text(one["label"], fileformat.MAX_LABEL):
            found.append(f"{where}: `label` is not a short text")
        named = one["fixes"]
        if not (isinstance(named, list) and all(isinstance(x, str) for x in named)):
            found.append(f"{where}: `fixes` is not a list of the ids of fixes")
            continue
        unknown = [x for x in named if x not in effects]
        if unknown:
            found.append(f"{where}: the file holds no fix {unknown[0]!r}")
            continue
        if len(set(named)) != len(named):
            found.append(f"{where}: holds a fix twice")
            continue
        if len(named) < 2:
            found.append(f"{where}: holds fewer than two fixes: one fix is built already")
            continue
        key = frozenset(named)
        if key in sets:
            found.append(f"{where}: holds the same fixes as another built set")
        sets.add(key)
        noise = _noise_errors(one["noise"], where, base.ids)
        if noise:
            found += noise
            continue
        results = _sparse(one["results"], f"{where}: its results", base, found)
        if results is None or not checked:
            continue
        chosen = [by_id[x] for x in named]
        if not any(p <= key for p in pairs):
            found += _disagreements(base, where, chosen, [effects[x] for x in named], one, results)
        elif key in sizes:  # one listed pair, built: its measured size is held to the build
            found += _disagreements(base, where, chosen, [effects[x] for x in named], one, results, sizes[key])


#: How many disagreements of one built set are named before the rest are counted.
NAMED = 5


def _disagreements(base: _Base, where: str, chosen: list, effects: list, one: Mapping, results: Mapping,
                   largest: float | None = None) -> list[str]:  # fmt: skip
    """Where a built set is further from the sum of its effects than the file says: by the
    rule, with the largest tolerance of its fixes and the sum of their noise and its own. A
    set the file calls independent must be the sum; a built pair whose cross term the file
    measured (`largest`) must lie within it."""
    tol = max(x["tolerance"]["value"] for x in chosen)
    if largest is not None:
        tol = max(tol, largest)
    found, more = [], 0
    for ind in base.ids:
        levels = [lv for lv in (_level(x["noise"], ind) for x in [*chosen, one]) if lv is not None]
        level = sum(levels) if levels else None
        cells = _summed(base, effects, ind)
        for k in sorted(set(cells) | set(results[ind])):
            before = base.values[ind][k]
            summed, ok = cells.get(k, (before, True))
            if not ok:
                continue  # no sum to hold the build to
            got = results[ind].get(k, before)
            kind = rule.classify(summed, got, floor=base.floor[ind][k], tolerance=tol, noise=level)
            if kind in claims.STILL or (kind == rule.MISSING and summed is None and got is None):
                continue
            if len(found) < NAMED:
                said = ("the file calls its fixes independent, and they are not" if largest is None
                        else f"the file measured their cross term at {largest:g} at most, and it is larger")  # fmt: skip
                found.append(
                    f"{where}, item {base.items[k]!r}, {ind}: built {got!r}, the sum of its effects is {summed!r} "
                    f"({kind}); {said}"
                )
            else:
                more += 1
    if more:
        found.append(f"{where}: and {more} more pairs where the build is not what the file says")
    return found


# ------------------------------------------------------------------------ against the diagnostics file


def against(f: Mapping, data: Mapping, full: Mapping | None = None) -> list[str]:
    """Everything a checked fixes file and its checked diagnostics file disagree on. Its items
    and base results are held to the matrix `full` where it is given, and to the listed items
    where it is not."""
    try:
        return _against(f, data, full)
    except Exception as error:  # noqa: BLE001 - a backstop, as in `errors`
        return [f"{fileformat.STOPPED} ({type(error).__name__}: {str(error)[:200]})"]


def _against(f: Mapping, data: Mapping, full: Mapping | None) -> list[str]:
    found = []
    of = f["of"]
    if of["title"] != data["title"]:
        found.append("it belongs to another file: `of.title` is not the diagnostics file's title")
    states = [s["id"] for s in data["states"]]
    if of["base"] not in states:
        return [*found, f"the base {of['base']!r} is no state of the diagnostics file"]
    if f["indicators"] != data["indicators"]:
        found.append("its indicators differ from the diagnostics file's")
    if f["item"] != data["item"] or f.get("indicator") != data.get("indicator"):
        found.append("its words for an item or an indicator differ from the diagnostics file's")
    if f["rule"] != {k: data["rule"][k] for k in RULE_KEYS}:
        found.append("its floors differ from the diagnostics file's")
    if found:
        return found
    ids = [i["id"] for i in data["indicators"]]
    at, nstates = states.index(of["base"]), len(states)
    if full is not None:
        if [list(r) for r in f["items"]] != [list(r) for r in full["items"]]:
            return ["its items are not the matrix's, in the matrix's order"]
        for x, ind in enumerate(ids):
            if [row[x * nstates + at] for row in full["values"]] != f["base"][ind]:
                found.append(f"the base results in {ind!r} are not the matrix's results of state {of['base']!r}")
        return found
    if len(f["items"]) != data["items_count"]["all"]:
        found.append(f"it holds {len(f['items'])} items, and the diagnostics file counts {data['items_count']['all']}")
    index = {row[0]: k for k, row in enumerate(f["items"])}
    for item in data["items"]:
        k = index.get(item["id"])
        if k is None:
            found.append(f"the listed item {item['id']!r} is not in the fixes file")
            continue
        if f["items"][k][1:] != [item["name"], item["place"], item["group"], item["unit"]]:
            found.append(f"item {item['id']!r}: its name, place, group or unit differ from the diagnostics file")
        for ind in ids:
            if item["values"][ind][at] != f["base"][ind][k]:
                found.append(f"item {item['id']!r}, {ind}: the base result is not the diagnostics file's")
    return found
