"""The acceptance cases of SPEC.md: one test (or one shared case) for each defect found in
the tools this one replaces, and for each rule the sessions asked for. The pair cases in
`acceptance/cases.json` are run here against the Python rule and in `js/page.test.js`
against the page script."""

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import breakdown, chain, claims, example, fileformat, rule, tables

from . import helpers
from .helpers import A, B

HERE = Path(__file__).parent
CASES = json.loads((HERE / "acceptance" / "cases.json").read_text(encoding="utf-8"))["cases"]
PAGE = HERE.parent / "src" / "sentier_diagnostics" / "page"


class PairCases(unittest.TestCase):
    """A1, A2, A3, A4, A5, A7, A10, A11: the shared cases, against the rule."""

    def test_every_case(self):
        self.assertGreaterEqual(len(CASES), 15)
        for case in CASES:
            with self.subTest(case["id"]):
                found = rule.judge(case["before"], case["after"], floor=case["floor"],
                                   tolerance=case["tolerance"], noise=case["noise"])  # fmt: skip
                self.assertEqual(found, (case["class"], case["direction"], case["band"]), case["from"])
                self.assertEqual(list(rule.severity(case["before"], case["after"], case["class"])), case["severity"])

    def test_every_class_has_a_case(self):
        self.assertEqual({c["class"] for c in CASES}, set(rule.CLASSES))


