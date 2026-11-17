"""What a step claims to move, and how each pair it moved is held against that claim.

A step of a chain (a fix, a mapping, a contribution, the import itself) may carry a
claim: which indicators and items it moves, in which direction, by how much at most, and
whether each must move or only may. A claim with no entry says that nothing moves.

    {"text": "Wheat and rice go down in climate change, by 30 % at most.",
     "by": {"kind": "person", "name": "A. Author"},
     "reach": 2,
     "scope": [{"indicators": ["x:climate"], "items": ["p01", "p05"],
                "direction": "down", "largest": 0.3, "expect": "must"}]}

`items` is `"*"` (every item), a list of ids, or null where the list stays with the
project that made it (a list it may not publish). `reach` is the number of items the
claim's lists name together, `"*"` entries aside; where a list stays private it is the
only trace of it. `largest` is relative to the size of the result before; a pair whose
result before lies within the floor (a zero reference) cannot be within it.

Each pair of a step with a claim gets one verdict, tried in this order:

    not judged           it is missing: nothing can be said of it
    claimed, not moved   an entry says it must move, and it agrees, is within noise or is
                         near zero: it did not move beyond the tolerance, the noise or the floor
    unchanged            it agrees, and no entry says it must move
    within noise         it moved by no more than two builds of one state differ
    not judged           it is near zero, and no entry says it must move
    not claimed          it moved, and no entry covers it
    as claimed           it moved, an entry covers it, in that entry's direction and size
    off claim            it moved, entries cover it, and none in its direction and size

Where `must` entries cover a moved pair, it is held against them only: a `may` entry
beside them cannot excuse a move the `must` entries do not allow.

A scope that a program worked out (every item whose supply chain reaches the change)
says what *may* move: it can be exceeded, never unmet. Its entries carry `"may"`.

Adapted in part from `before_after.py` of sentier-bafu (MIT, Copyright (c) 2026
sentier.dev); see NOTICE.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from . import rule

UNCHANGED = "unchanged"
NOISE = "within noise"
AS_CLAIMED = "as claimed"
OFF_CLAIM = "off claim"
NOT_CLAIMED = "not claimed"
NOT_MOVED = "claimed, not moved"
NOT_JUDGED = "not judged"
#: The verdicts, in the order a page lists them.
VERDICTS = (AS_CLAIMED, OFF_CLAIM, NOT_CLAIMED, NOT_MOVED, NOISE, UNCHANGED, NOT_JUDGED)
#: The verdicts a reviewer has to look at.
TO_LOOK_AT = frozenset({OFF_CLAIM, NOT_CLAIMED, NOT_MOVED})

MUST, MAY = "must", "may"
EXPECTS = (MUST, MAY)
WAYS = ("up", "down", "any")


def origin(kind: str, name: str | None = None, *, model: str | None = None,
           run_by: str | None = None) -> dict:  # fmt: skip
    """Who wrote a claim or an explanation: a person (by name), code (the program or rule,
    by name), or a model (its id, and who ran it)."""
    return {"kind": kind, "name": name, "model": model, "run_by": run_by}


def scope(indicators="*", items="*", direction="any", largest=None, expect=MAY) -> dict:
    """One entry of a claim. `items` may be a set the project keeps to itself: it is used to
    judge, and `published` leaves it out of a file. A single text other than "*" is refused:
    it would be read as a set of its characters."""
    if isinstance(items, str) and items != "*":
        raise TypeError(f"the items of a scope are '*', a list of ids or None, not the text {items!r}")
    if isinstance(indicators, str) and indicators != "*":
        raise TypeError(f"the indicators of a scope are '*' or a list of ids, not the text {indicators!r}")
    return {
        "indicators": indicators if indicators == "*" else sorted(indicators),
        "items": items if items == "*" or items is None else set(items),
        "direction": direction,
        "largest": largest,
        "expect": expect,
    }


def claim(text: str, entries: Iterable[dict] = (), *, by: dict | None = None,
          reach: int | None = None) -> dict:  # fmt: skip
    """What a step is expected to move. Without an entry: nothing moves."""
    return {"text": text, "by": by, "reach": reach, "scope": list(entries)}


def reach_of(entries: Iterable[Mapping]) -> int | None:
    """How many items the lists of a claim name together, `"*"` entries aside; None where a
    list is not in hand or no entry lists items.

    >>> reach_of([scope(["x"], {"a", "b"}), scope(["y"], {"b"}), scope(["z"])])
    2
    >>> reach_of([scope(["x"], None)]) is None, reach_of([scope()]) is None
    (True, True)
    """
    entries = list(entries)
    if any(e["items"] is None for e in entries):
        return None
    listed = [set(e["items"]) for e in entries if e["items"] != "*"]
    return len(set().union(*listed)) if listed else None


def published(found: dict, keep_items: bool = True) -> dict:
    """A claim as a file holds it: lists sorted, and with `keep_items` false every list of
    items left out (`items: null`), its size kept in `reach`."""
    reach, size = found.get("reach"), reach_of(found["scope"])
    if size is not None:
        if reach is not None and reach != size:
            raise ValueError(f"a claim's reach is {reach}, and its lists name {size} items")
        reach = size
    entries = []
    for entry in found["scope"]:
        items = entry["items"]
        if items not in ("*", None):
            items = sorted(items) if keep_items else None
        entries.append(entry | {"items": items})
    return {"text": found["text"], "by": found.get("by"), "reach": reach, "scope": entries}


def covers(entry: Mapping, item: str, indicator: str) -> bool:
    """Whether a scope entry covers one item in one indicator. An entry whose list of items
    is not in hand covers nothing here: judging needs the list."""
    if entry["indicators"] != "*" and indicator not in entry["indicators"]:
        return False
    items = entry["items"]
    return items == "*" or (items is not None and item in items)


def fits(entry: Mapping, before: float, after: float, way: str | None, kind: str | None = None) -> bool:
    """Whether a pair moved as an entry expects: its direction, and within its size. A zero
    reference has no size to be relative to, so it is never within a `largest`."""
    if entry["direction"] != "any" and entry["direction"] != way:
        return False
    if entry["largest"] is None:
        return True
    if kind == rule.ZERO_REFERENCE:
        return False
    moved_by = rule.change(before, after)
    return moved_by is not None and abs(moved_by) <= entry["largest"]


#: The classes of a pair that did not move beyond the tolerance, the noise or the floor.
STILL = frozenset({rule.AGREES, rule.WITHIN_NOISE, rule.NEAR_ZERO})


def verdict(kind: str, before, after, way: str | None, covering: list[Mapping]) -> str:
    """The verdict of one pair, given its class, its direction and the entries covering it.

    >>> down = scope(["x"], {"a"}, "down", 0.25, "must")
    >>> verdict("differs", 4.0, 3.5, "down", [down]), verdict("differs", 4.0, 2.0, "down", [down])
    ('as claimed', 'off claim')
    >>> verdict("agrees", 4.0, 4.0, None, [down]), verdict("agrees", 4.0, 4.0, None, [down | {"expect": "may"}])
    ('claimed, not moved', 'unchanged')
    >>> verdict("differs", 1.0, 2.0, "up", []), verdict("near zero", 0.0, 0.0, None, [down])
    ('not claimed', 'claimed, not moved')
    >>> verdict("missing", None, 1.0, None, [down]), verdict("differs", 4.0, 5.0, "up", [down, scope(["x"], {"a"})])
    ('not judged', 'off claim')
    """
    if kind == rule.MISSING:
        return NOT_JUDGED
    musts = [e for e in covering if e["expect"] == MUST]
    if kind in STILL:
        if musts:
            return NOT_MOVED
        return {rule.AGREES: UNCHANGED, rule.WITHIN_NOISE: NOISE}.get(kind, NOT_JUDGED)
    if not covering:
        return NOT_CLAIMED
    held_to = musts or covering
    return AS_CLAIMED if any(fits(e, before, after, way, kind) for e in held_to) else OFF_CLAIM


def entries_for(found: Mapping | None, indicator: str) -> list[Mapping]:
    """The entries of a claim that can cover anything in one indicator."""
    if not found:
        return []
    return [e for e in found["scope"] if e["indicators"] == "*" or indicator in e["indicators"]]


def judgeable(found: Mapping | None) -> bool:
    """Whether every list of items of a claim is in hand, so that its verdicts can be
    worked out again from a file."""
    return bool(found) and all(e["items"] is not None for e in found["scope"])
