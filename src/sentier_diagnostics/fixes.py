"""Fixes against one base, `sentier-diagnostics-fixes/1` (SPEC 16).

A chain measures each step with every earlier step applied, so a step's difference belongs
to its place in the order. A fixes file measures each fix on its own against one state of
a chain, the base: a fix has one effect, whichever set it joins and in whatever order. A
fix that cannot be applied alone names the fixes it needs (`requires`): its effect is
measured with them applied, against a build of them, and choosing it chooses them.

A reader may choose any set of fixes, and gets what they require with them. Its result is
the base plus the sum of their effects, except where a build the file holds inside the set
covers every fix that changes an item: there the build's result is taken. A set is
labelled:

    built       the file holds this build: one fix with what it requires, or a set the
                producer built (`built`)
    exact       interactions were checked, and no two of its fixes are a listed pair
    estimated   otherwise: drawn, and marked on every cell and count

A set has no verdict: each claim is judged in its own fix. A set's tolerance is the largest
of its fixes'; its noise is the sum of their noise, with the number of fixes whose noise was
measured, never read as none.

A listed pair holds no text: its kind of interaction (one of `PAIR_KINDS`, from where the
two changes meet in h = c·B·A⁻¹·f), how many items it can reach and the measured size of
its cross term. So nothing of the model, no name and no identifier, can go into it.

`errors(f)` checks a file on its own: its shape, every fix's counts and verdicts worked out
again from its effect and what it was measured against, the pairs, and every built set the
file calls independent against the sum of its effects. `against(f, data, full)` holds it to
its diagnostics file and that file's matrix, and a built set that names a state of the chain
to that state; `beside(f, folder)` finds them next to it, as `sentier-diagnostics check`
does.

`build(...)` makes a file from a checked diagnostics file, its matrix and the results built
with each fix; `chosen`, `label`, `compose` and `counts` give what a page draws for a set.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from functools import cached_property
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
FIX_KEYS = {"id", "label", "about", "kind", "explained", "link", "requires", "claim", "tolerance", "noise",
            "effect", "counts"}  # fmt: skip
INTERACTION_KEYS = {"checked", "method", "by", "pairs"}
PAIR_KEYS = {"fixes", "kind", "reach", "largest"}
BUILT_KEYS = {"id", "label", "fixes", "state", "results", "noise"}

#: Where two changes of h = c·B·A⁻¹·f meet, so that their joint result is not the sum of
#: their effects (SPEC 16.3). Two changes to different factors, or to different entries of
#: B, add up exactly and are never a pair.
TECHNOSPHERE = "technosphere"  # both change A, and an item's supply chain reaches both
TECHNOSPHERE_AND_EMISSION = "technosphere and emission"  # A, and an amount of B on a chain the A change shifts
TECHNOSPHERE_AND_FACTOR = "technosphere and factor"  # A, and the factor of a flow the A change shifts
EMISSION_AND_FACTOR = "emission and factor"  # an amount of a flow, and that flow's factor
SAME_ENTRY = "same entry"  # both change one number of A, B or c: two edits of one number do not add
PAIR_KINDS = (TECHNOSPHERE, TECHNOSPHERE_AND_EMISSION, TECHNOSPHERE_AND_FACTOR, EMISSION_AND_FACTOR, SAME_ENTRY)

MAX_FIXES, MAX_BUILT = 1000, 500
MAX_ITEMS, MAX_BYTES = matrix.MAX_ITEMS, matrix.MAX_BYTES

BUILT, EXACT, ESTIMATED = "built", "exact", "estimated"
LABELS = (BUILT, EXACT, ESTIMATED)

#: The shape of an identifier of a model (a UUID, or 32 hexadecimal digits): refused in the
#: one text the interactions hold, the method of the check.
IDENTIFIER = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b|\b[0-9a-fA-F]{32}\b"
)


# ------------------------------------------------------------------------ making a file


def fix(id: str, label: str, *, kind: str, requires: Iterable[str] = (), explained: bool = True,
        about: str | None = None, link: str | None = None, claim: dict | None = None,
        tolerance: dict | None = None, noise: dict | None = None) -> dict:  # fmt: skip
    """One fix, as `build` takes it: what a step has (`chain.step`), and the fixes it needs
    applied first."""
    one = chain.step(id, label, kind=kind, explained=explained, about=about, link=link, claim=claim,
                     tolerance=tolerance, noise=noise)  # fmt: skip
    return {**one, "requires": list(requires)}


def pair(a: str, b: str, kind: str, *, reach: int | None = None, largest: float | None = None) -> dict:
    """Two fixes that can interact: `kind` is one of `PAIR_KINDS`, `reach` how many items the
    cross term can change, `largest` its measured size (SPEC 16.6); None where not counted or
    not measured."""
    return {"fixes": [a, b], "kind": kind, "reach": reach, "largest": largest}


def interactions(checked: bool = False, *, method: str | None = None, by: dict | None = None,
                 pairs: Iterable[dict] = ()) -> dict:  # fmt: skip
    """The check of pairs: `checked` true where every pair was examined, false where none was;
    `pairs` are `pair(...)`, every pair that can interact, each once."""
    return {"checked": checked, "method": method, "by": by, "pairs": list(pairs)}


def built_set(id: str, label: str, fixes: Iterable[str], results: Mapping, *, state: str | None = None,
              noise: dict | None = None) -> dict:  # fmt: skip
    """A set the producer built: `results` are `{indicator: {item: result or None}}`, an item
    left out being the base result; `state` the id of the chain's state it is, where it is
    one (the release with every fix)."""
    return {"id": id, "label": label, "fixes": list(fixes), "state": state, "results": results,
            "noise": noise or chain.noise()}  # fmt: skip


def _cell(full: Mapping, k: int, x: int, at: int, nstates: int):
    """One result of a matrix: item `k`, indicator `x`, state `at`."""
    return full["values"][k][x * nstates + at]


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
    added_items: Iterable = (),
    file: str = chain.FILE,
    about: str | None = None,
    notes: Iterable[str] = (),
) -> dict:
    """A fixes file, counted and checked.

    - `data` and `full`: the checked diagnostics file and its matrix; the items and the base
      results come from the matrix, in its order.
    - `base`: the id of the state every fix is measured from.
    - `fixes`: `fix(...)`, in the order the page lists them; a fix's requirements come first.
    - `results`: `{fix id: {indicator: {item: result or None}}}`, built with that fix and what
      it requires. An item left out is the result without the fix.
    - `interactions`: `interactions(...)`; not checked where it is None.
    - `built`: `built_set(...)`.
    - `added_items`: `[id, name, place, group, unit]` of items a fix brings that the base
      does not hold; the base has no result for them.
    - `file`: the name of the diagnostics file beside it.
    """
    ids = [i["id"] for i in data["indicators"]]
    states = [s["id"] for s in data["states"]]
    if base not in states:
        raise ValueError(f"the base {base!r} is no state of {data['title']!r}")
    at, nstates = states.index(base), len(states)
    rows = [list(r) for r in full["items"]] + [list(r) for r in added_items]
    m = len(full["items"])
    index = {r[0]: k for k, r in enumerate(rows)}
    if len(index) != len(rows):
        raise ValueError("an added item is an item of the base already")
    base_values = {
        ind: [_cell(full, k, x, at, nstates) for k in range(m)] + [None] * (len(rows) - m)
        for x, ind in enumerate(ids)
    }
    known = [one["id"] for one in fixes]
    unknown = set(results) - set(known)
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
    ctx = _Base(f)

    def sparse(given: Mapping, where: str, under: Mapping) -> dict:
        unknown = set(given) - set(ids)
        if unknown:
            raise ValueError(f"{where}: results of an indicator the file does not hold: {sorted(unknown)}")
        out = {}
        for ind in ids:
            entries = []
            for item, value in (given.get(ind) or {}).items():
                if item not in index:
                    raise ValueError(f"{where}: {item!r} is no item of the base, and not an added item")
                if value is not None and not rule.is_value(value):
                    raise ValueError(f"{where}, {ind}, {item}: {value!r} is not a finite number or None")
                value = None if value is None else float(value)
                k = index[item]
                if value != under[ind].get(k, base_values[ind][k]):
                    entries.append([k, value])
            out[ind] = sorted(entries, key=lambda e: e[0])
        return out

    closures: dict[str, frozenset] = {}
    builds = _Builds(ctx, closures)
    nothing = {ind: {} for ind in ids}
    for one in built:
        results_of = sparse(one["results"], f"built set {one['id']!r}", nothing)
        builds.built[frozenset(one["fixes"])] = _columns(results_of)
        f["built"].append({
            "id": one["id"],
            "label": one["label"],
            "fixes": list(one["fixes"]),
            "state": one.get("state"),
            "results": results_of,
            "noise": one.get("noise") or chain.noise(),
        })  # fmt: skip
    for one in fixes:
        requires = list(one.get("requires") or ())
        for needed in requires:
            if needed not in closures:
                raise ValueError(f"fix {one['id']!r} requires {needed!r}, which is not a fix given before it")
        closures[one["id"]] = frozenset(requires).union(*(closures[r] for r in requires))
        before = builds.column(closures[one["id"]])
        if before is None:
            raise ValueError(
                f"fix {one['id']!r}: no build of what it requires ({', '.join(sorted(closures[one['id']]))}); "
                "add a built set of exactly those fixes"
            )
        found_claim = one.get("claim")
        made = {
            "id": one["id"],
            "label": one["label"],
            "about": one.get("about"),
            "kind": one["kind"],
            "explained": bool(one.get("explained", True)),
            "link": one.get("link"),
            "requires": requires,
            "claim": claims.published(found_claim, True) if found_claim else None,
            "tolerance": one.get("tolerance") or chain.tolerance(),
            "noise": one.get("noise") or chain.noise(),
            "effect": sparse(results.get(one["id"]) or {}, f"fix {one['id']!r}", before),
            "counts": None,
        }
        builds.entries[one["id"]] = _columns(made["effect"])
        made["counts"] = _fix_counts(ctx, made, builds.entries[one["id"]], before)
        f["fixes"].append(made)
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


# ------------------------------------------------------------------------ the base and the builds


class _Base:
    """The base of a checked file, worked out once: its results, the floor of every item, and
    (when a count asks) the class of every item against itself: agrees, near zero or missing."""

    def __init__(self, f: Mapping):
        self.ids = [i["id"] for i in f["indicators"]]
        self.items = [r[0] for r in f["items"]]
        self.index = {item: k for k, item in enumerate(self.items)}
        table = {(x["indicator"], x["unit"]): x["value"] for x in f["rule"]["floors"]}
        self.floor = {ind: [table[(ind, r[4])] for r in f["items"]] for ind in self.ids}
        self.values = f["base"]

    @cached_property
    def kinds(self) -> dict[str, list[str]]:
        return {
            ind: [rule.classify(v, v, floor=fl) for v, fl in zip(self.values[ind], self.floor[ind])]
            for ind in self.ids
        }

    @cached_property
    def tally(self) -> dict[str, dict[str, int]]:
        out = {}
        for ind in self.ids:
            tally = dict.fromkeys((rule.AGREES, rule.NEAR_ZERO, rule.MISSING), 0)
            for kind in self.kinds[ind]:
                tally[kind] += 1
            out[ind] = tally
        return out


class _Builds:
    """Every build a file holds, as a column over the base (`{indicator: {item index: result}}`,
    the items where it is not the base): a fix with what it requires (its effect laid over the
    build of its requirements) and every built set."""

    def __init__(self, base: _Base, closures: Mapping[str, frozenset]):
        self.base = base
        self.closures = closures  # fix id: every fix it requires, at any depth
        self.entries: dict[str, dict] = {}  # fix id: its written results, by indicator
        self.built: dict[frozenset, dict] = {}  # the fixes of a built set: its results
        self._memo: dict[frozenset, dict] = {}

    @classmethod
    def of(cls, f: Mapping) -> _Builds:
        found = cls(_Base(f), _closures(f))
        found.entries = {one["id"]: _columns(one["effect"]) for one in f["fixes"]}
        found.built = {frozenset(b["fixes"]): _columns(b["results"]) for b in f["built"]}
        return found

    def top(self, fixes: frozenset) -> str | None:
        """The fix that, with what it requires, is exactly these fixes; None where none is."""
        return next((y for y in fixes if y in self.entries and self.closures[y] | {y} == fixes), None)

    def column(self, fixes: Iterable[str]) -> dict | None:
        """The build of exactly these fixes, or None where the file holds none."""
        fixes = frozenset(fixes)
        if not fixes:
            return {ind: {} for ind in self.base.ids}
        if fixes in self._memo:
            return self._memo[fixes]
        found = None
        top = self.top(fixes)
        if top is not None:
            below = self.column(self.closures[top])
            if below is not None:
                found = {ind: {**below[ind], **self.entries[top][ind]} for ind in self.base.ids}
        if found is None and fixes in self.built:
            found = self.built[fixes]
        if found is not None:  # never remember "none": a build may be added later
            self._memo[fixes] = found
        return found

    def covers(self, fixes: frozenset, *, built: bool = True) -> list[frozenset]:
        """The builds inside a closed set that hold two fixes or more, in the order a set's
        result looks for them: every fix with what it requires, in the order of the file, then
        (where `built`) every built set, in the order of the file; never the set itself."""
        found = [self.closures[y] | {y} for y in self.entries if y in fixes and self.closures[y]]
        if built:
            found += [b for b in self.built if b < fixes]
        return found

    def composed(self, fixes: frozenset, ind: str, *, built: bool = True) -> dict[int, tuple[float | None, bool]]:
        """A closed set's result in one indicator, at every item one of its fixes changes:
        `{item index: (result, whether it could be formed)}`. Where the fixes that change an
        item all lie in one build inside the set (`covers`), the first such build's result is
        the set's: measured, not summed. Otherwise the base plus each fix's difference against
        what it was measured against. `built=False` leaves the built sets out: the sum a built
        set is held to stands on the fixes alone."""
        touching: dict[int, list[str]] = {}
        for y in fixes:
            for k in self.entries[y][ind]:
                touching.setdefault(k, []).append(y)
        covers = self.covers(fixes, built=built)
        base, mine = self.base.values[ind], {y: self.entries[y][ind] for y in fixes}
        under = {y: self.column(self.closures[y])[ind] for y in fixes}  # what each was measured against
        out = {}
        for k, ys in touching.items():
            if len(ys) == 1:
                out[k] = (mine[ys[0]][k], True)
                continue
            here = set(ys)
            cover = next((c for c in covers if here <= c), None)
            if cover is not None:
                column = self.column(cover)[ind]
                out[k] = (column[k] if k in column else base[k], True)
            else:
                out[k] = _sum(base[k], [(mine[y][k], under[y][k] if k in under[y] else base[k]) for y in ys])
        return out


def _closures(f: Mapping) -> dict[str, frozenset]:
    """Every fix of a checked file, with every fix it requires at any depth."""
    closures: dict[str, frozenset] = {}
    for one in f["fixes"]:
        closures[one["id"]] = frozenset(one["requires"]).union(*(closures[r] for r in one["requires"]))
    return closures


def _columns(sparse: Mapping) -> dict[str, dict[int, float | None]]:
    """`{indicator: [[item index, result], ...]}` as `{indicator: {item index: result}}`."""
    return {ind: {k: v for k, v in entries} for ind, entries in sparse.items()}


def _sum(before: float | None, changes: list[tuple[float | None, float | None]]) -> tuple[float | None, bool]:
    """The base plus the effects `(result, what it was measured against)` of several fixes at
    one item, and whether a sum could be formed: a side without a result has no difference to add.

    >>> _sum(1.0, [(1.5, 1.0), (2.0, 1.0)]), _sum(1.0, [(1.5, 1.0), (None, 1.0)])
    ((2.5, True), (None, False))
    >>> _sum(None, [(1.0, None), (2.0, None)]), _sum(1.0, [(3.0, 2.0), (1.5, 1.0)])
    ((None, False), (2.5, True))
    """
    if before is None or any(a is None or b is None for a, b in changes):
        return None, False
    return before + sum(a - b for a, b in changes), True


def _level(noise: Mapping, indicator: str) -> float | None:
    return (noise["by"] or {}).get(indicator) if noise["measured"] else None


def _side(before, after) -> str:
    return "both" if before is None and after is None else "before" if before is None else "after"


def _block(base: _Base, ind: str, changed: Mapping[int, float | None], tolerance: float,
           noise: float | None, claim: Mapping | None, under: Mapping[int, float | None] | None = None) -> dict:  # fmt: skip
    """The counts of one indicator over every item: the column `under` (the base, with the
    items `under` names laid over it) against that column with `changed` laid over it, judged
    by the rule with `tolerance` and `noise`, and against `claim` where there is one. Only the
    items the two columns name are judged one by one: every other pair is the base against
    itself, counted from the base's own classes."""
    under = under or {}
    classes = dict.fromkeys(rule.CLASSES, 0)
    missing = dict.fromkeys(fileformat.MISSING_SIDES, 0)
    ways = dict.fromkeys(rule.DIRECTIONS, 0)
    bands = dict.fromkeys(rule.BANDS, 0)
    verdicts = dict.fromkeys(claims.VERDICTS, 0) if claim is not None else None
    values, floors, kinds = base.values[ind], base.floor[ind], base.kinds[ind]
    # the column before, against itself
    own = {k: rule.classify(v, v, floor=floors[k]) for k, v in under.items()}
    tally = dict(base.tally[ind])
    for k, kind in own.items():
        tally[kinds[k]] -= 1
        tally[kind] += 1

    def kind_of(k):
        return own[k] if k in own else kinds[k]

    for kind, n in tally.items():
        classes[kind] += n
    missing["both"] += tally[rule.MISSING]
    entries = []
    if claim is not None:
        entries = [(e, None if e["items"] == "*" else set(e["items"])) for e in claims.entries_for(claim, ind)]
    for k, after in changed.items():
        before, was = (under[k] if k in under else values[k]), kind_of(k)
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
        # the pairs no change touched: the column before against itself
        musts = [listed for e, listed in entries if e["expect"] == claims.MUST]
        every = any(listed is None for listed in musts)
        must_items = set() if every else {base.index[i] for listed in musts for i in listed}
        for kind in (rule.AGREES, rule.NEAR_ZERO, rule.MISSING):
            untouched = tally[kind] - sum(1 for k in changed if kind_of(k) == kind)
            if kind == rule.MISSING:
                verdicts[claims.NOT_JUDGED] += untouched
                continue
            held = untouched if every else sum(1 for k in must_items if kind_of(k) == kind and k not in changed)
            verdicts[claims.NOT_MOVED] += held
            verdicts[claims.UNCHANGED if kind == rule.AGREES else claims.NOT_JUDGED] += untouched - held
    return {"pairs": len(values), "classes": classes, "missing": missing, "directions": ways, "bands": bands,
            "verdicts": verdicts, "closer": None, "further": None}  # fmt: skip


