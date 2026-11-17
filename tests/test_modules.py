"""Unit tests per module: the validator, tables, breakdowns, building from tables, the page
writer, the command and the doctests."""

from __future__ import annotations

import contextlib
import doctest
import importlib
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import breakdown, chain, claims, cli, example, fileformat, from_tables, matrix, page, rule, summary, tables

from . import helpers
from .helpers import A, B

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "tables"
MODULES = ["rule", "claims", "chain", "fileformat", "breakdown", "tables", "summary", "page", "from_tables", "matrix", "together",
           "fixes"]


def load_tests(loader, tests, pattern):
    for name in MODULES:
        tests.addTests(doctest.DocTestSuite(importlib.import_module(f"sentier_diagnostics.{name}")))
    return tests


class Validator(unittest.TestCase):
    """The validator works every listed value out again and refuses a file that disagrees."""

    def setUp(self):
        self.data = example.build()

    def refuses(self, change, says=None):
        found = fileformat.errors(helpers.mutated(self.data, change))
        self.assertTrue(found, "the validator took a wrong file")
        if says:
            self.assertTrue(any(says in e for e in found), found)

    def test_the_example_is_valid(self):
        self.assertEqual(fileformat.errors(self.data), [])

    def test_every_text_too_long_is_refused_and_a_free_text_names_its_limit(self):
        """Issue 19: a title over 120 characters, a label over 80 and an item's name over 300
        were refused without the limit. Each text of the example, made 5000 characters long, is
        refused; each free text says its limit and its length. A word from a fixed list or a
        reference to another part of the file is refused as what it is not."""
        data = example.build()
        free = {"title", "about", "made_by", "label", "note", "name", "short", "unit", "place", "group", "text", "doc",
                "not_checked", "one", "many", "model", "run_by", "id", "commit", "release", "machine"}  # fmt: skip
        lists = [data["notes"]] + [s["noise"]["between"] for s in data["states"] if (s.get("noise") or {}).get("between")]
        named = 0
        for parent, key in list(helpers.nodes(data)):
            if not isinstance(parent[key], str):
                continue
            kept, parent[key] = parent[key], "x" * 5000
            try:
                found = fileformat.errors(data)
            finally:
                parent[key] = kept
            with self.subTest(key=key, was=kept[:40]):
                self.assertTrue(found)
                if key in free or any(parent is one for one in lists) or (key == "kind" and parent in data["steps"]):
                    named += 1
                    self.assertTrue(any(re.search(r"is longer than \d+ characters \(5000\)$", e) for e in found), found[:3])
        self.assertGreater(named, 60)
        # a text the example holds as null, and each limit met exactly, which is allowed
        said = fileformat.errors(helpers.mutated(data, lambda d: d["explanations"][0].update(not_checked="x" * 601)))
        self.assertIn("explanation 1: `not_checked` is longer than 600 characters (601)", said)
        exact = helpers.mutated(data, lambda d: d.update(title="x" * 120, made_by="x" * 60, notes=["x" * 600]))
        exact["steps"][1].update(label="x" * 80, kind="x" * 40)
        exact["items"][0]["name"] = "x" * 300
        self.assertEqual(fileformat.errors(exact), [])

    def test_the_word_for_an_indicator_is_optional_and_checked(self):
        for word in ({"one": "impact category", "many": "impact categories"}, None):
            self.assertEqual(fileformat.errors(helpers.mutated(self.data, lambda d: d.update(indicator=word))), [])
        for wrong in ({"one": "category"}, {"one": "x", "many": "y", "few": "z"}, {"one": "", "many": "y"},
                      {"one": "x" * 31, "many": "y"}, "impact category", ["one", "many"]):  # fmt: skip
            self.refuses(lambda d, w=wrong: d.update(indicator=w), "`indicator")
        self.refuses(lambda d: d.update(indicator={"one": "x" * 31, "many": "y"}), "`indicator.one` is longer than 30 characters (31)")

    def test_a_class_that_contradicts_the_rule(self):
        def change(d):
            item = next(i for i in d["items"] if i["classes"]["x:climate"][-1] == rule.DIFFERS)
            item["classes"]["x:climate"][-1] = rule.AGREES
        self.refuses(change)

    def test_a_verdict_that_contradicts_the_claim(self):
        def change(d):
            item = next(i for i in d["items"] if "as claimed" in i["verdicts"]["x:climate"])
            k = item["verdicts"]["x:climate"].index("as claimed")
            item["verdicts"]["x:climate"][k] = "off claim"
        self.refuses(change)

    def test_a_direction_that_contradicts_the_values(self):
        def change(d):
            item = next(i for i in d["items"] if i["directions"]["x:climate"][-1] == "down")
            item["directions"]["x:climate"][-1] = "up"
        self.refuses(change)

    def test_items_out_of_order(self):
        self.refuses(lambda d: d["items"].reverse(), "worst first")

    def test_counts_that_do_not_add_up(self):
        self.refuses(lambda d: d["counts"]["total"]["x:climate"]["classes"].update(agrees=99), "add up")

    def test_another_major_version(self):
        found = fileformat.errors(helpers.mutated(self.data, lambda d: d.update(format="sentier-diagnostics/2")))
        self.assertEqual(found, ["format 'sentier-diagnostics/2': this reader knows sentier-diagnostics/1 only"])

    def test_an_older_format(self):
        found = fileformat.errors({"format": "sentier/before-after/2"})
        self.assertTrue(found)

    def test_unknown_and_missing_keys(self):
        self.refuses(lambda d: d.update(colour="blue"), "does not know")
        self.refuses(lambda d: d.pop("audience"), "requires")

    def test_a_published_state_after_the_first(self):
        self.refuses(lambda d: d["states"][2].update(kind="published"), "first state")

    def test_a_join_that_is_not_counts(self):
        self.refuses(lambda d: d["states"][0]["join"].update(compared=-1), "join")

    def test_an_explanation_finding(self):
        self.refuses(lambda d: d["explanations"][0].update(finding="accepted"), "finding")

    def test_control_characters_in_text(self):
        self.refuses(lambda d: d.update(title="a\u0000b"))

    def test_values_of_any_type_are_faults_and_never_raise(self):
        """Every node of the example replaced by values of other types: the check returns
        faults that name a place, and never raises or stops without one (issue 4)."""
        data = json.loads(json.dumps(self.data))
        data["items"] = data["items"][:5]  # five items hold every kind of node, and the explained ones
        data["items_count"].update(listed=5, not_listed=data["items_count"]["qualifying"] - 5)
        helpers.replaced_everywhere(self, data, fileformat.errors, stopped=fileformat.STOPPED)
        self.assertEqual(fileformat.errors(data), [])

    def test_a_claim_list_in_a_file_of_counts(self):
        data = example.build(tier="counts")
        listed = example.build()["steps"][1]["claim"]
        found = fileformat.errors(helpers.mutated(data, lambda d: d["steps"][1].update(claim=listed)))
        self.assertTrue(found)


class CountsAgainstItems(unittest.TestCase):
    """Where every item worth a look is listed, the counts are worked out again from the items
    and must match; where some are left out, nothing listed may exceed what is counted. Each
    edit below keeps every sum the validator checked before (sentier-bafu's review of PR 2)."""

    def setUp(self):
        self.data = example.build()
        self.assertEqual(self.data["items_count"]["not_listed"], 0)

    def refuses(self, change, says):
        found = fileformat.errors(helpers.mutated(self.data, change))
        self.assertTrue(any(says in e for e in found), found)

    def test_up_and_down_swapped_with_their_bands(self):
        def change(d):
            b = d["counts"]["steps"]["fix-1"]["x:climate"]
            b["directions"]["up"], b["directions"]["down"] = b["directions"]["down"], b["directions"]["up"]
            swapped = {k.replace("up,", "UP,").replace("down,", "up,").replace("UP,", "down,"): v
                       for k, v in b["bands"].items()}  # fmt: skip
            b["bands"] = {k: swapped[k] for k in b["bands"]}
        self.refuses(change, "listed items")

    def test_verdicts_rewritten_to_as_claimed(self):
        def change(d):
            v = d["counts"]["steps"]["fix-1"]["x:climate"]["verdicts"]
            v["as claimed"] += v["off claim"] + v["not claimed"]
            v["off claim"] = v["not claimed"] = 0
        self.refuses(change, "listed items")

    def test_a_band_count_moved(self):
        def change(d):
            b = d["counts"]["total"]["x:water"]["bands"]
            moved = next(k for k, n in b.items() if n and k.startswith("up"))
            b[moved] -= 1
            b["up, factor 2-10" if moved != "up, factor 2-10" else "up, factor 1-1.1"] += 1
        self.refuses(change, "listed items")

    def test_missing_moved_to_the_other_side(self):
        def change(d):
            for blocks in d["counts"]["steps"].values():
                for b in blocks.values():
                    if b["missing"]["after"]:
                        b["missing"]["before"] += b["missing"]["after"]
                        b["missing"]["after"] = 0
                        return
        self.refuses(change, "listed items")

    def test_attribution_rewritten(self):
        def change(d):
            for one in d["attribution"].values():
                total = sum(one["dominant"].values())
                one["dominant"] = dict.fromkeys(one["dominant"], 0) | {"rebuilt": total}
                one["unexplained_moved"] = 0
        self.refuses(change, "attribution")

    def test_closer_and_further_where_none_can_be(self):
        self.refuses(lambda d: d["counts"]["total"]["x:climate"].update(closer=0, further=0), "closer")
        self.refuses(lambda d: d["counts"]["steps"]["step-0"]["x:climate"].update(closer=0, further=0), "closer")

    def test_closer_and_further_rewritten(self):
        def change(d):
            b = d["counts"]["steps"]["fix-1"]["x:climate"]
            b["closer"], b["further"] = b["closer"] + b["further"], 0
        self.refuses(change, "listed items")

    def test_a_reach_that_is_not_the_size_of_the_lists(self):
        self.refuses(lambda d: d["steps"][1]["claim"].update(reach=4900), "reach")

    def test_floors_said_to_come_from_elsewhere(self):
        self.refuses(lambda d: d["rule"].update(floors_from="mapping-2"), "first state")
        self.refuses(lambda d: [f.update(basis="none", n=0) for f in d["rule"]["floors"]], "floor")

    def test_with_items_left_out_nothing_listed_exceeds_the_counts(self):
        data = helpers.two_states({A: {"p": 1.0, "q": 1.0}}, {A: {"p": 2.0, "q": 3.0}}, listed=1)
        self.assertEqual((data["items_count"]["not_listed"], data["items"][0]["id"]), (1, "q"))
        self.assertEqual(fileformat.errors(data), [])

        def change(d):  # q (listed) went up by a factor 3, p (not listed) by 2: say both by 2
            d["counts"]["total"][A]["bands"].update({"up, factor 2-10": 0, "up, factor 1.25-2": 2})
        self.assertEqual(data["counts"]["total"][A]["bands"]["up, factor 2-10"], 1)
        self.refuses_in(data, change, "listed items")

    def refuses_in(self, data, change, says):
        found = fileformat.errors(helpers.mutated(data, change))
        self.assertTrue(any(says in e for e in found), found)


