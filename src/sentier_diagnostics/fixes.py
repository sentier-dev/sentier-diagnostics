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
of its fixes'. Noise belongs to a build, as it belongs to a state of a chain (SPEC 5.3): the
base's is that state's (none where the base is the published results, which are exact), a
fix's is that of the build with it, a built set's that of its build. A fix is judged with the
sum of the noise of its build and of the one it was measured against. A set is judged item by
item with the noise of the builds the item's result stands on, never with that of a fix that
does not touch it: a build's result, with that build's and the base's; a sum, with each
summed fix's build and the one it was measured against. It says at how many of those builds
the noise is known, never reading not measured as none.

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
from collections.abc import Iterable, Mapping, Sequence
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
#: The noise of the base, when the base is a build; left out where it is the published
#: results, which are exact (SPEC 5.3).
OF_OPTIONAL = {"base_noise"}
#: The rule of the diagnostics file, without the chain's own total tolerance.
RULE_KEYS = fileformat.RULE_KEYS - {"total_tolerance"}
FIX_KEYS = {"id", "label", "about", "kind", "explained", "link", "requires", "claim", "tolerance", "noise",
            "effect", "counts"}  # fmt: skip
INTERACTION_KEYS = {"checked", "method", "by", "pairs"}
PAIR_KEYS = {"fixes", "kind", "reach", "largest"}
BUILT_KEYS = {"id", "label", "fixes", "state", "results", "noise"}

#: Where two changes of h = c·B·A⁻¹·f meet, so that their joint result is not the sum of
#: their effects (SPEC 16.3). Two changes to different factors, or to different entries of
#: B, add up exactly and are never a pair. In the order of precedence: a pair that meets in
#: several ways is the first that applies.
SAME_ENTRY = "same entry"  # both change one number of A, B or c: two edits of one number do not add
TECHNOSPHERE = "technosphere"  # both change A, and an item's supply chain reaches both
TECHNOSPHERE_AND_EMISSION = "technosphere and emission"  # A, and an amount of B on a chain the A change shifts
TECHNOSPHERE_AND_FACTOR = "technosphere and factor"  # A, and the factor of a flow the A change shifts
EMISSION_AND_FACTOR = "emission and factor"  # an amount of a flow, and that flow's factor
PAIR_KINDS = (SAME_ENTRY, TECHNOSPHERE, TECHNOSPHERE_AND_EMISSION, TECHNOSPHERE_AND_FACTOR, EMISSION_AND_FACTOR)

#: A pair's `largest` where no tolerance makes its build agree with the sum of its effects:
#: at some item the two lie on two sides of zero, one is zero, or one has no result (SPEC
#: 16.6). Not null, which says the size was not measured.
NO_SIZE = "no size"

MAX_FIXES, MAX_BUILT = 1000, 500
MAX_ITEMS, MAX_BYTES = matrix.MAX_ITEMS, matrix.MAX_BYTES

BUILT, EXACT, ESTIMATED = "built", "exact", "estimated"
#: What a set's result at an item stands on (`_Builds.composed`): one build, or a sum of fixes.
BUILD, SUM = "build", "sum"
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
    """One fix, as `build` takes it: what a step has (`chain.step`), the fixes it needs applied
    first, and the noise of the build with it (`chain.noise`), which belongs to that build as a
    state's noise belongs to the state."""
    one = chain.step(id, label, kind=kind, explained=explained, about=about, link=link, claim=claim,
                     tolerance=tolerance)  # fmt: skip
    return {**one, "requires": list(requires), "noise": noise}


def pair(a: str, b: str, kind: str, *, reach: int | None = None, largest: float | str | None = None) -> dict:
    """Two fixes that can interact: `kind` is the first of `PAIR_KINDS` that applies, `reach`
    how many items the cross term can change, counted on the build with both; `largest` its
    measured size (`size_of`), or `NO_SIZE`; None where not counted or not measured."""
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


