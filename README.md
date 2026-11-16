# sentier-diagnostics

What changed, before and after, in the impact assessment results of a life cycle
inventory database, and why.

One open tool for the Sentier projects (sentier-bafu, sentier-bafu-agribalyse,
sentier-agribalyse and others):

- a file format, `sentier-diagnostics/1`, and a strict validator;
- one rule for counting what moved, with named classes for zeros, sign changes, near-zero
  and missing results, so that nothing is blanked, zeroed or called agreement;
- a chain of steps from the published results to the current build, each held against
  what it claimed to move, with the whole difference split exactly between the steps and
  what nothing explains named;
- a static page that shows it, with no build step, no server and no network.

The published results are checked once, at the start (step 0). Every later step is
compared with the step before it.

No data is held here: no inventory, no characterisation factor, no result of a licensed
database. Scoring and the readers of each database stay in the projects that use this.

## Try it

```bash
PYTHONPATH=src python3 -m sentier_diagnostics example --out build/example
```

Then open `build/example/page/index.html`. The example is made up.

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

Status: first version, under review. The tag `v0.1.0` does not exist yet.

Licence: MIT, see [LICENSE](LICENSE).
