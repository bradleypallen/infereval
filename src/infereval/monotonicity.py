"""Monotonicity scoring for ordinal-ladder items (brief §12.2).

A *monotonicity ladder* walks one ordinal family's tiers (optionally holding a
tier of another family fixed) and asks whether the model's endorsement moves in
the declared direction as the tier rises. The items are the benchmark's
``monotonicity_step`` items (v0.17.0 native field); their verdicts come from an
evaluation :math:`\\eta`.

Scoring rule (this is the crux — the naive "non-decreasing over
{good, bad, abstain}" is undefined because ``abstain`` is not between ``bad`` and
``good``):

- Order **only the substantive verdicts**: ``bad < good``.
- ``abstain`` is a **gap**: skip it. It neither satisfies nor violates
  monotonicity, and is never interpolated to a numeric value.
- Read the substantive subsequence in tier order. A **violation** is a strict
  inversion — for ``non_decreasing``, a later tier scored ``bad`` after an
  earlier ``good`` (symmetrically for ``non_increasing``). A ladder with fewer
  than two substantive steps is *insufficient*, not a pass.

The measurement layer (Definitions 6–10) is untouched; this is an additional,
separately-reported diagnostic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import Verdict

if TYPE_CHECKING:
    from .benchmark import Benchmark
    from .evaluation import Evaluation

__all__ = [
    "LadderStep",
    "MonotonicityResult",
    "score_all_ladders",
    "score_ladder",
]

#: The two substantive verdicts, ordered ``bad < good`` for monotonicity.
_ORDER = {Verdict.BAD: 0, Verdict.GOOD: 1}
_SUBSTANTIVE = frozenset(_ORDER)


@dataclass(frozen=True)
class LadderStep:
    """One tier of a ladder: its item, tier id, 0-based tier index, and verdict."""

    item_id: str
    tier: str
    tier_index: int
    verdict: Verdict


@dataclass(frozen=True)
class MonotonicityResult:
    """The outcome of scoring one monotonicity ladder."""

    ladder: str | None
    family: str
    fixed: str | None
    expected: str  # "non_decreasing" | "non_increasing"
    steps: tuple[LadderStep, ...]
    """All steps, in tier order (ascending ``tier_index``)."""
    violations: tuple[tuple[str, str], ...]
    """``(earlier_item_id, later_item_id)`` pairs that strictly invert."""

    @property
    def substantive(self) -> tuple[LadderStep, ...]:
        """The good/bad steps only, in tier order (abstains dropped)."""
        return tuple(s for s in self.steps if s.verdict in _SUBSTANTIVE)

    @property
    def n_gaps(self) -> int:
        """How many steps were abstains (skipped gaps)."""
        return len(self.steps) - len(self.substantive)

    @property
    def is_monotone(self) -> bool:
        """Whether the substantive subsequence has no strict inversion."""
        return not self.violations

    @property
    def status(self) -> str:
        """``"violated"`` / ``"insufficient"`` / ``"monotone"``.

        ``"insufficient"`` (fewer than two substantive steps) is distinct from a
        pass: there is nothing to verify, so it is not counted as monotone.
        """
        if self.violations:
            return "violated"
        if len(self.substantive) < 2:
            return "insufficient"
        return "monotone"


def _violations(
    substantive: tuple[LadderStep, ...], expected: str
) -> tuple[tuple[str, str], ...]:
    """Adjacent strict inversions in the substantive subsequence.

    Over the totally-ordered substantive values, monotonicity holds iff no
    adjacent pair inverts, so the adjacent pairs are the minimal witness set.
    """
    out: list[tuple[str, str]] = []
    for a, b in zip(substantive, substantive[1:], strict=False):
        va, vb = _ORDER[a.verdict], _ORDER[b.verdict]
        # non_increasing violates when the value rises; non_decreasing when it drops.
        inverted = vb > va if expected == "non_increasing" else vb < va
        if inverted:
            out.append((a.item_id, b.item_id))
    return tuple(out)


def score_all_ladders(eta: Evaluation, benchmark: Benchmark) -> list[MonotonicityResult]:
    """Score every monotonicity ladder in ``benchmark`` against ``eta``.

    Ladders are grouped by ``(ladder, family, fixed)`` — a single monotone walk.
    Items whose id is absent from ``eta`` are skipped.
    """
    verdict_by_id = {it.id: it.model_verdict for it in eta.items}

    groups: dict[tuple[str | None, str, str | None], list[LadderStep]] = defaultdict(list)
    expected_by_key: dict[tuple[str | None, str, str | None], str] = {}
    for item in benchmark.items:
        ms = item.monotonicity_step
        if ms is None or item.id not in verdict_by_id:
            continue
        key = (item.ladder, ms.family, ms.fixed)
        groups[key].append(
            LadderStep(
                item_id=item.id,
                tier=ms.tier,
                tier_index=ms.tier_index,
                verdict=verdict_by_id[item.id],
            )
        )
        expected_by_key.setdefault(key, ms.expected)

    results: list[MonotonicityResult] = []
    for key, steps_list in groups.items():
        ladder, family, fixed = key
        steps = tuple(sorted(steps_list, key=lambda s: s.tier_index))
        substantive = tuple(s for s in steps if s.verdict in _SUBSTANTIVE)
        expected = expected_by_key[key]
        results.append(
            MonotonicityResult(
                ladder=ladder,
                family=family,
                fixed=fixed,
                expected=expected,
                steps=steps,
                violations=_violations(substantive, expected),
            )
        )
    results.sort(key=lambda r: (r.ladder or "", r.family, r.fixed or ""))
    return results


def score_ladder(
    eta: Evaluation, benchmark: Benchmark, ladder: str
) -> MonotonicityResult | None:
    """Score a single ladder by its ``ladder`` id, or ``None`` if there is none."""
    for result in score_all_ladders(eta, benchmark):
        if result.ladder == ladder:
            return result
    return None
