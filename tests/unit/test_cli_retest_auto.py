"""Tests for ``infereval retest --auto`` (v0.11.0).

Auto mode runs ``infereval evaluate`` twice internally against the
benchmark + provider + model, then computes the retest. Tests mock the
provider via ``ScriptedProvider`` patched at the import site.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from infereval.cli.main import cli
from infereval.providers.mock import ScriptedProvider

STOP_SIGN_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "stop_sign" / "benchmark.json"
)


# ---- Argument-shape validation --------------------------------------------


class TestArgumentValidation:
    def test_auto_without_benchmark_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["retest", "--auto", "--provider", "openai", "--model", "gpt-4o"],
        )
        assert result.exit_code != 0
        assert "--auto requires --benchmark" in result.output

    def test_auto_without_provider_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["retest", "--auto", "--benchmark", str(STOP_SIGN_PATH)],
        )
        assert result.exit_code != 0
        assert "--auto requires --provider and --model" in result.output

    def test_auto_with_positional_eta_paths_errors(self, tmp_path: Path) -> None:
        a = tmp_path / "a.json"
        a.write_text("{}")
        b = tmp_path / "b.json"
        b.write_text("{}")
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "retest", "--auto",
                "--benchmark", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o",
                str(a), str(b),
            ],
        )
        assert result.exit_code != 0
        assert "mutually exclusive with positional eta paths" in result.output


# ---- Happy path with ScriptedProvider -----------------------------------


def _scripted_provider(responses: list[str]) -> ScriptedProvider:
    return ScriptedProvider(responses=responses)


class TestHappyPath:
    def test_identical_captures_yield_perfect_agreement(self, tmp_path: Path) -> None:
        """Two captures with identical scripted responses produce κ
        undefined (degenerate p_e=1 on all-good) but 100% agreement."""
        # 4 items × 3 samples × 2 captures = 24 responses, all "GOOD".
        provider = _scripted_provider(["GOOD"] * 24)
        out = tmp_path / "retest.json"
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        assert "items:       4" in result.output
        assert "100.0%" in result.output  # agreement rate
        # Output file present and shape correct.
        loaded = json.loads(out.read_text())
        assert loaded["n_items"] == 4
        assert loaded["n_agreements"] == 4
        assert loaded["n_disagreements"] == 0

    def test_differing_captures_record_flips(self, tmp_path: Path) -> None:
        """Capture A: all GOOD. Capture B: flip the first item's
        majority verdict to BAD (3/3 BAD samples). Retest should
        record exactly 1 flip."""
        # 4 items × 3 samples = 12 responses per capture.
        capture_a = ["GOOD"] * 12
        # Capture B: BAD on the first item (samples 0-2), GOOD on rest.
        capture_b = ["BAD"] * 3 + ["GOOD"] * 9
        provider = _scripted_provider(capture_a + capture_b)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "items:       4" in result.output
        assert "flips:       1" in result.output


# ---- --save-etas ----------------------------------------------------------


class TestSaveEtas:
    def test_save_etas_writes_both_etas_and_logs(self, tmp_path: Path) -> None:
        save_dir = tmp_path / "etas"
        provider = _scripted_provider(["GOOD"] * 24)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--save-etas", str(save_dir),
                ],
            )
        assert result.exit_code == 0, result.output
        assert (save_dir / "eta-a.json").is_file()
        assert (save_dir / "eta-b.json").is_file()
        assert (save_dir / "eta-a.run.jsonl").is_file()
        assert (save_dir / "eta-b.run.jsonl").is_file()


# ---- --interval-s --------------------------------------------------------


class TestInterval:
    def test_interval_sleeps_between_captures(self, tmp_path: Path) -> None:
        """--interval-s 1 should add ~1s of wall time. We use a 1-sec
        interval and measure that the elapsed time exceeds the
        no-interval baseline by close to 1s. This is a conservative
        check (tolerates noise on slow CI)."""
        provider = _scripted_provider(["GOOD"] * 24)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=provider
        ):
            t0 = time.monotonic()
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--interval-s", "1",
                ],
            )
            elapsed = time.monotonic() - t0
        assert result.exit_code == 0, result.output
        # Conservative bound: at least 0.5s. ScriptedProvider is
        # instantaneous so almost all of the 1s should be the sleep.
        assert elapsed >= 0.5, f"expected ≥0.5s elapsed, got {elapsed:.2f}s"


# ---- Provider error handling -------------------------------------------


class TestMultiInterval:
    """v0.12.0: --interval-s repeatable; N >= 2 emits MultiIntervalRetestResult."""

    def test_two_intervals_identical_captures_yield_two_pairs(self, tmp_path: Path) -> None:
        # 3 captures × 4 items × 3 samples = 36 responses, all good.
        provider = _scripted_provider(["GOOD"] * 36)
        out = tmp_path / "result.json"
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--interval-s", "0", "--interval-s", "0",
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        assert "pairs" in loaded
        assert len(loaded["pairs"]) == 2
        # Both pairs are baseline-vs-later, anchored on capture 0.
        baseline_run_id = loaded["baseline_run_id"]
        for p in loaded["pairs"]:
            assert p["retest"]["run_a_id"] == baseline_run_id
            assert p["retest"]["run_b_id"] != baseline_run_id
        # Stdout uses the multi-interval table.
        assert "multi-interval, anchored on baseline" in result.output
        assert "interval (s)" in result.output

    def test_single_interval_default_unchanged_shape(self, tmp_path: Path) -> None:
        """Regression-guard: passing `--interval-s 0` once (or omitting
        the flag entirely, since `(0,)` is the default) emits the same
        single-RetestResult JSON shape as v0.11.0."""
        provider = _scripted_provider(["GOOD"] * 24)
        out = tmp_path / "result.json"
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "-o", str(out),  # no --interval-s — default (0,)
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        # v0.11.0 RetestResult shape, not the v0.12.0 wrapper.
        assert "pairs" not in loaded
        assert "run_a_id" in loaded
        assert "run_b_id" in loaded
        assert loaded["n_items"] == 4

    def test_save_etas_multi_interval_uses_indexed_naming(self, tmp_path: Path) -> None:
        save_dir = tmp_path / "etas"
        provider = _scripted_provider(["GOOD"] * 48)  # 4 captures × 12 each
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--interval-s", "0", "--interval-s", "0", "--interval-s", "0",
                    "--save-etas", str(save_dir),
                ],
            )
        assert result.exit_code == 0, result.output
        for i in range(4):
            assert (save_dir / f"eta-{i}.json").is_file(), (
                f"eta-{i}.json missing — multi-interval naming convention"
            )
            assert (save_dir / f"eta-{i}.run.jsonl").is_file()
        # Single-interval naming (eta-a / eta-b) NOT used here.
        assert not (save_dir / "eta-a.json").exists()
        assert not (save_dir / "eta-b.json").exists()

    def test_interval_s_sleep_is_respected(self, tmp_path: Path) -> None:
        """--interval-s 0 --interval-s 1: wall time ≥ 1s sleep."""
        provider = _scripted_provider(["GOOD"] * 36)
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            t0 = time.monotonic()
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--interval-s", "0", "--interval-s", "1",
                ],
            )
            elapsed = time.monotonic() - t0
        assert result.exit_code == 0, result.output
        assert elapsed >= 0.5, f"expected ≥0.5s elapsed, got {elapsed:.2f}s"

    def test_drift_between_baseline_and_later_capture_lowers_kappa(self, tmp_path: Path) -> None:
        """Capture 0 (baseline): all GOOD. Capture 1: all GOOD (back-to-
        back, no drift). Capture 2: first item flips to BAD (synthetic
        drift). The second pair's κ should be lower than the first
        pair's."""
        # 12 GOOD + 12 GOOD + (3 BAD + 9 GOOD)
        responses = (["GOOD"] * 12) + (["GOOD"] * 12) + (["BAD"] * 3 + ["GOOD"] * 9)
        provider = _scripted_provider(responses)
        out = tmp_path / "result.json"
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--interval-s", "0", "--interval-s", "0",
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        # Pair 0 (baseline vs capture 1): zero flips, both all-GOOD.
        assert loaded["pairs"][0]["retest"]["n_disagreements"] == 0
        # Pair 1 (baseline vs capture 2): exactly one flip (item 0).
        assert loaded["pairs"][1]["retest"]["n_disagreements"] == 1

    def test_intervals_s_field_in_output_matches_input(self, tmp_path: Path) -> None:
        provider = _scripted_provider(["GOOD"] * 48)
        out = tmp_path / "result.json"
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--interval-s", "0", "--interval-s", "0", "--interval-s", "0",
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        assert [p["interval_s"] for p in loaded["pairs"]] == [0, 0, 0]


