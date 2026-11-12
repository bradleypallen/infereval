"""Structural coherence checks against the derived implication frame ⟨B, I_M⟩.

Phase 2.1 of the construct-validity infrastructure (per *Closing the
Construct-Validity Gap in infereval*). Addresses **R13** (structural
coherence check on the derived frame) — the philosophically central
addition that moves the framework from "supporting agreement
measurement" to "supporting mastery characterization in the
inferentialist sense" (Hlobil & Brandom 2025; Brandom 1994).

The Hlobil–Brandom framework treats a handful of structural properties
as constitutive of inferential mastery. The framework guarantees one of
them by construction (**containment closure**, clause i of :math:`I_M` membership);
the others have to be *checked against the evaluation outcome*. This
module implements those checks as first-class operations so that
aggregate agreement statistics aren't conflated with structural mastery.

Three checks ship in this module:

- :func:`containment_closure_check` — sanity check that all
  self-implications (items where ``Γ ∩ Δ ≠ ∅``) are in ``I_M`` by
  construction.
- :func:`rsr_role_consistency_check` — for items carrying a role tag
  (``supporter`` / ``defeater`` / ``irrelevant-addition``) and an
  ``rsr_target``, compare the model's verdict against the verdict the
  role *predicts* given the base-inference verdict on the same target.
- :func:`base_case_stability_check` — when an ``rsr_target`` has
  multiple base-inference items, the model should give the same verdict
  on all of them.

Each check returns a :class:`StructuralCheck` dataclass with a count of
items checked, items satisfying the property, a list of anomalies, and
a derived rate. :func:`run_all_checks` returns a
:class:`StructuralReport` bundling the three.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .types import Verdict

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .benchmark import Benchmark, BenchmarkItem
    from .evaluation import Evaluation


# ---- Role / tag conventions ------------------------------------------------

# Tags the framework recognises as inferential roles relative to a target.
# Items lacking any of these are excluded from the RSR role-consistency
# check (the framework can't predict their expected verdict from role alone).
_ROLE_SUPPORTER = "supporter"
_ROLE_DEFEATER = "defeater"
_ROLE_IRRELEVANT = "irrelevant-addition"
_ROLE_BASE = "base-inference"

_RECOGNISED_ROLES = frozenset({
    _ROLE_SUPPORTER,
    _ROLE_DEFEATER,
    _ROLE_IRRELEVANT,
    _ROLE_BASE,
})


def _role_of(item: BenchmarkItem) -> str | None:
    """Return the first recognised role tag on ``item``, or ``None``."""
    for tag in item.tags:
        if tag in _RECOGNISED_ROLES:
            return tag
    return None


# ---- Data classes ----------------------------------------------------------


@dataclass(frozen=True)
class StructuralAnomaly:
    """One item that failed a structural check, with diagnostic context."""

    item_id: str
    expected: str
    """Human-readable description of what the structural rule predicted."""
    actual: str
    """What the model's verdict actually was."""
    explanation: str
    """Why this is flagged as an anomaly."""


@dataclass(frozen=True)
class StructuralCheck:
    """Result of one structural property check against an Evaluation."""

    name: str
    """Short identifier, e.g. ``"containment_closure"``."""
    items_checked: int
    items_satisfying: int
    anomalies: tuple[StructuralAnomaly, ...] = ()

    @property
    def rate(self) -> float | None:
        """Proportion of checked items satisfying the property; ``None`` when no items checked."""
        if self.items_checked == 0:
            return None
        return self.items_satisfying / self.items_checked


@dataclass(frozen=True)
class StructuralReport:
    """Bundle of structural checks run against an Evaluation + Benchmark pair."""

    evaluation_id: str
    benchmark_id: str
    checks: tuple[StructuralCheck, ...] = field(default_factory=tuple)

    @property
    def all_satisfied(self) -> bool:
        """True iff every check has rate == 1.0 (and no anomalies)."""
        return all(
            (c.rate is None or c.rate == 1.0) and not c.anomalies
            for c in self.checks
        )

    @property
    def total_anomalies(self) -> int:
        return sum(len(c.anomalies) for c in self.checks)


# ---- The three checks ------------------------------------------------------


