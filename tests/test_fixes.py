"""Fixes against one base (SPEC 16): the file, its check, and what a page draws for a set.
Every value here is made up."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import chain, claims, cli, fixes, rule

from . import helpers
from .helpers import INDICATORS, A, B

FLOORS = {(A, "kg"): 0.01, (B, "kg"): 0.01}


def chain_and_matrix(last=None):
    """A chain of two states and its matrix; the base is the second state. Item p3 moved in
    the step, so it is the one listed item."""
    s1 = last or {A: {"p1": 1.0, "p2": 2.0, "p3": 3.0, "p4": 0.0}, B: {"p1": 3.0, "p2": 5.0, "p3": 7.0, "p4": 1.0}}
    s0 = {A: {**s1[A], "p3": 4.0}, B: dict(s1[B])}
    items = sorted({i for column in s0.values() for i in column} | {i for column in s1.values() for i in column})
    return chain.build_with_matrix(
        "Two states",
        indicators=INDICATORS,
        states=[chain.state("s0", "Before", kind="published"), chain.state("s1", "After")],
        steps=[chain.step("one", "One step", kind="fix")],
        values={"s0": s0, "s1": s1},
        units=dict.fromkeys(items, "kg"),
        floors=FLOORS,
    )


def checked_pairs(*pairs):
    return fixes.interactions(True, method="Compared what each fix changes in the model.",
                              by=claims.origin("code", "pair check"), pairs=pairs)  # fmt: skip


def made(*, noise_a=None, noise_b=None, built_ab=1.0013, interactions="listed", built=True):
    """Three fixes against the base:

    - a and b each move p1 in A by less than their tolerance (1e-3): 1.0 to 1.0006 and 1.0007;
    - c moves p3 down in both indicators, as its claim says it must;
    - b and c can interact (a listed pair); the set of a and b was built.
    """
    data, full = chain_and_matrix()
    claim_c = claims.claim("p3 goes down.", [claims.scope([A], {"p3"}, "down", 0.5, claims.MUST)],
                           by=claims.origin("person", "A. Author"))  # fmt: skip
    pairs = {"listed": checked_pairs(("b", "c", "both change one market")), "none": checked_pairs(),
             "unchecked": fixes.interactions(False)}[interactions]  # fmt: skip
    f = fixes.build(
        "Fixes of two states",
        data=data,
        full=full,
        base="s1",
        fixes=[
            fixes.fix("a", "Fix A", kind="mapping", tolerance=chain.tolerance(1e-3), noise=noise_a),
            fixes.fix("b", "Fix B", kind="mapping", tolerance=chain.tolerance(1e-3), noise=noise_b),
            fixes.fix("c", "Fix C", kind="amount", claim=claim_c),
        ],
        results={"a": {A: {"p1": 1.0006}}, "b": {A: {"p1": 1.0007}}, "c": {A: {"p3": 2.0}, B: {"p3": 6.0}}},
        interactions=pairs,
        built=[fixes.built_set("ab", "A and B", ["a", "b"], {A: {"p1": built_ab}})] if built else (),
    )
    return f, data, full


def pair(a, b, reason="r", largest=None):
    return {"fixes": [a, b], "reason": reason, "largest": largest}


def at(f, item):
    return [row[0] for row in f["items"]].index(item)


def changed(f, change):
    return helpers.mutated(f, change)


def said(found, part):
    """Whether one of the errors says `part`."""
    return any(part in line for line in found)


class File(unittest.TestCase):
    def test_a_made_file_is_checked_clean(self):
        f, data, full = made()
        self.assertEqual(fixes.errors(f), [])
        self.assertEqual(fixes.against(f, data, full), [])
        self.assertEqual(fixes.against(f, data, None), [])
        self.assertEqual([row[0] for row in f["items"]], [row[0] for row in full["items"]])

    def test_an_effect_keeps_only_what_changed(self):
        f, *_ = made()
        self.assertEqual(f["fixes"][0]["effect"], {A: [[at(f, "p1"), 1.0006]], B: []})

    def test_the_file_survives_its_own_text(self):
        f, *_ = made()
        self.assertEqual(json.loads(fixes.dumps(f)), f)

    def test_written_and_read_back_beside_its_diagnostics_file(self):
        f, data, full = made()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            chain.write(data, folder / chain.FILE)
            fixes.write(f, folder / "fixes.json")
            self.assertEqual(fixes.read(folder / "fixes.json"), f)  # without the matrix: the listed items
            from sentier_diagnostics import matrix

            matrix.write(full, folder / "matrix.json")
            self.assertEqual(fixes.read(folder / "fixes.json"), f)

    def test_the_limits_are_the_specs(self):
        self.assertEqual((fixes.MAX_FIXES, fixes.MAX_BUILT, fixes.MAX_ITEMS, fixes.MAX_BYTES),
                         (1000, 500, 200_000, 64 * 1024 * 1024))  # fmt: skip
        f, *_ = made()
        many = changed(f, lambda g: g.__setitem__("fixes", g["fixes"] * 334))
        self.assertTrue(said(fixes.errors(many), "`fixes` is not a list of 1 to 1000"))

    def test_another_major_version_is_refused_by_name(self):
        f, *_ = made()
        self.assertEqual(fixes.errors({**f, "format": "sentier-diagnostics-fixes/2"}),
                         ["format 'sentier-diagnostics-fixes/2': this reader knows sentier-diagnostics-fixes/1 only"])  # fmt: skip
        self.assertEqual(fixes.errors({**f, "format": "sentier-diagnostics/1"}),
                         ["not a fixes file of format sentier-diagnostics-fixes/1"])  # fmt: skip

    def test_keys_are_read_strictly(self):
        f, *_ = made()
        self.assertTrue(said(fixes.errors({**f, "ranges": []}), "a key this format does not know: ranges"))
        self.assertTrue(said(fixes.errors({k: v for k, v in f.items() if k != "built"}), "requires: built"))
        extra = changed(f, lambda g: g["fixes"][0].__setitem__("verdicts", {}))
        self.assertTrue(said(fixes.errors(extra), "a fix is not"))

    def test_shape_faults_never_raise(self):
        f, *_ = made()
        valid = {("title", '"x"'), ("about", '"x"'), ("about", "null"), ("made_by", '"x"'), ("notes", "[]"),
                 ("built", "[]")}  # fmt: skip
        for key in f:
            for junk in (None, 1, "x", [], {}, [[None]], {"x": [1]}, True):
                with self.subTest(key=key, junk=junk):
                    found = fixes.errors({**f, key: junk})
                    self.assertFalse(said(found, fixes.fileformat.STOPPED), found)
                    if (key, json.dumps(junk)) not in valid:
                        self.assertNotEqual(found, [], f"{key} = {junk!r} passed")
        for part in ("effect", "counts", "noise", "tolerance", "claim"):
            for junk in (1, "x", [1], {"x": 1}):
                with self.subTest(fix_key=part, junk=junk):
                    found = fixes.errors(changed(f, lambda g, k=part, v=junk: g["fixes"][0].__setitem__(k, v)))
                    self.assertNotEqual(found, [])
                    self.assertFalse(said(found, fixes.fileformat.STOPPED), found)
        self.assertEqual(fixes.errors(None), ["not a fixes file: not an object"])


class Checks(unittest.TestCase):
    """SPEC 16.9, each check probed by the change it must find."""

    def test_of_names_the_file_its_title_and_one_of_its_states(self):
        f, data, full = made()
        self.assertTrue(said(fixes.against(changed(f, lambda g: g["of"].__setitem__("title", "Another")), data, full),
                             "belongs to another file"))  # fmt: skip
        self.assertTrue(said(fixes.against(changed(f, lambda g: g["of"].__setitem__("base", "s9")), data, full),
                             "no state of the diagnostics file"))  # fmt: skip
        self.assertTrue(said(fixes.errors(changed(f, lambda g: g["of"].__setitem__("file", "../up.json"))),
                             "`of` is not {file, title, base}"))  # fmt: skip

    def test_items_indicators_floors_and_words_are_the_diagnostics_files(self):
        f, data, full = made()
        cases = {
            "its indicators differ": lambda g: g["indicators"][0].__setitem__("name", "Another"),
            "its words for an item": lambda g: g.__setitem__("item", {"one": "product", "many": "products"}),
            "its floors differ": lambda g: g["rule"]["floors"][0].__setitem__("value", 0.011),
            "not the matrix's, in the matrix's order": lambda g: g["items"].reverse(),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.against(changed(f, change), data, full), part))

    def test_the_base_is_the_matrix_column_of_the_base_state(self):
        f, data, full = made()
        moved = changed(f, lambda g: g["base"][B].__setitem__(at(g, "p2"), 5.5))
        self.assertEqual(fixes.errors(moved), [])  # no fix touches p2: only the matrix can tell
        self.assertTrue(said(fixes.against(moved, data, full), "the base results in 'x:b' are not the matrix's"))

    def test_without_the_matrix_the_base_is_held_to_the_listed_items(self):
        f, data, _ = made()
        self.assertEqual([i["id"] for i in data["items"]], ["p3"])
        moved = changed(f, lambda g: g["base"][B].__setitem__(at(g, "p3"), 7.5))
        self.assertTrue(said(fixes.against(moved, data, None), "item 'p3', x:b: the base result"))
        fewer = changed(f, lambda g: g["items"].pop())
        self.assertTrue(said(fixes.against(fewer, data, None), "it holds 3 items, and the diagnostics file counts 4"))

    def test_an_effect_names_known_items_once_and_never_the_base(self):
        f, *_ = made()
        k1, k2 = at(f, "p1"), at(f, "p2")
        cases = {
            "names item 99, and the file holds 4": lambda g: g["fixes"][0]["effect"][A].append([99, 1.0]),
            "holds item 'p1' twice": lambda g: g["fixes"][0]["effect"][A].append([k1, 1.5]),
            "is written with the base result": lambda g: g["fixes"][0]["effect"][A].append([k2, 2.0]),
            "not one list per indicator": lambda g: g["fixes"][0]["effect"].__setitem__("x:z", []),
            "an entry is not [item index, result or null]": lambda g: g["fixes"][0]["effect"][B].append([k1]),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))

    def test_built_results_are_held_to_the_same_rules(self):
        f, *_ = made()
        k1 = at(f, "p1")
        cases = {
            "holds item 'p1' twice": lambda g: g["built"][0]["results"][A].append([k1, 1.5]),
            "is written with the base result": lambda g: g["built"][0]["results"][B].append([k1, 3.0]),
            "names item 7": lambda g: g["built"][0]["results"][B].append([7, 3.0]),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))

    def test_counts_and_verdicts_are_what_the_effect_and_the_base_give(self):
        f, *_ = made()

        def move(block, key, a, b):
            block[key][a] -= 1
            block[key][b] += 1

        cases = {
            "`classes` is not": lambda g: move(g["fixes"][0]["counts"][B], "classes", rule.AGREES, rule.WITHIN_NOISE),
            "`verdicts` is not": lambda g: move(g["fixes"][2]["counts"][A], "verdicts", claims.UNCHANGED,
                                                claims.NOT_JUDGED),
            "`bands` is not": lambda g: move(g["fixes"][2]["counts"][A], "bands", "down, factor 1.25-2",
                                             "down, factor 1.1-1.25"),
            "is null: a fix has no published results": lambda g: g["fixes"][0]["counts"][A].update(closer=0, further=0),
        }  # fmt: skip
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))
        # a changed effect with the counts left as they were
        moved = changed(f, lambda g: g["fixes"][0]["effect"][A].__setitem__(0, [at(g, "p1"), 1.5]))
        self.assertTrue(said(fixes.errors(moved), "fix 'a', counts of 'x:a': `classes` is not what its effect"))

    def test_a_fix_claim_names_its_items(self):
        f, *_ = made()
        hidden = changed(f, lambda g: g["fixes"][2]["claim"]["scope"][0].__setitem__("items", None))
        self.assertTrue(said(fixes.errors(hidden), "a fix's claim names its items"))
        unknown = changed(f, lambda g: (g["fixes"][2]["claim"]["scope"][0].__setitem__("items", ["p3", "p9"]),
                                        g["fixes"][2]["claim"].__setitem__("reach", 2)))  # fmt: skip
        self.assertTrue(said(fixes.errors(unknown), "its claim names 1 items the file does not hold"))

    def test_pairs_name_two_known_fixes_once(self):
        f, *_ = made()
        cases = {
            "the file holds no fix 'z'": lambda g: g["interactions"]["pairs"].append(pair("b", "z")),
            "names one fix twice": lambda g: g["interactions"]["pairs"].append(pair("a", "a")),
            "is listed twice": lambda g: g["interactions"]["pairs"].append(pair("c", "b")),
            "does not name two fixes": lambda g: g["interactions"]["pairs"].append({**pair("a", "b"), "fixes": ["a"]}),
            "`largest` is not a share": lambda g: g["interactions"]["pairs"][0].__setitem__("largest", -0.1),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))

    def test_no_half_check(self):
        f, *_ = made()
        listed = changed(f, lambda g: g["interactions"].update(checked=False, method=None, by=None))
        self.assertTrue(said(fixes.errors(listed), "pairs are listed and `checked` is false"))
        f, *_ = made(interactions="unchecked")
        self.assertEqual(fixes.errors(f), [])
        ran = changed(f, lambda g: g["interactions"].__setitem__("method", "Looked at some pairs."))
        self.assertTrue(said(fixes.errors(ran), "no check ran, so it has no `method`"))
        f, *_ = made()
        self.assertTrue(said(fixes.errors(changed(f, lambda g: g["interactions"].__setitem__("by", None))),
                             "says who or what ran it"))  # fmt: skip

    def test_a_built_set_holds_two_or_more_fixes_once_and_is_not_built_twice(self):
        f, *_ = made()
        empty = {A: [], B: []}
        noise = chain.noise()

        def add(names):
            return lambda g: g["built"].append({"id": "x", "label": "X", "fixes": names, "results": empty, "noise": noise})

        cases = {
            "fewer than two fixes": add(["a"]),
            "holds a fix twice": add(["a", "a"]),
            "the same fixes as another built set": add(["b", "a"]),
            "the file holds no fix 'z'": add(["a", "z"]),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))
        twice = changed(f, lambda g: g["built"].append(dict(g["built"][0], fixes=["a", "c"], results=empty)))
        self.assertTrue(said(fixes.errors(twice), "two built sets have the id 'ab'"))


def dense(f, fix_id):
    """A fix's counts worked out item by item, as `chain` counts a step: the reference the
    sparse count is held to."""
    one = next(x for x in f["fixes"] if x["id"] == fix_id)
    floors = {(x["indicator"], x["unit"]): x["value"] for x in f["rule"]["floors"]}
    out = {}
    for ind in (i["id"] for i in f["indicators"]):
        effect = dict(map(tuple, one["effect"][ind]))
        level = (one["noise"]["by"] or {}).get(ind) if one["noise"]["measured"] else None
        block = {"classes": dict.fromkeys(rule.CLASSES, 0), "missing": {"before": 0, "after": 0, "both": 0},
                 "verdicts": dict.fromkeys(claims.VERDICTS, 0) if one["claim"] else None}  # fmt: skip
        for k, row in enumerate(f["items"]):
            before = f["base"][ind][k]
            after = effect.get(k, before)
            kind, way, _ = rule.judge(before, after, floor=floors[(ind, row[4])],
                                      tolerance=one["tolerance"]["value"], noise=level)  # fmt: skip
            block["classes"][kind] += 1
            if kind == rule.MISSING:
                block["missing"]["both" if before is None and after is None else "before" if before is None else "after"] += 1
            if one["claim"]:
                covering = [e for e in claims.entries_for(one["claim"], ind) if claims.covers(e, row[0], ind)]
                block["verdicts"][claims.verdict(kind, before, after, way, covering)] += 1
        out[ind] = block
    return out


class SparseCounts(unittest.TestCase):
    def test_counting_the_changed_items_only_is_counting_every_item(self):
        last = {A: {"p1": 1.0, "p2": 2.0, "p3": 3.0, "p4": 0.0, "p5": None, "p6": -2.0},
                B: {"p1": 3.0, "p2": 5.0, "p3": 7.0, "p4": 1.0, "p5": 4.0, "p6": 0.001}}  # fmt: skip
        data, full = chain_and_matrix(last)
        every = claims.claim("All of B must move; p1 and p5 may move in A.",
                             [claims.scope([B], "*", "up", None, claims.MUST),
                              claims.scope([A], {"p1", "p5"}, "any", None, claims.MAY),
                              claims.scope([A], {"p2", "p4"}, "down", 0.1, claims.MUST)])  # fmt: skip
        wide = fixes.fix("w", "Wide", kind="amount", claim=every, noise=chain.noise(["one", "two"], {A: 0.05}))
        moved = {A: {"p1": 1.02, "p5": 3.0, "p2": None, "p6": 2.0}, B: {"p1": 3.5, "p5": None, "p6": 0.002, "p4": 1.0001}}
        f = fixes.build("Sparse", data=data, full=full, base="s1", fixes=[wide], results={"w": moved})
        again = dense(f, "w")
        for ind, block in f["fixes"][0]["counts"].items():
            for key in ("classes", "missing", "verdicts"):
                with self.subTest(ind=ind, key=key):
                    self.assertEqual(block[key], again[ind][key])
        self.assertEqual(sum(f["fixes"][0]["counts"][B]["verdicts"].values()), 6)


class Acceptance(unittest.TestCase):
    """SPEC 16.11. F7 is the page's (sentier-bafu)."""

    def test_f1_two_fixes_within_the_tolerance_differ_together(self):
        f, *_ = made(built=False)
        for one in ("a", "b"):
            self.assertEqual(fixes.counts(f, [one])["by"][A]["classes"][rule.DIFFERS], 0)
        together = fixes.counts(f, ["a", "b"])
        self.assertEqual(together["by"][A]["classes"][rule.DIFFERS], 1)
        self.assertEqual(together["label"], fixes.EXACT)
        self.assertAlmostEqual(fixes.compose(f, ["a", "b"])["results"][A][at(f, "p1")], 1.0013)

    def test_f2_a_set_with_a_listed_pair_is_estimated_everywhere(self):
        f, *_ = made()
        drawn = fixes.compose(f, ["c", "b"])
        self.assertEqual(drawn["label"], fixes.ESTIMATED)
        self.assertEqual(drawn["pairs"], [pair("b", "c", "both change one market")])
        self.assertEqual(drawn["pair_terms"], {"value": None, "measured": 0, "pairs": 1})
        self.assertEqual(fixes.counts(f, ["b", "c"])["label"], fixes.ESTIMATED)
        self.assertEqual(fixes.label(f, ["a", "b", "c"]), fixes.ESTIMATED)  # a built subset makes no set built
        self.assertEqual(fixes.label(f, ["a", "c"]), fixes.EXACT)

    def test_f3_unchecked_interactions_make_every_set_not_built_estimated(self):
        f, *_ = made(interactions="unchecked")
        self.assertEqual(fixes.label(f, ["a"]), fixes.BUILT)
        self.assertEqual(fixes.label(f, ["a", "b"]), fixes.BUILT)
        for names in (["a", "c"], ["b", "c"], ["a", "b", "c"]):
            self.assertEqual(fixes.label(f, names), fixes.ESTIMATED)

    def test_f4_a_built_set_that_is_not_the_sum_of_independent_fixes_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            made(interactions="none", built_ab=1.0030)
        self.assertIn("built set 'ab', item 'p1', x:a: built 1.003", str(caught.exception))
        self.assertIn("the file calls its fixes independent, and they are not", str(caught.exception))
        f, *_ = made(interactions="none")  # the sum: accepted
        self.assertEqual(fixes.errors(f), [])
        def interacting(g):
            g["built"][0]["results"][A][0] = [at(g, "p1"), 1.0030]
            g["interactions"]["pairs"].append(pair("a", "b", "both change one factor"))

        self.assertEqual(fixes.errors(changed(f, interacting)), [], "a listed pair is an interaction, shown, not refused")
        f, *_ = made(interactions="unchecked", built_ab=1.0030)
        self.assertEqual(fixes.errors(f), [], "without a check the file claims no independence")

    def test_f5_a_fix_is_judged_the_same_whichever_fixes_are_chosen_with_it(self):
        f, *_ = made()
        own = fixes.compose(f, ["c"])["fixes"][0]
        for names in (["a", "c"], ["c", "b"], ["b", "a", "c"]):
            drawn = fixes.compose(f, names)
            self.assertEqual(next(x for x in drawn["fixes"] if x["id"] == "c"), own)
            self.assertNotIn("verdicts", drawn)
            self.assertIsNone(fixes.counts(f, names)["by"][A]["verdicts"])
        self.assertEqual(fixes.compose(f, ["b", "a"])["results"], fixes.compose(f, ["a", "b"])["results"])

    def test_f6_the_noise_of_a_set_is_the_sum_said_with_how_many_were_measured(self):
        noise = chain.noise(["one", "two"], {A: 1e-3})
        f, *_ = made(noise_a=noise, noise_b=noise, interactions="none", built=False)
        self.assertEqual(fixes.noise_of(f, ["a", "b"])[A], {"value": 2e-3, "measured": 2, "fixes": 2})
        self.assertEqual(fixes.noise_of(f, ["a", "c"])[A], {"value": 1e-3, "measured": 1, "fixes": 2})
        self.assertEqual(fixes.noise_of(f, ["c"])[A], {"value": None, "measured": 0, "fixes": 1})
        self.assertEqual(fixes.noise_of(f, ["a"])[B], {"value": None, "measured": 0, "fixes": 1})
        # the sum, not the largest: 1.3e-3 apart is within 2e-3 and beyond 1e-3
        self.assertEqual(fixes.counts(f, ["a", "b"])["by"][A]["classes"][rule.WITHIN_NOISE], 1)

    def test_f8_a_pair_says_why_in_words_never_by_the_models_identifiers(self):
        f, *_ = made()
        # joined here, so that the repository itself holds no identifier-shaped text
        uuid_shaped = "-".join(["ab12cd34", "ab12", "ab12", "ab12", "ab12cd34ef56"])  # noqa: FLY002
        cases = {
            "a pair is not {fixes, reason, largest}": lambda g: g["interactions"]["pairs"][0].__setitem__("activities", ["m"]),
            "its reason holds an identifier": lambda g: g["interactions"]["pairs"][0].__setitem__(
                "reason", f"both change {uuid_shaped}"),
            "`interactions.method` holds an identifier": lambda g: g["interactions"].__setitem__(
                "method", "Compared " + "ab" * 16),
        }  # fmt: skip
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))
        self.assertIsNone(fixes.IDENTIFIER.search(fixes.dumps(f)))


