"""Tests for the question_form switch in endorse() (brief §3.1, §10.1)."""

from __future__ import annotations

import pytest

from infereval.context import make_template_builder
from infereval.endorsement import EndorsementRecord, endorse
from infereval.evaluation import EndorsementConfig, ProviderParams
from infereval.providers.mock import ScriptedProvider
from infereval.types import Bearer, Implication, Verdict


def _endorse(
    premises: list[str],
    conclusions: list[str],
    responses: list[str],
    *,
    question_form: str = "support",
) -> EndorsementRecord:
    imp = Implication.of(premises, conclusions, id="it")
    ids = set(premises) | set(conclusions)
    bearers = {b: Bearer(id=b, expression=f"expr {b}") for b in ids}
    return endorse(
        imp,
        bearers,
        ScriptedProvider(responses=responses),
        EndorsementConfig(n_samples=1),
        ProviderParams(),
        premise_builder=make_template_builder(joiner=" and "),
        conclusion_builder=make_template_builder(joiner=" or "),
        question_form=question_form,
    )


class TestSupportBackCompat:
    def test_support_prompt_is_the_legacy_surface(self) -> None:
        rec = _endorse(["a"], ["b"], ["GOOD"], question_form="support")
        # Byte-for-byte the pre-generalization user prompt.
        assert rec.rendered_user_prompt == "Premises: expr a\nConclusion: expr b\nVerdict:"
        assert rec.verdict == Verdict.GOOD

    def test_support_verdict_identity(self) -> None:
        assert _endorse(["a"], ["b"], ["BAD"], question_form="support").verdict == Verdict.BAD


class TestSupportRaisesOnNonSingleton:
    def test_raises_on_empty_succedent(self) -> None:
        with pytest.raises(ValueError, match="single-succedent"):
            _endorse(["a"], [], ["GOOD"], question_form="support")

    def test_raises_on_disjunctive_succedent(self) -> None:
        with pytest.raises(ValueError, match="single-succedent"):
            _endorse(["a"], ["b", "c"], ["GOOD"], question_form="support")


class TestCoherenceAllArities:
    def test_coherence_single_succedent(self) -> None:
        rec = _endorse(["a"], ["b"], ["INCOHERENT"], question_form="coherence")
        assert "Is this position coherent?" in rec.rendered_user_prompt
        assert rec.verdict == Verdict.GOOD  # incoherent → the inference holds

    def test_coherence_empty_succedent_incompatibility(self) -> None:
        # ⟨{a, b}, ∅⟩: INCOHERENT means "a and b cannot both hold" → good.
        rec = _endorse(["a", "b"], [], ["INCOHERENT"], question_form="coherence")
        assert rec.verdict == Verdict.GOOD
        rec2 = _endorse(["a", "b"], [], ["COHERENT"], question_form="coherence")
        assert rec2.verdict == Verdict.BAD

    def test_coherence_disjunctive_succedent(self) -> None:
        rec = _endorse(["a"], ["b", "c"], ["COHERENT"], question_form="coherence")
        assert "denies every one of" in rec.rendered_user_prompt
        assert rec.verdict == Verdict.BAD


class TestWorkedExamples:
    """One worked (question_form, rendering) example per cell (tightening #3)."""

    def test_support_plain_vs_coherence_plain_differ(self) -> None:
        support = _endorse(["a"], ["b"], ["GOOD"], question_form="support")
        coherence = _endorse(["a"], ["b"], ["INCOHERENT"], question_form="coherence")
        # Same |Δ|=1 content, genuinely different question posed → different prompt.
        assert support.rendered_user_prompt != coherence.rendered_user_prompt
        assert "Conclusion:" in support.rendered_user_prompt
        assert "commits to the following" in coherence.rendered_user_prompt
