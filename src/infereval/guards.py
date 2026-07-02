"""Validity guards (generalization brief §8, §12.7).

Domain-independent *validity instruments* run per domain. Their machinery is
shared; their results are domain-specific (a divergence in one domain says
nothing about another).

- :func:`distribution_agreement` — the shared gate: two evaluations of the same
  items must agree, per item, within a total-variation tolerance, at a sample
  floor. Built on :func:`infereval.comparison.compare_runs`.
- :func:`template_equivalence` — render a domain's sequents under two templates
  to the same respondents; the core verdict distributions must agree (§8). If
  they diverge the template is doing semantic work and comparability within the
  domain is broken — fix the template before shipping it. Make it a CI gate on
  any new template.
- :func:`shuffle_invariance` — the same Γ with its bearers shuffled must yield
  the same verdict (§12.7). Uses the same gate; the shuffled run is produced with
  an order-permuting premise context builder (a plugin context builder), so no
  new rendering path is needed.

Default tolerance: per-item TV distance below **0.10** with **≥ 30** substantive
samples per item. Without a threshold the gate is ceremony; with it, a template
that shifts verdicts fails CI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .comparison import compare_runs
from .metrics import verdict_distribution

if TYPE_CHECKING:
    from .evaluation import Evaluation

__all__ = [
    "AgreementResult",
    "distribution_agreement",
    "shuffle_invariance",
    "template_equivalence",
]

_DEFAULT_TV_THRESHOLD = 0.10
_DEFAULT_N_FLOOR = 30


@dataclass(frozen=True)
class AgreementResult:
    """Outcome of a distribution-agreement gate."""

    passed: bool
    threshold: float
    n_floor: int
    max_tv: float
    offenders: tuple[tuple[str, float], ...] = field(default_factory=tuple)
    """``(item_id, tv)`` pairs whose TV distance met or exceeded the threshold."""
    under_powered: tuple[str, ...] = field(default_factory=tuple)
    """Item ids with fewer than ``n_floor`` substantive samples in either run."""

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"{status}: max TV={self.max_tv:.3f} (threshold {self.threshold}), "
            f"{len(self.offenders)} over threshold, "
            f"{len(self.under_powered)} under-powered (n<{self.n_floor})"
        )


def _substantive_n(eta: Evaluation, item_id: str) -> int:
    item = next((it for it in eta.items if it.id == item_id), None)
    if item is None:
        return 0
    dist = verdict_distribution(item)
    return dist.good + dist.bad + dist.abstain


def distribution_agreement(
    eta_a: Evaluation,
    eta_b: Evaluation,
    *,
    threshold: float = _DEFAULT_TV_THRESHOLD,
    n_floor: int = _DEFAULT_N_FLOOR,
    require_same_setup: bool = True,
) -> AgreementResult:
    """Gate: every item's cross-run TV distance is below ``threshold`` at ``n_floor``.

    ``require_same_setup`` guards the §12.1 confound (same model snapshot +
    sampler config); the two runs are expected to differ only in the axis under
    test (template, or premise order).
    """
    cmp = compare_runs(eta_a, eta_b, require_same_setup=require_same_setup)
    offenders = tuple(
        sorted(
            ((k, v) for k, v in cmp.per_item_tv.items() if v >= threshold),
            key=lambda kv: -kv[1],
        )
    )
    under = tuple(
        it.id
        for it in eta_a.items
        if _substantive_n(eta_a, it.id) < n_floor
        or _substantive_n(eta_b, it.id) < n_floor
    )
    max_tv = max(cmp.per_item_tv.values(), default=0.0)
    return AgreementResult(
        passed=not offenders and not under,
        threshold=threshold,
        n_floor=n_floor,
        max_tv=max_tv,
        offenders=offenders,
        under_powered=under,
    )


def template_equivalence(
    eta_template_a: Evaluation,
    eta_template_b: Evaluation,
    *,
    threshold: float = _DEFAULT_TV_THRESHOLD,
    n_floor: int = _DEFAULT_N_FLOOR,
) -> AgreementResult:
    """§8 gate: two templates over the same items + model must agree within noise."""
    return distribution_agreement(
        eta_template_a,
        eta_template_b,
        threshold=threshold,
        n_floor=n_floor,
        require_same_setup=True,
    )


def shuffle_invariance(
    eta_ordered: Evaluation,
    eta_shuffled: Evaluation,
    *,
    threshold: float = _DEFAULT_TV_THRESHOLD,
    n_floor: int = _DEFAULT_N_FLOOR,
) -> AgreementResult:
    """§12.7 gate: shuffling premise order must not move the verdict.

    ``eta_shuffled`` is produced by evaluating the same benchmark with a premise
    context builder that permutes bearer order (a plugin context builder); the
    inferential content is identical, so the verdict distributions must agree.
    """
    return distribution_agreement(
        eta_ordered,
        eta_shuffled,
        threshold=threshold,
        n_floor=n_floor,
        require_same_setup=True,
    )
