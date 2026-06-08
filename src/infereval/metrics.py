"""Metrics for an evaluation :math:`\\eta`.

Implements Section 4 of the paper ("Evaluation methodology"):

- Coverage :math:`\\mathrm{cov}(\\eta)` and per-analyst coverage
  :math:`\\mathrm{cov}_j(\\eta)`.
- Substantive index :math:`S(\\eta, r)` against a reference verdict
  function :math:`r`.
- Analyst consensus :math:`c_i`.
- Cohen's kappa :math:`\\kappa_C(\\eta, r)` against any reference.
- Fleiss' kappa :math:`\\kappa_F(\\eta)` with :math:`M` as the
  :math:`(m+1)`-th annotator.
- Inter-analyst baseline :math:`\\kappa_F^*(\\beta)` over analyst verdicts
  alone (the comparison point of Remark 4).

Edge cases the paper flags are returned as :data:`None` (with a logged
warning) rather than raised: :math:`\\kappa_F^*` needs :math:`m \\geq 2`
and non-unanimity; :math:`\\kappa_C` is undefined when
:math:`p_e = 1`; both kappa variants are undefined when the relevant
substantive subset is empty.

The high-level :class:`MetricsReport` aggregator bundles all of the above
into a single object suitable for JSON-printing, with ``by_tag`` and
``by_rsr_target`` filters for the decompositions Section 4 calls out.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .types import Verdict

if TYPE_CHECKING:
    from .benchmark import Benchmark
    from .evaluation import Evaluation, EvaluationItem

log = logging.getLogger(__name__)

#: Type alias: a reference verdict function ``r(i) -> Verdict``.
ReferenceFn = Callable[[int], Verdict]

#: Type alias: a per-item weight function. Returns a non-negative weight
#: for each :class:`~infereval.evaluation.EvaluationItem`. Used by the
#: weighted variants of Cohen's / Fleiss' kappa to discount items where
#: the model's verdict is uncertain (e.g. thin sample-margin) so that
#: agreements driven by 3/5-with-2-abstain samples don't count the same
#: as agreements driven by 5/5 samples.
WeightFn = Callable[["EvaluationItem"], float]

#: Verdicts that count as "substantive" for the kappa definitions.
SUBSTANTIVE: frozenset[Verdict] = frozenset({Verdict.GOOD, Verdict.BAD})


# ---- Verdict-distribution (per-item dispersion summary) -------------------


@dataclass(frozen=True, slots=True)
class VerdictDistribution:
    """Per-item distribution of model sample verdicts before majority-vote collapse.

    Captures the dispersion that the standard ``E_M`` majority-vote pipeline
    discards. Two items can both collapse to ``E_M = good`` with very different
    evidence strength (5/5 vs. 3/5-with-2-abstain). Surfacing the dispersion
    lets downstream analysis distinguish confident agreements from thin ones
    (see also :func:`margin_weight` and the
    :class:`~infereval.structure.ThinMarginAgreementCheck`).
    """

    good: int
    bad: int
    abstain: int
    #: Post-tie-break majority verdict (the value of
    #: :attr:`infereval.evaluation.EvaluationItem.model_verdict`).
    verdict: Verdict
    #: Whether the majority vote required tie-break to resolve.
    tie_broken: bool = False

    @property
    def n_samples(self) -> int:
        """Total sample count: ``good + bad + abstain``."""
        return self.good + self.bad + self.abstain

    @property
    def entropy(self) -> float:
        """Shannon entropy of the verdict distribution, normalised to ``[0, 1]``.

        Normalisation divides by :math:`\\log 3` so a uniform distribution
        over the three verdicts gives ``1.0`` regardless of ``n_samples``.
        A single-class distribution (``5/0/0``) gives ``0.0``.
        """
        n = self.n_samples
        if n == 0:
            return 0.0
        h = 0.0
        for c in (self.good, self.bad, self.abstain):
            if c > 0:
                p = c / n
                h -= p * math.log(p)
        return h / math.log(3)

    @property
    def margin(self) -> float:
        """Plurality margin in ``[0, 1]``: ``(top - runner_up) / n_samples``.

        For ties at the top (e.g. ``2/2/1`` good/bad/abstain), ``top == runner_up``
        so the margin is ``0``. The post-tie-break :attr:`verdict` is still
        well-defined; the margin captures the fact that the vote was not
        decisive on its own.
        """
        n = self.n_samples
        if n == 0:
            return 0.0
        counts = sorted([self.good, self.bad, self.abstain], reverse=True)
        return (counts[0] - counts[1]) / n


@dataclass(frozen=True, slots=True)
class AggregateDispersion:
    """Corpus-level summary of per-item :class:`VerdictDistribution` statistics.

    Aggregates the dispersion across all items in an evaluation so a single
    line can convey "how confident was the model on average, and how many
    items were on a knife edge?"
    """

    n_items: int
    mean_entropy: float
    mean_margin: float
    #: Count of items whose :attr:`VerdictDistribution.margin` is strictly
    #: below the thin-margin threshold (default ``0.4``).
    n_thin_margin: int
    thin_margin_threshold: float
    #: Number of items where the majority vote required tie-break.
    n_tie_broken: int

    @property
    def fraction_thin_margin(self) -> float:
        """``n_thin_margin / n_items`` (``0.0`` if no items)."""
        return self.n_thin_margin / self.n_items if self.n_items else 0.0


def verdict_distribution(item: EvaluationItem) -> VerdictDistribution:
    """Build a :class:`VerdictDistribution` from an evaluation item.

    Uses the pre-computed :attr:`~infereval.evaluation.EvaluationItem.majority_vote`
    counts when present (the standard case for items produced by
    :func:`~infereval.endorsement.endorse`); falls back to counting the raw
    :attr:`~infereval.evaluation.EvaluationItem.samples` list (for items
    constructed by tests or external producers that didn't populate
    ``majority_vote``).
    """
    mv = item.majority_vote
    if mv is not None:
        return VerdictDistribution(
            good=mv.good,
            bad=mv.bad,
            abstain=mv.abstain,
            verdict=item.model_verdict,
            tie_broken=mv.tie_broken,
        )
    good = bad = abstain = 0
    for s in item.samples:
        # v0.15.0: skip samples whose provider call failed (provider_error
        # set) — those carry a placeholder ABSTAIN parsed_verdict that is
        # not a real model decision. Mirrors the same skip in
        # infereval.endorsement.endorse() when building MajorityVote.
        if s.provider_error is not None:
            continue
        if s.parsed_verdict == Verdict.GOOD:
            good += 1
        elif s.parsed_verdict == Verdict.BAD:
            bad += 1
        else:
            abstain += 1
    return VerdictDistribution(
        good=good,
        bad=bad,
        abstain=abstain,
        verdict=item.model_verdict,
        tie_broken=False,
    )


def margin_weight(item: EvaluationItem) -> float:
    """Standard per-item weight: the plurality margin in ``[0, 1]``.

    Pass to :func:`cohens_kappa`, :func:`fleiss_kappa`, or
    :func:`inter_analyst_fleiss` as the ``weights`` parameter to compute
    the confidence-weighted variants. An item with a 5/0/0 verdict
    distribution gets full weight; a 3/2/0 item gets ``0.2``; a 2/2/1
    tie-broken item gets ``0.0``.
    """
    return verdict_distribution(item).margin


# ---- Confidence intervals on κ (Politis-Romano subsampling) ----------------


#: Minimum benchmark size for which subsampling-based CIs are defined.
#: The framework's :func:`subsampling_kappa_ci` raises below this; the
#: rule-of-thumb subsample-size default ``round(K^0.7)`` collapses to
#: degenerate sizes (``round(9^0.7) = 5``, ``round(5^0.7) = 3``) before
#: this threshold, and Politis-Romano's large-sample guarantees are
#: visibly fragile at small ``K`` regardless of the chosen ``b``.
MIN_K_FOR_SUBSAMPLING_CI: int = 10


class SubsamplingNotApplicableError(ValueError):
    """Raised when :func:`subsampling_kappa_ci` is invoked on a benchmark too
    small for the subsampling procedure to be meaningful.

    The framework reports point estimates only at that scale; the analyst
    should report the κ value without a CI and note the benchmark size as
    a limitation.
    """


def _default_subsample_size(k: int) -> int:
    """Politis-Romano rule-of-thumb subsample size: ``round(K^0.7)``.

    Satisfies the conditions ``b → ∞`` and ``b/K → 0`` as ``K → ∞``. For
    typical benchmark sizes (``K = 20–60``) this gives ``b ≈ 8–18``.
    """
    return max(2, int(round(k**0.7)))


def subsampling_kappa_ci(
    kappa_fn: Callable[[Evaluation], float | None],
    eta: Evaluation,
    *,
    iterations: int = 1000,
    subsample_size: int | None = None,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Subsampling confidence interval for κ on an :class:`Evaluation`.

    Procedure: Politis & Romano (1994), *Large sample confidence regions
    based on sub-samples under minimal assumptions* (Ann. Statist. 22(4),
    pp. 2031–2050).

    Draws ``iterations`` subsamples of ``subsample_size`` items from the
    ``K = eta.n`` benchmark items WITHOUT replacement; recomputes
    ``kappa_fn`` on each subsample; constructs a basic percentile CI
    from the subsampling distribution, with the standard ``√(b/K)``
    rate correction that brings the spread of the subsampling
    distribution onto the scale of the full-sample statistic.

    Valid under minimal smoothness assumptions on the statistic. Suited
    to κ, which is a non-smooth functional of count data (discrete
    jumps at the majority-vote threshold) where the standard Efron
    nonparametric bootstrap can fail.

    Subsamples on which ``kappa_fn`` returns ``None`` (e.g. degenerate
    p_e=1, empty substantive subset) are dropped from the subsampling
    distribution. If fewer than 10% of subsamples produce defined κ
    values, the CI is widened with a logged warning to reflect that
    the procedure is operating near the edge of its applicability.

    Parameters
    ----------
    kappa_fn
        Function from :class:`Evaluation` to ``float | None`` — e.g.
        ``lambda e: cohens_kappa(e, consensus_reference(e))`` or
        :func:`fleiss_kappa`.
    eta
        Evaluation. Must have ``eta.n >= MIN_K_FOR_SUBSAMPLING_CI``;
        otherwise :class:`SubsamplingNotApplicableError` is raised.
    iterations
        Number of subsamples drawn (default 1000).
    subsample_size
        Items per subsample. Default ``round(K^0.7)``. Must satisfy
        ``2 <= subsample_size < K``.
    confidence
        Two-sided coverage (default 0.95).
    seed
        Optional RNG seed for reproducibility.

    Returns
    -------
    tuple[float, float, float]
        ``(point_estimate, lo, hi)`` — the κ on the full evaluation,
        plus the lower and upper bounds of the confidence interval.

    Raises
    ------
    SubsamplingNotApplicableError
        If ``eta.n < MIN_K_FOR_SUBSAMPLING_CI``.
    ValueError
        If ``subsample_size`` is out of range, or the point estimate
        itself is undefined.
    """
    # Local import keeps the module importable without dragging Evaluation in.
    import random

    k = eta.n
    if k < MIN_K_FOR_SUBSAMPLING_CI:
        raise SubsamplingNotApplicableError(
            f"subsampling_kappa_ci requires at least {MIN_K_FOR_SUBSAMPLING_CI} "
            f"items; got K = {k}. Report the point estimate without a CI and "
            f"note the benchmark size as a limitation."
        )

    b = subsample_size if subsample_size is not None else _default_subsample_size(k)
    if b < 2 or b >= k:
        raise ValueError(
            f"subsample_size must be in [2, K); got {b} with K = {k}"
        )

    point = kappa_fn(eta)
    if point is None:
        raise ValueError(
            "subsampling_kappa_ci: point estimate is undefined on the full "
            "evaluation (kappa_fn returned None); CI cannot be constructed"
        )

    rng = random.Random(seed)
    indices = list(range(k))
    sub_kappas: list[float] = []
    for _ in range(iterations):
        idx = rng.sample(indices, b)
        sub_eta = eta.model_copy(
            update={"items": [eta.items[i] for i in idx]}
        )
        kb = kappa_fn(sub_eta)
        if kb is not None:
            sub_kappas.append(kb)

    if not sub_kappas:
        log.warning(
            "subsampling_kappa_ci: all subsamples produced undefined κ; "
            "returning point estimate with degenerate CI"
        )
        return point, point, point

    defined_fraction = len(sub_kappas) / iterations
    if defined_fraction < 0.10:
        log.warning(
            "subsampling_kappa_ci: only %.1f%% of %d subsamples produced "
            "defined κ values; the CI is operating near the edge of its "
            "applicability — consider a larger benchmark or a different κ variant",
            100 * defined_fraction,
            iterations,
        )

    # Basic-percentile construction with the √(b/K) rate correction:
    # the spread of the subsampling distribution around the subsampling
    # mean is rescaled to the full-sample scale before being added to the
    # point estimate.
    sub_kappas.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = int(alpha * len(sub_kappas))
    hi_idx = max(0, int((1.0 - alpha) * len(sub_kappas)) - 1)
    quantile_lo = sub_kappas[lo_idx]
    quantile_hi = sub_kappas[hi_idx]
    sub_mean = sum(sub_kappas) / len(sub_kappas)
    scale = math.sqrt(b / k)
    lo = point + scale * (quantile_lo - sub_mean)
    hi = point + scale * (quantile_hi - sub_mean)
    return point, lo, hi


