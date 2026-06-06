"""Construct-validity report — the most opinionated extension in the series.

Phase 3.1 of the construct-validity infrastructure (per *Closing the
Construct-Validity Gap in infereval*). Closes R16 (mastery sense),
R17 (scope), R18 (constitution vs. evidence), R19 (carving-indexed
framing), and R20 (disclosure of analyst-supplied choices).

The asymmetry this module embodies: **cheap to write up correctly,
expensive to write up incorrectly**. The slot structure makes it
impossible to publish a "mastery established" summary verdict without
the corresponding analyst declarations and competing-explanation
checks. The framework refuses to render the strong-form header
without the supporting evidence; the analyst is welcome to publish
weak claims with the appropriate hedge but cannot publish them with
the unmarked banner.

The report integrates a fixed set of *analyst declarations* (the
:class:`ConstructValidityClaims` model) with auto-collected evidence
from optional Phase 2 artifacts (structural-coherence report, sweep
summary, factor-effects model fit). The summary verdict is computed
deterministically against the claims + evidence, not by the analyst.

The output is structured Markdown — readable as text, version-
controllable, and viewable as a rendered page.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .benchmark import Benchmark
    from .evaluation import Evaluation


# ---- Claims schema --------------------------------------------------------


class MasterySenseClaim(BaseModel):
    """R16: which sense of mastery the claim is about."""

    model_config = ConfigDict(extra="forbid")

    sense: Literal["evaluative", "generative", "standing", "combination"]
    """- ``evaluative``: endorsements-when-asked (the methodology's direct measurement).
    - ``generative``: inferential behavior in unprompted production.
    - ``standing``: a dispositional competence underlying both.
    - ``combination``: a mix; describe explicitly in ``description``."""
    description: str
    """One to three sentences, the analyst's own articulation."""


class ScopeClaim(BaseModel):
    """R17: scope the mastery claim applies over."""

    model_config = ConfigDict(extra="forbid")

    scope: Literal["items_in_benchmark", "domain_D_as_sampled", "general_capacity"]
    """- ``items_in_benchmark``: the claim is about the specific items in β.
    - ``domain_D_as_sampled``: the claim generalises to D as sampled by β.
    - ``general_capacity``: the claim is about inferential mastery as a general capacity."""
    justification: str
    """Why this scope is appropriate given β and the methodology used."""


class ConstitutionClaim(BaseModel):
    """R18: is agreement *evidence of* mastery or *constitutive of* it?"""

    model_config = ConfigDict(extra="forbid")

    position: Literal["evidence_of_mastery", "constitutive_of_mastery"]
    """- ``evidence_of_mastery``: agreement is evidence for a deeper underlying property.
    - ``constitutive_of_mastery``: agreement (with structural coherence) IS mastery (Brandom's structural-behavioural characterisation)."""
    justification: str
    """Brief explanation of the position taken and why."""


class CarvingClaim(BaseModel):
    """R19: carving-indexed framing of in-principle claims."""

    model_config = ConfigDict(extra="forbid")

    acknowledges_carving_indexed: bool
    """``True`` iff any in-principle claims are framed in the
    carving-indexed form Remark 10 specifies."""
    notes: str = ""
    """Required when ``acknowledges_carving_indexed`` is ``True``;
    document the carving used or pointers to the discussion."""


class IdentityCriterion(BaseModel):
    """R22, second leg: analyst-declared individuation criterion for reliability claims.

    Hlobil's individuation point: reliability is by definition agreement
    of distinct measurements of *the same individual*, so an identity
    criterion has to be declared *before* a test-retest κ can be
    interpreted. This object records that declaration in the same
    commitment-and-relativity pattern the framework already uses for
    ``carving`` (R19), ``scope`` (R17), ``mastery_sense`` (R16), and
    ``constitution`` (R18).

    Per-field booleans split into two groups:

    - **Framework-substantiated** (top group): the framework
      mechanically verifies these via the parity check on
      ``infereval retest``. The analyst asserts them; if the supplied
      evaluation artifacts don't conform,
      :class:`infereval.retest.RetestConfigMismatchError` fires.
    - **Analyst-substantiated** (middle group): the framework records
      these as commitments but cannot mechanically verify them. Same
      shape as the leakage-audit-gap handling for R8 / R9 — the
      ``unverifiable_caveats`` text is where the analyst documents
      what they're committing to without framework backup.

    The ``rationale`` field documents *why* these are the right
    individuation choices for the evaluation at hand, parallel to
    :attr:`ScopeClaim.justification` and
    :attr:`ConstitutionClaim.justification`.
    """

    model_config = ConfigDict(extra="forbid")

    # Framework-substantiated (the setup-conformance portion the parity
    # check actually covers — these were what v0.6.0 was implicitly
    # asserting):
    same_benchmark_hash: bool = True
    """Asserts that the two evaluations were against the same benchmark
    hash. Framework verifies via :func:`infereval.retest._check_compatibility`."""
    same_endorsement_config: bool = True
    """Asserts that the two evaluations used the same ``EndorsementConfig``
    (n_samples, tie_break). Framework verifies."""
    same_paraphrase_variant: bool = True
    """Asserts that the two evaluations used the same paraphrase
    variant. Framework verifies."""

    # Analyst-substantiated (the parts beyond setup conformance — these
    # are what v0.6.0 silently presupposed without recording):
    same_provider_model_id: bool
    """Asserts that the provider + model_id is the same in both runs.
    The evaluation JSON records this metadata; the framework can spot a
    bare mismatch (e.g. ``openai/gpt-5.5`` vs. ``openai/gpt-5.6``) but
    cannot distinguish a stable model from one whose provider-side
    weights rotated under the same id."""
    cross_update_identity_asserted: bool
    """Asserts that the model-version was stable across the run window
    — no silent provider-side weight rotation. Not mechanically
    verifiable for providers that don't expose snapshot/fingerprint
    metadata; recorded as commitment with caveat."""
    same_scaffolding: bool
    """Asserts that any framework-external scaffolding (system message,
    prompt wrapping outside the verification prompt, retry policy) was
    constant across the two runs. The framework records its own prompt
    and config; this field is the analyst's commitment on the
    framework-external parts."""

    # Free-text commitments:
    unverifiable_caveats: str
    """What the analyst is committing to without framework
    verification. Should explicitly name the provider's known
    limitations on individuation (e.g. ``"Anthropic does not currently
    expose a snapshot fingerprint; cross-update identity here is
    asserted on the basis of the runs being 4 hours apart with no
    announced model update in the interval"``)."""
    rationale: str
    """Why these are the right individuation choices for this
    evaluation. Parallel to :attr:`ScopeClaim.justification`.
    One to three sentences."""


class ReliabilityClaim(BaseModel):
    """R22 claims-file block: declared identity criterion plus any
    other reliability-related commitments.

    Currently wraps only :class:`IdentityCriterion`; future
    reliability-related commitments (e.g. choice of stability
    threshold, declared replication design) can land here without
    re-shaping the top-level :class:`ConstructValidityClaims`.
    """

    model_config = ConfigDict(extra="forbid")

    identity_criterion: IdentityCriterion


class CompetingExplanationChecks(BaseModel):
    """R4, R8, R9, R11, R13, R14, R15: which checks were actually run.

    All fields default to ``False`` (the conservative posture — the
    framework assumes no check was done unless the analyst explicitly
    declares it). The report's *Unaddressed competing explanations*
    section lists every ``False``.
    """

    model_config = ConfigDict(extra="forbid")

    paraphrase_sweep_run: bool = False
    sensitivity_sweep_run: bool = False
    structural_check_run: bool = False
    cross_panel_check_run: bool = False
    independent_reference_panel_used: bool = False
    held_out_items_used: bool = False
    training_data_separation_verified: bool = False
    cross_domain_comparison_run: bool = False
    replication_attempted: bool = False
    test_retest_run: bool = False
    """R22: test-retest reliability check has been run (two independent
    evaluations against the same benchmark have been compared via
    `infereval retest`). Required at scope ≥ ``domain_D_as_sampled``;
    informational at narrower scope. Per the methodology, an evaluation
    that doesn't replicate is not evidence of anything — within-run
    agreement statistics presuppose across-run reliability."""


class ConstructValidityClaims(BaseModel):
    """Top-level container for the analyst's construct-validity declarations."""

    model_config = ConfigDict(extra="forbid")

    mastery_sense: MasterySenseClaim
    scope: ScopeClaim
    constitution: ConstitutionClaim
    carving: CarvingClaim
    competing_explanations: CompetingExplanationChecks = Field(
        default_factory=CompetingExplanationChecks
    )
    reliability: ReliabilityClaim | None = None
    """R22, second leg: declared individuation criterion for the
    reliability claim. Optional at the top level so pre-0.6.1 claims
    files validate; required at scope ≥ ``domain_D_as_sampled`` for
    R22 satisfaction (the verdict gate in :func:`compute_verdict`
    caps the verdict at ``partially_defensible`` when it's missing
    AND ``competing_explanations.test_retest_run`` is True, mirroring
    the R19 carving-acknowledgement gate)."""

    @classmethod
    def stub(cls) -> ConstructValidityClaims:
        """Return an obviously-placeholder stub for ``--init-claims``."""
        return cls(
            mastery_sense=MasterySenseClaim(
                sense="evaluative",
                description="FILL IN: the analyst's articulation of what mastery means here.",
            ),
            scope=ScopeClaim(
                scope="items_in_benchmark",
                justification="FILL IN: why this scope is appropriate.",
            ),
            constitution=ConstitutionClaim(
                position="evidence_of_mastery",
                justification="FILL IN: brief explanation of the position taken.",
            ),
            carving=CarvingClaim(
                acknowledges_carving_indexed=False,
                notes="FILL IN if acknowledges_carving_indexed=true.",
            ),
            competing_explanations=CompetingExplanationChecks(),
            reliability=ReliabilityClaim(
                identity_criterion=IdentityCriterion(
                    # Framework-substantiated booleans default to True.
                    # The analyst can deny them (set to False) only by
                    # also deciding not to do a retest; otherwise
                    # `infereval retest` would reject the run pair.
                    same_benchmark_hash=True,
                    same_endorsement_config=True,
                    same_paraphrase_variant=True,
                    # Analyst-substantiated booleans — these are real
                    # commitments the analyst has to think about. The
                    # stub leaves them as False to force the analyst
                    # to consciously assert each one.
                    same_provider_model_id=False,
                    cross_update_identity_asserted=False,
                    same_scaffolding=False,
                    unverifiable_caveats=(
                        "FILL IN: what individuation commitments are being made "
                        "without framework-mechanical verification (e.g. "
                        "provider snapshot stability, scaffolding constancy)."
                    ),
                    rationale=(
                        "FILL IN: why these individuation choices are right for "
                        "this evaluation. Required at scope >= "
                        "domain_D_as_sampled for R22 satisfaction."
                    ),
                )
            ),
        )


# ---- Verdict computation ---------------------------------------------------


@dataclass(frozen=True)
class ReportVerdict:
    """Deterministic summary verdict computed from the claims + evidence."""

    label: Literal["defensible", "partially_defensible", "not_defensible"]
    one_liner: str
    rationale: list[str]


# ---- Negative-findings aggregation (Phase 3.2) ---------------------------


@dataclass(frozen=True)
class NegativeFinding:
    """One auto-collected negative finding from a Phase 2 artifact.

    A finding is "negative" in the construct-validity sense — a check
    that ran and returned a result that *weakens or complicates* the
    mastery claim. Per *Closing the Construct-Validity Gap in infereval*
    (Phase 3.2 / R21), the framework surfaces these by default in the
    report.
    """

    source: Literal[
        "structure",
        "sweep",
        "model_fit",
        "retest",
        "decomposition_under_powered",
    ]
    summary: str
    """One-line description rendered in the Negative findings section."""


def collect_negative_findings(
    *,
    structure_report: dict[str, object] | None = None,
    sweep_summary: dict[str, object] | None = None,
    model_fit: dict[str, object] | None = None,
    retest_result: dict[str, object] | None = None,
    factor_kinds: dict[str, str] | None = None,
    decomposition_cells: list[dict[str, object]] | None = None,
) -> list[NegativeFinding]:
    """Scan the supplied Phase 2 artifacts and return their negative findings.

    Sources:

    - **structure_report**: each anomaly across all checks is one finding.
    - **sweep_summary**: instability (verdict not "stable across the sweep
      range") is one finding.
    - **model_fit**: factors whose Wald p > 0.05 are surfaced as
      no-significant-effect findings. When ``factor_kinds`` supplies a
      valence label for a factor, the finding's summary explicitly
      states whether the null is a *weakening* of the mastery claim
      (a substantive factor that didn't differentiate) or a *strengthening*
      one (an experimentally-controlled factor that properly didn't
      affect behavior — e.g. the paraphrase axis). Unlabelled factors
      get the historical neutral summary so the analyst can read the
      valence from context.
    - **decomposition_cells** (v0.8.0, closes #84): under-powered by-tag /
      by-rsr-target cells. Each cell is a dict with keys ``title`` (str),
      ``n_substantive`` (int), ``cohens_kappa`` (float | None),
      ``fleiss_kappa`` (float | None), and ``is_under_powered`` (bool).
      Cells with ``is_under_powered = True`` emit one finding each —
      the κ value on the cell is forced by single-class-each marginals
      (n below :data:`infereval.metrics.MIN_K_FOR_SUBSAMPLING_CI`),
      not measured, and shouldn't carry the verdict on its own.

    Parameters
    ----------
    factor_kinds
        Optional mapping ``factor_name -> {"substantive",
        "experimentally_controlled"}`` from ``Benchmark.factor_kinds``.
        When omitted, all null-effect findings are summarised neutrally.
    decomposition_cells
        Optional list of per-cell summaries produced by
        :func:`infereval.metrics.cell_summary` (rendered as plain dicts
        for JSON-friendliness). When supplied, under-powered cells
        become section 4b negative findings under the
        ``decomposition_under_powered`` source.
    """
    findings: list[NegativeFinding] = []

    if structure_report is not None:
        checks_raw = structure_report.get("checks", [])
        checks = checks_raw if isinstance(checks_raw, list) else []
        for check in checks:
            if not isinstance(check, dict):
                continue
            anomalies = check.get("anomalies", ()) if isinstance(check, dict) else ()
            if not anomalies:
                continue
            check_name = check.get("name", "?")
            for a in anomalies:
                if isinstance(a, dict):
                    item_id = a.get("item_id", "?")
                    expl = a.get("explanation", "")
                    findings.append(
                        NegativeFinding(
                            source="structure",
                            summary=f"{check_name} / {item_id}: {expl}",
                        )
                    )

    if sweep_summary is not None:
        verdict_raw = sweep_summary.get("stability_verdict", "")
        verdict_str = str(verdict_raw).lower()
        # The SweepResult.stability_verdict strings live in three flavours:
        # "stable" (positive), "moderately sensitive" (negative),
        # "substantively" (negative). "Stable" doesn't appear in the
        # negative ones, so its absence is the right signal.
        if verdict_str and "stable" not in verdict_str:
            param = sweep_summary.get("parameter", "?")
            findings.append(
                NegativeFinding(
                    source="sweep",
                    summary=f"Sweep over `{param}`: {sweep_summary.get('stability_verdict')}",
                )
            )

    if model_fit is not None:
        wald_raw = model_fit.get("factor_wald", {})
        wald = wald_raw if isinstance(wald_raw, dict) else {}
        kinds = factor_kinds or {}
        for factor, p in wald.items():
            if not isinstance(p, (int, float)):
                continue
            if p > 0.05:
                kind = kinds.get(str(factor))
                if kind == "substantive":
                    valence = (
                        " — **weakens the mastery claim**: this factor was "
                        "declared substantive, so the model failing to "
                        "differentiate across its levels is a negative finding"
                    )
                elif kind == "experimentally_controlled":
                    valence = (
                        " — **strengthens the mastery claim**: this factor "
                        "was declared experimentally-controlled, so the null "
                        "result is the wanted outcome (content-not-form "
                        "behavior)"
                    )
                else:
                    valence = ""
                findings.append(
                    NegativeFinding(
                        source="model_fit",
                        summary=(
                            f"`{factor}`: Wald p = {p:.3f} "
                            f"(no significant effect detected){valence}"
                        ),
                    )
                )

    if retest_result is not None:
        # v0.13.0: dispatch on artifact shape. Multi-interval emits one
        # corpus-level finding per non-stable pair and pools flipped
        # items across pairs by item_id (earliest-interval first-seen
        # annotation). Single-interval keeps the v0.12.0 behavior
        # verbatim.
        if _retest_is_multi_interval(retest_result):
            _collect_negative_findings_multi_interval(findings, retest_result)
        else:
            _collect_negative_findings_single(findings, retest_result)

    # Decomposition cells (v0.8.0, closes #84): under-powered by-tag /
    # by-rsr-target cells become section 4b negative findings. The
    # framework already gates Politis-Romano CIs at MIN_K_FOR_SUBSAMPLING_CI
    # on the headline; this extends that discipline into the decomposition.
    if decomposition_cells:
        from .metrics import MIN_K_FOR_SUBSAMPLING_CI

        for cell in decomposition_cells:
            if not isinstance(cell, dict):
                continue
            if not cell.get("is_under_powered"):
                continue
            title = cell.get("title", "?")
            n_sub = cell.get("n_substantive", "?")
            kappa_c = cell.get("cohens_kappa")
            kappa_f = cell.get("fleiss_kappa")
            kappa_pieces: list[str] = []
            if isinstance(kappa_c, (int, float)):
                kappa_pieces.append(f"κ_C = {kappa_c:+.3f}")
            elif kappa_c is None:
                kappa_pieces.append("κ_C undefined")
            if isinstance(kappa_f, (int, float)):
                kappa_pieces.append(f"κ_F = {kappa_f:+.3f}")
            elif kappa_f is None:
                kappa_pieces.append("κ_F undefined")
            kappa_str = "; ".join(kappa_pieces) if kappa_pieces else "κ undefined"
            findings.append(
                NegativeFinding(
                    source="decomposition_under_powered",
                    summary=(
                        f"{title}: n_substantive = {n_sub} "
                        f"(< {MIN_K_FOR_SUBSAMPLING_CI}); {kappa_str} is "
                        "under-powered — the magnitude is forced by "
                        "single-class-each marginals on a small subset, not "
                        "measured. Use the direction as a diagnostic lead; "
                        "confirm via a paraphrase or content-axis check."
                    ),
                )
            )

    return findings


# Per-scope, which competing-explanation checks are *required* for the
# claim to be defensible. Stricter scopes require more checks.
_REQUIRED_CHECKS_BY_SCOPE: dict[str, frozenset[str]] = {
    "items_in_benchmark": frozenset({
        # Even the narrowest scope needs the within-benchmark hygiene.
        "structural_check_run",
        "sensitivity_sweep_run",
    }),
    "domain_D_as_sampled": frozenset({
        "structural_check_run",
        "sensitivity_sweep_run",
        "paraphrase_sweep_run",
        "cross_panel_check_run",
        "held_out_items_used",
        "test_retest_run",
    }),
    "general_capacity": frozenset({
        "structural_check_run",
        "sensitivity_sweep_run",
        "paraphrase_sweep_run",
        "cross_panel_check_run",
        "held_out_items_used",
        "training_data_separation_verified",
        "cross_domain_comparison_run",
        "replication_attempted",
        "test_retest_run",
    }),
}


def compute_verdict(
    claims: ConstructValidityClaims,
    *,
    structure_report: dict[str, object] | None = None,
    benchmark: Benchmark | None = None,
    retest_result: dict[str, object] | None = None,
) -> ReportVerdict:
    """Return the deterministic summary verdict for the claims + evidence.

    The verdict is computed against the *claims* file together with the
    supplied analytical artifacts. When no artifacts are passed
    (``structure_report=None``, ``benchmark=None``), the verdict is
    computed from claims alone and a "verdict computed unaudited"
    rationale line is added so the reader can tell.

    The deterministic rule:

    - "defensible" iff every check required by the declared scope is
      marked True AND no audited check returned a failing artifact AND
      the carving claim is explicit (acknowledges = True iff any
      in-principle claims are being made) AND the benchmark supports
      an inter-analyst baseline when one is required by the scope.
    - "not_defensible" iff *more than half* of the required checks
      are missing.
    - "partially_defensible" otherwise — including the "ran but didn't
      pass" cases (structural anomalies present, single-analyst benchmark
      with ``items_in_benchmark`` scope).

    Audit caps (added in v0.5.3 from external review):

    - If ``structure_report`` is supplied AND ``structural_check_run``
      is marked True AND the report contains any anomaly, the structural
      check is treated as failing — the verdict is capped at
      ``partially_defensible`` with a rationale line naming the count.
    - If ``benchmark`` is supplied AND the scope is
      ``items_in_benchmark`` AND ``len(benchmark.analysts) < 2``, the
      verdict is capped at ``partially_defensible`` with a rationale
      line surfacing the panel size — agreement with a single analyst
      cannot inherit the convergent-validity guarantee that
      multi-analyst agreement carries.

    Backwards-compatible callers that don't pass the artifacts get
    behaviour identical to v0.5.2 except for the additional "verdict
    computed unaudited" rationale line.
    """
    required = _REQUIRED_CHECKS_BY_SCOPE[claims.scope.scope]
    ce = claims.competing_explanations
    present = {name for name in required if getattr(ce, name)}
    missing = required - present

    rationale = []
    if not missing:
        rationale.append(
            f"All {len(required)} competing-explanation checks required for "
            f"scope={claims.scope.scope!r} are marked as run."
        )
    else:
        rationale.append(
            f"{len(missing)} of {len(required)} required checks NOT run: "
            f"{sorted(missing)}."
        )

    # Carving check applies only when scope reaches beyond items_in_benchmark.
    carving_ok = True
    if claims.scope.scope != "items_in_benchmark":
        if not claims.carving.acknowledges_carving_indexed:
            carving_ok = False
            rationale.append(
                f"Scope={claims.scope.scope!r} reaches beyond the items "
                "themselves, but carving-indexed framing is NOT acknowledged "
                "(R19 unaddressed)."
            )
        elif not claims.carving.notes.strip():
            carving_ok = False
            rationale.append(
                "Carving acknowledged but no notes supplied; R19 requires "
                "the carving to be documented."
            )

    # Audit caps (v0.5.3): downgrade when the analyst declared a check
    # was run but the corresponding artifact tells a different story.
    structural_failed = False
    if (
        structure_report is not None
        and getattr(ce, "structural_check_run", False)
    ):
        checks_obj = structure_report.get("checks") or []
        checks_iter = checks_obj if isinstance(checks_obj, list) else []
        total_anomalies = 0
        for check in checks_iter:
            if not isinstance(check, dict):
                continue
            anomalies = check.get("anomalies", ())
            if isinstance(anomalies, (list, tuple)):
                total_anomalies += len(anomalies)
        if total_anomalies > 0:
            structural_failed = True
            rationale.append(
                f"`structural_check_run` is marked True, but the supplied "
                f"structure report contains {total_anomalies} anomal"
                f"{'y' if total_anomalies == 1 else 'ies'} — "
                "the check ran but did not pass. Verdict capped at "
                "partially_defensible."
            )

    panel_too_small = False
    panel_size: int | None = None
    if benchmark is not None and claims.scope.scope == "items_in_benchmark":
        panel_size = len(benchmark.analysts)
        if panel_size < 2:
            panel_too_small = True
            rationale.append(
                f"Benchmark has m={panel_size} analyst(s); κ_F\\*(β) is "
                "undefined and there is no independent reference column. "
                "A green verdict at items_in_benchmark scope would certify "
                "agreement with a single labeler — capped at "
                "partially_defensible."
            )

    # R22 audit cap: if test_retest_run is asserted and the supplied
    # retest artifact shows substantively-unstable reliability (or κ is
    # undefined), cap the verdict at partially_defensible. Same shape
    # as the v0.5.3 structural-anomaly cap.
    #
    # v0.13.0: the cap now handles both single-interval (v0.11.0+
    # RetestResult) and multi-interval (v0.12.0+ MultiIntervalRetestResult)
    # artifacts. Multi-interval is reduced via worst-case-across-pairs:
    # if ANY captured interval is substantively unstable or has
    # undefined κ, the cap fires. Conservative reading — the mastery
    # claim has to hold at every time scale the analyst captured.
    retest_failed = False
    if (
        retest_result is not None
        and getattr(ce, "test_retest_run", False)
    ):
        if _retest_is_multi_interval(retest_result):
            worst = _retest_worst_pair(retest_result)
            if worst is not None:
                worst_retest = (
                    worst.get("retest") if isinstance(worst, dict) else None
                )
                worst_verdict_str = (
                    str(worst_retest.get("stability_verdict", ""))
                    if isinstance(worst_retest, dict)
                    else ""
                )
                worst_kappa = (
                    worst_retest.get("test_retest_kappa")
                    if isinstance(worst_retest, dict)
                    else None
                )
                worst_interval = worst.get("interval_s", 0)
                retest_is_substantively_unstable = (
                    "substantively unstable" in worst_verdict_str.lower()
                )
                retest_undefined = worst_kappa is None
                if retest_is_substantively_unstable or retest_undefined:
                    retest_failed = True
                    n_pairs_raw = retest_result.get("pairs")
                    n_pairs = (
                        len(n_pairs_raw)
                        if isinstance(n_pairs_raw, list)
                        else 0
                    )
                    if retest_undefined:
                        rationale.append(
                            f"`test_retest_run` is marked True, but the "
                            f"supplied multi-interval retest result has "
                            f"undefined κ at interval {worst_interval}s "
                            f"(degenerate agreement structure on the "
                            f"comparison column) — the check ran across "
                            f"{n_pairs} interval"
                            f"{'s' if n_pairs != 1 else ''} but at least "
                            f"one did not produce a usable reliability "
                            f"estimate. Verdict capped at "
                            f"partially_defensible."
                        )
                    else:
                        flip_rate = (
                            worst_retest.get("flip_rate")
                            if isinstance(worst_retest, dict)
                            else None
                        )
                        flip_str = (
                            f", flip rate = {flip_rate * 100:.1f}%"
                            if isinstance(flip_rate, (int, float))
                            else ""
                        )
                        rationale.append(
                            f"`test_retest_run` is marked True, but the "
                            f"supplied multi-interval retest result has "
                            f"a substantively-unstable pair at interval "
                            f"{worst_interval}s "
                            f"(κ = {worst_kappa:+.3f}{flip_str}); the "
                            f"headline κ_C cannot be interpreted as "
                            f"signal under this reliability across the "
                            f"time scales captured. Verdict capped at "
                            f"partially_defensible."
                        )
        else:
            retest_verdict = str(retest_result.get("stability_verdict", ""))
            retest_kappa = retest_result.get("test_retest_kappa")
            retest_is_substantively_unstable = (
                "substantively unstable" in retest_verdict.lower()
            )
            retest_undefined = retest_kappa is None
            if retest_is_substantively_unstable or retest_undefined:
                retest_failed = True
                if retest_undefined:
                    rationale.append(
                        "`test_retest_run` is marked True, but the supplied "
                        "retest result has undefined κ (degenerate agreement "
                        "structure on the comparison column) — the check "
                        "ran but did not produce a usable reliability "
                        "estimate. Verdict capped at partially_defensible."
                    )
                else:
                    flip_rate = retest_result.get("flip_rate")
                    flip_str = (
                        f", flip rate = {flip_rate * 100:.1f}%"
                        if isinstance(flip_rate, (int, float))
                        else ""
                    )
                    rationale.append(
                        f"`test_retest_run` is marked True, but the supplied "
                        f"retest result is substantively unstable "
                        f"(κ = {retest_kappa:+.3f}{flip_str}) — the check ran "
                        f"but did not pass. The headline κ_C cannot be "
                        f"interpreted as signal under this reliability. "
                        f"Verdict capped at partially_defensible."
                    )

    # v0.6.1 R22 second leg: at scope >= domain_D_as_sampled, R22
    # satisfaction requires `test_retest_run=True` AND a declared
    # IdentityCriterion (`reliability.identity_criterion` populated
    # with a non-empty rationale). Without a declared criterion the κ
    # is uninterpretable — same shape as the R19 carving-acknowledgement
    # gate.
    individuation_undeclared = False
    if (
        claims.scope.scope != "items_in_benchmark"
        and getattr(ce, "test_retest_run", False)
    ):
        reliability = getattr(claims, "reliability", None)
        if reliability is None or not reliability.identity_criterion.rationale.strip():
            individuation_undeclared = True
            rationale.append(
                f"`test_retest_run` is marked True at "
                f"scope={claims.scope.scope!r}, but the identity "
                f"criterion under which the test-retest κ is "
                f"interpretable has not been declared (R22 second leg "
                f"— `reliability.identity_criterion` missing or rationale "
                f"empty). Without a declared criterion the κ is "
                f"uninterpretable as a reliability number. Verdict "
                f"capped at partially_defensible. Same shape as the R19 "
                f"carving-acknowledgement gate."
            )

    if structure_report is None and benchmark is None and retest_result is None:
        rationale.append(
            "Verdict computed unaudited: no structure_report, benchmark, "
            "or retest_result supplied to compute_verdict, so 'check run' "
            "is taken at face value and panel size / retest stability are "
            "not inspected. Render through `infereval report` (which "
            "passes all three) for the audited verdict."
        )

    # Decide.
    audit_passes = (
        not structural_failed
        and not panel_too_small
        and not retest_failed
        and not individuation_undeclared
    )
    if not missing and carving_ok and audit_passes:
        one_liner = f"Mastery claim defensible at scope={claims.scope.scope!r}."
        if panel_size is not None:
            one_liner = (
                f"Mastery claim defensible at scope={claims.scope.scope!r} "
                f"(m={panel_size} analysts)."
            )
        return ReportVerdict(
            label="defensible",
            one_liner=one_liner,
            rationale=rationale,
        )
    if (len(missing) > len(required) / 2 or not carving_ok) and audit_passes:
        return ReportVerdict(
            label="not_defensible",
            one_liner=(
                f"Mastery claim NOT defensible from the supplied evidence at "
                f"scope={claims.scope.scope!r}."
            ),
            rationale=rationale,
        )
    return ReportVerdict(
        label="partially_defensible",
        one_liner=(
            f"Mastery claim partially defensible at scope={claims.scope.scope!r} — "
            "see Unaddressed competing explanations."
        ),
        rationale=rationale,
    )


# ---- Rendering ------------------------------------------------------------


def render_markdown(
    *,
    evaluation: Evaluation,
    benchmark: Benchmark,
    claims: ConstructValidityClaims,
    structure_report: dict[str, object] | None = None,
    sweep_summary: dict[str, object] | None = None,
    model_fit: dict[str, object] | None = None,
    retest_result: dict[str, object] | None = None,
    decomposition_cells: list[dict[str, object]] | None = None,
    generated_at: datetime | None = None,
    suppress_negatives: bool = False,
) -> str:
    """Produce the construct-validity report as Markdown.

    Optional arguments (``structure_report``, ``sweep_summary``,
    ``model_fit``) populate the Evidence section; when absent, that
    section explicitly notes the missing evidence.
    """
    from .metrics import (
        cohens_kappa,
        consensus_reference,
        coverage,
        fleiss_kappa,
        inter_analyst_fleiss,
        inter_analyst_fleiss_per_panel,
    )

    generated_at = generated_at or datetime.now(timezone.utc)

    kappa_c = cohens_kappa(evaluation, consensus_reference(evaluation))
    kappa_f = fleiss_kappa(evaluation)
    # v0.7.0 (#82): inter_analyst_fleiss returns the all-analyst κ_F*
    # by default. On panelled benchmarks the primary-panel value is
    # rendered as a sub-bullet below for methodological transparency.
    kappa_f_star = inter_analyst_fleiss(benchmark)
    panel_names = benchmark.panel_names() if benchmark is not None else []
    primary_panel_kappa: float | None = None
    primary_panel_name: str | None = None
    if panel_names:
        primary_panel_name = benchmark.resolved_primary_panel()
        if primary_panel_name is not None:
            per_panel = inter_analyst_fleiss_per_panel(benchmark)
            primary_panel_kappa = per_panel.get(primary_panel_name)
    cov = coverage(evaluation)
    verdict = compute_verdict(
        claims,
        structure_report=structure_report,
        benchmark=benchmark,
        retest_result=retest_result,
    )

    # Collect negative findings up-front so we can both render them and
    # apply the suppression penalty to the verdict in one place.
    findings = collect_negative_findings(
        structure_report=structure_report,
        sweep_summary=sweep_summary,
        model_fit=model_fit,
        retest_result=retest_result,
        factor_kinds=dict(benchmark.factor_kinds) if benchmark.factor_kinds else None,
        decomposition_cells=decomposition_cells,
    )
    any_phase2_supplied = any(
        x is not None for x in (
            structure_report, sweep_summary, model_fit, retest_result,
            decomposition_cells,
        )
    )

    # If suppression is enabled, the Summary verdict downgrades one tier:
    # defensible -> partially_defensible -> not_defensible. Hiding
    # evidence is itself a negative construct-validity signal.
    if suppress_negatives:
        downgraded_label = {
            "defensible": "partially_defensible",
            "partially_defensible": "not_defensible",
            "not_defensible": "not_defensible",
        }[verdict.label]
        if downgraded_label != verdict.label:
            verdict = ReportVerdict(
                label=downgraded_label,  # type: ignore[arg-type]
                one_liner=(
                    "Verdict downgraded one tier because "
                    "--suppress-negatives is enabled."
                ),
                rationale=[
                    *verdict.rationale,
                    "Negative-findings suppression downgrades the verdict "
                    "(Phase 3.2 / R21).",
                ],
            )

    lines: list[str] = []
    lines.append("# Construct-validity report")
    lines.append("")
    lines.append(f"_Generated: {generated_at.isoformat()}_")
    if suppress_negatives:
        lines.append("")
        lines.append(
            "> ⚠️ **Negative-findings suppression: ENABLED.** This is an "
            "explicit author choice via `--suppress-negatives`; the "
            "framework normally surfaces negative findings by default. "
            "Reviewers: ask why this flag was set."
        )
    lines.append("")

    # 1. Identity
    lines.append("## 1. Identity")
    lines.append("")
    lines.append(f"- **Evaluation**: `{evaluation.id}`")
    lines.append(f"- **Benchmark**: `{benchmark.id}`")
    lines.append(
        f"- **Model**: `{evaluation.model.provider}` / `{evaluation.model.model_id}`"
    )
    if evaluation.started_at:
        lines.append(f"- **Run started**: {evaluation.started_at.isoformat()}")
    lines.append(f"- **Items**: {evaluation.n}")
    lines.append(f"- **Analysts**: {benchmark.m}")
    lines.append("")

    # 2. Summary metrics
    #
    # v0.13.0 (#?): §2 is restructured into two sibling subheaded blocks
    # — `### Agreement` (cov/κ_C/κ_F/κ_F*) and `### Reliability (R22)`
    # (test-retest) — so test-retest reliability sits at the same visual
    # level as agreement. The `## 2.` anchor is preserved (no
    # renumbering cascade) but the visual hierarchy now reflects the
    # methodology paper's framing: agreement and reliability are
    # co-equal construct-validity dimensions, not a primary plus an
    # optional footnote.
    lines.append("## 2. Summary metrics")
    lines.append("")
    lines.append("### Agreement")
    lines.append("")
    lines.append(f"- **Coverage**: {cov:.4f}")
    lines.append(f"- **Cohen's κ_C (vs consensus)**: {_format_kappa(kappa_c)}")
    lines.append(f"- **Fleiss' κ_F**: {_format_kappa(kappa_f)}")
    # v0.7.0 (#82): on panelled benchmarks the headline κ_F* is the
    # all-analyst figure; the primary panel's value is rendered as a
    # sub-bullet so the methodological distinction (panels are an
    # additive convergent-validity device, not a replacement for the
    # baseline) is visible at the surface where the reader looks for
    # the Remark 4 number.
    if panel_names:
        lines.append(
            f"- **Inter-analyst κ_F\\* (all analysts)**: "
            f"{_format_kappa(kappa_f_star)}"
        )
        if primary_panel_name is not None:
            lines.append(
                f"  - *Primary panel (`{primary_panel_name}`) κ_F\\* = "
                f"{_format_kappa(primary_panel_kappa)}*"
            )
    else:
        lines.append(f"- **Inter-analyst κ_F\\***: {_format_kappa(kappa_f_star)}")
    lines.append("")
    lines.append("### Reliability (R22)")
    lines.append("")
    # Test-retest κ (R22): within-model analog of κ_F*. Always rendered
    # — informational at items_in_benchmark scope, verdict-gating at
    # scope ≥ domain_D_as_sampled. The renderer auto-detects single vs
    # multi-interval shape via the presence of a `pairs` key on the
    # supplied artifact, so a single CLI flag (--retest) consumes
    # either v0.11.0+ RetestResult or v0.12.0+ MultiIntervalRetestResult
    # JSON. v0.6.1: the κ row carries an explicit "under the declared
    # identity criterion ..." suffix when the criterion is present in
    # the supplied retest artifact, making explicit what the reliability
    # number is relative to (Hlobil's individuation point).
    _render_retest_section(lines, retest_result)
    lines.append("")

    # 3. Construct-validity claims (R16-R20)
    lines.append("## 3. Construct-validity claims (R16–R20)")
    lines.append("")
    lines.append(f"**Mastery sense (R16)**: {claims.mastery_sense.sense}")
    lines.append("")
    lines.append(f"> {claims.mastery_sense.description}")
    lines.append("")
    lines.append(f"**Scope (R17)**: {claims.scope.scope}")
    lines.append("")
    lines.append(f"> {claims.scope.justification}")
    lines.append("")
    lines.append(f"**Constitution vs. evidence (R18)**: {claims.constitution.position}")
    lines.append("")
    lines.append(f"> {claims.constitution.justification}")
    lines.append("")
    carving_status = (
        "acknowledged" if claims.carving.acknowledges_carving_indexed else "not acknowledged"
    )
    lines.append(f"**Carving-indexed framing (R19)**: {carving_status}")
    if claims.carving.notes.strip():
        lines.append("")
        lines.append(f"> {claims.carving.notes}")
    lines.append("")

    # v0.6.1 R22 second leg: render the declared individuation
    # criterion verbatim when claims include the reliability block.
    # Doubly-relative framing — the reliability claim is relative to
    # both the carving (R19, above) and the identity criterion (R22
    # second leg, here). Same commitment-and-relativity pattern.
    if claims.reliability is not None:
        crit = claims.reliability.identity_criterion
        lines.append(
            "**Reliability — identity criterion "
            "(R22, doubly-relative)**:"
        )
        lines.append("")
        lines.append(
            f"- Framework-substantiated: same_benchmark_hash="
            f"`{crit.same_benchmark_hash}`, same_endorsement_config="
            f"`{crit.same_endorsement_config}`, same_paraphrase_variant="
            f"`{crit.same_paraphrase_variant}`."
        )
        lines.append(
            f"- Analyst-substantiated: same_provider_model_id="
            f"`{crit.same_provider_model_id}`, "
            f"cross_update_identity_asserted="
            f"`{crit.cross_update_identity_asserted}`, "
            f"same_scaffolding=`{crit.same_scaffolding}`."
        )
        if crit.unverifiable_caveats.strip():
            lines.append("")
            lines.append(f"> _Unverifiable caveats:_ {crit.unverifiable_caveats}")
        if crit.rationale.strip():
            lines.append("")
            lines.append(f"> _Rationale:_ {crit.rationale}")
        lines.append("")

    # 4. Evidence
    lines.append("## 4. Evidence")
    lines.append("")
    lines.append("Auto-collected from optional Phase 2 artifacts:")
    lines.append("")

    if structure_report is not None:
        total_anomalies = structure_report.get("total_anomalies", 0)
        lines.append(
            f"- **Structural coherence checks** (R13): "
            f"{total_anomalies} anomalies flagged across the bundled checks."
        )
    else:
        lines.append("- **Structural coherence checks** (R13): NOT SUPPLIED.")

    if sweep_summary is not None:
        kc_range = sweep_summary.get("kappa_c_range")
        param = sweep_summary.get("parameter", "?")
        verdict_str = sweep_summary.get("stability_verdict", "?")
        if kc_range is not None:
            lines.append(
                f"- **Sensitivity sweep** over `{param}` (R11): "
                f"κ_C range = {kc_range:.3f}. {verdict_str}"
            )
        else:
            lines.append(
                f"- **Sensitivity sweep** over `{param}` (R11): {verdict_str}"
            )
    else:
        lines.append("- **Sensitivity sweep** (R11): NOT SUPPLIED.")

    if model_fit is not None:
        wald_raw = model_fit.get("factor_wald", {})
        wald = wald_raw if isinstance(wald_raw, dict) else {}
        sig = sum(1 for p in wald.values() if isinstance(p, (int, float)) and p < 0.05)
        lines.append(
            f"- **Factor-effects model fit** (R7, R12): "
            f"{sig}/{len(wald)} factors significant at α=0.05."
        )
    else:
        lines.append("- **Factor-effects model fit** (R7, R12): NOT SUPPLIED.")

    if retest_result is not None:
        retest_verdict_str = retest_result.get("stability_verdict", "?")
        n_flipped_raw = retest_result.get("flipped_items", [])
        n_flipped = len(n_flipped_raw) if isinstance(n_flipped_raw, list) else 0
        lines.append(
            f"- **Test-retest reliability** (R22): {retest_verdict_str} "
            f"({n_flipped} item(s) flipped between runs)."
        )
    else:
        lines.append("- **Test-retest reliability** (R22): NOT SUPPLIED.")
    lines.append("")

    # 4b. Negative findings (Phase 3.2, R21)
    lines.append("## 4b. Negative findings")
    lines.append("")
    if suppress_negatives:
        lines.append(
            "⚠️ **Suppressed via `--suppress-negatives`.** This is an "
            "explicit author choice; the framework normally surfaces "
            "negative findings by default. Reviewers: ask why this flag "
            "was set."
        )
    elif not any_phase2_supplied:
        lines.append(
            "No Phase 2 artifacts supplied; the auto-collection step had "
            "nothing to scan. See Unaddressed competing explanations (§5) "
            "for the analyst-declared check status."
        )
    elif not findings:
        lines.append("No negative findings detected in the supplied Phase 2 artifacts.")
    else:
        lines.append(
            "The framework auto-collects negative findings from the "
            "supplied Phase 2 artifacts. Each item below represents a "
            "check that ran but returned a finding that *weakens or "
            "complicates* the mastery claim."
        )
        lines.append("")
        # Group by source for readability.
        for src_label, src_key in [
            ("Structural anomalies", "structure"),
            ("Sweep instability", "sweep"),
            ("Factor-effects null findings", "model_fit"),
            ("Test-retest anomalies (R22)", "retest"),
            ("Decomposition under-powered (R12)", "decomposition_under_powered"),
        ]:
            src_items = [f for f in findings if f.source == src_key]
            if not src_items:
                continue
            lines.append(f"### {src_label} ({len(src_items)} flagged)")
            for f in src_items:
                lines.append(f"- {f.summary}")
            lines.append("")
    lines.append("")

    # 5. Unaddressed competing explanations
    lines.append("## 5. Unaddressed competing explanations")
    lines.append("")
    ce = claims.competing_explanations
    unaddressed = [
        (name, _human_label_for_check(name))
        for name in (
            "paraphrase_sweep_run",
            "sensitivity_sweep_run",
            "structural_check_run",
            "cross_panel_check_run",
            "independent_reference_panel_used",
            "held_out_items_used",
            "training_data_separation_verified",
            "cross_domain_comparison_run",
            "replication_attempted",
            "test_retest_run",
        )
        if not getattr(ce, name)
    ]
    if not unaddressed:
        lines.append("All declared competing-explanation checks marked as run.")
    else:
        lines.append(
            "The following checks were NOT run. Each omission weakens the "
            "defensibility of the corresponding mastery claim:"
        )
        lines.append("")
        for name, label in unaddressed:
            lines.append(f"- **{label}** (`{name}`)")
    lines.append("")

    # 6. Summary verdict
    lines.append("## 6. Summary verdict")
    lines.append("")
    badge = {
        "defensible": "✅",
        "partially_defensible": "⚠️",
        "not_defensible": "❌",
    }[verdict.label]
    lines.append(f"### {badge} {verdict.one_liner}")
    lines.append("")
    for note in verdict.rationale:
        lines.append(f"- {note}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by `infereval report` (Phase 3.1, R16–R20). The verdict "
        "is computed deterministically from the claims file; the framework "
        "refuses to render a 'defensible' verdict without the corresponding "
        "competing-explanation checks.*"
    )

    return "\n".join(lines) + "\n"


def _format_kappa(value: float | None) -> str:
    if value is None:
        return "undefined"
    return f"{value:+.4f}"


def _human_label_for_check(name: str) -> str:
    return name.replace("_", " ").capitalize()


# v0.13.0: stability-verdict ordering for worst-case selection. Lower
# rank = better. Used by both the multi-interval renderer (to pick the
# overall verdict line) and compute_verdict's R22 audit cap (to pick
# the worst pair when capping). `undefined …` strings rank worst —
# higher than substantively unstable — because an undefined κ means
# the check ran but produced no usable reliability number, which is at
# least as bad as a substantively-unstable result for audit purposes.
_STABILITY_RANK: dict[str, int] = {
    "stable": 0,
    "moderately stable": 1,
    "substantively unstable": 2,
    "undefined": 3,
}


def _stability_rank(verdict_str: str) -> int:
    """Map a stability_verdict prose string to its worst-case ordering rank.

    Recognises the four canonical prefixes; falls back to the worst
    rank for unknown strings so an unexpected verdict can't silently
    lift a cap.
    """
    s = (verdict_str or "").lower()
    if "substantively unstable" in s:
        return _STABILITY_RANK["substantively unstable"]
    if "moderately stable" in s:
        return _STABILITY_RANK["moderately stable"]
    if s.startswith("test-retest reliability is stable") or s == "stable":
        return _STABILITY_RANK["stable"]
    if "undefined" in s:
        return _STABILITY_RANK["undefined"]
    # Unknown / empty → treat as worst so we don't silently miss a cap.
    return _STABILITY_RANK["undefined"]


def _retest_is_multi_interval(retest_result: dict[str, object]) -> bool:
    """True iff the supplied retest artifact has the v0.12.0+ multi-interval shape.

    Detected by the presence of a list-typed ``pairs`` key. Single-pair
    MultiIntervalRetestResult artifacts (N=1) still render with the
    multi-interval table — the shape, not the count, drives the
    renderer.
    """
    pairs = retest_result.get("pairs")
    return isinstance(pairs, list)


def _retest_worst_pair(
    retest_result: dict[str, object],
) -> dict[str, object] | None:
    """Return the worst-case pair (by stability rank) from a multi-interval artifact.

    Returns ``None`` if the artifact has no pairs or isn't
    multi-interval. Ties broken by the largest interval (later
    captures matter more for the methodological claim).
    """
    if not _retest_is_multi_interval(retest_result):
        return None
    pairs_raw = retest_result.get("pairs")
    if not isinstance(pairs_raw, list) or not pairs_raw:
        return None
    best: dict[str, object] | None = None
    best_key: tuple[int, int] = (-1, -1)
    for pair in pairs_raw:
        if not isinstance(pair, dict):
            continue
        retest_dict = pair.get("retest")
        if not isinstance(retest_dict, dict):
            continue
        verdict_str = str(retest_dict.get("stability_verdict", ""))
        rank = _stability_rank(verdict_str)
        interval_raw = pair.get("interval_s", 0)
        interval = interval_raw if isinstance(interval_raw, int) else 0
        key = (rank, interval)
        if key > best_key:
            best_key = key
            best = pair
    return best


def _collect_negative_findings_single(
    findings: list[NegativeFinding], retest_result: dict[str, object]
) -> None:
    """v0.11.0+ single RetestResult → corpus finding + per-item flipped findings.

    Lifted verbatim from the pre-v0.13.0 inline block in
    :func:`collect_negative_findings` so single-interval behavior is
    byte-identical to v0.12.0.
    """
    # Corpus-level finding: stability_verdict isn't "stable".
    retest_verdict_raw = retest_result.get("stability_verdict", "")
    retest_verdict_str = str(retest_verdict_raw)
    # The stability_verdict strings are: "stable" (positive),
    # "moderately stable" (negative — replication concern flagged),
    # "substantively unstable" (negative — verdict-gating), and
    # "undefined ..." (κ undefined; treat as negative for hygiene).
    is_positive = (
        retest_verdict_str.lower().startswith("test-retest reliability is stable")
    )
    if retest_verdict_str and not is_positive:
        kappa = retest_result.get("test_retest_kappa")
        flip_rate = retest_result.get("flip_rate")
        kappa_str = (
            f"κ = {kappa:+.3f}" if isinstance(kappa, (int, float))
            else "κ undefined"
        )
        flip_str = (
            f", flip rate = {flip_rate * 100:.1f}%"
            if isinstance(flip_rate, (int, float))
            else ""
        )
        findings.append(
            NegativeFinding(
                source="retest",
                summary=(
                    f"Test-retest reliability (R22): {retest_verdict_str} "
                    f"[{kappa_str}{flip_str}]"
                ),
            )
        )
    # Per-item findings: each flipped item is one finding (capped to
    # 50 so an enormous flip list doesn't overwhelm the report;
    # the full list is in the artifact JSON).
    flipped_raw = retest_result.get("flipped_items", []) or []
    flipped = flipped_raw if isinstance(flipped_raw, list) else []
    cap = 50
    for fi in flipped[:cap]:
        if not isinstance(fi, dict):
            continue
        iid = fi.get("item_id", "?")
        va = fi.get("verdict_a", "?")
        vb = fi.get("verdict_b", "?")
        fl = fi.get("factor_levels") or {}
        fl_str = (
            f" [{', '.join(f'{k}={v}' for k, v in fl.items())}]"
            if isinstance(fl, dict) and fl
            else ""
        )
        findings.append(
            NegativeFinding(
                source="retest",
                summary=f"`{iid}`: verdict flipped {va} → {vb}{fl_str}",
            )
        )
    if len(flipped) > cap:
        findings.append(
            NegativeFinding(
                source="retest",
                summary=(
                    f"... and {len(flipped) - cap} more flipped items — "
                    "see the retest-result JSON for the full list."
                ),
            )
        )


def _collect_negative_findings_multi_interval(
    findings: list[NegativeFinding], retest_result: dict[str, object]
) -> None:
    """v0.12.0+ MultiIntervalRetestResult → per-pair corpus findings + pooled flips.

    Corpus level:
      One :class:`NegativeFinding` per non-stable pair, summary
      ``"Test-retest reliability (R22) at interval Ns: <verdict>
      [κ=X, flip rate=Y%]"``. Bounded by number of intervals.

    Per-item level:
      Flipped items are pooled across all pairs by ``item_id``. The
      earliest pair (smallest interval) in which an item flips
      determines its "first seen at interval Ns" annotation, so an
      item that flips in three pairs is one bullet, not three. Cap
      remains at 50 unique items like the single-interval path.
    """
    pairs_raw = retest_result.get("pairs")
    pairs: list[dict[str, object]] = (
        [p for p in pairs_raw if isinstance(p, dict)]
        if isinstance(pairs_raw, list)
        else []
    )

    # Pass 1 — corpus-level findings: one row per non-stable pair, in
    # the order they appear in `pairs` (analyst-supplied order).
    for pair in pairs:
        retest_dict = pair.get("retest")
        if not isinstance(retest_dict, dict):
            continue
        verdict_str = str(retest_dict.get("stability_verdict", ""))
        if not verdict_str:
            continue
        if verdict_str.lower().startswith("test-retest reliability is stable"):
            continue
        kappa = retest_dict.get("test_retest_kappa")
        flip_rate = retest_dict.get("flip_rate")
        kappa_str = (
            f"κ = {kappa:+.3f}" if isinstance(kappa, (int, float))
            else "κ undefined"
        )
        flip_str = (
            f", flip rate = {flip_rate * 100:.1f}%"
            if isinstance(flip_rate, (int, float))
            else ""
        )
        interval_raw = pair.get("interval_s", 0)
        interval = interval_raw if isinstance(interval_raw, int) else 0
        findings.append(
            NegativeFinding(
                source="retest",
                summary=(
                    f"Test-retest reliability (R22) at interval "
                    f"{interval}s: {verdict_str} [{kappa_str}{flip_str}]"
                ),
            )
        )

    # Pass 2 — pooled per-item flipped findings. Walk pairs in
    # ascending interval order so the "first seen" annotation is
    # genuinely the earliest interval, regardless of analyst-supplied
    # pair ordering.
    def _interval_key(p: dict[str, object]) -> int:
        v = p.get("interval_s", 0)
        return v if isinstance(v, int) else 0

    pairs_by_interval = sorted(pairs, key=_interval_key)
    seen: dict[str, NegativeFinding] = {}
    for pair in pairs_by_interval:
        retest_dict = pair.get("retest")
        if not isinstance(retest_dict, dict):
            continue
        flipped_raw = retest_dict.get("flipped_items", []) or []
        flipped = flipped_raw if isinstance(flipped_raw, list) else []
        interval_raw = pair.get("interval_s", 0)
        interval = interval_raw if isinstance(interval_raw, int) else 0
        for fi in flipped:
            if not isinstance(fi, dict):
                continue
            iid = str(fi.get("item_id", "?"))
            if iid in seen:
                # Already accounted for in an earlier (smaller-interval)
                # pair. Skip — avoids the same flipped item appearing as
                # three bullets when it shows up in three pairs.
                continue
            va = fi.get("verdict_a", "?")
            vb = fi.get("verdict_b", "?")
            fl = fi.get("factor_levels") or {}
            fl_str = (
                f" [{', '.join(f'{k}={v}' for k, v in fl.items())}]"
                if isinstance(fl, dict) and fl
                else ""
            )
            seen[iid] = NegativeFinding(
                source="retest",
                summary=(
                    f"`{iid}`: verdict flipped {va} → {vb}"
                    f"{fl_str} [first seen at interval {interval}s]"
                ),
            )

    # Cap matches the single-interval path: at most 50 unique items
    # surface; the full list lives in the artifact JSON.
    pooled = list(seen.values())
    cap = 50
    findings.extend(pooled[:cap])
    if len(pooled) > cap:
        findings.append(
            NegativeFinding(
                source="retest",
                summary=(
                    f"... and {len(pooled) - cap} more flipped items "
                    "(pooled across intervals) — see the multi-interval "
                    "retest-result JSON for the full list."
                ),
            )
        )


def _render_retest_section(
    lines: list[str], retest_result: dict[str, object] | None
) -> None:
    """Append the §2 Reliability (R22) block to ``lines``.

    Shape auto-detection:
    - ``retest_result is None`` → single "Not measured" bullet so the
      Reliability subhead is never empty (a missing R22 capture is
      itself a construct-validity signal).
    - ``retest_result`` is a v0.11.0+ ``RetestResult`` dict (no
      ``pairs`` key) → single-bullet rendering, preserving the exact
      v0.12.0 bullet text byte-for-byte so existing rendering tests
      continue to pass under the new subhead.
    - ``retest_result`` is a v0.12.0+ ``MultiIntervalRetestResult`` dict
      (``pairs`` list present) → per-interval markdown table +
      overall-verdict line + (optional) identity-criterion clause.
    """
    if retest_result is None:
        lines.append(
            "- Not measured (R22 not run for this evaluation)."
        )
        return

    if _retest_is_multi_interval(retest_result):
        _render_retest_multi_interval(lines, retest_result)
        return

    # Single-interval (v0.11.0 RetestResult). Behavior verbatim from
    # v0.12.0 — the same bullet line, just under the new ### subhead.
    retest_kappa = retest_result.get("test_retest_kappa")
    retest_kappa_v = (
        retest_kappa if isinstance(retest_kappa, (int, float)) else None
    )
    criterion_clause = ""
    embedded_crit = retest_result.get("identity_criterion")
    if isinstance(embedded_crit, dict):
        criterion_clause = (
            " *under the declared identity criterion "
            f"(`{_one_line_criterion_summary(embedded_crit)}`)*"
        )
    lines.append(
        f"- **Test-retest κ (R22)**: "
        f"{_format_kappa(retest_kappa_v)}{criterion_clause}"
    )


def _render_retest_multi_interval(
    lines: list[str], retest_result: dict[str, object]
) -> None:
    """Append the per-interval R22 table + overall-verdict line.

    Reads the MultiIntervalRetestResult dict shape produced by
    ``infereval.retest.multi_interval_retest_result_to_dict``. Each
    ``pairs[i]`` row carries ``interval_s``, ``run_id``, and an
    embedded ``retest`` dict whose ``test_retest_kappa`` /
    ``flipped_items`` / ``stability_verdict`` drive the row content.
    The overall verdict line is the worst stability across all pairs
    (cumulative-drift-since-baseline reading: if any captured interval
    is unstable, the mastery claim does not hold at that time scale).
    """
    baseline_run_id = retest_result.get("baseline_run_id", "?")
    benchmark_id = retest_result.get("benchmark_id", "?")
    pairs_raw = retest_result.get("pairs")
    pairs: list[dict[str, object]] = (
        [p for p in pairs_raw if isinstance(p, dict)]
        if isinstance(pairs_raw, list)
        else []
    )

    lines.append(
        f"- **Baseline run**: `{baseline_run_id}` (benchmark `{benchmark_id}`)."
    )
    lines.append("")
    lines.append(
        "| Interval (s) | Later run | κ vs baseline | Flips | Verdict |"
    )
    lines.append("|---:|---|---:|---:|---|")

    n_items: int | None = None
    for pair in pairs:
        interval_raw = pair.get("interval_s", 0)
        interval = interval_raw if isinstance(interval_raw, int) else 0
        run_id = pair.get("run_id", "?")
        retest_dict = pair.get("retest")
        if not isinstance(retest_dict, dict):
            lines.append(
                f"| {interval} | `{run_id}` | undefined | ? | malformed |"
            )
            continue
        kappa = retest_dict.get("test_retest_kappa")
        kappa_v = kappa if isinstance(kappa, (int, float)) else None
        flipped_raw = retest_dict.get("flipped_items", []) or []
        n_flipped = len(flipped_raw) if isinstance(flipped_raw, list) else 0
        # `n_items` comes off the embedded retest result; cached on first
        # pair seen for the verdict-line denominator.
        pair_n = retest_dict.get("n_items")
        if isinstance(pair_n, int) and n_items is None:
            n_items = pair_n
        n_str = f"{n_flipped}/{pair_n}" if isinstance(pair_n, int) else f"{n_flipped}"
        verdict_str = str(retest_dict.get("stability_verdict", "?"))
        # Compress the prose verdict into a short table-row label.
        verdict_short = _short_stability_label(verdict_str)
        lines.append(
            f"| {interval} | `{run_id}` | {_format_kappa(kappa_v)} | "
            f"{n_str} | {verdict_short} |"
        )

    lines.append("")
    worst = _retest_worst_pair(retest_result)
    if worst is not None:
        worst_retest = worst.get("retest") if isinstance(worst, dict) else None
        worst_verdict_str = (
            str(worst_retest.get("stability_verdict", "?"))
            if isinstance(worst_retest, dict)
            else "?"
        )
        worst_interval_raw = worst.get("interval_s", 0)
        worst_interval = (
            worst_interval_raw if isinstance(worst_interval_raw, int) else 0
        )
        lines.append(
            f"- **Overall verdict**: {_short_stability_label(worst_verdict_str)} "
            f"(worst-case across {len(pairs)} interval"
            f"{'s' if len(pairs) != 1 else ''}; driven by interval "
            f"{worst_interval}s)."
        )
    else:
        lines.append(
            "- **Overall verdict**: no pairs supplied "
            "(MultiIntervalRetestResult artifact carries an empty `pairs` list)."
        )

    # Identity-criterion clause. The criterion is one-shot at the
    # ReliabilityClaim / wrapper level; we look for it on the wrapper
    # first, then fall back to the first pair's embedded criterion
    # (for symmetry with the single-interval path, which reads it off
    # the RetestResult itself).
    crit = retest_result.get("identity_criterion")
    if not isinstance(crit, dict):
        for pair in pairs:
            pair_retest = pair.get("retest")
            if isinstance(pair_retest, dict):
                maybe_crit = pair_retest.get("identity_criterion")
                if isinstance(maybe_crit, dict):
                    crit = maybe_crit
                    break
    if isinstance(crit, dict):
        lines.append(
            f"- *Every pair compared under the declared identity criterion "
            f"(`{_one_line_criterion_summary(crit)}`).*"
        )


def _short_stability_label(verdict_str: str) -> str:
    """Compress a stability_verdict prose string into a short table-row label.

    Maps the four canonical prose verdicts to: ``stable``,
    ``moderately stable``, ``substantively unstable``, ``undefined``.
    Falls through to a leading-word abbreviation for unknown strings
    so the column never blows out of its width.
    """
    s = (verdict_str or "").lower()
    if "substantively unstable" in s:
        return "substantively unstable"
    if "moderately stable" in s:
        return "moderately stable"
    if "undefined" in s:
        return "undefined"
    if s.startswith("test-retest reliability is stable") or s == "stable":
        return "stable"
    return verdict_str.split(".")[0][:40] or "?"


def _one_line_criterion_summary(crit: dict[str, object]) -> str:
    """Summarise an IdentityCriterion as a single human-readable line.

    Lists the analyst-substantiated booleans the criterion asserts, so
    the section-2 test-retest κ row can render
    ``[+0.85] under the declared identity criterion (provider+model_id,
    cross-update identity asserted, scaffolding constant)``.

    Falls back to ``"framework-substantiated only"`` when none of the
    analyst-substantiated booleans are True.
    """
    asserted: list[str] = []
    if crit.get("same_provider_model_id"):
        asserted.append("provider+model_id")
    if crit.get("cross_update_identity_asserted"):
        asserted.append("cross-update identity asserted")
    if crit.get("same_scaffolding"):
        asserted.append("scaffolding constant")
    if not asserted:
        return "framework-substantiated only"
    return ", ".join(asserted)


__all__ = [
    "CarvingClaim",
    "CompetingExplanationChecks",
    "ConstitutionClaim",
    "ConstructValidityClaims",
    "IdentityCriterion",
    "MasterySenseClaim",
    "NegativeFinding",
    "ReliabilityClaim",
    "ReportVerdict",
    "ScopeClaim",
    "collect_negative_findings",
    "compute_verdict",
    "render_markdown",
]

# Used by the CLI for --init-claims; kept here so the JSON shape stays
# next to the schema.
_ = json
