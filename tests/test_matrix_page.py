"""The full matrix of a local file, and the page as a frameless body a site holds."""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from sentier_diagnostics import chain, cli, example, fileformat, from_tables, matrix, page

from . import helpers


def local():
    return example.build_local()


class Matrix(unittest.TestCase):
    def test_the_local_example_and_its_matrix_agree(self):
        data, full = local()
        self.assertEqual(fileformat.errors(data), [])
        self.assertEqual(matrix.errors(full), [])
        self.assertEqual(matrix.against(full, data), [])
        self.assertEqual(data["matrix"], {"file": "matrix.json", "items": 10})
        self.assertEqual(len(data["items"]), 6)

    def test_the_matrix_is_ordered_as_the_listed_items_are(self):
        data, full = local()
        self.assertEqual(
            [r[0] for r in full["items"]][: len(data["items"])], [i["id"] for i in data["items"]]
        )

    def test_a_matrix_survives_its_own_text(self):
        _, full = local()
        self.assertEqual(json.loads(matrix.dumps(full)), full)

    def test_every_changed_code_is_found(self):
        def written_out(m, at):
            """A result written as a number after the first state: changing it changes a step.
            (Changing the first, where the states after it are `=`, changes every state alike.)"""
            nstates = len(m["of"]["states"])
            n = next(n for n, v in enumerate(m["values"][at]) if n % nstates and isinstance(v, float) and v)
            return n, m["values"][at][n] * 3

        data, full = local()
        cases = {
            "a class code": lambda m: m["classes"].__setitem__(0, ("=" if m["classes"][0][0] != "=" else "D") + m["classes"][0][1:]),
            "a direction": lambda m: m["classes"].__setitem__(0, m["classes"][0].swapcase()),
            "a result": lambda m: m["values"][7].__setitem__(*written_out(m, 7)),
            "a verdict": lambda m: m["verdicts"].__setitem__(
                6, "".join("o" if c == "a" else "a" if c == "o" else c for c in m["verdicts"][6])),
            "a name of a listed item": lambda m: m["items"][0].__setitem__(1, "Another name"),
            "one item fewer": lambda m: [m[k].pop() for k in ("items", "values", "classes", "verdicts")],
            "the title": lambda m: m["of"].__setitem__("title", "Another"),
        }  # fmt: skip
        for name, change in cases.items():
            with self.subTest(name):
                changed = helpers.mutated(full, change)
                self.assertNotEqual(changed, full)
                found = matrix.errors(changed) or matrix.against(changed, data)
                self.assertNotEqual(found, [], name)

    def test_counts_that_are_not_the_matrix_are_found(self):
        data, full = local()
        cases = {
            "a count": lambda d: d["counts"]["total"]["x:climate"]["classes"].__setitem__(
                "agrees", d["counts"]["total"]["x:climate"]["classes"]["agrees"] + 1),
            "the attribution": lambda d: d["attribution"]["x:climate"].__setitem__(
                "spread", d["attribution"]["x:climate"]["spread"] + 1),
            "the items worth a look": lambda d: d["items_count"].__setitem__("qualifying", d["items_count"]["qualifying"] - 1),
            "the items of the matrix": lambda d: d["matrix"].__setitem__("items", 11),
        }  # fmt: skip
        for name, change in cases.items():
            with self.subTest(name):
                self.assertNotEqual(matrix.against(full, helpers.mutated(data, change)), [], name)

    def test_shape_faults_never_raise(self):
        _, full = local()
        for bad in (None, [], {"format": "sentier-diagnostics-matrix/2"}, {**full, "extra": 1},
                    {**full, "items": [[1, 2, 3, 4, 5]]}, {**full, "classes": ["?" * 15] * 10}):  # fmt: skip
            with self.subTest(repr(bad)[:60]):
                self.assertNotEqual(matrix.errors(bad), [])

    def test_a_matrix_is_written_and_read_back_checked(self):
        data, full = local()
        with tempfile.TemporaryDirectory() as folder:
            where = matrix.write(full, Path(folder) / "matrix.json")
            self.assertEqual(matrix.read(where, data), full)
            other = helpers.mutated(data, lambda d: d.update(title="Another"))
            with self.assertRaises(ValueError):
                matrix.read(where, other)


class NamesAMatrix(unittest.TestCase):
    """The key `matrix` of a diagnostics file (SPEC 4.2)."""

    def test_only_a_local_file_of_items_names_a_matrix(self):
        data, _ = local()
        public = helpers.mutated(data, lambda d: d.update(audience="public"))
        self.assertTrue(any("only a local file" in e for e in fileformat.errors(public)))

    def test_the_matrix_holds_every_item(self):
        data, _ = local()
        wrong = helpers.mutated(data, lambda d: d["matrix"].update(items=9))
        self.assertNotEqual(fileformat.errors(wrong), [])

    def test_a_matrix_is_named_by_a_plain_file_name(self):
        data, _ = local()
        for name in ("../matrix.json", "matrix.js", "/abs.json", "a b.json"):
            with self.subTest(name):
                self.assertNotEqual(
                    fileformat.errors(helpers.mutated(data, lambda d: d["matrix"].update(file=name))), []
                )

    def test_no_matrix_is_no_key_or_null(self):
        data, _ = local()
        self.assertEqual(fileformat.errors(helpers.mutated(data, lambda d: d.update(matrix=None))), [])
        self.assertEqual(fileformat.errors(helpers.mutated(data, lambda d: d.pop("matrix"))), [])

    def test_a_public_file_is_never_built_with_a_matrix(self):
        with self.assertRaises(ValueError):
            example._made(chain.build_with_matrix, audience="public")


