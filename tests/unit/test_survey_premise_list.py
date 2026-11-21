"""survey_body {premise_list}/{conclusion_list} and **bold** markup."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from infereval.benchmark import Benchmark
from infereval.survey.google_forms_gas import build_gas_script
from infereval.survey.qualtrics_qsf import _html_text, build_qsf
from infereval.survey.render import as_sentence, render_survey_question, strip_bold

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

LISTED_BODY = "**Premises:**\n{premise_list}\n\n**Conclusion:**\n{conclusion_list}"


def _bench(body: str = LISTED_BODY, header: str = "Judge each case.\n\nDoes it follow?") -> Benchmark:
    raw: dict[str, Any] = json.loads(PULM_PATH.read_text())
    raw["verification_prompt"] = {
        "id": "list-test",
        "template": "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
        "survey_header": header,
        "survey_stem": "Does it follow?",
        "survey_body": body,
    }
    return Benchmark.model_validate(raw)


class TestAsSentence:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Pip is a penguin", "Pip is a penguin."),
            ("the patient has acute dyspnea", "The patient has acute dyspnea."),
            ("Is it raining?", "Is it raining?"),
            ('Leo says, "The key is in the drawer."', 'Leo says, "The key is in the drawer."'),
            ("  Already done.  ", "Already done."),
        ],
    )
    def test_cases(self, text: str, expected: str) -> None:
        assert as_sentence(text) == expected


class TestListedBody:
    def test_one_sentence_per_line_in_model_order(self) -> None:
        bench = _bench()
        item = next(i for i in bench.items if len(i.premises) > 1)
        body = render_survey_question(bench, item).body
        joined = render_survey_question(
            _bench("{premise_context}"), item
        ).body  # the model's premise context, joined by the builder
        lines = body.split("\n")
        assert lines[0] == "**Premises:**"
        bullets = [ln for ln in lines if ln.startswith("• ")]
        assert len(bullets) == len(item.premises) + 1
        assert lines[-2] == "**Conclusion:**" and lines[-1].startswith("• ")
        bullets = bullets[:-1]
        # Same sentences, same order as the model's joined context.
        stripped = [b[2:].rstrip(".") for b in bullets]
        assert [s[0].lower() + s[1:] for s in stripped] == [
            s[0].lower() + s[1:] for s in joined.split(" and ")
        ]

    def test_bad_placeholder_refused(self) -> None:
        with pytest.raises(ValueError, match="premise_list"):
            _bench("{premises}")


class TestBold:
    def test_qualtrics_bold_and_other_platforms_plain(self) -> None:
        assert _html_text("**Premises:**\n• A & B.") == (
            "<strong>Premises:</strong><br>• A &amp; B."
        )
        assert strip_bold("**What you will do**\nRead.") == "What you will do\nRead."
        bench = _bench(header="**Instructions**\n\nJudge each case.\n\nDoes it follow?")
        qsf, mapping = build_qsf(bench, header_mode="instructions", include_rationales=False)
        texts = [el["Payload"]["QuestionText"] for el in qsf["SurveyElements"]
                 if el["Element"] == "SQ"]
        assert any(t.startswith("<strong>Instructions</strong>") for t in texts)
        assert all("**" not in t for t in texts)
        gas, _ = build_gas_script(bench)
        assert "**Premises:**" not in gas and "Premises:" in gas
