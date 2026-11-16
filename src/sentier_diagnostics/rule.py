"""The counting rule: what one pair of results is, which way it went, and how far.

Every comparison this package writes counts with these functions, so that two
projects mean the same by the same word. A pair is one item in one indicator, before
and after. It gets exactly one class:

    missing          a side has no result; it is never read as zero
    near zero        both sides lie within the floor of the indicator and the item's
                     reference unit: their ratio says nothing
    zero reference   the side before lies within the floor, the side after does not
    zero result      the side after lies within the floor, the side before does not
    sign change      both sides lie beyond the floor and have different signs
    agrees           the two differ by no more than the tolerance, relative to the larger
    within noise     they differ by more, but by no more than two builds of one state do
    beyond 10x       one side is more than ten times the size of the other
    differs          any other difference

The classes are tried in this order; the first that holds is the class. No class blanks
a value, sets it to zero or calls it agreement: the two results are always kept.

**Direction** has one rule: a pair that moved (`MOVES`) went up where the result after
is larger than the result before, as signed numbers, and down otherwise. Two results
below zero that go further below zero went down, although the size of the second is
the larger. Colour on a page follows the direction and nothing else.

**Bands** split a pair that differs, or is beyond 10x, by its direction and by the
factor between the sizes of its two results.

Standard library only. Parts of this module are adapted from `before_after.py` of
sentier-bafu (MIT, Copyright (c) 2026 sentier.dev); see NOTICE.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

MISSING = "missing"
NEAR_ZERO = "near zero"
ZERO_REFERENCE = "zero reference"
ZERO_RESULT = "zero result"
SIGN_CHANGE = "sign change"
AGREES = "agrees"
WITHIN_NOISE = "within noise"
BEYOND = "beyond 10x"
DIFFERS = "differs"

#: The classes, in the order a page lists them.
CLASSES = (
    AGREES,
    WITHIN_NOISE,
    DIFFERS,
    BEYOND,
    ZERO_REFERENCE,
    ZERO_RESULT,
    SIGN_CHANGE,
    NEAR_ZERO,
    MISSING,
)
#: The classes of a pair that moved: they have a direction.
MOVES = frozenset({DIFFERS, BEYOND, ZERO_REFERENCE, ZERO_RESULT, SIGN_CHANGE})
#: The classes that alone do not make an item worth listing.
QUIET = frozenset({AGREES, WITHIN_NOISE, NEAR_ZERO})

UP, DOWN = "up", "down"
DIRECTIONS = (UP, DOWN)

#: One side more than this many times the size of the other is beyond 10x.
BEYOND_FACTOR = 10.0
#: A result below this share of the median size of its group is near zero (`floor_of`).
FLOOR_FACTOR = 0.01
#: Two builds of one database on two machines differ by about 1e-7 to 1e-6 (measured on
#: sentier-bafu: 8e-12 on one runner, 2.8e-7 across runners). The default tolerance lies
#: one order above that, so that solver noise is never counted as a change.
DEFAULT_TOLERANCE = 1e-5

#: The factors between the sizes of two results at which a band ends, and the band's name.
SIZE_STEPS = (
    (math.log10(1.1), "1-1.1"),
    (math.log10(1.25), "1.1-1.25"),
    (math.log10(2.0), "1.25-2"),
    (1.0, "2-10"),
)
OVER = "over 10"
_STEPS = tuple(name for _, name in SIZE_STEPS) + (OVER,)
#: The bands, from far down to far up.
BANDS = tuple(f"down, factor {s}" for s in reversed(_STEPS)) + tuple(
    f"up, factor {s}" for s in _STEPS
)

#: How a class ranks when items are ordered from the worst: a lower rank comes first.
RANK = {
    SIGN_CHANGE: 0,
    ZERO_REFERENCE: 1,
    ZERO_RESULT: 2,
    BEYOND: 3,
    DIFFERS: 4,
    MISSING: 5,
    WITHIN_NOISE: 6,
    AGREES: 7,
    NEAR_ZERO: 8,
}


def is_value(value) -> bool:
    """A result: a finite number that is not a boolean.

    >>> is_value(1.5), is_value(0), is_value(True), is_value(float("nan")), is_value(None)
    (True, True, False, False, False)
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def relative_difference(before: float, after: float) -> float:
    """How far two results lie apart, relative to the larger of the two; 0 where both are 0.

    >>> relative_difference(2.0, 1.0), relative_difference(0.0, 0.0), relative_difference(1.0, -1.0)
    (0.5, 0.0, 2.0)
    """
    size = max(abs(before), abs(after))
    return abs(after - before) / size if size else 0.0


def change(before: float, after: float) -> float | None:
    """The change relative to the size of the result before, signed as the direction is:
    -0.5 is "50 % lower". None where the result before is zero.

    >>> change(2.0, 1.0), change(-2.0, -4.0), change(4.0, 6.0), change(0.0, 1.0)
    (-0.5, -1.0, 0.5, None)
    """
    return (after - before) / abs(before) if before else None


def size_ratio(before: float, after: float) -> float | None:
    """The size of the result after divided by the size of the result before, where both are
    of one sign and not zero; else None.

    >>> size_ratio(2.0, 3.0), size_ratio(-2.0, -4.0), size_ratio(2.0, -1.0), size_ratio(0.0, 1.0)
    (1.5, 2.0, None, None)
    """
    if not before or not after or (before > 0) != (after > 0):
        return None
    found = abs(after) / abs(before)
    return found if math.isfinite(found) and found > 0 else None


