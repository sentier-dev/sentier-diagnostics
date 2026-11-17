# sentier-diagnostics: specification

Version 1 of the format, `sentier-diagnostics/1`. Written 16 November 2026. This file says
what the tool answers, what its files hold, how it counts and what it shows. The code in
`src/sentier_diagnostics/` follows it, and every rule here has a test (see
[Acceptance cases](#11-acceptance-cases)). Where the code and this text disagree, one of
them is wrong: open an issue.

Contents: 1 Purpose · 2 Questions · 3 The chain · 4 The format · 5 The counting rule ·
6 Claims and verdicts · 7 Attribution · 8 Explanations · 9 Breakdowns · 10 Views ·
11 Acceptance cases · 12 Out of scope · 13 Decision: seed or rewrite · 14 What the
projects asked for · 15 Open questions · 16 Fixes against one base

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
two solvers on one package differ by about 3e-7. A build has a **noise**: how far two builds
of it differ, measured (section 5.3), or "not measured". The published results have no
builds and carry none: they are exact.

A **step** goes from one state to the next. Its kind is free text that the writer
chooses (`reproduction`, `fix`, `mapping`, `contribution`, `rebuild`, ...). A step has:

- a **claim** (optional): what it says it moves (section 6);
- a **tolerance**: how far two results may differ and still agree;
- a **noise**: the sum of the noise of its two states (section 5.3), worked out, never
  declared on the step;
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
order they were applied in. The file keeps the order; the page says so. A set of changes
chosen freely, not a run of consecutive steps, is not drawn from a chain: section 16
measures each fix on its own against one base, so that any set can be.

**A run of steps.** A file holds one comparison per step and one for the whole way. A run
of two or more consecutive steps, short of every step (steps 3 to 9), is not in the file:
the page judges it from every item's results (`together.py` is the reference). Its pair is
the item's result in the state before the run's first step and in the state after its last:
two built states, never a sum of steps. It is judged by the one rule (section 5) with the
largest tolerance of its steps and, per indicator, the sum of the noise of those two states
(5.3): the pair holds no result of a state inside the run, so neither does its noise. A run
has no verdict: each claim is judged
in its own step. A run needs every item, so it needs the matrix, or a file that lists every
item. Before it draws a run, the page judges each of its steps on its own from the same
results and holds that to the file's class and direction of the step for every item; a run
whose steps disagree with the file is refused, not drawn.

**Steps apart are not compared on a chain.** A step's difference was measured with every
step before it applied, the left-out ones too, and an LCA result is not linear in the
technosphere, so adding up steps apart would use differences measured in a state the set
never had. The page refuses them and says why. Any set of fixes is the business of a file
of fixes measured on one base (section 16, proposed in pull request 23).

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
| `rule` | The floors, the tolerance of the whole way and its noise, `total_noise`: the sum of the noise of the first and last state (section 5.3) |
| `states` | `[{id, label, about, kind, identity, join, noise}]` in order. `identity` is a short table of texts (commit, release, machine); `join` is what the reader counted when it matched its rows to items: `{compared, unmatched, ambiguous, note}`, or null. `noise` is `{measured, between, by, note}`: `between` names two builds of that state and `by` holds a share per indicator measured; every build carries it, measured or not, and the published results never do (exact). A file made before noise belonged to a state has it on no state |
| `steps` | `[{id, from, to, label, about, kind, explained, link, claim, tolerance, noise}]`, one fewer than the states, each from one state to the next. Where the states carry their noise, a step's `noise` is the sum of its two states', `between` null, and the validator holds it to them; it reads `measured: true` whether one end measured or both, and which did is in the states. In a file made before, it is the step's own, with its two builds |
| `counts` | `{steps: {step: {indicator: block}}, total: {indicator: block}}` |
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

`verdicts` is null for a step without a claim and for the whole way. `closer` and
`further` count, for a step after step 0, the moved values that came closer to or went
further from the published results. They are null for step 0 and the whole way, null for
every step of a chain whose first state is not the published results (there is nothing to
come closer to), and no page shows them as better or worse.

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

It also **works the counts out again from the listed items.** Only a pair worth a look
adds to the classes that moved, to missing (by side), to directions, bands, the verdicts
"as claimed", "off claim", "not claimed" and "claimed, not moved", to `closer` and
`further`, and to the attribution; and every item with such a pair is worth a look. So
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

Thirty states is 29 steps. A chain is the built states in order; hundreds of fixes, chosen
in any set, are a file of fixes measured on one base (section 16), not hundreds of states.

### 4.5 The matrix of every item

A file lists the items worth a look, up to `listed`. A project looking at its own build
wants every item: `chain.build_with_matrix` writes them in a second file of format
`sentier-diagnostics-matrix/1`, which the page loads after it has drawn. Only a local file
of items has one; a public file keeps its listed items only. A reader that writes CSV tables
names it in its description (`"matrix": "matrix.json"`), and `sentier-diagnostics build`
writes it beside the file.

```json
{"format": "sentier-diagnostics-matrix/1",
 "of": {"title": "...", "states": ["a", "b", "c"], "indicators": ["x:climate", "x:water"], "steps": ["s0", "s1"]},
 "items":    [["p01", "Wheat", "FR", "crops", "kg"], ...],
 "values":   [[0.52, 0.53, 0.47, 1.2, 1.2, null], ...],
 "classes":  ["=Dd===", ...],
 "verdicts": ["a.==", ...]}
```

One row per item, in the order of the listed items (worst first): `[id, name, place,
group, unit]`; the results per indicator and state, indicator after indicator; per
indicator one code per step and one for the whole way; and, where a step has a claim, per
indicator one verdict code per step (`.` for a step without a claim; `verdicts` is null when
no step has one). A result equal to the one before it in the same indicator, bit for bit, is
written `"="`: in a chain of many steps most results do not change, and this keeps the
matrix small. A `"="` that stands first in an indicator or after a missing result is
refused. The class codes are `=` agrees, `~` within noise, `0` near zero, `-`
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
significant digits). The whole way is counted with the largest tolerance of its steps.

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

**Noise belongs to a state** (decided by Manuel on 17 November 2026). A state's noise is how
far two builds of it differ; the published results have no builds and are exact. A step, a
run of steps and the whole way are each a comparison of two states, and each is judged with
the **sum** of the noise of its two ends, per indicator: rebuilding both ends moves the
difference between them by up to the sum of their noise, and nothing cancels between two
ends. A state inside a run adds nothing: the pair holds none of its results. So a step takes
the noise of its two states, a run that of the state before its first step and the state after
its last, and the whole way (`rule.total_noise`) that of the first and last state. A set of
fixes measured on one base takes the same rule, repeated (section 16).

An end that did not measure an indicator adds nothing to it, and the page says at how many of
the two ends the noise was measured ("measured at 1 of 2 ends"): a noise measured at one end
is never a bound for the comparison. An indicator measured at no end has no noise, and the page
says "not measured", never "identical"; the published results read "exact".

Why: sentier-agribalyse measured noise in upstream main, whose random identifiers make water
use differ by up to 21 % between two builds. The rule before this one took the largest noise
of any step for the whole way and for a run, so main's noise, a state inside them, put 1,504
of 2,451 water results "within noise" where the difference from the published results, exact
at one end and rebuilt bit-identically at the other, was real (A30). The rule before that
judged the whole way without noise, which called a move within the noise of its last state
"differs" (A28). Each comparison now carries the noise of what it compares, no more and no
less.

A file made before noise belonged to a state says a noise per step and never which state it was
measured on: its steps are judged with their own noise, its runs and its whole way without
noise, and the page says so. The validator refuses a `total_noise` in such a file.

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
site's accent. A test reads the sheet and holds this. Where the site's ink is light (or,
with no ink, its ground dark), the script marks the root `data-sd-scheme="dark"` and every
token the site did not set falls back to a dark colour, so that a light ink never stands
on the page's white. It reads the tokens as the browser resolves them (`light-dark()`,
another `var()`), and a token it cannot read as a colour is unknown, never black. A colour
the browser gives in sRGB, `oklab()` or `oklch()` is read as written; any other is drawn on
a canvas of one pixel and read back, and where the browser hides what a canvas holds (a
known colour does not come back as it went) it is unknown as well. It looks
again when the reader's colour scheme changes, when anything changes in the document or in
a shadow root the page sits in, and when a stylesheet loads: once a frame at most, and it
reads the tokens again only where they, the computed `color-scheme` or the reader's
scheme changed, so that a host's observer that answers the page's reading sets off no
other. A rule a site changes through the CSS object model alone changes nothing the page
can see.

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
`matrix.js`, which loads from disk too: it adds the matrix to a list,
`SENTIER_DIAGNOSTICS_MATRICES`, with the address it was loaded from, and a page takes the
entry of the script it names and no other, so that several pages in one document each take
their own. An entry of that script under another query (a host's `matrix.js?v=3`) is taken
where it is this file's matrix: the check against the file, not the address, keeps a stale
one out. A site serving `matrix.json` needs nothing else, as
the page fetches it over HTTP. Served over HTTP the page can also read `?file=...`, and it
opens a file a reader chooses (read in the browser, sent nowhere). **For one step and the whole way, the page works out no class, no direction and no count
of its own.** It reads them from the file, which the validator has checked, and only adds
the file's counts up: the classes that moved into "moved", and a step's counts over its
indicators. Two things it works out itself, and only from every item: the median and
percentiles of a distribution (10.3), and a run of steps (section 3), the one place where
it judges a pair itself in a diagnostics file (a set of fixes is the other, 16.8). It does so with the rule ported from `rule.py`, held to it by the
shared acceptance cases and by 813 pairs on every edge of the rule that the Python writes
(`tests/test_boundaries.py`), after holding each step of the run to the file's own classes.
`tests/fixtures/together.json` holds the counts `together.py` gives for every run of the
local example, and the page is held to them. A file read by `?file=` or chosen by a
reader has not passed through the validator: the page checks its shape only, says so above
everything it draws, and refuses a file it cannot draw instead of drawing part of it. A
matrix is held to the file it says it is of (title, states, indicators, steps, number of
items, the length of every row) before a row of it is drawn; its codes are checked by
`sentier-diagnostics check`, not again in the browser. Whatever the file says, only an
`https://` address becomes a link.

The text a page renders comes from the file or from words chosen to be neutral: it avoids
stage, triage, ledger, layer, upstream, provider and candidate (a test holds this).

**The page is a matrix page.** From the top: the header (10.1); the steps (10.1a), which
choose what is compared: the whole way, one step, or a run of steps; under them one line
for what is chosen: for a step, the states it goes between, what it is, its claim with who
made it, what the claim found, its tolerance and its noise; for a run, the two states it
lies between, each step's claim and what moved in it alone (the quiet ones folded into one
line), its tolerance and its noise; one row of controls (name, group, class, verdict, the size
filter) with the count and the legend in the row under it; then the matrix (10.5), which
opens an item in a drawer (10.6); directly under it, always open, the distributions of the
chosen comparison (10.3). The address keeps what is chosen and an open item, so that a
reviewer can send someone to exactly that view: nothing for the whole way, `#step=<id>` for
one step, `#steps=<first>:<last>` for a run (each id URL-encoded), and `&item=<id>`. In a
host's page each part carries the page's key, so that the page never reads the host's own
parts and two pages never take each other's: the host's name for it (`data-sd-key`), else
`sd.` for the first page in the document and `sd2.`, `sd3.` … for the next
(`#sd.step=<id>`). A host's name is a plain word (a letter, then up to 39 letters, digits,
`-` or `_`), not `sd` or `sdN`; the page refuses any other and says why. A page takes its
key in the document, never outside it: when it is mounted there, or else when it is first
found there (the document changes, the address changes, or it is used). It holds the key
while it is in the document, and a page that left keeps it until a page in the document
needs it. So a page drawn in place of one removed takes the key it left, and an address
made before still opens it; a page built and dropped before it was ever put in takes none;
two pages built before either is put in take one each once they are in. A page out of the
document answers no address. Put back, it takes its key again where no page in the
document holds it, or else the next free one; a page the host named waits instead, says
why, and is drawn once the other page with that name has left. Two pages in the document
never hold one key. `mount` returns `{show, open, close, unmount}`: `unmount()` takes the
page's listeners off (on the window, the document and its own elements), gives its key up
and draws nothing more, leaving the address as it was; a file or a matrix that comes after
it is not drawn. The element is left free: a page may be mounted on it again, as React's
StrictMode does. A page that gives a key up, by `unmount()` or by leaving the document,
wakes a page waiting for it. A host that removes a page for good calls `unmount()`; a page
removed without it stays in memory, in case it is put back. Every part the page does not
own is kept as it was. An
address naming a step the file does not have, steps apart, or a run the page cannot judge
(no matrix), says so and shows the whole way. Below
them, each closed until a reader opens it: the steps and the whole way (10.2), the worst
values (10.4), the explanations and the rule (10.7). A host's page never offers to open a
file; it says only why nothing is drawn.

