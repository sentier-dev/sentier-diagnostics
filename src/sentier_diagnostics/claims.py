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
project that made it (a list it may not publish) and only `reach`, the number of items,
is written. `largest` is relative to the size of the result before; a pair whose result
before is zero cannot be within it.

Each pair of a step with a claim gets one verdict:

    unchanged            it did not move, and no entry says it must
    within noise         it moved by no more than two builds of one state differ
    as claimed           it moved, an entry covers it, in that entry's direction and size
    off claim            it moved, entries cover it, and none in its direction and size
    not claimed          it moved, and no entry covers it
    claimed, not moved   an entry says it must move, and it did not
    not judged           it is missing or near zero: nothing can be said of it

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
    judge, and `published` leaves it out of a file."""
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


def published(found: dict, keep_items: bool = True) -> dict:
    """A claim as a file holds it: lists sorted, and with `keep_items` false every list of
    items left out (`items: null`), its size kept in `reach`."""
    listed = [e["items"] for e in found["scope"] if e["items"] not in ("*", None)]
    reach = found.get("reach")
    if reach is None and listed and len(listed) == len(found["scope"]):
        reach = len(set().union(*listed))
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


def fits(entry: Mapping, before: float, after: float, way: str | None) -> bool:
    """Whether a pair moved as an entry expects: its direction, and within its size."""
    if entry["direction"] != "any" and entry["direction"] != way:
        return False
    if entry["largest"] is None:
        return True
    moved_by = rule.change(before, after)
    return moved_by is not None and abs(moved_by) <= entry["largest"]


def verdict(kind: str, before, after, way: str | None, covering: list[Mapping]) -> str:
    """The verdict of one pair, given its class, its direction and the entries covering it.

    >>> down = scope(["x"], {"a"}, "down", 0.25, "must")
    >>> verdict("differs", 4.0, 3.5, "down", [down]), verdict("differs", 4.0, 2.0, "down", [down])
    ('as claimed', 'off claim')
    >>> verdict("agrees", 4.0, 4.0, None, [down]), verdict("agrees", 4.0, 4.0, None, [down | {"expect": "may"}])
    ('claimed, not moved', 'unchanged')
    >>> verdict("differs", 1.0, 2.0, "up", []), verdict("near zero", 0.0, 0.0, None, [down])
    ('not claimed', 'not judged')
    """
    if kind in (rule.MISSING, rule.NEAR_ZERO):
        return NOT_JUDGED
    if kind == rule.WITHIN_NOISE:
        return NOISE
    if kind == rule.AGREES:
        return NOT_MOVED if any(e["expect"] == MUST for e in covering) else UNCHANGED
    if not covering:
        return NOT_CLAIMED
    return AS_CLAIMED if any(fits(e, before, after, way) for e in covering) else OFF_CLAIM


def entries_for(found: Mapping | None, indicator: str) -> list[Mapping]:
    """The entries of a claim that can cover anything in one indicator."""
    if not found:
        return []
    return [e for e in found["scope"] if e["indicators"] == "*" or indicator in e["indicators"]]


def judgeable(found: Mapping | None) -> bool:
    """Whether every list of items of a claim is in hand, so that its verdicts can be
    worked out again from a file."""
    return bool(found) and all(e["items"] is not None for e in found["scope"])
