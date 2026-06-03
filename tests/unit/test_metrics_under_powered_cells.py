"""Tests for v0.8.0 under-powered per-cell rendering (closes #84).

The ``infereval metrics --by-tag`` / ``--by-rsr-target`` CLI renderers
extend decomposition cells with the substantive-n and per-class verdict
counts, and gate an ``[under-powered: n < 10]`` annotation on the κ_C
and κ_F lines when the cell's substantive subset falls below
:data:`infereval.metrics.MIN_K_FOR_SUBSAMPLING_CI`.

Headline ("Overall") rendering is unchanged — that path already has
``--ci`` for reliability, so no double-counting.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from infereval.cli.main import cli
from infereval.providers.mock import ScriptedProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


@pytest.fixture
def stop_sign_eta_file(tmp_path: Path) -> Path:
    """Stop-sign evaluation (4 items, all GOOD)."""
    out = tmp_path / "eta.json"
    provider = ScriptedProvider(responses=["GOOD"] * 12)
    with patch(
        "infereval.cli.evaluate_cmd.get_provider", return_value=provider
    ):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "evaluate", str(STOP_SIGN_PATH),
                "--provider", "openai", "--model", "gpt-4o-mini",
                "--output", str(out),
                "--n-samples", "3",
            ],
        )
        assert result.exit_code == 0, result.output
    return out


# ---- Decomposition cells: small (n < 10) -------------------------------


class TestUnderPoweredByTag:
    """The bundled stop-sign benchmark has only 4 items, so every by-tag
    subset is under-powered. These tests assert the annotation fires and
    the new n + class-count lines render."""

    def test_text_format_emits_under_powered_annotation_on_kappa_lines(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metrics", str(stop_sign_eta_file), "--by-tag", "defeater"],
        )
        assert result.exit_code == 0, result.output
        # The annotation must appear on κ_C and κ_F lines in the by-tag
        # cell.
        by_tag_section = result.output.split("By tag: defeater")[1]
        assert "[under-powered: n < 10]" in by_tag_section
        # The annotation must appear on BOTH κ_C and κ_F lines (the issue
        # gates the label on the kappa, not as a banner).
        kappa_lines = [
            line for line in by_tag_section.splitlines()
            if line.startswith("κ_C") or line.startswith("κ_F(")
        ]
        assert len(kappa_lines) == 2
        for line in kappa_lines:
            assert "[under-powered: n < 10]" in line

    def test_text_format_emits_n_substantive_and_class_counts(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metrics", str(stop_sign_eta_file), "--by-tag", "defeater"],
        )
        assert result.exit_code == 0, result.output
        by_tag_section = result.output.split("By tag: defeater")[1]
        assert "n (substantive)" in by_tag_section
        assert "M verdicts" in by_tag_section
        assert "reference verdicts" in by_tag_section
        assert "good " in by_tag_section
        assert "bad " in by_tag_section
        assert "abstain " in by_tag_section

    def test_markdown_format_emits_under_powered_in_kappa_rows(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--by-tag", "defeater",
                "--format", "markdown",
            ],
        )
        assert result.exit_code == 0, result.output
        by_tag_section = result.output.split("## By tag: defeater")[1]
        # Annotation lives inside the κ_C and κ_F table rows.
        assert "| κ_C(" in by_tag_section
        assert "| κ_F(η) |" in by_tag_section
        assert "[under-powered: n < 10]" in by_tag_section
        # The new table rows must also be present.
        assert "| n (substantive) |" in by_tag_section
        assert "| M verdicts |" in by_tag_section
        assert "| reference verdicts |" in by_tag_section

    def test_json_format_carries_cell_summary_keys(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--by-tag", "defeater",
                "--format", "json",
            ],
        )
        assert result.exit_code == 0, result.output
        sections = [
            json.loads(blob)
            for blob in result.output.strip().split("\n\n")
            if blob.strip()
        ]
        by_tag = next(s for s in sections if s.get("title") == "By tag: defeater")
        assert "n_substantive" in by_tag
        assert "m_counts" in by_tag
        assert "r_counts" in by_tag
        assert by_tag["under_powered"] is True
        assert by_tag["under_powered_threshold"] == 10
        # Class-count dict keys are the Verdict string values.
        assert set(by_tag["m_counts"]) == {"good", "bad", "abstain"}


# ---- Headline (Overall) is untouched -------------------------------------


class TestOverallUnchanged:
    """The headline cell must NOT carry the new n + class-count lines or
    the under-powered annotation. That path has its own ``--ci``
    reliability machinery; per-cell guard would double-count.
    """

    def test_text_overall_does_not_emit_cell_summary_lines(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["metrics", str(stop_sign_eta_file)])
        assert result.exit_code == 0, result.output
        overall_section = result.output.split("Overall")[1].split("By tag:")[0]
        assert "n (substantive)" not in overall_section
        assert "M verdicts" not in overall_section
        assert "reference verdicts" not in overall_section
        assert "[under-powered" not in overall_section

    def test_markdown_overall_does_not_emit_cell_summary_rows(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metrics", str(stop_sign_eta_file), "--format", "markdown"],
        )
        assert result.exit_code == 0, result.output
        assert "## Overall" in result.output
        assert "| n (substantive) |" not in result.output
        assert "| M verdicts |" not in result.output
        assert "[under-powered" not in result.output

    def test_json_overall_does_not_carry_cell_summary_keys(
        self, stop_sign_eta_file: Path
    ) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["metrics", str(stop_sign_eta_file), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output.strip())
        assert data["title"] == "Overall"
        assert "n_substantive" not in data
        assert "m_counts" not in data
        assert "r_counts" not in data
        assert "under_powered" not in data


# ---- Decomposition cells: healthy (n >= 10) -----------------------------


class TestHealthyDecompositionCell:
    """When a by-tag cell has substantive-n at or above the threshold,
    the n + class-count lines still appear (information addition) but
    the under-powered annotation does NOT fire."""

    def test_n_at_threshold_drops_annotation(self, tmp_path: Path) -> None:
        """Build a synthetic eta with exactly 10 same-tag items, all
        substantive — the cell's n_substantive is 10, equal to the
        threshold, so the annotation must NOT fire."""
        from infereval.evaluation import Evaluation
        from infereval.types import Verdict

        from ..conftest import build_evaluation

        eta = build_evaluation(
            rows=[([Verdict.GOOD], Verdict.GOOD)] * 10,
            tags_per_row=[["healthy"]] * 10,
        )
        eta_path = tmp_path / "eta.json"
        eta_path.write_text(eta.model_dump_json())
        # Round-trip through .load to make sure the file is valid.
        Evaluation.load(eta_path)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metrics", str(eta_path), "--by-tag", "healthy"],
        )
        assert result.exit_code == 0, result.output
        by_tag_section = result.output.split("By tag: healthy")[1]
        # The new lines DO appear...
        assert "n (substantive)        : 10" in by_tag_section
        # ...but the annotation does NOT.
        assert "[under-powered" not in by_tag_section
