"""What the page draws for a set of fixes, held to the Python reader bit for bit (SPEC 16.5,
16.8). The page ports `fixes.compose` and `fixes.counts`; these cases are what the Python
gives for every set of every made-up file below, and `tests/js/page.test.js` holds the page's
port to them, value for value and noise for noise. Every value here is made up.

The fixture `fixtures/fixes_page.json` is written by

    PYTHONPATH=src python3 -m tests.test_fixes_page write
"""

from __future__ import annotations

import itertools
import json
import unittest
from pathlib import Path

from sentier_diagnostics import chain, fixes

from .helpers import A, B
from .test_fixes import chain_and_matrix, checked_pairs, disjoint, made, measured, with_added, with_requires

FIXTURE = Path(__file__).parent / "fixtures" / "fixes_page.json"


def three_at_one_item():
    """Three fixes that each move p4 in A from 0.0, to 0.1, 0.2 and 0.3: their sum is where
    adding in order (0.6000000000000001) and `sum()` from Python 3.12 on (0.6) part in the last
    bit. And a fix with no result at p2 beside one that moves it: no sum can be formed there."""
    data, full = chain_and_matrix(noise={"s1": measured(1e-4)})
    return fixes.build(
        "Three fixes at one item", data=data, full=full, base="s1",
        fixes=[fixes.fix("x", "Fix x", kind="amount", noise=measured(1e-3)),
               fixes.fix("y", "Fix y", kind="amount", noise=measured(2e-3)),
               fixes.fix("z", "Fix z", kind="mapping", tolerance=chain.tolerance(1e-3)),
               fixes.fix("w", "Fix w", kind="mapping")],
        results={"x": {A: {"p4": 0.1, "p2": 2.5}}, "y": {A: {"p4": 0.2}, B: {"p4": 1.5}}, "z": {A: {"p4": 0.3}},
                 "w": {A: {"p2": None}}},
        interactions=checked_pairs(),
    )  # fmt: skip


def files() -> dict[str, dict]:
    """The made-up files, each checked clean."""
    found = {
        "a pair and two built sets": made(noise_a=measured(1e-3), noise_b=measured(2e-3), release=True,
                                          state_noise={"s1": measured(1e-4)}, noise_ab=measured(5e-3),
                                          noise_all=measured(1e-4))[0],  # fmt: skip
        "interactions not checked": made(interactions="unchecked")[0],
        "fixes that need others": with_requires()[0],
        "a fix that adds an item": with_added()[0],
        "three fixes apart": disjoint(),
        "three fixes at one item": three_at_one_item(),
    }
    for name, f in found.items():
        problems = fixes.errors(f)
        if problems:
            raise ValueError(f"{name}: {problems}")
    return found


def subsets(f: dict) -> list[list[str]]:
    ids = [one["id"] for one in f["fixes"]]
    return [list(c) for n in range(1, len(ids) + 1) for c in itertools.combinations(ids, n)]


def fixture() -> dict:
    out = []
    for name, f in files().items():
        sets = [{"ids": ids, "compose": fixes.compose(f, ids), "counts": fixes.counts(f, ids)} for ids in subsets(f)]
        out.append({"name": name, "file": f, "sets": sets})
    # through JSON: the keys of the noise each item is judged with become text, as the page reads them
    return json.loads(json.dumps({
        "about": "What fixes.compose and fixes.counts give for every set of made-up files, written by "
                 "tests/test_fixes_page.py; the page's port is held to them bit for bit.",
        "files": out,
    }))  # fmt: skip


class FixesPage(unittest.TestCase):
    def test_the_fixture_is_what_the_reader_gives(self):
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8")), fixture())

    def test_the_cases_reach_every_label_a_sum_that_cannot_be_formed_and_a_sum_of_three(self):
        cases = [s for one in fixture()["files"] for s in one["sets"]]
        self.assertEqual({s["compose"]["label"] for s in cases}, set(fixes.LABELS))
        self.assertTrue(any(any(s["compose"]["cannot_add"][i] for i in s["compose"]["cannot_add"]) for s in cases))
        self.assertTrue(any(s["compose"]["added"] for s in cases), "a fix chosen for what another requires")
        self.assertTrue(any(s["compose"]["pair_terms"]["pairs"] for s in cases), "a set that holds a listed pair")

    def test_three_differences_are_added_in_order_never_compensated(self):
        """0.0 + 0.1 + 0.2 + 0.3, added in the order of the file: 0.6000000000000001.
        `sum()` from Python 3.12 on gives 0.6: the page could not be held to a reader that
        parts from itself by version."""
        f = three_at_one_item()
        p4 = [row[0] for row in f["items"]].index("p4")
        self.assertEqual(f["base"][A][p4], 0.0)
        self.assertEqual(fixes.compose(f, ["x", "y", "z"])["results"][A][p4], 0.6000000000000001)
        self.assertEqual(fixes.label(f, ["x", "y", "z"]), fixes.EXACT)


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["write"]:
        FIXTURE.write_text(json.dumps(fixture(), indent=0, sort_keys=True) + "\n", encoding="utf-8")
