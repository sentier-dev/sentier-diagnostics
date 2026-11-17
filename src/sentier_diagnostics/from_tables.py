"""Build a diagnostics file from CSV tables and a short JSON description, without Python.

    {
      "title": "Our database, from the published results to main",
      "item": {"one": "dataset", "many": "datasets"},
      "indicator": {"one": "impact category", "many": "impact categories"},
      "indicators": [{"id": "ef31:climate", "name": "Climate change", "short": "Climate",
                      "unit": "kg CO2 eq"}],
      "items": "items.csv",
      "states": [
        {"id": "published", "label": "Published", "kind": "published", "results": "published.csv"},
        {"id": "repro", "label": "Recomputed", "results": "repro.csv"}
      ],
      "steps": [
        {"id": "step-0", "label": "Reproduction", "kind": "reproduction",
         "tolerance": {"value": 5e-4, "basis": "published rounding"},
         "claim": {"text": "Nothing moves.", "by": {"kind": "code", "name": "rule"}, "scope": []}}
      ],
      "listed": 200,
      "tier": "items"
    }

A local file of items may also name its matrix of every item (`"matrix": "matrix.json"`,
with `"audience": "local"`): `build_with_matrix` then gives it, and `sentier-diagnostics
build` writes it beside the file.

Paths are relative to the description. A built state's `noise` is what two builds of it
differ by: `{"states": ["a", "b"]}` (two states of this chain that are builds of it) or
`{"tables": [{"label": "...", "results": "a.csv"}, {"label": "...", "results": "b.csv"}]}`.
It is taken over the results beyond the floors of the chain's first state. A step takes no
noise of its own: it is compared with the sum of the noise of its two states, and the
published results are exact (SPEC section 5.3). A scope entry without `expect` says what
may move (`"may"`), as SPEC section 6 says.
"""

from __future__ import annotations

import math
from pathlib import Path

from . import chain, claims, fileformat, tables

KEYS = {"title", "about", "item", "indicator", "indicators", "items", "states", "steps", "listed", "tier", "audience",
        "claim_lists", "explanations", "notes", "floor_factor", "matrix"}  # fmt: skip


def _origin(said):
    if said is None:
        return None
    return claims.origin(said.get("kind"), said.get("name"), model=said.get("model"),
                         run_by=said.get("run_by"))  # fmt: skip


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional(value) -> bool:
    """A text, or null: what the file's check then reads in full."""
    return value is None or isinstance(value, str)