class Tables(unittest.TestCase):
    def write(self, text: str) -> Path:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [p.unlink() for p in folder.iterdir()] and folder.rmdir())
        path = folder / "t.csv"
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_byte_order_mark_is_not_part_of_the_first_column(self):
        found = tables.read_results(self.write("\ufeffitem,x:a,x:b\np,1,2\n"), [A, B])
        self.assertEqual(found, {A: {"p": 1.0}, B: {"p": 2.0}})

    def test_an_empty_cell_is_missing(self):
        found = tables.read_results(self.write("item,x:a,x:b\np,,0\n"), [A, B])
        self.assertEqual(found, {A: {"p": None}, B: {"p": 0.0}})

    def test_refusals(self):
        for text in (
            "item,x:a,x:b,x:c\np,1,2,3\n",  # an unknown column
            "item,x:a,x:a,x:b\np,1,1,2\n",  # a column twice
            "item,x:a,x:b\np,1,2\np,1,2\n",  # an item twice
            "item,x:a,x:b\np,1\n",  # a short row
            "item,x:a,x:b\np,inf,2\n",  # not finite
            "item,x:a,x:b\np,one,2\n",  # not a number
            "item,x:a,x:b\n,1,2\n",  # no item
            "",  # empty
            "item,x:a,x:b\np,1_5,2\n",  # Python reads 1_5 as 15
            "item,x:a,x:b\np,１２,2\n",  # full-width digits
            "item,x:a,x:b\np,٣,2\n",  # Arabic-Indic digits
            "item,x:a,x:b\np,1e-400,2\n",  # a result that is not zero, read as zero
            "item,x:a,x:b\np,0x10,2\n",  # not a decimal
        ):
            with self.subTest(text):
                with self.assertRaises(tables.TableError):
                    tables.read_results(self.write(text), [A, B])

    def test_decimal_numbers_as_machines_write_them(self):
        found = tables.read_results(self.write("item,x:a,x:b\np,-0,+1.5E+3\nq,.5,0e-400\nr,7.,1e-300\n"), [A, B])
        self.assertEqual(found, {A: {"p": 0.0, "q": 0.5, "r": 7.0}, B: {"p": 1500.0, "q": 0.0, "r": 1e-300}})

    def test_items_need_a_unit_column(self):
        with self.assertRaises(tables.TableError):
            tables.read_items(self.write("item,name\np,P\n"))
        found = tables.read_items(self.write("unit,item\nkg,p\n"))
        self.assertEqual(found["p"]["unit"], "kg")


class Breakdowns(unittest.TestCase):
    def test_both_sides_choose_the_parts(self):
        """A part large only after is listed, though it was zero before."""
        parts = [("a", None, 1.0, 1.0), ("b", None, 0.9, 0.9), ("new", None, 0.0, 2.0), ("small", None, 0.1, 0.1)]
        found = breakdown.build("p", "s0", "s1", {A: ("kg", parts)}, top=2)
        entry = found["indicators"][A]
        self.assertEqual([p["label"] for p in entry["parts"]], ["new", "a"])
        self.assertEqual(entry["parts_not_listed"], 2)
        self.assertEqual(entry["rest"], [1.0, 1.0])
        self.assertEqual(entry["total"], [2.0, 4.0])

    def test_values_of_any_type_are_faults_and_never_raise(self):
        """Every node of a breakdown replaced by values of other types (issue 4): a part that
        is not a part (`1`) is a fault, not a TypeError in the sums."""
        good = breakdown.build("p", "s0", "s1", {A: ("kg", [("a", "kind", 0.2, 0.1), ("b", None, 0.3, 0.3), ("c", None, 0.01, 0.0)])}, top=2)
        helpers.replaced_everywhere(self, good, breakdown.errors)
        self.assertEqual(breakdown.errors(good), [])
        for parts in ([1], [{"label": "a", "kind": None, "values": [1.0, 1.0]}, None]):
            bad = helpers.mutated(good, lambda d, p=parts: d["indicators"][A].update(parts=p))
            self.assertIn(f"indicator {A!r}: a part is not {{label, kind, values}}", breakdown.errors(bad))

    def test_each_text_of_a_breakdown_is_a_fault_with_its_part_and_its_length(self):
        """Issue 4: a part's label and kind, the item and states it names and an indicator's
        unit, each taken at its limit and one past it, and of other kinds."""
        good = breakdown.build("p", "s0", "s1", {A: ("kg", [("a", "kind", 0.2, 0.1), ("b", None, 0.3, 0.3)])})
        at = lambda field, value, part=1: helpers.mutated(good, lambda d: d["indicators"][A]["parts"][part].update({field: value}))  # noqa: E731
        self.assertEqual(breakdown.errors(at("label", "x" * breakdown.MAX_PART_LABEL)), [])
        self.assertEqual(breakdown.MAX_PART_LABEL, 300)  # SPEC 9
        self.assertEqual(breakdown.errors(at("kind", "k" * 40)), [])
        where = f"indicator {A!r}, part 1"
        for field, value, said in (
            ("label", "x" * 301, "`label` is longer than 300 characters (301)"),
            ("label", 5, "`label` is not a text"),
            ("label", "", "`label` is empty"),
            ("label", "a\nb", "`label` holds a control character, such as a line break or a tab"),
            ("kind", 7, "`kind` is not a text"),
            ("kind", "k" * 41, "`kind` is longer than 40 characters (41)"),
        ):
            with self.subTest(field=field, value=value):
                self.assertEqual(breakdown.errors(at(field, value)), [f"{where}: {said}"])
        unit = helpers.mutated(good, lambda d: d["indicators"][A].update(unit="u" * 41))
        self.assertEqual(breakdown.errors(unit), [f"indicator {A!r}: `unit` is longer than 40 characters (41)"])
        for value in (-1, 1.5, True, "0", None):
            with self.subTest(parts_not_listed=value):
                bad = helpers.mutated(good, lambda d, v=value: d["indicators"][A].update(parts_not_listed=v))
                self.assertEqual(breakdown.errors(bad), [f"indicator {A!r}: `parts_not_listed` is not a count"])
        for key, value in (("item", "p" * 101), ("from", ""), ("to", 3)):
            with self.subTest(key):
                found = breakdown.errors(helpers.mutated(good, lambda d, k=key, v=value: d.update({k: v})))
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].startswith(f"a breakdown names its item and the two states it compares: `{key}` "), found)

    def test_a_rest_without_parts_left_out(self):
        good = breakdown.build("p", "s0", "s1", {A: ("kg", [("a", None, 1.0, 2.0)])})
        bad = helpers.mutated(good, lambda d: d["indicators"][A].update(rest=[0.5, 0.0], total=[1.5, 2.0]))
        self.assertTrue(breakdown.errors(bad))

    def test_a_breakdown_is_of_the_item_and_step_that_name_it(self):
        data, wheat = example.build(), example.wheat_breakdown()
        self.assertEqual(breakdown.against(wheat, data, ("p01", "fix-1")), [])
        for named_by in (("p05", "fix-1"), ("p01", "total"), ("p01", "mapping-2")):
            with self.subTest(named_by):
                found = breakdown.against(wheat, data, named_by)
                self.assertTrue(any("named by" in e for e in found), found)

    def test_check_refuses_a_breakdown_named_by_another_item(self):
        data = example.build()
        rice = next(i for i in data["items"] if i["id"] == "p05")
        rice["breakdowns"] = {"total": "p01-fix-1.json"}
        folder = Path(tempfile.mkdtemp())
        chain.write(data, folder / chain.FILE)
        breakdown.write(example.wheat_breakdown(), folder / "p01-fix-1.json")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.check([folder / chain.FILE]), 1)
        self.assertIn("named by 'p05'", out.getvalue())
        with self.assertRaises(ValueError):
            page.write(data, folder / "page", {"p01-fix-1.json": example.wheat_breakdown()})


