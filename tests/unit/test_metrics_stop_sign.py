"""Hand-computed metric verifications against the paper's Example 1.

The stop-sign benchmark has m=1 analyst, n=4 items, with the analyst row
``[good, good, good, bad]``. We verify each scenario against numbers
worked out longhand from the paper's Definitions 6-10.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig
from infereval.evaluation import evaluate as run_evaluate
from infereval.metrics import (
    cohens_kappa,
    consensus_reference,
    coverage,
    fleiss_kappa,
    inter_analyst_fleiss,
)
from infereval.providers.mock import ScriptedProvider
from infereval.types import Verdict

from ..conftest import build_evaluation

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"

G = Verdict.GOOD
B = Verdict.BAD
A = Verdict.ABSTAIN


@pytest.fixture
def stop_sign() -> Benchmark:
    return Benchmark.load(STOP_SIGN_PATH)


# ---- Scenario 1: M matches analyst exactly (Simonelli's reading) ----------


class TestModelMatchesAnalyst:
    """GPT-4.1 as Simonelli reads it: agrees with paper on all 4 rows."""

    @pytest.fixture
    def eta(self, stop_sign: Benchmark):
        provider = ScriptedProvider(responses=["GOOD"] * 9 + ["BAD"] * 3)
        return run_evaluate(
            stop_sign,
            provider,
            config=EndorsementConfig(n_samples=3, question_form="support"),
        )

    def test_coverage_one(self, eta) -> None:
        assert coverage(eta) == 1.0

    def test_cohens_kappa_perfect(self, eta) -> None:
        # All 4 substantive, all match consensus (= single analyst at m=1)
        # p_o = 1, p_M(good) = 3/4, p_M(bad) = 1/4, p_r same, p_e = 9/16 + 1/16 = 10/16
        # kappa = (1 - 10/16) / (1 - 10/16) = 1.0
        assert cohens_kappa(eta, consensus_reference(eta)) == pytest.approx(1.0)

    def test_fleiss_kappa_perfect(self, eta) -> None:
        # At m=1, fleiss(M as 2nd annotator) == cohens vs analyst when both substantive
        assert fleiss_kappa(eta) == pytest.approx(1.0)

    def test_inter_analyst_fleiss_undefined(self, eta, stop_sign: Benchmark) -> None:
        # m=1 -> undefined; the comparison with kappa_C and kappa_F is unavailable per Remark 4
        assert inter_analyst_fleiss(eta) is None
        assert inter_analyst_fleiss(stop_sign) is None


# ---- Scenario 2: M wrong on the defeater (row-3) --------------------------


class TestModelMissesDefeater:
    """M endorses row-3 (painted-blue stop sign -> red) when the analyst says BAD."""

    @pytest.fixture
    def eta(self):
        # Use minimal Evaluation built directly (skip the run_evaluate pipeline
        # to keep the test focused on metrics arithmetic).
        return build_evaluation(
            rows=[([G], G), ([G], G), ([G], G), ([B], G)],
            item_ids=["row-0", "row-1", "row-2", "row-3"],
        )

    def test_cohens_kappa_zero_at_chance(self, eta) -> None:
        # M: G G G G; consensus (= analyst): G G G B
        # p_o = 3/4 = 0.75
        # p_M(good) = 1.0, p_M(bad) = 0.0
        # p_r(good) = 0.75, p_r(bad) = 0.25
        # p_e = 1.0*0.75 + 0.0*0.25 = 0.75
        # kappa = (0.75 - 0.75) / (1 - 0.75) = 0.0
        assert cohens_kappa(eta, consensus_reference(eta)) == pytest.approx(0.0)


# ---- Scenario 3: M abstains on the defeater ------------------------------


class TestModelAbstainsOnDefeater:
    """M abstains on row-3; coverage drops, kappa restricted to substantive subset."""

    @pytest.fixture
    def eta(self):
        return build_evaluation(
            rows=[([G], G), ([G], G), ([G], G), ([B], A)],
            item_ids=["row-0", "row-1", "row-2", "row-3"],
        )

    def test_coverage_three_quarters(self, eta) -> None:
        assert coverage(eta) == 0.75

    def test_cohens_kappa_undefined_p_e_one(self, eta) -> None:
        # S = {0, 1, 2} (row-3 excluded since M abstained)
        # On S: M = G G G, ref = G G G -> p_M(good) = 1, p_r(good) = 1
        # p_e = 1 -> undefined
        assert cohens_kappa(eta, consensus_reference(eta)) is None


# ---- Scenario 4: M completely abstains -----------------------------------


class TestModelAllAbstain:
    """Pathological: M abstains everywhere; kappa fully undefined."""

    @pytest.fixture
    def eta(self):
        return build_evaluation(rows=[([G], A), ([G], A), ([G], A), ([B], A)])

    def test_coverage_zero(self, eta) -> None:
        assert coverage(eta) == 0.0

    def test_cohens_kappa_none(self, eta) -> None:
        assert cohens_kappa(eta, consensus_reference(eta)) is None

    def test_fleiss_kappa_none(self, eta) -> None:
        # All M-side annotations are abstain -> S_F drops them all
        assert fleiss_kappa(eta) is None


# ---- Scenario 5: M flips everywhere --------------------------------------


class TestModelAntiCorrelated:
    """Perfectly anti-correlated M -- kappa goes strongly negative."""

    @pytest.fixture
    def eta(self):
        # Analyst: G G G B; M: B B B G
        return build_evaluation(rows=[([G], B), ([G], B), ([G], B), ([B], G)])

    def test_cohens_kappa_negative(self, eta) -> None:
        # p_o = 0/4 = 0
        # p_M(good) = 1/4, p_M(bad) = 3/4
        # p_r(good) = 3/4, p_r(bad) = 1/4
        # p_e = (1/4)*(3/4) + (3/4)*(1/4) = 3/16 + 3/16 = 6/16 = 0.375
        # kappa = (0 - 0.375) / (1 - 0.375) = -0.6
        assert cohens_kappa(eta, consensus_reference(eta)) == pytest.approx(-0.6)
