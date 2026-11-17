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

    claimed, not judged  an entry says it must move, and it is missing or near zero: whether
                         it moved cannot be said, and the claim is left open
    not judged           it is missing or near zero, and no entry says it must move
    claimed, not moved   an entry says it must move, and it agrees or is within noise: it did
                         not move beyond the tolerance or the noise
    unchanged            it agrees, and no entry says it must move
    within noise         it moved by no more than two builds of one state differ
    not claimed          it moved, and no entry covers it
    as claimed           it moved, and it fits every `must` entry that covers it (or, where
                         none does, one of the `may` entries): their direction and size
    off claim            it moved, and it does not

Where `must` entries cover a moved pair, it is held against them only, and against all of
them: each says what the pair must do, so a move up does not meet `must down` because a
`must any` or a `may any` beside it allows it. `may` entries say what may move: one that
fits is enough.

A claim is judged where it was made, with its lists in hand; `chain.build` refuses an entry
whose list is not (`items: null`), since such an entry would cover nothing and a `must`
would be met by default. A file may still leave its lists out (`published`).

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
OPEN = "claimed, not judged"
NOT_JUDGED = "not judged"
#: The verdicts, in the order a page lists them.
VERDICTS = (AS_CLAIMED, OFF_CLAIM, NOT_CLAIMED, NOT_MOVED, OPEN, NOISE, UNCHANGED, NOT_JUDGED)
#: The verdicts a reviewer has to look at: each makes its item worth a look.
TO_LOOK_AT = frozenset({OFF_CLAIM, NOT_CLAIMED, NOT_MOVED, OPEN})

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
#: The classes of a pair of which no verdict can say whether it moved.
UNJUDGEABLE = frozenset({rule.MISSING, rule.NEAR_ZERO})


def verdict(kind: str, before, after, way: str | None, covering: list[Mapping]) -> str:
    """The verdict of one pair, given its class, its direction and the entries covering it.

    >>> down = scope(["x"], {"a"}, "down", 0.25, "must")
    >>> verdict("differs", 4.0, 3.5, "down", [down]), verdict("differs", 4.0, 2.0, "down", [down])
    ('as claimed', 'off claim')
    >>> verdict("agrees", 4.0, 4.0, None, [down]), verdict("agrees", 4.0, 4.0, None, [down | {"expect": "may"}])
    ('claimed, not moved', 'unchanged')
    >>> verdict("differs", 1.0, 2.0, "up", []), verdict("near zero", 1e-9, 1e-12, None, [down])
    ('not claimed', 'claimed, not judged')
    >>> verdict("missing", None, 1.0, None, [down]), verdict("missing", None, 1.0, None, [])
    ('claimed, not judged', 'not judged')
    >>> verdict("differs", 4.0, 5.0, "up", [down, scope(["x"], {"a"})])
    'off claim'
    >>> verdict("differs", 1.0, 5.0, "up", [down, scope(expect="must")])  # all of the `must` entries
    'off claim'
    """
    musts = [e for e in covering if e["expect"] == MUST]
    if kind in UNJUDGEABLE:
        return OPEN if musts else NOT_JUDGED
    if kind in STILL:
        return NOT_MOVED if musts else {rule.AGREES: UNCHANGED, rule.WITHIN_NOISE: NOISE}[kind]
    if not covering:
        return NOT_CLAIMED
    if musts:
        return AS_CLAIMED if all(fits(e, before, after, way, kind) for e in musts) else OFF_CLAIM
    return AS_CLAIMED if any(fits(e, before, after, way, kind) for e in covering) else OFF_CLAIM


def entries_for(found: Mapping | None, indicator: str) -> list[Mapping]:
    """The entries of a claim that can cover anything in one indicator."""
    if not found:
        return []
    return [e for e in found["scope"] if e["indicators"] == "*" or indicator in e["indicators"]]


def judgeable(found: Mapping | None) -> bool:
    """Whether every list of items of a claim is in hand, so that its verdicts can be
    worked out again from a file."""
    return bool(found) and all(e["items"] is not None for e in found["scope"])
