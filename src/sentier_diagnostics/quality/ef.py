"""Draft EF 4.0 ratings from evidence normalised by an inventory adapter.

The inventory, its data connections and its included datasets have separate
criteria. Projects identify the evidence and its scope. These functions apply
the workbench's reading of JRC142199 to that evidence.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .contract import Absence, Observation, Result, Verdict

_VALIDITY_CLASSES = (5, 7, 10)
_STRONG_SPREAD = {"measured", "published", "modeled"}
_WEAK_SPREAD = {"estimated_default", "confidence_only", "unknown"}
_DATABASE_BASES = {"ilcd_el_ef4": 3.0, "ilcd_el_ef3": 4.0, "non_ef_modelling": 5.0}
OWN_CRITERIA = ("inventory_precision", "inventory_representativeness", "connection_representativeness")


def years_past_validity(reference_year: int | None, validity_years: int | None, *, year: int) -> int | None:
    """Years beyond validity. An undeclared class gives the 10-year lower bound.

    The adapter assigns any evidenced 5-, 7- or 10-year class. It must report
    when a lower bound was used and supply the assessment year for repeatability.
    """
    if validity_years is not None and (
        type(validity_years) is not int or validity_years not in _VALIDITY_CLASSES
    ):
        raise ValueError("validity_years must be 5, 7, 10 or None")
    if type(year) is not int or (reference_year is not None and type(reference_year) is not int):
        raise ValueError("reference and assessment years must be integers")
    if reference_year is None:
        return None
    return max(0, year - reference_year - (validity_years or max(_VALIDITY_CLASSES)))


def representativeness(
    *,
    technology: int | None = None,
    geography: int | None = None,
    time: int | None = None,
    years_past_validity: int | None = None,
) -> float | None:
    """Rate one inventory or connection. Degrees 0–3 mean same through substantial."""
    aspects = (technology, geography, time)
    for value in aspects:
        if value is not None and (type(value) is not int or value not in range(4)):
            raise ValueError("an EF deviation is 0, 1, 2, 3 or None")
    if years_past_validity is not None and (type(years_past_validity) is not int or years_past_validity < 0):
        raise ValueError("years_past_validity must be a non-negative integer or None")
    if 3 in aspects:
        return 5.0
    if aspects.count(None) > 1:
        return None
    tech, geo, temporal = (1 if level is None else level for level in aspects)
    rating = 1 + sum(value > 0 for value in (tech, geo, temporal))
    if 2 in (geo, temporal) or tech == 1:
        rating = max(3, rating)
    if tech == 2:
        rating = max(4, rating)
    downgrade = ((years_past_validity or 0) + 1) // 2
    return float(min(5, rating + downgrade))


def inventory_precision(
    *,
    method_tier: int | None = None,
    spread_tier: str | None = None,
    sample_size: int | None = None,
) -> float | None:
    """Rate own amounts from the construction evidence and independently graded spread.

    Tier 1 denotes modelled amounts and tier 5 an established last-resort or
    archetype construction. Intermediate tiers inherit the source's precision.
    A numerical range alone establishes no spread tier.
    """
    if method_tier is not None and (type(method_tier) is not int or method_tier not in range(1, 6)):
        raise ValueError("method_tier must be 1 through 5 or None")
    if spread_tier is not None and spread_tier not in _STRONG_SPREAD | _WEAK_SPREAD:
        raise ValueError(f"unknown uncertainty tier {spread_tier!r}")
    if sample_size is not None and (type(sample_size) is not int or sample_size < 0):
        raise ValueError("sample_size must be a non-negative integer or None")
    if method_tier == 5:
        return 5.0
    if method_tier != 1:
        return None
    if (sample_size is not None and sample_size <= 2) or spread_tier in _WEAK_SPREAD:
        return 4.0
    return 3.0 if spread_tier in _STRONG_SPREAD else None


def included_rating(bases: Iterable[str | None], *, unresolved: bool = False) -> float | None:
    """Rate documented external modelling bases across a dataset's input closure.

    An EF-compliant database requires its own reviewed ratings. Missing,
    unclassified and unresolved bases withhold a combined value unless a known
    non-EF basis already settles it at 5. Own-model nodes are traversed by the
    adapter and contribute no external rating themselves.
    """
    ratings = [_DATABASE_BASES.get(basis) for basis in bases if basis != "own_model"]
    if 5.0 in ratings:
        return 5.0
    if unresolved or None in ratings:
        return None
    return max((value for value in ratings if value is not None), default=None)


def own_quality(applicable: Mapping[str, float | None], *, threshold: float = 3.0) -> Result:
    """Translate the draft EF ratings for applicable own criteria into one IQS factor.

    Supply every applicable own criterion, with None when evidence is missing.
    Omit a criterion only when it does not apply. Included-dataset ratings are
    reported independently by the caller. The worst applicable criterion decides.
    """
    criterion = "ef_data_quality"
    if set(applicable).difference(OWN_CRITERIA):
        raise ValueError("expected own inventory and connection criteria")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 1 <= threshold < 5:
        raise ValueError("threshold must lie between 1 (inclusive) and 5 (exclusive)")
    if not applicable:
        return Result.not_applicable(criterion, "No own inventory or data connection applies.")
    rated = {name: value for name, value in applicable.items() if value is not None}
    for value in rated.values():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value not in (1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5)
        ):
            raise ValueError("an EF rating must lie on the 1–5 half-step scale")
    counts = (
        Observation("rated", len(rated), how="count of applicable own criteria with a draft rating"),
        Observation("applicable", len(applicable), how="count of applicable own criteria"),
    )
    worst = max(rated.values(), default=None)
    if worst is None or (len(rated) != len(applicable) and worst < 5):
        return Result.absent(
            criterion, Absence.NO_EVIDENCE, "Rated {rated} of {applicable} own criteria.", counts
        )
    verdict = Verdict.FAIL if worst == 5 else Verdict.WARN if worst > threshold else Verdict.PASS
    return Result.measured(
        criterion,
        verdict,
        (5.0 - worst) / 4,
        "Worst draft rating {worst} on {criteria}, threshold {threshold}. Rated {rated} of {applicable}.",
        (
            *counts,
            Observation("worst", worst, how="maximum of the rated own criteria"),
            Observation(
                "criteria",
                ", ".join(sorted(name for name, value in rated.items() if value == worst)),
                how="own criteria at the worst rating",
            ),
            Observation("threshold", threshold, how="project threshold for own EF ratings"),
        ),
        evaluated=len(rated),
    )


def connection_from_basis(
    basis: Mapping[str, str] | None,
    *,
    year_asked: bool,
    years_past_validity: int | None = None,
) -> float | None:
    """Rate a verified inventory-protocol answer basis (revision 50).

    An empty, verified basis records an exact match on all requested facets.
    A missing basis or an unknown substitution leaves the connection unrated.
    Callers must independently verify the basis against the delivered inventory.
    """
    if basis is None:
        return None
    degrees = {
        "product": ("technology", {"exact": 0, "child_term": 1, "parent_term": 2}),
        "variant": ("technology", {"exact": 0, "dropped_variant": 2}),
        "location": ("geography", {"exact": 0, "wider_region": 2, "other_region": 2, "narrower_region": 2}),
        "time": ("time", {"exact": 0, "other_year": 2}),
    }
    aspects = {"technology": 0, "geography": 0, "time": 0 if year_asked else None}
    for facet, level in basis.items():
        if facet not in degrees:
            return None
        aspect, allowed = degrees[facet]
        if level not in allowed:
            return None
        aspects[aspect] = max(aspects[aspect] or 0, allowed[level])
    return representativeness(**aspects, years_past_validity=years_past_validity)
