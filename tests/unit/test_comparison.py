"""Tests for cross-run comparison (:mod:`infereval.comparison`, brief §10.1)."""

from __future__ import annotations

import pytest

from infereval.benchmark import Benchmark
from infereval.comparison import compare_runs, total_variation_distance
from infereval.evaluation import EndorsementConfig, ProviderParams, evaluate
from infereval.providers.mock import ScriptedProvider
from infereval.types import Verdict


def _bench() -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "cmp",
            "bearers": {b: {"expression": b} for b in ("p", "c0", "c1", "c2")},
            "analysts": [{"id": "a1"}],
            "items": [
                {
                    "id": f"i{k}",
                    "premises": ["p"],
                    "conclusions": [f"c{k}"],
                    "analyst_verdicts": ["good"],
                }
                for k in range(3)
            ],
        }
    )


def _run(responses: list[str], *, model_id: str = "m", temperature: float = 0.0):
    return evaluate(
        _bench(),
        ScriptedProvider(responses=responses, model_id=model_id),
        config=EndorsementConfig(n_samples=1),
        params=ProviderParams(temperature=temperature),
    )


class TestTVDistance:
    def test_extremes(self) -> None:
        good = {Verdict.GOOD: 1.0, Verdict.BAD: 0.0, Verdict.ABSTAIN: 0.0}
        bad = {Verdict.GOOD: 0.0, Verdict.BAD: 1.0, Verdict.ABSTAIN: 0.0}
        assert total_variation_distance(good, good) == 0.0
        assert total_variation_distance(good, bad) == 1.0


class TestCompareRuns:
    def test_identical_runs_agree_perfectly(self) -> None:
        a = _run(["GOOD", "BAD", "GOOD"])
        b = _run(["GOOD", "BAD", "GOOD"])
        cmp = compare_runs(a, b)
        assert cmp.mean_tv_distance == 0.0
        assert cmp.cross_run_kappa == 1.0
        assert cmp.n_both_substantive == 3
        assert not cmp.insufficient_overlap

    def test_divergent_runs_have_positive_distance(self) -> None:
        a = _run(["GOOD", "GOOD", "GOOD"])
        b = _run(["GOOD", "BAD", "GOOD"])
        cmp = compare_runs(a, b)
        assert cmp.mean_tv_distance > 0.0
        assert cmp.per_item_tv["i1"] == 1.0  # flipped good→bad

    def test_insufficient_overlap_reports_none_kappa(self) -> None:
        a = _run(["GOOD", "GOOD", "GOOD"])
        b = _run(["ABSTAIN", "ABSTAIN", "ABSTAIN"])  # no substantive overlap
        cmp = compare_runs(a, b, coverage_floor=0.5)
        assert cmp.insufficient_overlap
        assert cmp.cross_run_kappa is None
        assert cmp.n_both_substantive == 0


class TestSetupGuard:
    def test_different_model_raises(self) -> None:
        a = _run(["GOOD", "GOOD", "GOOD"], model_id="model-x")
        b = _run(["GOOD", "GOOD", "GOOD"], model_id="model-y")
        with pytest.raises(ValueError, match="same model"):
            compare_runs(a, b)

    def test_different_sampler_config_raises(self) -> None:
        a = _run(["GOOD", "GOOD", "GOOD"], temperature=0.0)
        b = _run(["GOOD", "GOOD", "GOOD"], temperature=0.7)
        with pytest.raises(ValueError, match="sampler config"):
            compare_runs(a, b)

    def test_override_allows_mismatch(self) -> None:
        # Two verdict classes so κ is defined (all-one-class → p_e=1 → κ None).
        a = _run(["GOOD", "BAD", "GOOD"], model_id="model-x")
        b = _run(["GOOD", "BAD", "GOOD"], model_id="model-y")
        cmp = compare_runs(a, b, require_same_setup=False)
        assert cmp.cross_run_kappa == 1.0
