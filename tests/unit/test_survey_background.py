"""--background: one closed question in place of the free-text expertise question."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.survey.qualtrics_csv import merge_respondents, parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.session import BackgroundSpec, load_background

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

PROMPT = "Have you had any formal training in logic or philosophy?"
CHOICES = ("None", "Some", "A degree")
SPEC = BackgroundSpec(PROMPT, CHOICES)


def _expertise(qsf: dict[str, Any]) -> dict[str, Any]:
    (q,) = [
        el["Payload"] for el in qsf["SurveyElements"]
        if el["Element"] == "SQ" and el["Payload"]["DataExportTag"] == "expertise"
    ]
    return q


class TestSpec:
    @pytest.mark.parametrize(
        ("prompt", "choices"),
        [(" ", CHOICES), (PROMPT, ("None",)), (PROMPT, ("None", " None ")), (PROMPT, ("a", ""))],
    )
    def test_invalid(self, prompt: str, choices: tuple[str, ...]) -> None:
        with pytest.raises(ValueError, match="background"):
            BackgroundSpec(prompt, choices)

    def test_load(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text(json.dumps({"prompt": PROMPT, "choices": list(CHOICES)}))
        assert load_background(path) == SPEC
        path.write_text(json.dumps({"prompt": PROMPT, "choices": "None"}))
        with pytest.raises(ValueError, match="must be a list"):
            load_background(path)
        path.write_text(json.dumps({"prompt": PROMPT, "options": list(CHOICES)}))
        with pytest.raises(ValueError, match="unknown keys"):
            load_background(path)


class TestExport:
    def test_closed_question_replaces_free_text(self) -> None:
        bench = Benchmark.load(PULM_PATH)
        q = _expertise(build_qsf(bench, background=SPEC)[0])
        assert q["QuestionID"] == "QID1"
        assert (q["QuestionType"], q["Selector"]) == ("MC", "SAVR")
        assert q["QuestionText"] == PROMPT
        assert [c["Display"] for c in q["Choices"].values()] == list(CHOICES)
        assert q["Validation"]["Settings"]["ForceResponse"] == "ON"

    def test_default_is_free_text(self) -> None:
        q = _expertise(build_qsf(Benchmark.load(PULM_PATH))[0])
        assert q["QuestionType"] == "TE"
        assert q["Validation"]["Settings"]["ForceResponse"] == "OFF"


class TestImport:
    def test_chosen_label_is_expertise_description(self, tmp_path: Path) -> None:
        bench = Benchmark.load(PULM_PATH)
        header = ["ResponseId", "Finished", "expertise"] + [i.id for i in bench.items]
        rows = [[f"R_{n}", "True", label] + ["Good"] * len(bench.items)
                for n, label in enumerate(CHOICES)]
        path = tmp_path / "r.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows([header, header, ["{}"] * len(header), *rows])
        merged = merge_respondents(bench, parse_qualtrics_csv(path), analyst_id_prefix="p-")
        assert [a.expertise_description for a in merged.analysts[1:]] == list(CHOICES)


class TestCli:
    def _paths(self, tmp_path: Path) -> tuple[Path, Path]:
        spec = tmp_path / "background.json"
        spec.write_text(json.dumps({"prompt": PROMPT, "choices": list(CHOICES)}))
        return PULM_PATH, spec

    def test_export_reports_background(self, tmp_path: Path) -> None:
        bench, spec = self._paths(tmp_path)
        out = tmp_path / "s.qsf"
        result = CliRunner().invoke(
            cli, ["survey", "export", str(bench), "-o", str(out), "--background", str(spec)]
        )
        assert result.exit_code == 0, result.output
        assert "Background: one closed question (None / Some / A degree)" in result.output
        assert _expertise(json.loads(out.read_text()))["QuestionType"] == "MC"

    def test_refused_with_expertise_prompt_or_other_platform(self, tmp_path: Path) -> None:
        bench, spec = self._paths(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "survey", "export", str(bench), "-o", str(tmp_path / "s.qsf"),
            "--background", str(spec), "--expertise-prompt", "Your job?",
        ])
        assert result.exit_code == 2
        assert "drop --expertise-prompt" in result.output
        result = runner.invoke(cli, [
            "survey", "export", str(bench), "-o", str(tmp_path / "f.gs"),
            "--platform", "google_forms", "--background", str(spec),
        ])
        assert result.exit_code == 2
        assert "--background is implemented for --platform qualtrics only" in result.output
