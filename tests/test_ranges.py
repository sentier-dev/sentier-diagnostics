"""Ranges: runs of consecutive steps, each compared as the whole way is (SPEC section 5.5)."""

from __future__ import annotations

import json
import tempfile
import unittest
import warnings
from pathlib import Path

from sentier_diagnostics import chain, claims, fileformat, from_tables, matrix, rule

from . import helpers
from .helpers import A, B

STEPS = ("one", "two", "three", "four")
#: `q` moves by 0.8% a step, under the 1% tolerance of each, up twice and down twice: no
#: step and not the whole way moves it, and the runs one..two and three..four do, by 1.6%.
Q = [1.0, 1.008, 1.016, 1.008, 1.0]
#: `p` moves once, in step two, by half.
P = [2.0, 2.0, 1.0, 1.0, 1.0]
#: `r` does not move.
R = [3.0, 3.0, 3.0, 3.0, 3.0]


def five_states(ranges="all", claim=None, **more):
    """A chain of five states and four steps, each with a tolerance of 1%."""
    states = [chain.state(f"s{n}", f"State {n}", kind="published" if n == 0 else "build") for n in range(5)]
    steps = [
        chain.step(sid, f"Step {sid}", kind="fix", tolerance=chain.tolerance(0.01 if sid != "three" else 0.02),
                   claim=claim if sid == "two" else None)
        for sid in STEPS
    ]  # fmt: skip
    values = {
        f"s{n}": {A: {"p": P[n], "q": Q[n], "r": R[n]}, B: {"p": R[n], "q": R[n], "r": R[n]}} for n in range(5)
    }
    return chain._build(
        "Five states",
        indicators=helpers.INDICATORS,
        states=states,
        steps=steps,
        values=values,
        units=dict.fromkeys("pqr", "kg"),
        ranges=ranges,
        **more,
    )


def at(data, range_id):
    """Where a range stands in an item's lists: after the steps and the total."""
    return len(data["steps"]) + 1 + [r["id"] for r in data["ranges"]].index(range_id)


