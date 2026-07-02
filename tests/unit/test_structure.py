"""Tests for ``infereval.structure`` — Phase 2.1 structural coherence checks."""

from __future__ import annotations

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ScriptedProvider
from infereval.structure import (
    base_case_stability_check,
    containment_closure_check,
    rsr_role_consistency_check,
    run_all_checks,
)


def _bench(items: list[dict], analysts: list[dict] | None = None) -> Benchmark:
    return Benchmark.model_validate({
        "schema_version": "1.0",
        "id": "struct-test",
        "bearers": {
            "p": {"expression": "P"},
            "q": {"expression": "Q"},
            "r": {"expression": "R"},
            "s": {"expression": "S"},
        },
        "analysts": analysts or [{"id": "a"}],
        "items": items,
    })


# ---- Containment ----------------------------------------------------------


class TestContainmentClosure:
    def test_no_self_implications_yields_zero(self) -> None:
        bench = _bench([
            {"id": "i1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"]},
        ])
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD"]),
                       config=EndorsementConfig(n_samples=1))
        check = containment_closure_check(eta, bench)
        assert check.items_checked == 0
        assert check.rate is None  # nothing in scope

    def test_self_implication_counted(self) -> None:
        # Γ ∩ Δ ≠ ∅: bearer 'p' appears in both premises and conclusions.
        bench = _bench([
            {"id": "i1", "premises": ["p", "q"], "conclusions": ["p"],
             "analyst_verdicts": ["good"]},
        ])
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD"]),
                       config=EndorsementConfig(n_samples=1))
        check = containment_closure_check(eta, bench)
        # By construction, the self-implication is in I_M.
        assert check.items_checked == 1
        assert check.items_satisfying == 1
        assert check.rate == 1.0
        assert check.anomalies == ()


# ---- RSR role consistency -------------------------------------------------


