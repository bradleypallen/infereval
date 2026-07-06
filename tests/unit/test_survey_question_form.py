"""Tests for question_form-aware survey rendering + decode (v0.17.4),
plus the survey frame surface (``survey_header`` / ``frame_id``)."""

from __future__ import annotations

import logging

import pytest

from infereval.benchmark import Benchmark
from infereval.prompts import VerificationPrompt
from infereval.survey.render import (
    COHERENCE_QUESTION_HEADER,
    COHERENCE_VERDICT_CHOICES,
    DEFAULT_QUESTION_HEADER,
    DEFAULT_VERDICT_CHOICES,
    render_survey_question,
    verdict_from_choice_text,
)
from infereval.templates import (
    DEFEASIBLE_COHERENCE_FRAME,
    THIN_COHERENCE_FRAME,
    UNDERDET_COHERENCE_FRAME,
    CoherenceFrame,
)
from infereval.types import Verdict

BUILTIN_FRAMES = (THIN_COHERENCE_FRAME, DEFEASIBLE_COHERENCE_FRAME, UNDERDET_COHERENCE_FRAME)


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


# ---- Survey frames (the norm-statement axis' human-facing surface) ---------


def _frame_bench(**updates: object) -> Benchmark:
    """Benchmark with an id no test binds in the template/frame registries.

    ``test_uses_bound_domain_template`` above registers a domain template
    under the ``"survey-qf"`` id, so the frame tests use their own id to keep
    resolution on the default path unless a test binds something explicitly.
    ``updates`` are applied via ``model_copy`` (e.g. ``coherence_frame_id=...``,
    ``verification_prompt=...``).
    """
    bench = Benchmark.model_validate(
        {
            "id": "survey-frames",
            "bearers": {
                "p": {"expression": "the patient has acute dyspnea"},
                "q": {"expression": "the patient has cardiogenic pulmonary edema"},
            },
            "analysts": [{"id": "a1"}],
            "items": [
                {"id": "one", "premises": ["p"], "conclusions": ["q"], "analyst_verdicts": ["good"]},
            ],
        }
    )
    return bench.model_copy(update=dict(updates)) if updates else bench


class TestFrameBackCompat:
    """With nothing bound anywhere, headers are byte-identical to pre-frame output."""

    def test_default_support_header_byte_identical(self) -> None:
        b = _frame_bench()
        sq = render_survey_question(b, b.items[0], question_form="support")
        assert sq.header == DEFAULT_QUESTION_HEADER
        assert sq.frame_id == "default-v1"
        assert sq.choices == DEFAULT_VERDICT_CHOICES

    def test_default_coherence_header_byte_identical(self) -> None:
        b = _frame_bench()
        sq = render_survey_question(b, b.items[0], question_form="coherence")
        assert sq.header == COHERENCE_QUESTION_HEADER
        assert sq.frame_id == "thin-v1"
        assert sq.choices == COHERENCE_VERDICT_CHOICES

    def test_coherence_header_aliases_thin_frame(self) -> None:
        # Alias identity, not mere equality: the canonical text lives on the
        # thin frame; the module constant is the same object.
        assert COHERENCE_QUESTION_HEADER is THIN_COHERENCE_FRAME.survey_header


class TestFrameSurface:
    """Each built-in frame renders its own header; everything else is frame-fixed."""

    @pytest.mark.parametrize("frame", BUILTIN_FRAMES, ids=lambda f: f.id)
    def test_builtin_frame_renders_own_survey_header(self, frame: CoherenceFrame) -> None:
        b = _frame_bench()
        sq = render_survey_question(
            b, b.items[0], question_form="coherence", coherence_frame=frame
        )
        assert sq.header == frame.survey_header
        assert sq.frame_id == frame.id

    def test_choices_identical_across_all_frames(self) -> None:
        # The survey side of the polarity firewall: a frame changes ONLY the
        # header. Choice labels (and hence the importer decode keyed on their
        # first word) are library-owned at every frame.
        b = _frame_bench()
        rendered = [
            render_survey_question(
                b, b.items[0], question_form="coherence", coherence_frame=frame
            )
            for frame in BUILTIN_FRAMES
        ]
        assert all(sq.choices == COHERENCE_VERDICT_CHOICES for sq in rendered)
        # Bodies are frame-independent too — the frame is not a rendering axis.
        assert len({sq.body for sq in rendered}) == 1


