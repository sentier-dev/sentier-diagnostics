"""A run of steps together: what consecutive steps did, judged from every item's results.

A file holds one comparison per step and one for the whole way. A run of two or more steps,
short of every step, is judged by the page (SPEC section 3, "A run of steps"): an item's
pair is its result in the state before the run's first step and in the state after its last,
two built states, never a sum. It is judged by the one rule, with the largest tolerance of
the run's steps and per indicator the largest noise measured in any of them (the builds
inside a run cancel); a run has no verdict.

Steps apart are not judged together on a chain: each step was measured with every step
before it applied, so its difference belongs to that place in the order. Any set of fixes
is the business of a file of fixes measured on one base (SPEC section 16).

The page judges with a port of the rule, in the same order; this module is its reference:
`tests/fixtures/together.json` holds the counts it gives for every run of the local example,
and the page is held to them. Standard library only."""

from __future__ import annotations

from collections.abc import Mapping

from . import fileformat, matrix, rule


def counts(data: Mapping, m: Mapping, first: int, last: int) -> dict:
    """The counts of the run of steps `first` to `last` (their places, both taken in) over
    every item of a matrix, in the shape of a step's block per indicator, and each item's
    classes: `{"blocks": {indicator: block}, "classes": {item: {indicator: class}}}`. Raises
    ValueError for a run the file holds itself (one step, or every step) or one it does not
    know."""
    steps = data["steps"]
    if not 0 <= first < last < len(steps):
        raise ValueError("a run of two or more steps of this file, by their places, first before last")
    if first == 0 and last == len(steps) - 1:
        raise ValueError("every step is the whole way, the file's own")
    chosen = range(first, last + 1)
    taken = [steps[k] for k in chosen]
    tolerance = max(s["tolerance"]["value"] for s in taken)
    noise = fileformat.noise_together(taken)
    floors = {(f["indicator"], f["unit"]): f["value"] for f in data["rule"]["floors"]}
    ids = [i["id"] for i in data["indicators"]]
    nstates = len(data["states"])
    reference = data["states"][0]["kind"] == "published" and first != 0

    def empty():
        return {
            "pairs": 0,
            "classes": dict.fromkeys(rule.CLASSES, 0),
            "missing": dict.fromkeys(fileformat.MISSING_SIDES, 0),
            "directions": dict.fromkeys(rule.DIRECTIONS, 0),
            "bands": dict.fromkeys(rule.BANDS, 0),
            "verdicts": None,
            "closer": 0 if reference else None,
            "further": 0 if reference else None,
        }

    blocks = {i: empty() for i in ids}
    classes = {}
    for at, (item_id, _name, _place, _group, unit) in enumerate(m["items"]):
        flat = matrix.expand(m["values"][at], nstates)
        classes[item_id] = {}
        for x, indicator in enumerate(ids):
            values = flat[x * nstates : (x + 1) * nstates]
            before, after = values[first], values[last + 1]
            kind, way, band = rule.judge(before, after, floor=floors[(indicator, unit)], tolerance=tolerance,
                                         noise=noise.get(indicator))  # fmt: skip
            classes[item_id][indicator] = kind
            block = blocks[indicator]
            block["pairs"] += 1
            block["classes"][kind] += 1
            if kind == rule.MISSING:
                side = "both" if before is None and after is None else "before" if before is None else "after"
                block["missing"][side] += 1
            if band:
                block["bands"][band] += 1
            if way:
                block["directions"][way] += 1
            if reference and kind in rule.MOVES and values[0] is not None:
                was, now = abs(before - values[0]), abs(after - values[0])
                block["closer"] += now < was
                block["further"] += now > was
    return {"blocks": blocks, "classes": classes}