The line of the chosen step names every verdict on a move with its count, "as claimed"
first ("40 values moved as claimed, 2 off claim ◐"), and "Nothing moved, as claimed" only
where every count is zero. It gives them weight, not colour: a verdict is not an approval
(ADR 0010, A20).

### 10.1 Header
The title, the file's `about`, and one quiet line: how many items and indicators, how many
it holds of how many worth a look, and, for a local file, that its writer has not said it
may be published (a quiet part of the line, as a site's own notice, not a box). The states
in order, with their identity and join counts, head the steps (10.2).

### 10.1a Choosing steps
**A strip**: "The whole way", then one thin cell per step whose height is how many values
moved in it alone (on a log scale, so one value still shows), red at the top where nothing
explains it, a dot where a verdict is worth a look; numbered up to 40 steps, 2 px wide past
60, and scrolling inside its frame. A click chooses one step; Shift (or ⌘ or Ctrl) chooses
every step from the one chosen before, a run. The arrow keys move a step at a time; with
Shift they grow or shrink the run. Chosen steps are filled and underlined.

**A list**, opened by "Find and choose steps": every step with its number, label, kind and
what moved in it; a click chooses it, Shift a run; consecutive steps of one kind under one
heading that chooses their run; a search by number, name or kind; "Only steps where
something moved"; "Every step: the whole way". Without every item the list says why a run
cannot be judged yet, and one step and the whole way remain.

### 10.2 Steps and the whole way
Steps are numbered from 0 where the first state is `published`: step 0 is then the
reproduction (rule 1 of section 1). A chain that starts from a build of its own has no
reproduction, and its steps are numbered from 1.

One row per step: kind, explained or not, the claim and its origin, moved, up, down, the
verdicts, missing before and after, tolerance and noise. Then the whole way per indicator:
every class, up, down, the step that carries most of the difference (section 7), spread
over steps, not attributable, and moved by what nothing explains.

### 10.3 Distributions
One card per indicator, in the order of the matrix's columns (10.5), for the comparison
chosen above (one step, a run of steps or the whole way): a histogram of the file's own counts, from left to right a sign change,
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
more than the whole holds. The three percentiles share one precision: the fewest digits
(three at least, six at most) at which every two that differ read differently, so that no
rounded number stands as exact beside a longer one. Where six still read a percentile as the
median, it says "just under the median" or "just over the median" instead of two equal
numbers, and the numbers left take the digits they need.

A card's title sorts the matrix by its indicator; a heading of the matrix marks its card.

### 10.4 Worst
The N worst values of one comparison (a step or the whole way), ordered by class (sign
change, zero reference, zero result, beyond 10x, differs, missing), then by how far the two
sizes lie apart (`|log10(after/before)|`, or the relative difference where there is no
ratio). The page always says how many it shows of how many, and how many items worth a
look the file does not hold.

### 10.5 Matrix
Items by indicator for the comparison chosen above. **The indicators in which that
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
filters by text, group, class and verdict, the class filter also offering **every class that
moved at once** (and saying how many values moved among the items shown, the count beside
the comparison); 300 rows at a time with "show more". The
reader's **size filter** ("size at least ×1.1 ... ×10") hides smaller changes here and in
the worst list; zeros, sign changes and missing values always show, and the page says the
filter changes no count.

### 10.6 Item
A drawer at the right (the whole window on a phone), opened from a row of the matrix or the
worst list, closed with Close or Escape. It is a dialog drawn above the host's page, named
by the item: beside the matrix, which stays in use, where the window is wide; modal, the
rest inert, where it fills the window or the browser knows no popovers. First **why it differs**: the explanations about
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
| A28 | A move within the noise of its step was counted as "differs" over the whole way, which judged without noise | sentier-agribalyse | `StateNoise` (a move within the noise of an end), node "the whole way and a run take the noise of their two ends" |
| A29 | A run of steps judged by the page has the classes and counts of the Python reference, item by item, is refused where its steps disagree with the file, and steps apart are refused; the page's rule agrees with the Python's on every edge, to the last bit | review of PR 22 | `Together`, `Boundaries`, `tests/fixtures/together.json`, `tests/fixtures/boundaries.json`, node "a run judged by the page", "every edge of the rule", "refuses a run", "steps apart are refused" |
| A30 | The noise of a state inside a run or the whole way, taken as the largest of any step, put 1,504 of 2,451 real differences "within noise"; a comparison now takes the sum of the noise of its two ends, never an inner state's | sentier-agribalyse | `StateNoise`, `Together` (sum of two measured ends), node "two states are compared with the sum of their noise", "a run is judged with the sum of the noise of its two ends" |

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

## 16. Fixes against one base

Status: proposed, 18 November 2026. Manuel decided the direction: a chain is to hold
hundreds of fixes, any set of them can be chosen, and the set is **one base with fixes
measured on their own**, not a chain of hundreds of states ("yes, one base with
independently measured fixes"). He also decided that the fixes live in a file of their own,
and that a set the file cannot show to be exact is shown, marked as estimated. Four
questions were settled in the validator's pull request, before any producer writes a file,
for Manuel to agree there: a pair holds no text (16.6); a fix may require others (16.4); a
fix may bring items the base does not hold (16.4); and a built set may say which state of
the chain it is (16.7). Noise follows section 5.3 (Manuel: "sum, go ahead"): it belongs to
a build, and a comparison takes the sum of the noise of the builds it stands on (16.5).
sentier-bafu wrote a file from its own chain to review the format as its producer (12 fixes
and the release, checked clean), and its review defined the size of a pair (16.6), the route
an effect is measured on (16.4), and the premise of the list of pairs (16.3). The reader and
validator are `fixes.py`; the producer and the page are not written yet (16.12).

### 16.1 Why not a chain of fixes

A step of a chain is measured with every earlier step applied. Its difference belongs to
that place in the order (section 3, "Order matters"). Adding the difference of the third
step to the state before the first, without the second, uses a number measured in a
context the set never had. Precomputing every run of steps does not help either: 100 fixes
have 4,949 runs of two or more, and 2^100 sets. A fix measured on its own against one base
has one effect, whichever set it joins and in whatever order. A hundred fixes need a
hundred measurements.

The chain stays what it is: the built states in order, from the published results through
the base to a release. A fixes file hangs on one of its states.

### 16.2 Words

- **Base**: one state of a chain, the state every fix is measured against.
- **Build**: a set of results the producer made: the base, a fix with what it requires, or
  a built set (16.7). Noise belongs to a build, as it belongs to a state (section 5.3).
- **Fix**: one change, applied to the base alone and built. It has what a step has: a
  kind, a claim, a tolerance, `explained`, a link; and the noise of its build.
- **Requires**: the fixes a fix cannot be applied without. Its effect is measured with
  them applied, and choosing it chooses them.
- **Effect**: what a fix does, per item and indicator: its result with the fix (and what it
  requires) minus its result without the fix (with what it requires).
- **Set**: the fixes a reader chooses together, with everything they require. Its result is
  the base plus the sum of their effects.
- **Interaction**: two fixes whose joint result is not the sum of their effects.

### 16.3 When a sum is the result

An LCA result is h = c·B·A⁻¹·f. It is linear in the characterisation factors c and in
the biosphere matrix B each on its own, bilinear in the two together, and not linear in
the technosphere A. So:

- two fixes that change different characterisation factors, or different entries of B,
  add up exactly;
- a fix that changes the factor of a flow and one that changes how much of that flow an
  activity emits interact;
- two fixes that change A interact on every item whose supply chain reaches both changes.
  Most fixes of a database (a mapping, an amount, a market share) change A;
- a fix that changes A and one that changes B or c interact where the A change shifts how
  much of the changed flow or activity an item's chain draws on;
- two fixes that change the same number of A, B or c do not add up whatever kind it is:
  one replaces what the other set.

These are the kinds of pair a file can list (16.6). Two fixes that change different
factors, or different entries of B, are never a pair.

All of this holds for fixes that are fixed changes of A, B and c. **A fix that edits the
data a model is imported from can change what another fix puts into the matrices**: an
importer that links an exchange to a flow by its name, compartment or CAS number links it to
whatever another fix calls that flow. Changing which flow an exchange is (its name,
compartment or CAS number, where factors match on them) changes B. Several such edits can
be needed together without any one pair showing it. A producer whose fixes edit data checks
that the release's change of A, B and c is the sum of each fix's change, entry by entry, and
says so in `method` (16.6); where it is not, the fixes that meet before the matrices are a
pair (`same entry`), or one requires the others.

An interaction always shows in a pair: every term of A⁻¹ expanded in its changes that
holds two fixes holds two of them next to each other. So a set whose fixes are independent
two by two adds up exactly, however many it holds, and a check of pairs is enough. That
holds for independence in the model (the two changes share no factor, flow or path), not
for two fixes whose joint build happened to agree with their sum: agreement in one build is
evidence about that pair, and proves nothing about a set that holds it with others.

### 16.4 The file

Format `sentier-diagnostics-fixes/1`. It is always local: it holds a result for every
item. One JSON object, read as strictly as the diagnostics file (section 4.1).

| Key | What it holds |
|---|---|
| `format` | `"sentier-diagnostics-fixes/1"` |
| `of` | `{file, title, base, base_noise}`: the diagnostics file it belongs to (a file name), that file's title, the id of the state that is the base, and that state's noise as the diagnostics file says it (5.3). `base_noise` is left out where the base is the published results, which are exact |
| `title`, `about` | Short text; `about` may be null |
| `item`, `indicator`, `indicators` | As in the diagnostics file, and equal to it (`indicator` may be left out where that file leaves it out) |
| `rule` | `{floor_factor, floors_from, beyond, floors}`: the diagnostics file's rule without its `total_tolerance`, which belongs to the chain (a set has its own, 16.5). The floors come from the chain's first state, followed by a floor for each unit only an item a fix brings has |
| `items` | Every item, `[id, name, place, group, unit]`: the matrix's items in the matrix's order, then any item a fix brings that no state of the chain holds |
| `base` | The base result of every item, per indicator: `{indicator: [result or null, ...]}`, in the order of `items`; null for an item a fix brings |
| `fixes` | `[{id, label, about, kind, explained, link, requires, claim, tolerance, noise, effect, counts}]`, a fix's requirements before it; `noise` is that of the build with the fix |
| `interactions` | `{checked, method, by, pairs}` (16.6) |
| `built` | Sets the producer built: `[{id, label, fixes, state, results, noise}]` (16.7) |
| `notes`, `made_by` | As in the diagnostics file |

A fix's `effect` holds, per indicator, the items whose result with the fix is not the
result it was measured against bit for bit, as `[[item index, result], ...]`, the result
being the one built with the fix (`null` where it has none). **Every change is kept,
however small**: two changes under the tolerance each can be over it together, and a set is
a sum. An entry equal to the result it was measured against is refused: it would read as a
change. Every indicator has a list, empty where the fix changes nothing.

**An effect is measured on the base's route.** The result with the fix is built as the base
was (the same importer, linking and solver), or is the base result plus the difference
between two results of one other route, so that an item the fix does not reach keeps the
base result bit for bit. The base is held to the chain bit for bit and every entry that
differs is kept, so an effect computed another way fills up with the route's own
differences, each read as a change: sentier-bafu built one release twice, a pinned copy
against today's importer with no change meant, and 294,590 of 298,675 results moved, 722 of
them by 1e-5 or more. **Results are read exactly**, as they were written, and both sides the
same way. A reader that rounds the last bit merges distinct results and drops changes: a
default CSV reader misread 134,743 of the 298,675 results of one build in the last bit, and
lost 7 of the 86 changes of one patch; read round-trip, every result matches its text. Where
the two sides are read differently (effects read exactly, against a base held to a chain whose
results went through a rounding reader), every misread result reads as a change.

A fix's `counts` is one block per indicator (section 4.2), its pairs being the result it was
measured against and the result with the fix, judged with the fix's own tolerance and the
sum of the noise of those two builds (16.5); `closer` and
`further` are null, since a fix has no published results to come closer to. A fix's claim
names its items (no `items: null`): the file is local and holds every item, and the page
works out each item's verdict from the claim.

**A fix that cannot be applied alone** (a correction to a market that another fix creates,
a factor for a flow another fix adds) names the fixes it needs in `requires`: fixes that
come before it in `fixes`, each once, never itself. What it requires at any depth is
applied when it is built, and its effect and counts are measured against the build of
those fixes together. Where they are one fix with what it requires, that is that fix's
build (a fix that requires `d`, which requires `a`, is measured against the build of `d`);
otherwise it is a built set of exactly those fixes (16.7). A file that holds no such build
is refused: the effect would have nothing to be measured against. A fix and a fix it requires are never a pair (16.6):
one is measured with the other applied.

**A fix may bring items** no state of the chain holds (a new product an added activity
makes). They follow the matrix's items in `items`, their base result is null, and some fix
or built set gives each a result. Their unit takes the chain's floor; a unit no item of the
chain has takes the floor the chain gives a unit its first state holds no result in: 0, from
nothing (`basis: "none"`), added to the rule after the chain's floors.

A fix's claim is judged as a step's is (section 6), against what the fix was measured
against. Its verdicts do not depend on which other fixes are chosen or in what order: that
is what measuring a fix on its own buys.

### 16.5 A set and its label

A set holds everything its fixes require: choosing a fix chooses what it requires, at any
depth, and the page ticks those fixes too and says it added them. At each item, its result
is:

- where one fix of the set changes it, that fix's built result;
- where several do, and they all lie in one build the file holds inside the set, that
  build's result: measured, not summed. The builds are looked at in this order: each fix of
  the set that requires others, with what it requires, in the order of the file; then each
  built set inside the set, in the order of the file. The first that holds them all is
  taken;
- otherwise the base plus each fix's difference against the result it was measured
  against. A fix measured on top of another adds only its own difference, so what both
  build on is counted once. The differences are added left to right in the order of the
  file, one at a time from 0 (`fixes.in_order`), and then to the base; so are the sizes of
  a set's pair terms. Never a compensated sum: Python's `sum()` compensates from 3.12 on,
  and a reader that rounds otherwise parts from the page in the last bit.

Where one of those differences cannot be taken (a missing result with the fix or without
it), the set has no result there, and the page says the sum cannot be formed, apart from a
result that is missing. It is judged by the rule (section 5) against the base:

- its **tolerance** is the largest of its fixes';
- its **noise** follows section 5.3: noise belongs to a build, and a comparison takes the
  sum of the noise of the builds it stands on, never of one it does not. The base's is its
  state's (`of.base_noise`; the published results are exact and add nothing), a fix's that
  of the build with it and what it requires, a built set's that of its build. A set is
  judged **item by item**, with the builds that item's result stands on:
  - where its result is a build's (one fix changes it, or a build inside the set covers
    it, or the set is a build), that build's noise and the base's;
  - where it is a sum, the sum over the fixes that change the item of the noise of each
    fix's build and of the build it was measured against: the base once for each of them
    measured against it, since a rebuild of the base moves each of those differences the
    same way. The base the sum starts from is the base it is compared with, and cancels.

  A fix that does not change an item adds nothing to it. This is the fixes file's form of
  "a state inside a run adds nothing" (5.3): summed over every fix ticked, the noise of
  three fixes on three items, each built at 1 %, was 6 %, and ticking an unrelated fix put
  an item that moved 2.9 % "within noise" (sentier-bafu's probe; A30 again). The sum runs in
  the order of the file's fixes, each fix's measured-against build before its own, so that
  the page's port gives the same number bit for bit.

  Per indicator the page says the largest noise an item is judged with, and at how many of
  the builds those items stand on the noise is known ("noise known at 3 of 5 builds"; the
  published results are known, and exact), never reading not measured as none; where no
  build measured it the page says "not measured", never "identical". Where the set changes
  nothing in an indicator, no item is judged and the noise stands on no build (`builds` 0,
  `value` null): the page says nothing changed there, never "not measured", which is a gap
  in what was measured and not the absence of anything to measure. A noise names its two
  builds (`between`): two builds in one process on one solve route measure the engine's
  determinism and read 0, two routes measure how a result moves with the route; the note
  says which;
- it has **no verdict**: each claim is judged in its own fix.

Each set carries one of three labels, and the page shows it wherever the set is drawn:

| Label | When | What the page draws |
|---|---|---|
| built | the set is one fix with what it requires, or one of `built` | the built results |
| exact | `interactions.checked` is true, and no two of its fixes are a listed pair | the sum, as a result |
| estimated | otherwise | the sum, marked on every cell, in the line above the matrix and in every count ("estimated: 153 would differ"), with the listed pairs it holds, their kinds, and their pair terms where measured ("pair terms up to 0.003 %") |

An estimated set is never drawn as a built one: the mark is on the cell, not only in a
heading a reader may have scrolled past. Its **pair terms** are the sum of the measured
sizes (`largest`) of the listed pairs it holds: how far it may lie from its sum, to first
order (a term of three fixes or more needs interacting pairs, 16.3). Where a pair it holds
was not measured, or has no size (16.6), the pair terms are not known, and the page says how
many of its pairs were measured and how many of those have no size, never 0. Where
interactions were not checked, every set of
two fixes or more that was not built is estimated.

### 16.6 Interactions

The producer works out which pairs can interact from what each fix changes in its model
(which factors, which entries of B, which columns of A and what reaches them). The file
holds the result of that work, not the model: no identifier of an activity or a flow goes
into it.

- `checked`: true where every pair of fixes was examined, false where none was. There is no
  half: a reader must know whether a pair that is not listed was cleared or never looked at.
- `method`: what the check did, in a sentence, and `by`: who or what ran it (section 8).
- `pairs`: `[{fixes: [a, b], kind, reach, largest}]`, every pair that can interact, each
  once:
  - `kind`: where the two changes meet (16.3), the first that applies of `same entry` (both
    change one number), `technosphere` (both change A), `technosphere and emission` (A, and
    an amount of B), `technosphere and factor` (A, and a factor of c), `emission and factor`
    (an amount of a flow, and that flow's factor). A pair that meets in several ways (a fix
    to an amount and an emission of one activity, with a fix to A) takes the first;
  - `reach`: how many items the cross term can change, counted on the build with both fixes
    (1 to the number of items), or null where it was not counted. A fix can open a path (an
    exchange finds a supplier it had none for), so the base undercounts; whether an item
    reaches one fix's change does not depend on that fix, so the build with both bounds it;
  - `largest`: the size of its cross term: the smallest tolerance under which the build of
    the two agrees, by the rule, with the base plus their two effects. That is the largest
    relative difference of the two (the rule's measure, over the larger size, section 5)
    over items and indicators, leaving out the items the rule calls near zero on both sides
    (`fixes.size_of`). `"no size"` where no tolerance is enough: at some item the two lie on
    two sides of zero, one is zero, or one has no result. Null where it was not measured.
    "No size" and "not measured" are kept apart: one is a finding, the other a gap.

  A ratio over |h_ab| has no value where h_ab is 0 and grows without bound for items under
  the floor; such a share would swamp the pair terms of every set holding the pair and make
  the check of its build (16.7) pass anything. The rule's own measure has neither fault, and
  it is the tolerance the check applies. **A pair with no size must be built** (16.7): no set
  holding it can be bounded by its sum, and with the build the page takes its result where
  only those two change an item.

  A check that only asks whether A⁻¹ links two changes lists nearly every pair in a
  database where electricity and transport reach everything, and every set would be
  estimated; the size lets a reader tell a negligible estimate from a large one. A pair
  whose cross term is zero by the model's structure is not listed, and neither is a fix
  with a fix it requires.

**A pair holds no text.** A reason in words ("both change the market for wheat flour")
names the model, and a check of text can only catch what is shaped like an identifier, not
a name. A closed kind, a count and a size say what a reader needs (how the two meet, how
far it spreads, how large it is) and leave nothing to check. The one text the interactions
hold is `method`, and the check refuses one holding text shaped like an identifier (a UUID,
or 32 hexadecimal digits).

The validator cannot see the model, so it cannot prove a pair independent. It holds the
claim to every built set instead (16.7).

### 16.7 Built sets

The producer may build sets as well as single fixes: the release with every fix, a pair
it listed, to measure how far it is from the sum, or the fixes another fix requires, to
measure that fix against. A built set has an id, a label, its fixes (two or more, with
everything they require, and never exactly one fix with what it requires: that is built
already), its results (per indicator, the items whose result is not the base result bit for
bit, as an effect is written), its noise, and `state`: the id of the state of the chain it
is, where it is one, or null.

**A built set tests the claim of independence.** Where `checked` is true and no two of its
fixes are a listed pair, the built results must agree with the base plus the sum of the
effects, by the rule with the set's tolerance and noise, for every item. That sum stands on
the fixes alone (16.5 without its built sets): a set held to a build inside it, itself held
to the sum, would stack two tolerances. The noise is taken item by item, as in 16.5: the
built set's own, and that of the builds the sum stands on at that item (the build it takes
the result from; or the base, with each fix that changes the item, its build and the one it
was measured against; or the base alone where no fix changes it). A fix that does not change
the item adds nothing: otherwise a large built set would pass a real disagreement as within
noise. A file where they do not agree is refused, naming the set, the item and the
indicator: its producer called two fixes independent that are not. Where the set holds a
listed pair, the page shows how far the built results lie from the sum, as that set's
interaction. Where the set is exactly one listed pair with a measured `largest`, the built
results must lie within it of the sum (by the rule, with the larger of the set's tolerance
and `largest` as the tolerance): a file that understates a size it could have measured is
refused. Where the file says the pair has no size, its build must have none: a build that
agrees with its sum under some tolerance has that size, and the check refuses the file and
gives it.

Building the release with every fix is cheap (it is built anyway) and is the strongest test
the file can carry: it touches every pair at once. It can refute independence and never
confirm it: cross terms of opposite sign can cancel in the whole and not in a subset.

**A built set that names a state is two builds of one thing.** The release with every fix
is also the last state of the chain. Its `state` names it, a state after the base, and the
check holds the two to each other: the base with the built results, against the matrix's
results of that state, by the rule with the largest tolerance of its fixes and the noise of
the two builds, the built set's and the state's (none where the state is the published
results), for every item; for the listed items where the matrix is not beside it. A file
whose release does not reproduce the chain's is refused, naming the set, the item and the
indicator. A release taken from the same build as the chain's state passes this check by
construction; the check of independence above is the one that can fail it.

### 16.8 The page

- A searchable list chooses fixes: by name, kind and whether a fix moved anything, with a
  box per fix. Hundreds do not fit a row of chips. Choosing a fix ticks what it requires
  and says so; unticking a fix another chosen fix requires unticks that one too.
- The address names the set: `#set=a,b,c`, in the order of the file. An address that names
  a fix the file does not hold opens on the base and says which.
- One fix reads as a step does today: its claim, its verdicts, its own counts from the file.
- Any set drives the matrix, the distributions, the worst values and the drawer. Its line
  says its label, its fixes with their claims, its tolerance and its noise.
- The page works out the classes of a set, as it does those of a run of steps (section
  10): with the port of `rule.judge` that the shared cases (`tests/acceptance/cases.json`)
  and the boundary pairs the Python writes (`tests/test_boundaries.py`: every class edge,
  the floor, a sign crossing, every band edge, a factor too large for a float) hold to the
  Python rule. It works out a set's noise as 16.5 says, in the same order.
  Before it composes a set it works out each chosen fix's own classes again and compares
  them with the file's; where one differs, it composes nothing and says so.
- In the drawer, an item's difference in a set splits into its fixes' effects, exactly
  where the set is exact, each fix's against what it was measured with. For a built set
  holding a listed pair, the rest is shown as the interaction, never spread over the fixes.
- An estimated set says so wherever its numbers are: "≈" on every value that is a sum, and
  "Estimated:" before its counts, the worst values and the distributions. A value no sum
  can be formed for reads "no sum", never "missing".
- The page offers the choice between the steps of the chain and a set of fixes only where
  a file of fixes came with it. `sentier-diagnostics page FILE --out FOLDER --fixes FIXES`
  checks the file of fixes against the file and its matrix and writes it beside the page as
  `fixes.js`, which adds `{src, fixes}` to `SENTIER_DIAGNOSTICS_FIXES_FILES`, as `matrix.js`
  does; the root names it (`data-sd-fixes`) and the page takes the entry of that script
  only. A host may name `fixes.json` instead (read over http), or set one file of fixes
  for one page, `SENTIER_DIAGNOSTICS_FIXES`. A file of fixes that does not hang on the file
  shown (its title, a base that is no state of it, other indicators, other items or base
  results than the matrix's) is refused, and the page says why.

### 16.9 Checks

`sentier-diagnostics check` refuses a fixes file whose shape, keys, limits or numbers are
wrong (as section 4.3), and further one where:

- `of` does not name the diagnostics file beside it, its title or one of its states, or its
  items, indicators, floors or words differ from that file's (with a floor of 0 from nothing
  for each unit only an added item has); the diagnostics file says no noise of its states;
  `base_noise` is not the base state's noise, is missing where the base is a build, or is
  given where it is the published results;
- its items are not the matrix's in the matrix's order, followed by items a fix brings, or
  an item a fix brings has a base result, or no fix or built set gives it one;
- the base results differ from the matrix's results of the base state, where the matrix is
  beside it, or from the listed items' results, where it is not;
- a fix requires itself, a fix the file does not hold, a fix after it, or one fix twice; or
  the file holds no build of what it requires together;
- an effect or a built set names an item or indicator it does not hold, holds an entry
  equal to the result it was measured against, or holds one item twice;
- a fix's counts or verdicts are not what its effect and the build it was measured against
  give, by the rule, with its own tolerance and the noise of the two builds. With every item
  at hand, the counts must be exact;
- a pair names a fix it does not hold, a fix twice, or a fix and one it requires, or is
  listed twice; its kind is not one of the five, its reach not a count of items, its
  `largest` not a share, `"no size"` or null; a pair with no size has no build; `checked`
  is false and pairs are listed; a pair holds any other key; the method holds text shaped
  like an identifier;
- a built set holds fewer than two fixes, a fix twice, a fix without one it requires,
  exactly one fix with what it requires, or the same fixes as another; or disagrees with the
  sum of its effects where the file says its fixes are independent, or lies further from it
  than the measured size of the one pair it is, or has a size where the file says that pair
  has none; or names a state that is not after the base, or that its results do not
  reproduce.

`check` also prints what the file is made of: how many entries its fixes and built sets
hold, and its largest fixes (a fix to a market everything uses holds about one entry per
item and indicator).

### 16.10 Limits

Up to 1,000 fixes, 500 built sets, 200,000 items and 64 MB, as the matrix. A base of
11,947 items in 25 indicators is about 300,000 numbers; an effect holds only what changed.
sentier-bafu measured its fixes on that base: a patch moves tens of entries, a fix to a
characterisation factor about 12,000 (about 250 KB), a fix to a market everything uses up
to about 300,000 (6 to 7 MB). 64 MB holds about ten dense fixes and thousands of sparse
ones; effects move to one file per fix only if dense fixes become common. Checked on a
made-up file of that base with 100 fixes of 500 items each in every indicator, ten of them
requiring the fix before them, every build's noise measured (39.5 MB), the check takes
about 2.4 seconds, and counting a set of 50 of them, each item with its own noise, about
one.

### 16.11 Acceptance cases

Each is a test before the code is written.

| Case | Rule |
|---|---|
| F1 | Two fixes that each stay within the tolerance and together do not: the set differs, because an effect keeps every change |
| F2 | A set with a listed pair is marked estimated on every cell and in every count, and is never drawn as built |
| F3 | Interactions not checked: every set of two fixes or more that was not built is estimated, none exact |
| F4 | A built set that disagrees with the sum where the file calls its fixes independent is refused, naming the set, item and indicator |
| F5 | A fix's verdicts are the same whichever fixes are chosen with it |
| F6 | A set is judged item by item with the noise of the builds the item's result stands on: a build's and the base's, or for a sum, each summed fix's build and the one it was measured against (the base once for each fix). A fix that does not change the item adds nothing; the builds whose noise is known are counted, and not measured is never identical |
| F7 | The page's rule agrees with the Python rule on every shared case and generated boundary value, and the page refuses to compose where it cannot reproduce a fix's own classes |
| F8 | A file of fixes holds nothing of the model in a pair: its kind comes from a closed list, and any text in it is refused |
| F9 | A fix that requires another is measured against their build; choosing it chooses what it requires; in a set, each effect adds on top of what it was measured with, so what two fixes build on counts once; where a build inside the set holds every fix that changes an item, its result is taken, measured, not summed |
| F10 | A built set that names a state of the chain is refused where its results do not reproduce that state |
| F11 | A fix may bring an item no state holds: it follows the matrix's items, with no base result, and a fix gives it one; in a unit no item of the chain has, it takes a floor of 0 from nothing |
| F12 | A fix is judged with the noise of its build and of the build it was measured against; a built set is held to its sum, item by item, with the noise of the builds both sides stand on there, and to its state with its noise and the state's; the base's noise is its state's, and the published results are exact |
| F13 | A pair with no size is built, and its build has none; "no size" and "not measured" read apart |

### 16.12 Who does what, and in which order

1. This section, agreed by Manuel.
2. The validator, the reader and made-up fixtures (`fixes.py`, `tests/test_fixes.py`), in
   their own pull request: sentier-diagnostics.
3. The producer: every fix built on its own from one factorised base, the check of pairs,
   and the release built with every fix: sentier-bafu, from its engine of differences.
4. The page: the list of fixes, the set in the address, the port of the rule: sentier-bafu.

Open, for later: a public file of fixes (counts per fix only, no item); noise per item
(section 15); and how a fix becomes a step of the chain once it is released.
