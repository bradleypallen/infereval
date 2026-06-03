"""Tests for ``infereval survey import`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli

QUALTRICS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "qualtrics"
    / "responses_known_good.csv"
)
GOOGLE_FORMS_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "google_forms"
    / "responses_known_good.csv"
)
SURVEYMONKEY_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "surveymonkey"
    / "responses_known_good.csv"
)


@pytest.fixture
def five_item_benchmark_path(tmp_path: Path) -> Path:
    """Synthetic 5-item benchmark matching the CSV fixtures' item ids."""
    from infereval.benchmark import BearerModel, BenchmarkItem
    from infereval.types import Verdict

    bench = Benchmark(
        id="merge-test",
        bearers={
            "p": BearerModel(expression="premise"),
            "c": BearerModel(expression="conclusion"),
        },
        analysts=[{"id": "seed"}],
        items=[
            BenchmarkItem(
                id=f"item_00{i+1}",
                premises=["p"],
                conclusions=["c"],
                analyst_verdicts=[Verdict.GOOD],
            )
            for i in range(5)
        ],
    )
    path = tmp_path / "bench.json"
    path.write_text(bench.model_dump_json(indent=2))
    return path


class TestQualtricsImport:
    def test_two_respondents_merged(self, five_item_benchmark_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        runner = CliRunner()
        # R_gamma is incomplete; use --allow-partial to merge all 3.
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(QUALTRICS_FIXTURE),
                "-o", str(out),
                "--allow-partial",
            ],
        )
        assert result.exit_code == 0, result.output
        merged = Benchmark.load(out)
        assert len(merged.analysts) == 4  # seed + 3 from CSV

    def test_require_complete_rejects_partials(self, five_item_benchmark_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(QUALTRICS_FIXTURE),
                "-o", str(out),
            ],
        )
        # Default require-complete; R_gamma is incomplete.
        assert result.exit_code == 2
        assert "incomplete respondent" in result.output

    def test_respondent_filter(self, five_item_benchmark_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(QUALTRICS_FIXTURE),
                "-o", str(out),
                "--respondent", "R_alpha",
            ],
        )
        assert result.exit_code == 0, result.output
        merged = Benchmark.load(out)
        assert len(merged.analysts) == 2
        assert merged.analysts[1].id == "clinician-R_alpha"

    def test_unknown_respondent_id(self, five_item_benchmark_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(QUALTRICS_FIXTURE),
                "-o", str(out),
                "--respondent", "R_does_not_exist",
            ],
        )
        assert result.exit_code == 2
        assert "no respondent matched" in result.output


class TestGoogleFormsImport:
    def test_two_respondents_merged(self, five_item_benchmark_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(GOOGLE_FORMS_FIXTURE),
                "-o", str(out),
                "--platform", "google_forms",
            ],
        )
        assert result.exit_code == 0, result.output
        merged = Benchmark.load(out)
        assert len(merged.analysts) == 3  # seed + 2 from CSV


class TestSurveyMonkeyImport:
    def test_two_respondents_merged(self, five_item_benchmark_path: Path, tmp_path: Path) -> None:
        out = tmp_path / "merged.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(SURVEYMONKEY_FIXTURE),
                "-o", str(out),
                "--platform", "surveymonkey",
            ],
        )
        assert result.exit_code == 0, result.output
        merged = Benchmark.load(out)
        assert len(merged.analysts) == 3


class TestMappingSidecar:
    def test_mapping_explicit_path(
        self, five_item_benchmark_path: Path, tmp_path: Path
    ) -> None:
        """Explicit `--mapping` is loaded and threaded into the merger."""
        # Build a mapping sidecar with one custom override
        # (item_001 → custom_tag_001) so we can verify the override path
        # is wired through end-to-end.
        mapping_path = tmp_path / "mapping.json"
        mapping = [
            {"item_id": "item_001", "verdict_data_export_tag": "item_001"},
            {"item_id": "item_002", "verdict_data_export_tag": "item_002"},
            {"item_id": "item_003", "verdict_data_export_tag": "item_003"},
            {"item_id": "item_004", "verdict_data_export_tag": "item_004"},
            {"item_id": "item_005", "verdict_data_export_tag": "item_005"},
        ]
        mapping_path.write_text(json.dumps(mapping))

        out = tmp_path / "merged.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "import", str(five_item_benchmark_path),
                "-r", str(QUALTRICS_FIXTURE),
                "-o", str(out),
                "--mapping", str(mapping_path),
                "--respondent", "R_alpha",
            ],
        )
        assert result.exit_code == 0, result.output
        merged = Benchmark.load(out)
        # Item_001 → R_alpha said GOOD.
        from infereval.types import Verdict
        assert merged.items[0].analyst_verdicts[-1] == Verdict.GOOD
