"""Build a diagnostics file from CSV tables and a short JSON description, without Python.

    {
      "title": "Our database, from the published results to main",
      "item": {"one": "dataset", "many": "datasets"},
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

Paths are relative to the description. A step's `noise` is
`{"states": ["a", "b"]}` (two states of this chain that are builds of one state) or
`{"tables": [{"label": "...", "results": "a.csv"}, {"label": "...", "results": "b.csv"}]}`.
It is taken over the results beyond the floors of the chain's first state. A scope entry
without `expect` says what may move (`"may"`), as SPEC section 6 says.
"""

from __future__ import annotations

from pathlib import Path

from . import chain, claims, fileformat, tables

KEYS = {"title", "about", "item", "indicators", "items", "states", "steps", "listed", "tier", "audience", "claim_lists",
        "explanations", "notes", "floor_factor", "matrix"}  # fmt: skip


def _origin(said):
    if said is None:
        return None
    return claims.origin(said.get("kind"), said.get("name"), model=said.get("model"),
                         run_by=said.get("run_by"))  # fmt: skip


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _table(value, keys) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) for k in value) and set(keys) <= set(value)


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def description_errors(spec) -> list[str]:
    """What keeps a description from being read, one sentence each, before any table is
    opened. What the description says is checked again, in full, when the file is built."""
    if not isinstance(spec, dict):
        return ["a description is a JSON object"]
    found = [f"a key a description does not know: {k}" for k in sorted(set(spec) - KEYS)]
    for key in ("title", "items"):
        if not _text(spec.get(key)):
            found.append(f"`{key}` is a text")
    for key, check, says in (
        ("about", _text, "a text"),
        ("tier", _text, "a text"),
        ("audience", _text, "a text"),
        ("listed", lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 0, "a whole number"),
        ("claim_lists", lambda v: isinstance(v, bool), "true or false"),
        ("floor_factor", _number, "a number"),
        (
            "item",
            lambda v: _table(v, ("one", "many")) and all(map(_text, v.values())),
            "{one, many} in words",
        ),
        ("notes", lambda v: isinstance(v, list) and all(map(_text, v)), "a list of texts"),
        (
            "matrix",
            lambda v: isinstance(v, str) and fileformat.FILE_NAME.fullmatch(v) is not None,
            "the plain name of a .json file",
        ),
    ):
        if key in spec and spec[key] is not None and not check(spec[key]):
            found.append(f"`{key}` is {says}")
    indicators = spec.get("indicators")
    if not (
        isinstance(indicators, list) and indicators and all(_table(i, ("id", "name")) for i in indicators)
    ):
        found.append("`indicators` is a list of {id, name, short, unit}")
    states = spec.get("states")
    if not (isinstance(states, list) and len(states) >= 2
            and all(_table(s, ("id", "label", "results")) and _text(s["results"]) for s in states)):  # fmt: skip
        found.append("`states` is a list of at least two {id, label, results}, `results` naming a table")
        states = []
    known = {s["id"] for s in states if isinstance(s.get("id"), str)}
    steps = spec.get("steps")
    if not (isinstance(steps, list) and all(_table(s, ("id", "label", "kind")) for s in steps)):
        return [*found, "`steps` is a list of {id, label, kind}"]
    for one in steps:
        where = f"step {one['id']!r}"
        said = one.get("claim")
        if said is not None:
            if not (_table(said, ("text",)) and _text(said["text"])):
                found.append(f"{where}: a claim says what it claims (`text`)")
            elif not (
                isinstance(said.get("scope", []), list)
                and all(isinstance(e, dict) for e in said.get("scope", []))
            ):
                found.append(f"{where}: a claim's `scope` is a list of entries")
            elif said.get("by") is not None and not isinstance(said["by"], dict):
                found.append(f"{where}: a claim's `by` is {{kind, name}}")
        said = one.get("tolerance")
        if said is not None and not (_table(said, ("value",)) and _number(said["value"])):
            found.append(f"{where}: a tolerance is {{value, basis, note}} with a number as its value")
        said = one.get("noise")
        if said is not None:
            pair = said.get("states") if isinstance(said, dict) else None
            tables_ = said.get("tables") if isinstance(said, dict) else None
            if pair is not None:
                if not (
                    isinstance(pair, list)
                    and len(pair) == 2
                    and all(isinstance(s, str) and s in known for s in pair)
                ):
                    found.append(f"{where}: a noise's `states` names two states of this chain")
            elif not (isinstance(tables_, list) and len(tables_) == 2
                      and all(_table(t, ("label", "results")) and _text(t["results"]) for t in tables_)):  # fmt: skip
                found.append(
                    f"{where}: a noise is {{states: [a, b]}} or {{tables: [{{label, results}}, {{label, results}}]}}"
                )
    explanations = spec.get("explanations", [])
    if not (isinstance(explanations, list) and all(_table(e, ("text",)) for e in explanations)):
        found.append("`explanations` is a list of {text, by, ...}")
    return found


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
        said_noise = one.get("noise")
        found_noise = None
        if said_noise:
            if "states" in said_noise:
                a, b = said_noise["states"]
                pair, labels = (values[a], values[b]), (a, b)
            else:
                first, second = said_noise["tables"]
                pair = (tables.read_results(here / first["results"], ids),
                        tables.read_results(here / second["results"], ids))  # fmt: skip
                labels = (first["label"], second["label"])
            found_noise = chain.noise(
                labels,
                {i: chain.noise_of(pair[0][i], pair[1][i], floor=floor_by_item(i)) for i in ids},
                said_noise.get("note"),
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
                noise=found_noise,
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
            )  # fmt: skip
            for s in spec["states"]
        ],
        steps=steps,
        values=values,
        units=units,
        names=items,
        item_word=(word["one"], word["many"]),
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
