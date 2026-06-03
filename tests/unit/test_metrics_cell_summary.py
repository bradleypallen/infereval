"""Tests for ``CellSummary`` / ``cell_summary`` (v0.8.0, closes #84).

The per-cell decomposition summary aggregates the substantive-n and
per-class verdict counts a reader needs to interpret a decomposed
:math:`\\kappa`. The :attr:`is_under_powered` flag reuses
``MIN_K_FOR_SUBSAMPLING_CI = 10`` as the threshold.
"""

from __future__ import annotations

import pytest

from infereval.metrics import (
    MIN_K_FOR_SUBSAMPLING_CI,
    analyst_reference,
    cell_summary,
    consensus_reference,
)
from infereval.types import Verdict

from ..conftest import build_evaluation

G = Verdict.GOOD
B = Verdict.BAD
A = Verdict.ABSTAIN


# ---- substantive-n contract -----------------------------------------------


class TestSubstantiveN:
    def test_n_substantive_excludes_M_abstain(self) -> None:
        """Items where M abstains are excluded from substantive subset."""
        eta = build_evaluation(rows=[([G], G), ([G], A), ([G], B)])
        cs = cell_summary(eta, consensus_reference(eta))
        # row-0: M=G, ref=G -> in; row-1: M=A -> out; row-2: M=B, ref=G -> in.
        assert cs.n_substantive == 2

    def test_n_substantive_excludes_reference_abstain(self) -> None:
        """Items where the reference abstains are excluded too."""
        # 2 analysts so consensus can tie -> abstain.
        eta = build_evaluation(rows=[([G, G], G), ([G, B], B), ([B, B], B)])
        cs = cell_summary(eta, consensus_reference(eta))
        # row-1 ref is a 1-1 tie -> A -> excluded; rows 0, 2 in.
        assert cs.n_substantive == 2

    def test_empty_evaluation_yields_zero_n(self) -> None:
        eta = build_evaluation(rows=[])
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.n_substantive == 0
        assert cs.cohens_kappa is None
        assert cs.fleiss_kappa is None


# ---- class-count invariants -----------------------------------------------


class TestClassCounts:
    def test_class_counts_sum_to_n_substantive(self) -> None:
        eta = build_evaluation(rows=[([G], G), ([G], B), ([B], B), ([B], G)])
        cs = cell_summary(eta, consensus_reference(eta))
        assert sum(cs.m_counts.values()) == cs.n_substantive
        assert sum(cs.r_counts.values()) == cs.n_substantive

    def test_class_counts_have_zero_abstain(self) -> None:
        """On the substantive subset, abstain count is zero by
        construction — the subset excludes any item where M or the
        reference abstains."""
        eta = build_evaluation(rows=[([G], G), ([G], A), ([B], B), ([A], A)])
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.m_counts[Verdict.ABSTAIN] == 0
        assert cs.r_counts[Verdict.ABSTAIN] == 0

    def test_class_counts_match_issue84_n2_example(self) -> None:
        """Mirror the issue's worked Haiku M9 by-tag case: n = 2,
        M unanimously bad, reference unanimously good — the canonical
        forced ``κ_F = -1.0`` shape."""
        eta = build_evaluation(rows=[([G], B), ([G], B)])
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.n_substantive == 2
        assert cs.m_counts == {Verdict.GOOD: 0, Verdict.BAD: 2, Verdict.ABSTAIN: 0}
        assert cs.r_counts == {Verdict.GOOD: 2, Verdict.BAD: 0, Verdict.ABSTAIN: 0}
        # κ_C is undefined here (p_e = 1; each rater concentrated on a single
        # class); the issue example uses κ_F, which is the live degeneracy.
        assert cs.fleiss_kappa is not None
        assert cs.fleiss_kappa < 0  # forced negative


# ---- is_under_powered threshold gate -------------------------------------


class TestUnderPoweredFlag:
    def test_n_below_threshold_is_under_powered(self) -> None:
        eta = build_evaluation(rows=[([G], G), ([G], B)])
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.n_substantive == 2
        assert cs.is_under_powered is True

    def test_n_at_threshold_is_not_under_powered(self) -> None:
        """The threshold gate is ``n < MIN_K_FOR_SUBSAMPLING_CI``;
        equality is *not* under-powered."""
        rows = [([G], G)] * MIN_K_FOR_SUBSAMPLING_CI
        eta = build_evaluation(rows=rows)
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.n_substantive == MIN_K_FOR_SUBSAMPLING_CI
        assert cs.is_under_powered is False

    def test_n_above_threshold_is_not_under_powered(self) -> None:
        rows = [([G], G)] * (MIN_K_FOR_SUBSAMPLING_CI + 5)
        eta = build_evaluation(rows=rows)
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.is_under_powered is False

    def test_empty_cell_is_under_powered(self) -> None:
        eta = build_evaluation(rows=[])
        cs = cell_summary(eta, consensus_reference(eta))
        assert cs.is_under_powered is True


# ---- helper / MetricsReport method parity --------------------------------


class TestHelperMethodParity:
    def test_metrics_report_method_matches_helper(self) -> None:
        """``MetricsReport.cell_summary()`` delegates to the standalone
        helper with the analyst-consensus reference by default."""
        from infereval.metrics import MetricsReport

        eta = build_evaluation(rows=[([G], G), ([G], B), ([B], B)])
        via_helper = cell_summary(eta, consensus_reference(eta))
        via_report = MetricsReport(eta=eta).cell_summary()
        assert via_helper == via_report

    def test_metrics_report_method_with_analyst_reference(self) -> None:
        from infereval.metrics import MetricsReport

        eta = build_evaluation(rows=[([G], G), ([G], B), ([B], B)])
        ref = analyst_reference(eta, 0)
        via_helper = cell_summary(eta, ref)
        via_report = MetricsReport(eta=eta).cell_summary(ref)
        assert via_helper == via_report


# ---- frozen dataclass contract -------------------------------------------


class TestFrozenContract:
    def test_cell_summary_is_frozen(self) -> None:
        eta = build_evaluation(rows=[([G], G)])
        cs = cell_summary(eta, consensus_reference(eta))
        with pytest.raises((AttributeError, TypeError)):
            cs.n_substantive = 999  # type: ignore[misc]
