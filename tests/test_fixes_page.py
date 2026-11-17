"""What the page draws for a set of fixes, held to the Python reader bit for bit (SPEC 16.5,
16.8). The page ports `fixes.compose` and `fixes.counts`; these cases are what the Python
gives for every set of every made-up file below, and `tests/js/page.test.js` holds the page's
port to them, value for value and noise for noise. Every value here is made up.

The fixture `fixtures/fixes_page.json` is written by

    PYTHONPATH=src python3 -m tests.test_fixes_page write
"""

from __future__ import annotations

import contextlib
import io
import itertools
import json
import re
import tempfile
import unittest
from pathlib import Path

from sentier_diagnostics import chain, cli, fixes, matrix, page

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
    pair_and_built = made(noise_a=measured(1e-3), noise_b=measured(2e-3), release=True,
                          state_noise={"s1": measured(1e-4)}, noise_ab=measured(5e-3),
                          noise_all=measured(1e-4))[0]  # fmt: skip
    found = {
        "a pair and two built sets": pair_and_built,
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


def pages() -> dict[str, dict]:
    """Made-up pages for the page's own tests (tests/js/fixes.test.js): a diagnostics file, its
    matrix and a file of fixes of it. Fixes that need others; two fixes at one item whose
    interactions were not checked and whose set was not built, so that their sum is estimated;
    and a built set that is a state of the chain."""
    found = {
        "fixes that need others": with_requires(),
        "an estimated sum": made(interactions="unchecked", built=False),
        "a built set that is a state": made(release=True),
    }
    return {name: {"data": data, "matrix": full, "fixes": f} for name, (f, data, full) in found.items()}


def subsets(f: dict) -> list[list[str]]:
    ids = [one["id"] for one in f["fixes"]]
    return [list(c) for n in range(1, len(ids) + 1) for c in itertools.combinations(ids, n)]


def fixture() -> dict:
    out = []
    for name, f in files().items():
        sets = [
            {"ids": ids, "compose": fixes.compose(f, ids), "counts": fixes.counts(f, ids)}
            for ids in subsets(f)
        ]
        out.append({"name": name, "file": f, "sets": sets})
    # through JSON: the keys of the noise each item is judged with become text, as the page reads them
    return json.loads(json.dumps({
        "about": "What fixes.compose and fixes.counts give for every set of made-up files, written by "
                 "tests/test_fixes_page.py; the page's port is held to them bit for bit.",
        "files": out,
        "pages": pages(),
    }))  # fmt: skip


class FixesPage(unittest.TestCase):
    def test_the_fixture_is_what_the_reader_gives(self):
        self.assertEqual(json.loads(FIXTURE.read_text(encoding="utf-8")), fixture())

    def test_the_cases_reach_every_label_a_sum_that_cannot_be_formed_and_a_sum_of_three(self):
        cases = [s for one in fixture()["files"] for s in one["sets"]]
        self.assertEqual({s["compose"]["label"] for s in cases}, set(fixes.LABELS))
        self.assertTrue(
            any(any(s["compose"]["cannot_add"][i] for i in s["compose"]["cannot_add"]) for s in cases)
        )
        self.assertTrue(any(s["compose"]["added"] for s in cases), "a fix chosen for what another requires")
        self.assertTrue(
            any(s["compose"]["pair_terms"]["pairs"] for s in cases), "a set that holds a listed pair"
        )

    def test_the_pages_are_whole_and_their_fixes_hang_on_them(self):
        for name, one in pages().items():
            self.assertEqual(fixes.errors(one["fixes"]), [], name)
            self.assertEqual(fixes.against(one["fixes"], one["data"], one["matrix"]), [], name)

    def test_three_differences_are_added_in_order_never_compensated(self):
        """0.0 + 0.1 + 0.2 + 0.3, added in the order of the file: 0.6000000000000001.
        `sum()` from Python 3.12 on gives 0.6: the page could not be held to a reader that
        parts from itself by version."""
        f = three_at_one_item()
        p4 = [row[0] for row in f["items"]].index("p4")
        self.assertEqual(f["base"][A][p4], 0.0)
        self.assertEqual(fixes.compose(f, ["x", "y", "z"])["results"][A][p4], 0.6000000000000001)
        self.assertEqual(fixes.label(f, ["x", "y", "z"]), fixes.EXACT)


class PageWithFixes(unittest.TestCase):
    """`page.write` puts the file of fixes beside the page as `fixes.js`, which the page loads
    after it has drawn (SPEC 16.8); `sentier-diagnostics page --fixes` does the same."""

    HEAD = (
        "(window.SENTIER_DIAGNOSTICS_FIXES_FILES = window.SENTIER_DIAGNOSTICS_FIXES_FILES || []).push("
        '{"src": document.currentScript ? document.currentScript.src : null, "fixes": '
    )

    def test_the_fixes_go_beside_the_page_and_the_page_names_them(self):
        one = pages()["fixes that need others"]
        with tempfile.TemporaryDirectory() as folder:
            where = page.write(one["data"], Path(folder), None, one["matrix"], one["fixes"])
            self.assertEqual(sorted(p.name for p in where.parent.iterdir()),
                             ["diagnostics.css", "diagnostics.js", "fixes.js", "index.html", "matrix.js",
                              "standalone.css"])  # fmt: skip
            self.assertRegex(where.read_text(encoding="utf-8"), r'data-sd-fixes="fixes\.js"')
            script = (where.parent / "fixes.js").read_text(encoding="utf-8")
            # an entry of the list, as matrix.js is: the address of the script, and the file
            self.assertTrue(script.startswith(self.HEAD), script[:200])
            self.assertEqual(json.loads(script.removeprefix(self.HEAD).removesuffix("});\n")), one["fixes"])
            page.write(one["data"], Path(folder), None, one["matrix"])  # no fixes this time: they go
            self.assertFalse((where.parent / "fixes.js").exists())
            self.assertNotIn("data-sd-fixes", where.read_text(encoding="utf-8"))

    def test_fixes_of_another_file_are_refused(self):
        one = pages()["fixes that need others"]
        # of another chain: a built set that is a state this chain does not have
        other = pages()["a built set that is a state"]["fixes"]
        with (
            tempfile.TemporaryDirectory() as folder,
            self.assertRaisesRegex(ValueError, "not a file of fixes of this file"),
        ):
            page.write(one["data"], Path(folder), None, one["matrix"], other)
        # their base is not the matrix's results in the base state
        moved = json.loads(json.dumps(one["fixes"]))
        moved["base"][A][0] += 1.0
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            page.write(one["data"], Path(folder), None, one["matrix"], moved)

    def test_the_command_writes_the_fixes_it_is_given(self):
        one = pages()["fixes that need others"]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            chain.write(one["data"], folder / one["fixes"]["of"]["file"])
            matrix.write(one["matrix"], folder / one["data"]["matrix"]["file"])
            fixes.write(one["fixes"], folder / "fixes.json")
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = cli.main(["page", str(folder / one["fixes"]["of"]["file"]), "--out", str(folder / "p"),
                                 "--fixes", str(folder / "fixes.json")])  # fmt: skip
            self.assertEqual(code, 0, said.getvalue())
            self.assertTrue((folder / "p" / "fixes.js").is_file())
            self.assertTrue(
                re.search(
                    r'data-sd-fixes="fixes\.js"', (folder / "p" / "index.html").read_text(encoding="utf-8")
                )
            )


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["write"]:
        FIXTURE.write_text(json.dumps(fixture(), indent=0, sort_keys=True) + "\n", encoding="utf-8")
