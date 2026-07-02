"""Cross-run comparison for the question-form / rendering evaluation (brief §10.1).

Compares two evaluations of the *same items* produced under different
configurations (e.g. R0 support/plain vs R1 coherence/plain, or R1 vs R2
plain/domain). Reports, per the brief:

- per-item **total-variation distance** between the two runs' sample verdict
  distributions (good/bad/abstain), and its mean;
- a **cross-run κ** treating the two runs as two annotators (reuse Cohen's κ,
  Definition 9), computed **only over items substantive in both** runs
  (Definition 7); and
- a **coverage floor** (§12.4): when the both-substantive intersection is too
  small a fraction of the items, κ is reported as *insufficient overlap* rather
  than as a low-N number.

The comparison is only valid when the two runs share sampler config + model
snapshot (§12.1); :func:`compare_runs` asserts the setup-conformance fields that
:class:`~infereval.evaluation.Evaluation` records match, unless
``require_same_setup=False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .metrics import cohens_kappa, substantive_index, verdict_distribution
from .types import Verdict

if TYPE_CHECKING:
    from .evaluation import Evaluation

__all__ = ["RunComparison", "compare_runs", "total_variation_distance"]

_DEFAULT_COVERAGE_FLOOR = 0.5


def total_variation_distance(a: dict[Verdict, float], b: dict[Verdict, float]) -> float:
    """TV distance between two verdict distributions: ``0.5 · Σ|a_v − b_v|``."""
    return 0.5 * sum(
        abs(a.get(v, 0.0) - b.get(v, 0.0)) for v in Verdict
    )


def _distribution(eta: Evaluation, item_id: str) -> dict[Verdict, float]:
    """Sample verdict distribution (fractions) for one item, provider errors skipped."""
    item = next((it for it in eta.items if it.id == item_id), None)
    if item is None:
        return {}
    dist = verdict_distribution(item)
    total = dist.good + dist.bad + dist.abstain
    if total == 0:
        return {}
    return {
        Verdict.GOOD: dist.good / total,
        Verdict.BAD: dist.bad / total,
        Verdict.ABSTAIN: dist.abstain / total,
    }


@dataclass(frozen=True)
class RunComparison:
    """The result of comparing two same-item evaluations."""

    run_a: str
    run_b: str
    n_items: int
    n_both_substantive: int
    coverage_a: float
    coverage_b: float
    cross_run_kappa: float | None
    mean_tv_distance: float
    per_item_tv: dict[str, float] = field(default_factory=dict, repr=False)
    insufficient_overlap: bool = False

    @property
    def intersection_fraction(self) -> float:
        return 0.0 if self.n_items == 0 else self.n_both_substantive / self.n_items


def compare_runs(
    eta_a: Evaluation,
    eta_b: Evaluation,
    *,
    coverage_floor: float = _DEFAULT_COVERAGE_FLOOR,
    require_same_setup: bool = True,
) -> RunComparison:
    """Compare two evaluations of the same items (brief §10.1).

    ``eta_a`` drives item order; every item id in ``eta_a`` must appear in
    ``eta_b``. When ``require_same_setup`` (default), the two runs' model
    snapshot and sampler config must match (§12.1) or a ``ValueError`` is raised.
    """
    verdict_b = {it.id: it.model_verdict for it in eta_b.items}
    missing = [it.id for it in eta_a.items if it.id not in verdict_b]
    if missing:
        raise ValueError(
            f"eta_b is missing {len(missing)} item(s) present in eta_a: {missing[:5]}"
        )

    if require_same_setup:
        _assert_same_setup(eta_a, eta_b)

    # Per-item TV distance over the sample distributions.
    per_item_tv: dict[str, float] = {}
    for item in eta_a.items:
        per_item_tv[item.id] = total_variation_distance(
            _distribution(eta_a, item.id), _distribution(eta_b, item.id)
        )
    mean_tv = (
        sum(per_item_tv.values()) / len(per_item_tv) if per_item_tv else 0.0
    )

    # Cross-run κ: treat run B's model verdict as the reference for run A,
    # restricted to items substantive in both runs (Definition 7).
    def _ref(i: int) -> Verdict:
        return verdict_b[eta_a.items[i].id]

    both = substantive_index(eta_a, _ref)
    n_items = len(eta_a.items)
    intersection_fraction = 0.0 if n_items == 0 else len(both) / n_items
    insufficient = intersection_fraction < coverage_floor

    kappa = None if insufficient else cohens_kappa(eta_a, _ref)

    return RunComparison(
        run_a=eta_a.id,
        run_b=eta_b.id,
        n_items=n_items,
        n_both_substantive=len(both),
        coverage_a=_coverage(eta_a),
        coverage_b=_coverage(eta_b),
        cross_run_kappa=kappa,
        mean_tv_distance=mean_tv,
        per_item_tv=per_item_tv,
        insufficient_overlap=insufficient,
    )


def _coverage(eta: Evaluation) -> float:
    n = len(eta.items)
    if n == 0:
        return 0.0
    substantive = sum(1 for it in eta.items if it.model_verdict != Verdict.ABSTAIN)
    return substantive / n


def _assert_same_setup(eta_a: Evaluation, eta_b: Evaluation) -> None:
    """Guard the §12.1 confound: identical model snapshot + sampler config."""
    a_model, b_model = eta_a.model, eta_b.model
    if (a_model.provider, a_model.model_id) != (b_model.provider, b_model.model_id):
        raise ValueError(
            f"cross-run comparison requires the same model; got "
            f"{a_model.provider}:{a_model.model_id} vs {b_model.provider}:{b_model.model_id}. "
            f"Pass require_same_setup=False to override."
        )
    if a_model.params != b_model.params:
        raise ValueError(
            "cross-run comparison requires identical sampler config (temperature / "
            "max_tokens / seed / top_p); the two runs differ. "
            "Pass require_same_setup=False to override."
        )