def _rule_of(data: Mapping, added: Iterable) -> dict:
    """The rule of a fixes file: its diagnostics file's, without the chain's total tolerance,
    and a floor for every unit only an added item has: 0, from nothing, as the chain gives a
    unit its first state holds no result in (an added item is in no state of it)."""
    out = {k: data["rule"][k] for k in sorted(RULE_KEYS)}
    known = {one["unit"] for one in data["rule"]["floors"]}
    new = sorted({row[4] for row in added} - known, key=lambda u: (u is None, u or ""))
    out["floors"] = [*out["floors"], *({"indicator": i["id"], "unit": unit, "value": 0.0, "basis": "none", "n": 0}
                                       for i in data["indicators"] for unit in new)]  # fmt: skip
    return out


def _expanded(full: Mapping, nstates: int) -> list[list]:
    """The results of a matrix, item by item, a result written as the one before it
    (`matrix.SAME`) written out again."""
    return [matrix.expand(row, nstates) if matrix.SAME in row else row for row in full["values"]]


def _results_of(rows: list[list], x: int, at: int, nstates: int) -> list:
    """The results of expanded matrix rows in indicator `x` and state `at`, item by item."""
    col = x * nstates + at
    return [row[col] for row in rows]


def _base_noise(data: Mapping, at: int) -> dict | None:
    """The noise of the state at place `at` of a checked diagnostics file: None where it is the
    published results, which are exact. A file whose states carry no noise is refused: it never
    says which state its noise was measured on."""
    if not fileformat.states_carry_noise(data):
        raise ValueError(NO_STATE_NOISE)
    state = data["states"][at]
    return None if state["kind"] == "published" else state["noise"]


