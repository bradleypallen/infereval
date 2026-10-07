"""Tests for ``infereval.prompts``: VerificationPrompt, parse_verdict, defaults."""

from __future__ import annotations

import re

from infereval.benchmark import VerificationPromptOverride
from infereval.prompts import (
    DEFAULT_PARSE_REGEX,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_TEMPLATE,
    DEFAULT_VERIFICATION_PROMPT,
    DEFAULT_VERIFICATION_PROMPT_ID,
    VerificationPrompt,
    parse_verdict,
    resolve_verification_prompt,
)
from infereval.types import Verdict

# ---- Defaults --------------------------------------------------------------


class TestDefaults:
    def test_id_is_default_v1(self) -> None:
        assert DEFAULT_VERIFICATION_PROMPT_ID == "default-v1"
        assert DEFAULT_VERIFICATION_PROMPT.id == "default-v1"

    def test_system_mentions_three_verdicts(self) -> None:
        # Quick sanity check on the locked prompt wording: GOOD / BAD / ABSTAIN
        # all appear in the system message so the model knows the vocabulary.
        for token in ("GOOD", "BAD", "ABSTAIN"):
            assert token in DEFAULT_SYSTEM_PROMPT

    def test_user_template_placeholders(self) -> None:
        assert "{premise_context}" in DEFAULT_USER_TEMPLATE
        assert "{conclusion_context}" in DEFAULT_USER_TEMPLATE

    def test_parse_regex_matches_all_verdicts(self) -> None:
        rx = re.compile(DEFAULT_PARSE_REGEX, re.IGNORECASE)
        for token in ("GOOD", "BAD", "ABSTAIN", "good", "bad", "abstain"):
            assert rx.search(token) is not None


# ---- build_user ------------------------------------------------------------


class TestBuildUser:
    def test_substitutes_both_contexts(self) -> None:
        text = DEFAULT_VERIFICATION_PROMPT.build_user(
            "a is a stop sign and it is nighttime", "a is red"
        )
        assert "a is a stop sign and it is nighttime" in text
        assert "a is red" in text
        assert text.endswith("Verdict:")


# ---- parse_verdict ---------------------------------------------------------


class TestParseVerdict:
    def test_good(self) -> None:
        assert parse_verdict("GOOD") == (Verdict.GOOD, "ok")

    def test_bad(self) -> None:
        assert parse_verdict("BAD") == (Verdict.BAD, "ok")

    def test_abstain(self) -> None:
        assert parse_verdict("ABSTAIN") == (Verdict.ABSTAIN, "ok")

    def test_lowercase(self) -> None:
        assert parse_verdict("good") == (Verdict.GOOD, "ok")
        assert parse_verdict("bad") == (Verdict.BAD, "ok")
        assert parse_verdict("abstain") == (Verdict.ABSTAIN, "ok")

    def test_with_surrounding_text(self) -> None:
        # First match wins
        assert parse_verdict("GOOD. The conclusion follows from the premises.") == (
            Verdict.GOOD,
            "ok",
        )
        assert parse_verdict("After reflection, BAD") == (Verdict.BAD, "ok")

    def test_first_match_wins_when_multiple_present(self) -> None:
        # Pathological case: model says GOOD then BAD. We take the first.
        assert parse_verdict("GOOD then BAD")[0] == Verdict.GOOD

    def test_explicit_verdict_marker_overrides_first_match(self) -> None:
        # Observed in claude-haiku-4.5 stop-sign captures: provisional token,
        # reasoning, then a committed "Verdict: GOOD".
        text = (
            "BAD\n\nStop signs can be other colors. Let me reconsider: under "
            "default conditions stop signs are red.\n\nVerdict: GOOD"
        )
        assert parse_verdict(text) == (Verdict.GOOD, "ok")

    def test_last_marked_verdict_wins(self) -> None:
        text = "Verdict: GOOD\nOn reflection, no.\nVerdict: **BAD**"
        assert parse_verdict(text)[0] == Verdict.BAD

    def test_marker_matching_first_token_is_unchanged(self) -> None:
        assert parse_verdict("Verdict: BAD (painted blue defeats it)")[0] == Verdict.BAD

    def test_unmarked_later_token_does_not_override(self) -> None:
        # Without a marker the first-match rule still holds.
        assert parse_verdict("BAD. Some would say GOOD, but no.")[0] == Verdict.BAD

    def test_bare_token_on_final_line_overrides_first_match(self) -> None:
        text = (
            "BAD\n\nThe premise does not guarantee this.\n\nActually, reconsidering: "
            "a stop sign is ordinarily red.\n\nGOOD"
        )
        assert parse_verdict(text) == (Verdict.GOOD, "ok")

    def test_bare_token_on_final_line_with_emphasis(self) -> None:
        assert parse_verdict("BAD\n\nOn reflection...\n\n**GOOD**.")[0] == Verdict.GOOD

    def test_single_line_response_is_first_match(self) -> None:
        # A one-line response has no "final line" distinct from the whole.
        assert parse_verdict("GOOD")[0] == Verdict.GOOD
        assert parse_verdict("GOOD then BAD")[0] == Verdict.GOOD

    def test_final_line_with_prose_is_not_committed(self) -> None:
        assert parse_verdict("BAD\n\nsome would still call it GOOD")[0] == Verdict.BAD

    def test_marker_rule_applies_to_custom_pattern(self) -> None:
        rx = re.compile(r"\[(GOOD|BAD)\]", re.IGNORECASE)
        assert parse_verdict("[BAD] ... Verdict: [GOOD]", rx)[0] == Verdict.GOOD

    def test_unparseable_no_match(self) -> None:
        assert parse_verdict("Hmm, I'm not sure.") == (Verdict.ABSTAIN, "unparseable")

    def test_unparseable_empty(self) -> None:
        assert parse_verdict("") == (Verdict.ABSTAIN, "unparseable")

    def test_word_boundary_required(self) -> None:
        # "goodness" should not match "GOOD" because of the word boundary
        v, status = parse_verdict("goodness")
        assert v == Verdict.ABSTAIN
        assert status == "unparseable"

    def test_custom_pattern_passed_through(self) -> None:
        rx = re.compile(r"\[(GOOD|BAD)\]")
        v, status = parse_verdict("verdict: [GOOD]", pattern=rx)
        assert v == Verdict.GOOD
        assert status == "ok"