class TestFrameFailLoud:
    """A frame without a declared survey surface refuses to render a survey."""

    def test_headerless_coherence_frame_raises(self) -> None:
        bare = CoherenceFrame(id="bare-v1", system="judge coherence")
        assert bare.survey_header is None
        b = _frame_bench()
        with pytest.raises(ValueError, match=r"bare-v1.*survey_header"):
            render_survey_question(
                b, b.items[0], question_form="coherence", coherence_frame=bare
            )

    def test_explicit_headerless_verification_prompt_raises(self) -> None:
        vp = VerificationPrompt(
            id="situational-v9",
            system="judge support",
            user_template="Premises: {premise_context}\nConclusion: {conclusion_context}",
        )
        assert vp.survey_header is None
        b = _frame_bench()
        with pytest.raises(ValueError, match=r"situational-v9.*survey_header"):
            render_survey_question(
                b, b.items[0], question_form="support", verification_prompt=vp
            )

    def test_explicit_verification_prompt_with_header_is_used(self) -> None:
        vp = VerificationPrompt(
            id="situational-v9",
            system="judge support",
            user_template="Premises: {premise_context}\nConclusion: {conclusion_context}",
            survey_header="In the situation described, does the conclusion follow?",
        )
        b = _frame_bench()
        sq = render_survey_question(
            b, b.items[0], question_form="support", verification_prompt=vp
        )
        assert sq.header == "In the situation described, does the conclusion follow?"
        assert sq.frame_id == "situational-v9"
        # Choice labels stay library-owned under a custom support frame too.
        assert sq.choices == DEFAULT_VERDICT_CHOICES


class TestSupportFallback:
    """Benchmark-bound headerless prompts fall back to default-v1 wording, loudly."""

    def test_benchmark_bound_headerless_prompt_falls_back_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # A benchmark-declared verification_prompt override never carries a
        # survey_header (the JSON schema has no such field), so the render
        # preserves pre-frame behavior — the locked v0.9.0 header — while
        # logging the model/survey frame misalignment for post-run analysis.
        from infereval.benchmark import VerificationPromptOverride

        b = _frame_bench(
            verification_prompt=VerificationPromptOverride(
                id="situational-v2",
                template="Premises: {premise_context}\nConclusion: {conclusion_context}",
            )
        )
        with caplog.at_level(logging.WARNING, logger="infereval.survey.render"):
            sq = render_survey_question(b, b.items[0], question_form="support")
        assert sq.header == DEFAULT_QUESTION_HEADER
        # frame_id records what was actually shown, not the benchmark binding.
        assert sq.frame_id == "default-v1"
        fallback_records = [
            r for r in caplog.records if "survey.frame.fallback" in r.getMessage()
        ]
        assert len(fallback_records) == 1
        assert fallback_records[0].levelno == logging.WARNING
        # The log line names both the benchmark and the bound prompt id.
        assert "situational-v2" in fallback_records[0].getMessage()
        assert "survey-frames" in fallback_records[0].getMessage()

    def test_default_prompt_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        b = _frame_bench()
        with caplog.at_level(logging.WARNING, logger="infereval.survey.render"):
            render_survey_question(b, b.items[0], question_form="support")
        assert "survey.frame.fallback" not in caplog.text


class TestBenchmarkFrameBinding:
    def test_benchmark_coherence_frame_id_is_honored(self) -> None:
        b = _frame_bench(coherence_frame_id=DEFEASIBLE_COHERENCE_FRAME.id)
        sq = render_survey_question(b, b.items[0], question_form="coherence")
        assert sq.header == DEFEASIBLE_COHERENCE_FRAME.survey_header
        assert sq.frame_id == DEFEASIBLE_COHERENCE_FRAME.id
        # Firewall holds under a benchmark-bound anchored frame as well.
        assert sq.choices == COHERENCE_VERDICT_CHOICES


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
