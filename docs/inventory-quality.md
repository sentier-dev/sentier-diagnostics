# Inventory quality measurements

An adapter reads a project's records and registers criteria for the objects it can examine.
Each criterion returns a `Result`. A measured verdict records at least two observations
and renders its reason from them. Keep the policy for self-reported fields in the adapter
and pass it to `Reader(..., claims=...)`. Use a separate `Registry()` per project. Supply a
healthy fixture and at least one adverse mutation for every registered criterion, then run
`prove(criterion)` in the adapter tests.

## Computing a standing

`read_rules(path, shown=...)` parses a project's JSON policy and hashes the same bytes.
Pass the results for one object to `combine(results, rules)`. The caller supplies one
result per criterion in its profile, including an explicit absence when evidence is missing.
A criterion outside the scope of the object gets a not-applicable result. Rules define the
weights, absence charge, evidence floor, band thresholds and verdict caps. The resulting
standing records the uncapped mean, measured share, worst verdict and capped band. Quality
profiles can cover different phenomena. Compare standings within the same profile.

`quality.gate.compare` compares a quality document and a pinned baseline. Pass the
baseline schema, the band's `rules.said_order`, and `rules.held.gate.mean_drop`. The
result code is 0 for a comparable run without regressions, 1 for findings and 3 for a
comparison that could not be made. The project owns the baseline, the stable object IDs,
the file loading, and the decision to pin it again.

## Applying the workbench IQS branches

| Shared function in `sentier_diagnostics.quality` | Evidence the adapter supplies |
| --- | --- |
| `ef.representativeness` | Independently established deviations in technology, geography and time for the inventory or a connection. Use `None` for an unassessed aspect. |
| `ef.connection_from_basis` | Verified inventory-protocol answer facets. An absent basis and a verified exact match have different meanings. |
| `ef.years_past_validity` | A reference year, the assessment year, and an evidenced 5-, 7- or 10-year class. With an undeclared class, label the result as a lower bound. |
| `ef.inventory_precision` | A construction tier, a graded source of uncertainty and an optional pooled sample size. Tier 1 denotes a model or engineering calculation, tier 5 an established last-resort construction. Copied amounts require evidence of their source's precision. |
| `ef.included_rating` | Documented modelling bases of external inputs and whether the closure is incomplete. A basis of `ef_compliant` requires the included dataset's own reviewed rating. |
| `ef.own_quality` | All applicable own-component ratings, including an explicit `None` for each missing rating. A known 5 determines failure even on an incomplete record. Included-dataset ratings are reported beside this factor. |
| `uncertainty.exchange_state` | An exchange's amount and its consumed P5/P95 bounds. Also detects bounds stranded in provenance, an unusable pair, and a usable distribution excluding its own amount. |

For example, a connection with evidenced identical technology and geography and an
unassessed time span gives a draft rating of 2. A connection with geography alone
generally has insufficient evidence. A substantial deviation on any one aspect settles
the rating at 5. Preserve the underlying evidence, scope, missing fields and assessment
year in the project's report. Only the reviewer can assign the final EF rating.
[European Commission guidance, JRC142199](https://publications.jrc.ec.europa.eu/repository/handle/JRC142199)

The result contract, aggregation and gate originate in the combined Sentier project's
link-quality measurements. The EF projection follows lci-workbench
`iqs/ef-validity-processing@ab43ff154`, the own-criteria factor follows
`iqs/ef-rating-factor@99d939e63`, and exchange band checks follow
`iqs/release-band-report@7edad85e8`. Workbench catalog resolution, its project-specific
assignments of validity classes and modelling bases, and the combined project's link
criteria and evidence-publication policy belong to their respective adapters.