# ---- resolve_verification_prompt -------------------------------------------


class TestResolveVerificationPrompt:
    def test_no_override_returns_default(self) -> None:
        assert resolve_verification_prompt(None) is DEFAULT_VERIFICATION_PROMPT

    def test_override_replaces_template(self) -> None:
        override = VerificationPromptOverride(
            template="P: {premise_context} -> {conclusion_context}? Reply:",
        )
        prompt = resolve_verification_prompt(override)
        assert prompt.user_template == override.template
        # System defaults to DEFAULT_SYSTEM_PROMPT when the override doesn't supply one.
        assert prompt.system == DEFAULT_SYSTEM_PROMPT
        assert prompt.parse_regex == DEFAULT_PARSE_REGEX

    def test_override_with_custom_regex(self) -> None:
        override = VerificationPromptOverride(
            template="{premise_context} ?-> {conclusion_context}",
            parse_regex=r"\[(GOOD|BAD|ABSTAIN)\]",
        )
        prompt = resolve_verification_prompt(override)
        assert prompt.parse_regex == r"\[(GOOD|BAD|ABSTAIN)\]"

    def test_override_with_custom_system(self) -> None:
        override = VerificationPromptOverride(
            template="Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
            system="You are a strict deductive reasoner. Reply GOOD only if the inference is valid.",
        )
        prompt = resolve_verification_prompt(override)
        assert prompt.system == (
            "You are a strict deductive reasoner. "
            "Reply GOOD only if the inference is valid."
        )
        # User template still substituted.
        assert prompt.user_template == override.template

    def test_override_with_custom_id(self) -> None:
        override = VerificationPromptOverride(
            template="{premise_context} / {conclusion_context}",
            id="my-defeasible-v1",
        )
        prompt = resolve_verification_prompt(override)
        assert prompt.id == "my-defeasible-v1"

    def test_override_id_falls_back_to_caller_supplied_default(self) -> None:
        override = VerificationPromptOverride(
            template="{premise_context} / {conclusion_context}",
        )
        prompt = resolve_verification_prompt(override, override_id="explicit-fallback-id")
        assert prompt.id == "explicit-fallback-id"

    def test_override_all_fields_at_once(self) -> None:
        override = VerificationPromptOverride(
            template="P: {premise_context}\nC: {conclusion_context}\n=>",
            system="You evaluate strict deductive entailment.",
            parse_regex=r"\b(YES|NO|UNSURE)\b",
            id="strict-deductive-yes-no-v1",
        )
        prompt = resolve_verification_prompt(override)
        assert prompt.id == "strict-deductive-yes-no-v1"
        assert prompt.system == "You evaluate strict deductive entailment."
        assert prompt.user_template == "P: {premise_context}\nC: {conclusion_context}\n=>"
        assert prompt.parse_regex == r"\b(YES|NO|UNSURE)\b"


# ---- VerificationPrompt structure ------------------------------------------


class TestVerificationPrompt:
    def test_compile_parser_is_case_insensitive(self) -> None:
        p = VerificationPrompt(id="x", system="", user_template="", parse_regex=r"(GOOD)")
        rx = p.compile_parser()
        assert rx.search("good") is not None
        assert rx.search("GOOD") is not None
