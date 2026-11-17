"""Every sequent shape ⟨Γ, Δ⟩ renders, decodes and validates as specified.

Restall's bilateral reading makes implication (Γ ⊢ A), incompatibility (Γ ⊢),
disjunctive implication (Γ ⊢ A, B) and assertion/undeniability (⊢ Δ) shapes of
one judgment: is the position [assert Γ : deny Δ] out of bounds? The coherence
question form elicits all of them. These tests pin:

* the empty-premise shape ⟨∅, Δ⟩ renders as a deny-only position (it used to
  render "commits to the following: ; and denies: ...");
* ⟨∅, ∅⟩ is rejected at benchmark validation and before any rendering;
* the support form refuses ⟨∅, Δ⟩ (it is defined for |Γ| ≥ 1, |Δ| = 1);
* framework-default-v1 is byte-identical for every shape it already rendered;
* framework-default-v2 differs from v1 only by not doubling a full stop.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from infereval.benchmark import Benchmark
from infereval.context import make_template_builder
from infereval.endorsement import endorse
from infereval.evaluation import EndorsementConfig, ProviderParams
from infereval.providers.mock import ScriptedProvider
from infereval.survey.render import render_survey_question
from infereval.templates import (
    DefaultTemplate,
    DefaultTemplateV2,
    VerdictRequest,
    resolve_template,
    template_for_id,
)
from infereval.templates_clinical import ClinicalTemplate
from infereval.types import Bearer, Implication, Verdict

EXPR = {"g": "The tile looks red to Mira.", "a": "The tile is red.", "b": "The tile is orange."}


def _endorse(premises, conclusions, response="INCOHERENT", *, question_form="coherence", template=None):
    imp = Implication.of(premises, conclusions, id="it")
    bearers = {b: Bearer(id=b, expression=EXPR[b]) for b in set(premises) | set(conclusions)}
    return endorse(
        imp,
        bearers,
        ScriptedProvider(responses=[response]),
        EndorsementConfig(n_samples=1),
        ProviderParams(),
        premise_builder=make_template_builder(joiner=" and "),
        conclusion_builder=make_template_builder(joiner=" or "),
        question_form=question_form,
        template=template,
    )


def _scaffold(rec) -> str:
    return rec.rendered_user_prompt.split("\n")[0]


class TestShapesUnderV1:
    """framework-default-v1: the four populated shapes render; non-empty Γ is unchanged."""

    def test_implication_unchanged(self) -> None:
        assert _scaffold(_endorse(["g"], ["a"])) == (
            "Consider a position that commits to the following: The tile looks red to Mira.; "
            "and denies: The tile is red.."
        )

    def test_incompatibility_unchanged(self) -> None:
        assert _scaffold(_endorse(["g"], [])) == (
            "Consider a position that commits to the following: The tile looks red to Mira.."
        )

    def test_disjunctive_unchanged(self) -> None:
        assert _scaffold(_endorse(["g"], ["a", "b"])) == (
            "Consider a position that commits to the following: The tile looks red to Mira.; "
            "and denies every one of: The tile is red.; The tile is orange.."
        )

    def test_empty_premises_render_as_deny_only(self) -> None:
        rec = _endorse([], ["a"])
        assert _scaffold(rec) == "Consider a position that commits to nothing and denies: The tile is red.."
        assert "commits to the following: ;" not in rec.rendered_user_prompt

    def test_empty_premises_disjunctive(self) -> None:
        assert _scaffold(_endorse([], ["a", "b"])) == (
            "Consider a position that commits to nothing and denies every one of: "
            "The tile is red.; The tile is orange.."
        )

    @pytest.mark.parametrize("premises,conclusions", [(["g"], ["a"]), (["g"], []), ([], ["a"]), ([], ["a", "b"])])
    def test_polarity_is_uniform(self, premises, conclusions) -> None:
        assert _endorse(premises, conclusions, "INCOHERENT").verdict == Verdict.GOOD
        assert _endorse(premises, conclusions, "COHERENT").verdict == Verdict.BAD


class TestV2:
    """framework-default-v2: no doubled full stop; otherwise the same text as v1."""

    @pytest.mark.parametrize("premises,conclusions", [(["g"], ["a"]), (["g"], []), (["g"], ["a", "b"]), ([], ["a"]), ([], ["a", "b"])])
    def test_no_double_full_stop_and_same_words(self, premises, conclusions) -> None:
        v1 = _scaffold(_endorse(premises, conclusions, template=DefaultTemplate()))
        v2 = _scaffold(_endorse(premises, conclusions, template=DefaultTemplateV2()))
        assert ".." not in v2
        assert v2 == v1[:-1]  # v1 ends "..", v2 ends "."

    def test_v2_closes_text_without_terminal_punctuation(self) -> None:
        req = VerdictRequest(arity=1, gamma_ctx="a is a bird", delta_ctx=("a can fly",))
        assert DefaultTemplateV2().render(req) == (
            "Consider a position that commits to the following: a is a bird; and denies: a can fly."
        )
        assert DefaultTemplate().render(req) == DefaultTemplateV2().render(req)

    def test_v2_is_catalogued_and_v1_stays_default(self) -> None:
        assert template_for_id("framework-default-v2").id == "framework-default-v2"
        assert resolve_template().id == "framework-default-v1"


class TestGuards:
    def test_empty_empty_rejected_before_rendering(self) -> None:
        with pytest.raises(ValueError, match="excluded by stipulation"):
            _endorse([], [])

    def test_templates_refuse_empty_empty(self) -> None:
        req = VerdictRequest(arity=0, gamma_ctx="", delta_ctx=(), antecedent_empty=True)
        for tmpl in (DefaultTemplate(), DefaultTemplateV2()):
            with pytest.raises(ValueError, match="⟨∅, ∅⟩"):
                tmpl.render(req)

    def test_support_refuses_empty_premises(self) -> None:
        with pytest.raises(ValueError, match="at least one premise"):
            _endorse([], ["a"], "GOOD", question_form="support")

    def test_clinical_template_refuses_empty_premises(self) -> None:
        req = VerdictRequest(arity=1, gamma_ctx="", delta_ctx=("x",), antecedent_empty=True)
        with pytest.raises(ValueError, match="no rendering for items without premises"):
            ClinicalTemplate().render(req)


def _bench(items: list[dict]) -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "shapes",
            "bearers": {b: {"expression": e} for b, e in EXPR.items()},
            "analysts": [{"id": "a1"}],
            "items": items,
        }
    )


class TestSchema:
    def test_empty_empty_item_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no premises and no conclusions"):
            _bench([{"id": "x", "premises": [], "conclusions": [], "analyst_verdicts": ["good"]}])

    @pytest.mark.parametrize("premises,conclusions", [(["g"], []), ([], ["a"]), ([], ["a", "b"])])
    def test_one_empty_side_validates(self, premises, conclusions) -> None:
        b = _bench([{"id": "x", "premises": premises, "conclusions": conclusions, "analyst_verdicts": ["good"]}])
        assert b.items[0].premises == sorted(premises)


class TestSurveyMatchesModel:
    def test_coherence_survey_body_for_empty_premises(self) -> None:
        b = _bench([{"id": "x", "premises": [], "conclusions": ["a"], "analyst_verdicts": ["good"]}])
        q = render_survey_question(b, b.items[0], question_form="coherence")
        assert "commits to nothing and denies: The tile is red." in q.body
        assert "commits to the following: ;" not in q.body

    def test_support_survey_refuses_empty_premises(self) -> None:
        b = _bench([{"id": "x", "premises": [], "conclusions": ["a"], "analyst_verdicts": ["good"]}])
        with pytest.raises(ValueError, match="at least one premise"):
            render_survey_question(b, b.items[0], question_form="support")
