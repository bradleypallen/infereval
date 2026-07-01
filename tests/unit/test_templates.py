"""Tests for the template registry + coherence contract (:mod:`infereval.templates`)."""

from __future__ import annotations

import re

import pytest

from infereval.templates import (
    DefaultTemplate,
    VerdictRequest,
    arity_of,
    coherence_decode,
    coherence_prompt,
    register_template,
    resolve_template,
)
from infereval.types import Verdict

_PATTERN = re.compile(r"\b(INCOHERENT|COHERENT|UNCLEAR)\b", re.IGNORECASE)


def _req(arity, delta=()):
    return VerdictRequest(arity=arity, gamma_ctx="the premises", delta_ctx=tuple(delta))


class TestArity:
    def test_arity_of(self) -> None:
        assert arity_of([]) == 0
        assert arity_of(["x"]) == 1
        assert arity_of(["x", "y"]) == "many"


class TestDefaultTemplate:
    def test_renders_each_arity(self) -> None:
        t = DefaultTemplate()
        assert "denies" not in t.render(_req(0))  # arity 0 commits only
        assert "and denies: the conclusion" in t.render(_req(1, ["the conclusion"]))
        many = t.render(_req("many", ["A", "B"]))
        assert "denies every one of: A; B" in many

    def test_template_sees_no_bearer_ids(self) -> None:
        # The VerdictRequest carries only rendered contexts — the invariant that
        # a template cannot re-smuggle the domain into the verdict layer.
        assert not hasattr(VerdictRequest(arity=1, gamma_ctx="g", delta_ctx=("d",)), "premises")


class TestPolarityFirewall:
    @pytest.mark.parametrize("arity,delta", [(0, ()), (1, ("d",))])
    def test_incoherent_is_good_at_every_arity(self, arity, delta) -> None:
        req = _req(arity, delta)
        assert coherence_decode("INCOHERENT", _PATTERN, req) == (Verdict.GOOD, "ok")
        assert coherence_decode("COHERENT", _PATTERN, req) == (Verdict.BAD, "ok")
        assert coherence_decode("UNCLEAR", _PATTERN, req) == (Verdict.ABSTAIN, "ok")

    def test_incoherent_not_misparsed_as_coherent(self) -> None:
        # "INCOHERENT" contains "COHERENT"; the decode must not read it as good=bad.
        assert coherence_decode("the position is INCOHERENT.", _PATTERN, _req(1, ("d",))) == (
            Verdict.GOOD,
            "ok",
        )

    def test_unparseable_is_abstain(self) -> None:
        assert coherence_decode("no verdict token here", _PATTERN, _req(1, ("d",))) == (
            Verdict.ABSTAIN,
            "unparseable",
        )


class TestCoherencePrompt:
    def test_frames_scaffolding_with_question(self) -> None:
        rp = coherence_prompt(_req(1, ["the conclusion"]), DefaultTemplate())
        assert "Is this position coherent?" in rp.user
        assert "the premises" in rp.user
        assert rp.labels == ("INCOHERENT", "COHERENT", "UNCLEAR")


class TestRegistry:
    def test_default_and_binding(self) -> None:
        assert resolve_template().id == "framework-default-v1"
        assert resolve_template("no-such-domain").id == "framework-default-v1"

        class _Clinical:
            id = "clinical-v1"

            def render(self, req: VerdictRequest) -> str:
                return "could there be such a case?"

        register_template("my-domain", _Clinical())
        assert resolve_template("my-domain").id == "clinical-v1"
