"""Check uncertainty bands on the exchanges actually delivered by an inventory."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def band_state(exchange: Mapping[str, Any]) -> str:
    """Classify the amount and the P5/P95 pair the inventory reader can consume."""
    amount = _finite(exchange.get("amount"))
    if amount is None:
        return "invalid_amount"
    if amount == 0:
        return "zero_amount"
    if exchange.get("amount_p5") is None or exchange.get("amount_p95") is None:
        return "missing"
    lo, hi = (_finite(exchange[key]) for key in ("amount_p5", "amount_p95"))
    if lo is None or hi is None or lo >= hi:
        return "unconvertible"
    if lo <= amount <= hi:
        return "ok"
    # A positive pair can parameterise a lognormal despite excluding the estimate.
    return "excludes_amount" if lo > 0 else "unconvertible"


def exchange_state(exchange: Mapping[str, Any]) -> str:
    """Also locate a range stranded in provenance, which no P5/P95 reader uses."""
    state = band_state(exchange)
    if state != "missing":
        return state
    provenance = exchange.get("provenance")
    bounds = provenance.get("uncertainty") if isinstance(provenance, Mapping) else None
    if not isinstance(bounds, Mapping) or (bounds.get("min") is None and bounds.get("max") is None):
        return "missing"
    lo, hi = (_finite(bounds.get(key)) for key in ("min", "max"))
    if lo is None or hi is None:
        return "missing, range in provenance.uncertainty unreadable"
    amount = float(exchange["amount"])
    if min(lo, hi) <= amount <= max(lo, hi):
        return "missing, range in provenance.uncertainty contains the amount"
    return "missing, range in provenance.uncertainty excludes the amount"
