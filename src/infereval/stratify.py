"""Reporting stratification over native item metadata (brief §7).

Decompositions the shape-blind measurement layer (Definitions 6–10) does not
provide, because they read structure the κ core deliberately ignores:

- :func:`variation_breakdown` — group by the item's variation typology
  (``base`` / ``strengthen`` / ``contested`` / ``defeat`` / ``abstain_anchor``
  / ``monotonicity_step``), reporting the model-verdict mix and coverage per
  role. Joins an evaluation with its benchmark on item id.
- :func:`arity_partition` — group items by succedent arity: ``exclusivity``
  (``|Δ| = 0``, incompatibility), ``single`` (``|Δ| = 1``, the classic case),
  and ``exhaustivity`` (``|Δ| ≥ 2``, disjunctive). §7 requires exclusivity and
  exhaustivity items to be reported separately so near-analytic exhaustivity
  wins cannot inflate a "respects the partition" number. In the single-succedent
  fragment every item is ``single``; the partition becomes load-bearing once the
  compiler-emitted / multi-succedent items land.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import Verdict

if TYPE_CHECKING:
    from .benchmark import Benchmark
    from .evaluation import Evaluation

__all__ = ["VariationCell", "arity_partition", "variation_breakdown"]


@dataclass(frozen=True)
class VariationCell:
    """Per-variation model-verdict summary."""

    variation: str
    n: int
    good: int
    bad: int
    abstain: int

    @property
    def coverage(self) -> float:
        """Fraction of items on which the model returned a substantive verdict."""
        return 0.0 if self.n == 0 else (self.good + self.bad) / self.n


def variation_breakdown(eta: Evaluation, benchmark: Benchmark) -> list[VariationCell]:
    """Model-verdict mix per variation type, joined on item id.

    Items whose benchmark ``variation`` is unset are grouped under
    ``"unspecified"``. Returned in a stable order (declared typology first, then
    any extras alphabetically).
    """
    variation_by_id = {item.id: item.variation for item in benchmark.items}
    counts: dict[str, dict[Verdict, int]] = defaultdict(
        lambda: {Verdict.GOOD: 0, Verdict.BAD: 0, Verdict.ABSTAIN: 0}
    )
    for item in eta.items:
        variation = variation_by_id.get(item.id) or "unspecified"
        counts[variation][item.model_verdict] += 1

    order = [
        "base",
        "strengthen",
        "contested",
        "defeat",
        "abstain_anchor",
        "monotonicity_step",
    ]
    ordered_keys = [k for k in order if k in counts] + sorted(
        k for k in counts if k not in order
    )
    return [
        VariationCell(
            variation=k,
            n=sum(counts[k].values()),
            good=counts[k][Verdict.GOOD],
            bad=counts[k][Verdict.BAD],
            abstain=counts[k][Verdict.ABSTAIN],
        )
        for k in ordered_keys
    ]


def arity_partition(eta: Evaluation) -> dict[str, list[str]]:
    """Partition item ids by succedent arity: exclusivity / single / exhaustivity."""
    out: dict[str, list[str]] = {"exclusivity": [], "single": [], "exhaustivity": []}
    for item in eta.items:
        k = len(item.conclusions)
        bucket = "exclusivity" if k == 0 else "single" if k == 1 else "exhaustivity"
        out[bucket].append(item.id)
    return out