class Acceptance(unittest.TestCase):
    def test_a01_direction_is_the_sign_of_after_minus_before(self):
        """A1: going further below zero is down, whatever the ratio says."""
        for before, after, way in ((-2.0, -4.0, "down"), (-4.0, -2.0, "up"), (2.0, 4.0, "up"), (4.0, 2.0, "down")):
            kind = rule.classify(before, after)
            self.assertEqual(rule.direction(before, after, kind), way)

    def test_a02_the_file_carries_the_class_and_the_floor(self):
        """A2: what is listed as moved is what the rule counted with its floor; a page never
        recounts. A value below its floor in a file is near zero, and the validator refuses
        a file that says otherwise."""
        data = helpers.two_states({A: {"p": 1e-12, "q": 1.0}}, {A: {"p": 5e-12, "q": 2.0}},
                                  floors={(A, "kg"): 1e-9})  # fmt: skip
        listed = {i["id"]: i for i in data["items"]}
        self.assertEqual(listed["p"]["classes"][A], [rule.NEAR_ZERO, rule.NEAR_ZERO])
        self.assertEqual(data["counts"]["steps"]["one"][A]["classes"]["near zero"], 1)
        floors = {(f["indicator"], f["unit"]): f for f in data["rule"]["floors"]}
        self.assertEqual(floors[(A, "kg")]["value"], 1e-9)
        self.assertEqual(floors[(A, "kg")]["basis"], "declared")

    def test_a03_solver_noise_agrees(self):
        """A3: 1e-6 is within the default tolerance; measured noise has a class of its own."""
        self.assertEqual(rule.classify(1.0, 1.000001), rule.AGREES)
        self.assertEqual(rule.classify(1.0, 1.0002, noise=3e-4), rule.WITHIN_NOISE)
        self.assertGreater(rule.DEFAULT_TOLERANCE, 1e-6)

    def test_a04_beyond_ten_is_never_blanked(self):
        """A4: a factor of 25 is a class and a band, and its item is listed."""
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 25.0}})
        self.assertEqual(data["counts"]["total"][A]["classes"][rule.BEYOND], 1)
        self.assertEqual(data["items"][0]["classes"][A], [rule.BEYOND, rule.BEYOND])
        self.assertEqual(data["items"][0]["values"][A], [1.0, 25.0])

    def test_a05_near_zero_is_not_agreement(self):
        """A5: two results below the floor are near zero, a class of their own."""
        self.assertEqual(rule.classify(1e-10, 3e-10, floor=1e-9), rule.NEAR_ZERO)
        self.assertNotEqual(rule.NEAR_ZERO, rule.AGREES)
        data = helpers.two_states({A: {"p": 0.0, "q": 1.0}}, {A: {"p": 0.0, "q": 1.0}})
        classes = data["counts"]["total"][A]["classes"]
        self.assertEqual((classes["near zero"], classes["agrees"]), (1, 1))

    def test_a06_floors_are_kept_per_reference_unit(self):
        """A6: a result per machine hour and a result per kilogram are never pooled."""
        before = {A: {"kg1": 100.0, "kg2": 200.0, "mj1": 0.001, "mj2": 0.002}}
        after = {A: {"kg1": 100.0, "kg2": 200.0, "mj1": 0.002, "mj2": 0.002}}
        units = {"kg1": "kg", "kg2": "kg", "mj1": "MJ", "mj2": "MJ"}
        data = helpers.two_states(before, after, units=units)
        floors = {(f["indicator"], f["unit"]): f["value"] for f in data["rule"]["floors"]}
        self.assertAlmostEqual(floors[(A, "kg")], 1.5)
        self.assertAlmostEqual(floors[(A, "MJ")], 1.5e-5)
        mj1 = next(i for i in data["items"] if i["id"] == "mj1")
        self.assertEqual(mj1["classes"][A][0], rule.DIFFERS)  # pooled, it would be near zero

    def test_a07_missing_is_never_zero(self):
        """A7: a result missing on one side is missing, in the counts and in the list."""
        data = helpers.two_states({A: {"p": 0.5, "q": 1.0}}, {A: {"p": None, "q": 1.0}})
        block = data["counts"]["steps"]["one"][A]
        self.assertEqual(block["classes"]["missing"], 1)
        self.assertEqual(block["missing"], {"before": 0, "after": 1, "both": 0})
        self.assertEqual(data["items"][0]["values"][A], [0.5, None])
        self.assertEqual(rule.classify(None, 0.0), rule.MISSING)

    def test_a08_columns_are_read_by_name(self):
        """A8: two tables with their columns in another order are read alike."""
        with tempfile.TemporaryDirectory() as folder:
            one, two = Path(folder) / "one.csv", Path(folder) / "two.csv"
            one.write_text("item,x:a,x:b\np,1.5,2\nq,,3\n", encoding="utf-8")
            two.write_text("x:b,item,x:a\n2,p,1.5\n3,q,\n", encoding="utf-8")
            self.assertEqual(tables.read_results(one, [A, B]), tables.read_results(two, [A, B]))

    def test_a09_every_explanation_says_who_wrote_it(self):
        """A9: an explanation without its origin is refused; a model's names the model and
        who ran it, and the page says that it is a claim nobody checked."""
        data = example.build()
        self.assertEqual(fileformat.errors(data), [])
        unsigned = helpers.mutated(data, lambda d: d["explanations"][0].update(by=None))
        self.assertTrue(any("says who wrote it" in e for e in fileformat.errors(unsigned)))
        half = helpers.mutated(data, lambda d: d["explanations"][2]["by"].update(run_by=None))
        self.assertTrue(fileformat.errors(half))
        script = (PAGE / "diagnostics.js").read_text(encoding="utf-8")
        self.assertIn("A claim, not checked by a person", script)

    def test_a10_zero_and_sign_change_are_apart(self):
        self.assertEqual(rule.classify(0.0, 1.0), rule.ZERO_REFERENCE)
        self.assertEqual(rule.classify(1.0, 0.0), rule.ZERO_RESULT)
        self.assertEqual(rule.classify(-1.0, 1.0), rule.SIGN_CHANGE)
        self.assertIsNone(rule.band(-1.0, 1.0, rule.SIGN_CHANGE))

    def test_a11_results_are_not_rounded_before_the_ratio(self):
        """A11: 0.00104 and 0.00096 are both 0.001 at three decimals, and 8 % apart."""
        self.assertEqual(rule.classify(0.00104, 0.00096), rule.DIFFERS)
        data = helpers.two_states({A: {"p": 0.00104}}, {A: {"p": 0.00096}})
        self.assertEqual(data["items"][0]["values"][A], [0.00104, 0.00096])
        text = chain.dumps(data)
        self.assertIn("0.00104", text)

    def test_a12_not_a_number_is_refused(self):
        with self.assertRaises(ValueError):
            helpers.two_states({A: {"p": math.nan}}, {A: {"p": 1.0}})
        with self.assertRaises(ValueError):
            helpers.two_states({A: {"p": 1.0}}, {A: {"p": math.inf}})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            path.write_text('{"format": "sentier-diagnostics/1", "x": NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                chain.read(path)
            table = Path(folder) / "t.csv"
            table.write_text("item,x:a,x:b\np,nan,1\n", encoding="utf-8")
            with self.assertRaises(tables.TableError):
                tables.read_results(table, [A, B])

    def test_a13_a_missing_indicator_column_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / "t.csv"
            table.write_text("item,x:a\np,1\n", encoding="utf-8")
            with self.assertRaises(tables.TableError):
                tables.read_results(table, [A, B])

    def test_a14_a_breakdown_never_falls_back_silently(self):
        """A14: a breakdown whose totals are not the item's results is refused, and one
        whose parts do not add up is refused."""
        data = example.build()
        good = example.wheat_breakdown()
        self.assertEqual(breakdown.against(good, data), [])
        moved = helpers.mutated(good, lambda d: d["indicators"]["x:climate"]["total"].__setitem__(1, 0.5))
        self.assertTrue(breakdown.against(moved, data))
        self.assertTrue(breakdown.errors(moved))  # the parts no longer add up to it either
        other = helpers.mutated(good, lambda d: d.update(item="p02"))
        self.assertTrue(breakdown.against(other, data))

    def test_a15_breakdown_parts_keep_their_sign(self):
        """A15: a part below zero stays below zero; bars are drawn from the signed value."""
        parts = [("credit", "flow", -0.3, -0.1), ("burden", "flow", 1.0, 1.0)]
        found = breakdown.build("p", "a", "b", {A: ("kg", parts)}, top=5)
        credit = next(p for p in found["indicators"][A]["parts"] if p["label"] == "credit")
        self.assertEqual(credit["values"], [-0.3, -0.1])

    def test_a16_nothing_is_cut_short_silently(self):
        """A16: a list cut at `listed` says how many it left out, and a file that hides
        the cut is refused. A breakdown cut at `top` says how many parts it left out."""
        before = {A: {f"p{k}": 1.0 for k in range(6)}}
        after = {A: {f"p{k}": 2.0 + k for k in range(6)}}
        data = helpers.two_states(before, after, listed=2)
        self.assertEqual(data["items_count"], {"all": 6, "qualifying": 6, "listed": 2, "not_listed": 4})
        hidden = helpers.mutated(data, lambda d: d["items_count"].update(not_listed=0))
        self.assertTrue(fileformat.errors(hidden))
        cut = example.wheat_breakdown()["indicators"]["x:climate"]
        self.assertEqual((len(cut["parts"]), cut["parts_not_listed"]), (5, 3))

    def test_a17_a_file_of_counts_names_no_item(self):
        data = example.build(tier="counts")
        self.assertEqual(data["items"], [])
        self.assertEqual(data["items_count"]["listed"], 0)
        for step in data["steps"]:
            for entry in (step["claim"] or {"scope": []})["scope"]:
                self.assertIn(entry["items"], ("*", None))
        listed = example.build()["items"][:1]
        leaked = helpers.mutated(data, lambda d: d.update(items=listed))
        self.assertTrue(fileformat.errors(leaked))

    def test_a18_the_split_is_exact_and_says_what_it_cannot_split(self):
        """A18: per item, the steps' differences add up to the whole difference exactly;
        an item missing in a state between is counted as not attributable."""
        data = helpers.three_states({A: {"p": 1.0, "q": 1.0}}, {A: {"p": 1.5, "q": None}},
                                    {A: {"p": 1.75, "q": 3.0}}, explained=(True, False))  # fmt: skip
        attribution = data["attribution"][A]
        self.assertEqual(attribution["dominant"], {"one": 1, "two": 0})
        self.assertEqual(attribution["not_attributable"], 1)
        self.assertEqual(attribution["unexplained_moved"], 1)  # p moved in the step nothing explains
        for item in example.build()["items"]:
            for values in item["values"].values():
                if None in values:
                    continue
                steps = sum(values[k + 1] - values[k] for k in range(len(values) - 1))
                self.assertAlmostEqual(steps, values[-1] - values[0], places=12)

    def test_a19_claims_must_and_may(self):
        """A19: only a `must` entry can be unmet; an empty scope says nothing moves; a
        result before of zero cannot be within a relative `largest`."""
        must = claims.scope([A], {"p"}, "down", None, claims.MUST)
        may = claims.scope([A], {"p"}, "down")
        self.assertEqual(may["expect"], claims.MAY)  # the default
        self.assertEqual(claims.verdict(rule.AGREES, 1.0, 1.0, None, [must]), claims.NOT_MOVED)
        self.assertEqual(claims.verdict(rule.AGREES, 1.0, 1.0, None, [may]), claims.UNCHANGED)
        self.assertEqual(claims.verdict(rule.DIFFERS, 1.0, 2.0, "up", []), claims.NOT_CLAIMED)
        capped = claims.scope([A], "*", "up", 0.5)
        self.assertEqual(claims.verdict(rule.ZERO_REFERENCE, 0.0, 1.0, "up", [capped]), claims.OFF_CLAIM)
        uncapped = claims.scope([A], "*", "up")
        self.assertEqual(claims.verdict(rule.ZERO_REFERENCE, 0.0, 1.0, "up", [uncapped]), claims.AS_CLAIMED)
        nothing = claims.claim("Nothing moves.", [], by=claims.origin("code", "rule"))
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, claim=nothing)
        self.assertEqual(data["counts"]["steps"]["one"][A]["verdicts"]["not claimed"], 1)

    def test_a19b_a_claim_list_can_stay_with_its_writer(self):
        """A19: with `claim_lists` false, the file lists the items that moved but not the
        claim's list; the verdicts are kept and cannot be checked again."""
        data = example.build(claim_lists=False)
        self.assertEqual(fileformat.errors(data), [])
        fix = next(s for s in data["steps"] if s["id"] == "fix-1")
        self.assertEqual([e["items"] for e in fix["claim"]["scope"]], [None])
        self.assertEqual(fix["claim"]["reach"], 2)
        self.assertEqual(data["counts"], example.build()["counts"])

    def test_a20_no_field_of_acceptance(self):
        """A20 (sentier-bafu-agribalyse ADR 0010): a file carries no status and no
        `accepted_by`; the validator refuses fields it does not know, anywhere."""
        data = example.build()
        for change in (
            lambda d: d.update(status="accepted"),
            lambda d: d["explanations"][0].update(accepted_by="someone"),
            lambda d: d["steps"][1].update(status="ok"),
            lambda d: d["items"][0].update(status="ok"),
        ):
            self.assertTrue(fileformat.errors(helpers.mutated(data, change)))

    def test_a22_the_reference_is_neutral_after_step_0(self):
        """A22: coming closer to the published results is counted, never called better.
        Step 0 and the whole way have no such count, and the page shows none."""
        data = example.build()
        self.assertIsNone(data["counts"]["steps"]["step-0"]["x:climate"]["closer"])
        self.assertIsNone(data["counts"]["total"]["x:climate"]["closer"])
        for name in ("diagnostics.js", "index.html"):
            text = (PAGE / name).read_text(encoding="utf-8").lower()
            for word in ("better", "worse", "improve", "closer"):
                self.assertNotIn(word, text, f"{name} says {word!r}")

    def test_a23_indicators_are_matched_by_their_exact_id(self):
        """A23: a column `x:a:biogenic` is not the indicator `x:a`."""
        with tempfile.TemporaryDirectory() as folder:
            table = Path(folder) / "t.csv"
            table.write_text("item,x:a:biogenic,x:b\np,1,2\n", encoding="utf-8")
            with self.assertRaises(tables.TableError):
                tables.read_results(table, [A, B])

    def test_a24_a_result_on_one_side_only_is_counted_by_side(self):
        """A24 (sentier-bafu): items on one side only are counted, before and after apart."""
        data = helpers.two_states({A: {"p": 1.0, "q": None}}, {A: {"p": None, "q": 2.0, "r": None}})
        self.assertEqual(data["counts"]["steps"]["one"][A]["missing"], {"before": 1, "after": 1, "both": 1})
        wrong = helpers.mutated(data, lambda d: d["counts"]["steps"]["one"][A]["missing"].update(both=0))
        self.assertTrue(fileformat.errors(wrong))

    def test_a25_a_file_is_local_unless_its_writer_says_otherwise(self):
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}})
        self.assertEqual(data["audience"], "local")
        self.assertEqual(helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, audience="public")["audience"], "public")
        with self.assertRaises(ValueError):
            helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, audience="published")


if __name__ == "__main__":
    unittest.main()
