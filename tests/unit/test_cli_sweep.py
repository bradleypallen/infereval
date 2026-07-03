"""Tests for --coherence-frame threading on ``infereval sweep``.

The broader sweep CLI surface is covered in tests/unit/test_sweep.py
(TestSweepCLI); this module holds the coherence-frame threading tests
alongside the other CLI frame tests (test_cli_evaluate.py /
test_cli_retest_auto.py). The provider is mocked by patching
:func:`infereval.cli.sweep_cmd.get_provider`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from infereval.cli.main import cli
from infereval.evaluation import Evaluation
from infereval.providers.mock import ScriptedProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


class TestSweepCoherenceFrame:
    def test_explicit_frame_recorded_in_per_value_etas(self, tmp_path: Path) -> None:
        """--coherence-frame is held fixed across the sweep; every
        per-value eta records the resolved id in endorsement_config."""
        # 4 items × (1 + 2) samples across the two swept values.
        provider = ScriptedProvider(responses=["INCOHERENT"] * 12)
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
                    "--values", "1,2",
                    "--out-dir", str(tmp_path),
                    "--coherence-frame", "defeasible-coherence-explicit-v1",
                ],
            )
        assert result.exit_code == 0, result.output
        for value in (1, 2):
            eta = Evaluation.load(tmp_path / f"sweep-n_samples={value}-eta.json")
            assert eta.endorsement_config.coherence_frame_id == (
                "defeasible-coherence-explicit-v1"
            )

    def test_unknown_frame_id_exits_nonzero(self, tmp_path: Path) -> None:
        """An unknown frame id fails fast — before any provider client is
        constructed or sweep value is run."""
        runner = CliRunner()
        # No get_provider patch: the frame lookup precedes provider
        # construction, so no provider (or API key) is ever needed.
        result = runner.invoke(
            cli,
            [
                "sweep", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o",
                "--vary", "n_samples",
                "--values", "1,2",
                "--out-dir", str(tmp_path),
                "--coherence-frame", "no-such-frame-v1",
            ],
        )
        assert result.exit_code == 2
        assert "unknown coherence_frame_id" in result.output
        assert not (tmp_path / "sweep-summary.json").exists()