#: Why a fixes file needs the noise of the chain's states.
NO_STATE_NOISE = (
    "the diagnostics file says no noise of its states: it was made before noise belonged to a "
    "state (SPEC 5.3), so the base's noise cannot be read from it; make it again"
)


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
      does not hold; the base has no result for them. An added item in a unit no item of the
      chain has gets the floor the chain gives a unit with no results: 0, from nothing.
    - `file`: the name of the diagnostics file beside it.

    The base's noise is its state's (none where it is the published results); a fix's and a
    built set's noise are those of their builds.
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
    base_noise = _base_noise(data, at)
    expanded = _expanded(full, nstates)
    base_values = {ind: _results_of(expanded, x, at, nstates) + [None] * (len(rows) - m) for x, ind in enumerate(ids)}
    known = [one["id"] for one in fixes]
    unknown = set(results) - set(known)
    if unknown:
        raise ValueError(f"results of fixes that are not given: {sorted(unknown)}")
    of = {"file": file, "title": data["title"], "base": base}
    if base_noise is not None:
        of["base_noise"] = base_noise
    f = {
        "format": FORMAT,
        "of": of,
        "title": title,
        "about": about,
        "item": dict(data["item"]),
        **({"indicator": dict(data["indicator"])} if data.get("indicator") else {}),
        "indicators": [dict(i) for i in data["indicators"]],
        "rule": _rule_of(data, rows[m:]),
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
    builds = _Builds(ctx, closures, base_noise)
    nothing = {ind: {} for ind in ids}
    for one in built:
        results_of = sparse(one["results"], f"built set {one['id']!r}", nothing)
        builds.built[frozenset(one["fixes"])] = _columns(results_of)
        builds.noise[frozenset(one["fixes"])] = one.get("noise") or chain.noise()
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
        builds.noise[one["id"]] = made["noise"]
        made["counts"] = _fix_counts(builds, made, builds.entries[one["id"]], before)
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
    build of its requirements) and every built set; and the noise of each, as an end of a
    comparison (`end`)."""

    def __init__(self, base: _Base, closures: Mapping[str, frozenset], base_noise: Mapping | None = None):
        self.base = base
        self.closures = closures  # fix id: every fix it requires, at any depth
        self.entries: dict[str, dict] = {}  # fix id: its written results, by indicator
        self.built: dict[frozenset, dict] = {}  # the fixes of a built set: its results
        self.noise: dict[str | frozenset, Mapping] = {}  # a fix's id, or a built set's fixes: its noise
        # the base as an end: the published results are exact
        self.base_end = {"kind": "published"} if base_noise is None else {"kind": "build", "noise": base_noise}
        self._memo: dict[frozenset, dict] = {}

    @classmethod
    def of(cls, f: Mapping) -> _Builds:
        found = cls(_Base(f), _closures(f), f["of"].get("base_noise"))
        found.entries = {one["id"]: _columns(one["effect"]) for one in f["fixes"]}
        found.built = {frozenset(b["fixes"]): _columns(b["results"]) for b in f["built"]}
        found.noise = {one["id"]: one["noise"] for one in f["fixes"]}
        found.noise.update((frozenset(b["fixes"]), b["noise"]) for b in f["built"])
        return found

    def end(self, fixes: Iterable[str]) -> tuple[str | frozenset, Mapping] | None:
        """The build of exactly these fixes that `column` gives, as an end of a comparison:
        `(what names it, {kind, noise})`, the base being exact where it is the published
        results; None where the file holds no such build."""
        fixes = frozenset(fixes)
        if not fixes:
            return "", self.base_end
        top = self.top(fixes)
        if top is not None and self.column(self.closures[top]) is not None:
            return top, {"kind": "build", "noise": self.noise[top]}
        if fixes in self.built:
            return fixes, {"kind": "build", "noise": self.noise[fixes]}
        return None

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

    def composed(self, fixes: frozenset, ind: str, *, built: bool = True,
                 how: dict | None = None) -> dict[int, tuple[float | None, bool]]:  # fmt: skip
        """A closed set's result in one indicator, at every item one of its fixes changes:
        `{item index: (result, whether it could be formed)}`. Where one fix changes an item,
        its build's result is the set's; where several do and all lie in one build inside the
        set (`covers`), the first such build's: measured, not summed. Otherwise the base plus
        each fix's difference against what it was measured against. `built=False` leaves the
        built sets out: the sum a built set is held to stands on the fixes alone. `how` gathers
        what each result stands on, `{item index: ("build", its fixes) or ("sum", the fixes
        summed)}`, for its noise (`_item_ends`)."""
        touching: dict[int, list[str]] = {}
        for y in (y for y in self.closures if y in fixes):  # in the order of the file: one sum, one float
            for k in self.entries[y][ind]:
                touching.setdefault(k, []).append(y)
        covers = self.covers(fixes, built=built)
        base, mine = self.base.values[ind], {y: self.entries[y][ind] for y in fixes}
        under = {y: self.column(self.closures[y])[ind] for y in fixes}  # what each was measured against
        out = {}
        for k, ys in touching.items():
            if len(ys) == 1:
                out[k] = (mine[ys[0]][k], True)
                stands = (BUILD, self.closures[ys[0]] | {ys[0]})
            else:
                here = set(ys)
                cover = next((c for c in covers if here <= c), None)
                if cover is not None:
                    column = self.column(cover)[ind]
                    out[k] = (column[k] if k in column else base[k], True)
                    stands = (BUILD, cover)
                else:
                    out[k] = _sum(base[k], [(mine[y][k], under[y][k] if k in under[y] else base[k]) for y in ys])
                    stands = (SUM, tuple(ys))
            if how is not None:
                how[k] = stands
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


def _level(ends: Iterable[Mapping], indicator: str) -> float | None:
    """The noise a comparison is judged with in one indicator: the sum of the noise of its ends
    (`{kind, noise}`, SPEC 5.3), each counted as often as it enters it. The published results
    are exact and add nothing; an end that did not measure the indicator adds nothing either;
    None where no end measured it. For two ends it is `fileformat.noise_of_states`, bit for bit.

    >>> built = lambda by: {"kind": "build", "noise": {"measured": by is not None, "between": by and ["x", "y"], "by": by, "note": None}}
    >>> _level([built({"a": 1e-9}), built({"a": 3e-9})], "a"), _level([{"kind": "published"}, built(None)], "a")
    (4e-09, None)
    >>> _level([built({"a": 0.25})] * 3 + [built({"b": 1.0})], "a")
    0.75
    """
    level = None
    for end in ends:
        if end["kind"] == "published":
            continue
        said = end["noise"]
        if said["measured"] and indicator in said["by"]:
            level = (0.0 if level is None else level) + said["by"][indicator]
    return level


def _known(end: Mapping, indicator: str) -> bool:
    """Whether the noise of an end is known in one indicator: the published results (exact), or
    a build that measured it (`fileformat.ends_known`)."""
    return end["kind"] == "published" or (end["noise"]["measured"] and indicator in end["noise"]["by"])


def _built(noise: Mapping) -> dict:
    return {"kind": "build", "noise": noise}


def _side(before, after) -> str:
    return "both" if before is None and after is None else "before" if before is None else "after"


def _block(base: _Base, ind: str, changed: Mapping[int, float | None], tolerance: float,
           noise: float | Mapping[int, float | None] | None, claim: Mapping | None,
           under: Mapping[int, float | None] | None = None) -> dict:  # fmt: skip
    """The counts of one indicator over every item: the column `under` (the base, with the
    items `under` names laid over it) against that column with `changed` laid over it, judged
    by the rule with `tolerance` and `noise` (one for every item, or one per changed item), and
    against `claim` where there is one. Only the
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
        level = noise.get(k) if isinstance(noise, Mapping) else noise
        kind, way, band = rule.judge(before, after, floor=floors[k], tolerance=tolerance, noise=level)
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
            held = untouched if every else sum(1 for k in must_items if kind_of(k) == kind and k not in changed)
            # under a `must`: one that agrees did not move, one missing or near zero is left open
            verdicts[claims.NOT_MOVED if kind == rule.AGREES else claims.OPEN] += held
            verdicts[claims.UNCHANGED if kind == rule.AGREES else claims.NOT_JUDGED] += untouched - held
    return {"pairs": len(values), "classes": classes, "missing": missing, "directions": ways, "bands": bands,
            "verdicts": verdicts, "closer": None, "further": None}  # fmt: skip


