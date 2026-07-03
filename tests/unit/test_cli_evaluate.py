"""Tests for ``infereval evaluate``.

Real providers are mocked out by patching :func:`infereval.cli.evaluate_cmd.get_provider`
to return a :class:`ScriptedProvider`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from infereval.cli.main import cli
from infereval.evaluation import Evaluation
from infereval.providers.mock import ScriptedProvider
from infereval.types import Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


# ---- --dry-run --------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_provider_required(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["evaluate", str(STOP_SIGN_PATH), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Dry run" in result.output
        assert "default-v1" in result.output
        assert "## System prompt" in result.output
        # All four items should appear
        for rid in ("row-0", "row-1", "row-2", "row-3"):
            assert f"## Item {rid}" in result.output

    def test_dry_run_prompts_are_tex_stripped(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["evaluate", str(STOP_SIGN_PATH), "--dry-run"])
        # "$a$" should not appear; "a" should appear
        assert "$" not in result.output
        assert "a is a stop sign" in result.output


# ---- Full run with patched provider -----------------------------------------


class TestFullRun:
    def test_writes_evaluation_json(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        # Schedule the model to match the paper's analyst row
        provider = ScriptedProvider(
            responses=["GOOD"] * 9 + ["BAD"] * 3,
            model_id="patched-mock-v1",
        )
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate",
                    str(STOP_SIGN_PATH),
                    "--provider", "anthropic",
                    "--model", "claude-opus-4-7",
                    "--output", str(out_path),
                    "--n-samples", "3",
                    "--temperature", "0.0",
                    "--max-tokens", "8",
                    "--run-id", "test-run-001",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "OK: wrote" in result.output
        assert out_path.exists()

        eta = Evaluation.load(out_path)
        assert eta.id == "test-run-001"
        assert eta.benchmark_id == "stop-sign-example-1"
        assert eta.n == 4
        # The scripted responses produce GOOD for rows 0-2 and BAD for row-3
        assert eta.items[0].model_verdict == Verdict.GOOD
        assert eta.items[3].model_verdict == Verdict.BAD

    def test_records_provider_params(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate",
                    str(STOP_SIGN_PATH),
                    "--provider", "openai",
                    "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "2",
                    "--temperature", "0.3",
                    "--max-tokens", "16",
                    "--seed", "123",
                ],
            )
        assert result.exit_code == 0, result.output
        eta = Evaluation.load(out_path)
        assert eta.model.params.temperature == 0.3
        assert eta.model.params.max_tokens == 16
        assert eta.model.params.seed == 123
        assert eta.endorsement_config.n_samples == 2

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        out_path = tmp_path / "nested" / "dirs" / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                ],
            )
        assert result.exit_code == 0, result.output
        assert out_path.exists()


# ---- --coherence-frame threading (coherence-frame API) ---------------------


class TestCoherenceFrame:
    def test_explicit_frame_recorded_in_endorsement_config(self, tmp_path: Path) -> None:
        """--coherence-frame threads through evaluate(); the resolved id is
        stamped into the output eta's endorsement_config."""
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["INCOHERENT"] * 4)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                    "--coherence-frame", "defeasible-coherence-explicit-v1",
                ],
            )
        assert result.exit_code == 0, result.output
        eta = Evaluation.load(out_path)
        assert eta.endorsement_config.coherence_frame_id == (
            "defeasible-coherence-explicit-v1"
        )

    def test_absent_flag_records_thin_default(self, tmp_path: Path) -> None:
        """No --coherence-frame -> evaluate()'s default resolution; the
        stop-sign benchmark declares no frame binding, so the recorded id
        is the thin default."""
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["INCOHERENT"] * 4)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                ],
            )
        assert result.exit_code == 0, result.output
        eta = Evaluation.load(out_path)
        assert eta.endorsement_config.coherence_frame_id == "thin-v1"

    def test_unknown_frame_id_exits_nonzero(self, tmp_path: Path) -> None:
        """An unknown frame id fails fast — before any provider client is
        constructed — with the catalog listing in the error message."""
        out_path = tmp_path / "eta.json"
        runner = CliRunner()
        # No get_provider patch: the frame lookup precedes provider
        # construction, so no provider (or API key) is ever needed.
        result = runner.invoke(
            cli,
            [
                "evaluate", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o-mini",
                "--output", str(out_path),
                "--n-samples", "1",
                "--coherence-frame", "no-such-frame-v1",
            ],
        )
        assert result.exit_code == 2
        assert "unknown coherence_frame_id" in result.output
        assert "no-such-frame-v1" in result.output
        assert not out_path.exists()


