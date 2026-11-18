"""Public inventory quality interfaces exercised without project data or dependencies."""

import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sentier_diagnostics.quality import ef
from sentier_diagnostics.quality.contract import (
    Absence,
    ClaimAsEvidence,
    ContractError,
    Observation,
    Result,
    Verdict,
)
from sentier_diagnostics.quality.engine import Rules, RulesFile, combine, read_rules
from sentier_diagnostics.quality.gate import compare, pinned_links
from sentier_diagnostics.quality.reader import Reader
from sentier_diagnostics.quality.registry import Criterion, RegistrationError, Registry, prove
from sentier_diagnostics.quality.uncertainty import band_state, exchange_state


def policy():
    return {
        "about": "Test policy",
        "absent_charge": -0.1,
        "absent_charge_why": "Reward measured evidence",
        "evidence_floor": 0.5,
        "bands": [
            {"name": "high", "starts_at": 0.8},
            {"name": "middle", "starts_at": 0.4},
            {"name": "low", "starts_at": 0},
        ],
        "caps": {"warn": "middle", "fail": "low"},
        "gate": {"mean_drop": 0.05},
        "weights": {"count": 4, "coverage": 1},
    }


def quantity(count):
    verdict = Verdict.FAIL if count == 0 else Verdict.PASS
    return Result.measured(
        "count",
        verdict,
        1.0 if count else 0.0,
        "Count {found}, minimum {expected}.",
        (Observation("found", count, at="release:records"), Observation("expected", 1, at="rule:minimum")),
    )


