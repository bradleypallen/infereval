"""A support prompt's survey_confidence: a rating after each verdict, imported per analyst."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from infereval.benchmark import Benchmark, SurveyConfidence
from infereval.cli.main import cli
from infereval.evaluation import canonical_benchmark_hash
from infereval.prompts import ConfidenceScale, resolve_verification_prompt
from infereval.survey.google_forms_gas import build_gas_script
from infereval.survey.qualtrics_csv import merge_respondents, parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import render_survey_question
from infereval.survey.session import PracticeItem, PracticeSpec
from infereval.survey.surveymonkey_api import build_surveymonkey_payload

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

PROMPT = "How confident are you in that answer?"
LABELS = ["1 Not at all", "2 Slightly", "3 Fairly", "4 Very"]
VERDICTS = ["Good", "Bad", "Can't tell"]


def _bench_dict(confidence: bool = True) -> dict[str, Any]:
    data = json.loads(PULM_PATH.read_text())
    data["verification_prompt"] = {
        "id": "test-v1",
        "template": "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
        "survey_header": "Instructions.\n\nDoes it follow?",
        "survey_stem": "Does it follow?",
        "survey_choices": VERDICTS,
        **({"survey_confidence": {"prompt": PROMPT, "labels": LABELS}} if confidence else {}),
    }
    return data


def _bench(confidence: bool = True) -> Benchmark:
    return Benchmark.model_validate(_bench_dict(confidence))


def _questions(qsf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        el["Payload"]["DataExportTag"]: el["Payload"]
        for el in qsf["SurveyElements"]
        if el["Element"] == "SQ"
    }


def _block_elements(qsf: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    blocks = next(el for el in qsf["SurveyElements"] if el["Element"] == "BL")["Payload"]
    for block in blocks.values() if isinstance(blocks, dict) else blocks:
        elements = block.get("BlockElements", [])
        if any(be.get("QuestionID") == qid for be in elements):
            return list(elements)
    raise AssertionError(f"{qid} in no block")


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerow(header)  # question-text row
        w.writerow(["{}"] * len(header))  # ImportId row
        w.writerows(rows)
    return path


def _responses_csv(tmp_path: Path, bench: Benchmark, ratings: list[list[str]]) -> Path:
    """One Qualtrics row per entry of ``ratings`` (one confidence label per item)."""
    _, mapping = build_qsf(bench, header_mode="instructions", include_rationales=False)
    header = ["ResponseId", "Finished", "expertise"]
    for row in mapping:
        header += [row["verdict_data_export_tag"], row["confidence_data_export_tag"]]
    rows = []
    for n, per_item in enumerate(ratings):
        cells = [f"R_{n}", "True", ""]
        for i, label in enumerate(per_item):
            cells += [VERDICTS[i % 3], label]
        rows.append(cells)
    return _write_csv(tmp_path / "responses.csv", header, rows)


class TestDeclaration:
    @pytest.mark.parametrize(
        ("prompt", "labels"),
        [("", ["a", "b"]), ("How?", ["only"]), ("How?", ["a", "a"]), ("How?", ["a", " "])],
    )
    def test_invalid_scale_rejected(self, prompt: str, labels: list[str]) -> None:
        with pytest.raises(ValidationError, match="survey_confidence"):
            SurveyConfidence(prompt=prompt, labels=labels)

    def test_resolved_prompt_carries_scale(self) -> None:
        vp = resolve_verification_prompt(_bench().verification_prompt)
        assert vp.survey_confidence == ConfidenceScale(PROMPT, tuple(LABELS))

    def test_value_is_label_position(self) -> None:
        scale = ConfidenceScale(PROMPT, tuple(LABELS))
        assert [scale.value_of(f" {lab} ") for lab in LABELS] == [1, 2, 3, 4]
        with pytest.raises(ValueError, match="unrecognised confidence"):
            scale.value_of("Very")

    def test_confidence_lengths_checked(self) -> None:
        data = _bench_dict()
        m = len(data["analysts"])
        data["items"][0]["analyst_confidences"] = [None] * (m + 1)
        with pytest.raises(ValidationError, match="confidence ratings"):
            Benchmark.model_validate(data)
        data["items"][0]["analyst_confidences"] = [0] * m
        with pytest.raises(ValidationError, match="below 1"):
            Benchmark.model_validate(data)

    def test_hash_of_benchmark_without_ratings_unchanged(self) -> None:
        # exclude_none keeps the new optional field out of existing hashes.
        bench = Benchmark.load(PULM_PATH)
        assert all(item.analyst_confidences is None for item in bench.items)
        assert canonical_benchmark_hash(bench) == canonical_benchmark_hash(
            Benchmark.model_validate(json.loads(PULM_PATH.read_text()))
        )
        assert "analyst_confidences" not in json.dumps(
            bench.model_dump(mode="json", exclude_none=True)
        )


class TestExport:
    def test_rendered_question_carries_scale(self) -> None:
        bench = _bench()
        assert render_survey_question(bench, bench.items[0]).confidence == ConfidenceScale(
            PROMPT, tuple(LABELS)
        )
        assert render_survey_question(_bench(False), bench.items[0]).confidence is None

    def test_confidence_follows_each_verdict_on_its_page(self) -> None:
        qsf, mapping = build_qsf(_bench(), header_mode="instructions")
        qs = _questions(qsf)
        for row in mapping:
            tag = row["verdict_data_export_tag"]
            assert row["confidence_data_export_tag"] == f"{tag}_confidence"
            conf = qs[f"{tag}_confidence"]
            assert conf["QuestionText"] == PROMPT
            assert [c["Display"] for c in conf["Choices"].values()] == LABELS
            assert conf["Validation"]["Settings"]["ForceResponse"] == "ON"
            # verdict, confidence, rationale: one block, no page break between.
            elements = _block_elements(qsf, qs[tag]["QuestionID"])
            ids = [be.get("QuestionID") for be in elements]
            v = ids.index(qs[tag]["QuestionID"])
            assert ids[v + 1] == conf["QuestionID"]
            assert ids[v + 2] == qs[f"{tag}_rationale"]["QuestionID"]

    def test_no_confidence_without_declaration(self) -> None:
        qsf, mapping = build_qsf(_bench(False), header_mode="instructions")
        assert all(row["confidence_data_export_tag"] is None for row in mapping)
        assert not any(t.endswith("_confidence") for t in _questions(qsf))

    def test_practice_items_ask_confidence_on_same_page(self) -> None:
        practice = PracticeSpec(items=(PracticeItem("kettle", ("Sam boils a kettle",), "Hot"),))
        qsf, _ = build_qsf(_bench(), header_mode="instructions", practice=practice)
        qs = _questions(qsf)
        elements = _block_elements(qsf, qs["practice_kettle"]["QuestionID"])
        ids = [be.get("QuestionID") for be in elements]
        k = ids.index(qs["practice_kettle"]["QuestionID"])
        assert ids[k + 1] == qs["practice_kettle_confidence"]["QuestionID"]
        assert elements[k - 1] == {"Type": "Page Break"}

    @pytest.mark.parametrize(
        "build", [build_gas_script, build_surveymonkey_payload], ids=["google", "surveymonkey"]
    )
    def test_other_platforms_refuse(self, build: Any) -> None:
        with pytest.raises(ValueError, match="only by the Qualtrics export"):
            build(_bench())


class TestImport:
    def test_ratings_parsed_and_merged(self, tmp_path: Path) -> None:
        bench = _bench()
        n = len(bench.items)
        ratings = [[LABELS[i % 4] for i in range(n)], [LABELS[3]] * n]
        path = _responses_csv(tmp_path, bench, ratings)
        scale = resolve_verification_prompt(bench.verification_prompt).survey_confidence
        respondents = parse_qualtrics_csv(path, choices=tuple(VERDICTS), confidence=scale)
        assert [len(r.confidences) for r in respondents] == [n, n]
        assert not any(t.endswith("_confidence") for r in respondents for t in r.verdicts)

        merged = merge_respondents(bench, respondents, require_complete=True)
        m = len(bench.analysts)
        for i, item in enumerate(merged.items):
            assert item.analyst_confidences == [None] * m + [i % 4 + 1, 4]

    def test_unknown_label_raises_with_location(self, tmp_path: Path) -> None:
        bench = _bench()
        path = _responses_csv(tmp_path, bench, [["Very"] * len(bench.items)])
        with pytest.raises(ValueError, match="_confidence.*unrecognised confidence"):
            parse_qualtrics_csv(
                path, choices=tuple(VERDICTS),
                confidence=ConfidenceScale(PROMPT, tuple(LABELS)),
            )

    def test_blank_rating_is_none(self, tmp_path: Path) -> None:
        bench = _bench()
        n = len(bench.items)
        path = _responses_csv(tmp_path, bench, [[""] + [LABELS[1]] * (n - 1)])
        respondents = parse_qualtrics_csv(
            path, choices=tuple(VERDICTS), confidence=ConfidenceScale(PROMPT, tuple(LABELS))
        )
        merged = merge_respondents(bench, respondents)
        assert merged.items[0].analyst_confidences[-1] is None
        assert merged.items[1].analyst_confidences[-1] == 2

    def test_cli_import_uses_prompt_scale(self, tmp_path: Path) -> None:
        bench = _bench()
        bench_path = tmp_path / "bench.json"
        bench_path.write_text(bench.model_dump_json())
        path = _responses_csv(tmp_path, bench, [[LABELS[2]] * len(bench.items)])
        out = tmp_path / "merged.json"
        result = CliRunner().invoke(cli, [
            "survey", "import", str(bench_path), "-r", str(path), "-o", str(out),
            "--platform", "qualtrics",
        ])
        assert result.exit_code == 0, result.output
        merged = Benchmark.load(out)
        assert {item.analyst_confidences[-1] for item in merged.items} == {3}


class TestExportCli:
    def test_qualtrics_export_reports_confidence(self, tmp_path: Path) -> None:
        bench_path, out = tmp_path / "bench.json", tmp_path / "s.qsf"
        bench_path.write_text(_bench().model_dump_json())
        result = CliRunner().invoke(cli, [
            "survey", "export", str(bench_path), "-o", str(out), "--header-mode", "instructions",
        ])
        assert result.exit_code == 0, result.output
        assert "Confidence: asked after every verdict (4 labels" in result.output
        mapping = json.loads((tmp_path / "s.qsf.mapping.json").read_text())
        assert all(row["confidence_data_export_tag"] for row in mapping)

    def test_other_platform_exits_2(self, tmp_path: Path) -> None:
        bench_path, out = tmp_path / "bench.json", tmp_path / "f.gs"
        bench_path.write_text(_bench().model_dump_json())
        result = CliRunner().invoke(cli, [
            "survey", "export", str(bench_path), "-o", str(out), "--platform", "google_forms",
        ])
        assert result.exit_code == 2
        assert "qualtrics only" in result.output
        assert not out.exists()