# ---- Coverage --------------------------------------------------------------


def coverage(eta: Evaluation) -> float:
    """:math:`\\mathrm{cov}(\\eta) = |\\{i : E_M(I_i) \\neq \\text{abstain}\\}| / n`.

    Returns ``0.0`` for an empty evaluation rather than raising.
    """
    if eta.n == 0:
        return 0.0
    substantive = sum(1 for it in eta.items if it.model_verdict != Verdict.ABSTAIN)
    return substantive / eta.n


def coverage_analyst(eta: Evaluation, analyst_index: int) -> float:
    """:math:`\\mathrm{cov}_j(\\eta) = |\\{i : v_{i,j} \\neq \\text{abstain}\\}| / n`.

    ``analyst_index`` is 0-based and must be ``< m``.
    """
    if eta.n == 0:
        return 0.0
    substantive = sum(
        1
        for it in eta.items
        if it.analyst_verdicts[analyst_index] != Verdict.ABSTAIN
    )
    return substantive / eta.n


def coverage_per_analyst(eta: Evaluation) -> list[float]:
    """Per-analyst coverage as a list indexed by analyst position.

    Returns an empty list if ``eta`` has no items.
    """
    if eta.n == 0:
        return []
    m = len(eta.items[0].analyst_verdicts)
    return [coverage_analyst(eta, j) for j in range(m)]


