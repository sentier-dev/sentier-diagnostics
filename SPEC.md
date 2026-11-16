# sentier-diagnostics: specification

Version 1 of the format, `sentier-diagnostics/1`. Written 16 November 2026. This file says
what the tool answers, what its files hold, how it counts and what it shows. The code in
`src/sentier_diagnostics/` follows it, and every rule here has a test (see
[Acceptance cases](#11-acceptance-cases)). Where the code and this text disagree, one of
them is wrong: open an issue.

Contents: 1 Purpose · 2 Questions · 3 The chain · 4 The format · 5 The counting rule ·
6 Claims and verdicts · 7 Attribution · 8 Explanations · 9 Breakdowns · 10 Views ·
11 Acceptance cases · 12 Out of scope · 13 Decision: seed or rewrite · 14 What the
projects asked for · 15 Open questions

## 1. Purpose

One open tool, for every Sentier project, that answers: **what changed in the impact
assessment results of a database, from its published results to the current build, and
why.**

It replaces three tools that answered parts of this question and disagreed with each
other:

- the backtest dashboards by Laurenz Bougan: one React page per database, five copies that
  have drifted apart, one of them (ADEME) deployed behind a login;
- the before/after page of sentier-bafu, versions 1 and 2;
- the trial dashboard of sentier-bafu-agribalyse.

Three rules from Manuel Klarmann (16 November 2026) frame it:

1. Reproducing a database's published results is **step 0**. It is checked once, at the
   start. It is never the target of a later step.
2. The final view is **a chain of steps** from the published results to the current
   build. Each step's share of the whole difference is named, and so is what nothing
   explains. The split is exact.
3. The tool must be possible to trial, establish and maintain **without Laurenz**. The
   code is open; **no data goes into this repository**.

## 2. The questions it answers

| Question | Where the answer is |
|---|---|
| Does our computation reproduce the published results? | Step 0: its counts, and its claim "nothing moves beyond the published rounding" |
| What did each later step move? | Each step's counts by class, direction and band |
| Did each step move what it said it would, and only that? | Each step's verdicts against its claim |
| Which step carries how much of the whole difference? | Attribution: the steps' differences add up to the whole, per item |
| What does no step explain? | Steps marked `explained: false`, and the count of items they moved |
| Which items are worst, and why? | The worst-N list, the grid, the item view with its breakdown and explanations |
| What could not be judged? | Missing results (counted by side), near-zero pairs, items not attributable |

It does not say whether a result is right. Coming closer to the published results after
step 0 is counted as movement, never as better (see [A22](#11-acceptance-cases)).

## 3. The chain

A **state** is one set of results: an item's result per indicator. The first state may be
the published results (`kind: "published"`); every other state is a build (`kind: "build"`).

A **step** goes from one state to the next. Its kind is free text that the writer
chooses (`reproduction`, `fix`, `mapping`, `contribution`, `rebuild`, ...). A step has:

- a **claim** (optional): what it says it moves (section 6);
- a **tolerance**: how far two results may differ and still agree;
- a **noise** (optional): how far two builds of one state differ, measured;
- `explained`: `false` for a step that no cause explains (a rebuild on another machine,
  a change nobody can name). Its moves are counted as what nothing explains.

A plain before/after comparison is a chain of two states and one step.

**Order matters.** Where two steps touch the same results, each one's share depends on the
order they were applied in. The file keeps the order; the page says so.

**One chain per reference.** A database with two references (sentier-bafu-agribalyse has
ADEME's published results on ecoinvent and its own build on ecoinvent) gets one file per
reference. A joint view is an open question (section 15).

## 4. The format

### 4.1 Versions

A file says `"format": "sentier-diagnostics/1"`. The reader is strict: it refuses any key
it does not know and any other format, and says which format it read
(`format 'sentier-diagnostics/2': this reader knows sentier-diagnostics/1 only`). So every
change to the keys, and every change to what a class means, is a new major version. There
are no minor versions. The package version (`0.1.0`) is separate; a later package may read
several majors.

Files of `sentier/before-after/1` and `/2` (sentier-bafu) are not read. Section 13 says
why, and [docs/migration.md](docs/migration.md) says what happens to them.

### 4.2 The file

One JSON object. Numbers are finite: `NaN` and `Infinity` are refused when writing and
when reading. Results are written as computed, never rounded. All text is checked: no
control characters, bounded lengths.

| Key | What it holds |
|---|---|
| `format` | `"sentier-diagnostics/1"` |
| `tier` | `"items"`: the file lists items with their results. `"counts"`: counts only, no item anywhere (no item list, no item in a claim, no explanation of an item) |
| `audience` | `"local"` (the default) or `"public"`: whether its writer says it may be published. The tool checks only that it is one of the two; a site's own check decides what it accepts. A page of a local file says so at its top |
| `title`, `about` | Short text; `about` may be null |
| `item` | `{"one": "product", "many": "products"}`: the word for an item |
| `indicators` | `[{id, name, short, unit}]`. An indicator is matched by its exact id, never by a prefix |
| `rule` | The floors and the tolerance of the whole way (section 5) |
| `states` | `[{id, label, about, kind, identity, join}]` in order. `identity` is a short table of texts (commit, release, machine); `join` is what the reader counted when it matched its rows to items: `{compared, unmatched, ambiguous, note}`, or null |
| `steps` | `[{id, from, to, label, about, kind, explained, link, claim, tolerance, noise}]`, one fewer than the states, each from one state to the next |
| `counts` | `{steps: {step: {indicator: block}}, total: {indicator: block}}` |
| `attribution` | `{indicator: {dominant: {step: n}, not_attributable: n, unexplained_moved: n}}` (section 7) |
| `items` | The listed items, worst first (section 10.4) |
| `items_count` | `{all, qualifying, listed, not_listed}` |
| `explanations` | Section 8 |
| `notes` | Up to 20 texts |
| `made_by` | `"sentier-diagnostics 0.1.0"` |

A **block** counts one indicator in one step, or over the whole way:

```json
{"pairs": 2847,
 "classes": {"agrees": 2790, "within noise": 3, "differs": 40, "beyond 10x": 1,
             "zero reference": 2, "zero result": 0, "sign change": 1, "near zero": 6, "missing": 4},
 "missing": {"before": 1, "after": 3, "both": 0},
 "directions": {"up": 30, "down": 14},
 "bands": {"down, factor over 10": 0, "...": 0, "up, factor over 10": 1},
 "verdicts": {"as claimed": 35, "...": 0} ,
 "closer": 12, "further": 9}
```

`verdicts` is null for a step without a claim and for the whole way. `closer` and
`further` count, for a step after step 0, the moved values that came closer to or went
further from the published results. They are null for step 0 and the whole way, and no
page shows them as better or worse.

An **item** holds `id, name, place, group, unit` (its reference unit), `values` (per
indicator, one result per state, `null` where missing), and per indicator one class,
direction and band per step plus one for the whole way, the verdicts per step (or null
when no step has a claim), and `breakdowns` (`{step or "total": file name}`, or null).

### 4.3 The validator

`sentier_diagnostics.fileformat.errors(data)` returns every fault it finds, and nothing for
a file a page can show. `sentier-diagnostics check FILE ...` runs it and exits 1 on any
fault. Besides the shape, it **works every listed value out again**: class, direction and
band from the values with the file's own floor and tolerance, and the verdict from the
claim where the claim's list is in the file. It checks that counts add up (classes to
pairs, bands to what differs, up and down to what moved, missing by side to missing,
verdicts to pairs), that the items are listed worst first and that `items_count` says how
many were left out. A file that disagrees with its own rule is refused, not shown.

### 4.4 Limits

A page holds the whole file: 12 MB at most, which the writer reaches by listing fewer
items (`listed`, 200 by default). Up to 100 indicators, 30 states, 5,000 listed items,
500 explanations. The limits are in `fileformat.py`.

## 5. The counting rule

### 5.1 One class per pair

A **pair** is one item in one indicator, before and after a step. It gets exactly one
class. The classes are tried in this order; the first that holds is the class:

| Class | Holds when | Moved? |
|---|---|---|
| missing | a side has no result. Never read as zero | no |
| near zero | both sides lie within the floor | no |
| zero reference | the side before lies within the floor, the side after does not | yes |
| zero result | the side after lies within the floor, the side before does not | yes |
| sign change | both lie beyond the floor and have different signs | yes |
| agrees | they differ by no more than the tolerance, relative to the larger size | no |
| within noise | they differ by more, but by no more than the step's measured noise | no |
| beyond 10x | one size is more than ten times the other (exactly ten is not beyond) | yes |
| differs | any other difference | yes |

No class blanks a value, sets it to zero or calls it agreement. Both results are always
kept. A ratio is taken only where both sides lie beyond the floor and share a sign.

### 5.2 The floor

One floor per **indicator and reference unit**: `floor_factor` (0.01) times the median
size of the non-zero results of the first state in that group. Results per kilogram and
results per machine hour are never pooled. A writer may declare floors instead; the file
says for each floor its value, its basis (`median`, `declared`, or `none` where no result
was there to take one from) and how many results it was taken from.

Why the median and not the largest value: land use in AGRIBALYSE has a median about
4e-12 of its largest result, so a floor relative to the largest hides almost every item.
Why not a floor per value from the gross sum of its terms (sentier-agribalyse's proposal,
`max(|expected|, 1e-6 x gross)`): it needs the terms, which only a breakdown holds, and a
breakdown is often local. A project that has them can declare its floors. See section 15.

### 5.3 Tolerance and noise

The **tolerance** says when two results agree. Default 1e-5, relative to the larger size:
two runners differ by up to 2.8e-7 (measured in sentier-bafu) and two solvers by about
3e-7 (sentier-agribalyse), so differences of 1e-6 agree. Step 0 against published results takes
the rounding of what was published (`basis: "published rounding"`, e.g. 5e-4 for four
significant digits). The whole way is counted with the largest tolerance of its steps.

The **noise** is measured, never assumed: the largest relative difference between two
builds of one state, per indicator, over the items both hold. A step with measured noise
has a class "within noise" for differences no larger than it. Two words, two jobs:
tolerance (agreement by rule) and noise (measured instability). A third, the reader's
**size filter**, hides small changes on the page and changes no count (section 10.5).

One number per indicator is coarse: a few unstable items make every smaller difference
of that indicator "within noise". Large noise is a defect to fix (sentier-agribalyse's
random identifiers made water use differ by up to 21 % between two builds), not a width
to absorb. Noise per item is in section 15.

### 5.4 Direction, bands and colour

**Direction** is up where the result after is larger as a signed number, down otherwise,
and only for a pair that moved. Two results below zero that go further below zero went
**down**, although the second is larger in size.

**Bands** split a pair that differs or is beyond 10x by its direction and by the factor
between its two sizes: 1-1.1, 1.1-1.25, 1.25-2, 2-10, over 10. Ten bands, the same
distance from 1 on both sides, so that half and double look alike.

**Colour follows the direction and nothing else**: up blue, down orange (a pair readable
with the common colour-vision deficiencies). The strength of the tint follows the band. A
pair without a ratio (zero reference, zero result, sign change) is hatched. Within noise
is grey and hatched, near zero is grey, missing is red italic text.

## 6. Claims and verdicts

A step may say what it moves. A claim is text, who wrote it (section 8), and a scope:

```json
{"text": "Wheat and rice go down in climate change, by 30 % at most.",
 "by": {"kind": "person", "name": "A. Author", "model": null, "run_by": null},
 "reach": 2,
 "scope": [{"indicators": ["x:climate"], "items": ["p01", "p05"],
            "direction": "down", "largest": 0.3, "expect": "must"}]}
```

- `indicators`: `"*"` or a list of ids. `items`: `"*"`, a list, or null where the list
  stays with its writer (only its size, `reach`, is in the file).
- `direction`: `up`, `down` or `any`. `largest`: the largest change relative to the result
  before, or null.
- `expect`: `must` (each covered pair must move) or `may` (the default: it may move).
  Only a `must` entry can be unmet. A scope a program worked out (everything downstream of
  a change) says what may move.
- A claim with no entry says that nothing moves.
- A result before of zero cannot be within a relative `largest`, so such a pair is off
  claim under an entry with `largest`; an entry without `largest` judges it by direction.

Each pair of a step with a claim gets one verdict:

| Verdict | When |
|---|---|
| as claimed | it moved, and an entry covering it fits its direction and size |
| off claim | it moved, entries cover it, and none fits |
| not claimed | it moved, and no entry covers it |
| claimed, not moved | a `must` entry covers it, and it did not move |
| within noise | it differs by no more than the noise |
| unchanged | it did not move, and no `must` entry covers it |
| not judged | it is missing or near zero |

A claim's list may stay private (`claim_lists=False`): the verdicts are worked out by the
writer, kept in the file and marked on the page as not checkable from the file.

## 7. Attribution

For an item with a result in every state, the whole difference is the sum of the steps'
differences: `last − first = Σ (state k+1 − state k)`. The split is exact by construction;
it needs one build per state, which is what a chain is. Per indicator the file counts:

- `dominant`: for each step, the items that moved over the whole way whose largest
  difference in size comes from that step;
- `not_attributable`: items that moved over the whole way and have no result in some
  state between. Their difference cannot be split, and the file says how many;
- `unexplained_moved`: items that moved in a step marked `explained: false`.

The item view shows each step's share of the item's whole difference, signed, and the
share of the steps nothing explains.

A finer split inside a step (by link, by flow) is a breakdown (section 9). sentier-bafu-
agribalyse can split step 2 by link exactly because LCA is linear, but the ecoinvent unit
scores it needs are licensed, so that split stays local.

## 8. Explanations

An explanation is text about a step, an indicator, an item, or a combination, with:

- `by`, required: who wrote it. `{"kind": "person", "name": ...}`, `{"kind": "code",
  "name": ...}` (a computed reason), or `{"kind": "model", "model": ..., "run_by": ...}`
  (generated text: the model and who ran it are both required). The page labels each one
  by its origin, and a model's text reads "A claim, not checked by a person". Nothing
  generated is shown as a fact.
- `finding`: `"reason"` when it gives one, `"none found"` when someone looked and found
  none. An item with no explanation has none given. These are three different states, and
  the page keeps them apart.
- `source` (`{link, doc}`) and `not_checked` (what the writer did not check), both optional.

An explanation is a claim: it never changes a count, a class or a verdict. A file carries
no status, no "accepted by" and no approval of any kind (sentier-bafu-agribalyse ADR 0010):
the validator refuses such keys.

## 9. Breakdowns

A breakdown says what one item's result is made of, before and after one step: format
`sentier-diagnostics-breakdown/1`, one file per item and step, named in the item's
`breakdowns`. Per indicator: `total` (before, after), `parts` (label, kind, before,
after), `rest` and `parts_not_listed`.

- Parts are chosen by the **larger of their two sides**, so a part that appears only after
  the step is listed.
- What is not listed is summed into `rest`, and the count is written: never cut short
  silently. The page says what share of the total the first N parts make, on both sides.
- Parts and rest add up to the total on both sides (to 1e-9 of the size), and the totals
  are the item's results in the two states. `check` refuses a breakdown that disagrees with
  its diagnostics file, and says so when a named breakdown is not beside it. No fallback.
- Parts keep their sign; bars are drawn from the signed value.

Whether a breakdown may be published is its writer's decision. sentier-bafu publishes none;
sentier-agribalyse's sums over ecoinvent processes and may not be published.

## 10. Views

A static page: `index.html`, `diagnostics.js`, `diagnostics.css`. No build step, no
server, no network, no font or script from elsewhere. `sentier-diagnostics page FILE --out
FOLDER` writes it with the file beside it as `data.js`, so it opens from disk; served over
HTTP it can also read `?file=...`, and it opens a file a reader chooses (read in the
browser, sent nowhere). **The page works out no class, no direction and no count.** It
reads them from the file, which the validator has checked.

The text a page renders comes from the file or from words chosen to be neutral: it avoids
stage, triage, ledger, layer, upstream, provider and candidate (a test holds this).

### 10.1 Header
Title, the states in order (with their identity and join counts), the file's tier, how many
items it holds of how many worth a look, and a banner for a local file.

### 10.2 Steps and the whole way
One row per step: kind, explained or not, the claim and its origin, moved, up, down, the
verdicts, missing before and after, tolerance and noise. Then the whole way per indicator:
every class, up, down, the step that carries most of the difference, not attributable, and
moved by what nothing explains.

### 10.3 Distributions
Per indicator, the share of values in each band and class, down on the left, up on the
right. **Every indicator on the same scale**, so a tall bar means the same in each.

### 10.4 Worst
The N worst values of one comparison (a step or the whole way), ordered by class (sign
change, zero reference, zero result, beyond 10x, differs, missing), then by how far the two
sizes lie apart (`|log10(after/before)|`, or the relative difference where there is no
ratio). The page always says how many it shows of how many, and how many items worth a
look the file does not hold.

### 10.5 Grid
Items by indicator for one comparison, filtered by text, class, verdict and group, paged by
100 with "show more". The reader's **size filter** ("size at least ×1.1 ... ×10") hides
smaller changes here and in the worst list; zeros, sign changes and missing values always
show, and the page says the filter changes no count.

### 10.6 Item
Both sides in every state, the class, verdict and signed share of each step, the share
nothing explains, its explanations, and its breakdowns where they are in the file.

### 10.7 Explanations and rule
Every explanation with its origin badge; the rule with its tolerances, noise, floors and
notes.

Counts are also printed as Markdown by `sentier-diagnostics summary FILE`, for a pull
request or a reader without JavaScript.

## 11. Acceptance cases

Each defect found in the tools this replaces is a test. The pair cases are in
`tests/acceptance/cases.json`, shared by the Python rule (`tests/test_acceptance.py`) and
the page script (`tests/js/page.test.js`), so the two cannot drift apart unnoticed.

| Case | Defect or rule | Found in | Test |
|---|---|---|---|
| A1 | Two results below zero going further below were coloured as higher | before/after v1 | cases A1-*, `test_a01`, node "tone comes from the direction" |
| A2 | "Moved" was recounted by the page without its floor | before/after v1 | case A2-floor, `test_a02`, node "takes the class from the file" |
| A3 | 1e-6 solver noise was counted as a change | before/after v1 | cases A3-*, `test_a03` |
| A4 | Differences above 1000 % were blanked | backtest | cases A4-*, `test_a04` |
| A5 | Near-zero pairs were set to agreement | backtest | cases A5-*, `test_a05` |
| A6 | References of different units were pooled in one floor | backtest | `test_a06` |
| A7 | A missing cell was shown as 0.00 %; a missing value was turned into 0 and drawn as a match | backtest page and dashboard | cases A7-*, `test_a07`, node "missing side" |
| A8 | Reference columns were read by position | backtest | `test_a08` |
| A9 | Generated outlier notes were unlabelled and began from the premise that the deviation was not a calculation bug | backtest | `test_a09` |
| A10 | Zero and sign change are separate classes, never a ratio | rule | cases A10-*, `test_a10` |
| A11 | No rounding before the ratio | trial dashboard, backtest | case A11, `test_a11` |
| A12 | NaN and infinity are refused, in tables, in builds and in files | rule | `test_a12` |
| A13 | A missing indicator column is refused | rule | `test_a13` |
| A14 | A breakdown that does not match its item, or does not add up, is refused | rule | `test_a14` |
| A15 | Breakdown parts keep their sign | rule | `test_a15` |
| A16 | Nothing is cut short silently: lists and breakdowns say what they left out | trial dashboard | `test_a16` |
| A17 | A file of counts names no item | sentier-bafu-agribalyse | `test_a17` |
| A18 | The split is exact, and an item it cannot split is counted | rule | `test_a18` |
| A19 | Only `must` can be unmet; empty scope means nothing moves; zero before and `largest`; a private claim list | sentier-bafu, sentier-agribalyse | `test_a19`, `test_a19b` |
| A20 | No status or acceptance field anywhere | sentier-bafu-agribalyse ADR 0010 | `test_a20` |
| A21 | Distributions are drawn on one scale | trial dashboard | checked by hand in a browser (not automated) |
| A22 | Coming closer to the reference is never called better | ADR 0009, sentier-bafu | `test_a22` |
| A23 | An indicator is matched by its exact id, not a prefix | backtest | `test_a23` |
| A24 | Results on one side only are counted, by side | sentier-bafu | `test_a24` |
| A25 | A file is local unless its writer says otherwise | sentier-bafu, sentier-bafu-agribalyse | `test_a25` |

Also tested: the validator refuses a class, direction or verdict that contradicts the
values, items out of order, counts that do not add up, unknown keys and other formats
(`tests/test_modules.py`); the page loads nothing from elsewhere and writes no markup
from data; the committed example is what the code makes, holds every class and every
verdict, and no tracked file carries an identifier-shaped string
(`tests/test_repository.py`).

## 12. Out of scope

- **Scoring.** The tool takes results; it computes no LCA. The scorers stay with the build
  tools (Laurenz's in his backtest, sentier-bafu's in its release build).
- **Readers of a database or a reference.** Each project reads its own results and
  references, with its own fail-closed column mapping, and writes CSV tables or calls the
  Python API. `tables.py` reads only those tables, by column name.
- **Any data.** No inventory, no characterisation factor, no result of a licensed or
  embargoed database, no ecoinvent identifier, nothing from a partner. The example and the
  fixtures are made up. A test refuses identifier-shaped strings and data folders.
- **Deciding what may be published.** `audience` and `tier` are the writer's declaration;
  the tool checks their form and a site checks their meaning.
- **Approval.** No field says that something was accepted.

## 13. Decision: seed or rewrite

**The code of sentier-bafu's before/after version 2 is the seed. The format is rewritten,
under a new name.**

The seed is sound where it matters: classification in Python written into the file, a
strict reader that refuses unknown keys and non-finite numbers, the floor per indicator from
the median, symmetric bands, the direction from signed values, the claim and verdict model,
and an example that is the contract. Those were kept, adapted, and credited in `NOTICE`.

The format could not stay `sentier/before-after/2`, because what its words mean changes:

1. it compares two states, and the chain needs any number with attribution;
2. a stated claim was always "must" (about 4,900 false "claimed, not moved" values in
   sentier-agribalyse's identifier fix); `must` and `may` are now explicit;
3. missing results were dropped without a count; they are now a class, counted by side;
4. near zero, zero reference and zero result are new classes, and the floor is per unit;
5. the list `moved` also held items that did not move.

A reader of version 2 would read these files and draw wrong conclusions without an error.
A new major under the name of this repository makes that impossible. Old files stay
readable by the old page at its commit; [docs/migration.md](docs/migration.md) says how
each view moves.

The backtest dashboards are not a seed: their code is in private repositories that also
hold licensed data, and their MIT licence names Laurenz personally. Nothing was taken from
them. Their defects are described here, in words, as acceptance cases A4 to A9 and A23.

## 14. What the projects asked for

On 16 November 2026 the three sessions of sentier-bafu, sentier-agribalyse and
sentier-bafu-agribalyse wrote their requirements. What became of each:

| Asked for | By | In version 1 |
|---|---|---|
| `must` and `may` per scope entry, default `may` | bafu, agribalyse | yes |
| Counts of results on one side only | bafu | yes: `missing` by side |
| A materiality threshold apart from noise | bafu | yes, as the reader's size filter; it changes no count (section 5.3) |
| Decide `largest` where before is zero | bafu, agribalyse | decided (section 6); an absolute cap is open |
| More than one reference | bafu, agribalyse | one file per reference; a joint view is open |
| Closer and further not at the head of a later step | bafu, ADR 0009 | yes: counted, never shown as better |
| A chain of more than two states, each step's share | all three | yes |
| `listed` named and counted apart from what moved | bafu | yes: `items_count` |
| The page fetches its data as a file | bafu | yes: `data.js` beside the page, or `?file=` |
| Noise per item | bafu | no: later |
| The number of digits written | bafu | values are written unrounded; a rounded source is a tolerance basis |
| Symmetric bands, floor of 1 % of the median per indicator | bafu | yes, and per unit |
| No fixed prose such as "only the data differs" | bafu | yes: states carry their own `about` and `identity` |
| A test that the script agrees with the Python rule | bafu | yes: shared cases |
| A formatter target at the lowest Python | bafu | yes: `py310`, CI runs 3.10 to 3.14 |
| Standard library only; assets as package data with their paths | bafu, bafu-agribalyse | yes: `page.assets()` |
| A page without a frame, with a list of tokens for a site's frame | bafu, bafu-agribalyse | no: later (the page has its own tokens) |
| Reading version 1 and 2 files, or a converter | bafu | no: see section 13 and the migration plan |
| A tier a site check can refuse on | bafu, bafu-agribalyse | yes: `tier` (items or counts) and `audience` (public or local) |
| Join accounting per reference | bafu-agribalyse | yes: `join` per state |
| Reasons as data: given, none found, none given | bafu-agribalyse | yes: `finding`; "does not explain it" when a reason points the other way is later |
| Explanations labelled by origin | bafu-agribalyse, ADR 0009/0010 | yes |
| Breakdown on both sides, "the first N cover X %", tied to its run | bafu-agribalyse | yes, tied by the states it names |
| Annotations on a part (link quality band, open cases) | bafu-agribalyse | no: later |
| Placeholder share per item | bafu-agribalyse | no: later, derivable from a breakdown's part kinds |
| The comparison of characterisation factors | agribalyse | no: a reference-side explanation; later |
| Per-product table of all categories, distributions, drill-down, written reasons | agribalyse (from the backtest) | yes: grid, distributions, item view, explanations |
| Run identity on the page | agribalyse | yes: each state's `identity` |
| Indicators not hardcoded | agribalyse | yes: from the file |
| Readable without JavaScript for the counts; 375 px wide | bafu-agribalyse | 375 px: yes, no sideways scroll of the page (tables scroll inside their frame; checked in a browser). Without JavaScript: the summary is Markdown; a no-script page is later |

## 15. Open questions

For Manuel, unless he names someone else:

1. **Who is the second maintainer?** Rule 3 needs one. `MAINTAINERS.md` has the place.
2. **What may be public.** Per-item results against ADEME (the ADEME dashboard holds
   exactly these behind a login), the cap of 200 listed items in sentier-bafu, and
   breakdowns. The tool does not decide; each project's site check does.
3. **A per-value floor from the gross sum of terms** (section 5.2), for projects that have
   breakdowns. It would be a declared floor per pair, which the format cannot hold yet.
4. **Noise per item**, and an absolute cap for `largest` beside the relative one (useful
   for climate change from land use, where results are often near zero).
5. **A joint view of two references.**
6. **Laurenz's place in it.** His backtest's scorer and join accounting are the stronger
   half of what it did; the migration of the ADEME dashboard goes with him.
