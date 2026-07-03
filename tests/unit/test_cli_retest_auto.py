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
from infereval.evaluation import Evaluation
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


# ---- v0.14.0: --baseline-from staged-composition primitive ---------------
#
# `--baseline-from <eta-path>` loads a saved baseline eta, runs ONE fresh
# capture against it, and emits a one-pair MultiIntervalRetestResult whose
# `interval_s` is computed from the elapsed wall-clock between
# baseline.started_at and the fresh capture's started_at. This is the
# primitive on top of which `--append-to` is built.


def _capture_baseline_eta(tmp_path: Path) -> Path:
    """Helper: run a default `--auto --interval-s 0` and return the
    saved `eta-a.json` path. Used as the baseline fixture for the
    TestBaselineFrom tests below — the resulting baseline is real
    (ScriptedProvider-backed) so the parity check has something
    real to validate against.
    """
    save_dir = tmp_path / "phase1"
    provider = _scripted_provider(["GOOD"] * 24)
    runner = CliRunner()
    with patch("infereval.providers.get_provider", return_value=provider):
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
    return save_dir / "eta-a.json"


class TestBaselineFrom:
    def test_baseline_from_emits_one_pair_multi_result(self, tmp_path: Path) -> None:
        """Load a saved baseline, run one fresh capture against it,
        confirm output JSON is a one-pair MultiIntervalRetestResult."""
        baseline_path = _capture_baseline_eta(tmp_path)
        out = tmp_path / "from-baseline.json"
        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--baseline-from", str(baseline_path),
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        # MultiIntervalRetestResult shape: has `pairs` and `baseline_run_id`.
        assert "pairs" in loaded
        assert "baseline_run_id" in loaded
        assert len(loaded["pairs"]) == 1
        # The one pair is a valid retest result.
        pair = loaded["pairs"][0]
        assert "interval_s" in pair
        assert "retest" in pair
        assert pair["retest"]["n_items"] == 4

    def test_baseline_from_computes_interval_s_from_started_at(
        self, tmp_path: Path
    ) -> None:
        """The synthesized `interval_s` should reflect the actual
        elapsed wall-clock between baseline.started_at and the fresh
        capture's started_at — via `compute_interval_s`. Because the
        ScriptedProvider runs at machine speed, the elapsed time
        should be small but non-negative.
        """
        baseline_path = _capture_baseline_eta(tmp_path)
        out = tmp_path / "from-baseline.json"
        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--baseline-from", str(baseline_path),
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        interval_s = loaded["pairs"][0]["interval_s"]
        # The fresh capture happens after the baseline (same tmp_path
        # session), so interval_s must be >= 0. Upper bound is loose:
        # the test setup + scripted-provider eval all complete in
        # well under 60s on any modern machine.
        assert interval_s >= 0
        assert interval_s < 60

    def test_baseline_from_parity_check_fires_on_benchmark_hash_mismatch(
        self, tmp_path: Path
    ) -> None:
        """If the fresh capture is against a *different* benchmark than
        the baseline was, the parity check in `compute_retest` must
        fire with `RetestConfigMismatchError`."""
        # Capture baseline against stop-sign.
        baseline_path = _capture_baseline_eta(tmp_path)
        # Build a different benchmark (one item dropped).
        bench_data = json.loads(STOP_SIGN_PATH.read_text())
        bench_data["id"] = "stop-sign-truncated"
        bench_data["items"] = bench_data["items"][:3]
        other_bench_path = tmp_path / "other-bench.json"
        other_bench_path.write_text(json.dumps(bench_data))

        fresh_provider = _scripted_provider(["GOOD"] * 9)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(other_bench_path),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--baseline-from", str(baseline_path),
                ],
            )
        assert result.exit_code != 0, result.output
        assert "incompatible runs" in result.output.lower()

    def test_baseline_from_identity_criterion_threaded_via_claims(
        self, tmp_path: Path
    ) -> None:
        """`--claims` with a non-empty reliability.identity_criterion
        rationale → criterion appears in the emitted multi-result."""
        baseline_path = _capture_baseline_eta(tmp_path)
        claims_data = {
            "mastery_sense": {"sense": "evaluative", "description": "x"},
            "scope": {"scope": "items_in_benchmark", "justification": "x"},
            "constitution": {
                "position": "evidence_of_mastery", "justification": "x",
            },
            "carving": {
                "acknowledges_carving_indexed": False, "notes": "",
            },
            "competing_explanations": {"test_retest_run": True},
            "reliability": {
                "identity_criterion": {
                    "same_provider_model_id": True,
                    "cross_update_identity_asserted": True,
                    "same_scaffolding": True,
                    "unverifiable_caveats": "test caveat",
                    "rationale": "test rationale for v0.14.0 baseline-from",
                },
            },
        }
        claims_path = tmp_path / "claims.json"
        claims_path.write_text(json.dumps(claims_data))
        out = tmp_path / "from-baseline.json"

        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--claims", str(claims_path),
                    "--baseline-from", str(baseline_path),
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        # Criterion threaded through at the wrapper level.
        assert "identity_criterion" in loaded
        crit = loaded["identity_criterion"]
        assert crit["rationale"] == (
            "test rationale for v0.14.0 baseline-from"
        )

    def test_baseline_from_writes_to_output_path(self, tmp_path: Path) -> None:
        """`-o /path/to/file.json` writes the multi-result there."""
        baseline_path = _capture_baseline_eta(tmp_path)
        out = tmp_path / "subdir" / "result.json"  # subdir doesn't exist yet
        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--baseline-from", str(baseline_path),
                    "-o", str(out),
                ],
            )
        assert result.exit_code == 0, result.output
        assert out.is_file()
        loaded = json.loads(out.read_text())
        assert loaded["schema_version"] == "1.0"

    def test_baseline_from_mutually_exclusive_with_multi_interval_s(
        self, tmp_path: Path
    ) -> None:
        """`--baseline-from + --interval-s 0 --interval-s 3600` →
        click error. The staged path runs one fresh capture; multi
        `--interval-s` implies the N+1-capture orchestration path."""
        baseline_path = _capture_baseline_eta(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "retest", "--auto",
                "--benchmark", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o",
                "--baseline-from", str(baseline_path),
                "--interval-s", "0",
                "--interval-s", "3600",
            ],
        )
        assert result.exit_code != 0
        assert "incompatible with multiple --interval-s" in result.output