# ---- Consensus -------------------------------------------------------------


def consensus_verdict(verdicts: Sequence[Verdict]) -> Verdict:
    """Return the analyst consensus :math:`c_i` for one item's verdicts.

    From the paper, Definition 8: ``good`` if strict majority of analysts
    say ``good`` (vs. ``bad``); ``bad`` if strict majority say ``bad``;
    otherwise ``abstain``. Abstain votes do not count toward the majority
    of either substantive class but contribute to a tie.
    """
    good = sum(1 for v in verdicts if v == Verdict.GOOD)
    bad = sum(1 for v in verdicts if v == Verdict.BAD)
    if good > bad:
        return Verdict.GOOD
    if bad > good:
        return Verdict.BAD
    return Verdict.ABSTAIN


def consensus_reference(eta: Evaluation) -> ReferenceFn:
    """Return :math:`r(i) = c_i` as a :data:`ReferenceFn`."""
    per_item = [consensus_verdict(it.analyst_verdicts) for it in eta.items]

    def _ref(i: int) -> Verdict:
        return per_item[i]

    return _ref


def analyst_reference(eta: Evaluation, analyst_index: int) -> ReferenceFn:
    """Return :math:`r(i) = v_{i, \\text{analyst\\_index}}` as a :data:`ReferenceFn`."""
    per_item = [it.analyst_verdicts[analyst_index] for it in eta.items]

    def _ref(i: int) -> Verdict:
        return per_item[i]

    return _ref


# ---- Substantive index ----------------------------------------------------


def substantive_index(eta: Evaluation, reference: ReferenceFn) -> set[int]:
    """:math:`S(\\eta, r) = \\{i : E_M(I_i) \\in \\{\\text{good},\\text{bad}\\} \\wedge r(i) \\in \\{\\text{good},\\text{bad}\\}\\}`."""
    return {
        i
        for i, it in enumerate(eta.items)
        if it.model_verdict in SUBSTANTIVE and reference(i) in SUBSTANTIVE
    }


# ---- Cohen's kappa --------------------------------------------------------


