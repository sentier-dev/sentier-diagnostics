"""Observations, measured verdicts, missing evidence and inapplicable criteria."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "Absence",
    "ClaimAsEvidence",
    "ContractError",
    "Observation",
    "Result",
    "Status",
    "Verdict",
    "render_reason",
]


class ContractError(ValueError):
    """A result breaks the contract: a verdict without two observations, a reason that
    shows no operand, a measured result that evaluated nothing."""


class ClaimAsEvidence(ContractError):
    """A criterion read a claim as evidence: a field that would read the same on a
    completely wrong record. A claim may be cited, never read."""


class _TextEnum(str, Enum):
    __str__ = str.__str__


class Status(_TextEnum):
    MEASURED = "measured"  # the criterion judged the object
    ABSENT = "absent"  # it could not; never a pass
    NOT_APPLICABLE = "not_applicable"  # it does not apply to this object


class Verdict(_TextEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class Absence(_TextEnum):
    """Why a result is absent. The two are kept apart: the first is a fact about the object,
    the second about the machine of the run, and a comparison must never read one as the
    other."""

    NO_EVIDENCE = "no_evidence"  # the object holds nothing this criterion can judge
    INPUT_NOT_HERE = "input_not_here"  # an input the criterion needs is not on this machine


#: Worst first is the order a band is capped in.
SEVERITY: dict[Verdict, int] = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.FAIL: 2}

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")

Plain = str | int | float | bool | None


def _shown(value: Plain) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


@dataclass(frozen=True)
class Observation:
    """One value a criterion used: read at ``at`` (``<file label>:<column>``), or computed
    as ``how`` says. Exactly one of the two is given."""

    name: str
    value: Plain
    at: str | None = None
    how: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ContractError(f"observation name {self.name!r} is not a plain identifier")
        if (self.at is None) == (self.how is None):
            raise ContractError(
                f"observation {self.name!r}: say where it was read (at) or how it was "
                "computed (how), one of the two"
            )
        if self.value is not None and not isinstance(self.value, (str, bool, int, float)):
            raise ContractError(f"observation {self.name!r}: a value is one plain value")

        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ContractError(f"observation {self.name!r}: expected a finite value")

    @property
    def shown(self) -> str:
        return _shown(self.value)

    @property
    def source(self) -> str:
        """Where the value was read (``<file label>:<column>``) or how it was computed."""
        return self.at if self.at is not None else f"computed: {self.how}"


def render_reason(template: str, observations: Sequence[Observation], *, require_operands: int) -> str:
    """The reason, with every ``{name}`` replaced by the value of that observation.

    A name that was not observed is refused, at every status: a reason never speaks of a
    quantity nobody computed. A measured reason must substitute at least
    ``require_operands`` observations: a conclusion shows what it rests on.
    """
    by_name = {item.name: item for item in observations}
    if len(by_name) != len(observations):
        raise ContractError("observation names must be distinct")
    used: list[str] = []

    def place(match: re.Match[str]) -> str:
        name = match[1]
        if name not in by_name:
            raise ContractError(
                f"the reason names {{{name}}}, which was not observed; observed: {sorted(by_name)}"
            )
        used.append(name)
        return by_name[name].shown

    text = _PLACEHOLDER.sub(place, template)
    if len(set(used)) < require_operands:
        raise ContractError(
            f"the reason {template!r} shows {len(set(used))} observed operand(s); a measured "
            f"result shows at least {require_operands}: a conclusion says what it rests on"
        )
    return text


@dataclass(frozen=True)
class Result:
    """What one criterion found on one object. Make it with :meth:`measured`,
    :meth:`absent` or :meth:`not_applicable`, which hold the contract."""

    criterion: str
    status: Status
    reason: str
    observations: tuple[Observation, ...] = ()
    verdict: Verdict | None = None
    value: float | None = None
    absence: Absence | None = None
    evaluated: int = 0

    def __post_init__(self) -> None:
        measured = self.status is Status.MEASURED
        if measured != (self.verdict is not None):
            raise ContractError(f"{self.criterion}: a verdict is given exactly when measured")
        if measured != (self.value is not None):
            raise ContractError(f"{self.criterion}: a value is given exactly when measured")
        if (self.status is Status.ABSENT) != (self.absence is not None):
            raise ContractError(f"{self.criterion}: an absent result says why it is absent")
        if measured:
            if self.evaluated < 1:
                raise ContractError(
                    f"{self.criterion}: evaluated nothing and reports measured; a criterion "
                    "that evaluated nothing is absent"
                )
            if len(self.observations) < 2:
                raise ContractError(
                    f"{self.criterion}: a verdict rests on at least two observations, the "
                    f"value found and what it was set against; it has {len(self.observations)}"
                )
            assert self.value is not None
            if not 0.0 <= self.value <= 1.0:
                raise ContractError(f"{self.criterion}: value {self.value} is outside 0 to 1")
        if _PLACEHOLDER.search(self.reason):
            raise ContractError(f"{self.criterion}: the reason keeps a placeholder: {self.reason}")
        if not self.reason.strip():
            raise ContractError(f"{self.criterion}: a result has a reason")

    @classmethod
    def measured(
        cls,
        criterion: str,
        verdict: Verdict,
        value: float,
        template: str,
        observations: Sequence[Observation],
        *,
        evaluated: int = 1,
    ) -> Result:
        held = tuple(observations)
        # The structure is checked before the reason is rendered, so that a result without
        # two observations is refused for that, not for the wording of its reason.
        if evaluated < 1:
            raise ContractError(
                f"{criterion}: evaluated nothing and reports measured; a criterion that "
                "evaluated nothing is absent"
            )
        if len(held) < 2:
            raise ContractError(
                f"{criterion}: a verdict rests on at least two observations, the value found "
                f"and what it was set against; it has {len(held)}"
            )
        return cls(
            criterion=criterion,
            status=Status.MEASURED,
            verdict=verdict,
            value=round(float(value), 6),
            reason=render_reason(template, held, require_operands=2),
            observations=held,
            evaluated=evaluated,
        )

    @classmethod
    def absent(
        cls,
        criterion: str,
        absence: Absence,
        template: str,
        observations: Sequence[Observation] = (),
    ) -> Result:
        held = tuple(observations)
        return cls(
            criterion=criterion,
            status=Status.ABSENT,
            absence=absence,
            reason=render_reason(template, held, require_operands=0),
            observations=held,
        )

    @classmethod
    def not_applicable(
        cls, criterion: str, template: str, observations: Sequence[Observation] = ()
    ) -> Result:
        held = tuple(observations)
        return cls(
            criterion=criterion,
            status=Status.NOT_APPLICABLE,
            reason=render_reason(template, held, require_operands=0),
            observations=held,
        )

    @property
    def said(self) -> str:
        """The verdict, or the status where there is none: what a table shows."""
        return self.verdict.value if self.verdict is not None else self.status.value

    def as_written(self, sources: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
        """The result as a quality file holds it: the observations by name with their values.

        Where each observation was read or how it was computed is the same for every object
        a criterion judges, so it is written once: into ``sources`` (criterion, then name),
        which refuses a name that would stand for two sources. A result that does not apply
        is written without its observations.
        """
        written: dict[str, Any] = {
            "criterion": self.criterion,
            "status": self.status.value,
            "reason": self.reason,
        }
        if self.status is not Status.NOT_APPLICABLE:
            written["observed"] = {item.name: item.value for item in self.observations}
            if sources is not None:
                held = sources.setdefault(self.criterion, {})
                for item in self.observations:
                    if held.setdefault(item.name, item.source) != item.source:
                        raise ContractError(
                            f"{self.criterion}: the observation {item.name!r} stands for two "
                            f"sources: {held[item.name]!r} and {item.source!r}"
                        )
        if self.verdict is not None:
            written["verdict"] = self.verdict.value
            written["value"] = self.value
        if self.absence is not None:
            written["absence"] = self.absence.value
        return written
