"""Guards over the repository itself: the committed example is what the code makes, no
fixture carries an identifier that could be a licensed dataset's, and the text a page or
a summary renders avoids the words the projects that use it do not use."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

from sentier_diagnostics import breakdown, chain, example, page, summary

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

#: A UUID, or 32 hexadecimal digits: the shape of a dataset or flow identifier.
IDENTIFIER = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b|\b[0-9a-fA-F]{32}\b")
#: Words that sentier-bafu and sentier-bafu-agribalyse keep off their pages.
AVOIDED = ("stage", "triage", "ledger", "layer", "upstream", "provider", "candidate")


def tracked() -> list[Path]:
    try:
        names = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        names = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [ROOT / n for n in names if (ROOT / n).is_file()]


class Example(unittest.TestCase):
    def test_the_committed_example_is_what_the_code_makes(self):
        self.assertEqual((EXAMPLES / "diagnostics.json").read_text(encoding="utf-8"), chain.dumps(example.build()))
        found = breakdown.errors(example.wheat_breakdown())
        self.assertEqual(found, [])
        committed = chain.read(EXAMPLES / "diagnostics.json")
        self.assertEqual(committed, example.build())

    def test_the_example_holds_every_class_and_verdict(self):
        data = example.build()
        classes = {c for i in data["items"] for row in i["classes"].values() for c in row}
        verdicts = {v for i in data["items"] for row in i["verdicts"].values() for v in row if v}
        from sentier_diagnostics import claims, rule

        self.assertEqual(classes, set(rule.CLASSES))
        self.assertEqual(verdicts, set(claims.VERDICTS))


class Data(unittest.TestCase):
    def test_no_identifier_shaped_strings(self):
        for path in tracked():
            if path.suffix not in {".json", ".csv", ".py", ".js", ".md", ".html", ".css", ".toml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            with self.subTest(str(path.relative_to(ROOT))):
                self.assertIsNone(IDENTIFIER.search(text))

    def test_no_data_folders(self):
        for path in tracked():
            parts = path.relative_to(ROOT).parts
            self.assertFalse(parts[0] in {"results", "sources", "data"}, path)
            self.assertNotIn(path.suffix, {".parquet", ".xlsx", ".zip", ".gz", ".bz2", ".db", ".sqlite"}, path)


class Words(unittest.TestCase):
    def test_rendered_text_avoids_the_words_its_users_avoid(self):
        texts = {name: p.read_text(encoding="utf-8") for name, p in page.assets().items()}
        texts["summary"] = summary.text(example.build())
        for name, text in texts.items():
            for word in AVOIDED:
                with self.subTest(name=name, word=word):
                    self.assertIsNone(re.search(rf"\b{word}s?\b", text, re.IGNORECASE))


if __name__ == "__main__":
    unittest.main()