class PairSizes(unittest.TestCase):
    """A listed pair may carry the measured size of its cross term (`largest`): an estimated
    set then says how far it may lie from its sum, and a built pair holds the size to account."""

    def test_a_built_pair_lies_within_its_measured_size(self):
        f, *_ = made(interactions="unchecked", built_ab=1.0030)  # 1.7e-3 from the sum, 1.0013
        f["interactions"] = checked_pairs(("a", "b", "both change one factor"))
        self.assertEqual(fixes.errors(f), [], "not measured: the pair is shown, not held to a size")
        f["interactions"]["pairs"][-1]["largest"] = 0.002
        self.assertEqual(fixes.errors(f), [])
        f["interactions"]["pairs"][-1]["largest"] = 0.001
        found = fixes.errors(f)
        self.assertTrue(said(found, "built set 'ab', item 'p1', x:a"), found)
        self.assertTrue(said(found, "measured their cross term at 0.001 at most, and it is larger"), found)

    def test_the_pair_terms_of_a_set_are_the_sum_of_its_measured_pairs(self):
        f, *_ = made()
        f["interactions"]["pairs"] = [pair("b", "c", "one market", 1e-5), pair("a", "c", "one factor", 2e-5)]
        self.assertEqual(fixes.errors(f), [])
        terms = fixes.pair_terms(f, ["a", "b", "c"])
        self.assertEqual((terms["measured"], terms["pairs"]), (2, 2))
        self.assertAlmostEqual(terms["value"], 3e-5)
        f["interactions"]["pairs"][1]["largest"] = None
        self.assertEqual(fixes.pair_terms(f, ["a", "b", "c"]), {"value": None, "measured": 1, "pairs": 2})
        self.assertEqual(fixes.pair_terms(f, ["a", "b"]), {"value": 0, "measured": 0, "pairs": 0})


class Command(unittest.TestCase):
    def run_cli(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue()

    def test_check_holds_a_fixes_file_to_the_file_beside_it(self):
        from sentier_diagnostics import matrix

        f, data, full = made()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            chain.write(data, folder / chain.FILE)
            matrix.write(full, folder / "matrix.json")
            fixes.write(f, folder / "fixes.json")
            code, out = self.run_cli("check", folder / "fixes.json")
            self.assertEqual(code, 0, out)
            self.assertIn("3 fixes and 1 built sets hold 5 entries over 4 items; the largest fixes: 'c' 2", out)
            fixes.write(changed(f, lambda g: g["base"][B].__setitem__(at(g, "p2"), 5.5)), folder / "fixes.json")
            code, out = self.run_cli("check", folder / "fixes.json")
            self.assertEqual(code, 1, out)
            self.assertIn("the base results in 'x:b' are not the matrix's", out)
            (folder / chain.FILE).unlink()
            code, out = self.run_cli("check", folder / "fixes.json")
            self.assertEqual(code, 1, out)
            self.assertIn("names the diagnostics file diagnostics.json, which is not beside it", out)


if __name__ == "__main__":
    unittest.main()