def _fix_counts(base: _Base, one: Mapping, effect: Mapping, before: Mapping) -> dict:
    """A fix's counts: the build of what it requires against that build with its effect, with
    its own tolerance, noise and claim."""
    tol = one["tolerance"]["value"]
    return {
        ind: _block(base, ind, effect[ind], tol, _level(one["noise"], ind), one["claim"], before[ind])
        for ind in base.ids
    }


# ------------------------------------------------------------------------ a chosen set


def chosen(f: Mapping, ids: Iterable[str]) -> tuple[list[str], list[str]]:
    """The set a reader's choice makes: the chosen fixes and every fix they require, in the
    order of the file; and the fixes it added because a chosen one requires them (the page
    says so)."""
    order = {one["id"]: k for k, one in enumerate(f["fixes"])}
    ids = list(ids)
    if not ids:
        raise ValueError("a set holds at least one fix")
    for one in ids:
        if one not in order:
            raise ValueError(f"the file holds no fix {one!r}")
    if len(set(ids)) != len(ids):
        raise ValueError("a set holds each fix once")
    closures = _closures(f)
    closed = set(ids).union(*(closures[i] for i in ids))
    names = sorted(closed, key=order.__getitem__)
    return names, [x for x in names if x not in ids]


def _fixes_of(f: Mapping, names: Iterable[str]) -> list[dict]:
    wanted = set(names)
    return [one for one in f["fixes"] if one["id"] in wanted]