def _fix_counts(builds: _Builds, one: Mapping, effect: Mapping, before: Mapping) -> dict:
    """A fix's counts: the build of what it requires against that build with its effect, with
    its own tolerance and claim, and the noise of those two builds."""
    tol = one["tolerance"]["value"]
    ends = [builds.end(builds.closures[one["id"]])[1], _built(one["noise"])]
    return {
        ind: _block(builds.base, ind, effect[ind], tol, _level(ends, ind), one["claim"], before[ind])
        for ind in builds.base.ids
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
    no_size, pairs}`, the value being the sum of the sizes of the listed pairs it holds; None
    where some were not measured (a pair not measured is never a pair of size 0) or have no
    size (`NO_SIZE`), which the counts tell apart."""
    held = held_pairs(f, ids)
    said = [p["largest"] for p in held if p["largest"] is not None]
    sizes = [x for x in said if x != NO_SIZE]
    value = sum(sizes) if len(sizes) == len(held) else None
    return {"value": value, "measured": len(said), "no_size": len(said) - len(sizes), "pairs": len(held)}


def size_of(summed: Sequence, built: Sequence, floor: Sequence) -> float | str:
    """The size of a pair's cross term in one indicator (SPEC 16.6), item by item: the
    smallest tolerance under which its build agrees with the sum of its effects, by the rule.
    That is the largest relative difference of the two (`rule.relative_difference`) over the
    items the rule does not call near zero on both sides; `NO_SIZE` where no tolerance is
    enough: an item where the two lie on two sides of zero, one is zero, or one has no
    result. A pair's size is the largest over the indicators.

    >>> size_of([1.5, 2.0], [2.0, 2.0], [0.01, 0.01])
    0.25
    >>> size_of([1.5], [-0.1], [0.01]), size_of([-0.5], [0.0], [0.01]), size_of([1e-9], [-1e-9], [0.01])
    ('no size', 'no size', 0.0)
    """
    largest = 0.0
    for s, b, fl in zip(summed, built, floor):
        if s is None and b is None:
            continue
        if s is None or b is None:
            return NO_SIZE
        if abs(s) <= fl and abs(b) <= fl:
            continue
        if not ((s > 0 and b > 0) or (s < 0 and b < 0)):
            return NO_SIZE
        largest = max(largest, rule.relative_difference(s, b))
    return largest


def tolerance_of(f: Mapping, ids: Iterable[str]) -> float:
    """The tolerance of a set: the largest of its fixes'."""
    return max(one["tolerance"]["value"] for one in _fixes_of(f, chosen(f, ids)[0]))


def noise_of(f: Mapping, ids: Iterable[str]) -> dict[str, dict]:
    """The noise of a set against the base, per indicator (SPEC 16.5): `{value, known,
    builds}`. Each item it changes is judged with the noise of the builds its result stands on
    (`_against_base`), never with that of a fix that does not touch it; `value` is the largest
    of those, `builds` counts the builds they stand on and `known` those whose noise is known
    there (the published results are exact). None where none measured it: not measured is never
    none. A set that changes nothing in an indicator stands on no build there."""
    names = chosen(f, ids)[0]
    builds = _Builds.of(f)
    return _set_noise(builds, _changed(builds, names)[2])[0]


def _sum_side(builds: _Builds, fixes: Iterable[str]) -> list[tuple]:
    """The builds a sum over these fixes stands on, `(name, end)`: each fix's build and the one
    it was measured against (the base, for a fix that requires nothing)."""
    return [end for y in fixes for end in (builds.end(builds.closures[y]), (y, _built(builds.noise[y])))]


def _against_base(builds: _Builds, stands: tuple) -> list[tuple]:
    """The builds a set's result at one item and the base result there stand on, `(name, end)`:
    the build the result is taken from, and the base; for a sum, the builds of the sum alone,
    since the base it starts from is the base it is compared with, and cancels."""
    kind, what = stands
    if kind == BUILD:
        return [("", builds.base_end), builds.end(what)]
    return _sum_side(builds, what)


def _set_noise(builds: _Builds, how: Mapping[str, Mapping[int, tuple]]) -> tuple[dict, dict]:
    """A set's noise per indicator, `{value, known, builds}`, and the noise each item it changes
    is judged with, `{indicator: {item index: noise or None}}`."""
    summary, per_item = {}, {}
    for ind in builds.base.ids:
        levels, every, seen = {}, {}, {}
        for k, stands in how[ind].items():
            if stands not in seen:  # most items share what they stand on: one fix's build
                ends = _against_base(builds, stands)
                seen[stands] = _level([end for _, end in ends], ind)
                every.update(ends)
            levels[k] = seen[stands]
        found = [lv for lv in levels.values() if lv is not None]
        summary[ind] = {"value": max(found) if found else None,
                        "known": sum(_known(end, ind) for end in every.values()), "builds": len(every)}  # fmt: skip
        per_item[ind] = levels
    return summary, per_item


def _changed(builds: _Builds, names: list[str]) -> tuple[dict, dict, dict]:
    """The items a closed set changes, per indicator, with its result at each; the items
    where no sum can be formed; and what each result stands on (`_Builds.composed`)."""
    column = builds.column(names)
    if column is not None:
        whole = frozenset(names)
        return (column, {ind: [] for ind in builds.base.ids},
                {ind: dict.fromkeys(column[ind], (BUILD, whole)) for ind in builds.base.ids})  # fmt: skip
    changed, cannot, how = {}, {}, {}
    for ind in builds.base.ids:
        how[ind] = {}
        cells = builds.composed(frozenset(names), ind, how=how[ind])
        changed[ind] = {k: v for k, (v, _) in cells.items()}
        cannot[ind] = sorted(k for k, (_, ok) in cells.items() if not ok)
    return changed, cannot, how


def compose(f: Mapping, ids: Iterable[str]) -> dict:
    """What a page draws for a set: its fixes in the order of the file (each with its own
    claim and counts), the fixes added because a chosen one requires them, its label, the
    listed pairs it holds and their pair terms, its tolerance and noise (`noise_of`), the noise
    each item it changes is judged with (`item_noise`, `{indicator: {item index: noise or
    None}}`), and its result for every item, `{indicator: [result or None, ...]}` in the order
    of `items`. `cannot_add`
    names, per indicator, the item indices whose result is None because no sum can be formed
    there, so that it reads apart from a missing result. A set has no verdict."""
    names, added = chosen(f, ids)
    builds = _Builds.of(f)
    changed, cannot, how = _changed(builds, names)
    noise, item_noise = _set_noise(builds, how)
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
        "noise": noise,
        "item_noise": item_noise,
        "results": results,
        "cannot_add": cannot,
    }


def counts(f: Mapping, ids: Iterable[str]) -> dict:
    """The counts of a set against the base, per indicator, with its label beside them: an
    estimated set's counts are estimates ("estimated: 153 would differ"). No verdicts."""
    names = chosen(f, ids)[0]
    builds = _Builds.of(f)
    changed, _, how = _changed(builds, names)
    tol, item_noise = tolerance_of(f, names), _set_noise(builds, how)[1]
    return {
        "label": _label(f, builds, names),
        "by": {ind: _block(builds.base, ind, changed[ind], tol, item_noise[ind], None) for ind in builds.base.ids},
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
        and OF_KEYS <= set(of) <= OF_KEYS | OF_OPTIONAL
        and isinstance(of["file"], str)
        and fileformat.FILE_NAME.fullmatch(of["file"])
        and fileformat.is_text(of["title"], 120)
        and fileformat.is_text(of["base"], fileformat.MAX_ID)
    ):
        found.append(
            "`of` is not {file, title, base}, with `base_noise` where the base is a build: a file name, that "
            "file's title and a state's id"
        )
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
    if isinstance(of, dict) and "base_noise" in of:
        found += fileformat.noise_errors(of["base_noise"], "`of.base_noise`", indicators)
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
    builds = _Builds(base, closures, f["of"].get("base_noise"))
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
        noise = fileformat.noise_errors(one["noise"], where, base.ids)
        if noise:
            found += noise
            continue
        results = _sparse(one["results"], f"{where}: its results", base, found)
        if results is None:
            continue
        builds.built[key] = results
        builds.noise[key] = one["noise"]
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
        noise = fileformat.noise_errors(one["noise"], where, base.ids)
        if noise:
            found += noise
            return False
        builds.noise[one["id"]] = one["noise"]
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
        again = _fix_counts(builds, one, effect, before)
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
        if one["largest"] not in (None, NO_SIZE) and not fileformat.is_share(one["largest"]):
            found.append(
                f"{where}: `largest` is not a share, {NO_SIZE!r} where no tolerance is enough, or null where it was "
                "not measured"
            )
        key = frozenset(named)
        if key in pairs:
            found.append(f"{where}: is listed twice")
        pairs[key] = one
    return pairs


def _built_checks(f, found, builds: _Builds, built: list, pairs: Mapping[frozenset, dict]) -> None:
    """A built set the file calls independent must be the sum of its effects; a built pair
    whose cross term the file measured must lie within it; a pair with no size must be built,
    and its build must have none."""
    if not f["interactions"]["checked"]:
        return
    by_id = {one["id"]: one for one in f["fixes"]}
    for key, one in pairs.items():
        a, b = one["fixes"]
        if one["largest"] == NO_SIZE and builds.column(key | builds.closures[a] | builds.closures[b]) is None:
            found.append(
                f"the pair {a!r} and {b!r}: has no size, so no set holding it can be drawn from its sum: the "
                "file holds a build of the two with what they require (a built set)"
            )
    for one, key, results in built:
        where = f"built set {one['id']!r}"
        held = [p for p in pairs if p <= key]
        if not held:
            found += _disagreements(builds, where, key, by_id, one, results)
        elif held == [key] and pairs[key]["largest"] == NO_SIZE:
            found += _sized(builds, where, key, results)
        elif held == [key] and pairs[key]["largest"] is not None:
            found += _disagreements(builds, where, key, by_id, one, results, pairs[key]["largest"])


def _sized(builds: _Builds, where: str, key: frozenset, results: Mapping) -> list[str]:
    """A built pair the file says has no size must have none: where some tolerance makes its
    build agree with its sum, that tolerance is its size, and the file says it."""
    base = builds.base
    sizes = []
    for ind in base.ids:
        cells, values = builds.composed(key, ind, built=False), base.values[ind]
        items = sorted(set(cells) | set(results[ind]))
        summed = [cells[k][0] if k in cells else values[k] for k in items]
        if not all(cells[k][1] for k in items if k in cells):
            return []  # no sum at some item: nothing to measure against
        size = size_of(summed, [results[ind].get(k, values[k]) for k in items], [base.floor[ind][k] for k in items])
        if size == NO_SIZE:
            return []
        sizes.append(size)
    size = _number(max(sizes))
    return [f"{where}: the file says its pair has no size, and its build lies within {size} of the sum of its effects"]


#: How many disagreements of one built set are named before the rest are counted.
NAMED = 5


def _number(value: float | None) -> str:
    """A result in an error, to ten significant digits: the sum of 1.0006 and 1.0007 over
    1.0 reads 1.0013, not 1.0012999999999999.

    >>> _number(1.0012999999999999), _number(None), _number(-2.5e-12)
    ('1.0013', 'null', '-2.5e-12')
    """
    return "null" if value is None else f"{value:.10g}"


def _disagreements(builds: _Builds, where: str, key: frozenset, by_id: Mapping, one: Mapping, results: Mapping,
                   largest: float | None = None) -> list[str]:  # fmt: skip
    """Where a built set is further from the sum of its effects than the file says, by the
    rule, with the largest tolerance of its fixes and, item by item, the noise of the builds
    the two sides stand on: the built set's, and the build the sum takes the item from, or the
    base with each fix's build and what it was measured against where it adds the fixes that
    touch the item, or the base alone where none does."""
    base = builds.base
    own, from_base = _built(one["noise"]), [builds.base_end]
    tol = max(by_id[x]["tolerance"]["value"] for x in key)
    if largest is not None:
        tol = max(tol, largest)
    found, more = [], 0
    for ind in base.ids:
        how: dict[int, tuple] = {}
        cells = builds.composed(key, ind, built=False, how=how)
        for k in sorted(set(cells) | set(results[ind])):
            before = base.values[ind][k]
            summed, ok = cells.get(k, (before, True))
            if not ok:
                continue  # no sum to hold the build to
            got = results[ind].get(k, before)
            if k not in how:
                side = from_base
            elif how[k][0] == BUILD:
                side = [builds.end(how[k][1])[1]]
            else:
                side = from_base + [end for _, end in _sum_side(builds, how[k][1])]
            level = _level([own, *side], ind)
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
    if not fileformat.states_carry_noise(data):
        return [*found, NO_STATE_NOISE]
    base_state = data["states"][states.index(of["base"])]
    if base_state["kind"] == "published":
        if "base_noise" in of:
            found.append("the base is the published results, which are exact: `of.base_noise` is left out")
    elif "base_noise" not in of:
        found.append("the base is a build: `of.base_noise` is its noise, as the diagnostics file says it")
    elif of["base_noise"] != base_state["noise"]:
        found.append(f"`of.base_noise` is not the noise the diagnostics file gives state {of['base']!r}")
    if f["indicators"] != data["indicators"]:
        found.append("its indicators differ from the diagnostics file's")
    if f["item"] != data["item"] or f.get("indicator") != data.get("indicator"):
        found.append("its words for an item or an indicator differ from the diagnostics file's")
    m = len(full["items"]) if full is not None else data["items_count"]["all"]
    if f["rule"] != _rule_of(data, f["items"][m:]):
        found.append(
            "its floors differ from the diagnostics file's, with a floor of 0 from nothing for each unit only "
            "an added item has"
        )
    for one in f["built"]:
        later = one["state"] in states and states.index(one["state"]) > states.index(of["base"])
        if one["state"] is not None and not later:
            found.append(f"built set {one['id']!r}: `state` {one['state']!r} is not a state of the chain after the base")
    if found:
        return found
    ids = [i["id"] for i in data["indicators"]]
    at, nstates = states.index(of["base"]), len(states)
    if full is not None:
        if [list(r) for r in f["items"][:m]] != [list(r) for r in full["items"]]:
            return ["its items are not the matrix's, in the matrix's order, before any item a fix adds"]
        expanded = _expanded(full, nstates)
        for x, ind in enumerate(ids):
            if _results_of(expanded, x, at, nstates) != f["base"][ind][:m]:
                found.append(f"the base results in {ind!r} are not the matrix's results of state {of['base']!r}")
        found += _added_items(f, m)
        found += _states(f, data, lambda k, x, s: expanded[k][x * nstates + states.index(s)] if k < m else None,
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
    with the largest tolerance of its fixes and the noise of the two builds, its own and the
    state's (none where that is the published results)."""
    found = []
    by_id = {one["id"]: one for one in f["fixes"]}
    floors = _Base(f).floor
    of_state = {s["id"]: s for s in data["states"]}
    for one in f["built"]:
        if one["state"] is None:
            continue
        where = f"built set {one['id']!r}"
        state = of_state[one["state"]]
        ends = [_built(one["noise"]), state if state["kind"] == "published" else _built(state["noise"])]
        tol = max(by_id[x]["tolerance"]["value"] for x in one["fixes"])
        results = _columns(one["results"])
        named = 0
        for x, ind in enumerate(f["base"]):
            level = _level(ends, ind)
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
