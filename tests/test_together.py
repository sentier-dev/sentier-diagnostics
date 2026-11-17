"""Steps taken together: noise belongs to a state, and a step, a run or the whole way is
compared with the sum of the noise of its two ends (SPEC section 5.3),
the matrix the page judges a run of steps from (section 4.5, `"="`), and the run itself
(`together`, section 3), whose counts the page is held to.

The fixture `fixtures/together.json` is written by

    PYTHONPATH=src python3 -m tests.test_together write
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sentier_diagnostics import chain, example, fileformat, matrix, rule, together

from . import helpers
from .helpers import A, B

FIXTURE = Path(__file__).parent / "fixtures" / "together.json"
#: every run of two or more of the local example's four steps, short of the whole way
RUNS = [(0, 1), (1, 2), (2, 3), (0, 2), (1, 3)]
STEPS = ("one", "two", "three", "four")
#: `n` moves by 2% in step one, into State 1. Where State 1 is the state built twice (its
#: builds differ by 3%), the move is within noise in steps one and two, and differs over the
#: whole way, which compares State 0 and State 4 and holds no result of State 1
#: (sentier-agribalyse: noise of upstream main, an inner state, put 1,504 real differences
#: from the published results "within noise"). Where State 4 is, the whole way is within noise.
N = [1.0, 1.02, 1.02, 1.02, 1.02]
#: `p` moves once, in step two, by half.
P = [2.0, 2.0, 1.0, 1.0, 1.0]
#: `r` does not move.
R = [3.0, 3.0, 3.0, 3.0, 3.0]
#: `q` moves by 3.4% in step three, into State 3: beyond the larger noise of States 1 and 3
#: (3%), within their sum (4%), which the run of steps two and three is compared with.
Q = [1.0, 1.0, 1.0, 1.035, 1.035]
#: State 1 measured 3% in A and nothing in B; State 3 measured 1% in A. State 0 is the
#: published results: exact.
NOISE = {"s1": {A: 0.03}, "s3": {A: 0.01}}
#: three steps whose tolerances are 1e-5, 1e-2 and 1e-5: `t` moves by 5e-3 in the first, which
#: differs in that step and agrees in the run of the first two, judged with the larger of
#: their tolerances; judged with the smaller it would differ. `r` does not move.
TOLERANCES = (1e-5, 1e-2, 1e-5)
T = [1.0, 1.005, 1.005, 1.005]


def five_states(noise=NOISE, **more):
    """A chain of five states and four steps, each with a tolerance of 1%; `noise` is that of
    the built states named in it."""
    states = [
        chain.state(f"s{n}", f"State {n}", kind="published" if n == 0 else "build",
                    noise=chain.noise(("a", "b"), noise[f"s{n}"]) if f"s{n}" in noise else None)
        for n in range(5)
    ]  # fmt: skip
    steps = [chain.step(sid, f"Step {sid}", kind="fix", tolerance=chain.tolerance(0.01)) for sid in STEPS]
    values = {f"s{n}": {A: {"n": N[n], "p": P[n], "r": R[n], "q": Q[n]}, B: {"n": N[n], "p": R[n], "r": R[n], "q": R[n]}}
              for n in range(5)}  # fmt: skip
    return chain._build(
        "Five states",
        indicators=helpers.INDICATORS,
        states=states,
        steps=steps,
        values=values,
        units=dict.fromkeys("nprq", "kg"),
        **more,
    )


def mixed_tolerances():
    """A chain of four states and three steps whose tolerances differ (`TOLERANCES`), and its
    matrix."""
    states = [chain.state(f"s{n}", f"State {n}") for n in range(4)]
    steps = [chain.step(f"t{k}", f"Step t{k}", kind="fix", tolerance=chain.tolerance(t)) for k, t in enumerate(TOLERANCES)]
    values = {f"s{n}": {A: {"t": T[n], "r": 3.0}, B: {"t": T[n], "r": 3.0}} for n in range(4)}
    return chain.build_with_matrix(
        "Mixed tolerances",
        indicators=helpers.INDICATORS,
        states=states,
        steps=steps,
        values=values,
        units=dict.fromkeys("tr", "kg"),
    )


def item(data, item_id):
    return next(i for i in data["items"] if i["id"] == item_id)


class StateNoise(unittest.TestCase):
    def setUp(self):
        self.data, _ = five_states()
        self.at_the_end, _ = five_states(noise={"s4": {A: 0.03}})

    def test_a_step_takes_the_sum_of_the_noise_of_its_two_states(self):
        by = [s["noise"]["by"] for s in self.data["steps"]]
        self.assertEqual(by, [{A: 0.03}, {A: 0.03}, {A: 0.01}, {A: 0.01}])
        both, _ = five_states(noise={"s1": {A: 0.03}, "s2": {A: 0.01}})
        self.assertEqual(both["steps"][1]["noise"]["by"], {A: 0.0 + 0.03 + 0.01})
        self.assertIsNone(both["steps"][1]["noise"]["between"])

    def test_inner_states_add_nothing_to_the_whole_way(self):
        # noise measured in States 1 and 3 only: the whole way compares 0 and 4, which hold none
        self.assertEqual(self.data["rule"]["total_noise"], {})
        n = item(self.data, "n")
        self.assertEqual(n["classes"][A], [rule.WITHIN_NOISE, rule.AGREES, rule.AGREES, rule.AGREES, rule.DIFFERS])

    def test_a_move_within_the_noise_of_an_end_is_within_noise_over_the_whole_way(self):
        self.assertEqual(self.at_the_end["rule"]["total_noise"], {A: 0.03})
        n = item(self.at_the_end, "n")
        self.assertEqual(n["classes"][A], [rule.DIFFERS, rule.AGREES, rule.AGREES, rule.AGREES, rule.WITHIN_NOISE])
        self.assertEqual(self.at_the_end["counts"][fileformat.TOTAL][A]["classes"][rule.WITHIN_NOISE], 1)

    def test_the_published_results_are_exact(self):
        published = self.data["states"][0]
        self.assertNotIn("noise", published)
        self.assertEqual(fileformat.ends_known(published, self.data["states"][1], A), 2)
        self.assertEqual(fileformat.ends_known(published, self.data["states"][2], A), 1)
        with self.assertRaises(ValueError):
            chain.state("p", "Published", kind="published", noise=chain.noise(("a", "b"), {A: 0.0}))

    def test_an_indicator_no_state_measured_is_judged_without_noise(self):
        # not measured is not identical builds: the 2% in B moves, in its step and the whole way
        n = item(self.at_the_end, "n")
        self.assertEqual(n["classes"][B][0], rule.DIFFERS)
        self.assertEqual(n["classes"][B][-1], rule.DIFFERS)

    def test_no_measured_noise_at_all_leaves_everything_without_noise(self):
        data, _ = five_states(noise={})
        self.assertEqual(data["rule"]["total_noise"], {})
        self.assertTrue(all(not s["noise"]["measured"] for s in data["steps"]))
        self.assertEqual(item(data, "n")["classes"][A][0], rule.DIFFERS)
        self.assertEqual(fileformat.errors(data), [])

    def test_a_step_takes_no_noise_of_its_own(self):
        with self.assertRaises(ValueError):
            chain.step("x", "x", kind="fix", noise=chain.noise(("a", "b"), {A: 0.01}))

    def test_the_validator_holds_the_file_to_it(self):
        self.assertEqual(fileformat.errors(self.at_the_end), [])

        def wider(d):
            d["rule"]["total_noise"][A] = 0.05

        def not_measured(d):
            d["rule"]["total_noise"] = {}

        def not_a_share(d):
            d["rule"]["total_noise"] = {A: "3%"}

        def unknown(d):
            d["rule"]["total_noise"]["x:nowhere"] = 0.01

        def left_out(d):
            del d["rule"]["total_noise"]

        def a_step_wider(d):
            d["steps"][3]["noise"]["by"][A] = 0.05

        def a_step_named(d):
            d["steps"][3]["noise"]["between"] = ["a", "b"]

        def published_noise(d):
            d["states"][0]["noise"] = dict(d["states"][4]["noise"])

        def some_states(d):
            del d["states"][2]["noise"]

        def state_shape(d):
            d["states"][4]["noise"]["between"] = None

        cases = {
            "a wider noise than the ends measured": (wider, "sum of the noise of the first and last state"),
            "the noise left out": (not_measured, "sum of the noise of the first and last state"),
            "a noise that is not a share": (not_a_share, "share per indicator"),
            "an indicator the file does not have": (unknown, "share per indicator"),
            "no total noise where the states carry theirs": (left_out, "required"),
            "a step's noise not its states'": (a_step_wider, "sum of the noise of its two states"),
            "a step's noise named as if measured on it": (a_step_named, "sum of the noise of its two states"),
            "noise on the published results": (published_noise, "exact"),
            "some states with noise, some without": (some_states, "all do, or none"),
            "a state's measured noise without its builds": (state_shape, "names the two builds"),
        }
        for name, (change, words) in cases.items():
            with self.subTest(name):
                found = fileformat.errors(helpers.mutated(self.at_the_end, change))
                self.assertTrue(any(words in e for e in found), found)
                self.assertNotIn(fileformat.STOPPED, found)

    def test_the_validator_judges_the_whole_way_with_it(self):
        # mutation: a validator that judged the whole way without noise would refuse this file
        with mock.patch.object(fileformat, "total_noise_level", lambda data, indicator: None):
            found = fileformat.errors(self.at_the_end)
        self.assertTrue(any("'n'" in e and fileformat.TOTAL in e for e in found), found)

    def test_a_file_made_before_noise_belonged_to_a_state_still_reads(self):
        # its steps carry their own measured noise and its whole way none
        old = json.loads(json.dumps(self.data))
        for state in old["states"]:
            state.pop("noise", None)
        for step in old["steps"]:
            if step["noise"]["measured"]:
                step["noise"]["between"] = ["build a", "build b"]
        del old["rule"]["total_noise"]
        self.assertEqual(fileformat.errors(old), [])
        self.assertFalse(fileformat.states_carry_noise(old))
        self.assertEqual(fileformat.pair_noise(old, 1, 3), {})
        # one that took the whole way's noise from its steps, never merged, is refused
        guessed = json.loads(json.dumps(old))
        guessed["rule"]["total_noise"] = {A: 0.03}
        self.assertTrue(any("states carry none" in e for e in fileformat.errors(guessed)))


class Matrix(unittest.TestCase):
    def setUp(self):
        self.data, self.full = five_states(noise={"s1": {A: 0.03}, "s4": {A: 0.03}}, matrix_file="matrix.json")

    def test_the_matrix_agrees_with_its_file(self):
        self.assertEqual(matrix.errors(self.full), [])
        self.assertEqual(matrix.against(self.full, self.data), [])

    def test_the_matrix_judges_the_whole_way_with_the_noise_of_its_ends(self):
        with mock.patch.object(fileformat, "total_noise_level", lambda data, indicator: None):
            found = matrix.against(self.full, self.data)
        self.assertTrue(any("'n'" in e and "the whole way" in e for e in found), found)

    def test_a_result_equal_to_the_one_before_is_written_as_the_same(self):
        r = self.full["values"][[row[0] for row in self.full["items"]].index("r")]
        self.assertEqual(r, [3.0, "=", "=", "=", "=", 3.0, "=", "=", "=", "="])
        with tempfile.TemporaryDirectory() as tmp:
            path = matrix.write(self.full, Path(tmp) / "matrix.json")
            self.assertEqual(matrix.read(path, self.data), self.full)

    def test_bit_for_bit_only(self):
        self.assertEqual(matrix.compact([0.0, -0.0, 0.1 + 0.2, 0.3]), [0.0, -0.0, 0.1 + 0.2, 0.3])
        self.assertEqual(matrix.expand(matrix.compact([1.0, 1.0, None, 2.0]), 4), [1.0, 1.0, None, 2.0])

    def test_changes_are_found(self):
        n = [row[0] for row in self.full["items"]].index("n")
        cases = {
            "= first in an indicator": lambda m: m["values"][n].__setitem__(5, "="),
            "= after a missing result": lambda m: m["values"][n].__setitem__(2, None) or m["values"][n].__setitem__(3, "="),
            "a word other than =": lambda m: m["values"][n].__setitem__(2, "same"),
        }
        for name, change in cases.items():
            with self.subTest(name):
                found = matrix.errors(helpers.mutated(self.full, change))
                self.assertNotEqual(found, [], name)
                self.assertNotIn(fileformat.STOPPED, found)


def fixture() -> dict:
    data, full = example.build_local()
    return {
        "about": "Counts of every run of steps of examples/local, judged by together.counts; the page is held to them.",
        "runs": [{"first": a, "last": b, **together.counts(data, full, a, b)} for a, b in RUNS],
        "tolerances": tolerances_fixture(),
        "noise": noise_fixture(),
    }


def noise_fixture() -> dict:
    """The chain of `five_states`, file and matrix, with the counts of steps two and three as a
    run: its two ends, States 1 and 3, both measured noise, and `q` moved by 3.4% between them,
    within their sum and beyond the larger. The page is held to them."""
    data, full = five_states(matrix_file="matrix.json")
    return {
        "data": json.loads(chain.dumps(data)),
        "matrix": json.loads(matrix.dumps(full)),
        "first": 1,
        "last": 2,
        **together.counts(data, full, 1, 2),
    }


def tolerances_fixture() -> dict:
    """The chain of `mixed_tolerances`, file and matrix, with the counts of its first two steps
    as a run: the page is held to them, so a page that took the smaller tolerance fails."""
    data, full = mixed_tolerances()
    return {
        "data": json.loads(chain.dumps(data)),
        "matrix": json.loads(matrix.dumps(full)),
        "first": 0,
        "last": 1,
        **together.counts(data, full, 0, 1),
    }


class Together(unittest.TestCase):
    def setUp(self):
        self.data, self.full = example.build_local()

    def test_the_fixture_is_what_the_code_makes(self):
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8")), json.loads(json.dumps(fixture())))

    def test_one_run_is_the_states_it_runs_between(self):
        # steps 1 to 2 together are the state before step 1 against the state after step 2,
        # exactly: every item's class is the rule's on those two results
        found = together.counts(self.data, self.full, 1, 2)
        nstates = len(self.data["states"])
        ids = [i["id"] for i in self.data["indicators"]]
        floors = {(f["indicator"], f["unit"]): f["value"] for f in self.data["rule"]["floors"]}
        for at, row in enumerate(self.full["items"]):
            flat = matrix.expand(self.full["values"][at], nstates)
            for x, indicator in enumerate(ids):
                values = flat[x * nstates : (x + 1) * nstates]
                tolerance = max(s["tolerance"]["value"] for s in self.data["steps"][1:3])
                noise = fileformat.pair_noise(self.data, 1, 3).get(indicator)
                kind = rule.judge(values[1], values[3], floor=floors[(indicator, row[4])], tolerance=tolerance, noise=noise)[0]
                self.assertEqual(found["classes"][row[0]][indicator], kind)

    def test_a_run_takes_the_largest_tolerance_of_its_steps(self):
        data, full = mixed_tolerances()
        # `t` differs in the first step, by 5e-3 against its tolerance of 1e-5
        self.assertEqual(item(data, "t")["classes"][A][0], rule.DIFFERS)
        # the run of the first two steps takes 1e-2, the larger: there it agrees
        found = together.counts(data, full, 0, 1)
        self.assertEqual(found["classes"]["t"], {A: rule.AGREES, B: rule.AGREES})
        self.assertEqual(found["blocks"][A]["classes"][rule.AGREES], 2)
        # the same pair with the smaller tolerance differs: the test tells the two apart
        self.assertEqual(rule.judge(T[0], T[2], floor=0.0, tolerance=min(TOLERANCES[:2]))[0], rule.DIFFERS)

    def test_a_run_takes_no_verdict_and_the_noise_of_its_two_ends_only(self):
        found = together.counts(self.data, self.full, 2, 3)
        self.assertTrue(all(block["verdicts"] is None for block in found["blocks"].values()))
        # With fix 1 and Rebuilt are the two builds of one commit (places 2 and 3): a run that
        # ends on one of them takes its noise; steps two and three, from Recomputed to
        # Mapping 2, pass through both and take none
        water = "x:water"
        self.assertGreater(fileformat.pair_noise(self.data, 2, 4).get(water, 0), 0)
        self.assertGreater(self.data["steps"][2]["noise"]["by"][water], 0)
        self.assertEqual(fileformat.pair_noise(self.data, 1, 4), {})

    def test_a_run_whose_two_ends_measured_takes_their_sum(self):
        data, full = five_states(matrix_file="matrix.json")
        found = together.counts(data, full, 1, 2)
        self.assertEqual(fileformat.pair_noise(data, 1, 3), {A: 0.0 + 0.03 + 0.01})
        # q moved by 3.4% between them: within the sum, beyond the larger of the two alone
        self.assertEqual(found["classes"]["q"][A], rule.WITHIN_NOISE)
        self.assertEqual(rule.judge(Q[1], Q[3], floor=0.0, tolerance=0.01, noise=0.03)[0], rule.DIFFERS)
        self.assertEqual(item(data, "q")["classes"][A][2], rule.DIFFERS)

    def test_closer_and_further_only_from_the_published_results_and_without_step_0(self):
        # the local example starts from the published results: a run without step 0 counts
        # its moves closer to or further from them, one with step 0 counts none
        found = together.counts(self.data, self.full, 1, 3)["blocks"]
        for block in found.values():
            moved = sum(block["classes"][kind] for kind in rule.MOVES)
            self.assertLessEqual(block["closer"] + block["further"], moved)
        self.assertGreater(sum(b["closer"] + b["further"] for b in found.values()), 0)
        self.assertTrue(all(b["closer"] is None for b in together.counts(self.data, self.full, 0, 2)["blocks"].values()))

    def test_one_step_and_every_step_are_the_files_own(self):
        for first, last in ((1, 1), (0, 3), (2, 1), (3, 4), (-1, 1)):
            with self.subTest((first, last)), self.assertRaises(ValueError):
                together.counts(self.data, self.full, first, last)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["write"]:
        FIXTURE.write_text(json.dumps(fixture(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    else:
        unittest.main()