# ---- Argument validation ---------------------------------------------------


class TestArgValidation:
    def test_missing_provider_fails(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["evaluate", str(STOP_SIGN_PATH), "--model", "x", "--output", str(out_path)],
        )
        assert result.exit_code == 2
        assert "--provider" in result.output and "required" in result.output

    def test_missing_model_fails(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["evaluate", str(STOP_SIGN_PATH), "--provider", "openai", "--output", str(out_path)],
        )
        assert result.exit_code == 2
        assert "--model" in result.output

    def test_missing_output_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["evaluate", str(STOP_SIGN_PATH), "--provider", "openai", "--model", "gpt"],
        )
        assert result.exit_code == 2
        assert "--output" in result.output

    def test_unknown_provider_choice_rejected_by_click(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["evaluate", str(STOP_SIGN_PATH), "--provider", "fake",
             "--model", "x", "--output", "/tmp/x.json"],
        )
        assert result.exit_code != 0
        # click prints the available choices
        assert "anthropic" in result.output

    def test_provider_config_error_surfaces_cleanly(self, tmp_path: Path) -> None:
        # Trigger a real ProviderConfigError by asking for anthropic without an API key.
        out_path = tmp_path / "eta.json"
        runner = CliRunner()
        # Make sure no anthropic key is present.
        result = runner.invoke(
            cli,
            [
                "evaluate", str(STOP_SIGN_PATH),
                "--provider", "anthropic",
                "--model", "claude-opus-4-7",
                "--output", str(out_path),
            ],
            env={"ANTHROPIC_API_KEY": ""},
        )
        assert result.exit_code == 2
        assert "provider configuration" in result.output


# ---- OpenRouter attribution headers ---------------------------------------


class TestOpenRouter:
    def test_openrouter_passes_attribution_headers(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        captured_kwargs: dict[str, object] = {}

        def fake_get_provider(provider: str, model_id: str, **kwargs: object):
            captured_kwargs["provider"] = provider
            captured_kwargs.update(kwargs)
            return ScriptedProvider(responses=["GOOD"] * 10)

        with patch(
            "infereval.cli.evaluate_cmd.get_provider", side_effect=fake_get_provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openrouter",
                    "--model", "anthropic/claude-3.5-sonnet",
                    "--output", str(out_path),
                    "--n-samples", "1",
                    "--http-referer", "https://example.com",
                    "--x-title", "infereval-test",
                ],
            )
        assert result.exit_code == 0, result.output
        assert captured_kwargs["provider"] == "openrouter"
        assert captured_kwargs["http_referer"] == "https://example.com"
        assert captured_kwargs["x_title"] == "infereval-test"


# ---- Output validation ----------------------------------------------------


class TestOutputShape:
    def test_output_is_valid_evaluation_json(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                ],
            )
        assert result.exit_code == 0
        # Re-validate via the validate subcommand
        v = runner.invoke(cli, ["validate", "--evaluation", str(out_path)])
        assert v.exit_code == 0, v.output

    def test_output_contains_benchmark_hash(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                ],
            )
        with out_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["benchmark_hash"].startswith("sha256:")


# ---- Paraphrase variants on the CLI (Issue #32, Phase 1.2) ---------------


