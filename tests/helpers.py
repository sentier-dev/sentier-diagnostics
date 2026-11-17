"""Small chains built in tests. Every value here is made up."""

from __future__ import annotations

import copy
import html.parser

from sentier_diagnostics import chain, claims

A, B = "x:a", "x:b"
INDICATORS = [(A, "Indicator A", "A", "kg CO2 eq"), (B, "Indicator B", "B", "m3")]


def two_states(before: dict, after: dict, *, claim=None, units=None, first_kind="published", **more) -> dict:
    """A chain of one step: `before` and `after` are `{indicator: {item: value}}`."""
    items = {item for side in (before, after) for column in side.values() for item in column}
    return chain.build(
        "Two states",
        indicators=INDICATORS,
        states=[chain.state("s0", "Before", kind=first_kind), chain.state("s1", "After")],
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


#: Values of every JSON type and a few edges, put in place of a node to see that a check
#: returns faults for them and never raises (issue 4)
ODD = ([], {}, [[]], {"a": 1}, "x", -1, 1.5, True, None, 10**400, [None], 1, [1], {"x": [1]})


def nodes(node):
    """Every place in a JSON tree, as `(parent, key)`, parents before their children. The
    first, second and last of a list stand for the rest of it."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield node, key
            yield from nodes(value)
    elif isinstance(node, list):
        for key in sorted({0, 1, len(node) - 1} & set(range(len(node)))):
            yield node, key
            yield from nodes(node[key])


def replaced_everywhere(test, data, check, stopped=None):
    """Each node of `data` replaced in turn by each of `ODD`: `check` returns a list of
    faults and never raises, and no fault is `stopped` (the backstop of a check that names
    no place). `data` is left as it was."""
    for parent, key in list(nodes(data)):
        kept = parent[key]
        for value in ODD:
            parent[key] = value
            try:
                found = check(data)
            except Exception as error:  # noqa: BLE001 - the test is that nothing raises
                test.fail(f"{key!r} = {value!r}: {type(error).__name__}: {error}")
            test.assertIsInstance(found, list)
            if stopped is not None:
                test.assertFalse([e for e in found if e.startswith(stopped)], f"{key!r} = {value!r}")
        parent[key] = kept


class _Shown(html.parser.HTMLParser):
    """What a reader of a written page sees: its text outside scripts and styles, and the
    texts it shows on request (a tooltip, a label read aloud, a placeholder)."""

    SHOWN_ATTRIBUTES = ("title", "aria-label", "alt", "placeholder")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        self.parts += [value for name, value in attrs if name in self.SHOWN_ATTRIBUTES and value]

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def shown_text(page: str) -> str:
    """The text a reader of a written page sees, before its script draws anything."""
    reader = _Shown()
    reader.feed(page)
    return " ".join(" ".join(reader.parts).split())
