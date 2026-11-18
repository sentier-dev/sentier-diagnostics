"""Combine weighted evidence using the exact rules pinned by the caller."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contract import SEVERITY, Result, Status, Verdict

#: What is said of an object whose measured share is below the floor. Never a band.
NOT_ENOUGH_EVIDENCE = "not enough evidence"
#: What is said of an object to which no criterion applies (a link with no dataset).
NOTHING_TO_JUDGE = "nothing to judge"


def _number(value: Any, name: str, *, low: float, high: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not low <= value <= high
    ):
        raise ValueError(f"{name} must be a finite number between {low} and {high}")
    return float(value)


@dataclass(frozen=True)
class BandLine:
    name: str
    starts_at: float


@dataclass(frozen=True)
class Caps:
    fail: str
    warn: str


@dataclass(frozen=True)
class Gate:
    mean_drop: float


@dataclass(frozen=True)
class RulesFile:
    about: str
    absent_charge: float
    absent_charge_why: str
    evidence_floor: float
    bands: tuple[BandLine, ...]
    caps: Caps
    gate: Gate
    weights: dict[str, float]

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> RulesFile:
        """Read a JSON quality rules document and validate the scoring policy."""
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ValueError("quality rules have missing or unknown fields")
        if not all(isinstance(data[key], str) for key in ("about", "absent_charge_why")):
            raise ValueError("about and absent_charge_why must be text")
        if not isinstance(data["bands"], list) or len(data["bands"]) < 2:
            raise ValueError("quality rules need at least two bands")
        bands = []
        for row in data["bands"]:
            if not isinstance(row, dict) or set(row) != {"name", "starts_at"}:
                raise ValueError("a band needs its name and starts_at")
            if not isinstance(row["name"], str) or not re.fullmatch(r"[a-z]+( [a-z]+)*", row["name"]):
                raise ValueError("a band needs a lower-case name")
            bands.append(BandLine(row["name"], _number(row["starts_at"], "starts_at", low=0, high=1)))
        starts = [b.starts_at for b in bands]
        names = {b.name for b in bands}
        if starts != sorted(set(starts), reverse=True) or starts[-1] != 0 or len(names) != len(bands):
            raise ValueError("list distinct bands best first with the last starting at zero")
        caps = data["caps"]
        if not isinstance(caps, dict) or set(caps) != {"warn", "fail"}:
            raise ValueError("caps need a warn and a fail band")
        for cap in caps.values():
            if cap not in names:
                raise ValueError(f"the cap {cap!r} is no band")
        if not isinstance(data["gate"], dict) or set(data["gate"]) != {"mean_drop"}:
            raise ValueError("the gate needs mean_drop")
        drop = _number(data["gate"]["mean_drop"], "mean_drop", low=0, high=1)
        floor = _number(data["evidence_floor"], "evidence_floor", low=0, high=1)
        if drop in (0, 1) or floor == 0:
            raise ValueError("mean_drop must be between zero and one and evidence_floor positive")
        if not isinstance(data["weights"], dict):
            raise TypeError("weights must be an object keyed by criterion")
        weights = {key: _number(value, key, low=0, high=math.inf) for key, value in data["weights"].items()}
        if any(value == 0 for value in weights.values()):
            raise ValueError("every criterion weight must be positive")
        return cls(
            data["about"],
            _number(data["absent_charge"], "absent_charge", low=-1, high=0),
            data["absent_charge_why"],
            floor,
            tuple(bands),
            Caps(**caps),
            Gate(drop),
            weights,
        )


@dataclass(frozen=True)
class Rules:
    """The rules as read, with the file's place and checksum."""

    held: RulesFile
    path: str
    sha256: str

    @property
    def weights(self) -> dict[str, float]:
        return dict(self.held.weights)

    @property
    def bands(self) -> tuple[str, ...]:
        """The band names, best first."""
        return tuple(line.name for line in self.held.bands)

    @property
    def said_order(self) -> tuple[str, ...]:
        """Every way a standing can be said, best first: the bands, then not enough
        evidence, then nothing to judge."""
        return (*self.bands, NOT_ENOUGH_EVIDENCE, NOTHING_TO_JUDGE)

    def band_for(self, mean: float) -> str:
        for line in self.held.bands:
            if mean >= line.starts_at:
                return line.name
        return self.held.bands[-1].name

    def weight(self, criterion: str) -> float:
        try:
            return self.held.weights[criterion]
        except KeyError:
            raise KeyError(f"{self.path}: no weight for the criterion {criterion!r}") from None


def read_rules(path: Path, *, shown: str) -> Rules:
    if not path.is_file():
        raise FileNotFoundError(f"{shown}: the rules of the quality build are not there")
    raw = path.read_bytes()
    held = RulesFile.model_validate(json.loads(raw))
    return Rules(held=held, path=shown, sha256=hashlib.sha256(raw).hexdigest())


@dataclass(frozen=True)
class Standing:
    """Where one object stands. ``said`` is a band, :data:`NOT_ENOUGH_EVIDENCE` or
    :data:`NOTHING_TO_JUDGE`; ``band`` is the band only, ``None`` for the other two."""

    said: str
    band: str | None
    mean: float | None
    measured_share: float | None
    measured_weight: float
    applicable_weight: float
    worst: Verdict | None
    capped: bool = False

    def as_written(self) -> dict[str, object]:
        return {
            "said": self.said,
            "band": self.band,
            "mean": self.mean,
            "measured_share": self.measured_share,
            "measured_weight": self.measured_weight,
            "applicable_weight": self.applicable_weight,
            "worst": None if self.worst is None else self.worst.value,
            "capped": self.capped,
        }


def combine(results: Sequence[Result], rules: Rules) -> Standing:
    """The standing of one object from the results of its criteria."""
    if len({item.criterion for item in results}) != len(results):
        raise ValueError("each criterion is scored once per object")
    measured = [item for item in results if item.status is Status.MEASURED]
    absent = [item for item in results if item.status is Status.ABSENT]
    applicable = sum(rules.weight(item.criterion) for item in (*measured, *absent))
    weighed = sum(rules.weight(item.criterion) for item in measured)
    verdicts = [item.verdict for item in measured if item.verdict is not None]
    worst = max(verdicts, key=SEVERITY.__getitem__) if verdicts else None
    if applicable == 0:
        return Standing(NOTHING_TO_JUDGE, None, None, None, 0.0, 0.0, worst)
    total = sum(rules.weight(item.criterion) * (item.value or 0.0) for item in measured)
    total += sum(rules.weight(item.criterion) * rules.held.absent_charge for item in absent)
    mean = round(max(0.0, total / applicable), 6)
    share = round(weighed / applicable, 6)
    if share < rules.held.evidence_floor:
        return Standing(NOT_ENOUGH_EVIDENCE, None, mean, share, weighed, applicable, worst)
    band = rules.band_for(mean)
    capped = band
    if worst is Verdict.FAIL:
        capped = _worse(band, rules.held.caps.fail, rules)
    elif worst is Verdict.WARN:
        capped = _worse(band, rules.held.caps.warn, rules)
    return Standing(capped, capped, mean, share, weighed, applicable, worst, capped != band)


def _worse(band: str, cap: str, rules: Rules) -> str:
    order = rules.bands
    return band if order.index(band) >= order.index(cap) else cap