class TestProviderErrors:
    def test_provider_error_during_capture_b_exits_nonzero(self, tmp_path: Path) -> None:
        """A ProviderError raised partway through capture B should exit
        nonzero with a clear message and leave capture A on disk under
        --save-etas.

        ScriptedProvider cycles on exhaustion rather than raising, so we
        wrap the inner ``evaluate`` to raise on the second call (capture B).
        """
        from infereval.evaluation import evaluate as real_evaluate
        from infereval.providers.base import ProviderError

        provider = _scripted_provider(["GOOD"] * 12)
        save_dir = tmp_path / "etas"
        call_count = {"n": 0}

        def evaluate_then_raise(*args, **kwargs):  # noqa: ANN002,ANN003,ANN202
            call_count["n"] += 1
            if call_count["n"] == 1:
                return real_evaluate(*args, **kwargs)
            raise ProviderError("synthetic capture-B failure for the test")

        runner = CliRunner()
        with (
            patch("infereval.providers.get_provider", return_value=provider),
            patch("infereval.cli.retest_cmd.evaluate", side_effect=evaluate_then_raise),
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--save-etas", str(save_dir),
                ],
            )
        assert result.exit_code == 1, result.output
        assert "capture B" in result.output
        # Capture A survived to disk.
        assert (save_dir / "eta-a.json").is_file()