# ---- v0.14.0: --append-to staged-composition composer --------------------
#
# `--append-to <multi.json>` loads an existing MultiIntervalRetestResult,
# runs ONE fresh capture against the baseline (sibling `eta-0.json` by
# default), appends the new pair, and writes the updated multi-result
# back to the same path (or `-o` override).


def _phase1_multi(
    tmp_path: Path, extra_args: list[str] | None = None
) -> tuple[Path, Path]:
    """Capture a 2-pair Phase 1 multi.json (back-to-back + 0s sleep so
    the test is fast). Returns (multi_path, retest_dir). The retest_dir
    contains the saved etas (`eta-0.json`, `eta-1.json`, `eta-2.json`)
    AND the multi.json; sibling-resolution will then find `eta-0.json`
    naturally. ``extra_args`` appends further CLI flags to the Phase 1
    capture invocation (e.g. `--coherence-frame <id>`).
    """
    retest_dir = tmp_path / "phase1"
    retest_dir.mkdir(parents=True, exist_ok=True)
    multi_path = retest_dir / "multi.json"
    # 3 captures × 4 items × 3 samples = 36 responses.
    provider = _scripted_provider(["GOOD"] * 36)
    runner = CliRunner()
    with patch("infereval.providers.get_provider", return_value=provider):
        result = runner.invoke(
            cli,
            [
                "retest", "--auto",
                "--benchmark", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o",
                "--n-samples", "3",
                "--interval-s", "0",
                "--interval-s", "0",
                "--save-etas", str(retest_dir),
                "-o", str(multi_path),
                *(extra_args or []),
            ],
        )
    assert result.exit_code == 0, result.output
    return multi_path, retest_dir