def cohens_kappa(
    eta: Evaluation,
    reference: ReferenceFn,
    *,
    weights: WeightFn | None = None,
) -> float | None:
    """:math:`\\kappa_C(\\eta, r) = (p_o - p_e) / (1 - p_e)`.

    Returns :data:`None` when :math:`S(\\eta, r)` is empty or
    :math:`p_e = 1` (degenerate distribution). Logs a warning in both
    cases so the user sees why the value is undefined.

    Parameters
    ----------
    eta
        The evaluation.
    reference
        Per-item reference verdict function (typically the analyst
        consensus :math:`c_i`).
    weights
        Optional per-item weight function. When ``None`` (default), all
        substantive items count equally and the result is byte-identical
        to the unweighted formulation. When provided, observed and
        chance-expected agreement are computed as weighted relative
        frequencies — items with low weight contribute less to the
        agreement statistic. See :func:`margin_weight` for the standard
        confidence weighting. Items with zero weight are dropped from
        the substantive subset for numerical stability.
    """
    S = sorted(substantive_index(eta, reference))
    if not S:
        log.warning(
            "kappa_C undefined: substantive subset S(eta, r) is empty"
        )
        return None

    if weights is None:
        # Unweighted path: behaviour preserved exactly.
        n_S = len(S)
        p_o = sum(1 for i in S if eta.items[i].model_verdict == reference(i)) / n_S
        p_M: dict[Verdict, float] = {}
        p_r: dict[Verdict, float] = {}
        for c in (Verdict.GOOD, Verdict.BAD):
            p_M[c] = sum(1 for i in S if eta.items[i].model_verdict == c) / n_S
            p_r[c] = sum(1 for i in S if reference(i) == c) / n_S
        p_e = sum(p_M[c] * p_r[c] for c in (Verdict.GOOD, Verdict.BAD))
    else:
        # Weighted path: each item contributes its weight to numerator
        # and denominator. Items with zero weight are dropped.
        w_S = [weights(eta.items[i]) for i in S]
        w_total = sum(w_S)
        if w_total <= 0:
            log.warning(
                "kappa_C undefined: total weight over the substantive subset is "
                "non-positive (all items have zero weight under the supplied "
                "weight function)"
            )
            return None
        p_o = (
            sum(
                w
                for i, w in zip(S, w_S, strict=True)
                if eta.items[i].model_verdict == reference(i)
            )
            / w_total
        )
        p_M_w: dict[Verdict, float] = {}
        p_r_w: dict[Verdict, float] = {}
        for c in (Verdict.GOOD, Verdict.BAD):
            p_M_w[c] = (
                sum(
                    w
                    for i, w in zip(S, w_S, strict=True)
                    if eta.items[i].model_verdict == c
                )
                / w_total
            )
            p_r_w[c] = (
                sum(
                    w
                    for i, w in zip(S, w_S, strict=True)
                    if reference(i) == c
                )
                / w_total
            )
        p_e = sum(p_M_w[c] * p_r_w[c] for c in (Verdict.GOOD, Verdict.BAD))

    if abs(1.0 - p_e) < 1e-12:
        log.warning(
            "kappa_C undefined: chance-expected agreement p_e = 1 "
            "(M and reference both degenerate on a single class over S)"
        )
        return None

    return (p_o - p_e) / (1.0 - p_e)


# ---- Fleiss' kappa --------------------------------------------------------


def _fleiss_over_tuples(
    verdict_tuples: Sequence[Sequence[Verdict]],
    *,
    tuple_weights: Sequence[float] | None = None,
) -> float | None:
    """Fleiss' kappa over a list of equal-length annotator tuples.

    Items with any non-substantive verdict are dropped (matching the
    ``S_F`` filtering of the paper's Definition 10, and the substantive-index
    restriction of Definition 7).

    When ``tuple_weights`` is supplied, the per-item agreement
    contributions ``P_i`` and the cross-item category totals are
    aggregated as weighted averages rather than equal-weight means.
    Behaviour with ``tuple_weights=None`` is byte-identical to the
    unweighted formulation.
    """
    if not verdict_tuples:
        log.warning("Fleiss kappa undefined: no items")
        return None

    n_annotators = len(verdict_tuples[0])
    if n_annotators < 2:
        log.warning("Fleiss kappa undefined: fewer than 2 annotators")
        return None
    if any(len(vs) != n_annotators for vs in verdict_tuples):
        raise ValueError("All annotator tuples must have the same length")
    if tuple_weights is not None and len(tuple_weights) != len(verdict_tuples):
        raise ValueError(
            "tuple_weights length must match verdict_tuples length"
        )

    # Filter to fully-substantive items, carrying weights through if supplied.
    if tuple_weights is None:
        S_F_pairs: list[tuple[Sequence[Verdict], float]] = [
            (vs, 1.0)
            for vs in verdict_tuples
            if all(v in SUBSTANTIVE for v in vs)
        ]
    else:
        S_F_pairs = [
            (vs, w)
            for vs, w in zip(verdict_tuples, tuple_weights, strict=True)
            if all(v in SUBSTANTIVE for v in vs)
        ]
    n_F = len(S_F_pairs)
    if n_F == 0:
        log.warning("Fleiss kappa undefined: no items with all-substantive annotations")
        return None

    w_total = sum(w for _, w in S_F_pairs)
    if w_total <= 0:
        log.warning(
            "Fleiss kappa undefined: total weight over the substantive subset "
            "is non-positive (all items have zero weight)"
        )
        return None

    cat_totals: dict[Verdict, float] = {Verdict.GOOD: 0.0, Verdict.BAD: 0.0}
    weighted_P: float = 0.0
    pair_denom = n_annotators * (n_annotators - 1)

    for vs, w in S_F_pairs:
        n_ic = {
            Verdict.GOOD: sum(1 for v in vs if v == Verdict.GOOD),
            Verdict.BAD: sum(1 for v in vs if v == Verdict.BAD),
        }
        for c, count in n_ic.items():
            cat_totals[c] += w * count
        P_i = sum(n * (n - 1) for n in n_ic.values()) / pair_denom
        weighted_P += w * P_i

    P_bar = weighted_P / w_total

    # In the weighted formulation, each item contributes ``w_i * n_annotators``
    # to the total-annotation count for chance-expected agreement.
    total_annotations = w_total * n_annotators
    p_c = {c: cat_totals[c] / total_annotations for c in (Verdict.GOOD, Verdict.BAD)}
    P_bar_e = sum(p * p for p in p_c.values())

    if abs(1.0 - P_bar_e) < 1e-12:
        log.warning(
            "Fleiss kappa undefined: chance-expected agreement P_bar_e = 1 "
            "(all annotations in one class over S_F)"
        )
        return None

    return (P_bar - P_bar_e) / (1.0 - P_bar_e)


