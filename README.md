# sentier-diagnostics

What changed, before and after, in the impact assessment results of a life cycle
inventory database, and why.

One open tool for the Sentier projects (sentier-bafu, sentier-bafu-agribalyse,
sentier-agribalyse and others):

- a file format, `sentier-diagnostics/1`, and a strict validator;
- one rule for counting what moved, with named classes for zeros, sign changes, near-zero
  and missing results, so that nothing is blanked, zeroed or called agreement;
- a chain of steps from the published results to the current build, each held against
  what it claimed to move, with the whole difference split between the steps (exactly, up
  to the rounding the page shows) and what nothing explains named;
- a page that shows it: a frameless body a site holds in its own page, with a style
  scoped to it that takes the site's tokens, or a page of its own with no build step, no
  server and no network; a local file can carry a matrix of every item, which the page
  loads after it has drawn.

The published results are checked once, at the start (step 0). Every later step is
compared with the step before it.

No data is held here: no inventory, no characterisation factor, no result of a licensed
database. Scoring and the readers of each database stay in the projects that use this.

## Try it

```bash
PYTHONPATH=src python3 -m sentier_diagnostics example --out build/example
```

Then open `build/example/page/index.html`, or `build/example/local/page/index.html` for a
local file whose page loads the matrix of every item. The example is made up.

In a site's own page:

```python
from sentier_diagnostics import page

html = page.body(data, title=False)   # one <div class="sentier-diagnostics">, the file inside
assets = page.assets()                # diagnostics.js and diagnostics.css, to copy
```

Install it in a project, pinned to a tag:

```bash
uv add "sentier-diagnostics @ git+https://github.com/sentier-dev/sentier-diagnostics@v0.1.0"
```

Python 3.10 or later, standard library only.

## Read more

- [SPEC.md](SPEC.md): the questions, the format, the rule, the views, the acceptance cases.
- [docs/runbook.md](docs/runbook.md): tests, releases, reviews, for a maintainer alone.
- [docs/migration.md](docs/migration.md): how the existing dashboards move here and retire.
- [GLOSSARY.md](GLOSSARY.md), [MAINTAINERS.md](MAINTAINERS.md), [NOTICE](NOTICE).

Status: first release, `v0.1.0`. See its [release notes](https://github.com/sentier-dev/sentier-diagnostics/releases/tag/v0.1.0).

Licence: MIT, see [LICENSE](LICENSE).

## Inventory quality

The Python package also measures inventory and mapping quality from project-supplied
evidence. It includes weighted quality bands, baseline comparisons, draft Environmental
Footprint ratings and exchange uncertainty checks. [Inventory quality interfaces](docs/inventory-quality.md)
