"""Fixes against one base (SPEC 16): the file, its check, and what a page draws for a set.
Every value here is made up."""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import chain, claims, cli, fixes, matrix, rule

from . import helpers
from .helpers import INDICATORS, A, B

FLOORS = {(A, "kg"): 0.01, (B, "kg"): 0.01}


def chain_and_matrix(last=None, release=None, noise=None):
    """A chain of two states and its matrix; the base is the second state. Item p3 moved in
    the step, so it is the one listed item. With `release`, a third state after the base.
    `noise` gives a built state its noise, by its id."""
    noise = noise or {}
    s1 = last or {A: {"p1": 1.0, "p2": 2.0, "p3": 3.0, "p4": 0.0}, B: {"p1": 3.0, "p2": 5.0, "p3": 7.0, "p4": 1.0}}
    s0 = {A: {**s1[A], "p3": 4.0}, B: dict(s1[B])}
    items = sorted({i for column in s0.values() for i in column} | {i for column in s1.values() for i in column})
    states = [chain.state("s0", "Before", kind="published"), chain.state("s1", "After", noise=noise.get("s1"))]
    steps, values = [chain.step("one", "One step", kind="fix")], {"s0": s0, "s1": s1}
    if release is not None:
        states.append(chain.state("s2", "Release", noise=noise.get("s2")))
        steps.append(chain.step("two", "Every fix", kind="fix"))
        values["s2"] = release
    return chain.build_with_matrix(
        "Two states",
        indicators=INDICATORS,
        states=states,
        steps=steps,
        values=values,
        units=dict.fromkeys(items, "kg"),
        floors=FLOORS,
    )


def checked_pairs(*pairs):
    return fixes.interactions(True, method="Compared what each fix changes in the model.",
                              by=claims.origin("code", "pair check"), pairs=pairs)  # fmt: skip


#: The base with every fix of `made`: a and b at p1, c at p3.
RELEASE = {A: {"p1": 1.0013, "p2": 2.0, "p3": 2.0, "p4": 0.0}, B: {"p1": 3.0, "p2": 5.0, "p3": 6.0, "p4": 1.0}}


def made(*, noise_a=None, noise_b=None, built_ab=1.0013, interactions="listed", built=True, release=False,
         state_noise=None, noise_ab=None, noise_all=None):  # fmt: skip
    """Three fixes against the base:

    - a and b each move p1 in A by less than their tolerance (1e-3): 1.0 to 1.0006 and 1.0007;
    - c moves p3 down in both indicators, as its claim says it must;
    - b and c can interact (a listed pair); the set of a and b was built.

    With `release`, the chain has a third state, the base with every fix, and a built set of
    every fix says it is that state. `state_noise` gives the chain's built states their noise
    (s1 is the base), `noise_ab` and `noise_all` the built sets theirs."""
    data, full = chain_and_matrix(release=RELEASE if release else None, noise=state_noise)
    claim_c = claims.claim("p3 goes down.", [claims.scope([A], {"p3"}, "down", 0.5, claims.MUST)],
                           by=claims.origin("person", "A. Author"))  # fmt: skip
    pairs = {"listed": checked_pairs(fixes.pair("b", "c", fixes.TECHNOSPHERE)), "none": checked_pairs(),
             "unchecked": fixes.interactions(False)}[interactions]  # fmt: skip
    sets = [fixes.built_set("ab", "A and B", ["a", "b"], {A: {"p1": built_ab}}, noise=noise_ab)] if built else []
    if release:
        sets.append(fixes.built_set("all", "Every fix", ["a", "b", "c"], RELEASE, state="s2", noise=noise_all))
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
        built=sets,
    )
    return f, data, full


def pair(a, b, kind=fixes.TECHNOSPHERE, largest=None, reach=None):
    return fixes.pair(a, b, kind, reach=reach, largest=largest)


def at(f, item):
    return [row[0] for row in f["items"]].index(item)


def named(f, column):
    """A column of results by item: `{item: result}`."""
    return {row[0]: v for row, v in zip(f["items"], column)}


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
            "is written with the result it was measured against": lambda g: g["fixes"][0]["effect"][A].append([k2, 2.0]),
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
            "is written with the result it was measured against": lambda g: g["built"][0]["results"][B].append([k1, 3.0]),
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
            "`kind` is not one of": lambda g: g["interactions"]["pairs"][0].__setitem__("kind", "market"),
            "`reach` is not a count of 1 to 4 items": lambda g: g["interactions"]["pairs"][0].__setitem__("reach", 5),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))

    def test_a_pair_reaches_at_least_one_item(self):
        f, *_ = made()
        self.assertTrue(said(fixes.errors(changed(f, lambda g: g["interactions"]["pairs"][0].__setitem__("reach", 0))),
                             "`reach` is not a count of 1 to 4 items, or null"))  # fmt: skip
        self.assertEqual(fixes.errors(changed(f, lambda g: g["interactions"]["pairs"][0].__setitem__("reach", 4))), [])

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
            return lambda g: g["built"].append({"id": "x", "label": "X", "fixes": names, "state": None, "results": empty,
                                                "noise": noise})  # fmt: skip

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
        self.assertTrue(said(fixes.errors(changed(f, lambda g: g["built"][0].__setitem__("state", 5))),
                             "`state` is not the id of a state"))  # fmt: skip
        self.assertTrue(said(fixes.errors(twice), "two built sets have the id 'ab'"))