def containment_closure_check(
    evaluation: Evaluation, benchmark: Benchmark
) -> StructuralCheck:
    """Sanity-check that all self-implications are in ``I_M`` by construction.

    By clause i of :math:`I_M` membership, every implication ⟨Γ, Δ⟩ with
    ``Γ ∩ Δ ≠ ∅`` is in ``I_M`` regardless of what the model says.
    This check counts such items in the benchmark and confirms they're
    structurally satisfied; it doesn't *need* to consult the model's
    verdict (the framework guarantees it). Reported anyway because the
    count itself is informative — a benchmark with zero self-implications
    has different structural texture from one with many.
    """
    self_implications = [
        it
        for it in benchmark.items
        if set(it.premises) & set(it.conclusions)
    ]
    # Per construction, every such item is in I_M; rate is trivially 1.0
    # whenever items_checked > 0. We report the count for visibility.
    return StructuralCheck(
        name="containment_closure",
        items_checked=len(self_implications),
        items_satisfying=len(self_implications),
        anomalies=(),
    )


def rsr_role_consistency_check(
    evaluation: Evaluation, benchmark: Benchmark
) -> StructuralCheck:
    """Check that role-tagged items' model verdicts match the role's prediction.

    For each item carrying a role tag (``supporter`` / ``defeater`` /
    ``irrelevant-addition``) AND an ``rsr_target``, looks up the
    "base-inference" item with the same target and uses the model's
    verdict on the base to predict the expected verdict on the role-tagged
    item:

    - ``supporter`` is supposed to *strengthen* the base verdict. If the
      base is GOOD, the supporter should remain GOOD; if the base is
      BAD, the supporter is excluded (a supporter can't strengthen a
      bad inference — that's a defeater being treated wrongly).
    - ``defeater`` is supposed to *flip* the base verdict. If the base
      is GOOD, the defeater should be BAD.
    - ``irrelevant-addition`` is supposed to preserve the base verdict
      under RSR. If the base is GOOD, the irrelevant addition should
      stay GOOD; if the base is BAD, it should stay BAD.

    Anomalies are items whose model verdict contradicts the expected
    role-conditional verdict. Items where the base or the role-tagged
    item itself has an ABSTAIN verdict are excluded from the check
    (the role's prediction is undefined relative to abstention).
    """
    # Index items by id, evaluation-side and benchmark-side.
    eval_by_id = {it.id: it for it in evaluation.items}

    # Group benchmark items by their rsr_target's canonical key, then
    # within each target separate the base-inference reference items
    # from the role-tagged items we're going to check.
    targets: dict[
        tuple[tuple[str, ...], tuple[str, ...]],
        dict[str, list[BenchmarkItem]],
    ] = defaultdict(lambda: {"base": [], "checked": []})

    for it in benchmark.items:
        if it.rsr_target is None:
            continue
        key = (
            tuple(sorted(it.rsr_target.X)),
            tuple(sorted(it.rsr_target.A)),
        )
        role = _role_of(it)
        if role == _ROLE_BASE:
            targets[key]["base"].append(it)
        elif role in {_ROLE_SUPPORTER, _ROLE_DEFEATER, _ROLE_IRRELEVANT}:
            targets[key]["checked"].append(it)

    anomalies: list[StructuralAnomaly] = []
    items_checked = 0
    items_satisfying = 0

    for key, groups in targets.items():
        base_items = groups["base"]
        checked_items = groups["checked"]
        if not base_items or not checked_items:
            # Need a base reference and at least one role-tagged item
            # to run the check on this target.
            continue

        # If multiple base items exist, use their majority verdict (or
        # skip when they disagree — the base_case_stability_check
        # surfaces the divergence separately).
        # Partial-evaluation guard: a benchmark item carrying an
        # rsr_target may not appear in this evaluation (e.g. when the
        # eval was produced from a paraphrase-cycle variant or a tag
        # filter). Skip those items rather than raise; the metrics
        # contract elsewhere in the package is "missing data is
        # surfaced via warnings + None, not exceptions".
        present_base_items = [b for b in base_items if b.id in eval_by_id]
        if len(present_base_items) < len(base_items):
            missing = [b.id for b in base_items if b.id not in eval_by_id]
            log.warning(
                "rsr_role_consistency_check: skipping base items absent from "
                "evaluation %r: %s",
                evaluation.id,
                missing,
            )
        if not present_base_items:
            continue
        base_verdicts = [eval_by_id[b.id].model_verdict for b in present_base_items]
        if len(set(base_verdicts)) > 1:
            continue  # base is unstable; can't predict roles
        base_verdict = base_verdicts[0]
        if base_verdict == Verdict.ABSTAIN:
            # Base is non-substantive; role predictions are undefined.
            continue

        for it in checked_items:
            if it.id not in eval_by_id:
                log.warning(
                    "rsr_role_consistency_check: skipping role-tagged item "
                    "%r absent from evaluation %r",
                    it.id,
                    evaluation.id,
                )
                continue
            eval_item = eval_by_id[it.id]
            actual = eval_item.model_verdict
            if actual == Verdict.ABSTAIN:
                # The role-tagged item itself is non-substantive; skip.
                continue
            role = _role_of(it)
            assert role is not None  # checked above
            expected = _expected_verdict_for_role(role, base_verdict)
            if expected is None:
                continue  # role doesn't make a prediction here
            items_checked += 1
            if actual == expected:
                items_satisfying += 1
            else:
                target_str = (
                    f"⟨{{{','.join(key[0])}}}, {{{','.join(key[1])}}}⟩"
                )
                anomalies.append(
                    StructuralAnomaly(
                        item_id=it.id,
                        expected=str(expected),
                        actual=str(actual),
                        explanation=(
                            f"item is tagged '{role}' on target {target_str} "
                            f"with base verdict {base_verdict}; role predicts "
                            f"{expected} but model returned {actual}"
                        ),
                    )
                )

    return StructuralCheck(
        name="rsr_role_consistency",
        items_checked=items_checked,
        items_satisfying=items_satisfying,
        anomalies=tuple(anomalies),
    )


