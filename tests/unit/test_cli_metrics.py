"""Tests for ``infereval metrics``."""

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
    """Run evaluate against a patched provider matching the paper's analyst row."""
    out = tmp_path / "eta.json"
    provider = ScriptedProvider(responses=["GOOD"] * 9 + ["BAD"] * 3)
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
                "--question-form", "support",
            ],
        )
        assert result.exit_code == 0, result.output
    return out


# ---- Text format ----------------------------------------------------------


class TestTextFormat:
    def test_default_format_is_text(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["metrics", str(stop_sign_eta_file)])
        assert result.exit_code == 0, result.output
        assert "Overall" in result.output
        assert "n (items)" in result.output
        assert "coverage (M)           : 1.0000" in result.output
        assert "κ_C(η, consensus)       : +1.0000" in result.output
        assert "κ_F(η)" in result.output

    def test_kappa_f_star_shown_as_undefined(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["metrics", str(stop_sign_eta_file), "--benchmark", str(STOP_SIGN_PATH)]
        )
        # Single-analyst stop-sign benchmark -> κ_F* undefined
        assert "κ_F*(β) (inter-analyst, all): undefined" in result.output


# ---- Markdown format ------------------------------------------------------


class TestMarkdownFormat:
    def test_markdown_renders_table(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["metrics", str(stop_sign_eta_file), "--format", "markdown"]
        )
        assert result.exit_code == 0, result.output
        assert "## Overall" in result.output
        assert "| metric | value |" in result.output
        assert "| coverage(M) | 1.0000 |" in result.output


# ---- JSON format ----------------------------------------------------------


class TestJsonFormat:
    def test_json_is_parseable(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["metrics", str(stop_sign_eta_file), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        # Output is one JSON object per section, separated by blank lines
        # (or just one for overall with no filters).
        data = json.loads(result.output.strip())
        assert data["n"] == 4
        assert data["coverage"] == 1.0
        assert data["cohens_kappa[consensus]"] == 1.0
        assert data["title"] == "Overall"


# ---- --reference --------------------------------------------------------


class TestReference:
    def test_reference_analyst_index(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--reference", "analyst:0",
                "--format", "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output.strip())
        assert "cohens_kappa[analyst[0]]" in data

    def test_reference_analyst_id_requires_benchmark(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--reference", "analyst:paper-author",
            ],
        )
        # Without --benchmark, can't resolve the id
        assert result.exit_code != 0
        assert "requires --benchmark" in result.output

    def test_reference_analyst_id_with_benchmark(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--benchmark", str(STOP_SIGN_PATH),
                "--reference", "analyst:paper-author",
                "--format", "json",
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output.strip())
        assert data["cohens_kappa[analyst[0]]"] == 1.0

    def test_unknown_reference_spec_rejected(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["metrics", str(stop_sign_eta_file), "--reference", "weirdo"]
        )
        assert result.exit_code != 0
        assert "Unknown reference spec" in result.output


# ---- --by-tag -----------------------------------------------------------


class TestByTag:
    def test_single_tag(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["metrics", str(stop_sign_eta_file), "--by-tag", "defeater"],
        )
        assert result.exit_code == 0, result.output
        assert "By tag: defeater" in result.output
        # Defeater subset has 1 item -- coverage line should appear
        assert "n (items)              : 1" in result.output

    def test_multiple_tags(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--by-tag", "defeater",
                "--by-tag", "base-inference",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "By tag: defeater" in result.output
        assert "By tag: base-inference" in result.output


# ---- --by-rsr-target ----------------------------------------------------


class TestByRsrTarget:
    def test_requires_benchmark(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--by-rsr-target", '{"X": ["sa"], "A": ["ra"]}',
            ],
        )
        assert result.exit_code != 0
        assert "requires --benchmark" in result.output

    def test_with_benchmark_matches_target(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--benchmark", str(STOP_SIGN_PATH),
                "--by-rsr-target", '{"X": ["sa"], "A": ["ra"]}',
            ],
        )
        assert result.exit_code == 0, result.output
        assert "By RSR target" in result.output
        # All 4 stop-sign items target ⟨{sa}, {ra}⟩
        # Search for the subset section's n line
        sections = result.output.split("By RSR target")
        assert "n (items)              : 4" in sections[1]

    def test_malformed_json_rejected(self, stop_sign_eta_file: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "metrics", str(stop_sign_eta_file),
                "--benchmark", str(STOP_SIGN_PATH),
                "--by-rsr-target", "{not valid json",
            ],
        )
        assert result.exit_code != 0
        assert "must be JSON" in result.output


# ---- Failure modes ------------------------------------------------------


class TestFailureModes:
    def test_missing_evaluation_file(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["metrics", "/nope/missing.json"])
        assert result.exit_code != 0