def _para_benchmark_dict() -> dict:
    """A minimal 1-item benchmark with paraphrases on both sa and ra."""
    return {
        "schema_version": "1.0",
        "id": "para-cli",
        "bearers": {
            "sa": {
                "expression": "a is a stop sign",
                "paraphrases": ["a is a roadway stop indicator", "a is an octagonal red sign"],
            },
            "ra": {
                "expression": "a is red",
                "paraphrases": ["a appears red"],
            },
        },
        "analysts": [{"id": "a"}],
        "items": [
            {"id": "i1", "premises": ["sa"], "conclusions": ["ra"], "analyst_verdicts": ["good"]},
        ],
    }


class TestParaphraseCycleCLI:
    """``--paraphrase-variant`` and ``--paraphrase-cycle`` flags on evaluate."""

    def _bench_path(self, tmp_path: Path) -> Path:
        path = tmp_path / "para.json"
        path.write_text(json.dumps(_para_benchmark_dict()), encoding="utf-8")
        return path

    def test_paraphrase_variant_records_value(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"])
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(self._bench_path(tmp_path)),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                    "--paraphrase-variant", "1",
                ],
            )
        assert result.exit_code == 0, result.output
        eta = Evaluation.load(out_path)
        assert eta.paraphrase_variant == 1

    def test_paraphrase_cycle_writes_one_file_per_variant(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        # Need enough scripted responses to cover all variants × items.
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(self._bench_path(tmp_path)),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                    "--paraphrase-cycle",
                ],
            )
        assert result.exit_code == 0, result.output
        # Benchmark has K=3 variants (sa has 2 paraphrases -> 1+2 = 3).
        v0 = tmp_path / "eta-v0.json"
        v1 = tmp_path / "eta-v1.json"
        v2 = tmp_path / "eta-v2.json"
        assert v0.exists() and v1.exists() and v2.exists()
        # Unsuffixed file should NOT exist (cycle writes only suffixed).
        assert not out_path.exists()
        # Each file records its own variant.
        assert Evaluation.load(v0).paraphrase_variant == 0
        assert Evaluation.load(v1).paraphrase_variant == 1
        assert Evaluation.load(v2).paraphrase_variant == 2

    def test_paraphrase_cycle_suffixes_log_path_per_variant(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        log_path = tmp_path / "run.jsonl"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(self._bench_path(tmp_path)),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--log", str(log_path),
                    "--n-samples", "1", "--paraphrase-cycle",
                ],
            )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "run-v0.jsonl").exists()
        assert (tmp_path / "run-v1.jsonl").exists()
        assert (tmp_path / "run-v2.jsonl").exists()
        # Unsuffixed log should NOT exist.
        assert not log_path.exists()

    def test_paraphrase_cycle_suffixes_run_id_per_variant(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(self._bench_path(tmp_path)),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                    "--paraphrase-cycle", "--run-id", "my-run",
                ],
            )
        assert result.exit_code == 0, result.output
        assert Evaluation.load(tmp_path / "eta-v0.json").id == "my-run-v0"
        assert Evaluation.load(tmp_path / "eta-v2.json").id == "my-run-v2"

    def test_paraphrase_variant_out_of_range_rejected(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"])
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(self._bench_path(tmp_path)),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                    "--paraphrase-variant", "99",
                ],
            )
        assert result.exit_code != 0
        assert "out of range" in result.output
        assert "0..2" in result.output  # K-1 = 2

    def test_paraphrase_flags_mutually_exclusive(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"])
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(self._bench_path(tmp_path)),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                    "--paraphrase-variant", "1", "--paraphrase-cycle",
                ],
            )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output

    def test_paraphrase_cycle_on_benchmark_without_paraphrases(self, tmp_path: Path) -> None:
        # Stop-sign benchmark has no bearer paraphrases -> K=1. Cycle
        # should still complete (single run with variant=0), emit a note
        # about no effect, and write the unsuffixed output.
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o",
                    "--output", str(out_path), "--n-samples", "1",
                    "--paraphrase-cycle",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "no effect" in result.output
        # Single variant -> unsuffixed file (per the "len(variants) > 1" gate).
        assert out_path.exists()
        assert not (tmp_path / "eta-v0.json").exists()
