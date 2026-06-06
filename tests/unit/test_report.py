"""Tests for ``infereval.report`` — Phase 3.1 construct-validity report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ScriptedProvider
from infereval.report import (
    CompetingExplanationChecks,
    ConstructValidityClaims,
    compute_verdict,
    render_markdown,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


def _minimal_claims(
    *,
    scope: str = "items_in_benchmark",
    **ce_overrides: bool,
) -> ConstructValidityClaims:
    return ConstructValidityClaims(
        mastery_sense={
            "sense": "evaluative",
            "description": "test claim",
        },
        scope={
            "scope": scope,
            "justification": "test scope",
        },
        constitution={
            "position": "evidence_of_mastery",
            "justification": "test",
        },
        carving={
            "acknowledges_carving_indexed": False,
            "notes": "",
        },
        competing_explanations=CompetingExplanationChecks(**ce_overrides),
    )


# ---- Schema ---------------------------------------------------------------


class TestClaimsSchema:
    def test_well_formed_claims_validate(self) -> None:
        c = _minimal_claims()
        assert c.scope.scope == "items_in_benchmark"

    def test_missing_required_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConstructValidityClaims.model_validate({
                "mastery_sense": {"sense": "evaluative"},  # missing description
                "scope": {"scope": "items_in_benchmark", "justification": "x"},
                "constitution": {"position": "evidence_of_mastery", "justification": "x"},
                "carving": {"acknowledges_carving_indexed": False, "notes": ""},
            })

    def test_invalid_literal_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ConstructValidityClaims.model_validate({
                "mastery_sense": {"sense": "BOGUS", "description": "x"},
                "scope": {"scope": "items_in_benchmark", "justification": "x"},
                "constitution": {"position": "evidence_of_mastery", "justification": "x"},
                "carving": {"acknowledges_carving_indexed": False, "notes": ""},
            })

    def test_stub_has_all_required_fields(self) -> None:
        stub = ConstructValidityClaims.stub()
        json_text = stub.model_dump_json()
        # Parses back without error.
        reloaded = ConstructValidityClaims.model_validate(json.loads(json_text))
        assert reloaded.mastery_sense.sense == stub.mastery_sense.sense


# ---- Verdict computation --------------------------------------------------


class TestComputeVerdict:
    def test_all_required_checks_yields_defensible(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,
            sensitivity_sweep_run=True,
        )
        v = compute_verdict(claims)
        assert v.label == "defensible"

    def test_some_required_missing_yields_partial(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,  # 1 of 2 required for this scope
        )
        v = compute_verdict(claims)
        assert v.label == "partially_defensible"

    def test_majority_required_missing_yields_not_defensible(self) -> None:
        # general_capacity requires 8 checks; with none run, > half missing -> NOT.
        claims = _minimal_claims(scope="general_capacity")
        v = compute_verdict(claims)
        assert v.label == "not_defensible"

    def test_general_capacity_requires_carving_acknowledgement(self) -> None:
        # All 8 required checks run, but carving not acknowledged
        # at the general_capacity scope → NOT defensible (R19).
        claims = ConstructValidityClaims(
            mastery_sense={"sense": "standing", "description": "x"},
            scope={"scope": "general_capacity", "justification": "x"},
            constitution={"position": "evidence_of_mastery", "justification": "x"},
            carving={"acknowledges_carving_indexed": False, "notes": ""},
            competing_explanations=CompetingExplanationChecks(
                structural_check_run=True,
                sensitivity_sweep_run=True,
                paraphrase_sweep_run=True,
                cross_panel_check_run=True,
                held_out_items_used=True,
                training_data_separation_verified=True,
                cross_domain_comparison_run=True,
                replication_attempted=True,
            ),
        )
        v = compute_verdict(claims)
        assert v.label == "not_defensible"
        assert "carving" in " ".join(v.rationale).lower()

    def test_general_capacity_carving_with_empty_notes_still_fails_r19(self) -> None:
        claims = ConstructValidityClaims(
            mastery_sense={"sense": "standing", "description": "x"},
            scope={"scope": "general_capacity", "justification": "x"},
            constitution={"position": "evidence_of_mastery", "justification": "x"},
            carving={"acknowledges_carving_indexed": True, "notes": ""},
            competing_explanations=CompetingExplanationChecks(
                structural_check_run=True,
                sensitivity_sweep_run=True,
                paraphrase_sweep_run=True,
                cross_panel_check_run=True,
                held_out_items_used=True,
                training_data_separation_verified=True,
                cross_domain_comparison_run=True,
                replication_attempted=True,
            ),
        )
        v = compute_verdict(claims)
        assert v.label == "not_defensible"

    def test_general_capacity_fully_satisfied_is_defensible(self) -> None:
        claims = ConstructValidityClaims(
            mastery_sense={"sense": "standing", "description": "x"},
            scope={"scope": "general_capacity", "justification": "x"},
            constitution={"position": "evidence_of_mastery", "justification": "x"},
            carving={
                "acknowledges_carving_indexed": True,
                "notes": "Documented in §4.",
            },
            competing_explanations=CompetingExplanationChecks(
                structural_check_run=True,
                sensitivity_sweep_run=True,
                paraphrase_sweep_run=True,
                cross_panel_check_run=True,
                held_out_items_used=True,
                training_data_separation_verified=True,
                cross_domain_comparison_run=True,
                replication_attempted=True,
                test_retest_run=True,
            ),
            # v0.6.1 R22 second leg: declared identity criterion required at
            # scope >= domain_D_as_sampled when test_retest_run=True.
            reliability={
                "identity_criterion": {
                    "same_provider_model_id": True,
                    "cross_update_identity_asserted": True,
                    "same_scaffolding": True,
                    "unverifiable_caveats": "x",
                    "rationale": "x",
                }
            },
        )
        assert compute_verdict(claims).label == "defensible"


# ---- Markdown rendering ---------------------------------------------------


class TestMarkdownRendering:
    def _bench_and_eta(self) -> tuple[Benchmark, object]:  # type: ignore[type-arg]
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(
            bench, provider, config=EndorsementConfig(n_samples=1)
        )
        return bench, eta

    def _multi_analyst_bench_and_eta(self) -> tuple[Benchmark, object]:  # type: ignore[type-arg]
        """A 2-analyst variant of the stop-sign benchmark so the m<2
        audit cap (added in v0.5.3) doesn't trigger. Useful when a
        test wants to assert a clean defensible verdict at
        items_in_benchmark scope.
        """
        data = json.loads(STOP_SIGN_PATH.read_text())
        # Add a second analyst column duplicating the first.
        data["analysts"].append({"id": "second", "display_name": "second analyst"})
        for it in data["items"]:
            it["analyst_verdicts"].append(it["analyst_verdicts"][0])
        bench = Benchmark.model_validate(data)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(
            bench, provider, config=EndorsementConfig(n_samples=1)
        )
        return bench, eta

    def test_report_contains_all_sections(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
        )
        assert "# Construct-validity report" in md
        assert "## 1. Identity" in md
        assert "## 2. Summary metrics" in md
        assert "## 3. Construct-validity claims" in md
        assert "## 4. Evidence" in md
        assert "## 5. Unaddressed competing explanations" in md
        assert "## 6. Summary verdict" in md

    def test_report_lists_unaddressed_checks(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),  # no checks run
        )
        assert "paraphrase_sweep_run" in md
        assert "cross_panel_check_run" in md

    def test_report_integrates_structure_evidence_when_supplied(self) -> None:
        bench, eta = self._bench_and_eta()
        structure_report = {"total_anomalies": 0, "checks": []}
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(structural_check_run=True),
            structure_report=structure_report,
        )
        assert "0 anomalies flagged" in md
        # NOT SUPPLIED line for structure should be replaced.
        assert "Structural coherence checks** (R13): NOT SUPPLIED" not in md

    def test_report_shows_not_supplied_for_missing_evidence(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
        )
        assert "Structural coherence checks** (R13): NOT SUPPLIED" in md
        assert "Sensitivity sweep** (R11): NOT SUPPLIED" in md
        assert "Factor-effects model fit** (R7, R12): NOT SUPPLIED" in md

    def test_summary_verdict_renders_with_badge(self) -> None:
        bench, eta = self._multi_analyst_bench_and_eta()
        # All required checks run + m=2 (passes panel-size audit) → defensible.
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(
                structural_check_run=True,
                sensitivity_sweep_run=True,
            ),
        )
        assert "✅" in md
        assert "defensible" in md.lower()

    def test_panel_size_one_caps_verdict_at_partially(self) -> None:
        """Regression for review issue #1(c): a single-analyst benchmark
        with all required checks marked True must not earn a defensible
        verdict. The reviewer's concern: agreement with one person
        cannot inherit the convergent-validity guarantee that the green
        badge implies. The v0.5.3 audit cap downgrades to partially.
        """
        bench, eta = self._bench_and_eta()  # m=1 stop-sign
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(
                structural_check_run=True,
                sensitivity_sweep_run=True,
            ),
        )
        verdict_section = md.split("## 6. Summary verdict")[1]
        assert "⚠️" in verdict_section
        assert "m=1" in verdict_section

    def test_structural_anomaly_caps_verdict_at_partially(self) -> None:
        """Regression for review issue #1(a): a structural anomaly in
        the supplied artifact must downgrade the verdict even when
        structural_check_run=True. Pre-v0.5.3: clean ✅ on a failed
        structural check.
        """
        bench, eta = self._multi_analyst_bench_and_eta()
        structure_report = {
            "total_anomalies": 1,
            "checks": [
                {
                    "name": "rsr_role_consistency",
                    "anomalies": [
                        {
                            "item_id": "row-2",
                            "expected": "GOOD",
                            "actual": "BAD",
                            "explanation": "irrelevant-addition flipped under a defeater",
                        },
                    ],
                },
            ],
        }
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(
                structural_check_run=True,
                sensitivity_sweep_run=True,
            ),
            structure_report=structure_report,
        )
        verdict_section = md.split("## 6. Summary verdict")[1]
        assert "⚠️" in verdict_section
        assert "1 anomaly" in verdict_section

    # ---- v0.13.0: §2 restructure + multi-interval rendering ---------------
    #
    # All five tests below exercise the new §2 layout. The Agreement
    # subhead carries cov/κ_C/κ_F/κ_F* (unchanged content, just under a
    # new `### Agreement` parent). The Reliability (R22) subhead either
    # carries (a) "Not measured ..." when no artifact supplied, (b) the
    # v0.11.0+ single-bullet `Test-retest κ` line for a single
    # RetestResult shape, or (c) a per-interval markdown table +
    # overall-verdict line for a MultiIntervalRetestResult shape.
    # Shape detection is by presence of a `pairs` list on the artifact.

    @staticmethod
    def _single_retest_artifact(
        *, kappa: float = 1.0, n_items: int = 4
    ) -> dict[str, object]:
        """A minimal v0.11.0+ RetestResult-shaped dict for rendering tests."""
        return {
            "schema_version": "1.0",
            "framework_version": "0.13.0",
            "run_id_a": "run-a",
            "run_id_b": "run-b",
            "benchmark_id": "stop_sign_example",
            "benchmark_hash": "abc",
            "n_items": n_items,
            "test_retest_kappa": kappa,
            "flip_rate": 0.0,
            "stability_verdict": (
                "Test-retest reliability is stable."
            ),
            "flipped_items": [],
            "item_deltas": [],
        }

    @classmethod
    def _multi_retest_artifact(
        cls,
        *,
        intervals: tuple[int, ...] = (0, 86400, 604800),
        per_pair_verdicts: tuple[str, ...] = (
            "Test-retest reliability is stable.",
            "Test-retest reliability is moderately stable.",
            "Test-retest reliability is substantively unstable.",
        ),
        per_pair_kappas: tuple[float | None, ...] = (1.0, 0.65, 0.20),
    ) -> dict[str, object]:
        """A minimal v0.12.0+ MultiIntervalRetestResult-shaped dict.

        Each entry in ``intervals`` becomes one pair, anchored on the
        same baseline. Defaults to a stable→moderately→unstable
        progression so worst-case selection has something to bite on.
        """
        assert len(intervals) == len(per_pair_verdicts) == len(per_pair_kappas)
        pairs: list[dict[str, object]] = []
        for i, (interval, verdict, kappa) in enumerate(
            zip(intervals, per_pair_verdicts, per_pair_kappas, strict=True)
        ):
            pairs.append(
                {
                    "interval_s": interval,
                    "run_id": f"run-{i + 1}",
                    "retest": {
                        "schema_version": "1.0",
                        "framework_version": "0.13.0",
                        "run_id_a": "run-0",
                        "run_id_b": f"run-{i + 1}",
                        "benchmark_id": "stop_sign_example",
                        "benchmark_hash": "abc",
                        "n_items": 4,
                        "test_retest_kappa": kappa,
                        "flip_rate": 0.0 if kappa == 1.0 else 0.25,
                        "stability_verdict": verdict,
                        "flipped_items": [],
                        "item_deltas": [],
                    },
                }
            )
        return {
            "schema_version": "1.0",
            "framework_version": "0.13.0",
            "benchmark_id": "stop_sign_example",
            "benchmark_hash": "abc",
            "baseline_run_id": "run-0",
            "pairs": pairs,
        }

    def test_section_2_has_agreement_and_reliability_subheads(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
            retest_result=self._single_retest_artifact(),
        )
        # The two §2 subheads must both exist, in the documented order
        # (Agreement first because κ_C / κ_F are the per-evaluation
        # primary; Reliability second because it relates two evaluations).
        section_2 = md.split("## 2. Summary metrics")[1].split("## 3.")[0]
        assert "### Agreement" in section_2
        assert "### Reliability (R22)" in section_2
        assert section_2.index("### Agreement") < section_2.index(
            "### Reliability (R22)"
        )

    def test_section_2_reliability_renders_single_interval_bullet(self) -> None:
        bench, eta = self._bench_and_eta()
        artifact = self._single_retest_artifact(kappa=0.85)
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
            retest_result=artifact,
        )
        reliability = md.split("### Reliability (R22)")[1].split("## 3.")[0]
        # Verbatim v0.12.0 bullet text — backward-compat regression guard.
        assert "**Test-retest κ (R22)**" in reliability
        assert "+0.8500" in reliability
        # Multi-interval table elements must NOT appear under the
        # single-interval path.
        assert "Interval (s)" not in reliability
        assert "Baseline run" not in reliability

    def test_section_2_reliability_renders_multi_interval_table(self) -> None:
        bench, eta = self._bench_and_eta()
        artifact = self._multi_retest_artifact()
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
            retest_result=artifact,
        )
        reliability = md.split("### Reliability (R22)")[1].split("## 3.")[0]
        assert "**Baseline run**: `run-0`" in reliability
        # Per-interval table with the documented column header row.
        assert (
            "| Interval (s) | Later run | κ vs baseline | Flips | Verdict |"
            in reliability
        )
        # Three data rows for three intervals.
        assert "| 0 |" in reliability
        assert "| 86400 |" in reliability
        assert "| 604800 |" in reliability
        # Overall-verdict line is rendered.
        assert "**Overall verdict**" in reliability

    def test_section_2_reliability_when_no_retest_supplied(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
            retest_result=None,
        )
        reliability = md.split("### Reliability (R22)")[1].split("## 3.")[0]
        # A missing R22 capture is itself a construct-validity signal —
        # render an explicit "not measured" bullet instead of leaving
        # the subhead empty.
        assert "Not measured" in reliability
        assert "R22 not run" in reliability

    def test_section_2_reliability_worst_case_overall_verdict(self) -> None:
        # Back-to-back stable, day-apart stable, week-apart substantively
        # unstable. Overall verdict must reflect the worst case, NOT the
        # back-to-back result — that's the methodological commitment
        # documented in CLAUDE.md (worst-case across intervals).
        bench, eta = self._bench_and_eta()
        artifact = self._multi_retest_artifact(
            intervals=(0, 86400, 604800),
            per_pair_verdicts=(
                "Test-retest reliability is stable.",
                "Test-retest reliability is stable.",
                "Test-retest reliability is substantively unstable.",
            ),
            per_pair_kappas=(1.0, 1.0, 0.10),
        )
        md = render_markdown(
            evaluation=eta,  # type: ignore[arg-type]
            benchmark=bench,
            claims=_minimal_claims(),
            retest_result=artifact,
        )
        reliability = md.split("### Reliability (R22)")[1].split("## 3.")[0]
        overall_line = [
            ln for ln in reliability.splitlines()
            if "**Overall verdict**" in ln
        ][0]
        assert "substantively unstable" in overall_line
        # Worst-case line must cite the driving interval explicitly so
        # the analyst can see which time scale broke the claim.
        assert "604800" in overall_line


# ---- CLI ------------------------------------------------------------------


class TestReportCLI:
    def test_init_claims_writes_stub(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from infereval.cli.main import cli

        target = tmp_path / "claims.json"
        runner = CliRunner()
        result = runner.invoke(cli, ["report", "--init-claims", str(target)])
        assert result.exit_code == 0, result.output
        assert target.exists()
        # Stub parses as a valid claims file.
        data = json.loads(target.read_text(encoding="utf-8"))
        claims = ConstructValidityClaims.model_validate(data)
        assert claims.mastery_sense.sense == "evaluative"

    def test_full_report_against_stop_sign(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from infereval.cli.main import cli

        # First produce an evaluation file via the test fixture pattern.
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        eta_path = tmp_path / "eta.json"
        eta.dump(eta_path)

        claims_path = tmp_path / "claims.json"
        claims_path.write_text(_minimal_claims().model_dump_json(), encoding="utf-8")

        out_path = tmp_path / "report.md"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "report",
            "--evaluation", str(eta_path),
            "--benchmark", str(STOP_SIGN_PATH),
            "--claims", str(claims_path),
            "-o", str(out_path),
        ])
        assert result.exit_code == 0, result.output
        text = out_path.read_text(encoding="utf-8")
        assert "Construct-validity report" in text
        assert "Mastery claim" in text

    def test_missing_required_inputs_errors(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from infereval.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["report"])
        assert result.exit_code != 0
        assert "required" in result.output.lower()

    def test_mismatched_benchmark_id_rejected(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from infereval.cli.main import cli

        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        eta_path = tmp_path / "eta.json"
        eta.dump(eta_path)

        # Write a different benchmark with id "other".
        other = bench.model_copy(update={"id": "other-bench"})
        other_path = tmp_path / "other.json"
        other.dump(other_path)

        claims_path = tmp_path / "claims.json"
        claims_path.write_text(_minimal_claims().model_dump_json(), encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "report",
            "--evaluation", str(eta_path),
            "--benchmark", str(other_path),
            "--claims", str(claims_path),
        ])
        assert result.exit_code != 0
        assert "benchmark_id" in result.output


# ---- Phase 3.2: negative-results aggregation -----------------------------


class TestCollectNegativeFindings:
    """Auto-collection from Phase 2 artifacts (Issue #46, Phase 3.2)."""

    def test_no_artifacts_returns_empty(self) -> None:
        from infereval.report import collect_negative_findings
        assert collect_negative_findings() == []

    def test_structure_anomalies_surface(self) -> None:
        from infereval.report import collect_negative_findings
        sr = {
            "checks": [
                {
                    "name": "rsr_role_consistency",
                    "anomalies": [
                        {"item_id": "a9", "explanation": "role mismatch"},
                    ],
                }
            ]
        }
        findings = collect_negative_findings(structure_report=sr)
        assert len(findings) == 1
        assert findings[0].source == "structure"
        assert "a9" in findings[0].summary

    def test_sweep_instability_surfaces(self) -> None:
        from infereval.report import collect_negative_findings
        sweep = {
            "parameter": "n_samples",
            "stability_verdict": "κ_C range = 0.062; agreement is moderately sensitive",
        }
        findings = collect_negative_findings(sweep_summary=sweep)
        assert len(findings) == 1
        assert findings[0].source == "sweep"

    def test_stable_sweep_not_flagged(self) -> None:
        from infereval.report import collect_negative_findings
        sweep = {
            "parameter": "n_samples",
            "stability_verdict": "κ_C range = 0.005; agreement is stable across the sweep range.",
        }
        findings = collect_negative_findings(sweep_summary=sweep)
        assert findings == []

    def test_model_fit_null_factors_surface(self) -> None:
        from infereval.report import collect_negative_findings
        mf = {"factor_wald": {"role": 0.001, "para": 0.42}}
        findings = collect_negative_findings(model_fit=mf)
        names = [f.summary for f in findings]
        # role is significant -> not flagged; para is null -> flagged.
        assert any("para" in n for n in names)
        assert not any("role" in n for n in names)

    def test_all_significant_factors_yields_no_findings(self) -> None:
        from infereval.report import collect_negative_findings
        mf = {"factor_wald": {"role": 0.001, "para": 0.001}}
        findings = collect_negative_findings(model_fit=mf)
        assert findings == []

    def test_factor_kinds_label_substantive_null_as_weakening(self) -> None:
        """v0.5.3: factor_kinds={"role": "substantive"} should label a
        null result on the substantive factor as a weakening of the claim.
        """
        from infereval.report import collect_negative_findings
        mf = {"factor_wald": {"role": 0.42}}
        findings = collect_negative_findings(
            model_fit=mf, factor_kinds={"role": "substantive"},
        )
        assert len(findings) == 1
        assert "weakens the mastery claim" in findings[0].summary

    def test_factor_kinds_label_controlled_null_as_strengthening(self) -> None:
        """v0.5.3: factor_kinds={"paraphrase": "experimentally_controlled"}
        should label a null result as a *strengthening* of the claim
        (content-not-form behavior is the wanted outcome on a controlled
        factor).
        """
        from infereval.report import collect_negative_findings
        mf = {"factor_wald": {"paraphrase": 0.42}}
        findings = collect_negative_findings(
            model_fit=mf,
            factor_kinds={"paraphrase": "experimentally_controlled"},
        )
        assert len(findings) == 1
        assert "strengthens the mastery claim" in findings[0].summary

    def test_factor_kinds_omitted_keeps_neutral_summary(self) -> None:
        """v0.5.3 backwards compat: factors without a factor_kind entry
        get the historical neutral summary.
        """
        from infereval.report import collect_negative_findings
        mf = {"factor_wald": {"role": 0.42}}
        findings = collect_negative_findings(model_fit=mf, factor_kinds={})
        assert len(findings) == 1
        assert "weakens the mastery claim" not in findings[0].summary
        assert "strengthens the mastery claim" not in findings[0].summary

    # ---- v0.13.0: multi-interval pooling ----------------------------------
    #
    # collect_negative_findings, when given a MultiIntervalRetestResult
    # artifact, must (a) emit one corpus-level finding per non-stable
    # pair (NOT one per pair regardless of verdict — stable pairs are
    # positive evidence) and (b) pool flipped items across pairs by
    # item_id so an item that flips in three pairs is one bullet, not
    # three, with a "[first seen at interval Ns]" annotation pointing
    # at the smallest interval where it appeared.

    @staticmethod
    def _multi_retest_artifact_with_pairs(
        pairs: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "framework_version": "0.13.0",
            "benchmark_id": "stop_sign_example",
            "benchmark_hash": "abc",
            "baseline_run_id": "run-0",
            "pairs": pairs,
        }

    @staticmethod
    def _pair(
        *,
        interval_s: int,
        run_id: str,
        verdict: str,
        kappa: float | None = 0.5,
        flip_rate: float = 0.0,
        flipped_items: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        return {
            "interval_s": interval_s,
            "run_id": run_id,
            "retest": {
                "stability_verdict": verdict,
                "test_retest_kappa": kappa,
                "flip_rate": flip_rate,
                "flipped_items": flipped_items or [],
            },
        }

    def test_multi_interval_emits_one_finding_per_non_stable_pair(self) -> None:
        from infereval.report import collect_negative_findings
        artifact = self._multi_retest_artifact_with_pairs([
            self._pair(
                interval_s=0,
                run_id="run-1",
                verdict="test-retest reliability is stable",
                kappa=1.0,
            ),
            self._pair(
                interval_s=86400,
                run_id="run-2",
                verdict=(
                    "test-retest reliability is moderately stable "
                    "(κ = +0.700)"
                ),
                kappa=0.7,
                flip_rate=0.15,
            ),
            self._pair(
                interval_s=604800,
                run_id="run-3",
                verdict=(
                    "test-retest reliability is substantively unstable "
                    "(κ = +0.200)"
                ),
                kappa=0.2,
                flip_rate=0.4,
            ),
        ])
        findings = collect_negative_findings(retest_result=artifact)
        # Exactly two corpus findings (stable pair contributes nothing).
        corpus = [f for f in findings if "at interval" in f.summary]
        assert len(corpus) == 2
        assert any("86400s" in f.summary for f in corpus)
        assert any("604800s" in f.summary for f in corpus)
        # Stable pair must NOT show up.
        assert not any("interval 0s" in f.summary for f in corpus)

    def test_multi_interval_pools_flipped_items_across_pairs(self) -> None:
        """Same item_id flips in pair 1 (interval=0) and pair 2
        (interval=86400). One bullet must surface, annotated with the
        earlier interval as 'first seen'."""
        from infereval.report import collect_negative_findings
        same_flip = {"item_id": "row-3", "verdict_a": "good", "verdict_b": "bad"}
        artifact = self._multi_retest_artifact_with_pairs([
            self._pair(
                interval_s=0,
                run_id="run-1",
                verdict=(
                    "test-retest reliability is moderately stable "
                    "(κ = +0.700)"
                ),
                kappa=0.7,
                flipped_items=[same_flip],
            ),
            self._pair(
                interval_s=86400,
                run_id="run-2",
                verdict=(
                    "test-retest reliability is moderately stable "
                    "(κ = +0.700)"
                ),
                kappa=0.7,
                flipped_items=[same_flip],
            ),
        ])
        findings = collect_negative_findings(retest_result=artifact)
        per_item = [f for f in findings if "row-3" in f.summary]
        assert len(per_item) == 1
        assert "first seen at interval 0s" in per_item[0].summary

    def test_multi_interval_flip_cap_still_applies(self) -> None:
        """Pool of >50 unique items still caps at 50 bullets with a
        '... and X more' summary. Same shape as single-interval cap."""
        from infereval.report import collect_negative_findings
        many_flips = [
            {"item_id": f"row-{i}", "verdict_a": "good", "verdict_b": "bad"}
            for i in range(75)
        ]
        artifact = self._multi_retest_artifact_with_pairs([
            self._pair(
                interval_s=0,
                run_id="run-1",
                verdict=(
                    "test-retest reliability is substantively unstable "
                    "(κ = +0.100)"
                ),
                kappa=0.1,
                flip_rate=0.5,
                flipped_items=many_flips,
            ),
        ])
        findings = collect_negative_findings(retest_result=artifact)
        per_item = [
            f for f in findings
            if "row-" in f.summary and "flipped good → bad" in f.summary
        ]
        assert len(per_item) == 50
        # Tail summary present.
        assert any("25 more flipped items" in f.summary for f in findings)


# ---- compute_verdict audit caps (v0.5.3 review fix #1) -------------------


class TestComputeVerdictAuditCaps:
    """Direct unit tests for the audit caps wired into compute_verdict
    in v0.5.3 (addressing review issue #1). The cap activates when the
    relevant artifact is supplied; without artifacts the function falls
    back to the claims-only verdict with an unaudited rationale line.
    """

    def test_no_artifacts_adds_unaudited_rationale(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,
            sensitivity_sweep_run=True,
        )
        v = compute_verdict(claims)  # no artifacts
        assert v.label == "defensible"
        assert any("unaudited" in r.lower() for r in v.rationale)

    def test_structural_anomaly_caps_at_partially(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,
            sensitivity_sweep_run=True,
        )
        sr = {
            "checks": [
                {"name": "rsr_role_consistency", "anomalies": [
                    {"item_id": "a9", "explanation": "x"},
                ]},
            ],
        }
        v = compute_verdict(claims, structure_report=sr)
        assert v.label == "partially_defensible"
        assert any("anomaly" in r or "anomalies" in r for r in v.rationale)

    def test_structural_clean_does_not_cap(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,
            sensitivity_sweep_run=True,
        )
        sr = {"checks": [{"name": "rsr_role_consistency", "anomalies": []}]}
        # No benchmark supplied → m<2 cap doesn't activate either.
        v = compute_verdict(claims, structure_report=sr)
        assert v.label == "defensible"

    def test_single_analyst_benchmark_caps_at_partially(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,
            sensitivity_sweep_run=True,
        )
        bench = Benchmark.load(STOP_SIGN_PATH)  # m=1
        v = compute_verdict(claims, benchmark=bench)
        assert v.label == "partially_defensible"
        assert any("m=1" in r for r in v.rationale)

    def test_two_analyst_benchmark_passes_panel_audit(self) -> None:
        claims = _minimal_claims(
            scope="items_in_benchmark",
            structural_check_run=True,
            sensitivity_sweep_run=True,
        )
        data = json.loads(STOP_SIGN_PATH.read_text())
        data["analysts"].append({"id": "second", "display_name": "s"})
        for it in data["items"]:
            it["analyst_verdicts"].append(it["analyst_verdicts"][0])
        bench = Benchmark.model_validate(data)
        v = compute_verdict(claims, benchmark=bench)
        assert v.label == "defensible"
        assert "m=2" in v.one_liner

    def test_panel_cap_does_not_apply_to_broader_scopes(self) -> None:
        """The panel-size cap only fires at items_in_benchmark scope.
        At broader scopes, other competing-explanation checks
        (cross_panel_check_run, etc.) already need to be marked True
        to reach defensible, so the panel-size signal is redundant.
        """
        claims = ConstructValidityClaims(
            mastery_sense={"sense": "standing", "description": "x"},
            scope={"scope": "domain_D_as_sampled", "justification": "x"},
            constitution={"position": "evidence_of_mastery", "justification": "x"},
            carving={"acknowledges_carving_indexed": True, "notes": "x"},
            competing_explanations=CompetingExplanationChecks(
                structural_check_run=True,
                sensitivity_sweep_run=True,
                paraphrase_sweep_run=True,
                cross_panel_check_run=True,
                held_out_items_used=True,
                test_retest_run=True,
            ),
            # v0.6.1 R22 second leg: declared identity criterion required at
            # scope >= domain_D_as_sampled when test_retest_run=True.
            reliability={
                "identity_criterion": {
                    "same_provider_model_id": True,
                    "cross_update_identity_asserted": True,
                    "same_scaffolding": True,
                    "unverifiable_caveats": "x",
                    "rationale": "x",
                }
            },
        )
        bench = Benchmark.load(STOP_SIGN_PATH)  # m=1
        v = compute_verdict(claims, benchmark=bench)
        # No cap (m<2 only matters at items_in_benchmark); defensible.
        assert v.label == "defensible"


class TestNegativeFindingsRendering:
    """Section 4b rendering, including the --suppress-negatives behavior."""

    def _bench_and_eta(self) -> tuple[Benchmark, object]:
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        return bench, eta

    def _multi_analyst_bench_and_eta(self) -> tuple[Benchmark, object]:
        """2-analyst variant so the v0.5.3 m<2 cap doesn't compound."""
        data = json.loads(STOP_SIGN_PATH.read_text())
        data["analysts"].append({"id": "second", "display_name": "second"})
        for it in data["items"]:
            it["analyst_verdicts"].append(it["analyst_verdicts"][0])
        bench = Benchmark.model_validate(data)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        return bench, eta

    def test_no_artifacts_renders_nothing_to_scan(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta, benchmark=bench, claims=_minimal_claims(),
        )
        assert "## 4b. Negative findings" in md
        assert "No Phase 2 artifacts supplied" in md

    def test_clean_artifacts_render_no_negatives_detected(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta, benchmark=bench, claims=_minimal_claims(),
            structure_report={"checks": [], "total_anomalies": 0},
            sweep_summary={"parameter": "n_samples", "stability_verdict": "stable"},
            model_fit={"factor_wald": {"role": 0.001}},
        )
        assert "No negative findings detected" in md

    def test_anomalies_render_with_explanation(self) -> None:
        bench, eta = self._bench_and_eta()
        sr = {
            "checks": [
                {
                    "name": "rsr_role_consistency",
                    "anomalies": [
                        {"item_id": "a9", "explanation": "role mismatch"}
                    ],
                }
            ]
        }
        md = render_markdown(
            evaluation=eta, benchmark=bench, claims=_minimal_claims(),
            structure_report=sr,
        )
        assert "### Structural anomalies (1 flagged)" in md
        assert "a9" in md
        assert "role mismatch" in md

    def test_suppress_negatives_replaces_body(self) -> None:
        bench, eta = self._bench_and_eta()
        sr = {
            "checks": [
                {"name": "x", "anomalies": [{"item_id": "i1", "explanation": "y"}]}
            ]
        }
        md = render_markdown(
            evaluation=eta, benchmark=bench, claims=_minimal_claims(),
            structure_report=sr,
            suppress_negatives=True,
        )
        # The body is replaced with the suppression banner.
        assert "Suppressed via `--suppress-negatives`" in md
        # Anomaly content does NOT leak through.
        assert "### Structural anomalies" not in md

    def test_suppress_negatives_adds_header_warning(self) -> None:
        bench, eta = self._bench_and_eta()
        md = render_markdown(
            evaluation=eta, benchmark=bench, claims=_minimal_claims(),
            suppress_negatives=True,
        )
        # Header warning appears near the top.
        assert "Negative-findings suppression: ENABLED" in md

    def test_suppress_negatives_downgrades_verdict_one_tier(self) -> None:
        # Use a 2-analyst benchmark so the v0.5.3 m<2 cap doesn't
        # compound — we want to isolate the suppression downgrade.
        bench, eta = self._multi_analyst_bench_and_eta()
        # All checks run -> would be defensible -> downgraded to partially.
        md = render_markdown(
            evaluation=eta, benchmark=bench,
            claims=_minimal_claims(
                structural_check_run=True, sensitivity_sweep_run=True
            ),
            suppress_negatives=True,
        )
        # Verdict body says "downgraded one tier"
        assert "downgraded one tier" in md
        # Badge is ⚠️ (partially), not ✅ (defensible).
        verdict_section = md.split("## 6. Summary verdict")[1]
        assert "⚠️" in verdict_section
        # No "✅" appears in the verdict section (the rest of the doc shouldn't have one either).
        assert "✅" not in verdict_section


class TestSuppressNegativesCLI:
    def test_cli_flag_writes_suppression_banner(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from infereval.cli.main import cli

        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 12)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        eta_path = tmp_path / "eta.json"
        eta.dump(eta_path)

        claims_path = tmp_path / "claims.json"
        claims_path.write_text(_minimal_claims().model_dump_json(), encoding="utf-8")

        out_path = tmp_path / "report.md"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "report",
            "--evaluation", str(eta_path),
            "--benchmark", str(STOP_SIGN_PATH),
            "--claims", str(claims_path),
            "-o", str(out_path),
            "--suppress-negatives",
        ])
        assert result.exit_code == 0, result.output
        text = out_path.read_text(encoding="utf-8")
        assert "Negative-findings suppression: ENABLED" in text
        assert "Suppressed via `--suppress-negatives`" in text
