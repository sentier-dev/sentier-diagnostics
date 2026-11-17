# Glossary

The words this repository uses, each in one line. [SPEC.md](SPEC.md) says the rest.

- **Item**: one thing that has results, such as a product or a dataset. Its file calls it by its own word (`item.one`).
- **Indicator**: one impact category, named by an exact id.
- **Reference unit**: the unit an item's result is per (kg, MJ, machine hour). Floors are kept apart per unit.
- **State**: one set of results. The first may be the published results; the others are builds.
- **Step**: from one state to the next, with its kind, claim, tolerance and noise.
- **Step 0**: the reproduction of the published results. The start, never the target. A chain that does not start from the published results has no step 0: its steps are numbered from 1.
- **Chain**: the states in order and the steps between them.
- **Whole way**: from the first state to the last, every step together.
- **Run of steps**: two or more steps that follow each other, short of the whole way; compared as the two built states it lies between. Steps apart are not compared on a chain.
- **Pair**: one item in one indicator, before and after a step.
- **Class**: what a pair is, by one rule: agrees, within noise, differs, beyond 10x, zero reference, zero result, sign change, near zero, missing.
- **Moved**: a pair of class differs, beyond 10x, zero reference, zero result or sign change. Only these have a direction.
- **Direction**: up where the result after is larger as a signed number, down otherwise.
- **Band**: the direction and the factor between the two sizes of a pair that differs.
- **Floor**: the size below which a result counts as near zero; one per indicator and reference unit.
- **Tolerance**: how far two results may differ, relative to the larger, and still agree.
- **Noise**: how far two builds of one state differ, measured.
- **Size filter**: a reader's choice on the page that hides small changes. It changes no count.
- **Claim**: what a step says it moves; its **scope entries** say which indicators and items, which way, how far, and whether they **must** or **may** move.
- **Verdict**: how a pair of a step holds against the step's claim.
- **Attribution**: the split of an item's whole difference into the steps' differences.
- **Explanation**: text about a step, an indicator or an item, with its **origin** (person, code or model) and its **finding** (a reason, or none found). It changes no count.
- **Breakdown**: what one item's result is made of, before and after one step.
- **Tier**: whether a file lists items (`items`) or holds counts only (`counts`).
- **Audience**: whether a file's writer says it may be published (`public`) or not (`local`).
- **Listed items**: the items a file holds, the worst first, up to `listed`.
- **Matrix**: every item of a local file, listed or not, in a second file the page loads after it has drawn.
- **Body**: the page as one element a site holds in its own page; its style stays inside it.
- **Drawer**: the panel of one item, at the right of the page, opened from a row.
