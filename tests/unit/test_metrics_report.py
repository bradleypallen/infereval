"""Tests for ``infereval.metrics.MetricsReport``."""

from __future__ import annotations

from pathlib import Path

import pytest

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig
from infereval.evaluation import evaluate as run_evaluate
from infereval.metrics import MetricsReport
from infereval.providers.mock import ScriptedProvider
from infereval.types import Verdict

from ..conftest import build_evaluation

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"

G = Verdict.GOOD
B = Verdict.BAD
A = Verdict.ABSTAIN


# ---- Without benchmark ----------------------------------------------------


class TestNoBenchmark:
    def test_coverage_and_kappas(self) -> None:
        eta = build_evaluation(rows=[([G], G), ([G], G), ([B], B), ([B], G)])
        report = MetricsReport(eta=eta)
        assert report.n == 4
        assert report.coverage == 1.0
        assert report.coverage_per_analyst == [1.0]
        assert report.cohens_kappa() is not None  # consensus by default
        assert report.fleiss_kappa is not None
        assert report.inter_analyst_fleiss is None  # m=1

    def test_cohens_kappa_analyst_override(self) -> None:
        eta = build_evaluation(rows=[([G, B], G), ([B, G], B), ([G, G], G)])
        report = MetricsReport(eta=eta)
        # Against analyst 0: M = G B G, analyst-0 = G B G -> perfect
        assert report.cohens_kappa_analyst(0) == pytest.approx(1.0)

    def test_named_coverage_without_benchmark_raises(self) -> None:
        eta = build_evaluation(rows=[([G], G)])
        report = MetricsReport(eta=eta)
        with pytest.raises(ValueError, match="requires a benchmark"):
            report.coverage_per_analyst_named()

    def test_by_rsr_target_without_benchmark_raises(self) -> None:
        eta = build_evaluation(rows=[([G], G)])
        report = MetricsReport(eta=eta)
        with pytest.raises(ValueError, match="requires a benchmark"):
            report.by_rsr_target(frozenset({"sa"}), frozenset({"ra"}))

    def test_to_dict_omits_named_when_no_benchmark(self) -> None:
        eta = build_evaluation(rows=[([G], G), ([B], B)])
        d = MetricsReport(eta=eta).to_dict()
        assert "coverage_per_analyst_named" not in d
        assert "coverage" in d


# ---- With benchmark -------------------------------------------------------


@pytest.fixture
def stop_sign() -> Benchmark:
    return Benchmark.load(STOP_SIGN_PATH)


@pytest.fixture
def stop_sign_eta(stop_sign: Benchmark):
    provider = ScriptedProvider(responses=["GOOD"] * 9 + ["BAD"] * 3)
    return run_evaluate(
        stop_sign,
        provider,
        config=EndorsementConfig(n_samples=3, question_form="support"),
    )


class TestWithBenchmark:
    def test_named_coverage_uses_analyst_ids(self, stop_sign, stop_sign_eta) -> None:
        report = MetricsReport(eta=stop_sign_eta, benchmark=stop_sign)
        named = report.coverage_per_analyst_named()
        assert named == {"paper-author": 1.0}

    def test_to_dict_includes_named_with_benchmark(self, stop_sign, stop_sign_eta) -> None:
        report = MetricsReport(eta=stop_sign_eta, benchmark=stop_sign)
        d = report.to_dict()
        assert d["coverage_per_analyst_named"] == {"paper-author": 1.0}
        assert d["cohens_kappa_consensus"] == pytest.approx(1.0)
        assert d["fleiss_kappa"] == pytest.approx(1.0)
        assert d["inter_analyst_fleiss"] is None  # m=1


# ---- Filters --------------------------------------------------------------


class TestByTag:
    def test_filter_to_subset_with_tag(self) -> None:
        eta = build_evaluation(
            rows=[([G], G), ([G], B), ([B], B), ([B], G)],
            tags_per_row=[["base"], ["defeater"], ["base"], ["defeater"]],
        )
        report = MetricsReport(eta=eta)
        defeater_report = report.by_tag("defeater")
        assert defeater_report.n == 2
        # On defeater subset: M = B G, analyst = G B -> chance-level
        # p_o = 0
        # p_M(good)=0.5, p_M(bad)=0.5, p_r same -> p_e=0.5
        # kappa = -1
        assert defeater_report.cohens_kappa() == pytest.approx(-1.0)

    def test_filter_with_unknown_tag_yields_empty(self) -> None:
        eta = build_evaluation(
            rows=[([G], G), ([B], B)],
            tags_per_row=[["a"], ["b"]],
        )
        report = MetricsReport(eta=eta)
        empty = report.by_tag("c")
        assert empty.n == 0
        assert empty.coverage == 0.0
        assert empty.cohens_kappa() is None

    def test_filter_preserves_benchmark_ref(self, stop_sign, stop_sign_eta) -> None:
        report = MetricsReport(eta=stop_sign_eta, benchmark=stop_sign)
        base = report.by_tag("base-inference")
        assert base.benchmark is stop_sign


class TestByRsrTarget:
    def test_filter_matches_committed_rsr_target(self, stop_sign, stop_sign_eta) -> None:
        report = MetricsReport(eta=stop_sign_eta, benchmark=stop_sign)
        # All 4 items in the stop-sign benchmark target the same X / A
        sub = report.by_rsr_target(frozenset({"sa"}), frozenset({"ra"}))
        assert sub.n == 4
        assert sub.cohens_kappa() == pytest.approx(1.0)

    def test_filter_with_unmatched_target_yields_empty(self, stop_sign, stop_sign_eta) -> None:
        report = MetricsReport(eta=stop_sign_eta, benchmark=stop_sign)
        sub = report.by_rsr_target(frozenset({"nope"}), frozenset({"never"}))
        assert sub.n == 0
