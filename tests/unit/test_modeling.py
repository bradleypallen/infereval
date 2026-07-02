"""Tests for ``infereval.modeling`` — Phase 2.2 factor-effects modeling."""

from __future__ import annotations

import pytest

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, ProviderParams, evaluate
from infereval.modeling import ModelingError, fit_factor_model
from infereval.providers.mock import ScriptedProvider


def _factorial_bench_with_noise() -> tuple[Benchmark, list[str]]:
    """Build a 2-factor benchmark with predictable but non-separated outcomes.

    24 items, 2×2 design (role × para), 6 items per cell. The "role"
    factor is the primary driver: supporters agree with the analyst
    ~5/6 of the time, defeaters agree ~1/6 of the time. The "para"
    factor is uncorrelated with the outcome (null effect we should
    detect as non-significant). Each item gets n_samples=2 so we have
    48 observations total.

    Returns the benchmark and the ScriptedProvider response sequence
    that produces the intended noise pattern.
    """
    items = []
    responses: list[str] = []
    n_samples = 2
    cells = [("supporter", "v1"), ("supporter", "v2"), ("defeater", "v1"), ("defeater", "v2")]
    for cell_idx, (role, para) in enumerate(cells):
        for i in range(6):
            item_idx = cell_idx * 6 + i
            items.append({
                "id": f"i{item_idx:02d}",
                "premises": ["p"],
                "conclusions": ["q"],
                "analyst_verdicts": ["good"],
                "factor_levels": {"role": role, "para": para},
            })
            # Noise pattern (independent of para):
            #   supporter cells: 5/6 items get all-GOOD, 1/6 gets all-BAD
            #   defeater cells:  5/6 items get all-BAD,  1/6 gets all-GOOD
            if role == "supporter":
                base = "GOOD" if i < 5 else "BAD"
            else:
                base = "BAD" if i < 5 else "GOOD"
            responses.extend([base] * n_samples)

    bench = Benchmark.model_validate({
        "schema_version": "1.0",
        "id": "modeling-test",
        "bearers": {"p": {"expression": "P"}, "q": {"expression": "Q"}},
        "analysts": [{"id": "a"}],
        "factors": {
            "role": ["supporter", "defeater"],
            "para": ["v1", "v2"],
        },
        "items": items,
    })
    return bench, responses


class TestFactorEffectsFit:
    """End-to-end ``fit_factor_model`` against a predictable factorial design."""

    def test_role_factor_detected_para_null(self) -> None:
        bench, responses = _factorial_bench_with_noise()
        eta = evaluate(
            bench,
            ScriptedProvider(responses=responses),
            config=EndorsementConfig(n_samples=2, question_form="support"),
            params=ProviderParams(max_tokens=8),
        )
        fit = fit_factor_model(eta, bench)
        # 24 items × 2 samples = 48 observations.
        assert fit.n_observations == 48
        assert fit.n_items == 24
        # role is the driver → significant Wald.
        assert fit.factor_wald["role"] < 0.05
        # para is null → non-significant.
        assert fit.factor_wald["para"] > 0.05
        # defeater coefficient should be large-negative (lower odds of
        # agreement than the supporter baseline).
        role_effect = next(e for e in fit.effects if e.factor == "role")
        assert role_effect.coef < 0

    def test_returns_modelfit_with_methodology_notes(self) -> None:
        bench, responses = _factorial_bench_with_noise()
        eta = evaluate(
            bench,
            ScriptedProvider(responses=responses),
            config=EndorsementConfig(n_samples=2, question_form="support"),
        )
        fit = fit_factor_model(eta, bench)
        # Notes surface the GLMM caveat.
        notes_blob = " ".join(fit.notes).lower()
        assert "cluster" in notes_blob or "glmm" in notes_blob

    def test_pseudo_r2_in_unit_interval(self) -> None:
        bench, responses = _factorial_bench_with_noise()
        eta = evaluate(
            bench,
            ScriptedProvider(responses=responses),
            config=EndorsementConfig(n_samples=2, question_form="support"),
        )
        fit = fit_factor_model(eta, bench)
        assert fit.pseudo_r2 is not None
        assert 0.0 <= fit.pseudo_r2 <= 1.0

    def test_per_factor_wald_keys_match_declared_factors(self) -> None:
        bench, responses = _factorial_bench_with_noise()
        eta = evaluate(
            bench,
            ScriptedProvider(responses=responses),
            config=EndorsementConfig(n_samples=2, question_form="support"),
        )
        fit = fit_factor_model(eta, bench)
        assert set(fit.factor_wald.keys()) == set(bench.factors.keys())


