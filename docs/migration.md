# Migration plan

How each existing view of "what changed" moves to sentier-diagnostics and is retired, in
order, and what each project keeps. Written 16 November 2026. Nothing here has started:
each move is a pull request in the project that moves, reviewed and merged by a person.

## Order, and why

1. **The trial dashboard of sentier-bafu-agribalyse.** The smallest and the newest; its
   requirements shaped the format, and it has no outside readers.
2. **The before/after page of sentier-bafu.** Public, read by others, with old files on its
   site; it moves once the trial has shown the package works from a pinned release.
3. **Laurenz Bougan's backtest copies** that are not deployed. Only after Manuel has cleared
   ownership with Laurenz: the code is in private repositories that also hold licensed data,
   and its licence names him personally.
4. **The deployed ADEME dashboard, last and together with Laurenz.** It is the one people
   use; it moves when the others have run for a while, and with its author.

No view is retired before its replacement has run beside it and the differences between
the two are explained in writing (the parity step of each move).

## How a project depends on this

A package, never a copied file. Standard library only, Python 3.10 or later.

- **By tag** in the project's lock file (sentier-bafu-agribalyse, with `uv`):
  `sentier-diagnostics @ git+https://github.com/sentier-dev/sentier-diagnostics@v0.1.0`.
- **By commit** in one pins file (sentier-bafu's `scripts/release_build/pins.toml`).
- **Tags are never moved or deleted.** A fresh clone runs `uv sync --offline` from its cache,
  so a moved tag would break it silently. A fix is a new tag.
- A site copies the page's files from `sentier_diagnostics.page.assets()` and writes the
  data with `page.as_script("SENTIER_DIAGNOSTICS", data)`, or calls `page.write`.

The first tag, `v0.1.0`, is made by a person after the first pull request is merged.

## 1. The trial dashboard (sentier-bafu-agribalyse)

**What it is.** `trial_dashboard.py` writes one HTML page with about 600 lines of
JavaScript inside Python strings; `trial.py` and `trial_categories.py` count agreement in
two ways that disagree.

**Steps.**

1. Pin `v0.1.0`. Write a function that turns a trial's results into a chain: the ADEME
   published results (state 0, `kind: "published"`), the strict BAFU build, then one
   state per accepted amendment. Step 1 of the trial's own chain (AGRIBALYSE rebuilt on
   ecoinvent) is sentier-agribalyse's build; include it where its results may be read
   locally, otherwise the chain starts at the published results and says so in `about`.
2. Its ADEME reader keeps mapping each heading to a method and unit through its explicit
   table (fail-closed) and writes the results as CSV by indicator id, or passes them to
   `chain.build`. The counts of compared, unmatched and ambiguous rows go into the state's
   `join`.
3. `trial-notes.json` becomes explanations: curated reasons `by: person`, computed counts
   `by: code`, blind readings by an agent `by: model` with who ran them. A note that looked
   and found nothing is `finding: "none found"`.
4. `trial_explain.py` writes breakdowns (`sentier-diagnostics-breakdown/1`), local only.
5. Two files per trial: a **local** one with items (`audience: "local"`, `tier: "items"`),
   and a **public** one of counts (`tier: "counts"`, `audience: "public"`), which its site
   check accepts because it names no item.
6. **Parity.** On one trial build, put the old dashboard's counts beside the new file's.
   Every difference must be one of the rule changes in SPEC section 13 (the floor per unit,
   near zero as its own class, missing counted). Write the table into the pull request.
7. Remove the dashboard's page code and the second definition of agreement. Keep the
   readers.

**Keeps.** Its ADEME reader and column table, its mapping and link quality, its notes and
their checks against the documents they cite, its site frame and its site check.

**Waits for.** Link quality bands and open cases on a breakdown part, and the placeholder
share per item (SPEC section 14, later). Until then the trial page shows them beside the
diagnostics page, not inside it.

## 2. The before/after page (sentier-bafu)

**What it is.** `sentier/before-after/1` and `/2` files, written by
`scripts/release_build/before_after_account.py`, shown by `scripts/sitebuild/beforeafter.py`,
`review.py` and `site/assets/before-after.js` on the release site.

**Steps.**