def fleiss_kappa(
    eta: Evaluation,
    *,
    weights: WeightFn | None = None,
) -> float | None:
    """:math:`\\kappa_F(\\eta)` with :math:`M` as the :math:`(m+1)`-th annotator.

    The annotators on each item are the analyst verdicts followed by
    ``model_verdict``. Items where any annotator (analyst or model) is
    non-substantive are excluded from :math:`S_F` per the paper's
    Definition 10.

    Parameters
    ----------
    eta
        The evaluation.
    weights
        Optional per-item weight function. When ``None`` (default), each
        item contributes equally and the result is byte-identical to the
        unweighted formulation. When provided, each item's contribution
        to ``P_bar`` and to the chance-expected agreement is scaled by
        ``weights(item)`` — pass :func:`margin_weight` to compute the
        confidence-weighted variant.
    """
    tuples = [
        [*item.analyst_verdicts, item.model_verdict] for item in eta.items
    ]
    tuple_weights = (
        [weights(item) for item in eta.items] if weights is not None else None
    )
    return _fleiss_over_tuples(tuples, tuple_weights=tuple_weights)


def inter_analyst_fleiss(
    source: Evaluation | Benchmark,
    *,
    analyst_indices: Sequence[int] | None = None,
) -> float | None:
    """:math:`\\kappa_F^*(\\beta)`: Fleiss' kappa over analyst verdicts alone.

    Accepts either an :class:`~infereval.evaluation.Evaluation` or a
    :class:`~infereval.benchmark.Benchmark`. Returns :data:`None` (with
    a logged warning) when :math:`m < 2` or when the analysts are
    unanimous on every item -- the two conditions Remark 4 calls out as
    making the baseline unavailable.

    By default Fleiss' kappa is computed over **all** analyst columns
    declared on ``source.analysts``. This is the methodological reading
    of Remark 4: the inter-analyst baseline is the agreement of the
    full analyst pool whose verdicts the benchmark records.

    For panelled benchmarks, the per-panel decomposition is available
    via :func:`inter_analyst_fleiss_per_panel`; the cross-panel Cohen's
    kappa is in :func:`cross_panel_kappa`. Those exist alongside the
    all-analyst figure here, not in place of it.

    Parameters
    ----------
    source
        :class:`Evaluation` or :class:`Benchmark`.
    analyst_indices
        Optional positional indices into ``source.analysts``. When
        supplied, Fleiss' kappa is computed only over those columns.
        Useful for computing the figure over any subset (e.g.
        ``analyst_indices=benchmark.analyst_indices_in_panel(
        benchmark.resolved_primary_panel())`` reproduces the
        primary-panel-only behaviour the pre-v0.7.0 default returned
        on panelled benchmarks).

    Notes
    -----
    .. versionchanged:: 0.7.0
        On panelled benchmarks, the default behaviour changed from
        "primary panel only" to "all analysts". The previous default
        silently inflated κ_F* when the primary panel was internally
        unanimous; per :gh-issue:`82`, the all-analyst figure is the
        methodologically correct Remark 4 baseline. The
        ``analyst_indices`` parameter is the explicit migration path
        for the rare caller who wants the pre-0.7.0 narrowed value.
    """
    items = source.items
    if analyst_indices is None:
        tuples = [list(it.analyst_verdicts) for it in items]
    else:
        tuples = [[it.analyst_verdicts[j] for j in analyst_indices] for it in items]
    return _fleiss_over_tuples(tuples)


def inter_analyst_fleiss_per_panel(
    benchmark: Benchmark,
) -> dict[str, float | None]:
    """:math:`\\kappa_F^*` computed per analyst panel.

    Returns a mapping ``panel_name -> κ_F*`` for every panel declared on
    the benchmark. A panel value is ``None`` when the panel has fewer
    than 2 analysts or when the analysts are unanimous on every item
    (per the same conditions :func:`inter_analyst_fleiss` honours).

    Empty dict if the benchmark is unpanelled. Phase 1.4 of the
    construct-validity infrastructure (R4).
    """
    out: dict[str, float | None] = {}
    for name in benchmark.panel_names():
        indices = benchmark.analyst_indices_in_panel(name)
        tuples = [
            [it.analyst_verdicts[j] for j in indices] for it in benchmark.items
        ]
        out[name] = _fleiss_over_tuples(tuples)
    return out


def _panel_consensus_verdict(
    item_verdicts: Sequence[Verdict],
    indices: Sequence[int],
) -> Verdict:
    """Majority verdict among the indexed analysts; abstain on tie.

    Used as the per-item consensus for cross-panel agreement
    calculations. Matches the conservative tie-break the framework uses
    elsewhere (per CLAUDE.md locked methodology defaults).
    """
    counts = Counter(item_verdicts[j] for j in indices)
    if not counts:
        return Verdict.ABSTAIN
    top = counts.most_common(1)[0][1]
    winners = [v for v, c in counts.items() if c == top]
    if len(winners) > 1:
        return Verdict.ABSTAIN
    return winners[0]