def _expected_verdict_for_role(role: str, base_verdict: Verdict) -> Verdict | None:
    """Predict the role-tagged item's verdict given the base verdict.

    Returns ``None`` when the role doesn't make a prediction at all
    (e.g. ``supporter`` against a BAD base — supporting a bad inference
    is conceptually incoherent and we treat the item as out-of-scope).
    """
    if role == _ROLE_SUPPORTER:
        # Strengthening only makes sense when base is GOOD.
        return Verdict.GOOD if base_verdict == Verdict.GOOD else None
    if role == _ROLE_DEFEATER:
        # Defeating means flipping good to bad. If base is already BAD,
        # the defeater is structurally redundant; skip.
        return Verdict.BAD if base_verdict == Verdict.GOOD else None
    if role == _ROLE_IRRELEVANT:
        # RSR: irrelevant addition preserves the base verdict.
        return base_verdict
    return None


def base_case_stability_check(
    evaluation: Evaluation, benchmark: Benchmark
) -> StructuralCheck:
    """When a target has multiple ``base-inference`` items, the model should agree on all of them.

    Anomalies surface targets where the model gives different verdicts
    on multiple base-inference items, since the base verdict is what
    the rest of the RSR machinery is anchored to.
    """
    eval_by_id = {it.id: it for it in evaluation.items}
    base_by_target: dict[
        tuple[tuple[str, ...], tuple[str, ...]], list[BenchmarkItem]
    ] = defaultdict(list)

    for it in benchmark.items:
        if it.rsr_target is None or _role_of(it) != _ROLE_BASE:
            continue
        key = (
            tuple(sorted(it.rsr_target.X)),
            tuple(sorted(it.rsr_target.A)),
        )
        base_by_target[key].append(it)

    anomalies: list[StructuralAnomaly] = []
    items_checked = 0
    items_satisfying = 0
    for key, bases in base_by_target.items():
        # Partial-evaluation guard: same as in rsr_role_consistency_check.
        present_bases = [b for b in bases if b.id in eval_by_id]
        if len(present_bases) < len(bases):
            missing = [b.id for b in bases if b.id not in eval_by_id]
            log.warning(
                "base_case_stability_check: skipping base items absent from "
                "evaluation %r: %s",
                evaluation.id,
                missing,
            )
        if len(present_bases) < 2:
            continue  # nothing to check (need ≥ 2 present bases per target)
        verdicts = [eval_by_id[b.id].model_verdict for b in present_bases]
        unique = set(verdicts)
        items_checked += len(present_bases)
        if len(unique) == 1:
            items_satisfying += len(present_bases)
        else:
            target_str = (
                f"⟨{{{','.join(key[0])}}}, {{{','.join(key[1])}}}⟩"
            )
            # Flag every present base item in the divergent set as an anomaly.
            for b, v in zip(present_bases, verdicts, strict=True):
                anomalies.append(
                    StructuralAnomaly(
                        item_id=b.id,
                        expected=f"a single shared verdict across base-inferences on {target_str}",
                        actual=f"{v} (other base items on this target: {unique - {v}})",
                        explanation=(
                            f"target {target_str} has {len(present_bases)} base-inference "
                            f"items present in the evaluation with verdicts "
                            f"{[str(v) for v in verdicts]} — the base case is "
                            f"structurally unstable"
                        ),
                    )
                )

    return StructuralCheck(
        name="base_case_stability",
        items_checked=items_checked,
        items_satisfying=items_satisfying,
        anomalies=tuple(anomalies),
    )


