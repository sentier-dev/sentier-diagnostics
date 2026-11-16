"""Unit tests per module: the validator, tables, breakdowns, building from tables, the page
writer, the command and the doctests."""

from __future__ import annotations

import contextlib
import doctest
import importlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import breakdown, chain, claims, cli, example, fileformat, from_tables, page, rule, summary, tables

from . import helpers
from .helpers import A, B

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "tables"
MODULES = ["rule", "claims", "chain", "fileformat", "breakdown", "tables", "summary", "page", "from_tables"]


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
        ):
            with self.subTest(text):
                with self.assertRaises(tables.TableError):
                    tables.read_results(self.write(text), [A, B])

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

    def test_a_rest_without_parts_left_out(self):
        good = breakdown.build("p", "s0", "s1", {A: ("kg", [("a", None, 1.0, 2.0)])})
        bad = helpers.mutated(good, lambda d: d["indicators"][A].update(rest=[0.5, 0.0], total=[1.5, 2.0]))
        self.assertTrue(breakdown.errors(bad))


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

    def test_noise_is_taken_beyond_the_floor_only(self):
        """A residue near zero (4e-16 in one build, 0 in the other) is not noise: it would make
        the noise 1.0 and hide a correction by a factor of 580 as "within noise"."""
        spec = {"title": "t", "item": {"one": "i", "many": "is"},
                "indicators": [{"id": A, "name": "A", "short": "A", "unit": "kg"}], "items": "items.csv",
                "states": [{"id": "s0", "label": "0", "results": "s0.csv"}, {"id": "s1", "label": "1", "results": "s1.csv"}],
                "steps": [{"id": "fix", "label": "fix", "kind": "fix",
                           "noise": {"tables": [{"label": "a", "results": "s0.csv"}, {"label": "b", "results": "again.csv"}]},
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
        for name, path in page.assets().items():
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
            self.assertEqual(names, ["breakdowns.js", "data.js", "diagnostics.css", "diagnostics.js", "index.html"])


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

    def test_the_noise_says_its_size(self):
        said = summary.text(example.build())
        self.assertIn("Water 2.4 %", said)


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

    def test_check_refuses_a_file_larger_than_a_page_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "d.json"
            text = chain.dumps(example.build())
            path.write_text(text + " " * (fileformat.MAX_BYTES - len(text.encode()) + 1), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.check([path]), 1)
            self.assertIn("bytes", out.getvalue())


if __name__ == "__main__":
    unittest.main()