def dense(f, fix_id, under=None, under_noise=None):
    """A fix's counts worked out item by item, as `chain` counts a step: the reference the
    sparse count is held to. `under` is what the fix was measured against, written out by
    hand (`{indicator: {item index: result}}`), the base where it says nothing; `under_noise`
    the noise of that build, the base's where it is None. The noise is the sum of the two
    builds' (SPEC 5.3)."""
    under = under or {}
    ends = [under_noise or f["of"].get("base_noise"), next(x for x in f["fixes"] if x["id"] == fix_id)["noise"]]
    one = next(x for x in f["fixes"] if x["id"] == fix_id)
    floors = {(x["indicator"], x["unit"]): x["value"] for x in f["rule"]["floors"]}
    out = {}
    for ind in (i["id"] for i in f["indicators"]):
        effect = dict(map(tuple, one["effect"][ind]))
        said = [n["by"][ind] for n in ends if n and n["measured"] and ind in n["by"]]
        level = None if not said else said[0] if len(said) == 1 else said[0] + said[1]
        block = {"classes": dict.fromkeys(rule.CLASSES, 0), "missing": {"before": 0, "after": 0, "both": 0},
                 "verdicts": dict.fromkeys(claims.VERDICTS, 0) if one["claim"] else None}  # fmt: skip
        for k, row in enumerate(f["items"]):
            before = under.get(ind, {}).get(k, f["base"][ind][k])
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
        self.assertEqual(drawn["pairs"], [pair("b", "c")])
        self.assertEqual(drawn["pair_terms"], {"value": None, "measured": 0, "no_size": 0, "pairs": 1})
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
            g["interactions"]["pairs"].append(pair("a", "b", fixes.SAME_ENTRY))

        self.assertEqual(fixes.errors(changed(f, interacting)), [], "a listed pair is an interaction, shown, not refused")
        f, *_ = made(interactions="unchecked", built_ab=1.0030)
        self.assertEqual(fixes.errors(f), [], "without a check the file claims no independence")

    def test_f4_a_built_set_is_held_to_the_sum_of_its_fixes_not_to_a_build_inside_it(self):
        """Tolerances do not stack: a, b and c built together lie within 1e-3 of the build of a
        and b (1.0022), which lies within 1e-3 of the sum (1.0013), and 1.8e-3 from the sum."""
        f, *_ = made(interactions="none", built_ab=1.0022)
        self.assertEqual(fixes.errors(f), [])

        def add(g):
            p1, p3 = at(g, "p1"), at(g, "p3")
            results = {A: sorted([[p1, 1.0031], [p3, 2.0]]), B: [[p3, 6.0]]}
            g["built"].append({"id": "abc", "label": "Every fix", "fixes": ["a", "b", "c"], "state": None,
                               "results": results, "noise": chain.noise()})  # fmt: skip

        found = fixes.errors(changed(f, add))
        self.assertTrue(said(found, "built set 'abc', item 'p1', x:a: built 1.0031, the sum of its effects is 1.0013"),
                        found)  # fmt: skip

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
        """The base (s1) was not measured: it adds nothing, and is one build of three whose
        noise is not known. Where a set changes nothing, it stands on no build."""
        noise = chain.noise(["one", "two"], {A: 1e-3})
        f, *_ = made(noise_a=noise, noise_b=noise, interactions="none", built=False)
        self.assertEqual(fixes.noise_of(f, ["a", "b"])[A], {"value": 2e-3, "known": 2, "builds": 3})
        self.assertEqual(fixes.noise_of(f, ["a", "c"])[A], {"value": 1e-3, "known": 1, "builds": 3})
        self.assertEqual(fixes.noise_of(f, ["c"])[A], {"value": None, "known": 0, "builds": 2})
        self.assertEqual(fixes.noise_of(f, ["a"])[B], {"value": None, "known": 0, "builds": 0})
        # the sum, not the largest: 1.3e-3 apart is within 2e-3 and beyond 1e-3
        self.assertEqual(fixes.counts(f, ["a", "b"])["by"][A]["classes"][rule.WITHIN_NOISE], 1)

    def test_f8_a_pair_holds_no_text_so_nothing_of_the_model_goes_into_it(self):
        f, *_ = made()
        # joined here, so that the repository itself holds no identifier-shaped text
        uuid_shaped = "-".join(["ab12cd34", "ab12", "ab12", "ab12", "ab12cd34ef56"])  # noqa: FLY002
        cases = {
            "a pair is not {fixes, kind, reach, largest}": lambda g: g["interactions"]["pairs"][0].__setitem__(
                "reason", f"both change {uuid_shaped}"),
            "`kind` is not one of same entry": lambda g: g["interactions"]["pairs"][0].__setitem__(
                "kind", f"both change {uuid_shaped}"),
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
        f["interactions"] = checked_pairs(pair("a", "b", fixes.SAME_ENTRY))
        self.assertEqual(fixes.errors(f), [], "not measured: the pair is shown, not held to a size")
        f["interactions"]["pairs"][-1]["largest"] = 0.002
        self.assertEqual(fixes.errors(f), [])
        f["interactions"]["pairs"][-1]["largest"] = 0.001
        found = fixes.errors(f)
        self.assertTrue(said(found, "built set 'ab', item 'p1', x:a"), found)
        self.assertTrue(said(found, "measured their cross term at 0.001 at most, and it is larger"), found)

    def test_the_pair_terms_of_a_set_are_the_sum_of_its_measured_pairs(self):
        f, *_ = made()
        f["interactions"]["pairs"] = [pair("b", "c", largest=1e-5), pair("a", "c", fixes.SAME_ENTRY, 2e-5)]
        self.assertEqual(fixes.errors(f), [])
        terms = fixes.pair_terms(f, ["a", "b", "c"])
        self.assertEqual((terms["measured"], terms["pairs"]), (2, 2))
        self.assertAlmostEqual(terms["value"], 3e-5)
        f["interactions"]["pairs"][1]["largest"] = None
        self.assertEqual(fixes.pair_terms(f, ["a", "b", "c"]), {"value": None, "measured": 1, "no_size": 0, "pairs": 2})
        self.assertEqual(fixes.pair_terms(f, ["a", "b"]), {"value": 0, "measured": 0, "no_size": 0, "pairs": 0})

    def test_a_pair_with_no_size_is_built_and_its_build_has_none(self):
        """A build of a and b on the other side of zero from their sum: no tolerance makes the
        two agree. Said of a build 1.7e-3 from its sum (1.0030 and 1.0013), it is refused:
        that is its size."""
        f, *_ = made(interactions="unchecked", built_ab=-0.5)
        f["interactions"] = checked_pairs(pair("a", "b", fixes.SAME_ENTRY, fixes.NO_SIZE))
        self.assertEqual(fixes.errors(f), [])
        self.assertEqual(fixes.pair_terms(f, ["a", "b", "c"]), {"value": None, "measured": 1, "no_size": 1, "pairs": 1})
        self.assertEqual(fixes.label(f, ["a", "b"]), fixes.BUILT)
        self.assertEqual(fixes.label(f, ["a", "b", "c"]), fixes.ESTIMATED)
        self.assertEqual(named(f, fixes.compose(f, ["a", "b", "c"])["results"][A])["p1"], -0.5, "taken from the build")
        agrees = changed(f, lambda g: g["built"][0]["results"][A][0].__setitem__(1, 1.0030))
        self.assertTrue(said(fixes.errors(agrees), "built set 'ab': the file says its pair has no size, and its build "
                                                   "lies within 0.00169491525"))  # fmt: skip
        unbuilt = changed(f, lambda g: g["built"].clear())
        self.assertTrue(said(fixes.errors(unbuilt), "the pair 'a' and 'b': has no size, so no set holding it can be drawn"))
        other = changed(f, lambda g: g["interactions"]["pairs"][0].__setitem__("largest", "large"))
        self.assertTrue(said(fixes.errors(other), "`largest` is not a share, 'no size' where no tolerance is enough"))

    def test_the_kinds_are_listed_in_their_order_of_precedence(self):
        self.assertEqual(fixes.PAIR_KINDS, ("same entry", "technosphere", "technosphere and emission",
                                            "technosphere and factor", "emission and factor"))  # fmt: skip

def with_requires(*, built_ab=True):
    """Fixes that need others applied first, against the base of `chain_and_matrix`:

    - a moves p1 in A to 1.5; b moves p2 in B to 5.5; both alone;
    - d requires a: built with a and d, p1 is 1.8 and p2 is 2.5;
    - e requires d (so a too): with a, d and e, p3 is 3.3 as well;
    - g requires a and b: with a, b and g, p1 is 1.6, p2 is 2.2 and p4 is 0.5. The file holds
      a build of a and b, which g was measured against.

    Each fix's results are written whole, as built; its effect keeps what it changed on top
    of what it requires."""
    data, full = chain_and_matrix()
    f = fixes.build(
        "Fixes that need others",
        data=data,
        full=full,
        base="s1",
        fixes=[
            fixes.fix("a", "Fix A", kind="mapping"),
            fixes.fix("b", "Fix B", kind="mapping"),
            fixes.fix("d", "Fix D", kind="amount", requires=["a"]),
            fixes.fix("e", "Fix E", kind="amount", requires=["d"]),
            fixes.fix("g", "Fix G", kind="amount", requires=["a", "b"]),
        ],
        results={
            "a": {A: {"p1": 1.5}},
            "b": {B: {"p2": 5.5}},
            "d": {A: {"p1": 1.8, "p2": 2.5}},
            "e": {A: {"p1": 1.8, "p2": 2.5, "p3": 3.3}},
            "g": {A: {"p1": 1.6, "p2": 2.2, "p4": 0.5}, B: {"p2": 5.5}},
        },
        interactions=checked_pairs(),
        built=[fixes.built_set("ab", "A and B", ["a", "b"], {A: {"p1": 1.5}, B: {"p2": 5.5}})] if built_ab else (),
    )
    return f, data, full


class Requires(unittest.TestCase):
    """A fix that cannot be applied alone names the fixes it needs (SPEC 16.2)."""

    def test_a_fix_is_measured_against_the_build_of_what_it_requires(self):
        f, data, full = with_requires()
        self.assertEqual(fixes.errors(f), [])
        self.assertEqual(fixes.against(f, data, full), [])
        effect = {one["id"]: one["effect"] for one in f["fixes"]}
        p1, p2, p3, p4 = (at(f, p) for p in ("p1", "p2", "p3", "p4"))
        self.assertEqual(effect["d"], {A: [[p1, 1.8], [p2, 2.5]], B: []})
        self.assertEqual(effect["e"], {A: [[p3, 3.3]], B: []}, "what d already did is d's")
        self.assertEqual(effect["g"], {A: [[p1, 1.6], [p2, 2.2], [p4, 0.5]], B: []}, "b's change in B is b's")
        # the counts: against that build, item by item
        under = {"d": {A: {p1: 1.5}}, "e": {A: {p1: 1.8, p2: 2.5}}, "g": {A: {p1: 1.5}, B: {p2: 5.5}}}
        for one in f["fixes"]:
            again = dense(f, one["id"], under.get(one["id"]))
            for ind in (A, B):
                with self.subTest(fix=one["id"], ind=ind):
                    self.assertEqual(one["counts"][ind]["classes"], again[ind]["classes"])
        e = f["fixes"][3]["counts"][A]["classes"]
        self.assertEqual((e[rule.DIFFERS], e[rule.AGREES], e[rule.NEAR_ZERO]), (1, 2, 1), "e changes p3 only")

    def test_an_effect_written_with_the_result_of_its_requirements_is_refused(self):
        f, *_ = with_requires()
        stale = changed(f, lambda g: g["fixes"][2]["effect"][A].append([at(g, "p4"), 0.0]))
        self.assertTrue(said(fixes.errors(stale), "item 'p4' is written with the result it was measured against"))
        kept = changed(f, lambda g: g["fixes"][3]["effect"][A].insert(0, [at(g, "p1"), 1.8]))
        self.assertTrue(said(fixes.errors(kept), "fix 'e': its effect, x:a: item 'p1' is written with the result"))

    def test_choosing_a_fix_chooses_what_it_requires(self):
        f, *_ = with_requires()
        self.assertEqual(fixes.chosen(f, ["e"]), (["a", "d", "e"], ["a", "d"]))
        drawn = fixes.compose(f, ["e"])
        self.assertEqual((drawn["label"], drawn["added"]), (fixes.BUILT, ["a", "d"]))
        self.assertEqual(named(f, drawn["results"][A]), {"p1": 1.8, "p2": 2.5, "p3": 3.3, "p4": 0.0})
        self.assertEqual([x["requires"] for x in drawn["fixes"]], [[], ["a"], ["d"]])
        self.assertEqual(fixes.label(f, ["g"]), fixes.BUILT)
        drawn = fixes.compose(f, ["g"])["results"]
        self.assertEqual(named(f, drawn[A]), {"p1": 1.6, "p2": 2.2, "p3": 3.0, "p4": 0.5})
        self.assertEqual(named(f, drawn[B]), {"p1": 3.0, "p2": 5.5, "p3": 7.0, "p4": 1.0})

    def test_effects_add_each_on_top_of_what_it_was_measured_with(self):
        f, *_ = with_requires()
        # e and b: every item is one fix's with what it requires, so each result is a built one
        drawn = fixes.compose(f, ["e", "b"])
        self.assertEqual((drawn["label"], drawn["added"]), (fixes.EXACT, ["a", "d"]))
        self.assertEqual(named(f, drawn["results"][A]), {"p1": 1.8, "p2": 2.5, "p3": 3.3, "p4": 0.0})
        self.assertEqual(named(f, drawn["results"][B]), {"p1": 3.0, "p2": 5.5, "p3": 7.0, "p4": 1.0})
        # d and g both build on a: a's effect counts once, each of theirs on top
        drawn = fixes.compose(f, ["d", "g"])
        self.assertEqual(drawn["label"], fixes.EXACT)
        p1, p2 = at(f, "p1"), at(f, "p2")
        self.assertAlmostEqual(drawn["results"][A][p1], 1.0 + 0.5 + 0.3 + 0.1)
        self.assertAlmostEqual(drawn["results"][A][p2], 2.0 + 0.5 + 0.2)
        self.assertEqual(drawn["cannot_add"], {A: [], B: []})

    def test_where_one_fix_with_its_requirements_covers_an_item_its_build_is_the_result(self):
        """a removes p1's result and d, which requires a, gives it one: no difference can be
        taken against a missing result, so only the build of d says what p1 is."""
        data, full = chain_and_matrix()
        four = [fixes.fix("a", "A", kind="mapping"), fixes.fix("d", "D", kind="amount", requires=["a"]),
                fixes.fix("b", "B", kind="mapping"), fixes.fix("c", "C", kind="mapping")]  # fmt: skip
        results = {"a": {A: {"p1": None}}, "d": {A: {"p1": 2.0}}, "b": {A: {"p2": 2.5}}, "c": {A: {"p1": 1.2}}}
        f = fixes.build("A requirement that removes a result", data=data, full=full, base="s1", fixes=four,
                        results=results, interactions=checked_pairs())  # fmt: skip
        p1 = at(f, "p1")
        drawn = fixes.compose(f, ["d", "b"])
        self.assertEqual((drawn["label"], drawn["results"][A][p1], drawn["cannot_add"]), (fixes.EXACT, 2.0, {A: [], B: []}))
        for names in (["d", "c"], ["a", "c"]):
            with self.subTest(names=names):
                drawn = fixes.compose(f, names)
                self.assertEqual((drawn["results"][A][p1], drawn["cannot_add"]), (None, {A: [p1], B: []}))

    def test_where_a_build_inside_the_set_covers_an_item_its_result_is_measured_not_summed(self):
        """a and b interact at p1 (a listed pair): built together, p1 is 2.9, not their sum 2.7.
        g requires both and leaves p1 alone; c is apart."""
        data, full = chain_and_matrix()
        four = [fixes.fix("a", "A", kind="mapping"), fixes.fix("b", "B", kind="mapping"),
                fixes.fix("g", "G", kind="amount", requires=["a", "b"]), fixes.fix("c", "C", kind="amount")]  # fmt: skip
        results = {"a": {A: {"p1": 1.5}}, "b": {A: {"p1": 2.2}}, "g": {A: {"p1": 2.9, "p2": 3.0}}, "c": {A: {"p3": 2.0}}}
        f = fixes.build("A measured joint", data=data, full=full, base="s1", fixes=four, results=results,
                        interactions=checked_pairs(pair("a", "b")),
                        built=[fixes.built_set("ab", "A and B", ["a", "b"], {A: {"p1": 2.9}})])  # fmt: skip
        p1 = at(f, "p1")
        for names in (["a", "b", "c"], ["g", "c"]):
            with self.subTest(names=names):
                drawn = fixes.compose(f, names)
                self.assertEqual((drawn["label"], drawn["results"][A][p1]), (fixes.ESTIMATED, 2.9))
        # the sum a built set is held to stands on the fixes alone
        cells = fixes._Builds.of(f).composed(frozenset({"a", "b", "c"}), A, built=False)
        self.assertAlmostEqual(cells[p1][0], 2.7)

    def test_a_fix_whose_requirements_were_never_built_together_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            with_requires(built_ab=False)
        self.assertIn("fix 'g': no build of what it requires (a, b)", str(caught.exception))
        f, *_ = with_requires()
        gone = changed(f, lambda g: g["built"].clear())
        self.assertTrue(said(fixes.errors(gone), "it requires 'a', 'b', and the file holds no build of them together"))

    def test_requires_names_earlier_fixes_once(self):
        f, *_ = with_requires()
        cases = {
            "fix 'd': requires itself": lambda g: g["fixes"][2].__setitem__("requires", ["d"]),
            "requires 'z', and the file holds no such fix": lambda g: g["fixes"][2].__setitem__("requires", ["z"]),
            "requires 'b', which comes after it": lambda g: g["fixes"][0].__setitem__("requires", ["b"]),
            "requires a fix twice": lambda g: g["fixes"][2].__setitem__("requires", ["a", "a"]),
            "`requires` is not a list of the ids of fixes": lambda g: g["fixes"][2].__setitem__("requires", "a"),
        }
        for part, change in cases.items():
            with self.subTest(part):
                self.assertTrue(said(fixes.errors(changed(f, change)), part))
        with self.assertRaises(ValueError):
            fixes.build("x", data=chain_and_matrix()[0], full=chain_and_matrix()[1], base="s1",
                        fixes=[fixes.fix("d", "D", kind="amount", requires=["a"]), fixes.fix("a", "A", kind="amount")],
                        results={})  # fmt: skip

    def test_a_fix_and_what_it_requires_are_never_a_pair(self):
        f, *_ = with_requires()
        for a, b in (("a", "d"), ("e", "a"), ("d", "e")):
            with self.subTest(pair=(a, b)):
                found = fixes.errors(changed(f, lambda g, a=a, b=b: g["interactions"]["pairs"].append(pair(a, b))))
                self.assertTrue(said(found, "one requires the other"), found)
        self.assertEqual(fixes.errors(changed(f, lambda g: g["interactions"]["pairs"].append(pair("d", "g")))), [])

    def test_a_built_set_holds_what_its_fixes_require_and_is_not_a_fix_with_its_requirements(self):
        f, *_ = with_requires()
        empty, noise = {A: [], B: []}, chain.noise()

        def add(names, results=empty):
            return lambda g: g["built"].append({"id": "x", "label": "X", "fixes": names, "state": None,
                                                "results": results, "noise": noise})  # fmt: skip

        self.assertTrue(said(fixes.errors(changed(f, add(["d", "b"]))), "holds 'd' without 'a', which it requires"))
        self.assertTrue(said(fixes.errors(changed(f, add(["a", "d"]))), "is built already: it is fix 'd'"))
        # a, b and d built together: checked, with no listed pair, so it must be the sum
        p1, p2 = at(f, "p1"), at(f, "p2")
        summed = {A: [[p1, 1.8], [p2, 2.5]], B: [[p2, 5.5]]}
        self.assertEqual(fixes.errors(changed(f, add(["a", "b", "d"], summed))), [])
        self.assertEqual(fixes.label(changed(f, add(["a", "b", "d"], summed)), ["d", "b"]), fixes.BUILT)
        off = {A: [[p1, 1.8], [p2, 2.9]], B: [[p2, 5.5]]}
        found = fixes.errors(changed(f, add(["a", "b", "d"], off)))
        self.assertTrue(said(found, "built set 'x', item 'p2', x:a: built 2.9, the sum of its effects is 2.5"), found)


def with_added():
    """One fix that brings an item no state of the chain holds: p9, in kg."""
    data, full = chain_and_matrix()
    f = fixes.build(
        "Fixes that add an item",
        data=data,
        full=full,
        base="s1",
        fixes=[fixes.fix("n", "A new item", kind="mapping")],
        results={"n": {A: {"p9": 0.7}, B: {"p9": 1.2}}},
        interactions=checked_pairs(),
        added_items=[["p9", "A new thing", None, None, "kg"]],
    )
    return f, data, full


class AddedItems(unittest.TestCase):
    """A fix may bring items the base does not hold (SPEC 16.2)."""

    def test_an_added_item_follows_the_matrix_items_with_no_base_result(self):
        f, data, full = with_added()
        self.assertEqual(fixes.errors(f), [])
        self.assertEqual(fixes.against(f, data, full), [])
        self.assertEqual(fixes.against(f, data, None), [])
        self.assertEqual([row[0] for row in f["items"]], [row[0] for row in full["items"]] + ["p9"])
        self.assertEqual((f["base"][A][-1], f["base"][B][-1]), (None, None))
        self.assertEqual(named(f, fixes.compose(f, ["n"])["results"][A]),
                         {"p1": 1.0, "p2": 2.0, "p3": 3.0, "p4": 0.0, "p9": 0.7})  # fmt: skip
        self.assertEqual(f["fixes"][0]["counts"][A]["missing"], {"before": 1, "after": 0, "both": 0})

    def test_an_added_item_has_no_base_result_and_a_result_from_some_fix(self):
        f, data, full = with_added()
        held = changed(f, lambda g: g["base"][A].__setitem__(4, 0.7))
        self.assertTrue(said(fixes.against(held, data, full), "item 'p9' is not in the matrix, and the base has a result"))
        idle = changed(f, lambda g: g["fixes"][0].update(effect={A: [], B: []}))
        self.assertTrue(said(fixes.against(idle, data, full), "item 'p9' is in no state of the chain, and no fix gives it"))
        with self.assertRaises(ValueError) as caught:
            fixes.build("x", data=data, full=full, base="s1", fixes=[fixes.fix("n", "N", kind="mapping")], results={},
                        interactions=checked_pairs(), added_items=[["p9", "A new thing", None, None, "kg"]])  # fmt: skip
        self.assertIn("item 'p9' is in no state of the chain", str(caught.exception))

    def test_an_added_item_in_a_new_unit_gets_a_floor_from_nothing(self):
        """No item of the chain is in litres: the chain would give the unit a floor of 0, from no
        result, so the fixes file does."""
        data, full = chain_and_matrix()
        f = fixes.build("An item in litres", data=data, full=full, base="s1", fixes=[fixes.fix("n", "N", kind="mapping")],
                        results={"n": {A: {"p9": 0.7}, B: {"p9": 1.2}}}, interactions=checked_pairs(),
                        added_items=[["p9", "A new thing", None, None, "l"]])  # fmt: skip
        self.assertEqual(f["rule"]["floors"][-2:], [{"indicator": i, "unit": "l", "value": 0.0, "basis": "none", "n": 0}
                                                    for i in (A, B)])  # fmt: skip
        self.assertEqual((fixes.errors(f), fixes.against(f, data, full), fixes.against(f, data, None)), ([], [], []))
        raised = changed(f, lambda g: g["rule"]["floors"][-1].__setitem__("value", 0.5))
        self.assertEqual(fixes.errors(raised), [])
        self.assertTrue(said(fixes.against(raised, data, full), "its floors differ from the diagnostics file's"))

    def test_added_items_come_after_the_matrix_items_and_are_new(self):
        f, data, full = with_added()
        first = changed(f, lambda g: g["items"].insert(0, g["items"].pop()))
        self.assertTrue(said(fixes.against(first, data, full), "before any item a fix adds"))
        with self.assertRaises(ValueError) as caught:
            fixes.build("x", data=data, full=full, base="s1", fixes=[fixes.fix("n", "N", kind="mapping")], results={},
                        added_items=[["p2", "Again", None, None, "kg"]])  # fmt: skip
        self.assertIn("an added item is an item of the base already", str(caught.exception))


class ChainState(unittest.TestCase):
    """A built set may say it is a state of the chain after the base: the two builds are held
    to each other (SPEC 16.4)."""

    def test_a_built_set_that_is_a_state_agrees_with_it(self):
        f, data, full = made(release=True)
        self.assertEqual(fixes.errors(f), [])
        self.assertEqual(fixes.against(f, data, full), [])
        self.assertEqual(fixes.against(f, data, None), [])
        self.assertEqual(fixes.label(f, ["c", "b", "a"]), fixes.BUILT)

    def test_a_built_set_that_is_not_the_state_it_names_is_refused(self):
        f, data, full = made(release=True)
        def nudge(g):
            entries = g["built"][-1]["results"][A]
            entries[[k for k, _ in entries].index(at(g, "p1"))][1] = 1.01

        off = changed(f, nudge)
        self.assertEqual(fixes.errors(off), [], "on its own the file cannot tell")
        found = fixes.against(off, data, full)
        self.assertTrue(said(found, "built set 'all', item 'p1', x:a: built 1.01, and state 's2' of the chain"), found)
        self.assertEqual([i["id"] for i in data["items"]], ["p3", "p1"])
        found = fixes.against(off, data, None)
        self.assertTrue(said(found, "built set 'all', item 'p1', x:a: built 1.01"), "without the matrix: the listed items")

    def test_the_state_comes_after_the_base(self):
        f, data, full = made(release=True)
        for state in ("s1", "s0", "s9"):
            with self.subTest(state=state):
                moved = changed(f, lambda g, s=state: g["built"][-1].__setitem__("state", s))
                self.assertTrue(said(fixes.against(moved, data, full), "is not a state of the chain after the base"))

def measured(value, ind=A):
    return chain.noise(["one", "two"], {ind: value})


class Noise(unittest.TestCase):
    """Noise belongs to a build, as it belongs to a state of a chain (SPEC 5.3, 16.5): the
    base's is its state's, a fix's that of the build with it, a built set's that of its
    build. A comparison takes the sum of the noise of the builds it stands on."""

    def test_the_base_takes_the_noise_of_its_state(self):
        f, data, full = made(state_noise={"s1": measured(1e-4)})
        self.assertEqual(f["of"]["base_noise"], data["states"][1]["noise"])
        self.assertEqual(fixes.errors(f), [])
        self.assertEqual(fixes.against(f, data, full), [])
        other = changed(f, lambda g: g["of"]["base_noise"]["by"].__setitem__(A, 2e-4))
        self.assertTrue(said(fixes.against(other, data, full), "`of.base_noise` is not the noise the diagnostics file "
                                                               "gives state 's1'"))  # fmt: skip
        gone = changed(f, lambda g: g["of"].pop("base_noise"))
        self.assertEqual(fixes.errors(gone), [], "on its own the file cannot tell a published base")
        self.assertTrue(said(fixes.against(gone, data, full), "the base is a build: `of.base_noise` is its noise"))
        bad = changed(f, lambda g: g["of"]["base_noise"].__setitem__("between", None))
        self.assertTrue(said(fixes.errors(bad), "`of.base_noise`: measured noise names the two builds"))

    def test_a_published_base_is_exact_and_takes_no_noise(self):
        data, full = chain_and_matrix()
        f = fixes.build("From the published results", data=data, full=full, base="s0",
                        fixes=[fixes.fix("a", "Fix A", kind="mapping", noise=measured(1e-3))],
                        results={"a": {A: {"p1": 1.5}}})  # fmt: skip
        self.assertNotIn("base_noise", f["of"])
        self.assertEqual(fixes.noise_of(f, ["a"])[A], {"value": 1e-3, "known": 2, "builds": 2})
        self.assertEqual(fixes.noise_of(f, ["a"])[B], {"value": None, "known": 0, "builds": 0}, "a changes nothing in B")
        noisy = changed(f, lambda g: g["of"].__setitem__("base_noise", chain.noise()))
        self.assertTrue(said(fixes.against(noisy, data, full), "the base is the published results, which are exact"))

    def test_a_fix_is_judged_with_the_noise_of_its_build_and_of_the_base(self):
        """1.0 to 1.0015 is 1.5e-3 apart: beyond the tolerance (1e-3) and the fix's own noise
        (1e-3), within the sum of its and the base's (2e-3)."""

        def judged(base_noise):
            data, full = chain_and_matrix(noise={"s1": base_noise})
            f = fixes.build("One fix", data=data, full=full, base="s1",
                            fixes=[fixes.fix("a", "Fix A", kind="mapping", tolerance=chain.tolerance(1e-3),
                                             noise=measured(1e-3))],
                            results={"a": {A: {"p1": 1.0015}}})  # fmt: skip
            self.assertEqual(f["fixes"][0]["counts"][A]["classes"], dense(f, "a")[A]["classes"])
            return f["fixes"][0]["counts"][A]["classes"][rule.WITHIN_NOISE]

        self.assertEqual(judged(measured(1e-3)), 1)
        self.assertEqual(judged(None), 0)

    def test_a_fix_measured_against_its_requirements_takes_their_builds_noise(self):
        """d is 1.5e-3 from the build of a: within the noise of a's build and d's, beyond d's
        and the base's (not measured)."""
        data, full = chain_and_matrix()
        f = fixes.build("A fix that needs another", data=data, full=full, base="s1",
                        fixes=[fixes.fix("a", "Fix A", kind="mapping", noise=measured(1e-3)),
                               fixes.fix("d", "Fix D", kind="amount", requires=["a"], tolerance=chain.tolerance(1e-3),
                                         noise=measured(1e-3))],
                        results={"a": {A: {"p1": 1.5}}, "d": {A: {"p1": 1.5 * 1.0015}}})  # fmt: skip
        counts = f["fixes"][1]["counts"][A]["classes"]
        self.assertEqual(counts[rule.WITHIN_NOISE], 1)
        again = dense(f, "d", {A: {at(f, "p1"): 1.5}}, under_noise=measured(1e-3))
        self.assertEqual(counts, again[A]["classes"])

    def test_a_sum_counts_the_base_once_for_each_fix_measured_against_it(self):
        """a and b each moved p1 from the base: a rebuild of the base moves both differences.
        With a and c, no item is a sum: p1 is a's build and p3 c's, each against the base."""
        f, *_ = made(noise_a=measured(1e-3), noise_b=measured(1e-3), interactions="none", built=False,
                     state_noise={"s1": measured(1e-4)})  # fmt: skip
        self.assertEqual(fixes.noise_of(f, ["a", "b"])[A], {"value": 1e-4 + 1e-3 + 1e-4 + 1e-3, "known": 3, "builds": 3})
        self.assertEqual(fixes.noise_of(f, ["a", "c"])[A], {"value": 1e-4 + 1e-3, "known": 2, "builds": 3})
        self.assertEqual(fixes.noise_of(f, ["c"])[A], {"value": 1e-4, "known": 1, "builds": 2}, "one fix: its build")
        drawn = fixes.compose(f, ["a", "c"])
        self.assertEqual(named(f, [drawn["item_noise"][A].get(k) for k in range(len(f["items"]))]),
                         {"p1": 1e-4 + 1e-3, "p2": None, "p3": 1e-4, "p4": None})  # fmt: skip

    def test_an_item_takes_the_noise_of_the_builds_its_result_stands_on_never_another_fixs(self):
        """sentier-bafu's probe: three fixes on three items, each build at 1 %, the base at
        0.5 %; c moves p3 by 2.9 %. At p3 the set's result is c's build, so its noise is the
        base's and c's (1.5 %) whichever fixes are ticked with c: p3 differs in every set. A
        noise summed over every fix (4.5 % for three) would put it within noise as soon as a
        is ticked."""
        f = disjoint()
        for names in (["c"], ["a", "c"], ["a", "b", "c"]):
            with self.subTest(names=names):
                self.assertEqual(fixes.compose(f, names)["item_noise"][A][at(f, "p3")], 0.005 + 0.01)
                classes = fixes.counts(f, names)["by"][A]["classes"]
                self.assertEqual((classes[rule.DIFFERS], classes[rule.WITHIN_NOISE]), (len(names), 0))
        self.assertEqual(fixes.noise_of(f, ["a", "b", "c"])[A], {"value": 0.005 + 0.01, "known": 4, "builds": 4})

    def test_a_set_counts_each_item_with_its_own_noise(self):
        """a moves p1 by 2.9 % with its build at 1 %; c moves p3 by 10 % with its build at 4 %.
        In the set of both, p1 is judged with 1.5 % and differs; the set's largest noise (4.5 %)
        would put it within noise."""
        data, full = chain_and_matrix(noise={"s1": measured(0.005)})
        f = fixes.build("Two noises", data=data, full=full, base="s1",
                        fixes=[fixes.fix("a", "Fix a", kind="amount", noise=measured(0.01)),
                               fixes.fix("c", "Fix c", kind="amount", noise=measured(0.04))],
                        results={"a": {A: {"p1": 1.029}}, "c": {A: {"p3": 3.3}}},
                        interactions=checked_pairs())  # fmt: skip
        self.assertEqual(fixes.errors(f), [])
        noise = fixes.compose(f, ["a", "c"])["item_noise"][A]
        self.assertEqual((noise[at(f, "p1")], noise[at(f, "p3")]), (0.005 + 0.01, 0.005 + 0.04))
        classes = fixes.counts(f, ["a", "c"])["by"][A]["classes"]
        self.assertEqual((classes[rule.DIFFERS], classes[rule.WITHIN_NOISE]), (2, 0))

    def test_a_built_set_is_compared_as_its_own_build(self):
        f, *_ = made(noise_ab=measured(5e-3), interactions="none", state_noise={"s1": measured(1e-4)})
        self.assertEqual(fixes.label(f, ["a", "b"]), fixes.BUILT)
        self.assertEqual(fixes.noise_of(f, ["a", "b"])[A], {"value": 1e-4 + 5e-3, "known": 2, "builds": 2})

    def test_a_sum_runs_in_the_order_of_the_file(self):
        """Six fixes change p1, the base is the published results. Their builds' noise summed in
        the order of the file is 0.26099999999999995; of the 720 orders only that one and the
        one with its first two swapped give that float, so an order by id, by the set's own
        hashing or by anything else is caught: the page's port must sum as the file runs, not
        as an object's keys come. (sentier-bafu's review: 3 fixes already in id order let an
        id-sorted sum through.)"""
        order = (("f", 0.084), ("b", 0.012), ("e", 0.058), ("a", 0.016), ("d", 0.05), ("c", 0.041))
        data, full = chain_and_matrix()
        f = fixes.build("Six on one item", data=data, full=full, base="s1",
                        fixes=[fixes.fix(x, f"Fix {x}", kind="amount", noise=measured(n)) for x, n in order],
                        results={x: {A: {"p1": 1.0 + n}} for x, n in order},
                        interactions=checked_pairs())  # fmt: skip

        def summed(noises):
            level = None
            for n in noises:
                level = n if level is None else level + n
            return level

        in_file = summed(n for _, n in order)
        self.assertEqual(fixes.compose(f, sorted(x for x, _ in order))["item_noise"][A][at(f, "p1")], in_file)
        alike = [p for p in itertools.permutations(order) if summed(n for _, n in p) == in_file]
        self.assertEqual(alike, [order, (order[1], order[0], *order[2:])], "the test no longer tells orders apart")

    def test_a_result_taken_from_a_build_inside_the_set_takes_that_builds_noise(self):
        """The set of a, b and c takes p1 in A from the build of a and b: p1 stands on that
        build and the base, not on a's and b's own builds; p3 on c's and the base."""
        f, *_ = made(noise_ab=measured(5e-2), interactions="none")
        self.assertEqual(fixes.label(f, ["a", "b", "c"]), fixes.EXACT)
        noise = fixes.noise_of(f, ["a", "b", "c"])
        self.assertEqual(noise[A], {"value": 5e-2, "known": 1, "builds": 3})
        self.assertEqual(noise[B], {"value": None, "known": 0, "builds": 2})
        self.assertEqual(fixes.compose(f, ["a", "b", "c"])["noise"], noise)
        self.assertEqual(fixes.counts(f, ["a", "b", "c"])["by"][A]["classes"][rule.WITHIN_NOISE], 1)

    def test_a_built_set_is_held_to_its_sum_with_the_noise_of_every_build_both_stand_on(self):
        """1.00406 is 2.75e-3 from the sum, 1.0013: within the noise of the base three times
        (once, and once under each fix), a, b and the built set (6 x 5e-4); beyond it with any
        one of them left out (5 x 5e-4), and without the base (3 x 5e-4)."""
        kw = {"noise_a": measured(5e-4), "noise_b": measured(5e-4), "noise_ab": measured(5e-4), "interactions": "none",
              "built_ab": 1.00406}  # fmt: skip
        f, *_ = made(state_noise={"s1": measured(5e-4)}, **kw)
        self.assertEqual(fixes.errors(f), [])
        gone = changed(f, lambda g: g["of"].pop("base_noise"))
        self.assertTrue(said(fixes.errors(gone), "built set 'ab', item 'p1', x:a: built 1.00406"))
        own = changed(f, lambda g: g["built"][0].__setitem__("noise", chain.noise()))
        self.assertTrue(said(fixes.errors(own), "built set 'ab', item 'p1', x:a: built 1.00406"))

    def test_a_built_set_is_held_at_each_item_to_the_builds_its_sum_stands_on_there(self):
        """The three fixes built together, p3 1.8 % from c's build: within the noise of that
        build and the built set's (2 %), not of the base's and the built set's (1.5 %). At
        2.4 % it is refused, where every fix's noise and the base's (6 %) would let it pass."""
        f = disjoint()
        self.assertEqual(fixes.errors(f), [])
        p1, p2, p3 = (at(f, p) for p in ("p1", "p2", "p3"))

        def add(value):
            return lambda g: g["built"].append({"id": "abc", "label": "All three", "fixes": ["a", "b", "c"], "state": None,
                                                "results": {A: sorted([[p1, 1.5], [p2, 2.5], [p3, value]]), B: []},
                                                "noise": measured(0.01)})  # fmt: skip

        self.assertEqual(fixes.errors(changed(f, add(3.09 * 1.018))), [], "1.8 % from c's build: within 2 %")
        found = fixes.errors(changed(f, add(3.09 * 1.025)))
        self.assertTrue(said(found, "built set 'abc', item 'p3', x:a"), found)

    def test_a_built_set_is_held_at_an_item_none_of_its_fixes_change_to_the_base(self):
        """a and b built together move p3, which neither changes: there the sum is the base, so
        the build is held to it with the base's noise and its own (1.5 %). 1.2 % passes; it
        would not with the built set's noise alone (1 %). 1.6 % is refused. (sentier-bafu's
        review: no test had a built set move an item none of its fixes move.)"""
        f = disjoint()
        p1, p2, p3 = (at(f, p) for p in ("p1", "p2", "p3"))

        def add(value):
            return lambda g: g["built"].append({"id": "ab", "label": "A and B", "fixes": ["a", "b"], "state": None,
                                                "results": {A: sorted([[p1, 1.5], [p2, 2.5], [p3, value]]), B: []},
                                                "noise": measured(0.01)})  # fmt: skip

        self.assertEqual(fixes.errors(changed(f, add(3.0 * 1.012))), [], "1.2 % from the base: within 1.5 %")
        found = fixes.errors(changed(f, add(3.0 * 1.016)))
        self.assertTrue(said(found, "built set 'ab', item 'p3', x:a"), found)

    def test_a_release_is_held_to_its_state_with_the_noise_of_both(self):
        """1.0028 is 1.5e-3 from the state's 1.0013: within the two builds' noise (2e-3),
        beyond the built set's alone."""

        def nudge(g):
            entries = g["built"][-1]["results"][A]
            entries[[k for k, _ in entries].index(at(g, "p1"))][1] = 1.0028

        f, data, full = made(release=True, state_noise={"s2": measured(1e-3)}, noise_all=measured(1e-3))
        self.assertEqual(fixes.against(changed(f, nudge), data, full), [])
        f, data, full = made(release=True, noise_all=measured(1e-3))
        self.assertTrue(said(fixes.against(changed(f, nudge), data, full), "built set 'all', item 'p1', x:a: built 1.0028"))

    def test_a_diagnostics_file_whose_states_carry_no_noise_is_refused(self):
        f, data, full = made()
        old = changed(data, lambda d: [s.pop("noise", None) for s in d["states"]])
        with self.assertRaises(ValueError) as caught:
            fixes.build("x", data=old, full=full, base="s1", fixes=[fixes.fix("a", "A", kind="mapping")], results={})
        self.assertIn(fixes.NO_STATE_NOISE, str(caught.exception))
        self.assertEqual(fixes.against(f, old, full), [fixes.NO_STATE_NOISE])


def disjoint():
    """Three fixes on three items in A, each built twice and measured at 1 %, the base at
    0.5 %: a moves p1 to 1.5, b p2 to 2.5, c p3 from 3.0 to 3.09 (2.9 %). No pair is listed."""
    data, full = chain_and_matrix(noise={"s1": measured(0.005)})
    return fixes.build(
        "Three fixes apart", data=data, full=full, base="s1",
        fixes=[fixes.fix(x, f"Fix {x}", kind="amount", noise=measured(0.01)) for x in ("a", "b", "c")],
        results={"a": {A: {"p1": 1.5}}, "b": {A: {"p2": 2.5}}, "c": {A: {"p3": 3.09}}},
        interactions=checked_pairs(),
    )  # fmt: skip


class Matrix(unittest.TestCase):
    def test_a_result_written_as_the_one_before_is_read_written_out(self):
        f, data, full = made()
        row = full["values"][[r[0] for r in full["items"]].index("p1")]
        self.assertIn(matrix.SAME, row)
        self.assertEqual(f["base"][A][at(f, "p1")], 1.0)
        self.assertEqual(fixes.against(f, data, full), [])
        written = changed(full, lambda m: m["values"][0].__setitem__(1, matrix.SAME))  # p3 in A: 3.0 is not 4.0
        self.assertTrue(said(fixes.against(f, data, written), "the base results in 'x:a' are not the matrix's"))


class Command(unittest.TestCase):
    def run_cli(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue()

    def test_check_holds_a_fixes_file_to_the_file_beside_it(self):
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