class Attribution(unittest.TestCase):
    """Which step carries an item's whole difference (SPEC 7; issue 8)."""

    def chain_of(self, values, noise):
        """`noise` is that of each built state, in order: a step is compared with the sum of
        its two states' noise, the published results being exact."""
        steps = [chain.step(f"s{k}", f"Step {k}", kind="fix") for k in range(len(noise))]
        return chain.build(
            "Attribution",
            indicators=helpers.INDICATORS,
            states=[chain.state("p", "Published", kind="published")]
            + [chain.state(f"b{k}", f"Build {k}", noise=chain.noise(("x", "y"), {A: n}) if n else None)
               for k, n in enumerate(noise)],  # fmt: skip
            steps=steps,
            values={"p": {A: {"i": values[0]}}} | {f"b{k}": {A: {"i": v}} for k, v in enumerate(values[1:])},
            units={"i": "kg"},
        )

    def test_a_step_that_did_not_move_carries_nothing(self):
        # Build 0's noise is in both its steps: the second moves by 9 %, beyond it
        data = self.chain_of([1.0, 1.045, 1.15], [0.05, None])
        self.assertEqual([data["items"][0]["classes"][A][k] for k in range(3)],
                         [rule.WITHIN_NOISE, rule.DIFFERS, rule.DIFFERS])  # fmt: skip
        self.assertEqual(data["attribution"][A]["dominant"], {"s0": 0, "s1": 1})

    def test_a_whole_way_that_moved_while_no_step_did_is_spread(self):
        data = self.chain_of([1.0, 1.04, 1.08], [0.05, 0.05])
        self.assertEqual(data["items"][0]["classes"][A][2], rule.DIFFERS)
        self.assertEqual(data["attribution"][A]["dominant"], {"s0": 0, "s1": 0})
        self.assertEqual(data["attribution"][A]["spread"], 1)
        self.assertEqual(fileformat.errors(data), [])
        self.assertIn("| Spread over steps |", summary.text(data))

    def chain_items(self, values, noise):
        """Several items along one chain: `values` maps each to its result in every state,
        None where it has none; `noise` is that of each built state, as in `chain_of`."""
        steps = [chain.step(f"s{k}", f"Step {k}", kind="fix") for k in range(len(noise))]
        names = ["p"] + [f"b{k}" for k in range(len(noise))]
        return chain.build(
            "Attribution",
            indicators=helpers.INDICATORS,
            states=[chain.state("p", "Published", kind="published")]
            + [chain.state(f"b{k}", f"Build {k}", noise=chain.noise(("x", "y"), {A: n}) if n else None)
               for k, n in enumerate(noise)],  # fmt: skip
            steps=steps,
            values={name: {A: {i: v[at] for i, v in values.items() if v[at] is not None}} for at, name in enumerate(names)},
            units={i: "kg" for i in values},
        )

    def test_the_largest_step_carries_it_only_where_it_moved_the_item(self):
        # issue 8: the largest step, s2 (0.35), is within its noise; s0 moved by less (0.05)
        # and is not named in its place: in the item view it is 8.3 % of the difference
        data = self.chain_of([1.0, 1.05, 1.25, 1.6], [0.01, 0.3, 0.01])
        self.assertEqual([data["items"][0]["classes"][A][k] for k in range(4)],
                         [rule.DIFFERS, rule.WITHIN_NOISE, rule.WITHIN_NOISE, rule.DIFFERS])  # fmt: skip
        self.assertEqual(data["attribution"][A]["dominant"], {"s0": 0, "s1": 0, "s2": 0})
        self.assertEqual(data["attribution"][A]["spread"], 1)
        self.assertEqual(fileformat.errors(data), [])

    def test_the_summary_and_the_validator_count_the_spread(self):
        data = self.chain_items({
            "i": [1.0, 1.05, 1.25, 1.6],   # largest step within its noise, a smaller one moved: spread
            "k": [1.0, 1.1, 1.3, 1.65],    # the same
            "q": [1.0, 1.0, 1.25, 1.6],    # no step moved: spread
            "j": [1.0, 1.0, 1.0, 2.0],     # carried by s2
            "m": [1.0, 2.0, 2.0, 2.0],     # carried by s0
            "n": [1.0, None, 2.0, 2.0],    # no result in Build 0: not attributable
        }, [0.01, 0.3, 0.01])  # fmt: skip
        said = data["attribution"][A]
        self.assertEqual((said["dominant"], said["spread"], said["not_attributable"]), ({"s0": 1, "s1": 0, "s2": 1}, 3, 1))
        self.assertEqual(fileformat.errors(data), [])
        lines = summary.text(data).splitlines()
        head = next(line for line in lines if "| Spread over steps |" in line)
        row = lines[lines.index(head) + 2]
        cells = dict(zip([c.strip() for c in head.strip("|").split("|")], [c.strip() for c in row.strip("|").split("|")]))
        self.assertEqual((cells["Largest step"], cells["Spread over steps"], cells["Not attributable"]),
                         ("Step 0 (1), Step 2 (1)", "3", "1"))  # fmt: skip
        for change in (dict(spread=2), dict(spread=4), dict(dominant={"s0": 3, "s1": 0, "s2": 1}, spread=1)):
            moved = helpers.mutated(data, lambda d, change=change: d["attribution"][A].update(change))
            self.assertTrue(any("attribution" in e for e in fileformat.errors(moved)), change)

    def test_a_tie_goes_to_the_earlier_step(self):
        data = self.chain_of([1.0, 2.0, 3.0], [None, None])
        self.assertEqual(data["attribution"][A]["dominant"], {"s0": 1, "s1": 0})

    def test_the_validator_works_the_spread_out_again(self):
        data = self.chain_of([1.0, 1.04, 1.08], [0.05, 0.05])
        moved = helpers.mutated(data, lambda d: d["attribution"][A].update(spread=0, dominant={"s0": 1, "s1": 0}))
        self.assertTrue(any("attribution" in e for e in fileformat.errors(moved)))