def held_pairs(f: Mapping, ids: Iterable[str]) -> list[dict]:
    """The listed pairs of a set: two of its fixes that can interact."""
    names = set(chosen(f, ids)[0])
    return [p for p in f["interactions"]["pairs"] if set(p["fixes"]) <= names]


def label(f: Mapping, ids: Iterable[str]) -> str:
    """Built, exact or estimated (SPEC 16.5)."""
    names = chosen(f, ids)[0]
    return _label(f, _Builds.of(f), names)


def _label(f: Mapping, builds: _Builds, names: list[str]) -> str:
    if builds.column(names) is not None:
        return BUILT
    if f["interactions"]["checked"] and not held_pairs(f, names):
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
    return max(one["tolerance"]["value"] for one in _fixes_of(f, chosen(f, ids)[0]))


def noise_of(f: Mapping, ids: Iterable[str]) -> dict[str, dict]:
    """The noise of a set, per indicator: `{value, measured, fixes}`, the value being the sum
    of the noise of the fixes whose noise was measured there, and None where none was: not
    measured is never none."""
    fixes = _fixes_of(f, chosen(f, ids)[0])
    out = {}
    for ind in (i["id"] for i in f["indicators"]):
        levels = [lv for lv in (_level(one["noise"], ind) for one in fixes) if lv is not None]
        out[ind] = {"value": sum(levels) if levels else None, "measured": len(levels), "fixes": len(fixes)}
    return out