class Build(unittest.TestCase):
    def setUp(self):
        self.data, _ = five_states()

    def test_every_run_of_two_or_more_steps_but_the_whole_way(self):
        self.assertEqual(
            [r["id"] for r in self.data["ranges"]],
            ["one..two", "one..three", "two..three", "two..four", "three..four"],
        )
        first = self.data["ranges"][1]
        self.assertEqual(first["steps"], ["one", "two", "three"])
        self.assertEqual((first["from"], first["to"]), ("s0", "s3"))

    def test_a_range_takes_the_largest_tolerance_of_its_steps_and_no_noise(self):
        tolerance = {r["id"]: r["tolerance"] for r in self.data["ranges"]}
        self.assertEqual(tolerance, {"one..two": 0.01, "one..three": 0.02, "two..three": 0.02,
                                     "two..four": 0.02, "three..four": 0.02})  # fmt: skip

    def test_a_range_moves_where_each_of_its_steps_agrees(self):
        q = next(i for i in self.data["items"] if i["id"] == "q")
        steps_and_total = q["classes"][A][: len(STEPS) + 1]
        self.assertEqual(set(steps_and_total), {rule.AGREES})
        self.assertEqual(q["classes"][A][at(self.data, "one..two")], rule.DIFFERS)
        self.assertEqual(q["directions"][A][at(self.data, "one..two")], rule.UP)
        self.assertEqual(q["directions"][A][at(self.data, "two..four")], None)  # 1.008 to 1.0: under 2%
        # q is worth a look for its ranges alone, and listed; p moves in one..two by its step two
        self.assertEqual(self.data["counts"]["ranges"]["one..two"][A]["classes"][rule.DIFFERS], 2)

    def test_a_range_has_no_verdict_and_no_closer_or_further(self):
        claim = claims.claim("p goes down.", [claims.scope([A], {"p"}, "down", None, claims.MUST)],
                             by=claims.origin("person", "A. Author"))  # fmt: skip
        data, _ = five_states(claim=claim)
        for block in data["counts"]["ranges"]["two..three"].values():
            self.assertEqual((block["verdicts"], block["closer"], block["further"]), (None, None, None))
        self.assertIsNotNone(data["counts"]["steps"]["two"][A]["verdicts"])
        p = next(i for i in data["items"] if i["id"] == "p")
        self.assertEqual(len(p["verdicts"][A]), len(STEPS))

    def test_no_ranges_says_none_was_asked_for(self):
        data, _ = five_states(ranges=None)
        self.assertEqual(data["ranges"], [])  # not left out: that is a file made before ranges
        self.assertEqual(data["counts"]["ranges"], {})
        self.assertEqual(fileformat.errors(data), [])

    def test_a_file_made_before_ranges_and_one_that_asked_for_none_are_kept_apart(self):
        data, _ = five_states(ranges=None)
        before = json.loads(json.dumps(data))
        del before["ranges"], before["counts"]["ranges"]
        self.assertEqual(fileformat.errors(before), [])  # a file made before ranges still reads
        for broken, says in (
            (lambda d: d.update(ranges=None), "`ranges` is a list"),
            (lambda d: d["counts"].pop("ranges"), "`counts` is not"),  # [] without its counts
            (lambda d: d.pop("ranges"), "`counts` is not"),  # counts of ranges, and no key
        ):
            one = json.loads(json.dumps(data))
            broken(one)
            self.assertTrue(any(says in e for e in fileformat.errors(one)), says)
        self.assertEqual(len(data["items"][0]["classes"][A]), len(STEPS) + 1)
        self.assertNotIn("q", [i["id"] for i in data["items"]])  # nothing moved it without its ranges

    def test_auto_is_every_range_up_to_eight_steps_and_none_beyond(self):
        def steps(n):
            return [{"id": f"k{k}", "from": f"s{k}", "to": f"s{k + 1}", "tolerance": {"value": 0.01}}
                    for k in range(n)]  # fmt: skip

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # every range up to the limit, and not a word
            self.assertEqual(len(chain._ranges("auto", steps(chain.AUTO_RANGES))), 8 * 7 // 2 - 1)
        # past the limit none, and the build says so: a ninth step does not drop them unseen
        with self.assertWarnsRegex(UserWarning, r"a chain of 9 steps has no ranges unless asked"):
            self.assertEqual(chain._ranges("auto", steps(chain.AUTO_RANGES + 1)), [])
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # asked for none: nothing to warn of
            self.assertEqual(chain._ranges(None, steps(chain.AUTO_RANGES + 1)), [])
        self.assertEqual(chain._ranges("auto", steps(1)), [])
        self.assertEqual(chain._ranges("auto", steps(2)), [])  # the one run of two is the whole way

    def test_ranges_within_two_steps(self):
        steps = [{"id": s} for s in STEPS]
        self.assertEqual(chain.ranges_within(steps, "two", "four"),
                         [("two", "three"), ("two", "four"), ("three", "four")])  # fmt: skip
        data, _ = five_states(ranges=chain.ranges_within(steps, "two", "four"))
        self.assertEqual([r["id"] for r in data["ranges"]], ["two..three", "two..four", "three..four"])

    def test_ranges_asked_for_wrongly_are_refused(self):
        for said, words in (
            ([("one", "one")], "at least two steps"),
            ([("three", "two")], "at least two steps"),
            ([("one", "four")], "the whole way"),
            ([("one", "five")], "of this chain"),
            ([("one", "two"), ("one", "two")], "twice"),
            ("some", "not 'some'"),
        ):
            with self.subTest(said):
                with self.assertRaises(ValueError) as caught:
                    five_states(ranges=said)
                self.assertIn(words, str(caught.exception))


class Validator(unittest.TestCase):
    """Every change a range can suffer is found, and none stops the check."""

    def setUp(self):
        self.data, _ = five_states()
        self.assertEqual(fileformat.errors(self.data), [])

    def finds(self, change, words):
        found = fileformat.errors(helpers.mutated(self.data, change))
        self.assertTrue(found, "nothing found")
        self.assertFalse([e for e in found if e.startswith(fileformat.STOPPED)], found)
        self.assertTrue(any(words in e for e in found), found)

    def test_changes_to_a_range(self):
        def item(d, name):
            return next(i for i in d["items"] if i["id"] == name)

        def recount(d, range_id):
            """One pair that differs, counted as one that agrees, consistently: only the
            listed items can say it is wrong."""
            block = d["counts"]["ranges"][range_id][A]
            q = item(d, "q")
            block["classes"][rule.DIFFERS] -= 1
            block["classes"][rule.AGREES] += 1
            block["directions"][q["directions"][A][at(d, range_id)]] -= 1
            block["bands"][q["bands"][A][at(d, range_id)]] -= 1

        cases = {
            "an id that is not its steps": (lambda d: d["ranges"][0].update(id="one..three"), "first and last step"),
            "steps that are not consecutive": (lambda d: d["ranges"][1].update(steps=["one", "three"]), "consecutive"),
            "a state it does not lead from": (lambda d: d["ranges"][0].update(**{"from": "s1"}), "does not lead"),
            "a tolerance that is not its steps'": (lambda d: d["ranges"][0].update(tolerance=0.5), "largest tolerance"),
            "a tolerance that is not a share": (lambda d: d["ranges"][0].update(tolerance=[]), "a range is not"),
            "a range of one step": (lambda d: d["ranges"][0].update(id="one..one", steps=["one"]), "at least two"),
            "a range of every step": (
                lambda d: d["ranges"][0].update(id="one..four", steps=list(STEPS), to="s4", tolerance=0.02),
                "the whole way",
            ),
            "a range twice": (lambda d: d["ranges"].append(dict(d["ranges"][0])), "another range"),
            "counts without a range": (lambda d: d["counts"]["ranges"].pop("two..three"), "every range"),
            "counts of ranges the file does not have": (lambda d: d.pop("ranges"), "only where"),
            "a range class rewritten": (
                lambda d: item(d, "q")["classes"][A].__setitem__(at(d, "one..two"), rule.AGREES),
                "the rule gives",
            ),
            "a range count moved": (lambda d: recount(d, "one..two"), "in the listed items"),
            "verdicts in a range": (
                lambda d: d["counts"]["ranges"]["one..two"][A].update(verdicts=dict.fromkeys(claims.VERDICTS, 0)),
                "verdicts without a claim",
            ),
            "closer in a range": (
                lambda d: d["counts"]["ranges"]["one..two"][A].update(closer=0, further=0),
                "null everywhere else",
            ),
            "an item one range short": (lambda d: [item(d, "q")[k][A].pop() for k in ("classes", "directions", "bands")],
                                        "each range"),  # fmt: skip
        }
        for name, (change, words) in cases.items():
            with self.subTest(name):
                self.finds(change, words)

    def test_values_of_any_type_in_a_range_never_stop_the_check(self):
        odd = ([], {}, [[]], {"a": 1}, "x", -1, 1.5, True, None, 10**400, [None])
        data = json.loads(json.dumps(self.data))
        for n in range(len(data["ranges"])):
            for key in fileformat.RANGE_KEYS:
                kept = data["ranges"][n][key]
                for value in odd:
                    data["ranges"][n][key] = value
                    found = fileformat.errors(data)
                    self.assertFalse([e for e in found if e.startswith(fileformat.STOPPED)], (key, value, found))
                data["ranges"][n][key] = kept
        for value in odd:
            data["ranges"] = value
            found = fileformat.errors(data)
            self.assertFalse([e for e in found if e.startswith(fileformat.STOPPED)], (value, found))


class Matrix(unittest.TestCase):
    def setUp(self):
        self.data, self.full = five_states(matrix_file="matrix.json")

    def test_the_matrix_holds_each_range_and_agrees_with_its_file(self):
        self.assertEqual(self.full["of"]["ranges"], [r["id"] for r in self.data["ranges"]])
        ncodes = len(STEPS) + 1 + len(self.data["ranges"])
        self.assertTrue(all(len(c) == 2 * ncodes for c in self.full["classes"]))
        self.assertEqual(matrix.errors(self.full), [])
        self.assertEqual(matrix.against(self.full, self.data), [])

    def test_a_result_equal_to_the_one_before_is_written_as_the_same(self):
        r = self.full["values"][[row[0] for row in self.full["items"]].index("r")]
        self.assertEqual(r, [3.0, "=", "=", "=", "=", 3.0, "=", "=", "=", "="])
        with tempfile.TemporaryDirectory() as tmp:
            path = matrix.write(self.full, Path(tmp) / "matrix.json")
            self.assertEqual(matrix.read(path, self.data), self.full)

    def test_changes_are_found(self):
        q = [row[0] for row in self.full["items"]].index("q")

        def flip(m):
            codes = m["classes"][q]
            where = len(STEPS) + 1  # the first range of the first indicator
            m["classes"][q] = codes[:where] + ("=" if codes[where] != "=" else "D") + codes[where + 1 :]

        cases = {
            "a range code": (flip, matrix.against),
            "the ranges named in another order": (lambda m: m["of"]["ranges"].reverse(), matrix.against),
            "one range code too few": (lambda m: m["classes"].__setitem__(q, m["classes"][q][:-1]), matrix.errors),
            "= first in an indicator": (lambda m: m["values"][q].__setitem__(5, "="), matrix.errors),
            "= after a missing result": (
                lambda m: m["values"][q].__setitem__(1, None) or m["values"][q].__setitem__(2, "="),
                matrix.errors,
            ),
        }
        for name, (change, check) in cases.items():
            with self.subTest(name):
                changed = helpers.mutated(self.full, change)
                found = check(changed, self.data) if check is matrix.against else check(changed)
                self.assertNotEqual(found, [], name)
                self.assertNotIn(fileformat.STOPPED, found)

    def test_counts_of_a_range_are_what_the_matrix_holds(self):
        def moved(d):
            block = d["counts"]["ranges"]["three..four"][B]["classes"]
            block[rule.AGREES] -= 1
            block[rule.NEAR_ZERO] += 1

        changed = helpers.mutated(self.data, moved)
        self.assertIn("counts of 'three..four' in 'x:b': `classes` is not what the matrix holds",
                      matrix.against(self.full, changed))  # fmt: skip


class Description(unittest.TestCase):
    def write(self, tmp, ranges):
        here = Path(tmp)
        (here / "items.csv").write_text("item,unit\np,kg\nq,kg\n", encoding="utf-8")
        for n in range(4):
            (here / f"s{n}.csv").write_text(f"item,{A}\np,{P[n]}\nq,{Q[n]}\n", encoding="utf-8")
        spec = {
            "title": "Four states",
            "indicators": [{"id": A, "name": "Indicator A"}],
            "items": "items.csv",
            "states": [{"id": f"s{n}", "label": f"State {n}", "results": f"s{n}.csv"} for n in range(4)],
            "steps": [{"id": s, "label": s, "kind": "fix"} for s in STEPS[:3]],
        }
        if ranges is not None:
            spec["ranges"] = ranges
        path = here / "description.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def test_a_description_chooses_its_ranges(self):
        for said, ids in (
            (None, ["one..two", "two..three"]),
            ("none", []),
            ([["two", "three"]], ["two..three"]),
            ({"within": ["one", "two"]}, ["one..two"]),
        ):
            with self.subTest(said), tempfile.TemporaryDirectory() as tmp:
                data = from_tables.build(self.write(tmp, said))
                self.assertEqual([r["id"] for r in data["ranges"]], ids)

    def test_a_wrong_choice_is_a_sentence(self):
        for said in ("every", [["one"]], [["one", "nine"]], {"within": ["one"]}, {"from": ["one", "two"]}):
            with self.subTest(said), tempfile.TemporaryDirectory() as tmp:
                path = self.write(tmp, said)
                spec = json.loads(path.read_text())
                self.assertTrue(any("`ranges`" in e for e in from_tables.description_errors(spec)))


if __name__ == "__main__":
    unittest.main()