class FromTables(unittest.TestCase):
    def test_the_fixture_builds(self):
        data = from_tables.build(FIXTURES / "description.json")
        self.assertEqual(fileformat.errors(data), [])
        self.assertEqual(data["audience"], "public")
        step0 = data["counts"]["steps"]["step-0"]
        self.assertEqual(step0["x:water"]["missing"], {"before": 0, "after": 1, "both": 0})
        fix = data["steps"][1]
        self.assertTrue(fix["noise"]["measured"])
        self.assertAlmostEqual(fix["noise"]["by"]["x:water"], 3e-7 / 1.2000004, places=12)
        wheat = next(i for i in data["items"] if i["id"] == "w1")
        self.assertEqual(wheat["verdicts"]["x:climate"], ["unchanged", "as claimed"])
        self.assertEqual(data["explanations"][0]["finding"], "none found")

    def test_the_located_factors_step(self):
        """The first real step sentier-bafu will show, made up: water use and land use may
        move, nothing else does. Both move as claimed; the steel's climate change is not
        claimed."""
        data = from_tables.build(HERE / "fixtures" / "located-factors" / "description.json")
        self.assertEqual(fileformat.errors(data), [])
        counts = data["counts"]["steps"]["located-factors"]
        said = {i: {k: n for k, n in b["verdicts"].items() if n} for i, b in counts.items()}
        self.assertEqual(said, {"x:water": {"as claimed": 3, "unchanged": 3},
                                "x:climate": {"not claimed": 1, "unchanged": 5},
                                "x:ecotox": {"unchanged": 6},
                                "x:land": {"as claimed": 1, "unchanged": 5}})  # fmt: skip
        steel = next(i for i in data["items"] if i["id"] == "d5")
        self.assertEqual(steel["verdicts"]["x:climate"], ["not claimed"])
        self.assertIsNone(counts["x:water"]["closer"])  # no published state: nothing to come closer to

    def description(self, folder: Path, tables_: dict, spec: dict) -> Path:
        for name, text in tables_.items():
            (folder / name).write_text(text, encoding="utf-8")
        path = folder / "d.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return path

    def test_a_scope_entry_without_expect_may_move(self):
        """SPEC 6: `may` is the default. A "may move" claim read from tables does not report
        what did not move as "claimed, not moved"."""
        spec = {"title": "t", "item": {"one": "i", "many": "is"},
                "indicators": [{"id": A, "name": "A", "short": "A", "unit": "m3"}], "items": "items.csv",
                "states": [{"id": "s0", "label": "0", "results": "s0.csv"}, {"id": "s1", "label": "1", "results": "s1.csv"}],
                "steps": [{"id": "st", "label": "step", "kind": "method",
                           "claim": {"text": "A may move.", "by": {"kind": "person", "name": "A"},
                                     "scope": [{"indicators": [A], "items": "*"}]}}]}  # fmt: skip
        with tempfile.TemporaryDirectory() as folder:
            path = self.description(Path(folder), {"items.csv": "item,unit\na,kg\nb,kg\n",
                                                   "s0.csv": f"item,{A}\na,1.0\nb,2.0\n",
                                                   "s1.csv": f"item,{A}\na,1.5\nb,2.0\n"}, spec)  # fmt: skip
            data = from_tables.build(path)
        self.assertEqual(data["steps"][0]["claim"]["scope"][0]["expect"], "may")
        said = {k: n for k, n in data["counts"]["steps"]["st"][A]["verdicts"].items() if n}
        self.assertEqual(said, {"as claimed": 1, "unchanged": 1})

    def test_a_description_names_its_word_for_an_indicator(self):
        spec = {"title": "t", "item": {"one": "i", "many": "is"},
                "indicators": [{"id": A, "name": "A", "short": "A", "unit": "m3"}], "items": "items.csv",
                "states": [{"id": "s0", "label": "0", "results": "s0.csv"}, {"id": "s1", "label": "1", "results": "s1.csv"}],
                "steps": [{"id": "st", "label": "step", "kind": "method"}]}  # fmt: skip
        tables_ = {"items.csv": "item,unit\na,kg\n", "s0.csv": f"item,{A}\na,1.0\n", "s1.csv": f"item,{A}\na,1.5\n"}
        with tempfile.TemporaryDirectory() as folder:
            self.assertNotIn("indicator", from_tables.build(self.description(Path(folder), tables_, spec)))
            word = {"one": "impact category", "many": "impact categories"}
            data = from_tables.build(self.description(Path(folder), tables_, {**spec, "indicator": word}))
            self.assertEqual((data["indicator"], fileformat.errors(data)), (word, []))
            wrong = {**spec, "indicator": {"one": "impact category"}}
            self.assertTrue(any("indicator" in e for e in from_tables.description_errors(wrong)))

    def test_noise_is_taken_beyond_the_floor_only(self):
        """A residue near zero (4e-16 in one build, 0 in the other) is not noise: it would make
        the noise 1.0 and hide a correction by a factor of 580 as "within noise"."""
        spec = {"title": "t", "item": {"one": "i", "many": "is"},
                "indicators": [{"id": A, "name": "A", "short": "A", "unit": "kg"}], "items": "items.csv",
                "states": [{"id": "s0", "label": "0", "results": "s0.csv",
                            "noise": {"tables": [{"label": "a", "results": "s0.csv"}, {"label": "b", "results": "again.csv"}]}},
                           {"id": "s1", "label": "1", "results": "s1.csv"}],
                "steps": [{"id": "fix", "label": "fix", "kind": "fix",
                           "claim": {"text": "Berries go down.", "by": {"kind": "person", "name": "A"},
                                     "scope": [{"indicators": [A], "items": ["berry"], "direction": "down", "expect": "must"}]}}]}  # fmt: skip
        with tempfile.TemporaryDirectory() as folder:
            path = self.description(Path(folder), {"items.csv": "item,unit\nberry,kg\ndump,kg\nmid,kg\n",
                                                   "s0.csv": f"item,{A}\nberry,383.17\ndump,3.9e-16\nmid,0.52\n",
                                                   "s1.csv": f"item,{A}\nberry,0.6587\ndump,3.9e-16\nmid,0.52\n",
                                                   "again.csv": f"item,{A}\nberry,383.17\ndump,0\nmid,0.52\n"}, spec)  # fmt: skip
            data = from_tables.build(path)
        self.assertEqual(data["steps"][0]["noise"]["by"], {A: 0.0})
        berry = data["items"][0]
        self.assertEqual((berry["id"], berry["classes"][A][0], berry["verdicts"][A][0]), ("berry", "beyond 10x", "as claimed"))

    def test_an_indicator_without_a_pair_beyond_the_floor_has_no_noise(self):
        floor = {"a": 0.1, "b": 0.1}
        self.assertIsNone(chain.noise_of({"a": 0.0, "b": 0.05}, {"a": 1e-9, "b": 0.0}, floor=floor))
        self.assertEqual(chain.noise_of({"a": 1.0, "b": 0.05}, {"a": 1.0, "b": 0.0}, floor=floor), 0.0)
        said = chain.noise(("a", "b"), {A: 0.0, B: None})
        self.assertEqual(said["by"], {A: 0.0})

    SMALL = {"title": "t", "indicators": [{"id": A, "name": "A", "short": "A", "unit": "kg"}], "items": "items.csv",
             "states": [{"id": "s0", "label": "0", "results": "s0.csv"}, {"id": "s1", "label": "1", "results": "s1.csv"}],
             "steps": [{"id": "st", "label": "step", "kind": "fix"}]}  # fmt: skip
    SMALL_TABLES = {"items.csv": "item,unit\na,kg\nb,kg\n", "s0.csv": f"item,{A}\na,1.0\nb,2.0\n",
                    "s1.csv": f"item,{A}\na,1.5\nb,2.0\n"}  # fmt: skip

    def test_an_item_without_results_is_missing_in_every_state(self):
        """An item of the items table that no results table holds is counted, as missing on
        both sides of every step (issue 13)."""
        with tempfile.TemporaryDirectory() as folder:
            tables_ = self.SMALL_TABLES | {"items.csv": "item,unit\na,kg\nb,kg\nghost,kg\n"}
            data = from_tables.build(self.description(Path(folder), tables_, self.SMALL))
        self.assertEqual(data["items_count"]["all"], 3)
        self.assertEqual(data["counts"]["steps"]["st"][A]["missing"], {"before": 0, "after": 0, "both": 1})
        ghost = next(i for i in data["items"] if i["id"] == "ghost")
        self.assertEqual(ghost["values"][A], [None, None])

    def test_ordinary_mistakes_are_sentences_not_tracebacks(self):
        """Each mistake ends in one ValueError that says what is wrong, and the command prints
        it after `error:` and exits 1 (issue 11)."""
        cases = {
            "a results table that is not there": ({}, {"s1.csv": None}),
            "a cell larger than a CSV field may be": ({}, {"s1.csv": f"item,{A}\na,{'1' * 140000}\nb,2\n"}),
            "listed that is a text": ({"listed": "5"}, {}),
            "no title": ({"title": None}, {}),
            "an indicator without an id": ({"indicators": [{"name": "A"}]}, {}),
            "a state without results": ({"states": [{"id": "s0", "label": "0"}, {"id": "s1", "label": "1", "results": "s1.csv"}]}, {}),
            "a step that is a text": ({"steps": ["st"]}, {}),
            "a claim without text": ({"steps": [{"id": "st", "label": "s", "kind": "fix", "claim": {"scope": []}}]}, {}),
            "a noise of three states": ({"steps": [{"id": "st", "label": "s", "kind": "fix", "noise": {"states": ["s0", "s1", "s1"]}}]}, {}),
            "a noise of an unknown state": ({"steps": [{"id": "st", "label": "s", "kind": "fix", "noise": {"states": ["s0", "x"]}}]}, {}),
            "a tolerance without a value": ({"steps": [{"id": "st", "label": "s", "kind": "fix", "tolerance": {"basis": "declared"}}]}, {}),
        }  # fmt: skip
        for name, (changes, table_changes) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as folder:
                spec = {k: v for k, v in (self.SMALL | changes).items() if v is not None}
                tables_ = {k: v for k, v in (self.SMALL_TABLES | table_changes).items() if v is not None}
                path = self.description(Path(folder), tables_, spec)
                with self.assertRaises(ValueError) as caught:
                    from_tables.build(path)
                self.assertNotIn("Traceback", str(caught.exception))
                with contextlib.redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(cli.main(["build", str(path), "--out", str(Path(folder) / "out.json")]), 1)
                self.assertTrue(err.getvalue().startswith("error: "), err.getvalue())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            path.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(ValueError):
                from_tables.build(path)

    def test_a_value_of_any_type_in_a_description_is_a_sentence(self):
        """Every node of the fixture's description replaced by values of other types (issue
        11): the build stops with a ValueError, never another exception, and so the command
        says `error:` and exits 1. Fields the fixture leaves out are added first, so that
        they are walked too: a claim's `reach` (`true` was read as 1), a state's `about`, the
        matrix, an explanation's link and doc."""
        spec = json.loads((FIXTURES / "description.json").read_text(encoding="utf-8"))
        spec["steps"][1].update(explained=True, about="a", link=None)
        spec["steps"][1]["claim"]["reach"] = 1
        spec["states"][1]["about"] = "a"
        spec["explanations"][0].update(link="https://example.org/a", doc="a")
        spec.update(listed=4, claim_lists=True, tier="items", floor_factor=0.01, indicator={"one": "a", "many": "b"})
        local = {**spec, "audience": "local", "matrix": "matrix.json"}  # only a local file names a matrix
        with tempfile.TemporaryDirectory() as folder:
            for name in ("items.csv", "published.csv", "repro.csv", "again.csv", "fixed.csv"):
                (Path(folder) / name).write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
            path = Path(folder) / "d.json"

            def built(d):
                path.write_text(json.dumps(d), encoding="utf-8")
                try:
                    from_tables.build(path)
                except ValueError as error:
                    return [str(error)]
                return []

            for walked in (spec, local):
                self.assertEqual(built(walked), [])
                helpers.replaced_everywhere(self, walked, built)

    def test_a_value_of_the_wrong_kind_is_not_read_as_another(self):
        """What the build would have read as something else is refused, with its place: `"no"`
        as explained, `[]` as no identity or as the default basis, an entry with a key no
        entry takes as one that may move anything (issue 11)."""
        def step(**more):
            return {"steps": [{"id": "st", "label": "s", "kind": "fix", **more}]}

        cases = {
            "step 'st': `explained` is true or false": step(explained="no"),
            "state 's1': `identity` is a table of texts, or null": {"states": [self.SMALL["states"][0], {**self.SMALL["states"][1], "identity": []}]},
            "step 'st', `tolerance`: `basis` is a text or null": step(tolerance={"value": 0.01, "basis": []}),
            "step 'st', scope entry 1: a key a description does not take there: a": step(claim={"text": "t", "scope": [{"a": 1}]}),
            "step 'st', scope entry 1: `items` is \"*\", a list of ids or null": step(claim={"text": "t", "scope": [{"items": {}}]}),
            "indicator 1: a key a description does not take there: colour": {"indicators": [{**self.SMALL["indicators"][0], "colour": "red"}]},
            "step 'st', `tolerance`: `value` is a number": step(tolerance={"value": 10**400}),
            "the description: `listed` is a whole number": {"listed": None},
            "the description: `notes` is a list of texts": {"notes": None},
        }  # fmt: skip
        noise = "state 's1': a noise is {states: [a, b]} or {tables: [{label, results}, {label, results}]}, with a `note`"
        for said_noise in ({"states": ["s0", "s1"], "note": 5}, {"states": ["s0", "s1"], "colour": "red"}):
            cases[noise + " " + str(said_noise)] = {"states": [self.SMALL["states"][0], {**self.SMALL["states"][1], "noise": said_noise}]}
        for said, changes in cases.items():
            with self.subTest(said):
                self.assertIn(said.split(" {'states'")[0], from_tables.description_errors(self.SMALL | changes))

    def test_no_count_number_or_flag_takes_a_value_python_reads_as_one(self):
        """In Python `True == 1`, `1` is true and `1.0 == 1`, so a count, a number or a flag
        given a value of another kind would be read as one (the review of issue 11: `reach:
        true` was built, and read as 1). Each place refuses each such value, with its place."""
        def st(**more):
            return {"steps": [{"id": "st", "label": "s", "kind": "fix", **more}]}

        def claim(**more):
            return st(claim={"text": "t", **more})

        def joined(**more):
            return {"states": [{**self.SMALL["states"][0], "join": {"compared": 2, **more}}, self.SMALL["states"][1]]}

        places = {
            (True, False, 1.0, "1"): [
                ("the description: `listed`", lambda v: {"listed": v}),
                ("step 'st', its claim: `reach`", lambda v: claim(reach=v)),
                ("state 's0', `join`: `compared`", lambda v: joined(compared=v)),
                ("state 's0', `join`: `unmatched`", lambda v: joined(unmatched=v)),
                ("state 's0', `join`: `ambiguous`", lambda v: joined(ambiguous=v)),
            ],
            (True, False, "0.5"): [
                ("the description: `floor_factor`", lambda v: {"floor_factor": v}),
                ("step 'st', `tolerance`: `value`", lambda v: st(tolerance={"value": v})),
                ("step 'st', scope entry 1: `largest`", lambda v: claim(scope=[{"largest": v}])),
            ],
            (1, 0, "true", None): [
                ("the description: `claim_lists`", lambda v: {"claim_lists": v}),
                ("step 'st': `explained`", lambda v: st(explained=v)),
            ],
        }
        self.assertEqual(from_tables.description_errors(self.SMALL), [])
        for values, said in places.items():
            for place, changed in said:
                for value in values:
                    with self.subTest(place=place, value=value):
                        found = from_tables.description_errors(self.SMALL | changed(value))
                        self.assertTrue(any(e.startswith(place + " is ") for e in found), found)

    def test_a_file_the_command_cannot_write_is_a_sentence(self):
        """A place to write that cannot be written (its folder is a file) ends in `error:`
        and exit 1, as a mistake in the description does."""
        with tempfile.TemporaryDirectory() as folder:
            blocked = Path(folder) / "a-file"
            blocked.write_text("", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = cli.main(["build", str(FIXTURES / "description.json"), "--out", str(blocked / "d.json")])
            self.assertEqual(code, 1)
            self.assertTrue(err.getvalue().startswith("error: "), err.getvalue())

    def test_an_unknown_key_in_a_description(self):
        spec = json.loads((FIXTURES / "description.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            for name in ("items.csv", "published.csv", "repro.csv", "again.csv", "fixed.csv"):
                (Path(folder) / name).write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
            path = Path(folder) / "d.json"
            path.write_text(json.dumps(spec | {"status": "accepted"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                from_tables.build(path)
            (Path(folder) / "items.csv").write_text("item,unit\nw1,kg\n", encoding="utf-8")
            path.write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(ValueError):  # results of items without a unit
                from_tables.build(path)


class Page(unittest.TestCase):
    def test_the_assets_load_nothing_from_elsewhere(self):
        for name, path in page.assets(standalone=True).items():
            text = path.read_text(encoding="utf-8")
            with self.subTest(name):
                for said in ("http://", "https://", "//cdn", "@import", "fonts.g", "<iframe"):
                    self.assertNotIn(said, text)

    def test_the_script_writes_no_markup(self):
        script = page.assets()["diagnostics.js"].read_text(encoding="utf-8")
        for said in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(said, script)

    def test_a_text_cannot_end_the_script_element(self):
        text = page.as_script("X", {"title": "</script><script>alert(1)</script>"})
        self.assertNotIn("</", text)
        self.assertTrue(text.isascii())

    def test_the_page_refuses_a_wrong_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                page.write({"format": "sentier-diagnostics/1"}, Path(folder))

    def test_the_page_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            where = page.write(example.build(), Path(folder), {"p01-fix-1.json": example.wheat_breakdown()})
            names = sorted(p.name for p in where.parent.iterdir())
            self.assertEqual(names, ["diagnostics.css", "diagnostics.js", "index.html", "standalone.css"])


class Command(unittest.TestCase):
    def run_cli(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue()

    def test_example_check_summary_page(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            self.assertEqual(self.run_cli("example", "--out", folder)[0], 0)
            code, said = self.run_cli("check", folder / "diagnostics.json", folder / "p01-fix-1.json")
            self.assertEqual(code, 0, said)
            code, said = self.run_cli("summary", folder / "diagnostics.json")
            self.assertEqual(code, 0)
            self.assertIn("## Steps", said)
            (folder / "p01-fix-1.json").unlink()
            code, said = self.run_cli("check", folder / "diagnostics.json")
            self.assertEqual(code, 0)
            self.assertIn("not beside it (not checked)", said)  # said, never silent
            self.assertEqual(self.run_cli("page", folder / "diagnostics.json", "--out", folder / "p")[0], 0)

    def test_check_fails_on_a_wrong_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            path.write_text(json.dumps(helpers.mutated(example.build(), lambda d: d.update(tier="all"))), encoding="utf-8")
            code, said = self.run_cli("check", path)
            self.assertEqual(code, 1)
            self.assertIn("FAIL", said)

    def test_build_from_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "d.json"
            code, said = self.run_cli("build", FIXTURES / "description.json", "--out", out)
            self.assertEqual(code, 0, said)
            self.assertEqual(fileformat.errors(chain.read(out)), [])


class Summary(unittest.TestCase):
    def test_a_local_file_says_so(self):
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}})
        self.assertIn("Local file", summary.text(data))
        self.assertNotIn("Local file", summary.text(example.build()))

    def test_missing_on_both_sides_is_missing_before_and_after(self):
        data = helpers.two_states({A: {"p": None, "q": 1.0}, B: {"p": 1.0, "q": 1.0}},
                                  {A: {"p": None, "q": 1.0}, B: {"p": 1.0, "q": 1.0}})  # fmt: skip
        self.assertEqual(data["counts"]["steps"]["one"][A]["missing"], {"before": 0, "after": 0, "both": 1})
        row = next(line for line in summary.text(data).splitlines() if line.startswith("| 0. "))
        self.assertEqual(row.split(" | ")[4:6], ["1", "1"])

    def test_each_verdict_worth_a_look_has_its_column(self):
        # two pairs left open (one missing, one near zero), one not moved, none of the others
        claim = helpers.claim_down({"p", "q", "z"})
        data = helpers.two_states({A: {"p": None, "q": 1.0, "z": 0.0, "f": 1.0}, B: dict.fromkeys("pqzf", 1.0)},
                                  {A: {"p": 1.0, "q": 1.0, "z": 0.0, "f": 1.0}, B: dict.fromkeys("pqzf", 1.0)},
                                  claim=claim)  # fmt: skip
        lines = summary.text(data).splitlines()
        head = next(line for line in lines if line.startswith("| Step |")).strip("| ").split(" | ")
        row = next(line for line in lines if line.startswith("| 0. ")).strip("| ").split(" | ")
        said = dict(zip(head, row))
        self.assertEqual([said[k] for k in ("As claimed", "Off claim", "Not claimed", "Claimed, not moved", "Claimed, not judged")],
                         ["0", "0", "0", "1", "2"])  # fmt: skip

    def test_the_noise_says_its_size(self):
        said = summary.text(example.build())
        self.assertIn("Water 2.4 %", said)

    def test_steps_are_numbered_from_1_where_the_chain_starts_from_no_published_results(self):
        """Step 0 checks that the published results are reproduced; a chain that starts from
        a build of its own has no such step and counts from 1."""
        published = summary.text(helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}))
        self.assertTrue(any(line.startswith("| 0. One step |") for line in published.splitlines()))
        built = summary.text(helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, first_kind="build"))
        rows = [line for line in built.splitlines() if line.startswith("| 1. One step |")]
        self.assertEqual(len(rows), 1)
        self.assertNotIn("Step 0", built)

    def test_the_file_word_for_an_indicator(self):
        data = example.build()
        self.assertIn(f"{len(data['indicators'])} indicators.", summary.text(data))
        data["indicator"] = {"one": "impact category", "many": "impact categories"}
        self.assertEqual(fileformat.errors(data), [])
        said = summary.text(data)
        self.assertIn(f"{len(data['indicators'])} impact categories.", said)
        self.assertIn("| Impact category |", said)
        self.assertIn("one per impact category and reference unit", said)
        self.assertNotIn("| Indicator |", said)
        self.assertNotIn(" indicators. ", said.replace(data["about"], ""))

    def test_texts_of_the_file_are_not_markdown(self):
        """A text from the file cannot add a table column, a link, markup or a mention to a
        pull request the summary is pasted into (issue 17)."""
        data = example.build()
        data["title"] = "A <b>title</b> for @someone, see [this](https://example.org) | *now*"
        data["steps"][1]["label"] = "fix|x"
        data["steps"][1]["kind"] = "_k_"
        data["indicators"][0]["short"] = "C`O`2"
        data["notes"] = ["ask @team about #12"]
        self.assertEqual(fileformat.errors(data), [])
        said = summary.text(data)
        for raw in ("<b>", "@someone", "@team", "[this](", "fix|x", "*now*", "_k_", "C`O`2"):
            self.assertNotIn(raw, said)
        row = next(line for line in said.splitlines() if line.startswith("| 1. "))
        header = next(line for line in said.splitlines() if line.startswith("| Step |"))
        unescaped = lambda line: len(re.findall(r"(?<!\\)\|", line))  # noqa: E731
        self.assertEqual(unescaped(row), unescaped(header))

    def test_every_text_is_escaped_in_every_place_the_summary_writes_it(self):
        """Each text of the file gets its own mark, `*tN*`; written without `md` at any one
        place, the mark shows raw there (issue 17: removing `md` from 9 of its 14 places
        failed no test)."""
        data = example.build()
        marks = iter(range(100))
        mark = lambda: f"- *t{next(marks)}* @x"  # noqa: E731
        data["title"], data["about"], data["notes"] = mark(), mark(), [mark(), mark()]
        data["indicator"] = {"one": mark(), "many": mark()}
        data["item"]["many"] = mark()
        data["indicators"][0]["short"] = mark()
        data["indicators"][1]["short"], data["indicators"][1]["name"] = None, mark()
        for state in data["states"]:
            state["label"] = mark()
        data["states"][0]["join"]["note"] = mark()
        noisy = next(s for s in data["states"] if (s.get("noise") or {}).get("between"))
        noisy["noise"]["between"] = [mark(), mark()]
        for step in data["steps"]:
            step["label"], step["kind"] = mark(), f"*k{next(marks)}*"
        self.assertEqual(fileformat.errors(data), [])
        said = summary.text(data)
        for n in range(next(marks)):
            with self.subTest(n):
                raw = next(f"*{p}{n}*" for p in "tk" if f"*{p}{n}*" in json.dumps(data))
                self.assertNotIn(raw, said)
                self.assertIn(summary.md(raw), said)
        # each place: a state's label in the states, the join, both ends, the rule and the floors
        published = summary.md(data["states"][0]["label"])
        for place in ("States: " + published, "Read into " + published, f"The whole way: {published} → ",
                      f"- {published}: exact", "median size in " + published):  # fmt: skip
            self.assertIn(place, said)

    def test_a_text_shows_as_written_and_makes_nothing_of_its_own(self):
        """What GitHub makes of a text pasted into a pull request: a list, a rule, code, a
        link, an emoji, an issue, a mention, maths. Each case below was rendered by GitHub's
        Markdown API (`gh api markdown`, mode gfm) on 17 November 2026, at the start of a
        line, after `- `, after `# ` and in a table cell: each showed as written and made
        nothing, a commit's hash aside, which GitHub links to that commit."""
        j, s = "⁠", " "
        cases = {
            "---": "\\---", "===": "\\===", "- a": "\\- a", "+ a": "\\+ a", "* a": "\\* a",
            "1. a": "1\\. a", "12) a": "12\\) a", "2026 was": "2026 was", "    code": s * 4 + "code",
            "https://a.org": f"https:{j}//a.org", "www.a.org": f"www{j}.a.org", "WWW.A.org": f"WWW{j}.A.org",
            "mailto:a@b.org": f"mailto:{j}a@{j}b.org", ":warning:": f":{j}warning:{j}",
            "#1": f"\\#{j}1", "GH-1": f"GH{j}-1", "o/r/issues/1": f"o/r/issues/{j}1", "@team": f"@{j}team",
            "$x$": f"{j}\\$x{j}\\$", "a|b": "a\\|b", "&amp;": "\\&amp;", "<b>": "\\<b\\>",
            "high-level": "high-level", "a857d60": "a857d60",
            # nine digits still start a list, ten do not; two tildes strike through
            "123456789. a": "123456789\\. a", "1234567890. a": "1234567890. a", "~~a~~": "\\~\\~a\\~\\~",
        }  # fmt: skip
        shown = lambda md: re.sub(r"\\(.)", r"\1", md.replace(j, "")).replace(s, " ")  # noqa: E731
        for text, md in cases.items():
            with self.subTest(text):
                self.assertEqual(summary.md(text), md)
                self.assertEqual(shown(summary.md(text)), text)

    def test_the_summary_writes_a_number_as_the_page_does(self):
        """The summary wrote a noise of 120 % as `1.2e+02 %`, 1e-5 % as `1e-05 %`, and a
        tolerance of 1e-5 as `1e-05` where the page writes `0.00001` (review of 9a11c09).
        Its writers are held to the page's own, run over the whole range of the floats."""
        said = summary.text(example.build())
        self.assertIn("tolerance 0.00001 (default)", said)
        self.assertNotRegex(said, r"\de[-+]\d")
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        values = [9999.5, 99999.5, 999.95, 0.0099995, 0.00099995, 5e-324, 1.7976931348623157e308, 1e21,
                  1234.5, -1234.5, 0.1 + 0.2, -2.5e-9, 1e-6, 9.999999e-7, -0.00099996, 0.0]  # fmt: skip
        values += [m * 10.0**e for e in range(-323, 308) for m in (1, 1.2345, 9.5, 9.9995, 9.99995)]
        values = [v for v in values if math.isfinite(v)]
        script = ("const p = require(process.argv[1]); const v = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
                  "process.stdout.write(JSON.stringify(v.map((x) => [p.exactText(x), p.formatNumber(x)])))")  # fmt: skip
        run = subprocess.run([node, "-e", script, str(Path(page.__file__).parent / "page" / "diagnostics.js")],
                             input=json.dumps(values), capture_output=True, text=True, check=True)  # fmt: skip
        for value, (exact, short) in zip(values, json.loads(run.stdout)):
            self.assertEqual(summary._exact(value), exact, value)
            self.assertEqual(summary._short(value, 4), short, value)


class Verdicts(unittest.TestCase):
    """How a pair is held against its claim (SPEC 6; issues 3, 12 and 16)."""

    def verdict(self, kind, before, after, entries):
        way = rule.direction(before, after, kind)
        return claims.verdict(kind, before, after, way, entries)

    def test_where_a_must_covers_a_pair_its_may_entries_are_not_held(self):
        """SPEC 6: a pair that moved is held to the `must` entries that cover it, and only where
        none does to the `may` entries (a mutation holding it to every entry went unnoticed)."""
        must_down = claims.scope([A], {"p"}, "down", None, claims.MUST)
        may_up = claims.scope([A], {"p"}, "up", None, claims.MAY)
        self.assertEqual(self.verdict(rule.DIFFERS, 2.0, 1.0, [must_down, may_up]), claims.AS_CLAIMED)
        self.assertEqual(self.verdict(rule.DIFFERS, 2.0, 1.0, [may_up, must_down]), claims.AS_CLAIMED)
        self.assertEqual(self.verdict(rule.DIFFERS, 2.0, 1.0, [may_up]), claims.OFF_CLAIM)

    def test_a_must_that_did_not_move_beyond_the_noise_is_unmet(self):
        must = claims.scope([A], {"p"}, "down", None, claims.MUST)
        may = claims.scope([A], {"p"}, "down", None, claims.MAY)
        for kind in (rule.AGREES, rule.WITHIN_NOISE):
            with self.subTest(kind):
                self.assertEqual(self.verdict(kind, 1.0, 1.0, [must]), claims.NOT_MOVED)
        self.assertEqual(self.verdict(rule.AGREES, 1.0, 1.0, [may]), claims.UNCHANGED)
        self.assertEqual(self.verdict(rule.WITHIN_NOISE, 1.0, 1.0, [may]), claims.NOISE)

    def test_a_must_on_a_pair_that_cannot_be_judged_is_left_open(self):
        # issue 3: 1e-9 -> 1e-12 below the floor did move; whether as claimed cannot be said
        must = claims.scope([A], {"p"}, "down", None, claims.MUST)
        may = claims.scope([A], {"p"}, "down", None, claims.MAY)
        self.assertEqual(self.verdict(rule.NEAR_ZERO, 1e-9, 1e-12, [must]), claims.OPEN)
        self.assertEqual(self.verdict(rule.MISSING, None, 1.0, [must]), claims.OPEN)
        self.assertEqual(self.verdict(rule.MISSING, 1.0, None, [must, may]), claims.OPEN)
        self.assertEqual(self.verdict(rule.NEAR_ZERO, 1e-9, 1e-12, [may]), claims.NOT_JUDGED)
        self.assertEqual(self.verdict(rule.MISSING, None, 1.0, [may]), claims.NOT_JUDGED)
        self.assertEqual(self.verdict(rule.MISSING, None, None, []), claims.NOT_JUDGED)
        self.assertIn(claims.OPEN, claims.TO_LOOK_AT)

    def test_several_must_entries_must_all_fit(self):
        # issue 12: `must any` beside `must down, 10 % at most` does not let 1.0 -> 5.0 pass
        anything = claims.scope("*", "*", "any", None, claims.MUST)
        down_a_little = claims.scope([A], {"p"}, "down", 0.1, claims.MUST)
        both = [anything, down_a_little]
        self.assertEqual(self.verdict(rule.BEYOND, 1.0, 5.0, both), claims.OFF_CLAIM)
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 0.5, both), claims.OFF_CLAIM)
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 0.95, both), claims.AS_CLAIMED)
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 0.95, [*both, claims.scope([A], {"p"}, "up", None, claims.MUST)]),
                         claims.OFF_CLAIM)  # fmt: skip
        # `may` entries: one that fits is enough
        mays = [claims.scope([A], {"p"}, "up"), claims.scope([A], {"p"}, "down", 0.1)]
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 0.95, mays), claims.AS_CLAIMED)
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 1.5, mays), claims.AS_CLAIMED)

    def test_build_refuses_an_entry_whose_list_is_not_in_hand(self):
        # issue 3: such an entry covers nothing, and a `must` would be met by default
        for expect in (claims.MUST, claims.MAY):
            with self.subTest(expect), self.assertRaisesRegex(ValueError, "no list of items in hand"):
                helpers.two_states({A: {"p": 1.0}}, {A: {"p": 1.0}},
                                   claim=claims.claim("t", [claims.scope([A], None, "down", None, expect)]))  # fmt: skip
        # the list given and kept out of the file is the way to keep it private
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 1.0}}, claim=helpers.claim_down({"p"}), claim_lists=False)
        self.assertEqual(data["steps"][0]["claim"]["scope"][0]["items"], None)
        self.assertEqual(data["counts"]["steps"][data["steps"][0]["id"]][A]["verdicts"][claims.NOT_MOVED], 1)

    def test_a_must_is_judged_on_its_own_where_entries_overlap(self):
        must_down = claims.scope([A], {"p"}, "down", None, claims.MUST)
        may_any = claims.scope([A], {"p"}, "any", None, claims.MAY)
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 2.0, [must_down, may_any]), claims.OFF_CLAIM)
        self.assertEqual(self.verdict(rule.DIFFERS, 2.0, 1.0, [must_down, may_any]), claims.AS_CLAIMED)
        self.assertEqual(self.verdict(rule.DIFFERS, 1.0, 2.0, [may_any]), claims.AS_CLAIMED)

    def test_a_zero_reference_is_never_within_a_relative_largest(self):
        capped = claims.scope([A], {"p"}, "up", 0.3, claims.MAY)
        self.assertEqual(self.verdict(rule.ZERO_REFERENCE, 9e-10, 1.1e-9, [capped]), claims.OFF_CLAIM)
        uncapped = claims.scope([A], {"p"}, "up", None, claims.MAY)
        self.assertEqual(self.verdict(rule.ZERO_REFERENCE, 9e-10, 1.1e-9, [uncapped]), claims.AS_CLAIMED)

    def test_a_scope_item_no_state_holds_is_refused(self):
        with self.assertRaises(ValueError):
            helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, claim=helpers.claim_down({"p", "typo"}))

    def test_a_must_on_a_near_zero_pair_is_listed_and_valid(self):
        # z is near zero and quiet in both indicators: only its open claim makes it worth a look
        before = {A: {"p": 1.0, "q": 1.0, "z": 0.0}, B: {"p": 1.0, "q": 1.0, "z": 1.0}}
        after = {A: {"p": 1.0, "q": 2.0, "z": 0.0}, B: {"p": 1.0, "q": 1.0, "z": 1.0}}
        data, full = chain.build_with_matrix(
            "Two states", indicators=helpers.INDICATORS,
            states=[chain.state("s0", "Before"), chain.state("s1", "After")],
            steps=[chain.step("one", "One step", kind="fix", claim=helpers.claim_down({"z"}))],
            values={"s0": before, "s1": after}, units=dict.fromkeys("pqz", "kg"),
        )  # fmt: skip
        self.assertEqual(fileformat.errors(data), [])
        self.assertEqual(matrix.against(full, data), [])
        self.assertEqual([i["id"] for i in data["items"]], ["q", "z"], "p is quiet; z is listed for its claim alone")
        z = next(i for i in data["items"] if i["id"] == "z")
        self.assertEqual(z["verdicts"][A], [claims.OPEN])
        self.assertEqual(data["counts"]["steps"]["one"][A]["verdicts"][claims.OPEN], 1)
        # the validator counts it from the listed items: a file that leaves it out of its counts is refused
        hidden = helpers.mutated(data, lambda d: (d["counts"]["steps"]["one"][A]["verdicts"].__setitem__(claims.OPEN, 0),
                                                  d["counts"]["steps"]["one"][A]["verdicts"].__setitem__(claims.NOT_JUDGED, 1)))
        self.assertTrue(any("claimed, not judged" in e for e in fileformat.errors(hidden)), fileformat.errors(hidden))

    def test_reach_is_the_size_of_the_lists_beside_a_star(self):
        found = claims.published(claims.claim("t", [claims.scope([A], {"p", "q"}), claims.scope([B])]), keep_items=False)
        self.assertEqual(found["reach"], 2)
        self.assertEqual([e["items"] for e in found["scope"]], [None, "*"])

    def test_a_scope_may_list_as_many_items_as_a_file(self):
        many = {f"i{k}" for k in range(600)}
        data = helpers.two_states({A: dict.fromkeys(many, 1.0)}, {A: dict.fromkeys(many, 1.0)},
                                  claim=claims.claim("t", [claims.scope([A], many)], by=claims.origin("person", "A")))  # fmt: skip
        self.assertEqual(fileformat.errors(data), [])
        self.assertEqual(len(data["steps"][0]["claim"]["scope"][0]["items"]), 600)


