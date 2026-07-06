"""Default-path survey exports are byte-unchanged by the frame axis.

The fixtures under ``tests/fixtures/survey_preframe/`` were generated at
commit 18b4129 — the survey-frame core had landed in ``render.py`` but the
exporters had NOT yet been touched (they were last changed in v0.17.4).
They are the pre-frame-threading golden bytes of each platform's main
artifact on the default path, serialized exactly as the CLI writes them
(``json.dumps(..., indent=2)`` for Qualtrics/SurveyMonkey, raw source for
Google Forms).

The contract: with no frame argument, ``support`` resolves the locked
v0.9.0 header (``default-v1`` wording) and ``coherence`` resolves the thin
frame (whose ``survey_header`` is byte-identical to the v0.17.4
``COHERENCE_QUESTION_HEADER``), so every platform's MAIN artifact is
byte-identical to its pre-frame output. Only the mapping sidecar gains
provenance keys — deliberately excluded from this comparison.

Regenerate the fixtures ONLY if the pre-frame default surface itself
legitimately changes (which breaks live surveys — think twice).

Regeneration log:
- 2026-07-06 (coherence fixtures only): the coherence-form rationale prompt
  changed from the support wording ("abstained or rated bad" — a
  support-vocabulary leak onto the coherence surface flagged by the survey
  header review) to the coherence wording ("chose Unclear or found the
  position untenable"). Verified diff-confined to that line on all three
  platforms before regenerating. Support fixtures untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infereval.benchmark import Benchmark
from infereval.survey.google_forms_gas import build_gas_script
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.surveymonkey_api import build_surveymonkey_payload

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "survey_preframe"


@pytest.fixture
def golden_benchmark() -> Benchmark:
    """The exact benchmark the fixtures were generated from."""
    return Benchmark.load(FIXTURES / "benchmark.json")


@pytest.mark.parametrize("question_form", ["support", "coherence"])
class TestDefaultPathByteIdentity:
    """No frame flag + thin/default resolution → identical artifact bytes."""

    def test_qualtrics_qsf_bytes_unchanged(
        self, golden_benchmark: Benchmark, question_form: str
    ) -> None:
        qsf, _mapping = build_qsf(golden_benchmark, question_form=question_form)
        expected = (FIXTURES / f"qualtrics_{question_form}.qsf.json").read_text(
            encoding="utf-8"
        )
        assert json.dumps(qsf, indent=2) == expected

    def test_google_forms_gas_bytes_unchanged(
        self, golden_benchmark: Benchmark, question_form: str
    ) -> None:
        gas, _mapping = build_gas_script(golden_benchmark, question_form=question_form)
        expected = (FIXTURES / f"google_forms_{question_form}.gs").read_text(
            encoding="utf-8"
        )
        assert gas == expected

    def test_surveymonkey_payload_bytes_unchanged(
        self, golden_benchmark: Benchmark, question_form: str
    ) -> None:
        payload, _mapping = build_surveymonkey_payload(
            golden_benchmark, question_form=question_form
        )
        expected = (FIXTURES / f"surveymonkey_{question_form}.json").read_text(
            encoding="utf-8"
        )
        assert json.dumps(payload, indent=2) == expected
