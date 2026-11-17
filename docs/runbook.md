# Runbook

For whoever maintains this repository, with nobody else to ask. Everything below runs on a
fresh clone with Python 3.10 or later and, for the page tests, Node 20 or later. No package
is needed beyond the standard library.

## Run the tests

```bash
python3 -m unittest discover -s tests -t .
```

```bash
node --test tests/js/page.test.js
```

The first runs the unit tests, the acceptance cases and the doctests of every module. The
second runs the same acceptance cases against the page script. CI
(`.github/workflows/ci.yml`) runs both, on Python 3.10 to 3.14, and also builds the
package, installs it into a fresh environment and runs it from there.

## See the example

```bash
PYTHONPATH=src python3 -m sentier_diagnostics example --out build/example
```

Open `build/example/page/index.html` in a browser. The example is made up: ten products,
three indicators, five states, one value of every class and one of every verdict. The same
file is committed as `examples/diagnostics.json`; a test fails when the code would write
something else. After a deliberate change, write it again:

```bash
PYTHONPATH=src python3 -c "from pathlib import Path; from sentier_diagnostics import chain, breakdown, example; chain.write(example.build(), Path('examples/diagnostics.json')); breakdown.write(example.wheat_breakdown(), Path('examples/p01-fix-1.json'))"
```

and read the diff: it names the items that changed, one per line.

## Make a file from a project's results

Without Python code: one CSV table of results per state (`item` and one column per
indicator id, in any order), one table of items (`item`, `unit`, and optionally `name`,
`place`, `group`), and a description. `tests/fixtures/tables/` is a complete example.

```bash
sentier-diagnostics build description.json --out diagnostics.json
```

```bash
sentier-diagnostics check diagnostics.json
```

```bash
sentier-diagnostics page diagnostics.json --out site/diagnostics
```

```bash
sentier-diagnostics summary diagnostics.json
```

From Python, `chain.build(...)` takes the same and returns the file, checked. `check` exits 1
and prints every fault; a fault means the file disagrees with its own rule, and the page
would refuse it.

## Review a pull request

1. CI is green on every Python.
2. A change to the rule (`rule.py`, `claims.py`) comes with a case in
   `tests/acceptance/cases.json` or a test in `tests/test_acceptance.py`, and SPEC.md says
   the same as the code.
3. A change to what a file holds is a new format (below), or it is refused.
4. The page still works out nothing: `diagnostics.js` reads classes, directions, bands and
   verdicts from the file. It sets text with `textContent` only.
5. No data: no results of a real database, no identifier of a dataset or flow, nothing from
   a partner. `tests/test_repository.py` refuses identifier-shaped strings and data folders,
   but it cannot see everything; read the diff.

A person reviews and merges. Nobody merges their own pull request.

## Change the format

The reader refuses what it does not know, so every change to the keys or to what a class
means is a new major version:

1. `fileformat.FORMAT` becomes `sentier-diagnostics/2`; the page's `FORMAT` too.
2. Decide whether the package reads `/1` as well. If it does, keep the old checks in their
   own function and test both.
3. SPEC.md gets the new version's section; the old one stays, marked as such.
4. Tell the projects that use it (see [migration.md](migration.md)): each moves when it is
   ready, on its own pin.

## Make a release

After a merge to `main`, on the merge commit:

1. `__version__` in `src/sentier_diagnostics/__init__.py` is the new version.
2. Tag it `vX.Y.Z` and push the tag. **Never move or delete a tag**: projects pin them, and
   their offline installs read them from a cache.
3. Write what changed in the release notes on GitHub, and which format it writes.

## Where things are

| File | What it does |
|---|---|
| `src/sentier_diagnostics/rule.py` | The counting rule: classes, direction, bands, floors, order worst first |
| `claims.py` | Claims, scope entries, verdicts |
| `chain.py` | Builds a file from states, steps and results; attribution; writing and reading |
| `fileformat.py` | The validator |
| `breakdown.py` | Breakdowns of one item, and their check against a file |
| `tables.py`, `from_tables.py` | Reading CSV tables by column name; building from a description |
| `summary.py` | The Markdown summary |
| `page.py`, `page/` | The static page and its writer |
| `cli.py` | The command |
| `example.py` | The made-up example |
| `SPEC.md` | What all of it means |

## When something looks wrong

- **A value is in the wrong class.** Find its pair in the file, then run
  `rule.judge(before, after, floor=..., tolerance=..., noise=...)` with the floor and
  tolerance the file's `rule` and step give. If the rule is wrong, add a case first.
- **The page shows nothing.** Open the browser's console; the page says why it refused a
  file. `sentier-diagnostics check` says the same at more length.
- **Everything of an indicator is "within noise".** Its noise is one number, the largest
  difference between two builds: one unstable item widens it for all. Look at the two
  builds, not at the tolerance.
- **A breakdown is "not with this page".** It is named in the file and was not beside it
  when the page was written. Whether to publish it is its writer's decision.
