# sentier-diagnostics

What changed, before and after, in the impact assessment results of a life cycle
inventory database, and why.

This repository will hold one open tool for the Sentier projects (sentier-bafu,
sentier-bafu-agribalyse, sentier-agribalyse and others): a file format for results
compared before and after a change, one rule for counting what moved, the attribution
of a difference to the steps that made it, and a static page that shows it.

The published results of a database are checked once, at the start: a faithful import
reproduces them. Every later step (a fix, a contribution, a changed mapping) is compared
with the step before it and with what it claimed to move. The page shows the whole way
from the published results to the current build, and what no step explains.

No data is held here: no inventory, no characterisation factors, no results of a
licensed database. Scoring and the readers of each database stay in the projects that
use this tool.

Status: being specified. Not ready for use.

Licence: MIT, see [LICENSE](LICENSE).