class TestRSRRoleConsistency:
    @staticmethod
    def _rsr_bench(role_for_i2: str, base_verdict_target: str = "good") -> Benchmark:
        """Two-item benchmark sharing a target — i1 base, i2 role-tagged."""
        return _bench([
            {
                "id": "i1",
                "premises": ["p"],
                "conclusions": ["q"],
                "analyst_verdicts": ["good" if base_verdict_target == "good" else "bad"],
                "tags": ["base-inference"],
                "rsr_target": {"X": ["p"], "A": ["q"]},
            },
            {
                "id": "i2",
                "premises": ["p", "r"],
                "conclusions": ["q"],
                "analyst_verdicts": ["good"],  # not consulted by the check
                "tags": [role_for_i2],
                "rsr_target": {"X": ["p"], "A": ["q"]},
            },
        ])

    def _eval_with_verdicts(self, bench: Benchmark, base_verdict: str, role_verdict: str):
        # ScriptedProvider cycles, so the responses are placed in benchmark
        # item order. The benchmark above orders i1 then i2.
        provider = ScriptedProvider(responses=[base_verdict.upper(), role_verdict.upper()])
        return evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=1, question_form="support"),
        )

    def test_supporter_on_good_base_consistent_when_good(self) -> None:
        bench = self._rsr_bench("supporter")
        eta = self._eval_with_verdicts(bench, "good", "good")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 1
        assert check.items_satisfying == 1
        assert not check.anomalies

    def test_supporter_on_good_base_anomalous_when_bad(self) -> None:
        bench = self._rsr_bench("supporter")
        eta = self._eval_with_verdicts(bench, "good", "bad")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 1
        assert check.items_satisfying == 0
        assert len(check.anomalies) == 1
        assert check.anomalies[0].item_id == "i2"
        assert "expected good" in check.anomalies[0].explanation or check.anomalies[0].expected == "good"

    def test_defeater_on_good_base_consistent_when_bad(self) -> None:
        bench = self._rsr_bench("defeater")
        eta = self._eval_with_verdicts(bench, "good", "bad")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 1
        assert check.items_satisfying == 1

    def test_defeater_on_good_base_anomalous_when_good(self) -> None:
        bench = self._rsr_bench("defeater")
        eta = self._eval_with_verdicts(bench, "good", "good")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 1
        assert check.items_satisfying == 0
        assert len(check.anomalies) == 1

    def test_irrelevant_addition_preserves_verdict(self) -> None:
        bench = self._rsr_bench("irrelevant-addition")
        eta = self._eval_with_verdicts(bench, "good", "good")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 1
        assert check.items_satisfying == 1

        # Same role, base BAD -> expected BAD; if model says GOOD, anomaly.
        bench2 = self._rsr_bench("irrelevant-addition", base_verdict_target="bad")
        eta2 = self._eval_with_verdicts(bench2, "bad", "good")
        check2 = rsr_role_consistency_check(eta2, bench2)
        assert check2.items_checked == 1
        assert check2.items_satisfying == 0
        assert len(check2.anomalies) == 1

    def test_supporter_skipped_on_bad_base(self) -> None:
        # Supporting a BAD base is conceptually out of scope; the role
        # makes no prediction, so the check excludes the item entirely.
        bench = self._rsr_bench("supporter", base_verdict_target="bad")
        eta = self._eval_with_verdicts(bench, "bad", "good")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 0

    def test_role_item_abstain_skipped(self) -> None:
        # If the model abstains on the role-tagged item, the check
        # excludes it (role's prediction is undefined relative to abstain).
        bench = self._rsr_bench("supporter")
        eta = self._eval_with_verdicts(bench, "good", "ABSTAIN")
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 0

    def test_no_base_inference_yields_no_check(self) -> None:
        # Role-tagged item but no base-inference reference -> nothing to compare.
        bench = _bench([
            {"id": "i1", "premises": ["p", "r"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["supporter"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
        ])
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD"]),
                       config=EndorsementConfig(n_samples=1))
        check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 0


# ---- Base-case stability ---------------------------------------------------


class TestBaseCaseStability:
    def test_no_multi_base_target_vacuously_satisfied(self) -> None:
        bench = _bench([
            {"id": "i1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
        ])
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD"]),
                       config=EndorsementConfig(n_samples=1))
        check = base_case_stability_check(eta, bench)
        assert check.items_checked == 0

    def test_two_base_inferences_with_same_verdict(self) -> None:
        # Same target, two base-inference items, model agrees on both.
        bench = _bench([
            {"id": "i1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
            {"id": "i2", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
        ])
        # Both items have the same premises so technically duplicate;
        # but the schema allows distinct ids. ScriptedProvider returns
        # the same verdict per call.
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD"]),
                       config=EndorsementConfig(n_samples=1))
        check = base_case_stability_check(eta, bench)
        assert check.items_checked == 2
        assert check.items_satisfying == 2
        assert not check.anomalies

    def test_two_base_inferences_with_different_verdicts(self) -> None:
        bench = _bench([
            {"id": "i1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
            # Same RSR target but slightly different premises to get a
            # different scripted response.
            {"id": "i2", "premises": ["p", "s"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
        ])
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD", "BAD"]),
                       config=EndorsementConfig(n_samples=1, question_form="support"))
        check = base_case_stability_check(eta, bench)
        assert check.items_checked == 2
        assert check.items_satisfying == 0
        assert len(check.anomalies) == 2


# ---- Integrated report ---------------------------------------------------


class TestRunAllChecks:
    def test_bundle_returns_all_checks(self) -> None:
        bench = _bench([
            {"id": "i1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"]},
        ])
        eta = evaluate(bench, ScriptedProvider(responses=["GOOD"]),
                       config=EndorsementConfig(n_samples=1))
        report = run_all_checks(eta, bench)
        assert len(report.checks) == 4
        check_names = {c.name for c in report.checks}
        assert check_names == {
            "containment_closure",
            "rsr_role_consistency",
            "base_case_stability",
            "thin_margin_agreement",
        }
        assert report.evaluation_id == eta.id
        assert report.benchmark_id == bench.id
        assert report.all_satisfied  # no anomalies on a trivial benchmark


# ---- Partial-evaluation guard (v0.5.3 review fix) ------------------------


class TestPartialEvaluationGuard:
    """Regression for the review's issue #2: the structural checks must
    not raise KeyError when the evaluation is missing items that the
    benchmark carries an rsr_target for. This happens in real flows —
    a `--paraphrase-cycle` run emits per-variant evaluations, and any
    re-run on a tag subset will leave items missing too. The contract
    matches the metrics module: skip missing items with a warning,
    don't raise.
    """

    def _two_base_one_role_bench(self) -> Benchmark:
        return _bench([
            {"id": "b1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
            {"id": "b2", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["base-inference"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
            {"id": "r1", "premises": ["p", "r"], "conclusions": ["q"],
             "analyst_verdicts": ["good"], "tags": ["irrelevant-addition"],
             "rsr_target": {"X": ["p"], "A": ["q"]}},
        ])

    def _partial_eval(self, bench: Benchmark, present_ids: set[str], verdicts: list[str]):
        """Build an evaluation that contains only items in present_ids."""
        from infereval.evaluation import Evaluation, EvaluationItem, ModelInfo
        from infereval.types import Verdict

        items = []
        v_iter = iter(verdicts)
        for it in bench.items:
            if it.id not in present_ids:
                continue
            v = Verdict(next(v_iter))
            items.append(EvaluationItem(
                id=it.id,
                premises=list(it.premises),
                conclusions=list(it.conclusions),
                analyst_verdicts=list(it.analyst_verdicts),
                tags=list(it.tags),
                model_verdict=v,
                samples=[],
            ))
        return Evaluation(
            id="partial-test", benchmark_id=bench.id,
            model=ModelInfo(provider="mock", model_id="scripted-mock-v1"),
            items=items,
        )

    def test_rsr_role_consistency_skips_missing_role_item(self, caplog) -> None:
        bench = self._two_base_one_role_bench()
        # Drop r1 — the role-tagged item is absent from the evaluation.
        eta = self._partial_eval(bench, {"b1", "b2"}, ["good", "good"])
        with caplog.at_level("WARNING"):
            check = rsr_role_consistency_check(eta, bench)
        assert check.items_checked == 0  # role-tagged item was skipped
        assert "r1" in caplog.text
        assert "absent from evaluation" in caplog.text

    def test_rsr_role_consistency_skips_missing_base_item(self, caplog) -> None:
        bench = self._two_base_one_role_bench()
        # Drop b1 — one of two base-inference items is absent.
        eta = self._partial_eval(bench, {"b2", "r1"}, ["good", "good"])
        with caplog.at_level("WARNING"):
            check = rsr_role_consistency_check(eta, bench)
        # b2 is the only base present; the role check proceeds against
        # its verdict. r1 (irrelevant-addition) is GOOD as expected.
        assert check.items_checked == 1
        assert check.items_satisfying == 1
        assert "b1" in caplog.text

    def test_base_case_stability_skips_missing_base_item(self, caplog) -> None:
        bench = self._two_base_one_role_bench()
        # Drop b1 — only one base remains, so the stability check has
        # nothing to compare against.
        eta = self._partial_eval(bench, {"b2", "r1"}, ["good", "good"])
        with caplog.at_level("WARNING"):
            check = base_case_stability_check(eta, bench)
        assert check.items_checked == 0
        assert "b1" in caplog.text

    def test_run_all_checks_does_not_raise_on_partial_eval(self) -> None:
        bench = self._two_base_one_role_bench()
        eta = self._partial_eval(bench, {"b2"}, ["good"])
        # Pre-fix: KeyError: 'b1' from rsr_role_consistency_check.
        report = run_all_checks(eta, bench)
        assert report.evaluation_id == eta.id
        assert len(report.checks) == 4


# ---- CLI integration -----------------------------------------------------


def test_cli_structure_runs_against_pulmonology_artifacts(tmp_path) -> None:
    """Sanity check the CLI front-end against bundled example data."""
    from pathlib import Path

    from click.testing import CliRunner

    from infereval.cli.main import cli

    repo_root = Path(__file__).resolve().parents[2]
    eval_path = repo_root / "experiments" / "results" / "pulmonology" / "gemini-2.5-pro-eta.json"
    bench_path = repo_root / "examples" / "pulmonary_edema" / "benchmark.json"
    if not (eval_path.exists() and bench_path.exists()):
        # Repos that don't ship the pulmonology artifacts skip this.
        return

    runner = CliRunner()
    result = runner.invoke(
        cli, ["structure", str(eval_path), "--benchmark", str(bench_path)]
    )
    assert result.exit_code == 0, result.output
    # Section headings.
    assert "structural coherence report" in result.output
    assert "Containment closure:" in result.output
    assert "RSR role consistency:" in result.output
    assert "Base-case stability:" in result.output


def test_cli_structure_rejects_mismatched_benchmark(tmp_path) -> None:
    """Evaluation's benchmark_id must match the supplied --benchmark id."""
    import json

    from click.testing import CliRunner

    from infereval.cli.main import cli

    # Build a benchmark + evaluation referencing different benchmark_ids.
    bench_data = {
        "schema_version": "1.0",
        "id": "bench-A",
        "bearers": {"p": {"expression": "P"}, "q": {"expression": "Q"}},
        "analysts": [{"id": "a"}],
        "items": [
            {"id": "i1", "premises": ["p"], "conclusions": ["q"],
             "analyst_verdicts": ["good"]},
        ],
    }
    bench_path = tmp_path / "bench.json"
    bench_path.write_text(json.dumps(bench_data), encoding="utf-8")

    eta_data = {
        "id": "test-run",
        "benchmark_id": "bench-B",  # mismatch!
        "model": {"provider": "mock", "model_id": "scripted-mock-v1"},
        "items": [],
    }
    eta_path = tmp_path / "eta.json"
    eta_path.write_text(json.dumps(eta_data), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli, ["structure", str(eta_path), "--benchmark", str(bench_path)]
    )
    assert result.exit_code != 0
    assert "benchmark_id" in result.output and "id=" in result.output
