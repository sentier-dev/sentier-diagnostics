"""Compare quality observations with a baseline pinned under the same rules."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_NOT_COMPARED = 3

BAND_DROP = "band drop"
EVIDENCE_LOST = "evidence lost"
NEW_FAIL = "new fail"
MEAN_DROP = "mean drop"
GONE = "gone"


@dataclass(frozen=True)
class Finding:
    kind: str
    id: str
    item: str
    unit: str
    said: str

    def line(self) -> str:
        return f"{self.kind}: {self.item} per {self.unit}: {self.said}"


@dataclass(frozen=True)
class GateResult:
    findings: tuple[Finding, ...] = ()
    not_compared: tuple[str, ...] = ()
    counted: Mapping[str, int] | None = None

    @property
    def code(self) -> int:
        if self.findings:
            return EXIT_FINDING
        if self.not_compared:
            return EXIT_NOT_COMPARED
        return EXIT_OK


_MEASURED = ("pass", "warn", "fail")
_PINNABLE = {*_MEASURED, "absent:no_evidence", "not_applicable"}


def _answer(result: Mapping[str, Any]) -> str:
    """Encode an answer after checking that its status and verdict agree."""
    status = result["status"]
    verdict, absence = result.get("verdict"), result.get("absence")
    if status == "measured" and verdict in _MEASURED and absence is None:
        return verdict
    if status == "absent" and verdict is None and absence in ("no_evidence", "input_not_here"):
        return f"absent:{absence}"
    if status == "not_applicable" and verdict is None and absence is None:
        return status
    raise ValueError("The criterion has an inconsistent status, verdict or absence.")


def _rules_digest(quality: Mapping[str, Any]) -> str:
    rules = quality.get("rules")
    digest = rules.get("sha256") if isinstance(rules, Mapping) else None
    if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError("The quality rules need their SHA-256 digest.")
    return digest


def pinned_links(quality: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Encode each object once. Reject incomplete evidence and ambiguous records."""
    _rules_digest(quality)
    if quality.get("not_here"):
        raise ValueError("An input was unavailable when the current results were measured.")
    entries = {}
    for link in quality["links"]:
        identity = link["id"]
        if identity in entries:
            raise ValueError("Duplicate object id in current results.")
        answers = {}
        for result in link["results"]:
            criterion = result["criterion"]
            if criterion in answers:
                raise ValueError(f"Duplicate criterion {criterion!r} in current results.")
            answer = _answer(result)
            if answer == "absent:input_not_here":
                raise ValueError("An input was unavailable when the current results were measured.")
            answers[criterion] = answer
        entries[identity] = {"said": link["said"], "mean": link["standing"]["mean"], "answers": answers}
    return entries


def compare(
    quality: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    order: tuple[str, ...],
    mean_drop: float,
    schema: str,
) -> GateResult:
    """What worsened from ``baseline`` to ``quality`` (both as their files hold them)."""
    if baseline.get("schema") != schema or not isinstance(baseline.get("links"), list):
        return GateResult(not_compared=(f"the baseline is not of the schema {schema}, so it cannot be read",))
    if quality.get("not_here"):
        return GateResult(
            not_compared=(
                "the quality file was made where an input was not on the machine, so a criterion "
                "absent there says nothing about the link: " + "; ".join(quality["not_here"]),
            )
        )
    try:
        current = pinned_links(quality)
        if baseline.get("rules_sha256") != quality["rules"]["sha256"]:
            raise ValueError("The current rules differ from the rules used to pin the baseline.")
        now = {link["id"]: link for link in quality["links"]}
        pinned = {entry["id"]: entry for entry in baseline["links"]}
        if len(pinned) != len(baseline["links"]):
            raise ValueError("Duplicate object id in baseline.")
        for entry in pinned.values():
            answers = entry["answers"]
            if not isinstance(answers, Mapping) or not set(answers.values()) <= _PINNABLE:
                raise ValueError("The baseline includes an unavailable input or an invalid criterion answer.")
        for entries in (pinned, current):
            for entry in entries.values():
                if entry["said"] not in order:
                    raise ValueError("A recorded standing is outside the rule profile.")
                mean = entry["mean"]
                if mean is not None and (type(mean) not in (int, float) or not 0 <= mean <= 1):
                    raise ValueError("A recorded mean is outside the range 0 to 1.")
    except (KeyError, ValueError, TypeError) as exc:
        return GateResult(not_compared=(f"Cannot compare quality records: {exc}",))
    findings: list[Finding] = []
    counted: Counter[str] = Counter()
    for link_id, before in sorted(pinned.items()):
        held = now.get(link_id)
        if held is None:
            findings.append(
                Finding(
                    GONE,
                    link_id,
                    before.get("item", link_id),
                    before.get("unit", ""),
                    "no longer in the table",
                )
            )
            continue
        after = current[link_id]
        kinds: list[tuple[str, str]] = []
        if order.index(after["said"]) > order.index(before["said"]):
            kinds.append((BAND_DROP, f"{before['said']} -> {after['said']}"))
        elif order.index(after["said"]) < order.index(before["said"]):
            counted["better"] += 1
        for criterion in sorted(before["answers"].keys() | after["answers"].keys()):
            was = before["answers"].get(criterion)
            now_is = after["answers"].get(criterion)
            if was in _MEASURED and now_is in (None, "absent:no_evidence"):
                kinds.append((EVIDENCE_LOST, f"{criterion}: {was} -> absent"))
            if now_is == "fail" and was != "fail":
                kinds.append((NEW_FAIL, f"{criterion}: {was} -> fail"))
        if (
            before["mean"] is not None
            and after["mean"] is not None
            and Decimal(str(before["mean"])) - Decimal(str(after["mean"])) > Decimal(str(mean_drop))
        ):
            kinds.append((MEAN_DROP, f"{before['mean']} -> {after['mean']}"))
        findings.extend(Finding(kind, link_id, held["item"], held["unit"], said) for kind, said in kinds)
    counted["new"] = sum(1 for link_id in current if link_id not in pinned)
    counted["compared"] = sum(1 for link_id in pinned if link_id in now)
    return GateResult(findings=tuple(findings), counted=dict(counted))