class Chain(unittest.TestCase):
    def test_a_file_with_its_keys_in_another_order_is_written_whole(self):
        """The list of items is not found by its text: a claim's empty list after it is left alone."""
        nothing = claims.claim("Nothing listed moves.", [claims.scope([A], set())], by=claims.origin("person", "A"))
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, claim=nothing)
        reordered = {"items": data["items"], **{k: v for k, v in data.items() if k != "items"}}
        self.assertEqual(json.loads(chain.dumps(reordered)), data)
        self.assertEqual(chain.dumps(data), chain.dumps(dict(data)))

    def test_scope_items_given_as_one_text_are_refused(self):
        with self.assertRaises(TypeError):
            claims.scope([A], "p01")

    def test_a_reach_that_disagrees_with_the_lists_is_refused(self):
        with self.assertRaises(ValueError):
            claims.published(claims.claim("t", [claims.scope([A], {"p", "q"})], reach=4900))
        self.assertEqual(claims.published(claims.claim("t", [claims.scope([A], {"p", "q"})]))["reach"], 2)

    def test_a_claim_that_lists_no_items_has_no_reach(self):
        # issue 35: every entry takes "*", or there is none: a reach would count nothing
        for entries in ([claims.scope([A])], [claims.scope([A]), claims.scope([B])], []):
            with self.assertRaises(ValueError):
                claims.published(claims.claim("t", entries, reach=7))
            self.assertIsNone(claims.published(claims.claim("t", entries))["reach"])
        # a list kept private is a list: its reach is the only trace of it, and stays
        private = claims.published(claims.claim("t", [claims.scope([A], None), claims.scope([B])], reach=7))
        self.assertEqual(private["reach"], 7)
        data = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}}, claim=claims.claim("t", [claims.scope([A])], by=claims.origin("person", "A")))
        self.assertEqual(fileformat.errors(data), [])
        for scope in ([{"indicators": "*", "items": "*", "direction": "any", "largest": None, "expect": "may"}], []):
            given = helpers.mutated(data, lambda d, scope=scope: d["steps"][0]["claim"].update(reach=7, scope=scope))
            self.assertTrue(any("no entry of it lists items" in e for e in fileformat.errors(given)), fileformat.errors(given))
        kept = helpers.mutated(data, lambda d: d["steps"][0]["claim"].update(
            reach=1, scope=[{"indicators": "*", "items": None, "direction": "any", "largest": None, "expect": "may"}]))
        self.assertFalse(any("reach" in e for e in fileformat.errors(kept)), fileformat.errors(kept))

    def test_a_claim_lists_as_many_items_as_its_chain_holds(self):
        # issue 36: a chain may hold more items than a file lists, and a claim about all of
        # them is still a list: the chain and the 12 MB bound it, not the 5,000 of a file
        n = fileformat.MAX_ITEMS + 1
        names = [f"p{i:05d}" for i in range(n)]
        before = {A: dict.fromkeys(names, 1.0)}
        after = {A: dict.fromkeys(names, 1.0) | {names[0]: 2.0}}
        data = helpers.two_states(before, after, claim=claims.claim("t", [claims.scope([A], names)]))
        said = data["steps"][0]["claim"]
        self.assertEqual((said["reach"], len(said["scope"][0]["items"]), data["items_count"]["all"]), (n, n, n))
        self.assertEqual(fileformat.errors(data), [])

        def scope(d):
            return d["steps"][0]["claim"]["scope"][0]

        twice = helpers.mutated(data, lambda d: scope(d)["items"].append(names[0]))
        self.assertTrue(any("not a list of distinct ids" in e for e in fileformat.errors(twice)), fileformat.errors(twice))
        # a claim names items of its chain: neither its lists nor a private list's size reach further
        beyond = helpers.mutated(data, lambda d: (scope(d)["items"].append("q"), d["steps"][0]["claim"].update(reach=n + 1)))
        self.assertTrue(any(f"its claim reaches {n + 1} items, and the chain holds {n}" in e
                            for e in fileformat.errors(beyond)), fileformat.errors(beyond))  # fmt: skip
        for reach, refused in ((n, False), (n + 1, True)):
            kept = helpers.mutated(data, lambda d, reach=reach: (scope(d).update(items=None), d["steps"][0]["claim"].update(reach=reach)))
            self.assertEqual(any("the chain holds" in e for e in fileformat.errors(kept)), refused, fileformat.errors(kept))

    def test_the_validator_looks_an_item_up_in_a_claim_without_reading_its_list(self):
        # issue 36: a list may name 200,000 items, and every listed item is judged against it
        # in every indicator and step; a scan of the list for each would take hours
        class Unread(list):
            def __contains__(self, item):
                raise AssertionError("a claim's list was scanned for an item")

        data = example.build()
        for one in data["steps"]:
            for entry in (one["claim"] or {}).get("scope", ()):
                if isinstance(entry["items"], list):
                    entry["items"] = Unread(entry["items"])
        self.assertEqual(fileformat.errors(data), [])

    def test_a_fault_of_a_listed_item_is_said_once(self):
        """An item whose place, group or unit is wrong is still listed: the explanations about
        the items are not also said to be about an item the file does not list (they were,
        where the check of the items stopped). One about an item that is not listed still is."""
        for field, value in (("place", "x" * 61), ("group", ["g"]), ("unit", 5)):
            with self.subTest(field):
                data = helpers.mutated(example.build(), lambda d, f=field, v=value: next(
                    i for i in d["items"] if i["id"] == "p01").update({f: v}))
                found = fileformat.errors(data)
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].startswith(f"item 'p01': `{field}` "), found)
        stopped = helpers.mutated(example.build(), lambda d: (
            next(i for i in d["items"] if i["id"] == "p01").update(unit=5),
            next(e for e in d["explanations"] if e["about"]["item"] == "p05")["about"].update(item="p99")))
        self.assertEqual(sorted(e.split(":")[-1] for e in fileformat.errors(stopped)),
                         [" `unit` is not a text", " about an item the file does not list"])

    def test_where_the_check_of_the_items_stops_it_still_knows_the_items_it_read(self):
        """A place or group fault does not stop the check of the items: a unit fault on a later
        item is said too. Where the check stops (an item that is not a table, a count of items
        that cannot be read), no explanation about a listed item is said to be about an item
        the file does not list, and a count that cannot be read is said once, not once per
        block of counts (review of 9a11c09)."""
        data = example.build()
        first, last = data["items"][0]["id"], data["items"][-1]["id"]
        explained = {e["about"]["item"] for e in data["explanations"] if e["about"].get("item")}
        self.assertTrue(explained - {first, last})
        for field, value in (("place", "x" * 61), ("group", ["g"])):
            with self.subTest(field):
                found = fileformat.errors(helpers.mutated(data, lambda d, f=field, v=value: (
                    d["items"][0].update({f: v}), d["items"][-1].update(unit=5))))
                self.assertEqual([e.split(":")[0] for e in found], [f"item {first!r}", f"item {last!r}"], found)
        # an item that is not a table, which no explanation is about
        broken = next(k for k, i in enumerate(data["items"]) if 0 < k and i["id"] not in explained)
        found = fileformat.errors(helpers.mutated(data, lambda d: d["items"].__setitem__(broken, 5)))
        self.assertTrue(any(e.startswith("an item is not {") for e in found), found)
        self.assertFalse([e for e in found if "does not list" in e], found)
        # a count of items that cannot be read
        found = fileformat.errors(helpers.mutated(data, lambda d: d.update(items_count=5)))
        self.assertEqual(found, ["`items_count` is not {all, qualifying, listed, not_listed} in counts"])

    def test_a_lone_surrogate_is_not_a_text(self):
        data = example.build()
        data["title"] = "half \ud800 a character"
        self.assertTrue(fileformat.errors(data))

    def test_no_approval_hides_in_a_state_identity(self):
        """SPEC 8: a file carries no status and no approval, and `identity` is no way round it."""
        refused = ("status", "accepted_by", "Approved", "approval",
                   # issue 19: what the first rule let through
                   "signed_off", "reviewed_by", "verified", "validated", "\uff53\uff54\uff41\uff54\uff55\uff53", "st\u200batus",
                   "peerReviewed", "sign-off", "QA", "ok", "lgtm", "checked_by", "rejected", "audit",
                   "certified", "confirmed", "endorsed_by", "okay", "pass", "passed", "passes", "ack", "acked", "signed",
                   "agreed", "pending", "isOk", "qaDone", "peerPassed",
                   # and what the review of the fix found still let through
                   "authorized_by", "authorised", "vetted_by", "acknowledged_by", "attested", "cleared_by", "sanctioned",
                   "signature", "verdict", "decision", "decided_by", "granted", "ratified", "vet", "vetting",
                   "peerVetted", "unCleared")  # fmt: skip
        said = lambda key: fileformat.errors(  # noqa: E731
            helpers.mutated(example.build(), lambda d: d["states"][1]["identity"].update({key: "yes"})))
        for key in refused:
            with self.subTest(key):
                self.assertTrue(any("`identity`" in e for e in said(key)))
        for key in ("solver", "database_version", "brightway-flows", "checksum", "token", "package", "run",
                    "stratified", "authority", "signal", "nuclear_share", "decimals", "event",
                    # a stem is not looked for across two words (review of 9a11c09)
                    "stat_test", "format_test", "at_test", "design_at", "clear_edge", "grant_edge",
                    "designation", "designator", "designate"):  # fmt: skip
            with self.subTest(key):
                self.assertEqual(said(key), [])

    def test_a_key_written_twice_is_refused_when_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            text = chain.dumps(example.build())
            path.write_text(text.replace('"tier": "items",', '"tier": "items", "tier": "counts",', 1), encoding="utf-8")
            with self.assertRaises(ValueError):
                chain.read(path)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cli.check([path]), 1)
            self.assertIn("twice", out.getvalue())

    def test_the_limit_of_listed_items_is_named(self):
        data = example.build()
        data["items"] = data["items"] * 501  # 5,010: the count agrees, only the limit is met
        data["items_count"].update(listed=len(data["items"]), qualifying=len(data["items"]), all=len(data["items"]))
        self.assertTrue(any("of at most 5000" in e for e in fileformat.errors(data)))

    def test_check_refuses_a_file_larger_than_a_page_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            text = chain.dumps(example.build())
            path.write_text(text + " " * (fileformat.MAX_BYTES - len(text.encode()) + 1), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.check([path]), 1)
            self.assertIn("bytes", out.getvalue())
            self.assertIn("leave the claims' lists out", out.getvalue())  # the example's claims list items


