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

Paths are relative to the description. A step's `noise` is
`{"states": ["a", "b"]}` (two states of this chain that are builds of one state) or
`{"tables": [{"label": "...", "results": "a.csv"}, {"label": "...", "results": "b.csv"}]}`.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import chain, claims, tables

KEYS = {"title", "about", "item", "indicators", "items", "states", "steps", "listed", "tier", "audience", "claim_lists",
        "explanations", "notes", "floor_factor"}  # fmt: skip


def _origin(said):
    if said is None:
        return None
    return claims.origin(said.get("kind"), said.get("name"), model=said.get("model"),
                         run_by=said.get("run_by"))  # fmt: skip


def build(path: Path) -> dict:
    """The diagnostics file a description and its tables give, checked."""
    path = Path(path)
    spec = json.loads(path.read_text(encoding="utf-8"))
    unknown = set(spec) - KEYS
    if unknown:
        raise ValueError(f"{path}: keys a description does not know: {', '.join(sorted(unknown))}")
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
    steps = []
    for one in spec["steps"]:
        said_claim = one.get("claim")
        found_claim = None
        if said_claim is not None:
            found_claim = claims.claim(
                said_claim["text"],
                [
                    claims.scope(e.get("indicators", "*"), e.get("items", "*"), e.get("direction", "any"),
                                 e.get("largest"), e.get("expect", claims.MUST))
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
                labels, {i: chain.noise_of(pair[0][i], pair[1][i]) for i in ids}, said_noise.get("note")
            )
        said_tol = one.get("tolerance")
        steps.append(
            chain.step(
                one["id"], one["label"], kind=one["kind"], explained=one.get("explained", True),
                about=one.get("about"), link=one.get("link"), claim=found_claim,
                tolerance=chain.tolerance(said_tol["value"], said_tol.get("basis"), said_tol.get("note"))
                if said_tol else None,
                noise=found_noise,
            )  # fmt: skip
        )
    explanations = [
        chain.explanation(
            e["text"], _origin(e.get("by")), step=e.get("step"), indicator=e.get("indicator"),
            item=e.get("item"), link=e.get("link"), doc=e.get("doc"), not_checked=e.get("not_checked"),
            finding=e.get("finding", "reason"),
        )  # fmt: skip
        for e in spec.get("explanations", [])
    ]
    word = spec.get("item", {"one": "item", "many": "items"})
    return chain.build(
        spec["title"],
        about=spec.get("about"),
        indicators=indicators,
        states=[
            chain.state(s["id"], s["label"], kind=s.get("kind", "build"), about=s.get("about"),
                        identity=s.get("identity"), join=s.get("join"))  # fmt: skip
            for s in spec["states"]
        ],
        steps=steps,
        values=values,
        units={k: v["unit"] for k, v in items.items()},
        names=items,
        item_word=(word["one"], word["many"]),
        listed=spec.get("listed", 200),
        tier=spec.get("tier", "items"),
        audience=spec.get("audience", "local"),
        claim_lists=spec.get("claim_lists", True),
        floor_factor=spec.get("floor_factor", chain.rule.FLOOR_FACTOR),
        explanations=explanations,
        notes=spec.get("notes", []),
    )