class InventoryQualityTest(unittest.TestCase):
    def test_observations_claims_and_mutations(self):
        r = Reader(
            {"count": 8, "grade": "excellent"}, {}, default="records", claims={"grade": "self-reported"}
        )
        self.assertEqual(r.observe("count").source, "records:count")
        self.assertEqual(r.cite("grade"), "excellent")
        with self.assertRaises(ClaimAsEvidence):
            r.observe("grade")
        self.assertEqual(quantity(8).as_written()["observed"], {"found": 8, "expected": 1})
        with self.assertRaises(ContractError):
            Result.measured("x", Verdict.PASS, 1, "{a} and {b}", [Observation("a", 1, how="counted")] * 2)
        c = Criterion(
            "count",
            "Records",
            "release",
            "non-empty",
            "records",
            (Verdict.PASS, Verdict.FAIL),
            "detect missing records",
            quantity,
            lambda: 8,
            (("drop all", lambda n: 0),),
        )
        first, second = Registry(), Registry()
        first.register(c)
        self.assertEqual([ok for _, ok, _ in prove(c)], [True, True])
        self.assertFalse(second.all_of("release"))
        with self.assertRaises(RegistrationError):
            first.register(c)

    def test_policy_and_coverage(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "rules.json"
            raw = json.dumps(policy()).encode()
            path.write_bytes(raw)
            rules = read_rules(path, shown="rules.json")
        self.assertEqual(rules.sha256, hashlib.sha256(raw).hexdigest())
        missing = Result.absent("coverage", Absence.NO_EVIDENCE, "No evidence.")
        self.assertEqual(combine([quantity(1), missing], rules).mean, 0.78)
        self.assertEqual(combine([missing], rules).said, "not enough evidence")
        self.assertEqual(combine([], rules).said, "nothing to judge")
        capped = Result.measured(
            "coverage",
            Verdict.FAIL,
            1,
            "{a} / {b}",
            [Observation("a", 1, at="a"), Observation("b", 1, at="b")],
        )
        self.assertEqual(
            (combine([quantity(1), capped], rules).band, combine([quantity(1), capped], rules).mean),
            ("low", 1.0),
        )
        with self.assertRaises(ValueError):
            combine([quantity(1), quantity(1)], rules)
        with self.assertRaises(ValueError):
            RulesFile.model_validate({**policy(), "weights": {"count": float("nan")}})

    def test_gate_and_threshold(self):
        rules = Rules(RulesFile.model_validate(policy()), "rules", "digest")

        def document(result, mean):
            return {
                "rules": {"sha256": rules.sha256},
                "links": [
                    {
                        "id": "id",
                        "item": "example",
                        "unit": "kg",
                        "said": "middle",
                        "standing": {"mean": mean},
                        "results": [result.as_written()],
                    }
                ],
            }

        prior = document(quantity(3), 0.8)
        baseline = {
            "schema": "v1",
            "rules_sha256": rules.sha256,
            "links": [{"id": "id", **pinned_links(prior)["id"]}],
        }

        def gate(report):
            return compare(
                report, baseline, schema="v1", order=rules.said_order, mean_drop=rules.held.gate.mean_drop
            )

        self.assertEqual(gate(document(quantity(1), 0.75)).code, 0)
        self.assertEqual(
            {f.kind for f in gate(document(quantity(0), 0.7)).findings}, {"new fail", "mean drop"}
        )
        self.assertEqual(
            gate(document(Result.absent("count", Absence.NO_EVIDENCE, "missing"), 0.8)).findings[0].kind,
            "evidence lost",
        )
        self.assertEqual(
            gate(document(Result.absent("count", Absence.INPUT_NOT_HERE, "missing input"), 0.8)).code, 3
        )
        self.assertEqual(gate({**prior, "rules": {"sha256": "different"}}).code, 3)

    def test_representativeness(self):
        for args, expected in [
            ((0, 0, 0), 1),
            ((0, 0, None), 2),
            ((None, 0, 0), 3),
            ((0, 2, 0), 3),
            ((2, 0, 0), 4),
            ((None, None, 3), 5),
            ((None, None, 1), None),
        ]:
            self.assertEqual(
                ef.representativeness(technology=args[0], geography=args[1], time=args[2]), expected
            )
        for age, expected in [(0, 1), (1, 2), (2, 2), (3, 3), (12, 5)]:
            self.assertEqual(
                ef.representativeness(technology=0, geography=0, time=0, years_past_validity=age), expected
            )
        for years, past in [(5, 4), (7, 2), (10, 0), (None, 0)]:
            self.assertEqual(ef.years_past_validity(2017, years, year=2026), past)
        self.assertIsNone(ef.years_past_validity(None, 7, year=2026))
        self.assertIsNone(ef.connection_from_basis(None, year_asked=True))
        self.assertEqual(ef.connection_from_basis({}, year_asked=False), 2.0)
        self.assertEqual(ef.connection_from_basis({"variant": "dropped_variant"}, year_asked=True), 4.0)
        self.assertIsNone(ef.connection_from_basis({"variant": "unrecognised"}, year_asked=True))

    def test_precision_and_record_scope(self):
        for method, spread, n, expected in [
            (5, None, None, 5),
            (1, "measured", None, 3),
            (1, "modeled", 1, 4),
            (1, "estimated_default", None, 4),
            (1, None, None, None),
            (3, "published", 30, None),
        ]:
            self.assertEqual(
                ef.inventory_precision(method_tier=method, spread_tier=spread, sample_size=n), expected
            )
        self.assertEqual(ef.included_rating(["non_ef_modelling", None], unresolved=True), 5)
        self.assertIsNone(ef.included_rating(["ilcd_el_ef3", "undeclared"]))
        self.assertEqual(ef.included_rating(["ilcd_el_ef4", "own_model", "ilcd_el_ef3"]), 4)
        for ratings, answer in [
            ({}, "not_applicable"),
            ({"inventory_precision": None}, "absent"),
            ({"connection_representativeness": 3}, "pass"),
            ({"inventory_precision": 4}, "warn"),
            ({"inventory_precision": 5, "inventory_representativeness": None}, "fail"),
            ({"inventory_precision": 4, "inventory_representativeness": None}, "absent"),
        ]:
            self.assertEqual(ef.own_quality(ratings).said, answer)
        with self.assertRaises(ValueError):
            ef.own_quality({"included_datasets": 5})

    def test_exchange_bands(self):
        for (amount, lo, hi), state in [
            ((0, None, None), "zero_amount"),
            ((2, None, None), "missing"),
            ((2, 1, 3), "ok"),
            ((-1, -3, 0), "ok"),
            ((2, 3, 4), "excludes_amount"),
            ((-2, -1, 1), "unconvertible"),
            ((1, 2, 2), "unconvertible"),
            ((None, None, None), "invalid_amount"),
            ((2, 1, float("inf")), "unconvertible"),
        ]:
            self.assertEqual(band_state({"amount": amount, "amount_p5": lo, "amount_p95": hi}), state)
        self.assertEqual(
            exchange_state({"amount": 2, "provenance": {"uncertainty": {"min": 1, "max": 3}}}),
            "missing, range in provenance.uncertainty contains the amount",
        )
