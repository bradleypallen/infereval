"""Tests for reporting stratification (:mod:`infereval.stratify`)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from infereval.benchmark import Benchmark
from infereval.evaluation import Evaluation, EvaluationItem
from infereval.stratify import arity_partition, variation_breakdown
from infereval.types import Verdict

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "examples" / "clinical_pilot"
DRYRUN = ROOT / "experiments" / "results" / "clinical_pilot" / "dryrun_2026-06-30"


class TestVariationBreakdown:
    def test_pilot_variation_mix(self) -> None:
        bench = Benchmark.load(PILOT / "benchmark.json")
        eta = Evaluation.load(DRYRUN / "gpt-5.5-eta.json")
        cells = {c.variation: c for c in variation_breakdown(eta, bench)}
        # All 35 items are accounted for across the declared typology.
        assert sum(c.n for c in cells.values()) == 35
        assert cells["monotonicity_step"].n == 13
        assert cells["contested"].n == 6
        # gpt-5.5 returned a substantive verdict on every item in the dry-run.
        assert all(c.coverage == 1.0 for c in cells.values())

    def test_ordering_follows_declared_typology(self) -> None:
        bench = Benchmark.load(PILOT / "benchmark.json")
        eta = Evaluation.load(DRYRUN / "gpt-5.5-eta.json")
        keys = [c.variation for c in variation_breakdown(eta, bench)]
        assert keys[0] == "base"
        assert keys.index("strengthen") < keys.index("monotonicity_step")


class TestArityPartition:
    def test_pilot_is_all_single_succedent(self) -> None:
        eta = Evaluation.load(DRYRUN / "gpt-5.5-eta.json")
        part = arity_partition(eta)
        assert len(part["single"]) == 35
        assert part["exclusivity"] == []
        assert part["exhaustivity"] == []

    def test_buckets_by_conclusion_count(self) -> None:
        # Forward-compat: exclusivity (|Δ|=0) and exhaustivity (|Δ|≥2) buckets.
        items = [
            EvaluationItem(
                id="excl",
                premises=["a", "b"],
                conclusions=[],
                analyst_verdicts=[],
                model_verdict=Verdict.GOOD,
            ),
            EvaluationItem(
                id="one",
                premises=["a"],
                conclusions=["c"],
                analyst_verdicts=[],
                model_verdict=Verdict.GOOD,
            ),
            EvaluationItem(
                id="disj",
                premises=["a"],
                conclusions=["c", "d"],
                analyst_verdicts=[],
                model_verdict=Verdict.BAD,
            ),
        ]
        part = arity_partition(SimpleNamespace(items=items))  # type: ignore[arg-type]
        assert part == {
            "exclusivity": ["excl"],
            "single": ["one"],
            "exhaustivity": ["disj"],
        }