#: Default plurality-margin cutoff below which a model-vs-analyst agreement
#: is considered "thin" — i.e. the agreement could plausibly flip on a
#: re-run because the model's sample distribution was not decisive.
#: ``0.4`` catches ``3/5`` agreements (margin ``0.2`` over the runner-up)
#: as thin while letting ``4/5`` (margin ``0.6``) through as confident.
DEFAULT_THIN_MARGIN_THRESHOLD: float = 0.4


def thin_margin_agreement_check(
    evaluation: Evaluation,
    benchmark: Benchmark | None = None,  # noqa: ARG001 - parity with other checks
    *,
    threshold: float = DEFAULT_THIN_MARGIN_THRESHOLD,
) -> StructuralCheck:
    """Flag analyst-model agreements with thin sample-margin support.

    Within-run companion to the across-run :func:`infereval.retest.compute_retest`
    check. Surfaces items where the model's verdict agrees with analyst
    consensus *but* the agreement is supported by a thin majority over
    the sampled verdicts (e.g. ``3/5`` good with ``2`` abstain). Such
    agreements are vulnerable to flipping on a re-run, and counting
    them the same as ``5/5`` agreements in the headline κ inflates the
    apparent reliability of the measurement.

    Universe of checked items: those where the model verdict is
    substantive (``good`` / ``bad``), the analyst consensus is
    substantive, and the two agree. Items where the model and analysts
    disagree are not relevant to this check (a thin disagreement is
    handled by the across-run test-retest comparator, not here).

    Parameters
    ----------
    evaluation
        The evaluation to check.
    benchmark
        Unused; accepted for API parity with the other structural
        checks (and so that :func:`run_all_checks` can dispatch
        uniformly).
    threshold
        Plurality-margin cutoff (default :data:`DEFAULT_THIN_MARGIN_THRESHOLD`).
        An agreement counts as thin when ``verdict_distribution(item).margin
        < threshold``.
    """
    # Local imports to avoid a metrics<->structure cycle at import time.
    from .metrics import (
        SUBSTANTIVE,
        consensus_verdict,
        verdict_distribution,
    )

    items_checked = 0
    items_satisfying = 0
    anomalies: list[StructuralAnomaly] = []
    for it in evaluation.items:
        consensus = consensus_verdict(it.analyst_verdicts)
        if it.model_verdict not in SUBSTANTIVE or consensus not in SUBSTANTIVE:
            continue
        if it.model_verdict != consensus:
            continue  # disagreement — not in this check's universe
        items_checked += 1
        dist = verdict_distribution(it)
        if dist.margin >= threshold:
            items_satisfying += 1
        else:
            anomalies.append(
                StructuralAnomaly(
                    item_id=it.id,
                    expected=f"agreement margin ≥ {threshold:.2f}",
                    actual=(
                        f"margin = {dist.margin:.2f} "
                        f"(good={dist.good}, bad={dist.bad}, abstain={dist.abstain}"
                        f"{', tie-broken' if dist.tie_broken else ''})"
                    ),
                    explanation=(
                        f"model agrees with analyst consensus ({consensus}) "
                        f"but the sampled majority is thin; this agreement "
                        f"could flip on a re-run"
                    ),
                )
            )

    return StructuralCheck(
        name="thin_margin_agreement",
        items_checked=items_checked,
        items_satisfying=items_satisfying,
        anomalies=tuple(anomalies),
    )


def run_all_checks(
    evaluation: Evaluation,
    benchmark: Benchmark,
    *,
    thin_margin_threshold: float = DEFAULT_THIN_MARGIN_THRESHOLD,
) -> StructuralReport:
    """Run all four structural checks and bundle the results."""
    return StructuralReport(
        evaluation_id=evaluation.id,
        benchmark_id=evaluation.benchmark_id,
        checks=(
            containment_closure_check(evaluation, benchmark),
            rsr_role_consistency_check(evaluation, benchmark),
            base_case_stability_check(evaluation, benchmark),
            thin_margin_agreement_check(
                evaluation, benchmark, threshold=thin_margin_threshold
            ),
        ),
    )


__all__ = [
    "DEFAULT_THIN_MARGIN_THRESHOLD",
    "StructuralAnomaly",
    "StructuralCheck",
    "StructuralReport",
    "base_case_stability_check",
    "containment_closure_check",
    "rsr_role_consistency_check",
    "run_all_checks",
    "thin_margin_agreement_check",
]