def _number(value) -> bool:
    """A finite number: `10**400` is an integer that no float holds."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _texts(value) -> bool:
    return isinstance(value, list) and all(map(_text, value))


class _Place:
    """The faults of one description, each said with the place it is at."""

    def __init__(self):
        self.found: list[str] = []

    def keys(self, value, where: str, required: tuple, optional: tuple = ()) -> bool:
        """Whether `value` is a table of the keys a description takes there; each fault said."""
        shape = "{" + ", ".join((*required, *optional)) + "}"
        if not isinstance(value, dict):
            self.found.append(f"{where} is {shape}")
            return False
        unknown = sorted(str(k) for k in set(value) - set(required) - set(optional))
        missing = [k for k in required if k not in value]
        if unknown:
            self.found.append(f"{where}: a key a description does not take there: {', '.join(unknown)}")
        if missing:
            self.found.append(f"{where}: `{missing[0]}` is required ({shape})")
        return not unknown and not missing

    def each(self, value, where: str, checks) -> None:
        """Each `(key, check, says)` of a table that holds the key: one fault for each that
        fails. A key it does not hold is left to its default."""
        for key, check, says in checks:
            if key in value and not check(value[key]):
                self.found.append(f"{where}: `{key}` is {says}")

    def origin(self, value, where: str) -> None:
        if value is not None and self.keys(value, where, ("kind",), ("name", "model", "run_by")):
            self.each(value, where, [("kind", _text, "a text"), *[(k, _optional, "a text or null") for k in ("name", "model", "run_by")]])


#: What a description takes at its top: the check, what it is, and whether null stands for
#: the default (the build reads the others with a default only where they are absent).
TOP = (
    ("title", _text, "a text"),
    ("items", _text, "a text naming the table of items"),
    ("about", _optional, "a text or null"),
    ("tier", _text, "a text"),
    ("audience", _text, "a text"),
    ("listed", _count, "a whole number"),
    ("claim_lists", lambda v: isinstance(v, bool), "true or false"),
    ("floor_factor", _number, "a number"),
    ("notes", _texts, "a list of texts"),
    ("matrix", lambda v: v is None or (isinstance(v, str) and fileformat.FILE_NAME.fullmatch(v) is not None),
     "the plain name of a .json file, or null"),
)


def description_errors(spec) -> list[str]:
    """What keeps a description from being read, one sentence each with its place, before
    any table is opened. Every value the build reads is of the kind it takes, so that a
    mistake is a sentence, never a traceback, and never read as something else (`"no"` as
    explained, `[]` as no identity). What the description says is checked again, in full,
    when the file is built."""
    if not isinstance(spec, dict):
        return ["a description is a JSON object"]
    at = _Place()
    found = at.found
    found += [f"a key a description does not know: {k}" for k in sorted(map(str, set(spec) - KEYS))]
    for key in ("title", "items"):
        if key not in spec:
            found.append(f"`{key}` is a text")
    at.each(spec, "the description", TOP)
    for key in ("item", "indicator"):
        said = spec.get(key)
        if said is None and key == "indicator":
            continue
        if key in spec and not (at.keys(said, f"`{key}`", ("one", "many")) and all(map(_text, said.values()))):
            found.append(f"`{key}` is {{one, many}} in words")
    indicators = spec.get("indicators")
    if not (isinstance(indicators, list) and indicators):
        found.append("`indicators` is a list of {id, name, short, unit}")
        indicators = []
    for n, one in enumerate(indicators, 1):
        where = f"indicator {n}"
        if at.keys(one, where, ("id", "name"), ("short", "unit")):
            at.each(one, where, [("id", _text, "a text"), ("name", _text, "a text"),
                                 ("short", _optional, "a text or null"), ("unit", _optional, "a text or null")])  # fmt: skip
    states = spec.get("states")
    if not (isinstance(states, list) and len(states) >= 2):
        found.append("`states` is a list of at least two {id, label, results}, `results` naming a table")
        states = []
    good = [one for n, one in enumerate(states, 1) if _state(at, one, n)]
    known = {one["id"] for one in good}
    for one in good:
        said = one.get("noise")
        if said is not None:
            where = f"state {one['id']!r}"
            if one.get("kind") == "published":
                found.append(f"{where}: the published results have no builds and take no noise: they are exact")
            else:
                found += _noise_errors(said, where, known)
    steps = spec.get("steps")
    if not isinstance(steps, list):
        return [*found, "`steps` is a list of {id, label, kind}"]
    for n, one in enumerate(steps, 1):
        _step(at, one, n)
    explanations = spec.get("explanations", [])
    if not isinstance(explanations, list):
        found.append("`explanations` is a list of {text, by, ...}")
        explanations = []
    for n, one in enumerate(explanations, 1):
        where = f"explanation {n}"
        if at.keys(one, where, ("text",), ("by", "step", "indicator", "item", "link", "doc", "not_checked", "finding")):
            at.each(one, where, [("text", _text, "a text"), ("finding", _text, "a text"),
                                 *[(k, _optional, "a text or null") for k in ("step", "indicator", "item", "link", "doc", "not_checked")]])  # fmt: skip
            at.origin(one.get("by"), f"{where}, `by`")
    return found


def _state(at: _Place, one, n: int) -> bool:
    """Whether a state of a description can be read; its faults said."""
    where = f"state {one['id']!r}" if isinstance(one, dict) and _text(one.get("id")) else f"state {n}"
    if not at.keys(one, where, ("id", "label", "results"), ("kind", "about", "identity", "join", "noise")):
        return False
    before = len(at.found)
    at.each(one, where, [("id", _text, "a text"), ("label", _text, "a text"), ("results", _text, "a text naming a table"),
                         ("kind", _text, "a text"), ("about", _optional, "a text or null"),
                         ("identity", lambda v: v is None or (isinstance(v, dict) and all(isinstance(k, str) and _optional(x) for k, x in v.items())),
                          "a table of texts, or null")])  # fmt: skip
    join = one.get("join")
    if join is not None and at.keys(join, f"{where}, `join`", ("compared",), ("unmatched", "ambiguous", "note")):
        at.each(join, f"{where}, `join`", [*[(k, _count, "a count") for k in ("compared", "unmatched", "ambiguous")],
                                           ("note", _optional, "a text or null")])  # fmt: skip
    return len(at.found) == before


def _step(at: _Place, one, n: int) -> None:
    where = f"step {one['id']!r}" if isinstance(one, dict) and _text(one.get("id")) else f"step {n}"
    if isinstance(one, dict) and one.get("noise") is not None:
        at.found.append(f"{where}: noise belongs to the state that was built twice: move it to that state "
                        "(a step is compared with the sum of the noise of its two states)")  # fmt: skip
    if not at.keys(one, where, ("id", "label", "kind"), ("explained", "about", "link", "claim", "tolerance", "noise")):
        return
    at.each(one, where, [("id", _text, "a text"), ("label", _text, "a text"), ("kind", _text, "a text"),
                         ("explained", lambda v: isinstance(v, bool), "true or false"),
                         ("about", _optional, "a text or null"), ("link", _optional, "a text or null")])  # fmt: skip
    said = one.get("tolerance")
    if said is not None:
        if not (isinstance(said, dict) and "value" in said):
            at.found.append(f"{where}: a tolerance is {{value, basis, note}} with a number as its value")
        elif at.keys(said, f"{where}, `tolerance`", ("value",), ("basis", "note")):
            at.each(said, f"{where}, `tolerance`", [("value", _number, "a number"), ("basis", _optional, "a text or null"),
                                                    ("note", _optional, "a text or null")])  # fmt: skip
    said = one.get("claim")
    if said is None:
        return
    if not (isinstance(said, dict) and _text(said.get("text"))):
        at.found.append(f"{where}: a claim says what it claims (`text`)")
        return
    if not at.keys(said, f"{where}, its claim", ("text",), ("by", "reach", "scope")):
        return
    at.each(said, f"{where}, its claim", [("reach", lambda v: v is None or _count(v), "a count or null")])
    at.origin(said.get("by"), f"{where}, its claim's `by`")
    scope = said.get("scope", [])
    if not isinstance(scope, list):
        at.found.append(f"{where}: a claim's `scope` is a list of entries")
        return
    for k, entry in enumerate(scope, 1):
        place = f"{where}, scope entry {k}"
        if at.keys(entry, place, (), ("indicators", "items", "direction", "largest", "expect")):
            at.each(entry, place, [
                ("indicators", lambda v: v == "*" or _texts(v), '"*" or a list of ids'),
                ("items", lambda v: v is None or v == "*" or _texts(v), '"*", a list of ids or null'),
                ("direction", lambda v: v in claims.WAYS, "up, down or any"),
                ("largest", lambda v: v is None or _number(v), "a number or null"),
                ("expect", lambda v: v in claims.EXPECTS, "must or may"),
            ])  # fmt: skip


def _noise_errors(said, where: str, known: set) -> list[str]:
    pair = said.get("states") if isinstance(said, dict) else None
    tables_ = said.get("tables") if isinstance(said, dict) else None
    if not isinstance(said, dict) or set(said) - {"states", "tables", "note"} or not _optional(said.get("note")):
        return [f"{where}: a noise is {{states: [a, b]}} or {{tables: [{{label, results}}, {{label, results}}]}}, with a `note`"]
    if pair is not None:
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(s, str) and s in known for s in pair)):
            return [f"{where}: a noise's `states` names two states of this chain"]
    elif not (isinstance(tables_, list) and len(tables_) == 2
              and all(isinstance(t, dict) and set(t) == {"label", "results"} and _text(t["label"]) and _text(t["results"])
                      for t in tables_)):  # fmt: skip
        return [f"{where}: a noise is {{states: [a, b]}} or {{tables: [{{label, results}}, {{label, results}}]}}"]
    return []


def build(path: Path) -> dict:
    """The diagnostics file a description and its tables give, checked. Every mistake is a
    ValueError that says what is wrong (`tables.TableError` for a table)."""
    return build_with_matrix(path)[0]


def build_with_matrix(path: Path) -> tuple[dict, dict | None]:
    """The diagnostics file, and its matrix of every item where the description names one
    (None where it does not). Only a local file of items may name one."""
    path = Path(path)
    spec = fileformat.load_json(path)
    errors = description_errors(spec)
    if errors:
        raise ValueError(f"{path}: " + "; ".join(errors))
    here = path.parent
    indicators = spec["indicators"]
    ids = [i["id"] for i in indicators]
    items = tables.read_items(here / spec["items"])
    values = {s["id"]: tables.read_results(here / s["results"], ids) for s in spec["states"]}
    for state_id, by_indicator in values.items():
        unknown = {item for column in by_indicator.values() for item in column} - set(items)
        if unknown:
            raise ValueError(
                f"state {state_id!r}: items without a row in {spec['items']} (and so without "
                f"a reference unit): {', '.join(sorted(unknown)[:10])}"
            )
    # an item of the items table that no results table holds is missing in every state:
    # counted, never dropped
    first = values[spec["states"][0]["id"]]
    held = {item for by_indicator in values.values() for column in by_indicator.values() for item in column}
    for item in sorted(set(items) - held):
        for indicator in ids:
            first[indicator][item] = None
    # noise is taken beyond the floors the chain counts with: those of its first state
    floor_factor = spec.get("floor_factor", chain.rule.FLOOR_FACTOR)
    units = {k: v["unit"] for k, v in items.items()}
    floors = chain.rule.floors_of(values[spec["states"][0]["id"]], units, floor_factor)

    def floor_by_item(indicator):
        return {item: floors.get((indicator, unit), (0.0, 0))[0] for item, unit in units.items()}

    def noise_of_state(said):
        """What two builds of a state differ by, from two states of this chain or two tables."""
        if not said:
            return None
        if "states" in said:
            a, b = said["states"]
            pair, labels = (values[a], values[b]), (a, b)
        else:
            first, second = said["tables"]
            pair = (tables.read_results(here / first["results"], ids),
                    tables.read_results(here / second["results"], ids))  # fmt: skip
            labels = (first["label"], second["label"])
        return chain.noise(
            labels,
            {i: chain.noise_of(pair[0][i], pair[1][i], floor=floor_by_item(i)) for i in ids},
            said.get("note"),
        )

    steps = []
    for one in spec["steps"]:
        said_claim = one.get("claim")
        found_claim = None
        if said_claim is not None:
            found_claim = claims.claim(
                said_claim["text"],
                [
                    claims.scope(
                        e.get("indicators", "*"),
                        e.get("items", "*"),
                        e.get("direction", "any"),
                        e.get("largest"),
                        e.get("expect", claims.MAY),
                    )
                    for e in said_claim.get("scope", [])
                ],  # fmt: skip
                by=_origin(said_claim.get("by")),
                reach=said_claim.get("reach"),
            )
        said_tol = one.get("tolerance")
        steps.append(
            chain.step(
                one["id"],
                one["label"],
                kind=one["kind"],
                explained=one.get("explained", True),
                about=one.get("about"),
                link=one.get("link"),
                claim=found_claim,
                tolerance=chain.tolerance(said_tol["value"], said_tol.get("basis"), said_tol.get("note"))
                if said_tol
                else None,
            )  # fmt: skip
        )
    explanations = [
        chain.explanation(
            e["text"],
            _origin(e.get("by")),
            step=e.get("step"),
            indicator=e.get("indicator"),
            item=e.get("item"),
            link=e.get("link"),
            doc=e.get("doc"),
            not_checked=e.get("not_checked"),
            finding=e.get("finding", "reason"),
        )  # fmt: skip
        for e in spec.get("explanations", [])
    ]
    word = spec.get("item", {"one": "item", "many": "items"})
    named = spec.get("matrix")
    if named is not None and (
        spec.get("audience", "local") != "local" or spec.get("tier", "items") != "items"
    ):
        raise ValueError(
            f"{path}: only a local file of items names a matrix; a public file keeps the listed items only"
        )
    given = dict(
        about=spec.get("about"),
        indicators=indicators,
        states=[
            chain.state(
                s["id"],
                s["label"],
                kind=s.get("kind", "build"),
                about=s.get("about"),
                identity=s.get("identity"),
                join=s.get("join"),
                noise=noise_of_state(s.get("noise")),
            )  # fmt: skip
            for s in spec["states"]
        ],
        steps=steps,
        values=values,
        units=units,
        names=items,
        item_word=(word["one"], word["many"]),
        indicator_word=(spec["indicator"]["one"], spec["indicator"]["many"]) if spec.get("indicator") else None,
        listed=spec.get("listed", 200),
        tier=spec.get("tier", "items"),
        audience=spec.get("audience", "local"),
        claim_lists=spec.get("claim_lists", True),
        floor_factor=floor_factor,
        explanations=explanations,
        notes=spec.get("notes", []),
    )
    if named is None:
        return chain.build(spec["title"], **given), None
    return chain.build_with_matrix(spec["title"], matrix_file=named, **given)
