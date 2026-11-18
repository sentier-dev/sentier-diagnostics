"""Criteria registered per project with a healthy example and adverse mutations."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .contract import Result, Status, Verdict, _TextEnum


class Channel(_TextEnum):
    PUBLIC = "public"
    LOCAL = "local"


class RegistrationError(ValueError):
    """A criterion does not meet the conditions of the registry."""


@dataclass(frozen=True)
class Criterion:
    """One criterion. ``objects`` names what it judges: ``link`` or ``dataset version``."""

    id: str
    title: str
    objects: str
    judges: str
    evidence: str
    verdicts: tuple[Verdict, ...]
    why: str
    evaluate: Callable[[Any], Result]
    healthy: Callable[[], Any]
    mutations: tuple[tuple[str, Callable[[Any], Any]], ...]
    channel: Channel = Channel.PUBLIC
    #: Inputs beyond the committed files, by name: ``release``, ``local opinions``.
    needs: tuple[str, ...] = ()

    @property
    def worst(self) -> Verdict:
        """The verdict a mutation must bring about: fail where the criterion can fail."""
        return Verdict.FAIL if Verdict.FAIL in self.verdicts else Verdict.WARN

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "objects": self.objects,
            "judges": self.judges,
            "evidence": self.evidence,
            "verdicts": [verdict.value for verdict in self.verdicts],
            "why": self.why,
            "channel": self.channel.value,
            "needs": list(self.needs),
        }


class Registry:
    """A project owns its set of criteria and their order."""

    def __init__(self) -> None:
        self.criteria: dict[str, Criterion] = {}

    def register(self, criterion: Criterion) -> Criterion:
        """Take a criterion into the registry, or refuse it."""
        if criterion.id in self.criteria:
            raise RegistrationError(f"a criterion {criterion.id!r} is registered already")
        if not criterion.mutations:
            raise RegistrationError(
                f"{criterion.id}: no mutation. A criterion comes with at least one function that "
                "breaks a healthy object the way it is meant to notice"
            )
        if Verdict.PASS not in criterion.verdicts:
            raise RegistrationError(f"{criterion.id}: a criterion can pass")
        if criterion.worst not in criterion.verdicts or len(criterion.verdicts) < 2:
            raise RegistrationError(f"{criterion.id}: a criterion can give more than one answer")
        self.criteria[criterion.id] = criterion
        return criterion

    def get(self, criterion_id: str) -> Criterion:
        try:
            return self.criteria[criterion_id]
        except KeyError:
            raise RegistrationError(f"no criterion {criterion_id!r} is registered") from None

    def all_of(self, objects: str) -> tuple[Criterion, ...]:
        """The criteria that judge one kind of object, in the order of registration."""
        return tuple(item for item in self.criteria.values() if item.objects == objects)


def prove(criterion: Criterion) -> list[tuple[str, bool, str]]:
    """Run the healthy object and every mutation: ``(name, flipped, what was said)``.

    The first entry is the healthy object itself, which must pass. A mutation flips when the
    criterion is measured on the broken object and gives its worst verdict.
    """
    out: list[tuple[str, bool, str]] = []
    healthy = criterion.evaluate(criterion.healthy())
    passed = healthy.status is Status.MEASURED and healthy.verdict is Verdict.PASS
    out.append(("healthy", passed, healthy.reason))
    for name, mutate in criterion.mutations:
        broken = criterion.evaluate(mutate(criterion.healthy()))
        flipped = broken.status is Status.MEASURED and broken.verdict is criterion.worst
        out.append((name, flipped, broken.reason))
    return out


def ids(criteria: Iterable[Criterion]) -> tuple[str, ...]:
    return tuple(item.id for item in criteria)