def _changed(builds: _Builds, names: list[str]) -> tuple[dict, dict]:
    """The items a closed set changes, per indicator, with its result at each; and the items
    where no sum can be formed."""
    column = builds.column(names)
    if column is not None:
        return column, {ind: [] for ind in builds.base.ids}
    changed, cannot = {}, {}
    for ind in builds.base.ids:
        cells = builds.composed(frozenset(names), ind)
        changed[ind] = {k: v for k, (v, _) in cells.items()}
        cannot[ind] = sorted(k for k, (_, ok) in cells.items() if not ok)
    return changed, cannot


def compose(f: Mapping, ids: Iterable[str]) -> dict:
    """What a page draws for a set: its fixes in the order of the file (each with its own
    claim and counts), the fixes added because a chosen one requires them, its label, the
    listed pairs it holds and their pair terms, its tolerance and noise, and its result for
    every item, `{indicator: [result or None, ...]}` in the order of `items`. `cannot_add`
    names, per indicator, the item indices whose result is None because no sum can be formed
    there, so that it reads apart from a missing result. A set has no verdict."""
    names, added = chosen(f, ids)
    builds = _Builds.of(f)
    changed, cannot = _changed(builds, names)
    results = {}
    for ind in builds.base.ids:
        column = list(builds.base.values[ind])
        for k, value in changed[ind].items():
            column[k] = value
        results[ind] = column
    return {
        "fixes": [{k: one[k] for k in ("id", "label", "requires", "claim", "counts")} for one in _fixes_of(f, names)],
        "added": added,
        "label": _label(f, builds, names),
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
    names = chosen(f, ids)[0]
    builds = _Builds.of(f)
    changed, _ = _changed(builds, names)
    tol, noise = tolerance_of(f, names), noise_of(f, names)
    return {
        "label": _label(f, builds, names),
        "by": {ind: _block(builds.base, ind, changed[ind], tol, noise[ind]["value"], None) for ind in builds.base.ids},
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
    closures = _requirements(f, found)
    if closures is None:
        return found
    builds = _Builds(base, closures)
    built = _built_sets(f, found, base, builds)
    if built is None or not _fixes(f, found, base, builds):
        return found
    pairs = _interactions(f, found, closures, n)
    if pairs is not None:
        _built_checks(f, found, builds, built, pairs)
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


def _sparse(said, where: str, base: _Base, found: list[str], under: Mapping | None = None) -> dict | None:
    """An effect, or the results of a built set: per indicator, the items whose result is not
    the one it was measured against (`under`, laid over the base), `[[item index, result or
    null], ...]`."""
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
        against_ = (under or {}).get(ind) or {}
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
            if value == (against_[k] if k in against_ else base.values[ind][k]):
                found.append(
                    f"{where}, {ind}: item {base.items[k]!r} is written with the result it was measured "
                    "against, as if it changed"
                )
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


def _requirements(f, found) -> dict[str, frozenset] | None:
    """Every fix's id and what it requires, at any depth. A fix's requirements come before it
    in `fixes`, so that no fix requires itself through others."""
    said = f["fixes"]
    if not isinstance(said, list) or not 0 < len(said) <= MAX_FIXES:
        found.append(f"`fixes` is not a list of 1 to {MAX_FIXES} fixes")
        return None
    for one in said:
        if not isinstance(one, dict) or set(one) != FIX_KEYS or not fileformat.is_text(one["id"], fileformat.MAX_ID):
            found.append(f"a fix is not {{{', '.join(sorted(FIX_KEYS))}}}")
            return None
    every = [one["id"] for one in said]
    if len(set(every)) != len(every):
        found.append("two fixes have the same id")
        return None
    closures: dict[str, frozenset] = {}
    for one in said:
        where = f"fix {one['id']!r}"
        needs = one["requires"]
        if not (isinstance(needs, list) and all(isinstance(x, str) for x in needs)):
            found.append(f"{where}: `requires` is not a list of the ids of fixes")
            return None
        if len(set(needs)) != len(needs):
            found.append(f"{where}: requires a fix twice")
            return None
        for x in needs:
            if x == one["id"]:
                found.append(f"{where}: requires itself")
                return None
            if x not in every:
                found.append(f"{where}: requires {x!r}, and the file holds no such fix")
                return None
            if x not in closures:
                found.append(f"{where}: requires {x!r}, which comes after it: a fix's requirements come first")
                return None
        closures[one["id"]] = frozenset(needs).union(*(closures[x] for x in needs))
    return closures


def _built_sets(f, found, base: _Base, builds: _Builds) -> list | None:
    """Every built set, its shape and results; added to `builds`. None where one is wrong:
    a fix measured against a build the file does not hold cannot be checked."""
    said = f["built"]
    if not isinstance(said, list) or len(said) > MAX_BUILT:
        found.append(f"`built` is not a list of at most {MAX_BUILT} sets")
        return None
    closures = builds.closures
    out, ids, sets, before = [], set(), set(), len(found)
    for one in said:
        if not isinstance(one, dict) or set(one) != BUILT_KEYS or not fileformat.is_text(one["id"], fileformat.MAX_ID):
            found.append(f"a built set is not {{{', '.join(sorted(BUILT_KEYS))}}}")
            return None
        where = f"built set {one['id']!r}"
        if one["id"] in ids:
            found.append(f"two built sets have the id {one['id']!r}")
        ids.add(one["id"])
        if not fileformat.is_text(one["label"], fileformat.MAX_LABEL):
            found.append(f"{where}: `label` is not a short text")
        if not fileformat.is_optional(one["state"], fileformat.MAX_ID):
            found.append(f"{where}: `state` is not the id of a state, or null")
        named = one["fixes"]
        if not (isinstance(named, list) and all(isinstance(x, str) for x in named)):
            found.append(f"{where}: `fixes` is not a list of the ids of fixes")
            continue
        unknown = [x for x in named if x not in closures]
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
        lacking = sorted((x, r) for x in named for r in closures[x] - key)
        if lacking:
            found.append(f"{where}: holds {lacking[0][0]!r} without {lacking[0][1]!r}, which it requires")
            continue
        top = next((y for y in named if closures[y] | {y} == key), None)
        if top is not None:
            found.append(f"{where}: is built already: it is fix {top!r} with what it requires")
            continue
        if key in sets:
            found.append(f"{where}: holds the same fixes as another built set")
        sets.add(key)
        noise = _noise_errors(one["noise"], where, base.ids)
        if noise:
            found += noise
            continue
        results = _sparse(one["results"], f"{where}: its results", base, found)
        if results is None:
            continue
        builds.built[key] = results
        out.append((one, key, results))
    return None if len(found) > before else out


def _fixes(f, found, base: _Base, builds: _Builds) -> bool:
    """Every fix: its texts, claim, tolerance and noise; its effect, measured against the build
    of what it requires; and its counts and verdicts, worked out again."""
    for one in f["fixes"]:
        where = f"fix {one['id']!r}"
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
                return False
            if any(e["items"] is None for e in one["claim"]["scope"]):
                found.append(f"{where}: a fix's claim names its items: a page works out each item's verdict from it")
                return False
            unknown = {i for e in one["claim"]["scope"] if e["items"] != "*" for i in e["items"]} - set(base.index)
            if unknown:
                found.append(f"{where}: its claim names {len(unknown)} items the file does not hold")
                return False
        tol = one["tolerance"]
        if not (
            isinstance(tol, dict)
            and set(tol) == {"value", "basis", "note"}
            and fileformat.is_share(tol["value"])
            and tol["basis"] in fileformat.TOLERANCE_BASES
            and fileformat.is_optional(tol["note"])
        ):
            found.append(f"{where}: `tolerance` is not {{value, basis, note}}")
            return False
        noise = _noise_errors(one["noise"], where, base.ids)
        if noise:
            found += noise
            return False
        before = builds.column(builds.closures[one["id"]])
        if before is None:
            needs = ", ".join(repr(x) for x in sorted(builds.closures[one["id"]]))
            found.append(
                f"{where}: it requires {needs}, and the file holds no build of them together (a built set of "
                "exactly those fixes): its effect has nothing to be measured against"
            )
            return False
        effect = _sparse(one["effect"], f"{where}: its effect", base, found, before)
        if effect is None:
            return False
        builds.entries[one["id"]] = effect
        written = one["counts"]
        if not isinstance(written, dict) or set(written) != set(base.ids):
            found.append(f"{where}: `counts` is not one block per indicator")
            return False
        shape = [e for ind in base.ids for e in fileformat._block(written[ind], f"{where}, counts of {ind!r}", one)]
        shape += [f"{where}, counts of {ind!r}: `{key}` is null: a fix has no published results to come closer to"
                  for ind in base.ids for key in ("closer", "further") if written[ind][key] is not None]  # fmt: skip
        if shape:
            found += shape
            continue
        again = _fix_counts(base, one, effect, before)
        for ind in base.ids:
            for key, value in again[ind].items():
                if written[ind][key] != value:
                    found.append(f"{where}, counts of {ind!r}: `{key}` is not what its effect gives")
    return True


def _interactions(f, found, closures: Mapping[str, frozenset], n: int) -> dict[frozenset, dict] | None:
    """The pairs of fixes that can interact, each once, by their two ids."""
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
    pairs: dict[frozenset, dict] = {}
    for one in said["pairs"]:
        if not isinstance(one, dict) or set(one) != PAIR_KEYS:
            found.append(
                "a pair is not {fixes, kind, reach, largest}: it holds no text, so that nothing of the model "
                "goes into it"
            )
            return None
        named = one["fixes"]
        if not (isinstance(named, list) and len(named) == 2 and all(isinstance(x, str) for x in named)):
            found.append("a pair does not name two fixes")
            return None
        a, b = named
        where = f"the pair {a!r} and {b!r}"
        unknown = [x for x in named if x not in closures]
        if unknown:
            found.append(f"{where}: the file holds no fix {unknown[0]!r}")
            continue
        if a == b:
            found.append(f"{where}: names one fix twice")
            continue
        if a in closures[b] or b in closures[a]:
            found.append(f"{where}: one requires the other, so its effect is measured with the other applied")
            continue
        if one["kind"] not in PAIR_KINDS:
            found.append(f"{where}: `kind` is not one of {', '.join(PAIR_KINDS)}")
        if one["reach"] is not None and not (fileformat.is_count(one["reach"]) and 0 < one["reach"] <= n):
            found.append(f"{where}: `reach` is not a count of 1 to {n} items, or null")
        if one["largest"] is not None and not fileformat.is_share(one["largest"]):
            found.append(f"{where}: `largest` is not a share, or null where it was not measured")
        key = frozenset(named)
        if key in pairs:
            found.append(f"{where}: is listed twice")
        pairs[key] = one
    return pairs


def _built_checks(f, found, builds: _Builds, built: list, pairs: Mapping[frozenset, dict]) -> None:
    """A built set the file calls independent must be the sum of its effects; a built pair
    whose cross term the file measured must lie within it."""
    if not f["interactions"]["checked"]:
        return
    by_id = {one["id"]: one for one in f["fixes"]}
    for one, key, results in built:
        where = f"built set {one['id']!r}"
        held = [p for p in pairs if p <= key]
        if not held:
            found += _disagreements(builds, where, key, by_id, one, results)
        elif held == [key] and pairs[key]["largest"] is not None:
            found += _disagreements(builds, where, key, by_id, one, results, pairs[key]["largest"])


#: How many disagreements of one built set are named before the rest are counted.
NAMED = 5


def _number(value: float | None) -> str:
    """A result in an error, to ten significant digits: the sum of 1.0006 and 1.0007 over
    1.0 reads 1.0013, not 1.0012999999999999.

    >>> _number(1.0012999999999999), _number(None), _number(-2.5e-12)
    ('1.0013', 'null', '-2.5e-12')
    """
    return "null" if value is None else f"{value:.10g}"


def _tolerance_and_noise(fixes: list[Mapping], ind: str, own: Mapping | None = None) -> tuple[float, float | None]:
    """The tolerance of a set (the largest of its fixes') and its noise (the sum of theirs,
    and of `own` where a built set's own noise is measured); None where none is measured."""
    noises = [x["noise"] for x in fixes] + ([own] if own else [])
    levels = [lv for lv in (_level(x, ind) for x in noises) if lv is not None]
    return max(x["tolerance"]["value"] for x in fixes), (sum(levels) if levels else None)


def _disagreements(builds: _Builds, where: str, key: frozenset, by_id: Mapping, one: Mapping, results: Mapping,
                   largest: float | None = None) -> list[str]:  # fmt: skip
    """Where a built set is further from the sum of its effects than the file says, by the
    rule, with the set's tolerance and the sum of its fixes' noise and its own."""
    base = builds.base
    fixes = [by_id[x] for x in sorted(key)]
    found, more = [], 0
    for ind in base.ids:
        tol, level = _tolerance_and_noise(fixes, ind, one["noise"])
        if largest is not None:
            tol = max(tol, largest)
        cells = builds.composed(key, ind, built=False)
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
                    f"{where}, item {base.items[k]!r}, {ind}: built {_number(got)}, the sum of its effects is "
                    f"{_number(summed)} "
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
    where it is not; so is a built set that names a state of the chain."""
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
    for one in f["built"]:
        later = one["state"] in states and states.index(one["state"]) > states.index(of["base"])
        if one["state"] is not None and not later:
            found.append(f"built set {one['id']!r}: `state` {one['state']!r} is not a state of the chain after the base")
    if found:
        return found
    ids = [i["id"] for i in data["indicators"]]
    at, nstates = states.index(of["base"]), len(states)
    if full is not None:
        m = len(full["items"])
        if [list(r) for r in f["items"][:m]] != [list(r) for r in full["items"]]:
            return ["its items are not the matrix's, in the matrix's order, before any item a fix adds"]
        for x, ind in enumerate(ids):
            if [_cell(full, k, x, at, nstates) for k in range(m)] != f["base"][ind][:m]:
                found.append(f"the base results in {ind!r} are not the matrix's results of state {of['base']!r}")
        found += _added_items(f, m)
        found += _states(f, data, lambda k, x, s: _cell(full, k, x, states.index(s), nstates) if k < m else None,
                         range(len(f["items"])))  # fmt: skip
        return found
    if len(f["items"]) < data["items_count"]["all"]:
        found.append(f"it holds {len(f['items'])} items, and the diagnostics file counts {data['items_count']['all']}")
    index = {row[0]: k for k, row in enumerate(f["items"])}
    listed = {}
    for item in data["items"]:
        k = index.get(item["id"])
        if k is None:
            found.append(f"the listed item {item['id']!r} is not in the fixes file")
            continue
        listed[k] = item
        if f["items"][k][1:] != [item["name"], item["place"], item["group"], item["unit"]]:
            found.append(f"item {item['id']!r}: its name, place, group or unit differ from the diagnostics file")
        for ind in ids:
            if item["values"][ind][at] != f["base"][ind][k]:
                found.append(f"item {item['id']!r}, {ind}: the base result is not the diagnostics file's")
    found += _states(f, data, lambda k, x, s: listed[k]["values"][ids[x]][states.index(s)], sorted(listed))
    return found


def _added_items(f: Mapping, m: int) -> list[str]:
    """The items after the matrix's: a fix brings them, so the base has no result for them and
    a fix or a built set gives one."""
    found = []
    given = set()
    for one in [*f["fixes"], *f["built"]]:
        for entries in (one["effect"] if "effect" in one else one["results"]).values():
            given.update(k for k, v in entries if k >= m and v is not None)
    for k in range(m, len(f["items"])):
        name = f["items"][k][0]
        if any(f["base"][ind][k] is not None for ind in f["base"]):
            found.append(f"item {name!r} is not in the matrix, and the base has a result for it")
        elif k not in given:
            found.append(f"item {name!r} is in no state of the chain, and no fix gives it a result")
    return found


def _states(f: Mapping, data: Mapping, cell, items) -> list[str]:
    """A built set that names a state of the chain is two builds of one thing: by the rule,
    with the set's tolerance and the sum of its fixes' noise and its own."""
    found = []
    by_id = {one["id"]: one for one in f["fixes"]}
    floors = _Base(f).floor
    for one in f["built"]:
        if one["state"] is None:
            continue
        where = f"built set {one['id']!r}"
        fixes = [by_id[x] for x in one["fixes"]]
        results = _columns(one["results"])
        named = 0
        for x, ind in enumerate(f["base"]):
            tol, level = _tolerance_and_noise(fixes, ind, one["noise"])
            for k in items:
                got = results[ind].get(k, f["base"][ind][k])
                there = cell(k, x, one["state"])
                kind = rule.classify(there, got, floor=floors[ind][k], tolerance=tol, noise=level)
                if kind in claims.STILL or (kind == rule.MISSING and there is None and got is None):
                    continue
                named += 1
                if named <= NAMED:
                    found.append(
                        f"{where}, item {f['items'][k][0]!r}, {ind}: built {_number(got)}, and state "
                        f"{one['state']!r} of the chain, which it says it is, holds {_number(there)} ({kind})"
                    )
        if named > NAMED:
            found.append(f"{where}: and {named - NAMED} more pairs where it is not state {one['state']!r}")
    return found
