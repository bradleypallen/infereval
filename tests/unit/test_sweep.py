"""Tests for ``infereval.sweep`` — Phase 2.3 sensitivity-analysis sweeps."""

from __future__ import annotations

from pathlib import Path

import pytest

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig
from infereval.providers.mock import ScriptedProvider
from infereval.sweep import SweepError, coerce_values, run_sweep

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


def _bench() -> Benchmark:
    return Benchmark.load(STOP_SIGN_PATH)


# ---- coerce_values --------------------------------------------------------


class TestCoerceValues:
    def test_n_samples_coerces_to_int(self) -> None:
        assert coerce_values("n_samples", ["1", "3", "5"]) == [1, 3, 5]

    def test_temperature_coerces_to_float(self) -> None:
        assert coerce_values("temperature", ["0.0", "0.5", "1.0"]) == [0.0, 0.5, 1.0]

    def test_tie_break_validates_literal(self) -> None:
        assert coerce_values("tie_break", ["abstain", "good"]) == ["abstain", "good"]

    def test_tie_break_rejects_unknown(self) -> None:
        with pytest.raises(SweepError, match="tie_break"):
            coerce_values("tie_break", ["wrongvalue"])

    def test_unknown_parameter_rejected(self) -> None:
        with pytest.raises(SweepError, match="supported parameters"):
            coerce_values("bogus_param", ["1"])

    def test_non_integer_for_int_parameter_rejected(self) -> None:
        with pytest.raises(SweepError, match="not a valid int"):
            coerce_values("n_samples", ["abc"])

    def test_paraphrase_variant_coerces_to_int(self) -> None:
        assert coerce_values("paraphrase_variant", ["0", "1", "2"]) == [0, 1, 2]


# ---- run_sweep ------------------------------------------------------------


class TestRunSweep:
    def test_n_samples_sweep_writes_one_pair_per_value(self, tmp_path: Path) -> None:
        # Enough scripted responses to cover 4 items × max(values) samples.
        provider = ScriptedProvider(responses=["GOOD"] * 30)
        result = run_sweep(
            _bench(),
            provider,
            parameter="n_samples",
            values=[1, 3, 5],
            out_dir=tmp_path,
            config=EndorsementConfig(question_form="support"),
        )
        assert len(result.rows) == 3
        assert all(r.coverage == 1.0 for r in result.rows)
        # Per-value files written.
        for v in (1, 3, 5):
            assert (tmp_path / f"sweep-n_samples={v}-eta.json").exists()
            assert (tmp_path / f"sweep-n_samples={v}-run.jsonl").exists()

    def test_kappa_c_range_zero_on_constant_data(self, tmp_path: Path) -> None:
        # ScriptedProvider always returns the same verdict, so changing
        # n_samples does not change the majority verdict — κ_C constant.
        provider = ScriptedProvider(responses=["GOOD"] * 30)
        result = run_sweep(
            _bench(), provider,
            parameter="n_samples",
            values=[1, 3, 5],
            out_dir=tmp_path,
            config=EndorsementConfig(question_form="support"),
        )
        assert result.kappa_c_range == 0.0
        assert "stable" in result.stability_verdict

    def test_tie_break_sweep(self, tmp_path: Path) -> None:
        # tie_break only matters when there's a tie among n_samples
        # verdicts. With n_samples=2 and one GOOD + one BAD per item,
        # tie_break determines the verdict. Use a long response cycle.
        # Stop-sign has 4 items × n_samples=2 = 8 calls.
        provider = ScriptedProvider(responses=["GOOD", "BAD"] * 8)
        result = run_sweep(
            _bench(), provider,
            parameter="tie_break",
            values=["abstain", "good", "bad"],
            out_dir=tmp_path,
        )
        assert len(result.rows) == 3
        values_seen = {str(r.value) for r in result.rows}
        assert values_seen == {"abstain", "good", "bad"}

    def test_empty_values_rejected(self, tmp_path: Path) -> None:
        provider = ScriptedProvider(responses=["GOOD"])
        with pytest.raises(SweepError, match="at least one"):
            run_sweep(_bench(), provider, parameter="n_samples", values=[], out_dir=tmp_path)

    def test_unsupported_parameter_rejected(self, tmp_path: Path) -> None:
        provider = ScriptedProvider(responses=["GOOD"])
        with pytest.raises(SweepError, match="unsupported"):
            run_sweep(_bench(), provider, parameter="bogus", values=[1], out_dir=tmp_path)


# ---- stability_verdict ---------------------------------------------------


class TestStabilityVerdict:
    """Verdict thresholds: stable < 0.05 < moderate < 0.10 < substantive."""

    def _result(self, kappas: list[float | None]) -> object:
        from infereval.sweep import SweepResult, SweepRow

        rows = tuple(
            SweepRow(
                value=i, coverage=1.0, kappa_c=k, kappa_f=None,
                n_agreement=0, n_total=0, eta_path=Path("/tmp/x"),
            )
            for i, k in enumerate(kappas)
        )
        return SweepResult(parameter="n_samples", rows=rows)

    def test_tight_range_yields_stable(self) -> None:
        r = self._result([0.60, 0.62, 0.63])
        assert "stable" in r.stability_verdict.lower()

    def test_moderate_range_flagged_moderate(self) -> None:
        r = self._result([0.50, 0.58, 0.55])  # range 0.08
        assert "moderately sensitive" in r.stability_verdict.lower()

    def test_wide_range_flagged_substantively(self) -> None:
        r = self._result([0.30, 0.70, 0.55])  # range 0.40
        assert "substantively" in r.stability_verdict.lower()

    def test_single_defined_kappa_insufficient(self) -> None:
        r = self._result([0.50, None, None])
        assert "insufficient" in r.stability_verdict.lower()


# ---- CLI integration -----------------------------------------------------


class TestSweepCLI:
    def test_cli_runs_full_sweep(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from click.testing import CliRunner

        from infereval.cli.main import cli

        provider = ScriptedProvider(responses=["GOOD"] * 30)
        with patch(
            "infereval.cli.sweep_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "sweep", str(STOP_SIGN_PATH),
                    "--provider", "openai",
                    "--model", "gpt-4o-mini",
                    "--vary", "n_samples",
                    "--values", "1,3,5",
                    "--out-dir", str(tmp_path),
                    "--question-form", "support",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "sensitivity sweep: n_samples" in result.output
        assert "κ_C range" in result.output
        assert (tmp_path / "sweep-summary.json").exists()
        assert (tmp_path / "sweep-n_samples=1-eta.json").exists()
        assert (tmp_path / "sweep-n_samples=3-eta.json").exists()
        assert (tmp_path / "sweep-n_samples=5-eta.json").exists()

    def test_cli_rejects_invalid_values(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from infereval.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "sweep", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o",
                "--vary", "n_samples",
                "--values", "not-an-int",
                "--out-dir", str(tmp_path),
            ],
        )
        assert result.exit_code != 0
        assert "not a valid int" in result.output