def distance(before: float, after: float) -> float | None:
    """How far the sizes of two results lie apart: |log10| of their factor; None without one.

    >>> distance(1.0, 10.0), distance(-1.0, -0.1), distance(1.0, -1.0)
    (1.0, 1.0, None)
    """
    found = size_ratio(before, after)
    return abs(math.log10(found)) if found is not None else None


def classify(
    before: float | None,
    after: float | None,
    *,
    floor: float = 0.0,
    tolerance: float = DEFAULT_TOLERANCE,
    noise: float | None = None,
) -> str:
    """The class of one pair of results (see the module's text).

    >>> classify(1.0, None), classify(1e-9, -2e-9, floor=1e-6), classify(0.0, 2.0)
    ('missing', 'near zero', 'zero reference')
    >>> classify(2.0, 0.0), classify(-1.0, 1.0), classify(1.0, 1.000001)
    ('zero result', 'sign change', 'agrees')
    >>> classify(1.0, 1.02, noise=0.05), classify(1.0, 20.0), classify(-2.0, -4.0)
    ('within noise', 'beyond 10x', 'differs')
    """
    if before is None or after is None:
        return MISSING
    small_before, small_after = abs(before) <= floor, abs(after) <= floor
    if small_before and small_after:
        return NEAR_ZERO
    if small_before:
        return ZERO_REFERENCE
    if small_after:
        return ZERO_RESULT
    if (before > 0) != (after > 0):
        return SIGN_CHANGE
    gap = relative_difference(before, after)
    if gap <= tolerance:
        return AGREES
    if noise and gap <= noise:
        return WITHIN_NOISE
    larger, smaller = max(abs(before), abs(after)), min(abs(before), abs(after))
    if larger > BEYOND_FACTOR * smaller:
        return BEYOND
    return DIFFERS


def direction(before: float | None, after: float | None, kind: str) -> str | None:
    """Which way a pair that moved went, as signed numbers; None for a pair that did not.

    >>> direction(-2.0, -4.0, DIFFERS), direction(1.0, 3.0, DIFFERS), direction(1.0, 1.0, AGREES)
    ('down', 'up', None)
    """
    if kind not in MOVES:
        return None
    return UP if after > before else DOWN


def band(before: float | None, after: float | None, kind: str) -> str | None:
    """The band of a pair that differs or is beyond 10x; None for any other class.

    >>> band(1.0, 1.5, DIFFERS), band(-2.0, -4.0, DIFFERS), band(10.0, 0.5, BEYOND)
    ('up, factor 1.25-2', 'down, factor 1.25-2', 'down, factor over 10')
    """
    if kind not in (DIFFERS, BEYOND):
        return None
    way = direction(before, after, kind)
    if kind == BEYOND:
        return f"{way}, factor {OVER}"
    found = distance(before, after)
    for edge, name in SIZE_STEPS:
        if found <= edge:
            return f"{way}, factor {name}"
    return f"{way}, factor {SIZE_STEPS[-1][1]}"  # exactly ten times: not beyond


def judge(
    before: float | None,
    after: float | None,
    *,
    floor: float = 0.0,
    tolerance: float = DEFAULT_TOLERANCE,
    noise: float | None = None,
) -> tuple[str, str | None, str | None]:
    """Class, direction and band of one pair, from the one rule."""
    kind = classify(before, after, floor=floor, tolerance=tolerance, noise=noise)
    return kind, direction(before, after, kind), band(before, after, kind)


def severity(before: float | None, after: float | None, kind: str) -> tuple[int, float]:
    """The key that orders pairs from the worst: the rank of the class, then how far apart.

    >>> sorted([(1.0, 1.5), (1.0, -1.0), (1.0, 3.0)], key=lambda p: severity(*p, classify(*p)))
    [(1.0, -1.0), (1.0, 3.0), (1.0, 1.5)]
    """
    if before is None or after is None:
        return RANK[kind], 0.0
    found = distance(before, after)
    return RANK[kind], -(found if found is not None else relative_difference(before, after))


def floor_of(values: Iterable[float | None], factor: float = FLOOR_FACTOR) -> tuple[float, int]:
    """The floor of one group of results and how many results it was taken from: `factor`
    times the median size of the results that are not zero. No such result: no floor.

    >>> floor_of([0.0, 1.0, -3.0, 2.0]), floor_of([0.0, None])
    ((0.02, 3), (0.0, 0))
    """
    sizes = sorted(abs(v) for v in values if is_value(v) and v != 0)
    if not sizes:
        return 0.0, 0
    middle = len(sizes) // 2
    median = sizes[middle] if len(sizes) % 2 else (sizes[middle - 1] + sizes[middle]) / 2
    return factor * median, len(sizes)


def floors_of(
    values: Mapping[str, Mapping[str, float | None]],
    units: Mapping[str, str | None],
    factor: float = FLOOR_FACTOR,
) -> dict[tuple[str, str | None], tuple[float, int]]:
    """One floor per indicator and reference unit, from one set of results.

    `values` is `{indicator: {item: result}}`, `units` the reference unit of each item. Items
    of different units are never pooled: a result per tractor and a result per kilogram are
    not of one size.

    >>> found = floors_of({"x": {"a": 1.0, "b": 3.0, "t": 5000.0}}, {"a": "kg", "b": "kg", "t": "unit"})
    >>> found[("x", "kg")], found[("x", "unit")]
    ((0.02, 2), (50.0, 1))
    """
    found = {}
    for indicator, by_item in values.items():
        groups: dict[str | None, list[float | None]] = {}
        for item, value in by_item.items():
            groups.setdefault(units.get(item), []).append(value)
        for unit, group in groups.items():
            found[(indicator, unit)] = floor_of(group, factor)
    return found