class FloorAndLargestFloats(unittest.TestCase):
    """Issue 37: the floor's median held by tests of its own, not only a doctest; and two
    results near the largest float, on either side of zero, lie a finite distance apart."""

    def test_the_floor_is_the_factor_times_the_median_size(self):
        factor = rule.FLOOR_FACTOR
        for values, median, n in (
            ([5.0, 1.0, 3.0], 3.0, 3),  # an odd count: the one in the middle, in any order
            ([10.0, 1.0, 3.0, 2.0], 2.5, 4),  # an even count: halfway between the two in the middle
            ([-4.0, 1.0, 2.0], 2.0, 3),  # by size: a negative result counts as large as it is
            ([0.0, 0.0, 7.0, None], 7.0, 1),  # a zero and a missing result are no size
            ([1e308, 1.6e308], 1.3e308, 2),  # near the largest float: halved before they are added
        ):
            with self.subTest(values=values):
                floor, count = rule.floor_of(values)
                self.assertEqual(count, n)
                self.assertTrue(math.isclose(floor, factor * median, rel_tol=1e-15), (floor, factor * median))
        self.assertEqual(rule.floor_of([0.0, None]), (0.0, 0))
        self.assertEqual(rule.floor_of([2.0, 4.0], 0.5), (1.5, 2))
        # one floor per indicator and unit, each the median of its own group
        found = rule.floors_of({"x": {"a": 1.0, "b": 9.0, "c": 3.0, "t": 40.0}}, {"a": "kg", "b": "kg", "c": "kg", "t": "unit"})
        self.assertEqual(found, {("x", "kg"): (factor * 3.0, 3), ("x", "unit"): (factor * 40.0, 1)})

    def test_two_results_near_the_largest_float_lie_two_apart_not_infinitely(self):
        self.assertEqual(rule.relative_difference(1e308, -1e308), 2.0)
        self.assertEqual(rule.relative_difference(-1.7e308, 1.7e308), 2.0)
        self.assertEqual(rule.change(1e308, -1e308), -2.0)
        self.assertEqual(rule.change(-1e308, 1e308), 2.0)
        # the noise of two builds of one state that far apart is 2, not infinite: an infinite
        # noise would put every pair within it
        self.assertEqual(chain.noise_of({"a": 1e308, "b": 1.0}, {"a": -1e308, "b": 1.0}, floor=0.0), 2.0)
        # a claim of a change of up to 300 % holds a sign change from 1e308 to -1e308
        entry = claims.scope([A], {"p"}, "any", 3.0, claims.MUST)
        self.assertEqual(claims.verdict(rule.SIGN_CHANGE, 1e308, -1e308, "down", [entry]), claims.AS_CLAIMED)
        # and the order from the worst sees them two apart
        self.assertEqual(rule.severity(1e308, -1e308, rule.SIGN_CHANGE)[1], -2.0)


