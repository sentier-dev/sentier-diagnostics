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
   explains. The split is exact (up to the rounding of floating point, which the page
   shows: section 7).
3. The tool must be possible to trial, establish and maintain **without Laurenz**. The
   code is open; **no data goes into this repository**.

## 2. The questions it answers

| Question | Where the answer is |
|---|---|
| Does our computation reproduce the published results? | Step 0: its counts against its tolerance, the published rounding. What moves beyond it is the residual the chain starts from (section 3) |
| What did each later step move? | Each step's counts by class, direction and band |
| Did each step move what it said it would, and only that? | Each step's verdicts against its claim |
| Which step carries how much of the whole difference? | Attribution: the steps' differences add up to the whole, per item, up to rounding |
| What does no step explain? | Steps marked `explained: false`, and the count of items they moved |
| Which items are worst, and why? | The worst-N list, the grid, the item view with its breakdown and explanations |
| What could not be judged? | Missing results (counted by side), near-zero pairs, items not attributable |

It does not say whether a result is right. Coming closer to the published results after
step 0 is counted as movement, never as better (see [A22](#11-acceptance-cases)).

## 3. The chain

A **state** is one set of results: an item's result per indicator. The first state may be
the published results (`kind: "published"`); every other state is a build (`kind: "build"`).
A state's `identity` names what makes it: commit, release, machine, and the solver, since
two solvers on one package differ by about 3e-7.

A **step** goes from one state to the next. Its kind is free text that the writer
chooses (`reproduction`, `fix`, `mapping`, `contribution`, `rebuild`, ...). A step has:

- a **claim** (optional): what it says it moves (section 6);
- a **tolerance**: how far two results may differ and still agree;
- a **noise** (optional): how far two builds of one state differ, measured;
- `explained`: `false` for a step that no cause explains (a rebuild on another machine,
  a change nobody can name). Its moves are counted as what nothing explains.

**Step 0 needs no claim.** Its tolerance (the published rounding, or a declared one) does
the judging, and what moves beyond it is the residual of the reproduction: the distance the
chain starts from, not a regression. The page and the summary say so. A claim "nothing
moves" is allowed, but it adds nothing: every value of the residual then reads "not claimed".

A plain before/after comparison is a chain of two states and one step. The first real one
will be sentier-bafu's **located factors** (a flow that names a country takes that
country's factor), with the claim "water use and land use may move; nothing else moves":
one scope entry, water use and land use, every item, `may`. Any other indicator that moves
is "not claimed". The claim was first written for water use alone; sentier-bafu's first
run of this tool on its own results (16 November 2026) showed land use moving too, for 5
datasets, read as "not claimed". The tool found what the claim left out, which is its job.
sentier-bafu then took the list from its build, not by hand: its install report names the
methods that actually take a country's own factor (`coverage.located_by_method`), and on
BAFU:2026 v1 those are water use and land use. Its file builds the scope from that list,
so the claim stays right when the factors change. `tests/fixtures/located-factors/` is
that step, made up, and a test holds what it shows.

**Order matters.** Where two steps touch the same results, each one's share depends on the
order they were applied in. The file keeps the order; the page says so.

**Ranges: several steps together.** A reviewer of a chain of fixes asks what some of them
did together, not only what each did. A **range** is a run of at least two consecutive
steps, short of every step (that is the whole way): it compares the state before its first
step with the state after its last, and is judged as the whole way is (section 5.3): the
largest tolerance of its steps, no noise, and no verdict, since each claim is judged in its
own step. Its classes are worked out by the rule from those two states, never added up
from its steps: steps that each move 0.8 % under a tolerance of 1 % agree one by one, and
two of them together differ.

**Decision: a run, not any set.** Each state is built on the one before it, so the only
comparisons a chain holds are between two of its states, and a set of steps with a gap,
such as the first and the third fix, was never built on its own. A page that is asked for
steps apart takes in the steps between them and says so; it never sums steps it cannot
see, and it never claims what a combination nobody built would give. Building every
combination is the producer's business: 11 fixes have 2,047 of them.

**The producer chooses its ranges** (`ranges` of `chain.build`): `"all"`, a list of
`(first step, last step)` pairs (`chain.ranges_within` gives every run between two steps,
such as the fixes of a build), or none. Without a choice, a chain of at most 8 steps has
every range and a longer one none (`chain.AUTO_RANGES`): n steps have n(n-1)/2 - 1 ranges,
and each is a comparison of every item in every indicator. A description of CSV tables
says the same in its `ranges` key.

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
| `indicator` | Optional. `{"one": "impact category", "many": "impact categories"}`: the word for an indicator, which the page and the summary use; null or absent for "indicator" |
| `indicators` | `[{id, name, short, unit}]`. An indicator is matched by its exact id, never by a prefix |
| `rule` | The floors and the tolerance of the whole way (section 5) |
| `states` | `[{id, label, about, kind, identity, join}]` in order. `identity` is a short table of texts (commit, release, machine); `join` is what the reader counted when it matched its rows to items: `{compared, unmatched, ambiguous, note}`, or null |
| `steps` | `[{id, from, to, label, about, kind, explained, link, claim, tolerance, noise}]`, one fewer than the states, each from one state to the next |
| `ranges` | Optional. `[{id, steps, from, to, tolerance}]`: the runs of consecutive steps compared as one (section 3). `id` is `first..last`, `from` the state before the first step, `to` the state after the last, `tolerance` the largest of its steps. Absent where the file has none |
| `counts` | `{steps: {step: {indicator: block}}, total: {indicator: block}}`, and `ranges: {range: {indicator: block}}` where, and only where, the file has ranges |
| `attribution` | `{indicator: {dominant: {step: n}, not_attributable: n, spread: n, unexplained_moved: n}}` (section 7) |
| `items` | The listed items, worst first (section 10.4) |
| `items_count` | `{all, qualifying, listed, not_listed}` |
| `explanations` | Section 8 |
| `notes` | Up to 20 texts |
| `made_by` | `"sentier-diagnostics 0.1.0"` |
| `matrix` | Optional. `{"file": name, "items": n}`: the full matrix of every item, a second file beside this one (section 4.5); null or absent for none. Only a local file of items names one, and `items` is `items_count.all` |

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

`verdicts` is null for a step without a claim, for the whole way and for a range. `closer` and
`further` count, for a step after step 0, the moved values that came closer to or went
further from the published results. They are null for step 0, the whole way and a range, null for
every step of a chain whose first state is not the published results (there is nothing to
come closer to), and no page shows them as better or worse.

An **item** holds `id, name, place, group, unit` (its reference unit), `values` (per
indicator, one result per state, `null` where missing), and per indicator one class,
direction and band per step, then one for the whole way, then one per range in the order of
`ranges`; the verdicts per step (or null
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

It also **works the counts out again from the listed items.** Only a pair worth a look
adds to the classes that moved, to missing (by side), to directions, bands, the verdicts
"as claimed", "off claim", "not claimed" and "claimed, not moved", to `closer` and
`further`, and to the attribution; and every item with such a pair, in a step, the whole
way or a range, is worth a look. So
where nothing worth a look is left out (`not_listed` 0), these counts must equal what the
listed items hold, and where some are left out, no count may be smaller than what the
listed items hold. What only quiet pairs add to (agrees, within noise, near zero, and the
verdicts of those) is held by the sums alone: a file that invents agreeing items it does
not list cannot be caught from the file. Further: a claim whose lists are all in the file
has the size of their union as its `reach`, `"*"` entries aside; the floors come from the first state,
and a floor's basis agrees with its count (`median` from results, `none` is 0 from none,
`declared` from none); `closer` and `further` are counted for a step after step 0 from
published results and are null everywhere else.

### 4.4 Limits

A page holds the whole file: 12 MB at most, which the writer reaches by listing fewer
items (`listed`, 200 by default). Up to 100 indicators, 30 states, 5,000 listed items,
500 explanations and 20 notes; a claim has up to 50 scope entries, and an entry may list as
many items as a file may (5,000); a state's identity has up to 12 entries. Ids are up to
100 characters, labels 80, texts 600 and an explanation's text 2,000. The limits are in
`fileformat.py`, and a refusal names the limit it met.

### 4.5 The matrix of every item

A file lists the items worth a look, up to `listed`. A project looking at its own build
wants every item: `chain.build_with_matrix` writes them in a second file of format
`sentier-diagnostics-matrix/1`, which the page loads after it has drawn. Only a local file
of items has one; a public file keeps its listed items only. A reader that writes CSV tables
names it in its description (`"matrix": "matrix.json"`), and `sentier-diagnostics build`
writes it beside the file.

```json
{"format": "sentier-diagnostics-matrix/1",
 "of": {"title": "...", "states": ["a", "b", "c"], "indicators": ["x:climate", "x:water"], "steps": ["s0", "s1"],
        "ranges": []},
 "items":    [["p01", "Wheat", "FR", "crops", "kg"], ...],
 "values":   [[0.52, 0.53, 0.47, 1.2, "=", null], ...],
 "classes":  ["=Dd===", ...],
 "verdicts": ["a.==", ...]}
```

One row per item, in the order of the listed items (worst first): `[id, name, place,
group, unit]`; the results per indicator and state, indicator after indicator, a result
that is the same number as the state before it (bit for bit) written `"="`; per indicator
one code per step, one for the whole way and one per range of `of.ranges`; and, where a step has a claim, per
indicator one verdict code per step (`.` for a step without a claim; `verdicts` is null when
no step has one). The class codes are `=` agrees, `~` within noise, `0` near zero, `-`
missing, and for a pair that moved its class in upper case up and lower case down: `D`
differs, `B` beyond 10x, `R` zero reference, `T` zero result, `S` sign change. The verdict
codes are `a` as claimed, `o` off claim, `n` not claimed, `c` claimed, not moved, `~` within
noise, `=` unchanged, `?` not judged. A matrix holds no band: it follows from the results.

`matrix.errors(m)` checks the shape and never raises. `matrix.against(m, data)` works every
code out again with the file's floors, tolerances and noise (and every verdict where the
claim's lists are in the file), and holds the file to it: with every item at hand, its
counts, attribution, `items_count.all` and `qualifying` must be what the matrix holds,
exactly, and every listed item must be in the matrix with the same name and results.
`sentier-diagnostics check` does both when the matrix lies beside its file. A matrix holds
up to 200,000 items and 64 MB.

The `"="` keeps a chain of fixes small: most fixes leave most results as they were, and
sentier-bafu's chain of 16 states over 11,947 datasets and 25 impact categories would
otherwise hold every number 16 times. It is a writing of the results, not a finding: a
reader writes each `=` out as the number before it, and `"="` that stands first in an
indicator or after a missing result is refused.

## 5. The counting rule

### 5.1 One class per pair

A **pair** is one item in one indicator, before and after a step. It gets exactly one
class. The classes are tried in this order; the first that holds is the class:

| Class | Holds when | Moved? |
|---|---|---|
| missing | a side has no result. Never read as zero | no |
| near zero | both sides lie within the floor | no |
| agrees | they share a sign and differ by no more than the tolerance, relative to the larger size | no |
| within noise | they share a sign and differ by more, but by no more than the step's measured noise | no |
| zero reference | the side before lies within the floor, the side after does not | yes |
| zero result | the side after lies within the floor, the side before does not | yes |
| sign change | both lie beyond the floor and have different signs | yes |
| beyond 10x | one size is more than ten times the other (exactly ten is not beyond) | yes |
| differs | any other difference | yes |

Agreement is tried before the floor's own classes, so a pair that lies on both sides of the
floor and agrees (0.010000001 and 0.009999999 at a floor of 0.01) agrees: crossing the floor
by solver noise is not a change (A26). A pair beyond the floor on both sides is classed as
before; only a pair that crosses the floor by no more than the tolerance or the noise is
affected.

No class blanks a value, sets it to zero or calls it agreement. Both results are always
kept. A ratio is taken only where both sides lie beyond the floor and share a sign. How far
two sizes lie apart is the |log10| of their factor; where the factor is too large or too
small for a float (1e-300 and 1e300), the difference of their logarithms, in Python and on
the page alike (A27).

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
significant digits). The whole way is counted with the largest tolerance of its steps,
and no noise: noise is measured between two builds of one state, and the whole way is not
one step. A range is counted the same way, with the largest tolerance of its own steps.

The **noise** is measured, never assumed: the largest relative difference between two
builds of one state, per indicator, over the items whose results lie beyond the floor in
both builds (the floors of the chain's first state). A pair within the floor is left out:
a residue of 4e-16 in one build and 0 in the other would otherwise make the noise 1.0 and
put every move below a factor of 2 "within noise" (found by sentier-bafu: it hid a
correction by a factor of 580). An indicator with no such pair has no noise in the file,
and the page and the summary say "not measured" for it, never "identical". A noise above
1 % (`chain.LARGE_NOISE`) is called large on the page and in the summary, which give its
size. A step with measured noise has a class "within noise" for differences no larger than
it. Two words, two jobs:
tolerance (agreement by rule) and noise (measured instability). A third, the reader's
**size filter**, hides small changes on the page and changes no count (section 10.5).

One number per indicator is coarse: a few unstable items make every smaller difference
of that indicator "within noise". Two builds that are identical are a finding, shown as
"identical", and never as "not measured". Large noise is a defect to fix (sentier-agribalyse's
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
  stays with its writer. Every listed id is an item of the chain: `chain.build` refuses a
  claim that names an item no state holds (a typo would otherwise be a claim about nothing).
- `reach`: how many items the claim's lists name together, `"*"` entries aside. Where every
  list is in the file the validator checks it; where a list stays private it is the only
  trace of that list. It is null where no entry lists items.
- `direction`: `up`, `down` or `any`. `largest`: the largest change relative to the result
  before, or null.
- `expect`: `must` (each covered pair must move) or `may` (the default: it may move).
  Only a `must` entry can be unmet. A scope a program worked out (everything downstream of
  a change) says what may move.
- A claim with no entry says that nothing moves.
- A pair whose result before lies within the floor (a zero reference) has no size for a
  relative `largest` to be relative to: it is off claim under an entry with `largest`, and
  an entry without `largest` judges it by direction alone.

Each pair of a step with a claim gets one verdict. They are tried in this order; the first
that holds is the verdict:

| Verdict | When |
|---|---|
| not judged | it is missing: nothing can be said of it |
| claimed, not moved | a `must` entry covers it, and it agrees, is within noise or is near zero: it did not move beyond the tolerance, the noise or the floor |
| unchanged | it agrees |
| within noise | it differs by no more than the noise |
| not judged | it is near zero |
| not claimed | it moved, and no entry covers it |
| as claimed | it moved, and an entry it is held to fits its direction and size |
| off claim | it moved, and no entry it is held to fits |

A pair that moved is held to the `must` entries that cover it, and only where none does to
the `may` entries. So a `may any` entry beside a `must down` entry cannot make a move up
"as claimed": the `must` entry says which way the pair must go.

A claim's list may stay private (`claim_lists=False`): the verdicts are worked out by the
writer, kept in the file and marked on the page as not checkable from the file.

## 7. Attribution

For an item with a result in every state, the whole difference is the sum of the steps'
differences: `last − first = Σ (state k+1 − state k)`. The split is exact by construction,
up to the rounding of floating point; it needs one build per state, which is what a chain
is. Per indicator the file counts, among the items that moved over the whole way:

- `dominant`: for each step, the items whose largest difference comes from that step,
  among the steps in which the item moved. A step in which it agrees, is within noise or
  is near zero carries none of it, however large its difference. Where two steps move it
  by the same amount, the earlier one carries it;
- `spread`: items that moved over the whole way while no single step moved them: each
  step stayed within its tolerance, its noise or the floor, and only together do they
  move it. No step carries such an item;
- `not_attributable`: items that have no result in some state between. Their difference
  cannot be split, and the file says how many;
- `unexplained_moved`: items that moved in a step marked `explained: false`, counted
  whether or not they moved over the whole way.

So `dominant` over the steps, `spread` and `not_attributable` add up to the items that
moved over the whole way.

The item view shows each step's share of the item's whole difference, signed, the share of
the steps nothing explains, and the **sum of the shares it shows**: in floating point that
sum may differ from 100 % in its last digits, and the page prints what it computed instead
of a fixed 100 %. Where the steps' differences, taken by size, add up to more than ten
times the whole difference, the steps **cancel**: their shares would be large, of both
signs, and partly rounding. The page then prints no shares and says how many times the
whole difference the steps add up to. It also says why it prints none for an item that
did not move, that is missing in a state between, or that is missing at either end.

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
the validator refuses such keys, and refuses an entry of a state's `identity` whose name
says status, accepted or approved, since an identity holds free names.

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
  are the item's results in the two states.
- A breakdown is of the item that names it and of the step (or the whole way) it is named
  for. `check` refuses one named by another item or for another step, saying which item
  and step named it and which it is of; the page does not draw it under the item that
  named it.
- `check` refuses a breakdown that disagrees with its diagnostics file, and says so when a
  named breakdown is not beside it. No fallback.
- Parts keep their sign; bars are drawn from the signed value.

Whether a breakdown may be published is its writer's decision. sentier-bafu publishes none;
sentier-agribalyse's sums over ecoinvent processes and may not be published.

## 10. Views

**One body for a site and for a page of its own.** `page.body(data)` is the diagnostics as
one element, `<div class="sentier-diagnostics" data-sentier-diagnostics>`, with the file
(and its breakdowns) inside it as JSON: no `<html>`, `<head>` or `<body>`, and no id, so a
site may hold it anywhere, even twice. The site loads `diagnostics.js` and
`diagnostics.css` from `page.assets()`; the script mounts into every such element (a site
that draws it later marks it `="manual"` and calls `SentierDiagnostics.mount(element,
{data})`). `data-sd-base` names where the files it loads lie, and `title=False` leaves the
heading to the site. The script sets the document's title only on a page of its own.

**The style is scoped.** Every rule of `diagnostics.css` is under `.sentier-diagnostics`;
it sets no font, nothing on `:root`, `html` or `body`, and resets inside its root what a
site does to bare tables (borders, phone layouts that turn rows into blocks). Its colours
are `--sd-*` properties that take the site's tokens where the site sets them
(`--sd-ink: var(--ink, #1d232a)`, and so on for `--muted`, `--surface`, `--paper-deep`,
`--line`, `--line-strong`, `--index`, `--fail`, `--radius`, `--t-*`, `--s*`); up, down and
noise keep colours of their own (amber up, teal down), so that a direction never takes a
site's accent. A test reads the sheet and holds this.

**A host lets the body be wide.** The matrix needs the page's width, and a site that caps
the children of an article at a reading measure (`.prose > * { max-width: 44rem }`) caps
the body with them, which leaves a 25-indicator grid a few columns wide. A host lifts that
cap for the body, as sentier-bafu does:
`.prose > .sentier-diagnostics { max-width: none }` (and the same for any wrapper of the
page that holds a measure).

`sentier-diagnostics page FILE --out FOLDER` writes a page of its own: `index.html` with
the body in it, the two assets, and `standalone.css`, which sets the tokens and font a site
would. It opens from disk; no build step, no server, no network, no font or script from
elsewhere. Where the file names a matrix that lies beside it, the page writes it as
`matrix.js`, which loads from disk too; a site serving `matrix.json` needs nothing else, as
the page fetches it over HTTP. Served over HTTP the page can also read `?file=...`, and it
opens a file a reader chooses (read in the browser, sent nowhere). **The page works out no
class, no direction and no count of its own.** It reads them from the file, which the
validator has checked, and only adds the file's counts up: the classes that moved into
"moved", and a step's counts over its indicators. The one number it works out itself is
the median and percentiles of a distribution (10.3), and only from every item. A file read by `?file=` or chosen by a
reader has not passed through the validator: the page checks its shape only, says so above
everything it draws, and refuses a file it cannot draw instead of drawing part of it. A
matrix is held to the file it says it is of (title, states, indicators, steps, number of
items, the length of every row) before a row of it is drawn; its codes are checked by
`sentier-diagnostics check`, not again in the browser. Whatever the file says, only an
`https://` address becomes a link.

The text a page renders comes from the file or from words chosen to be neutral: it avoids
stage, triage, ledger, layer, upstream, provider and candidate (a test holds this).

**The page is a matrix page.** From the top: the header (10.1); a row of chips that
chooses the comparison, the whole way first and then each step with its number, the values
that moved in it, a `!` where nothing explains it and a mark for each verdict worth a look
(the arrow keys move between them); under the chips one line for the chosen step: the
states it goes between, what it is, its claim with who made it, what the claim found, its
tolerance and its noise; one row of controls (name, group, class, verdict, the size
filter) with the count and the legend in the row under it; then the matrix (10.5), which
opens an item in a drawer (10.6); directly under it, always open, the distributions of the
chosen comparison (10.3). The address keeps the chosen step and an open item
(`#step=<id>&item=<id>`), so that a reviewer can send someone to exactly that view. Below
them, each closed until a reader opens it: the steps and the whole way (10.2), the worst
values (10.4), the explanations and the rule (10.7). A host's page never offers to open a
file; it says only why nothing is drawn.

**Several steps together.** Where the file has ranges, a reader chooses several steps:
Shift-click a second step (or Shift and an arrow key) for the steps from one to the other,
⌘- or Ctrl-click to add a step or take one off at an end, or turn on "Several steps" so
that a plain click does that (for a touch screen). The chips of the run are pressed, and a
step taken in only because it lies between two chosen ones is hatched. The matrix, the
distributions, the worst values and the drawer then show the range: the file's own counts
and classes of it, never a sum of its steps. Its line says which states it goes between,
which steps lie between the chosen ones and why they are taken in, and each step's claim
with what it found in that step alone; it says that a range has no noise and no verdict.
Every step chosen is the whole way. A run the file does not compare is said, with the runs
it does, and nothing changes; a step inside a run cannot be taken off, and the page says
so. The address keeps a range by its id (`#step=first..last`); an address that names a run
the file does not compare, or no comparison at all, opens on the whole way and says why.

The line of the chosen step names every verdict on a move with its count, "as claimed"
first ("40 values moved as claimed, 2 off claim ◐"), and "Nothing moved, as claimed" only
where every count is zero. It gives them weight, not colour: a verdict is not an approval
(ADR 0010, A20).

### 10.1 Header
The title, the file's `about`, and one quiet line: how many items and indicators, how many
it holds of how many worth a look, and, for a local file, that its writer has not said it
may be published (a quiet part of the line, as a site's own notice, not a box). The states
in order, with their identity and join counts, head the steps (10.2).

### 10.2 Steps and the whole way
Steps are numbered from 0 where the first state is `published`: step 0 is then the
reproduction (rule 1 of section 1). A chain that starts from a build of its own has no
reproduction, and its steps are numbered from 1.

One row per step: kind, explained or not, the claim and its origin, moved, up, down, the
verdicts, missing before and after, tolerance and noise. Then the whole way per indicator:
every class, up, down, the step that carries most of the difference (section 7), spread
over steps, not attributable, and moved by what nothing explains.

### 10.3 Distributions
One card per indicator, in the order of the matrix's columns (10.5), for the comparison the
chips have chosen: a histogram of the file's own counts, from left to right a sign change,
the bands down from far to near, agrees and within noise (two bars, the band around 1),
the bands up from near to far, then zero reference, zero result, near zero and missing.
Every count is in its bar's title.

**Bar heights: each card to its own tallest bar by default**, with one scale for every card
(the share of all values) as a switch beside the legend. A step that moves a few values
of thousands moves them in most indicators by less than a pixel on one scale, and the
reviewer looks for exactly those; so each card says what its full height is ("tallest bar:
7", or on one scale "full height: 300 of 11 947"), and a bar of one value is never drawn as
large as a bar of thousands without that number beside it. An indicator in which nothing
moved and nothing is missing is quietened, as its column is.

Under each card, how many moved and are missing, and **the median, 10th and 90th
percentile of after ÷ before: the one statistic the page works out itself.** It is taken
only where the page holds every item (the matrix is loaded, or the file lists them all),
over the values with a ratio (both results neither zero nor missing, of one sign), and says
over how many ("Median of 11 893 ratios", and how many have none). From the listed items
alone it gives none and says why: they are the furthest apart, and their median would say
more than the whole holds. Each percentile has as few digits as keep it apart from a
neighbour that differs (three at least, six at most); where six still read the same it
says "just under the median" or "just over the median" instead of two equal numbers.

A card's title sorts the matrix by its indicator; a heading of the matrix marks its card.

### 10.4 Worst
The N worst values of one comparison (a step or the whole way), ordered by class (sign
change, zero reference, zero result, beyond 10x, differs, missing), then by how far the two
sizes lie apart (`|log10(after/before)|`, or the relative difference where there is no
ratio). The page always says how many it shows of how many, and how many items worth a
look the file does not hold.

### 10.5 Matrix
Items by indicator for the comparison the chips have chosen. **The indicators in which that
comparison moved most come first**, so that what a step did is in view without scrolling;
an indicator in which it moved nothing and nothing is missing comes last, quietened, and
keeps its column (a missing value counts with what moved: it is a finding, not stillness).
Choosing another comparison sorts the grid furthest-first again, since a new comparison
has a new order. In it: each cell with a ratio shows the result after
divided by the result before in three significant digits (`1.00`, `0.984`, `2.27`,
`1.01e−3`), agreeing pairs included, so that a column reads as numbers; a cell without one
says what the class says (from 0, to 0, + → −, missing, ≈ 0). The class shows as the tint
and a mark, never in place of the number: an agreeing cell has no tint, one within noise
is marked `~`, one beyond 10x `»`. A `1.00` with a tint is a pair that moved by less than
the rounding shows; its title holds both results exactly. The cell's colour is its
direction's and its strength the band's; for a matrix row, which holds no band, the
band is named from the results as the rule names it (a test holds the two equal). The ratio
and the shading are a display: they change no class. The listed items, or every item once
the matrix is loaded, a dot marking the listed ones; the page says which it holds and why
(none named, loading, loaded, or the reason it was not loaded). **The grid opens with the
items furthest apart**: by the largest factor between the two results over every
indicator, among the values that moved and have a ratio; then the items whose moves have
none (from or to zero, a sign change), by their worst value in the order of 10.4; then
those that did not move. A heading sorts by how far the two lie apart in that indicator,
the furthest first (the order of 10.4), or by name, and a second click goes back;
filters by text, group, class and verdict; 300 rows at a time with "show more". The
reader's **size filter** ("size at least ×1.1 ... ×10") hides smaller changes here and in
the worst list; zeros, sign changes and missing values always show, and the page says the
filter changes no count.

### 10.6 Item
A drawer at the right (the whole window on a phone), opened from a row of the matrix or the
worst list, closed with Close or Escape. First **why it differs**: the explanations about
the item, then those about a step or an indicator in which it moved (said to be so, as they
may not be about it), or "none given" when the file holds neither; the file holds every
explanation, so this "none" is never said over a part of a list. Then per indicator, the
one whose whole way lies furthest apart first: both sides in every state, the class,
verdict and signed share of each step, the share nothing explains and the sum of the shares
(or why there are none: section 7). Then its breakdowns where they are in the file and fit
the item and step.

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
| A9 | Generated outlier notes were unlabelled and began from the premise that the deviation was not a calculation bug | backtest | `test_a09`, node "a text by a model is drawn as a claim" |
| A10 | Zero and sign change are separate classes, never a ratio | rule | cases A10-*, `test_a10` |
| A11 | No rounding before the ratio | trial dashboard, backtest | case A11, `test_a11` |
| A12 | NaN and infinity are refused, in tables, in builds and in files | rule | `test_a12` |
| A13 | A missing indicator column is refused | rule | `test_a13` |
| A14 | A breakdown that does not match its item, or does not add up, is refused | rule | `test_a14` |
| A15 | Breakdown parts keep their sign | rule | `test_a15` |
| A16 | Nothing is cut short silently: lists and breakdowns say what they left out | trial dashboard | `test_a16` |
| A17 | A file of counts names no item | sentier-bafu-agribalyse | `test_a17` |
| A18 | The split is exact up to rounding, the page prints the sum it computed, and an item it cannot split is counted | rule, review of PR 2 | `test_a18`, node "A18" |
| A19 | Only `must` can be unmet, and it is unmet by a pair that stayed within the tolerance, the noise or the floor; empty scope means nothing moves; a zero reference is never within `largest`; a private claim list | sentier-bafu, sentier-agribalyse, review of PR 2 | `test_a19`, `test_a19b`, `Verdicts` |
| A20 | No status or acceptance field anywhere | sentier-bafu-agribalyse ADR 0010 | `test_a20` |
| A21 | Distributions: each card says what its full height is; one scale for every card is a switch; percentiles only from every item, over the values with a ratio, with their number | trial dashboard, review of PR 21 | node "one scale", "a median of after ÷ before only from every item", "over how many ratios", "just under or over the median" |
| A22 | Coming closer to the reference is never called better | ADR 0009, sentier-bafu | `test_a22`, node "nothing drawn calls a move better or worse" |
| A23 | An indicator is matched by its exact id, not a prefix | backtest | `test_a23` |
| A24 | Results on one side only are counted, by side | sentier-bafu | `test_a24` |
| A25 | A file is local unless its writer says otherwise | sentier-bafu, sentier-bafu-agribalyse | `test_a25` |
| A26 | A pair on both sides of the floor that agrees was a zero result, and listed second worst | review of PR 2 | cases A26-* |
| A27 | A factor too large for a float: Python and the page ordered the pair differently, the page wrote "×Infinity" | review of PR 2 | case A27 |
| A28 | Choosing several fixes did not change what the matrix and the distributions below it showed | sentier-bafu (Manuel, 17 November 2026) | `tests/test_ranges.py`; node "Shift-click chooses the steps from one to another together", "steps chosen apart take in the steps between them" |
| A29 | A run of steps was judged as the sum of its steps: two moves under the tolerance each, over it together, agreed | ranges | `test_a_range_moves_where_each_of_its_steps_agrees` |

Also tested: the validator refuses a class, direction or verdict that contradicts the
values, items out of order, counts that do not add up, unknown keys and other formats
(`tests/test_modules.py`); it refuses counts, attribution, `reach` and floors that
disagree with the listed items (`CountsAgainstItems`, one test per edit sentier-bafu's
review made by hand); each of its checks, broken on its own, names its own fault
(`EachRuleOnItsOwn`), so that a check another one backs up cannot go missing unseen; it
returns faults and never raises, whatever type a value has
(a fuzz test of every value in the example); a file is read strictly (no `NaN`, no key
twice), and a table's numbers are plain ASCII decimals; `build` and `check` end in one
line on ordinary mistakes, never a traceback; the summary escapes the file's texts in
Markdown; noise is taken beyond the floor, and a scope entry read from tables without
`expect` may move; the page draws the example whole under Node with a small stand-in for
the DOM (`tests/js/dom.js`), loads nothing from elsewhere and writes no markup from data;
the page takes the matrix the Python writes and refuses one of another file, loads it as a
script or over HTTP after it has drawn, draws 300 rows at a time, sorts by a heading, and
opens the drawer with "why it differs" first (node tests); `matrix.against` finds a changed
code, direction, result, verdict or count (`tests/test_matrix_page.py`); `page.body` is one
root with no frame and no id, and its data cannot end the element that holds it; every
selector of the style is inside the root, with no font and nothing on `:root` or `body`;
the committed examples (the public file, and the local file with its matrix in
`examples/local/`) are what the code makes, the public one holds every class and every verdict, and no
tracked file carries an identifier-shaped string (`tests/test_repository.py`).

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
| The page fetches its data as a file | bafu | yes: the data inside the body, or `window.SENTIER_DIAGNOSTICS` from a site's own `data.js` (`page.as_script`), or `?file=` |
| Every item, not only the listed ones, on a local page | bafu | yes: the matrix (section 4.5), loaded after the page is drawn |
| Noise per item | bafu | no: later |
| The number of digits written | bafu | values are written unrounded; a rounded source is a tolerance basis |
| Symmetric bands, floor of 1 % of the median per indicator | bafu | yes, and per unit |
| No fixed prose such as "only the data differs" | bafu | yes: states carry their own `about` and `identity` |
| A test that the script agrees with the Python rule | bafu | yes: shared cases |
| A formatter target at the lowest Python | bafu | yes: `py310`, CI runs 3.10 to 3.14 |
| Standard library only; assets as package data with their paths | bafu, bafu-agribalyse | yes: `page.assets()` |
| A page without a frame, with a list of tokens for a site's frame | bafu, bafu-agribalyse | yes: `page.body`, a scoped style whose `--sd-*` take the site's tokens (section 10) |
| The grid as the trial dashboard reads: a ratio in every cell, a strong tint, the furthest apart first, compact columns | bafu (from Manuel, 17 November 2026) | yes (section 10.5); 25 indicators still scroll sideways at a laptop's width |
| The look of the trial dashboard: a sortable grid, a drawer for an item | bafu-agribalyse | yes: its look and structure; none of its values, and not its two definitions of agreement, its hand-written labels or a "none" over a top-N list (section 10) |
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
| The file's own word for an indicator ("impact category") | bafu | yes: the optional `indicator` |
| No step 0 in a chain that does not start from the published results | bafu | yes: its steps are numbered from 1 (section 10.2) |
| Choose any set of fixes at the top; the matrix and everything under it show those | bafu (from Manuel, 17 November 2026) | yes, as a run of steps: a set with a gap takes in the steps between, said on the page (section 3) |
| Readable without JavaScript for the counts; 375 px wide | bafu-agribalyse | 375 px: yes, no sideways scroll of the page (tables scroll inside their frame; checked in a browser). Without JavaScript: the summary is Markdown; a no-script page is later |

## 15. Open questions

For Manuel, unless he names someone else:

1. **The second maintainer.** Answered by Manuel on 16 November 2026: Laurenz Bougan.
   Rule 3 still holds: the runbook is written so that either can work alone.
2. **What may be public.** Per-item results against ADEME (the ADEME dashboard holds
   exactly these behind a login), the cap of 200 listed items in sentier-bafu, and
   breakdowns. The tool does not decide; each project's site check does.
3. **A per-value floor from the gross sum of terms** (section 5.2), for projects that have
   breakdowns. It would be a declared floor per pair, which the format cannot hold yet.
4. **Noise per item**, and an absolute cap for `largest` beside the relative one (useful
   for climate change from land use, where results are often near zero). The case for noise
   per item, from sentier-agribalyse's first use on 16 November 2026: two builds of
   upstream main differ in 228 of 2,451 products, by up to 21 % in water use. One noise
   number per indicator then puts 1,507 values of step 0 and 152 of step 1 "within noise"
   because of those 228.
5. **A joint view of two references.**
6. **Laurenz's backtest.** Its scorer and join accounting are the stronger half of what it
   did, and the migration of the ADEME dashboard goes with him. sentier-agribalyse relays
   that Manuel wants his dashboard built on, not replaced; this plan retires its page and
   keeps his scorer. Which of the two Manuel means is for him and Laurenz to settle.
