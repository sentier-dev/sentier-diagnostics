"""The rule at its edges: pairs on, just under and just over every edge of `rule.judge`, which
the page's port of the rule is held to (`tests/js/page.test.js`). The acceptance cases say
what the rule must do; these say where exactly it changes its mind, down to the last bit, so
that a port that rounds one edge differently is found before a reader sees a class the file
would not give.

Every edge: the tolerance, the noise (and no noise, and a noise of 0), the floor on either
side and both sides, a sign crossing (and zeros of both signs), ten times, every band edge,
factors too large or too small for a float, subnormal results, and a missing side. Each pair
is also written mirrored (after and before swapped) and below zero.

The fixture `fixtures/boundaries.json` is written by

    PYTHONPATH=src python3 -m tests.test_boundaries write
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import chain, claims, cli, example, fileformat, from_tables, rule, summary

FIXTURE = Path(__file__).parent / "fixtures" / "boundaries.json"
TOLERANCE = 1e-5
NOISE = 0.03
#: sizes the edges are taken at: an ordinary result, a small and a large one
SIZES = (1.0, 3.7e-12, 2.5e8)


def near(x: float, steps: int = 2) -> list[float]:
    """x and the floats next to it, `steps` on each side."""
    out = [x]
    down = up = x
    for _ in range(steps):
        down, up = math.nextafter(down, -math.inf), math.nextafter(up, math.inf)
        out[:0] = [down]
        out.append(up)
    return out


def pairs():
    """(why, before, after, floor, tolerance, noise) at every edge, before mirroring."""
    for size in SIZES:
        for after in near(size / (1 - TOLERANCE)):
            yield "the tolerance", size, after, 0.0, TOLERANCE, None
        for after in near(size / (1 - NOISE)):
            yield "the noise", size, after, 0.0, TOLERANCE, NOISE
            yield "a noise of 0 is none", size, after, 0.0, TOLERANCE, 0.0
        for factor in (1.1, 1.25, 2.0, 10.0):
            for after in near(size * factor):
                yield f"the band edge at {factor}", size, after, 0.0, TOLERANCE, None
        for floor in near(size):
            # its mirror is the floor after; twenty times: across the floor it has no ratio
            yield "the floor before", size, 20 * size, floor, TOLERANCE, None
            # five times: across the floor or not, the ratio classes it (issue #38)
            yield "the floor before, within ten times", size, 5 * size, floor, TOLERANCE, None
            yield "the floor on both sides", size, size * 0.5, floor, TOLERANCE, None
            # crossing the floor by less than the tolerance agrees (SPEC A26)
            yield "across the floor within the tolerance", size * (1 + 4e-6), size * (1 - 4e-6), floor, TOLERANCE, None
        for after in near(10 * size):
            # the side before within the floor: ten times is a ratio, more is from zero
            yield "across the floor at ten times", size, after, size, TOLERANCE, None
        for after in near(-size):
            yield "a sign crossing", size, after, 0.0, TOLERANCE, None
            yield "a sign crossing within the floor", size, after, size, TOLERANCE, None
    for before, after in ((0.0, -0.0), (0.0, 0.0), (5e-324, -5e-324), (0.0, 1.0), (1.0, 0.0), (-0.0, 2.0)):
        yield "zeros", before, after, 0.0, TOLERANCE, None
    # edges hit exactly: 0.75 against 1.0 lies 0.25 apart in exact arithmetic
    for before in near(0.75):
        yield "the noise, exactly", before, 1.0, 0.0, TOLERANCE, 0.25
        yield "the tolerance, exactly", before, 1.0, 0.0, 0.25, None
    yield "a tolerance of 0", 1.0, 1.0, 0.0, 0.0, None
    for after in near(1.0):
        yield "a tolerance of 0", 1.0, after, 0.0, 0.0, None
    for before, after in ((1e-300, 1e300), (1e300, 1.7976931348623157e308), (5e-324, 1.0), (1e-310, 2e-310),
                          (1e-310, 1e-309), (2.2250738585072014e-308, 2.2250738585072014e-307), (5e-324, 1e-323)):  # fmt: skip
        yield "a factor too large or too small for a float", before, after, 0.0, TOLERANCE, None
    for before, after in ((None, 1.0), (1.0, None), (None, None)):
        yield "a missing side", before, after, 0.0, TOLERANCE, None


def cases() -> list[dict]:
    out, seen = [], set()

    def neg(v):
        return None if v is None else -v

    for why, before, after, floor, tolerance, noise in pairs():
        for b, a in ((before, after), (after, before), (neg(before), neg(after)), (neg(after), neg(before))):
            key = (repr(b), repr(a), floor, tolerance, noise)
            if key in seen:
                continue
            seen.add(key)
            kind, way, band = rule.judge(b, a, floor=floor, tolerance=tolerance, noise=noise)
            out.append({"why": why, "before": b, "after": a, "floor": floor, "tolerance": tolerance, "noise": noise,
                        "class": kind, "direction": way, "band": band})  # fmt: skip
    return out


def fixture() -> dict:
    return {
        "about": "Pairs at every edge of rule.judge, written by tests/test_boundaries.py; the page's rule is held to them.",
        "cases": cases(),
    }


class Boundaries(unittest.TestCase):
    def test_the_fixture_is_what_the_rule_gives(self):
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8")), json.loads(json.dumps(fixture())))

    def test_within_ten_times_the_floor_changes_no_class(self):
        # a pair of one sign within ten times is classed by its ratio, wherever the floor lies
        found = {(c["class"], c["band"]) for c in cases() if c["why"] == "the floor before, within ten times"}
        self.assertEqual({k for k, _ in found}, {rule.DIFFERS})

    def test_every_class_and_every_band_is_reached(self):
        found = cases()
        self.assertEqual({c["class"] for c in found}, set(rule.CLASSES))
        self.assertEqual({c["band"] for c in found} - {None}, set(rule.BANDS))

    def test_each_edge_is_crossed(self):
        # an edge whose neighbours all fall on one side tests nothing: each must split
        by_edge = {}
        for c in cases():
            by_edge.setdefault(c["why"], set()).add((c["class"], c["band"]))
        for why in ("the tolerance", "the noise", "the band edge at 1.1", "the band edge at 1.25", "the band edge at 2.0",
                    "the band edge at 10.0", "the floor before", "the floor on both sides", "across the floor at ten times",
                    "the noise, exactly", "the tolerance, exactly"):  # fmt: skip
            with self.subTest(why):
                self.assertGreater(len(by_edge[why]), 1, why)


class OtherEdges(unittest.TestCase):
    """The other edges a reader meets, each taken on it and just past it (issue 15: one-line
    mutations of `<=` to `<` or `>` to `>=` here went unnoticed): a claim's largest change,
    the floor a noise is measured beyond, the mark of a large noise, closer and further, the
    12 MB of a file and the 200 items a description lists unless it says otherwise."""

    def test_a_change_of_exactly_a_claims_largest_is_within_it(self):
        entry = claims.scope(["a"], "*", "up", 0.5, claims.MAY)
        self.assertEqual(rule.change(1.0, 1.5), 0.5)
        self.assertTrue(claims.fits(entry, 1.0, 1.5, "up"))
        self.assertFalse(claims.fits(entry, 1.0, math.nextafter(1.5, 2.0), "up"))

    def test_a_noise_is_measured_beyond_its_floor_not_on_it(self):
        self.assertIsNone(chain.noise_of({"a": 0.01}, {"a": 0.02}, floor=0.01))
        self.assertIsNotNone(chain.noise_of({"a": math.nextafter(0.01, 1.0)}, {"a": 0.02}, floor=0.01))

    def test_a_noise_of_exactly_the_large_mark_is_not_called_large(self):
        names = {"a": "A"}
        said = lambda size: summary.noise_text({"measured": True, "between": ["x", "y"], "by": {"a": size}}, names)  # noqa: E731
        self.assertEqual(chain.LARGE_NOISE, 0.01)  # SPEC 5.3: above 1 % a noise is large
        self.assertNotIn("(large)", said(0.01))
        self.assertIn("(large)", said(math.nextafter(0.01, 1.0)))

    def test_closer_and_further_may_add_up_to_what_moved_and_no_more(self):
        data = example.build()
        step = next(s for s in data["steps"] if s["id"] == "fix-1")
        block = copy.deepcopy(data["counts"]["steps"]["fix-1"]["x:climate"])
        moved = sum(block["classes"][k] for k in rule.MOVES)
        self.assertGreater(moved, 0)
        block.update(closer=moved, further=0)
        self.assertEqual([e for e in fileformat._block(block, "b", step) if "closer" in e], [])
        block.update(further=1)
        self.assertIn("b: more came closer or went further than moved", fileformat._block(block, "b", step))

    def test_a_file_of_12_mb_is_checked_and_one_byte_more_refused(self):
        # written as SPEC says it, not taken from the constant, so that a change of the
        # constant is a change a test sees
        limit = 12 * 1024 * 1024
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            text = chain.dumps(example.build())
            for size, code in ((limit, 0), (limit + 1, 1)):
                path.write_text(text + " " * (size - len(text.encode())), encoding="utf-8")
                self.assertEqual(path.stat().st_size, size)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.check([path]), code, size)

    def test_a_description_lists_200_items_unless_it_says_otherwise(self):
        many = 205
        spec = {"title": "t", "item": {"one": "i", "many": "is"},
                "indicators": [{"id": "x:a", "name": "A", "short": "A", "unit": "m3"}], "items": "items.csv",
                "states": [{"id": "s0", "label": "0", "results": "s0.csv"}, {"id": "s1", "label": "1", "results": "s1.csv"}],
                "steps": [{"id": "st", "label": "step", "kind": "method"}]}  # fmt: skip
        tables_ = {"items.csv": ["item,unit"] + [f"p{k},kg" for k in range(many)],
                   "s0.csv": ["item,x:a"] + [f"p{k},{1.0 + k}" for k in range(many)],
                   "s1.csv": ["item,x:a"] + [f"p{k},{2.0 * (1.0 + k)}" for k in range(many)]}  # fmt: skip
        with tempfile.TemporaryDirectory() as folder:
            for name, lines in tables_.items():
                (Path(folder) / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
            (Path(folder) / "d.json").write_text(json.dumps(spec), encoding="utf-8")
            data = from_tables.build(Path(folder) / "d.json")
        self.assertEqual(data["items_count"]["qualifying"], many)
        self.assertEqual(data["items_count"]["listed"], 200)
        self.assertEqual(len(data["items"]), 200)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["write"]:
        FIXTURE.write_text(json.dumps(fixture(), indent=0, sort_keys=True) + "\n", encoding="utf-8")
    else:
        unittest.main()