class EachRuleOnItsOwn(unittest.TestCase):
    """Each check of the validator, broken on its own in the example: its own fault must be
    named. Other checks often refuse the same file too, so a test that asserts only that
    the file is refused cannot tell a check that works from one that is gone (issue 15)."""

    def refused(self, change, said):
        found = fileformat.errors(helpers.mutated(example.build(), change))
        self.assertTrue(any(said in e for e in found), f"{said!r} not in {found}")

    @staticmethod
    def block(d, step="fix-1", indicator="x:climate"):
        return d["counts"]["steps"][step][indicator]

    def test_bands_add_up_to_what_differs(self):
        self.refused(lambda d: self.block(d)["bands"].update({"up, factor 1-1.1": 1}),
                     "the bands do not add up to what differs")  # fmt: skip

    def test_no_more_bands_up_than_went_up(self):
        def change(d):
            self.block(d)["bands"].update({"up, factor 1.1-1.25": 2, "down, factor 1.25-2": 0})

        self.refused(change, "more bands up than values that went up")

    def test_up_and_down_add_up_to_what_moved(self):
        self.refused(lambda d: self.block(d)["directions"].update(up=2), "up and down do not add up to what moved")

    def test_verdicts_add_up_to_the_pairs(self):
        self.refused(lambda d: self.block(d)["verdicts"].update(unchanged=8), "the verdicts do not add up to the pairs")

    def test_every_item_is_counted(self):
        self.refused(lambda d: d["items_count"].update(all=11, qualifying=10), "not every item is counted")

    def test_the_attribution_accounts_for_every_item_that_moved(self):
        self.refused(lambda d: d["attribution"]["x:climate"].update(spread=1),
                     "does not account for every item whose total moved")  # fmt: skip

    def test_a_link_is_https(self):
        self.refused(lambda d: d["steps"][1].update(link="http://example.org/fix-1"), "is not an https address")

    def test_a_breakdown_is_named_by_a_file_name_not_a_path(self):
        self.refused(lambda d: d["items"][0].update(breakdowns={"fix-1": "../p01-fix-1.json"}),
                     "a file that is a path")  # fmt: skip

    def test_an_item_is_listed_once(self):
        def change(d):
            d["items"][1] = d["items"][0]

        self.refused(change, "is listed twice")

    def test_two_steps_have_two_ids(self):
        self.refused(lambda d: d["steps"][2].update(id="fix-1"), "two steps have the same id")

    def test_a_step_leads_from_one_state_to_the_next(self):
        self.refused(lambda d: d["steps"][1].update(**{"from": "published"}), "does not lead from state")

    def test_the_tolerance_of_the_whole_way_is_the_largest(self):
        self.refused(lambda d: d["rule"].update(total_tolerance=1e-3), "not the largest tolerance of the steps")

    def test_a_person_is_named(self):
        self.refused(lambda d: d["explanations"][0]["by"].update(name=None), "a person is named")

    def test_a_listed_verdict_fits_its_class(self):
        def change(d):
            item = next(i for i in d["items"] if i["classes"]["x:climate"][1] == rule.AGREES)
            item["verdicts"]["x:climate"][1] = claims.AS_CLAIMED

        self.refused(change, "'agrees' cannot be 'as claimed'")

    def test_a_file_of_counts_explains_no_single_item(self):
        def change(d):
            d["tier"] = "counts"
            d["items"] = []
            for entry in (e for s in d["steps"] if s["claim"] for e in s["claim"]["scope"]):
                if isinstance(entry["items"], list):
                    entry["items"] = None  # a file of counts keeps its claim lists private
            d["items_count"].update(listed=0, not_listed=d["items_count"]["qualifying"])

        self.refused(change, "a file of counts explains no single item")

    def test_an_item_with_nothing_worth_a_look_is_not_listed(self):
        same = {"p": 1.0, "q": 1.0}
        quiet = helpers.two_states({A: same, B: same}, {A: {"p": 2.0, "q": 1.0}, B: same})
        loud = helpers.two_states({A: same, B: same}, {A: {"p": 2.0, "q": 3.0}, B: same})
        self.assertEqual([i["id"] for i in quiet["items"]], ["p"])
        q = next(i for i in loud["items"] if i["id"] == "q")
        q["values"][A] = [1.0, 1.0]
        q["classes"][A] = [rule.AGREES, rule.AGREES]
        q["directions"][A] = q["bands"][A] = [None, None]
        quiet["items"].append(q)
        quiet["items_count"].update(listed=2, qualifying=2)
        found = fileformat.errors(quiet)
        self.assertTrue(any("listed, though nothing in it is worth a look" in e for e in found), found)

    def test_write_refuses_a_file_larger_than_a_page_holds(self):
        data = example.build()
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError) as said:
            original, fileformat.MAX_BYTES = fileformat.MAX_BYTES, 1000
            try:
                chain.write(data, Path(folder) / "d.json")
            finally:
                fileformat.MAX_BYTES = original
        self.assertIn("a page holds 1000 at most", str(said.exception))
        # issue 36: where claims list items, leaving their lists out is the other way down
        self.assertIn("list fewer items (`listed`), or leave the claims' lists out (`claim_lists`)", str(said.exception))
        bare = helpers.two_states({A: {"p": 1.0}}, {A: {"p": 2.0}})
        self.assertEqual(fileformat.smaller_by(bare), "list fewer items (`listed`)")
        self.assertEqual(fileformat.smaller_by(["not", "a", "file"]), "list fewer items (`listed`)")


class SummaryCounts(unittest.TestCase):
    """The summary prints the file's counts as they are (issue 15)."""

    def setUp(self):
        self.data = helpers.three_states({A: {"p": 1.0, "q": 1.0, "r": 1.0}}, {A: {"p": 1.5, "q": None, "r": -1.0}},
                                         {A: {"p": 1.75, "q": 3.0, "r": 0.0}}, explained=(True, False))  # fmt: skip
        self.lines = summary.text(self.data).splitlines()

    def cells(self, start):
        row = next(line for line in self.lines if line.startswith(start))
        return [c.strip() for c in row.strip("|").split("|")]

    def test_values_moved_counts_every_class_that_moved(self):
        # step 0: p differs, r changes sign; q is missing, which is not a move
        self.assertEqual(self.cells("| 0. First step")[3], "2")

    def test_not_attributable_is_printed(self):
        header, row = self.cells("| Indicator"), self.cells("| A |")
        self.assertEqual(row[header.index("Not attributable")], "1")
        self.assertEqual(row[header.index("Spread over steps")], "0")


if __name__ == "__main__":
    unittest.main()
