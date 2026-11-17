"""Steps taken together: the whole way judged with the noise of its steps (SPEC section 5.3),
the matrix that lets the page compose any set of steps (section 4.5, `"="`), and the
composition itself (`together`, section 3), whose counts the page is held to.

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
#: sets of the local example's four steps: one run, steps apart, every step but one, and a
#: set without step 0, whose moves are counted closer to or further from the published results
SETS = [[1, 2], [0, 2], [1, 3], [0, 1, 3], [2, 3]]
STEPS = ("one", "two", "three", "four")
#: `n` moves by 2% in a step whose two builds differ by 3%: within noise in that step, and
#: over the whole way, which the other steps leave as it is (sentier-agribalyse's "codes"
#: and "open fixes": one step of noise only and one still step).
N = [1.0, 1.02, 1.02, 1.02, 1.02]
#: `p` moves once, in step two, by half.
P = [2.0, 2.0, 1.0, 1.0, 1.0]
#: `r` does not move.
R = [3.0, 3.0, 3.0, 3.0, 3.0]
#: step one measured 3% in A and nothing in B; step three measured 1% in A
NOISE = {"one": {A: 0.03}, "three": {A: 0.01}}


def five_states(noise=NOISE, **more):
    """A chain of five states and four steps, each with a tolerance of 1%."""
    states = [chain.state(f"s{n}", f"State {n}", kind="published" if n == 0 else "build") for n in range(5)]
    steps = [
        chain.step(sid, f"Step {sid}", kind="fix", tolerance=chain.tolerance(0.01),
                   noise=chain.noise(("x", "y"), noise[sid]) if sid in noise else None)
        for sid in STEPS
    ]  # fmt: skip
    values = {f"s{n}": {A: {"n": N[n], "p": P[n], "r": R[n]}, B: {"n": N[n], "p": R[n], "r": R[n]}} for n in range(5)}
    return chain._build(
        "Five states",
        indicators=helpers.INDICATORS,
        states=states,
        steps=steps,
        values=values,
        units=dict.fromkeys("npr", "kg"),
        **more,
    )


def item(data, item_id):
    return next(i for i in data["items"] if i["id"] == item_id)


class TotalNoise(unittest.TestCase):
    def setUp(self):
        self.data, _ = five_states()

    def test_the_whole_way_takes_the_largest_noise_measured_in_its_steps(self):
        self.assertEqual(self.data["rule"]["total_noise"], {A: 0.03})

    def test_a_move_within_the_noise_of_its_step_is_within_noise_over_the_whole_way(self):
        n = item(self.data, "n")
        self.assertEqual(n["classes"][A], [rule.WITHIN_NOISE, rule.AGREES, rule.AGREES, rule.AGREES, rule.WITHIN_NOISE])
        self.assertEqual(self.data["counts"][fileformat.TOTAL][A]["classes"][rule.WITHIN_NOISE], 1)

    def test_an_indicator_no_step_measured_is_judged_without_noise(self):
        # not measured is not identical builds: the 2% in B moves, in its step and the whole way
        n = item(self.data, "n")
        self.assertEqual(n["classes"][B][0], rule.DIFFERS)
        self.assertEqual(n["classes"][B][-1], rule.DIFFERS)

    def test_no_measured_noise_at_all_leaves_the_whole_way_without_noise(self):
        data, _ = five_states(noise={})
        self.assertEqual(data["rule"]["total_noise"], {})
        self.assertEqual(item(data, "n")["classes"][A][-1], rule.DIFFERS)
        self.assertEqual(fileformat.errors(data), [])

    def test_the_validator_holds_the_file_to_it(self):
        self.assertEqual(fileformat.errors(self.data), [])

        def wider(d):
            d["rule"]["total_noise"][A] = 0.05

        def not_measured(d):
            d["rule"]["total_noise"] = {}

        def not_a_share(d):
            d["rule"]["total_noise"] = {A: "3%"}

        def unknown(d):
            d["rule"]["total_noise"]["x:nowhere"] = 0.01

        cases = {
            "a wider noise than any step measured": (wider, "largest measured noise"),
            "the noise left out": (not_measured, "largest measured noise"),
            "a noise that is not a share": (not_a_share, "share per indicator"),
            "an indicator the file does not have": (unknown, "share per indicator"),
        }
        for name, (change, words) in cases.items():
            with self.subTest(name):
                found = fileformat.errors(helpers.mutated(self.data, change))
                self.assertTrue(any(words in e for e in found), found)
                self.assertNotIn(fileformat.STOPPED, found)

    def test_the_validator_judges_the_whole_way_with_it(self):
        # mutation: a validator that judged the whole way without noise would refuse this file
        with mock.patch.object(fileformat, "total_noise_level", lambda data, indicator: None):
            found = fileformat.errors(self.data)
        self.assertTrue(any("'n'" in e and fileformat.TOTAL in e for e in found), found)

    def test_a_file_made_before_the_whole_way_took_noise_still_reads(self):
        data, _ = five_states(noise={})
        del data["rule"]["total_noise"]
        self.assertEqual(fileformat.errors(data), [])
        # and one where the noise changes a class is held to the old rule: no noise
        before = json.loads(json.dumps(self.data))
        del before["rule"]["total_noise"]
        found = fileformat.errors(before)
        self.assertTrue(any("'n'" in e and fileformat.TOTAL in e for e in found), found)


class Matrix(unittest.TestCase):
    def setUp(self):
        self.data, self.full = five_states(matrix_file="matrix.json")

    def test_the_matrix_agrees_with_its_file(self):
        self.assertEqual(matrix.errors(self.full), [])
        self.assertEqual(matrix.against(self.full, self.data), [])

    def test_the_matrix_judges_the_whole_way_with_the_noise_of_its_steps(self):
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
        "about": "Counts of sets of steps of examples/local, composed by together.counts; the page is held to them.",
        "sets": [{"steps": chosen, **together.counts(data, full, chosen)} for chosen in SETS],
    }


class Together(unittest.TestCase):
    def setUp(self):
        self.data, self.full = example.build_local()

    def test_the_fixture_is_what_the_code_makes(self):
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8")), json.loads(json.dumps(fixture())))

    def test_one_run_is_the_states_it_runs_between(self):
        # steps 1 to 2 together are the state before step 1 against the state after step 2,
        # exactly: every item's class is the rule's on those two results
        found = together.counts(self.data, self.full, [1, 2])
        nstates = len(self.data["states"])
        ids = [i["id"] for i in self.data["indicators"]]
        floors = {(f["indicator"], f["unit"]): f["value"] for f in self.data["rule"]["floors"]}
        for at, row in enumerate(self.full["items"]):
            flat = matrix.expand(self.full["values"][at], nstates)
            for x, indicator in enumerate(ids):
                values = flat[x * nstates : (x + 1) * nstates]
                tolerance = max(s["tolerance"]["value"] for s in self.data["steps"][1:3])
                noise = fileformat.noise_together(self.data["steps"][1:3]).get(indicator)
                kind = rule.judge(values[1], values[3], floor=floors[(indicator, row[4])], tolerance=tolerance, noise=noise)[0]
                self.assertEqual(found["classes"][row[0]][indicator], kind)

    def test_steps_apart_add_their_differences(self):
        values = [1.0, 2.0, 2.5, 4.0]
        # steps 0 and 2: 1.0, plus 1.0 from step 0 and 1.5 from step 2
        self.assertEqual(together.pair(values, together.runs_of([0, 2])), (1.0, 3.5))
        # which is every step but step 1: the last result with step 1's difference taken off
        self.assertEqual(together.pair(values, together.runs_of([0, 2]))[1], values[-1] - (values[2] - values[1]))
        # a result the set needs that is missing makes its side missing; one it skips does not
        self.assertEqual(together.pair([1.0, 2.0, None, 4.0], together.runs_of([0, 2])), (1.0, None))
        self.assertEqual(together.pair([1.0, None, 2.5, 4.0], together.runs_of([2])), (2.5, 4.0))

    def test_a_set_takes_no_verdict_and_its_noise_is_the_largest_of_its_steps(self):
        found = together.counts(self.data, self.full, [2, 3])
        self.assertTrue(all(block["verdicts"] is None for block in found["blocks"].values()))
        # step 3 measured noise in water: a set with it takes that noise, one without has none
        water = "x:water"
        self.assertGreater(fileformat.noise_together(self.data["steps"][2:4]).get(water, 0), 0)
        self.assertNotIn(water, fileformat.noise_together(self.data["steps"][0:3]))

    def test_closer_and_further_only_from_the_published_results_and_without_step_0(self):
        # the local example starts from the published results: a set without step 0 counts
        # its moves closer to or further from them, one with step 0 counts none
        found = together.counts(self.data, self.full, [1, 3])["blocks"]
        for block in found.values():
            moved = sum(block["classes"][kind] for kind in rule.MOVES)
            self.assertLessEqual(block["closer"] + block["further"], moved)
        self.assertGreater(sum(b["closer"] + b["further"] for b in found.values()), 0)
        self.assertTrue(all(b["closer"] is None for b in together.counts(self.data, self.full, [0, 2])["blocks"].values()))

    def test_one_step_and_every_step_are_the_files_own(self):
        for chosen in ([1], [0, 1, 2, 3], [], [4]):
            with self.subTest(chosen), self.assertRaises(ValueError):
                together.counts(self.data, self.full, chosen)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["write"]:
        FIXTURE.write_text(json.dumps(fixture(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    else:
        unittest.main()
