"""Small chains built in tests. Every value here is made up."""

from __future__ import annotations

import copy

from sentier_diagnostics import chain, claims

A, B = "x:a", "x:b"
INDICATORS = [(A, "Indicator A", "A", "kg CO2 eq"), (B, "Indicator B", "B", "m3")]


def two_states(before: dict, after: dict, *, claim=None, units=None, **more) -> dict:
    """A chain of one step: `before` and `after` are `{indicator: {item: value}}`."""
    items = {item for side in (before, after) for column in side.values() for item in column}
    return chain.build(
        "Two states",
        indicators=INDICATORS,
        states=[chain.state("s0", "Before", kind="published"), chain.state("s1", "After")],
        steps=[chain.step("one", "One step", kind="fix", claim=claim)],
        values={"s0": before, "s1": after},
        units=units or dict.fromkeys(items, "kg"),
        **more,
    )


def three_states(first: dict, middle: dict, last: dict, *, explained=(True, True), **more) -> dict:
    items = {item for side in (first, middle, last) for column in side.values() for item in column}
    return chain.build(
        "Three states",
        indicators=INDICATORS,
        states=[chain.state("s0", "Published", kind="published"), chain.state("s1", "Middle"),
                chain.state("s2", "Last")],  # fmt: skip
        steps=[chain.step("one", "First step", kind="fix", explained=explained[0]),
               chain.step("two", "Second step", kind="fix", explained=explained[1])],  # fmt: skip
        values={"s0": first, "s1": middle, "s2": last},
        units=dict.fromkeys(items, "kg"),
        **more,
    )


def claim_down(items, largest=None, expect=claims.MUST, indicators=(A,)):
    return claims.claim(
        "They go down.",
        [claims.scope(list(indicators), set(items), "down", largest, expect)],
        by=claims.origin("person", "A. Author"),
    )


def mutated(data: dict, change) -> dict:
    """A deep copy of a file with one change applied, for tests of the validator."""
    copied = copy.deepcopy(data)
    change(copied)
    return copied