class Elements(HTMLParser):
    """Every start tag of a fragment, with its attributes."""

    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def tags_of(text: str) -> list[tuple[str, dict]]:
    parser = Elements()
    parser.feed(text)
    return parser.tags


class Body(unittest.TestCase):
    def test_one_root_and_no_frame_no_id(self):
        text = page.body(example.build(), breakdowns={"p01-fix-1.json": example.wheat_breakdown()})
        tags = tags_of(text)
        self.assertEqual(tags[0][0], "div")
        self.assertEqual(tags[0][1].get("class"), "sentier-diagnostics")
        self.assertIn("data-sentier-diagnostics", tags[0][1])
        self.assertEqual([t for t, a in tags if "data-sentier-diagnostics" in a], ["div"])
        self.assertFalse({"html", "head", "body", "main", "link", "style", "h1"} & {t for t, _ in tags})
        self.assertFalse([t for t, a in tags if "id" in a], "no id a host's page could hold twice")
        self.assertTrue(text.rstrip().endswith("</div>"))

    def test_the_data_inside_is_the_file_and_cannot_end_its_element(self):
        data = helpers.mutated(example.build(), lambda d: d.update(about="</script><!-- <script>x</script>"))
        text = page.body(data)
        found = re.search(r'<script type="application/json" data-sd="data">(.*?)</script>', text, re.S)
        self.assertIsNotNone(found)
        self.assertNotIn("<", found.group(1))
        self.assertTrue(found.group(1).isascii())
        self.assertEqual(json.loads(found.group(1)), data)

    def test_base_matrix_and_title_are_the_hosts(self):
        text = page.body(example.build(), base='runs/1/"x', title=False, matrix="m.json")
        root = tags_of(text)[0][1]
        self.assertEqual(root["data-sd-base"], 'runs/1/"x')
        self.assertEqual(root["data-sd-matrix"], "m.json")
        self.assertNotIn("data-sd-standalone", root)
        title = next(a for t, a in tags_of(text) if a.get("data-sd") == "title")
        self.assertIn("hidden", title)
        with self.assertRaises(ValueError):
            page.body(example.build(), matrix="../m.json")

    def test_a_wrong_file_has_no_body(self):
        with self.assertRaises(ValueError):
            page.body({"format": "sentier-diagnostics/1"})

    def test_the_page_of_its_own_holds_the_body_and_the_matrix_beside_it(self):
        data, full = local()
        with tempfile.TemporaryDirectory() as folder:
            where = page.write(data, Path(folder), None, full)
            names = sorted(p.name for p in where.parent.iterdir())
            self.assertEqual(
                names, ["diagnostics.css", "diagnostics.js", "index.html", "matrix.js", "standalone.css"]
            )
            text = where.read_text(encoding="utf-8")
            root = next(a for t, a in tags_of(text) if "data-sentier-diagnostics" in a)
            self.assertEqual(root["data-sd-matrix"], "matrix.js")
            self.assertIn("data-sd-standalone", root)
            script = (where.parent / "matrix.js").read_text(encoding="utf-8")
            head = "(window.SENTIER_DIAGNOSTICS_MATRICES = window.SENTIER_DIAGNOSTICS_MATRICES || []).push("
            self.assertTrue(script.startswith(head), script[:120])
            self.assertEqual(json.loads(script.removeprefix(head).removesuffix(");\n")), full)
            page.write(data, Path(folder))  # no matrix this time: the old one goes
            self.assertFalse((where.parent / "matrix.js").exists())

    def test_the_page_refuses_a_matrix_of_another_file(self):
        data, full = local()
        other = helpers.mutated(full, lambda m: m["values"][0].__setitem__(0, 123.0))
        with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError):
            page.write(data, Path(folder), None, other)


