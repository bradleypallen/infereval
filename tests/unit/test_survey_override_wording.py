"""A benchmark's own verification prompt can declare its survey wording.

Before this, ``VerificationPromptOverride`` had no survey fields, so a
benchmark with a custom prompt always exported surveys under the default-v1
("good diagnostic inference") header: humans and the model were asked
different questions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError

from infereval.benchmark import Benchmark, VerificationPromptOverride
from infereval.cli.main import cli
from infereval.prompts import resolve_verification_prompt
from infereval.survey.render import DEFAULT_QUESTION_HEADER, render_survey_question

HEADER = (
    "Treat every stated premise as true and use ordinary background knowledge. "
    "Do the premises give a reasonable basis for drawing the proposed conclusion?"
)
STEM = "Do the premises give a reasonable basis for drawing the proposed conclusion?"


def _bench(**vp_extra: str) -> Benchmark:
    vp = {"id": "custom-v1", "system": "Judge the inference.",
          "template": "Premises: {premise_context}\nConclusion: {conclusion_context}"} | vp_extra
    return Benchmark.model_validate({
        "id": "override-wording",
        "bearers": {"s": {"expression": "there is a stop sign beside the road"},
                    "r": {"expression": "the sign has a red background"}},
        "analysts": [{"id": "a1"}],
        "items": [{"id": "i0", "premises": ["s"], "conclusions": ["r"], "analyst_verdicts": ["good"]}],
        "verification_prompt": vp,
    })


def test_override_survey_wording_reaches_the_resolved_prompt() -> None:
    b = _bench(survey_header=HEADER, survey_stem=STEM)
    vp = resolve_verification_prompt(b.verification_prompt)
    assert (vp.id, vp.survey_header, vp.survey_stem) == ("custom-v1", HEADER, STEM)


def test_support_survey_uses_override_header_and_stem(caplog: pytest.LogCaptureFixture) -> None:
    b = _bench(survey_header=HEADER, survey_stem=STEM)
    with caplog.at_level(logging.WARNING, logger="infereval.survey.render"):
        q = render_survey_question(b, b.items[0])
    assert q.header == HEADER and q.stem == STEM and q.frame_id == "custom-v1"
    assert "diagnostic" not in q.full_text()
    assert q.body_with_stem().endswith(STEM)
    assert not any("survey.frame.fallback" in r.getMessage() for r in caplog.records)


def test_override_without_survey_wording_still_falls_back_with_a_pointer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    b = _bench()
    with caplog.at_level(logging.WARNING, logger="infereval.survey.render"):
        q = render_survey_question(b, b.items[0])
    assert q.header == DEFAULT_QUESTION_HEADER and q.frame_id == "default-v1"
    msgs = [r.getMessage() for r in caplog.records if "survey.frame.fallback" in r.getMessage()]
    assert msgs and "Declare survey_header" in msgs[0]


@pytest.mark.parametrize(
    ("extra", "match"),
    [
        ({"survey_stem": STEM}, "requires survey_header"),
        ({"survey_header": HEADER, "survey_stem": "Is the conclusion true?"}, "trailing substring"),
    ],
)
def test_stem_must_end_the_header(extra: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        VerificationPromptOverride.model_validate({"template": "{premise_context} {conclusion_context}"} | extra)


def test_qualtrics_export_carries_override_wording(tmp_path: Path) -> None:
    bench_path = tmp_path / "b.json"
    bench_path.write_text(_bench(survey_header=HEADER, survey_stem=STEM).model_dump_json())
    out = tmp_path / "survey.qsf"
    result = CliRunner().invoke(cli, ["survey", "export", str(bench_path), "-o", str(out)])
    assert result.exit_code == 0, result.output
    text = out.read_text()
    assert "reasonable basis for drawing the proposed conclusion" in text
    assert "diagnostic inference" not in text
    # a non-default frame always gets a mapping sidecar recording which frame the humans saw
    sidecars = [p for p in tmp_path.iterdir() if p.suffix == ".json" and p.name != "b.json"]
    assert sidecars, sorted(p.name for p in tmp_path.iterdir())
    assert any("custom-v1" in json.dumps(json.loads(p.read_text())) for p in sidecars)