def cross_panel_kappa(
    benchmark: Benchmark,
    *,
    primary: str | None = None,
    check: str | None = None,
) -> float | None:
    """Cohen's :math:`\\kappa_C` between two panels' per-item consensus verdicts.

    Computes a per-panel consensus verdict for each item (majority among
    panel members, abstain on tie) and then runs Cohen's kappa between
    the two columns, restricted to items where both panels yield a
    substantive verdict.

    Parameters
    ----------
    benchmark
        Panelled benchmark.
    primary
        Name of the primary panel. Defaults to
        ``benchmark.resolved_primary_panel()``.
    check
        Name of the panel to compare against. When ``None`` and exactly
        two panels are declared, picks the non-primary one
        automatically.

    Returns
    -------
    float | None
        Cohen's kappa over the substantive-on-both items, or ``None``
        when fewer than two non-trivial agreement counts are available,
        or when either named panel doesn't exist.

    Phase 1.4 of the construct-validity infrastructure (R4 — guards
    against shared-error agreement within the primary panel by
    surfacing the independent panel's view).
    """
    names = benchmark.panel_names()
    if primary is None:
        primary = benchmark.resolved_primary_panel()
    if primary is None or primary not in names:
        log.warning(
            "cross_panel_kappa: primary panel %r not declared on benchmark %r",
            primary,
            benchmark.id,
        )
        return None
    if check is None:
        others = [n for n in names if n != primary]
        if len(others) != 1:
            log.warning(
                "cross_panel_kappa: 'check' panel must be supplied when the "
                "benchmark declares != 2 panels (declared: %s)",
                names,
            )
            return None
        check = others[0]
    if check not in names:
        log.warning(
            "cross_panel_kappa: check panel %r not declared on benchmark %r",
            check,
            benchmark.id,
        )
        return None

    primary_idx = benchmark.analyst_indices_in_panel(primary)
    check_idx = benchmark.analyst_indices_in_panel(check)

    primary_col = [
        _panel_consensus_verdict(it.analyst_verdicts, primary_idx)
        for it in benchmark.items
    ]
    check_col = [
        _panel_consensus_verdict(it.analyst_verdicts, check_idx)
        for it in benchmark.items
    ]

    # Restrict to items where both panels reached a substantive consensus.
    pairs = [
        (p, c)
        for p, c in zip(primary_col, check_col, strict=True)
        if p != Verdict.ABSTAIN and c != Verdict.ABSTAIN
    ]
    if not pairs:
        log.warning(
            "cross_panel_kappa: empty substantive intersection between panels "
            "%r and %r on benchmark %r",
            primary,
            check,
            benchmark.id,
        )
        return None

    cats = (Verdict.GOOD, Verdict.BAD)
    n = len(pairs)
    p_obs = sum(1 for p, c in pairs if p == c) / n
    pa = {v: sum(1 for p, _ in pairs if p == v) / n for v in cats}
    pc = {v: sum(1 for _, c in pairs if c == v) / n for v in cats}
    p_exp = sum(pa[v] * pc[v] for v in cats)
    if abs(1 - p_exp) < 1e-12:
        log.warning(
            "cross_panel_kappa: chance-expected agreement = 1 (one panel is "
            "fully degenerate to a single class); kappa is undefined"
        )
        return None
    return (p_obs - p_exp) / (1 - p_exp)


# ---- Per-cell decomposition summary (v0.8.0, closes #84) ------------------


@dataclass(frozen=True, slots=True)
class CellSummary:
    """Per-cell decomposition summary for under-powered-aware rendering.

    Aggregates the marginal information a reader needs to interpret a
    decomposed :math:`\\kappa` value — particularly on small subsets
    where the magnitude is forced by single-class-each marginals rather
    than measured. Used by the ``infereval metrics --by-tag`` /
    ``--by-rsr-target`` CLI renderers and by the construct-validity
    report's section 4b under-powered findings (issue #84, v0.8.0).

    The class counts are computed over the *substantive subset*
    :math:`S(\\eta, r)` — the same subset :math:`\\kappa_C` is computed
    over — so abstain counts are zero by construction. The full-cell
    coverage and abstain counts are still available via the parent
    :class:`MetricsReport`; this dataclass is intentionally narrow.

    The :attr:`is_under_powered` flag reuses
    :data:`MIN_K_FOR_SUBSAMPLING_CI` as the threshold; cells at or above
    the threshold render unchanged, cells below it get an
    ``[under-powered: n < 10]`` annotation on the rendered kappa value
    and surface as section 4b negative findings.
    """

    n_substantive: int
    """``|S(\\eta, r)|`` — the size of the substantive subset that κ is
    computed over. The under-powered threshold gates on this, not on the
    pre-substantive-index ``eta.n`` count."""

    m_counts: dict[Verdict, int]
    """M's verdict counts over the substantive subset. Keys cover all
    three :class:`~infereval.types.Verdict` values; the abstain count
    is zero by construction (the subset excludes M-abstain items)."""

    r_counts: dict[Verdict, int]
    """Reference's verdict counts over the substantive subset. Same
    keys + abstain-is-zero contract as :attr:`m_counts`."""

    cohens_kappa: float | None
    """:math:`\\kappa_C(\\eta, r)` on this cell. ``None`` when the
    substantive subset is empty or :math:`p_e = 1`."""

    fleiss_kappa: float | None
    """:math:`\\kappa_F(\\eta)` on this cell. ``None`` when the
    substantive subset is empty or degenerate."""

    @property
    def is_under_powered(self) -> bool:
        """``True`` when ``n_substantive < MIN_K_FOR_SUBSAMPLING_CI``.

        Mirrors the threshold used to gate Politis-Romano CIs on the
        headline. Cells at or above the threshold render unchanged;
        cells below it get the under-powered annotation on the κ line
        and surface as section 4b negative findings in the
        construct-validity report.
        """
        return self.n_substantive < MIN_K_FOR_SUBSAMPLING_CI


