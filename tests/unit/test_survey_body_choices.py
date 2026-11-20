"""A support prompt's survey_body / survey_choices: the case as the model saw it."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from infereval.benchmark import Benchmark, VerificationPromptOverride
from infereval.context import resolve_context_builders
from infereval.endorsement import endorse
from infereval.evaluation import EndorsementConfig, ProviderParams
from infereval.prompts import resolve_verification_prompt
from infereval.providers.mock import StaticOkProvider
from infereval.survey.qualtrics_csv import parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import (
    DEFAULT_VERDICT_CHOICES,
    render_survey_question,
    verdict_from_choice_text,
)
from infereval.types import Verdict

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"
FIXTURE = ROOT / "tests" / "fixtures" / "qualtrics" / "responses_known_good.csv"

TEMPLATE = "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:"
BODY = "Premises: {premise_context}\nConclusion: {conclusion_context}"
LABELS = ["Good", "Bad", "Can't tell"]


def _bench(**survey: Any) -> Benchmark:
    data = json.loads(PULM_PATH.read_text())
    data["context_builders"] = {
        "premise": {"kind": "template", "template": "{expressions}", "joiner": " and "},
        "conclusion": {"kind": "template", "template": "{expressions}", "joiner": " or "},
    }
    data["verification_prompt"] = {
        "id": "test-v1",
        "system": "Judge it.",
        "template": TEMPLATE,
        "survey_header": "Instructions.\n\nDoes it follow?",
        "survey_stem": "Does it follow?",
        **survey,
    }
    return Benchmark.model_validate(data)


def _model_user_prompt(bench: Benchmark, item_index: int) -> str:
    item = bench.items[item_index]
    pb, cb = resolve_context_builders(bench.context_builders)
    record = endorse(
        item.to_implication(),
        bench.runtime_bearers(),
        StaticOkProvider(),
        EndorsementConfig(n_samples=1),
        ProviderParams(),
        premise_builder=pb,
        conclusion_builder=cb,
        verification_prompt=resolve_verification_prompt(bench.verification_prompt),
    )
    return record.rendered_user_prompt


class TestOverrideValidation:
    def test_body_placeholders_checked(self) -> None:
        with pytest.raises(ValidationError, match="placeholders"):
            VerificationPromptOverride(template=TEMPLATE, survey_body="Case: {case}")

    @pytest.mark.parametrize("labels", [["Good", "Bad"], ["Good", "Good", "Bad"], ["a", "", "c"]])
    def test_choices_checked(self, labels: list[str]) -> None:
        with pytest.raises(ValidationError, match="three distinct"):
            VerificationPromptOverride(template=TEMPLATE, survey_choices=labels)

    def test_resolved_prompt_carries_both(self) -> None:
        vp = resolve_verification_prompt(
            VerificationPromptOverride(template=TEMPLATE, survey_body=BODY, survey_choices=LABELS)
        )
        assert vp.survey_body == BODY
        assert vp.survey_choices == tuple(LABELS)


class TestRender:
    def test_body_is_the_models_stimulus(self) -> None:
        bench = _bench(survey_body=BODY)
        # Items with several premises exercise the joiner and bearer order.
        multi = next(i for i, it in enumerate(bench.items) if len(it.premises) > 1)
        for idx in (0, multi):
            sq = render_survey_question(bench, bench.items[idx])
            assert sq.body + "\nVerdict:" == _model_user_prompt(bench, idx)
        assert " and " in render_survey_question(bench, bench.items[multi]).body

    def test_choices_replace_default_labels(self) -> None:
        sq = render_survey_question(_bench(survey_choices=LABELS), _bench().items[0])
        assert sq.choices == tuple(LABELS)

    def test_defaults_unchanged_without_fields(self) -> None:
        bench = _bench()
        sq = render_survey_question(bench, bench.items[0])
        assert sq.choices == DEFAULT_VERDICT_CHOICES
        assert sq.body.startswith("Premises:\n- ")

    def test_qsf_uses_body_stem_and_labels(self) -> None:
        bench = _bench(survey_body=BODY, survey_choices=LABELS)
        qsf, mapping = build_qsf(bench, header_mode="instructions", include_rationales=False)
        q = next(
            el["Payload"] for el in qsf["SurveyElements"]
            if el["Element"] == "SQ"
            and el["Payload"]["DataExportTag"] == mapping[0]["verdict_data_export_tag"]
        )
        assert q["QuestionText"].startswith("Premises: ")
        assert q["QuestionText"].endswith("\n\nDoes it follow?")
        assert [c["Display"] for c in q["Choices"].values()] == LABELS


class TestDecode:
    def test_declared_labels_decode_by_position(self) -> None:
        got = [verdict_from_choice_text(c, choices=tuple(LABELS)) for c in LABELS]
        assert got == [Verdict.GOOD, Verdict.BAD, Verdict.ABSTAIN]

    def test_cant_tell_needs_declared_labels(self) -> None:
        with pytest.raises(ValueError, match="unrecognised"):
            verdict_from_choice_text("Can't tell")

    def test_default_labels_still_decode_with_choices(self) -> None:
        assert verdict_from_choice_text(
            DEFAULT_VERDICT_CHOICES[2], choices=tuple(LABELS)
        ) is Verdict.ABSTAIN

    def test_qualtrics_import_with_declared_labels(self, tmp_path: Path) -> None:
        rows = list(csv.reader(FIXTURE.open(encoding="utf-8")))
        relabel = {
            "good": "Good", "bad": "Bad", "abstain": "Can't tell",
        }
        for row in rows[3:]:
            for i, cell in enumerate(row):
                first = cell.split()[0].lower() if cell.strip() else ""
                if first in relabel and "—" in cell:
                    row[i] = relabel[first]
        path = tmp_path / "relabelled.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)
        got = parse_qualtrics_csv(path, choices=tuple(LABELS))
        assert [r.verdicts for r in got] == [r.verdicts for r in parse_qualtrics_csv(FIXTURE)]
