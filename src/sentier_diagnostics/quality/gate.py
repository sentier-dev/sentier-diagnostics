"""Compare quality observations with a baseline pinned under the same rules."""

from __future__ import annotations

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


def _answer(result: Mapping[str, Any]) -> str:
    """How a result is pinned: its verdict, or its status (with the reason of an absence)."""
    if result.get("verdict"):
        return str(result["verdict"])
    if result.get("absence"):
        return f"absent:{result['absence']}"
    return str(result["status"])


def pinned_links(quality: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        link["id"]: {
            "said": link["said"],
            "mean": link["standing"]["mean"],
            "answers": {result["criterion"]: _answer(result) for result in link["results"]},
        }
        for link in quality["links"]
    }


_MEASURED = ("pass", "warn", "fail")


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
    if baseline.get("rules_sha256") != quality["rules"]["sha256"]:
        return GateResult(not_compared=("The current rules differ from the rules used to pin the baseline.",))
    if quality.get("not_here"):
        return GateResult(
            not_compared=(
                "the quality file was made where an input was not on the machine, so a criterion "
                "absent there says nothing about the link: " + "; ".join(quality["not_here"]),
            )
        )
    now = {link["id"]: link for link in quality["links"]}
    current = pinned_links(quality)
    pinned = {entry["id"]: entry for entry in baseline["links"]}
    if len(now) != len(quality["links"]) or len(pinned) != len(baseline["links"]):
        return GateResult(not_compared=("Duplicate object ids prevent a baseline comparison.",))
    if any("absent:input_not_here" in row["answers"].values() for row in current.values()):
        return GateResult(not_compared=("An input was unavailable when the current results were measured.",))
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