def cell_summary(
    eta: Evaluation,
    reference: ReferenceFn,
) -> CellSummary:
    """Compute the :class:`CellSummary` for an evaluation and reference.

    Pure (no I/O). Reuses :func:`substantive_index`, :func:`cohens_kappa`,
    and :func:`fleiss_kappa`; iterates the substantive subset once to
    accumulate the M and reference class counts.

    Parameters
    ----------
    eta
        The evaluation (or the filtered evaluation returned by
        :meth:`MetricsReport.by_tag` / :meth:`MetricsReport.by_rsr_target`).
    reference
        Per-item reference verdict function — typically
        :func:`consensus_reference` for the by-tag/by-rsr-target cells
        the CLI renders, but any :data:`ReferenceFn` works.

    Returns
    -------
    CellSummary
        Frozen summary suitable for rendering or for passing to
        :func:`~infereval.report.collect_negative_findings`.
    """
    substantive = substantive_index(eta, reference)
    m_counts: dict[Verdict, int] = {
        Verdict.GOOD: 0,
        Verdict.BAD: 0,
        Verdict.ABSTAIN: 0,
    }
    r_counts: dict[Verdict, int] = {
        Verdict.GOOD: 0,
        Verdict.BAD: 0,
        Verdict.ABSTAIN: 0,
    }
    for i in substantive:
        m_counts[eta.items[i].model_verdict] += 1
        r_counts[reference(i)] += 1
    return CellSummary(
        n_substantive=len(substantive),
        m_counts=m_counts,
        r_counts=r_counts,
        cohens_kappa=cohens_kappa(eta, reference),
        fleiss_kappa=fleiss_kappa(eta),
    )


# ---- High-level aggregator -----------------------------------------------


