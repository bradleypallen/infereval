"""Tests for question_form-aware survey rendering + decode (v0.17.4)."""

from __future__ import annotations

import pytest

from infereval.benchmark import Benchmark
from infereval.survey.render import (
    render_survey_question,
    verdict_from_choice_text,
)
from infereval.types import Verdict


def _bench() -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "survey-qf",
            "bearers": {
                "p": {"expression": "the patient has acute dyspnea"},
                "q": {"expression": "the patient has cardiogenic pulmonary edema"},
                "r": {"expression": "the patient has ARDS"},
            },
            "analysts": [{"id": "a1"}],
            "items": [
                {"id": "one", "premises": ["p"], "conclusions": ["q"], "analyst_verdicts": ["good"]},
                {"id": "excl", "premises": ["p", "q"], "conclusions": [], "analyst_verdicts": ["good"]},
                {"id": "disj", "premises": ["p"], "conclusions": ["q", "r"], "analyst_verdicts": ["good"]},
            ],
        }
    )


class TestSupportRendering:
    def test_support_single_succedent(self) -> None:
        b = _bench()
        sq = render_survey_question(b, b.items[0], question_form="support")
        assert sq.question_form == "support"
        assert "good diagnostic inference" in sq.header
        assert "Premises:" in sq.body and "Conclusion:" in sq.body
        assert sq.choices[0].startswith("Good")

    def test_support_raises_on_non_singleton(self) -> None:
        b = _bench()
        with pytest.raises(ValueError, match="single-succedent"):
            render_survey_question(b, b.items[1], question_form="support")  # |Δ|=0


class TestCoherenceRendering:
    def test_coherence_single(self) -> None:
        b = _bench()
        sq = render_survey_question(b, b.items[0], question_form="coherence")
        assert sq.question_form == "coherence"
        assert "without conflict" in sq.header  # plainly-worded coherence question
        assert "commits to the following" in sq.body  # default template scaffolding
        assert sq.choices[1].startswith("Incoherent")

    def test_coherence_renders_all_arities(self) -> None:
        b = _bench()
        for item in b.items:  # |Δ| = 1, 0, 2
            sq = render_survey_question(b, item, question_form="coherence")
            assert sq.body  # non-empty, no raise
        # Arity-0 (incompatibility) commits only, denies nothing.
        excl = render_survey_question(b, b.items[1], question_form="coherence")
        assert "denies" not in excl.body
        disj = render_survey_question(b, b.items[2], question_form="coherence")
        assert "denies every one of" in disj.body

    def test_uses_bound_domain_template(self) -> None:
        from infereval.templates import register_template

        class _Clinical:
            id = "clin-survey-v1"

            def render(self, req) -> str:
                return "Could there be such a patient?"

        register_template("survey-qf", _Clinical())
        sq = render_survey_question(_bench(), _bench().items[0], question_form="coherence")
        assert sq.body == "Could there be such a patient?"


class TestDecodePolarity:
    def test_support_decode(self) -> None:
        assert verdict_from_choice_text("Good — follows", question_form="support") == Verdict.GOOD
        assert verdict_from_choice_text("Bad — does not", question_form="support") == Verdict.BAD
        assert verdict_from_choice_text("Abstain — n/a", question_form="support") == Verdict.ABSTAIN

    def test_coherence_decode_inverts(self) -> None:
        # The firewall: incoherent → good, coherent → bad.
        assert verdict_from_choice_text("Incoherent — untenable", question_form="coherence") == Verdict.GOOD
        assert verdict_from_choice_text("Coherent — holds", question_form="coherence") == Verdict.BAD
        assert verdict_from_choice_text("Unclear — cannot judge", question_form="coherence") == Verdict.ABSTAIN

    def test_unknown_choice_raises(self) -> None:
        with pytest.raises(ValueError, match="unrecognised"):
            verdict_from_choice_text("Maybe", question_form="support")

    def test_unknown_question_form_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown question_form"):
            verdict_from_choice_text("Good", question_form="nope")