class TestAppendTo:
    def test_append_to_grows_pairs_count(self, tmp_path: Path) -> None:
        """Load a 2-pair Phase 1 multi.json, append one fresh capture,
        confirm output has 3 pairs."""
        multi_path, _ = _phase1_multi(tmp_path)
        before = json.loads(multi_path.read_text())
        assert len(before["pairs"]) == 2

        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code == 0, result.output
        after = json.loads(multi_path.read_text())
        # In-place update: same path, +1 pair.
        assert len(after["pairs"]) == 3
        # The baseline anchor is preserved across the append.
        assert after["baseline_run_id"] == before["baseline_run_id"]

    def test_append_to_preserves_identity_criterion(
        self, tmp_path: Path
    ) -> None:
        """If the existing multi.json carries an identity_criterion,
        the appended-to artifact preserves it verbatim — the criterion
        applies to every pair including the appended one."""
        multi_path, _ = _phase1_multi(tmp_path)
        # Inject a criterion into the loaded JSON, then write it back
        # (simulates a Phase 1 capture run with --claims).
        data = json.loads(multi_path.read_text())
        data["identity_criterion"] = {
            "same_benchmark_hash": True,
            "same_endorsement_config": True,
            "same_paraphrase_variant": True,
            "same_provider_model_id": True,
            "cross_update_identity_asserted": True,
            "same_scaffolding": True,
            "unverifiable_caveats": "test caveat",
            "rationale": "Phase 1 identity criterion for --append-to test",
        }
        multi_path.write_text(json.dumps(data))

        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code == 0, result.output
        after = json.loads(multi_path.read_text())
        assert "identity_criterion" in after
        assert after["identity_criterion"]["rationale"] == (
            "Phase 1 identity criterion for --append-to test"
        )

    def test_append_to_parity_check_fires_on_config_mismatch(
        self, tmp_path: Path
    ) -> None:
        """If the fresh capture's config differs from the baseline
        (different n_samples), the parity check in compute_retest
        fires with RetestConfigMismatchError."""
        multi_path, _ = _phase1_multi(tmp_path)
        # _phase1_multi used --n-samples 3; now use --n-samples 5
        # for the fresh capture → endorsement_config mismatch.
        fresh_provider = _scripted_provider(["GOOD"] * 20)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "5",  # mismatch
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code != 0
        assert "incompatible runs" in result.output.lower()

    def test_append_to_resolves_baseline_from_sibling_eta_0_by_default(
        self, tmp_path: Path
    ) -> None:
        """Default baseline-resolution looks for `eta-0.json` in the
        directory containing the multi.json. _phase1_multi writes both
        next to each other, so no `--baseline-from` override is needed."""
        multi_path, retest_dir = _phase1_multi(tmp_path)
        assert (retest_dir / "eta-0.json").is_file()

        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code == 0, result.output

    def test_append_to_runid_uses_distinct_append_prefix(
        self, tmp_path: Path
    ) -> None:
        """The new pair's run_id must have a distinct prefix from the
        existing pairs (which share the Phase 1 `retest-auto-<hex>`
        prefix); --append-to mints `retest-append-<hex>`."""
        multi_path, _ = _phase1_multi(tmp_path)
        before = json.loads(multi_path.read_text())
        existing_run_ids = {p["run_id"] for p in before["pairs"]}

        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code == 0, result.output
        after = json.loads(multi_path.read_text())
        new_pair = after["pairs"][-1]
        assert new_pair["run_id"] not in existing_run_ids
        # Distinct prefix marks the staged provenance.
        assert new_pair["run_id"].startswith("retest-append-")

    def test_append_to_writes_back_to_same_path_in_place(
        self, tmp_path: Path
    ) -> None:
        """No `-o` → updates the supplied multi.json file in place.
        Output file path unchanged; existing pairs untouched; only
        the new pair appended."""
        multi_path, _ = _phase1_multi(tmp_path)
        original_size = multi_path.stat().st_size

        fresh_provider = _scripted_provider(["GOOD"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code == 0, result.output
        # In-place: same path, larger content (new pair appended).
        assert multi_path.is_file()
        assert multi_path.stat().st_size > original_size


# ---- --coherence-frame threading (coherence-frame API) --------------------


class TestCoherenceFrame:
    def test_auto_captures_record_explicit_frame(self, tmp_path: Path) -> None:
        """--coherence-frame threads into both auto-mode captures; the
        saved etas record the resolved id in endorsement_config."""
        save_dir = tmp_path / "etas"
        provider = _scripted_provider(["INCOHERENT"] * 24)
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--coherence-frame", "defeasible-coherence-explicit-v1",
                    "--save-etas", str(save_dir),
                ],
            )
        assert result.exit_code == 0, result.output
        for name in ("eta-a.json", "eta-b.json"):
            eta = Evaluation.load(save_dir / name)
            assert eta.endorsement_config.coherence_frame_id == (
                "defeasible-coherence-explicit-v1"
            )

    def test_unknown_frame_id_exits_nonzero(self) -> None:
        """An unknown frame id fails fast — before any provider client is
        constructed — with the catalog listing in the error message."""
        runner = CliRunner()
        # No get_provider patch: the frame lookup precedes provider
        # construction, so no provider (or API key) is ever needed.
        result = runner.invoke(
            cli,
            [
                "retest", "--auto",
                "--benchmark", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o",
                "--coherence-frame", "no-such-frame-v1",
            ],
        )
        assert result.exit_code == 2
        assert "unknown coherence_frame_id" in result.output

    def test_baseline_from_derives_frame_from_baseline_eta(
        self, tmp_path: Path
    ) -> None:
        """Absent an explicit flag, the fresh capture re-elicits under the
        frame the baseline eta records (not the thin default), so the
        endorsement_config parity check passes and the retest completes."""
        # Phase 1: capture a baseline under the anchored frame.
        save_dir = tmp_path / "phase1"
        provider = _scripted_provider(["INCOHERENT"] * 24)
        runner = CliRunner()
        with patch("infereval.providers.get_provider", return_value=provider):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--coherence-frame", "defeasible-coherence-explicit-v1",
                    "--save-etas", str(save_dir),
                ],
            )
        assert result.exit_code == 0, result.output
        baseline_path = save_dir / "eta-a.json"

        # Phase 2: --baseline-from WITHOUT --coherence-frame. Without the
        # derivation the fresh capture would resolve to thin-v1 and
        # compute_retest would refuse the cross-frame comparison.
        fresh_dir = tmp_path / "phase2"
        fresh_provider = _scripted_provider(["INCOHERENT"] * 12)
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--baseline-from", str(baseline_path),
                    "--save-etas", str(fresh_dir),
                ],
            )
        assert result.exit_code == 0, result.output
        fresh = Evaluation.load(fresh_dir / "eta-1.json")
        assert fresh.endorsement_config.coherence_frame_id == (
            "defeasible-coherence-explicit-v1"
        )

    def test_baseline_from_explicit_flag_overrides_derivation(
        self, tmp_path: Path
    ) -> None:
        """An explicit --coherence-frame wins over baseline derivation; the
        resulting cross-frame comparison (thin-v1 baseline vs anchored
        fresh capture) is refused by the endorsement_config parity check."""
        baseline_path = _capture_baseline_eta(tmp_path)  # thin-v1 baseline
        fresh_provider = _scripted_provider(["INCOHERENT"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--baseline-from", str(baseline_path),
                    "--coherence-frame", "defeasible-coherence-explicit-v1",
                ],
            )
        assert result.exit_code != 0, result.output
        assert "incompatible runs" in result.output.lower()

    def test_append_to_derives_frame_from_baseline_eta(
        self, tmp_path: Path
    ) -> None:
        """--append-to derives the frame from the baseline eta the same way
        --baseline-from does: the appended capture re-elicits under the
        baseline's frame and the pair count grows."""
        multi_path, retest_dir = _phase1_multi(
            tmp_path,
            extra_args=["--coherence-frame", "defeasible-coherence-explicit-v1"],
        )
        fresh_provider = _scripted_provider(["INCOHERENT"] * 12)
        runner = CliRunner()
        with patch(
            "infereval.providers.get_provider", return_value=fresh_provider
        ):
            result = runner.invoke(
                cli,
                [
                    "retest", "--auto",
                    "--benchmark", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--n-samples", "3",
                    "--append-to", str(multi_path),
                ],
            )
        assert result.exit_code == 0, result.output
        after = json.loads(multi_path.read_text())
        assert len(after["pairs"]) == 3
        # The appended fresh capture (slot eta-3) re-elicited under the
        # baseline's frame.
        fresh = Evaluation.load(retest_dir / "eta-3.json")
        assert fresh.endorsement_config.coherence_frame_id == (
            "defeasible-coherence-explicit-v1"
        )


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