@dataclass
class MetricsReport:
    """Bundle of metrics over an :class:`Evaluation`, with decomposition filters.

    Parameters
    ----------
    eta
        The evaluation to report on.
    benchmark
        Optional benchmark. Required for :meth:`by_rsr_target` and
        :meth:`coverage_per_analyst_named`; other methods work without it.
    """

    eta: Evaluation
    benchmark: Benchmark | None = None

    # ---- Coverage ----

    @property
    def n(self) -> int:
        """Number of evaluation items."""
        return self.eta.n

    @property
    def coverage(self) -> float:
        return coverage(self.eta)

    @property
    def coverage_per_analyst(self) -> list[float]:
        return coverage_per_analyst(self.eta)

    def coverage_per_analyst_named(self) -> dict[str, float]:
        """Per-analyst coverage keyed by analyst id (requires :attr:`benchmark`)."""
        if self.benchmark is None:
            raise ValueError(
                "coverage_per_analyst_named requires a benchmark to resolve analyst ids"
            )
        return {
            a.id: coverage_analyst(self.eta, j)
            for j, a in enumerate(self.benchmark.analysts)
        }

    # ---- Kappa ----

    def cohens_kappa(
        self,
        reference: ReferenceFn | None = None,
        *,
        weights: WeightFn | None = None,
    ) -> float | None:
        """:math:`\\kappa_C(\\eta, r)`. Default reference is the analyst consensus :math:`c_i`.

        Pass ``weights=margin_weight`` for the confidence-weighted variant.
        """
        ref = reference if reference is not None else consensus_reference(self.eta)
        return cohens_kappa(self.eta, ref, weights=weights)

    def cohens_kappa_analyst(
        self,
        analyst_index: int,
        *,
        weights: WeightFn | None = None,
    ) -> float | None:
        """:math:`\\kappa_C(\\eta, v_{:,j})`: M vs. one specific analyst."""
        return cohens_kappa(
            self.eta,
            analyst_reference(self.eta, analyst_index),
            weights=weights,
        )

    @property
    def fleiss_kappa(self) -> float | None:
        return fleiss_kappa(self.eta)

    def fleiss_kappa_weighted(self, weights: WeightFn) -> float | None:
        """Weighted :math:`\\kappa_F(\\eta)` — pass :func:`margin_weight` for the standard variant.

        Exposed as a method (not a property) because weighting is an
        opt-in methodological choice that needs to be made explicitly,
        per the locked-default that the unweighted κ remains the
        headline number.
        """
        return fleiss_kappa(self.eta, weights=weights)

    @property
    def inter_analyst_fleiss(self) -> float | None:
        return inter_analyst_fleiss(self.eta)

    # ---- Per-cell summary (decomposition under-powered guard; v0.8.0) ----

    def cell_summary(
        self, reference: ReferenceFn | None = None
    ) -> CellSummary:
        """:class:`CellSummary` for this report against ``reference``.

        Default reference is the analyst consensus :math:`c_i`. Used by
        the ``infereval metrics --by-tag`` / ``--by-rsr-target`` CLI
        renderers and by ``infereval report --by-tag …`` to surface the
        per-cell substantive-n and class counts and to gate the
        under-powered annotation.
        """
        ref = reference if reference is not None else consensus_reference(self.eta)
        return cell_summary(self.eta, ref)

    # ---- Confidence intervals (subsampling, Politis-Romano) ----

    def cohens_kappa_with_ci(
        self,
        reference: ReferenceFn | None = None,
        *,
        iterations: int = 1000,
        subsample_size: int | None = None,
        confidence: float = 0.95,
        seed: int | None = None,
    ) -> tuple[float, float, float]:
        """:math:`\\kappa_C` with a Politis-Romano subsampling CI.

        Convenience wrapper around :func:`subsampling_kappa_ci`. See its
        docstring for the procedure, the subsample-size default, and
        the raises behaviour for too-small benchmarks.
        """
        ref = reference if reference is not None else consensus_reference(self.eta)
        return subsampling_kappa_ci(
            lambda e: cohens_kappa(e, ref),
            self.eta,
            iterations=iterations,
            subsample_size=subsample_size,
            confidence=confidence,
            seed=seed,
        )

    def fleiss_kappa_with_ci(
        self,
        *,
        iterations: int = 1000,
        subsample_size: int | None = None,
        confidence: float = 0.95,
        seed: int | None = None,
    ) -> tuple[float, float, float]:
        """:math:`\\kappa_F` with a Politis-Romano subsampling CI."""
        return subsampling_kappa_ci(
            fleiss_kappa,
            self.eta,
            iterations=iterations,
            subsample_size=subsample_size,
            confidence=confidence,
            seed=seed,
        )

    # ---- Dispersion (per-item and aggregate) ----

    @property
    def verdict_distributions(self) -> dict[str, VerdictDistribution]:
        """Per-item :class:`VerdictDistribution` keyed by item id.

        Always computed (cheap); included in :meth:`to_dict` output so
        downstream consumers can read the dispersion without re-running
        majority-vote logic.
        """
        return {
            item.id: verdict_distribution(item) for item in self.eta.items
        }

    def aggregate_dispersion_summary(
        self, *, thin_margin_threshold: float = 0.4
    ) -> AggregateDispersion:
        """Corpus-level summary of per-item dispersion."""
        dists = list(self.verdict_distributions.values())
        n = len(dists)
        if n == 0:
            return AggregateDispersion(
                n_items=0,
                mean_entropy=0.0,
                mean_margin=0.0,
                n_thin_margin=0,
                thin_margin_threshold=thin_margin_threshold,
                n_tie_broken=0,
            )
        return AggregateDispersion(
            n_items=n,
            mean_entropy=sum(d.entropy for d in dists) / n,
            mean_margin=sum(d.margin for d in dists) / n,
            n_thin_margin=sum(1 for d in dists if d.margin < thin_margin_threshold),
            thin_margin_threshold=thin_margin_threshold,
            n_tie_broken=sum(1 for d in dists if d.tie_broken),
        )

    # ---- Filters ----

    def by_tag(self, tag: str) -> MetricsReport:
        """Return a report restricted to items carrying ``tag``."""
        filtered = self.eta.model_copy(
            update={"items": [it for it in self.eta.items if tag in it.tags]}
        )
        return MetricsReport(eta=filtered, benchmark=self.benchmark)

    def by_rsr_target(self, X: frozenset[str], A: frozenset[str]) -> MetricsReport:
        """Return a report restricted to items whose ``rsr_target`` matches ``(X, A)``.

        ``rsr_target`` lives on benchmark items, not evaluation items, so
        :attr:`benchmark` is required.
        """
        if self.benchmark is None:
            raise ValueError("by_rsr_target requires a benchmark to read rsr_target fields")
        keep_ids = {
            bi.id
            for bi in self.benchmark.items
            if bi.rsr_target is not None
            and frozenset(bi.rsr_target.X) == X
            and frozenset(bi.rsr_target.A) == A
        }
        filtered = self.eta.model_copy(
            update={"items": [it for it in self.eta.items if it.id in keep_ids]}
        )
        return MetricsReport(eta=filtered, benchmark=self.benchmark)

    # ---- Reporting ----

    def to_dict(
        self,
        *,
        include_verdict_distributions: bool = True,
        thin_margin_threshold: float = 0.4,
    ) -> dict[str, Any]:
        """Render as a JSON-friendly dict (None where a kappa is undefined).

        Parameters
        ----------
        include_verdict_distributions
            When ``True`` (default, the ``report_verdict_distribution = true``
            locked methodology default), include per-item
            :class:`VerdictDistribution` entries plus the aggregate
            dispersion summary. Pass ``False`` to suppress for
            consumers that want the pre-dispersion shape exactly.
        thin_margin_threshold
            Plurality-margin cutoff for the aggregate-dispersion
            "thin-margin" count. Default ``0.4`` matches the
            :class:`~infereval.structure.ThinMarginAgreementCheck`
            default.
        """
        out: dict[str, Any] = {
            "n": self.n,
            "coverage": self.coverage,
            "coverage_per_analyst": self.coverage_per_analyst,
            "cohens_kappa_consensus": self.cohens_kappa(),
            "fleiss_kappa": self.fleiss_kappa,
            "inter_analyst_fleiss": self.inter_analyst_fleiss,
        }
        if self.benchmark is not None:
            out["coverage_per_analyst_named"] = self.coverage_per_analyst_named()
        if include_verdict_distributions:
            distributions = self.verdict_distributions
            out["verdict_distributions"] = {
                item_id: {
                    "good": d.good,
                    "bad": d.bad,
                    "abstain": d.abstain,
                    "n_samples": d.n_samples,
                    "verdict": d.verdict.value,
                    "tie_broken": d.tie_broken,
                    "entropy": d.entropy,
                    "margin": d.margin,
                }
                for item_id, d in distributions.items()
            }
            agg = self.aggregate_dispersion_summary(
                thin_margin_threshold=thin_margin_threshold
            )
            out["aggregate_dispersion"] = {
                "n_items": agg.n_items,
                "mean_entropy": agg.mean_entropy,
                "mean_margin": agg.mean_margin,
                "n_thin_margin": agg.n_thin_margin,
                "fraction_thin_margin": agg.fraction_thin_margin,
                "thin_margin_threshold": agg.thin_margin_threshold,
                "n_tie_broken": agg.n_tie_broken,
            }
        return out


__all__ = [
    "MIN_K_FOR_SUBSAMPLING_CI",
    "SUBSTANTIVE",
    "AggregateDispersion",
    "CellSummary",
    "MetricsReport",
    "ReferenceFn",
    "SubsamplingNotApplicableError",
    "VerdictDistribution",
    "WeightFn",
    "analyst_reference",
    "cell_summary",
    "cohens_kappa",
    "consensus_reference",
    "consensus_verdict",
    "coverage",
    "coverage_analyst",
    "coverage_per_analyst",
    "fleiss_kappa",
    "inter_analyst_fleiss",
    "margin_weight",
    "substantive_index",
    "subsampling_kappa_ci",
    "verdict_distribution",
]