1. Pin a commit of this repository in `pins.toml`.
2. `before_after_account.py` writes `sentier-diagnostics/1` through `chain.build`: BAFU's
   release (published), then the import fixes, each patch and each contribution, each a
   state. Where a step has not been built on its own yet, the file has fewer states and the
   step's `about` says what it holds; the steps' shares are exact only for steps that were
   built. A claim derived from reach is `expect: "may"`; the claim's list stays private
   (`claim_lists=False`), as today.
3. Measure noise: keep the scores of an earlier build of the same state, or build one
   state twice in a run, and pass them as the step's noise. Until then the file says "not
   measured", as now.
4. `build_site.py` copies `page.assets()` into the site and writes `data.js` beside them.
   The page keeps its own tokens until a frame-less body exists (SPEC section 14).
5. **Parity.** For build 22, put the version 2 file and the new file side by side: the
   same pairs, with each class of version 2 mapped to its class here. List every pair that
   changes class and why (the floor per unit, `must`/`may`, missing counted).
6. **Old files.** Builds whose inputs are kept are written again with the new writer. Older
   artifacts stay readable by the old page at commit `a6a8df5`, which stays in the fork's
   history; their site entries link to that page. No converter: a version 2 file lists
   only the items that moved and does not count missing results, so a converted file would
   look complete and not be.
7. Remove `scripts/runrecord/before_after.py`, `review.py` and `example.py`,
   `scripts/sitebuild/beforeafter.py`, `review.py` and `text.py`,
   `site/assets/before-after.js`, `before-after.css` and `review.js`, and
   `docs/before-after.md` (link to this repository's SPEC instead). The tests
   `ClassTests`, `ExampleTests`, `ClaimTests`, `VersionTests`, `IndexTests`, `FrameTests` and
   `TextTests` are covered here by the acceptance cases; `RecordTests` and `PageTests` stay.

**Keeps.** `before_after_account.py` (the writer, with its refusal when its "not claimed"
count differs from the comparison's), `compare_builds.py` and its refusals, `last_run.py`,
`build_site.py`, `sitebuild/lastrun.py`, `runrecord/summary.py` and `transcript.py`,
`shared_files.py`, and its scoring. The cap on listed datasets (200) and what may be public
stay its decision.

## 3. Laurenz Bougan's backtest copies

**Before anything:** Manuel clears with Laurenz who owns the code and under what licence.
Nothing is read from those repositories into this one before that.

**Steps, per copy.**

1. His scorer stays where it is. Beside its outputs it writes two CSV tables per state
   (results by item and indicator id; items with their reference unit) and a short
   `description.json`; `sentier-diagnostics build` makes the file. Reference columns are
   then read by name (fixing A8), missing cells stay missing (A7), nothing is blanked (A4)
   or set to agreement (A5), and floors are per unit (A6).
2. `outlier_reasons.json` becomes explanations `by: model` with the model and who ran it
   (A9). The premise "the deviation is not a calculation bug" goes; a reason says what it
   rests on and what it did not check.
3. **Parity**, as above, against his table for one run.
4. Retire the copy's page. Keep the scorer and its join accounting.

**Waits for.** The comparison of characterisation factors (his `cf_comparison.csv` panel)
has no place here yet; it is a reference-side explanation (SPEC section 14). Until it does,
that panel stays on his page, linked from the diagnostics page's notes.

## 4. The deployed ADEME dashboard

Last, and with Laurenz. It sits behind a login and shows per-product results against ADEME.

1. Manuel decides whether per-product differences against ADEME may be public. Until then
   the public file is counts only; the logged-in deployment can serve a local file with
   items.
2. Run the new page beside the old one on the same run for an agreed time, with Laurenz.
3. Switch the deployment to the new page; keep the old one read-only for a while.
4. Retire it.

## What each project keeps

| Project | Keeps | Moves here |
|---|---|---|
| sentier-bafu | its scoring, `compare_builds.py`, the writer `before_after_account.py`, the run record and site frame, what may be public | counting, claims, the format, the page |
| sentier-bafu-agribalyse | its ADEME reader and column table, mapping and link quality, notes and their checks, its site check | counting, the format, the page; its reasons as explanations |
| sentier-agribalyse | the build, its reference file, its scoring, its noise fix | the chain's format and page |
| Laurenz's backtests | the scorer and its join with the reference | the page, the counting rule |

## When it is done

Every view above is retired, each project depends on a tagged release, and this
repository has a second maintainer who can cut a release without the first
([runbook](runbook.md)).