def rules_of(css: str) -> list[tuple[str, str]]:
    """The (selector list, at-rule context) of every rule of a style sheet; comments removed."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    found, context, depth, start = [], [], 0, 0
    for at, char in enumerate(css):
        if char == "{":
            head = css[start:at].strip()
            if head.startswith("@"):
                context.append(head)
            else:
                found.append((head, " ".join(context)))
                context.append(None)
            depth += 1
            start = at + 1
        elif char == "}":
            context.pop()
            depth -= 1
            start = at + 1
        elif char == ";":
            start = at + 1
    return found


class ScopedStyle(unittest.TestCase):
    """The style a site loads overrides none of the site's own rules (SPEC 10)."""

    def setUp(self):
        self.css = page.assets()["diagnostics.css"].read_text(encoding="utf-8")

    def test_every_selector_is_inside_the_root(self):
        rules = rules_of(self.css)
        self.assertGreater(len(rules), 50)
        for selectors, context in rules:
            for one in selectors.split(","):
                with self.subTest(one.strip()):
                    self.assertTrue(one.strip().startswith(".sentier-diagnostics"), (one, context))

    def test_no_font_no_root_no_body(self):
        bare = re.sub(r"/\*.*?\*/", "", self.css, flags=re.DOTALL)
        self.assertNotIn("font-family", bare)
        self.assertNotIn("@font-face", bare)
        self.assertNotIn("@import", bare)
        self.assertNotIn(":root", bare)
        for selectors, _ in rules_of(self.css):
            with self.subTest(selectors):
                self.assertIsNone(re.search(r"(^|[\s,>+~])(html|body)\b", selectors))

    def test_every_colour_takes_the_hosts_token_first(self):
        tokens = dict(re.findall(r"(--sd-[a-z-]+):\s*var\((--[a-z-]+)", self.css))
        for mine, theirs in (
            ("--sd-ink", "--ink"),
            ("--sd-surface", "--surface"),
            ("--sd-line", "--line"),
            ("--sd-muted", "--muted"),
        ):
            self.assertEqual(tokens.get(mine), theirs)

    def test_the_frame_of_a_page_of_its_own_is_apart(self):
        frame = page.assets(standalone=True)["standalone.css"].read_text(encoding="utf-8")
        self.assertIn(":root", frame)
        self.assertNotIn(".sentier-diagnostics", frame)


class Command(unittest.TestCase):
    def run_cli(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main([str(a) for a in args])
        return code, out.getvalue()

    def test_check_holds_a_matrix_to_its_file(self):
        data, full = local()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            chain.write(data, folder / "diagnostics.json")
            matrix.write(full, folder / "matrix.json")
            code, said = self.run_cli("check", folder / "diagnostics.json", folder / "matrix.json")
            self.assertEqual(code, 0, said)
            matrix.write(
                helpers.mutated(full, lambda m: m["values"][0].__setitem__(0, 123.0)), folder / "matrix.json"
            )
            code, said = self.run_cli("check", folder / "diagnostics.json")
            self.assertEqual(code, 1, said)
            (folder / "matrix.json").unlink()
            code, said = self.run_cli("check", folder / "diagnostics.json")
            self.assertEqual(code, 0, said)
            self.assertIn("names the matrix matrix.json, which is not beside it", said)

    def test_page_writes_the_matrix_beside_the_page(self):
        data, full = local()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            chain.write(data, folder / "diagnostics.json")
            matrix.write(full, folder / "matrix.json")
            code, said = self.run_cli("page", folder / "diagnostics.json", "--out", folder / "p")
            self.assertEqual(code, 0, said)
            self.assertTrue((folder / "p" / "matrix.js").is_file())

    def test_example_writes_the_local_example(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            code, said = self.run_cli("example", "--out", folder)
            self.assertEqual(code, 0, said)
            for name in (
                "local/diagnostics.json",
                "local/matrix.json",
                "local/page/index.html",
                "local/page/matrix.js",
            ):
                self.assertTrue((folder / name).is_file(), name)


class FromTables(unittest.TestCase):
    """A table reader names a matrix in its description (asked for by sentier-agribalyse)."""

    TABLES = Path(__file__).resolve().parent / "fixtures" / "tables"

    def described(self, folder: Path, **more) -> Path:
        for one in self.TABLES.iterdir():
            (folder / one.name).write_bytes(one.read_bytes())
        spec = json.loads((folder / "description.json").read_text(encoding="utf-8"))
        spec.update(more)
        (folder / "description.json").write_text(json.dumps(spec), encoding="utf-8")
        return folder / "description.json"

    def test_a_description_names_the_matrix_and_build_writes_it(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = self.described(folder, matrix="matrix.json", audience="local")
            data, full = from_tables.build_with_matrix(path)
            self.assertEqual(data["matrix"], {"file": "matrix.json", "items": data["items_count"]["all"]})
            self.assertEqual(matrix.against(full, data), [])
            self.assertEqual(from_tables.build(path), data)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["build", str(path), "--out", str(folder / "out" / "d.json")]), 0)
            self.assertEqual(
                matrix.read(folder / "out" / "matrix.json", chain.read(folder / "out" / "d.json")), full
            )

    def test_without_the_key_there_is_no_matrix(self):
        with tempfile.TemporaryDirectory() as folder:
            data, full = from_tables.build_with_matrix(self.described(Path(folder)))
            self.assertIsNone(full)
            self.assertNotIn("matrix", data)

    def test_a_public_file_or_a_bad_name_is_refused(self):
        for more in ({"matrix": "matrix.json", "audience": "public"}, {"matrix": "../m.json", "audience": "local"},
                     {"matrix": 3}):  # fmt: skip
            with self.subTest(more), tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):
                    from_tables.build_with_matrix(self.described(Path(folder), **more))


if __name__ == "__main__":
    unittest.main()
