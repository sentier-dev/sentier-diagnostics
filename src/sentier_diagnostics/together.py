"""Several steps together: what a set of steps did, composed from every item's results.

A file holds one comparison per step and one for the whole way. Any other set of steps is
composed (SPEC section 3, "Several steps together"): an item's pair is its result before the
first chosen step, and that result with each run's difference added, where a run is a span
of consecutive chosen steps. A single run is its own pair exactly, the result after its last
step. The pair is judged by the one rule, with the largest tolerance of the chosen steps and
per indicator the largest noise measured in any of them; a set has no verdict.

The page composes with the same arithmetic (`composePair` in diagnostics.js), in the same
order, so both give the same numbers bit for bit. This module is its reference:
`tests/fixtures/together.json` holds the counts it gives for sets of the local example, and
the page is held to them.

Where steps apart change the same results, each one's difference depends on the steps before
it, left-out ones included, and the composed pair is not what the chosen steps would do
alone. Standard library only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from . import fileformat, matrix, rule


def runs_of(chosen: Sequence[int]) -> list[tuple[int, int]]:
    """The runs of a set of steps (their places), each (first, last).

    >>> runs_of([0, 1, 3, 5, 6])
    [(0, 1), (3, 3), (5, 6)]
    """
    out: list[list[int]] = []
    for k in sorted(set(chosen)):
        if out and out[-1][1] == k - 1:
            out[-1][1] = k
        else:
            out.append([k, k])
    return [(a, b) for a, b in out]


def pair(values: Sequence[float | None], runs: Sequence[tuple[int, int]]) -> tuple[float | None, float | None]:
    """The pair of a set of steps in one indicator, from the results over the states.

    >>> pair([1.0, 2.0, 2.5, 4.0], [(1, 2)])
    (2.0, 4.0)
    >>> pair([1.0, 2.0, 2.5, 4.0], [(0, 0), (2, 2)])
    (1.0, 3.5)
    >>> pair([1.0, None, 2.5, 4.0], [(0, 0), (2, 2)])
    (1.0, None)
    """
    before = values[runs[0][0]]
    if len(runs) == 1:
        return before, values[runs[0][1] + 1]
    if before is None:
        return None, None
    total = 0.0
    for first, last in runs:
        a, b = values[first], values[last + 1]
        if a is None or b is None:
            return before, None
        total += b - a
    return before, before + total


def counts(data: Mapping, m: Mapping, chosen: Sequence[int]) -> dict:
    """The counts of a set of steps over every item of a matrix, in the shape of a step's
    block per indicator, and each item's classes: `{"blocks": {indicator: block},
    "classes": {item: {indicator: class}}}`. Raises ValueError for a set the file holds
    itself (one step, or every step) or one it does not know."""
    steps = data["steps"]
    chosen = sorted(set(chosen))
    if not chosen or chosen[0] < 0 or chosen[-1] >= len(steps):
        raise ValueError("a set of steps of this file, by their places")
    if len(chosen) in (1, len(steps)):
        raise ValueError("one step and the whole way are the file's own")
    runs = runs_of(chosen)
    taken = [steps[k] for k in chosen]
    tolerance = max(s["tolerance"]["value"] for s in taken)
    noise = fileformat.noise_together(taken)
    floors = {(f["indicator"], f["unit"]): f["value"] for f in data["rule"]["floors"]}
    ids = [i["id"] for i in data["indicators"]]
    nstates = len(data["states"])
    reference = data["states"][0]["kind"] == "published" and chosen[0] != 0

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
            before, after = pair(values, runs)
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