class TestModelingErrors:
    """``ModelingError`` surfaces specific failure modes with actionable text."""

    def test_no_factors_declared_raises(self) -> None:
        bench = Benchmark.model_validate({
            "schema_version": "1.0",
            "id": "no-factors",
            "bearers": {"p": {"expression": "P"}, "q": {"expression": "Q"}},
            "analysts": [{"id": "a"}],
            "items": [
                {"id": "i1", "premises": ["p"], "conclusions": ["q"],
                 "analyst_verdicts": ["good"]},
            ],
        })
        eta = evaluate(
            bench, ScriptedProvider(responses=["GOOD"]),
            config=EndorsementConfig(n_samples=1),
        )
        with pytest.raises(ModelingError, match="declares no factors"):
            fit_factor_model(eta, bench)

    def test_all_abstain_raises(self) -> None:
        bench, _ = _factorial_bench_with_noise()
        # ScriptedProvider returns gibberish so every sample parses as ABSTAIN.
        responses = ["???"] * 48
        eta = evaluate(
            bench, ScriptedProvider(responses=responses),
            config=EndorsementConfig(n_samples=2, question_form="support"),
        )
        with pytest.raises(ModelingError, match="abstain"):
            fit_factor_model(eta, bench)


class TestModelingCLI:
    """Integration of the ``infereval model`` command."""

    def test_cli_prints_factor_wald_table(self, tmp_path) -> None:

        from click.testing import CliRunner

        from infereval.cli.main import cli

        bench, responses = _factorial_bench_with_noise()
        eta = evaluate(
            bench, ScriptedProvider(responses=responses),
            config=EndorsementConfig(n_samples=2, question_form="support"),
        )
        bench_path = tmp_path / "bench.json"
        bench.dump(bench_path)
        eta_path = tmp_path / "eta.json"
        eta.dump(eta_path)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["model", str(eta_path), "--benchmark", str(bench_path)]
        )
        assert result.exit_code == 0, result.output
        assert "factor-effects model of agreement" in result.output
        assert "Per-factor joint Wald tests:" in result.output
        assert "role" in result.output and "para" in result.output
        assert "Methodology:" in result.output

    def test_cli_rejects_mismatched_benchmark_id(self, tmp_path) -> None:
        import json

        from click.testing import CliRunner

        from infereval.cli.main import cli

        bench_path = tmp_path / "bench.json"
        bench_path.write_text(
            json.dumps({
                "schema_version": "1.0",
                "id": "bench-A",
                "bearers": {"p": {"expression": "P"}, "q": {"expression": "Q"}},
                "analysts": [{"id": "a"}],
                "factors": {"f": ["a", "b"]},
                "items": [{"id": "i1", "premises": ["p"], "conclusions": ["q"],
                           "analyst_verdicts": ["good"], "factor_levels": {"f": "a"}}],
            }),
            encoding="utf-8",
        )
        eta_path = tmp_path / "eta.json"
        eta_path.write_text(
            json.dumps({
                "id": "test",
                "benchmark_id": "bench-B",  # mismatch
                "model": {"provider": "mock", "model_id": "scripted-mock-v1"},
                "items": [],
            }),
            encoding="utf-8",
        )
        runner = CliRunner()
        result = runner.invoke(
            cli, ["model", str(eta_path), "--benchmark", str(bench_path)]
        )
        assert result.exit_code != 0
        assert "benchmark_id" in result.output
