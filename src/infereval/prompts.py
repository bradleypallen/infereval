"""Verification prompts and verdict parsing.

The framework's default verification prompt is identified by
``default-v1``. Benchmarks may override it via the ``verification_prompt``
field in their JSON schema; this module provides the type plus the
default template and parser.

The default template follows the methodology of Allen et al. (2025, NeSy
proceedings) -- repeated sampling of a verification prompt, parse the
single-token verdict, abstain when unparseable -- without quoting that
work's literal wording. The token vocabulary is ``GOOD``, ``BAD``,
``ABSTAIN`` so the parser regex is unambiguous and unambiguously distinct
from English prose continuations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .benchmark import VerificationPromptOverride
from .types import ParseStatus, Verdict

DEFAULT_VERIFICATION_PROMPT_ID = "default-v1"

DEFAULT_SYSTEM_PROMPT = (
    "You are evaluating whether an inference from premises to a conclusion is good, "
    "bad, or whether you should abstain.\n\n"
    "Answer with exactly one of: GOOD, BAD, ABSTAIN. No other text.\n\n"
    "GOOD means the conclusion follows from the premises in everyday reasoning.\n"
    "BAD means the premises do not support the conclusion.\n"
    "ABSTAIN means the question is ill-formed, ambiguous, or you cannot judge."
)

DEFAULT_USER_TEMPLATE = (
    "Premises: {premise_context}\n"
    "Conclusion: {conclusion_context}\n"
    "Verdict:"
)

DEFAULT_PARSE_REGEX = r"\b(GOOD|BAD|ABSTAIN)\b"


@dataclass(frozen=True)
class VerificationPrompt:
    """A verification prompt template.

    Attributes
    ----------
    id
        Stable identifier recorded in evaluation JSON
        (``endorsement_config.verification_prompt_id``).
    system
        System message sent to the provider. May be empty.
    user_template
        Format string with ``{premise_context}`` and ``{conclusion_context}``
        placeholders, used to build each per-sample user prompt.
    parse_regex
        Regex applied (case-insensitively) to the model's response. The
        first match's group 1 is uppercased and interpreted as a
        :class:`Verdict` value (``GOOD`` / ``BAD`` / ``ABSTAIN``).
    survey_header
        Optional human-facing surface of this prompt's frame: the survey
        instruction text stating the same assessment norms in respondent
        voice (the support-form analogue of
        :attr:`infereval.templates.CoherenceFrame.survey_header`). It
        changes only the header — choice labels and importer decode stay
        library-controlled. ``None`` means no survey surface is declared;
        the survey renderer falls back to the locked v0.9.0 header for
        ``default-v1`` only and fails loudly for any other prompt, so a
        non-default frame can never silently elicit humans under the
        default's wording.
    """

    id: str
    system: str
    user_template: str
    parse_regex: str = DEFAULT_PARSE_REGEX
    survey_header: str | None = None

    def build_user(self, premise_context: str, conclusion_context: str) -> str:
        """Return the per-sample user prompt with both contexts substituted in."""
        return self.user_template.format(
            premise_context=premise_context,
            conclusion_context=conclusion_context,
        )

    def compile_parser(self) -> re.Pattern[str]:
        """Compile :attr:`parse_regex` as a case-insensitive pattern."""
        return re.compile(self.parse_regex, re.IGNORECASE)


DEFAULT_VERIFICATION_PROMPT = VerificationPrompt(
    id=DEFAULT_VERIFICATION_PROMPT_ID,
    system=DEFAULT_SYSTEM_PROMPT,
    user_template=DEFAULT_USER_TEMPLATE,
    parse_regex=DEFAULT_PARSE_REGEX,
)


def resolve_verification_prompt(
    override: VerificationPromptOverride | None,
    *,
    override_id: str = "benchmark-override-v1",
) -> VerificationPrompt:
    """Return the default prompt, or a benchmark-supplied override.

    Each override field that is ``None`` falls back to the framework
    default:

    - :attr:`VerificationPromptOverride.system` ``None`` →
      :data:`DEFAULT_SYSTEM_PROMPT`.
    - :attr:`VerificationPromptOverride.parse_regex` ``None`` →
      :data:`DEFAULT_PARSE_REGEX`.
    - :attr:`VerificationPromptOverride.id` ``None`` → ``override_id``
      (caller-supplied fallback identifier).

    A benchmark JSON can now fully specify a custom verification prompt
    (system + user template + parse regex + identifier) without dropping
    to the Python API.
    """
    if override is None:
        return DEFAULT_VERIFICATION_PROMPT
    return VerificationPrompt(
        id=override.id or override_id,
        system=override.system if override.system is not None else DEFAULT_SYSTEM_PROMPT,
        user_template=override.template,
        parse_regex=override.parse_regex or DEFAULT_PARSE_REGEX,
    )


def parse_verdict(
    text: str,
    pattern: re.Pattern[str] | None = None,
) -> tuple[Verdict, ParseStatus]:
    """Extract a :class:`Verdict` from a raw model response.

    Returns ``(Verdict.ABSTAIN, "unparseable")`` if no token matches; per
    the paper's Definition 2 ("Unparseable responses are mapped to abstain").
    """
    if pattern is None:
        pattern = DEFAULT_VERIFICATION_PROMPT.compile_parser()
    match = pattern.search(text)
    if match is None:
        return Verdict.ABSTAIN, "unparseable"
    token = match.group(1).upper()
    try:
        return Verdict(token.lower()), "ok"
    except ValueError:
        # Regex group didn't match a known verdict; treat as unparseable.
        return Verdict.ABSTAIN, "unparseable"


__all__ = [
    "DEFAULT_PARSE_REGEX",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_USER_TEMPLATE",
    "DEFAULT_VERIFICATION_PROMPT",
    "DEFAULT_VERIFICATION_PROMPT_ID",
    "ParseStatus",
    "VerificationPrompt",
    "parse_verdict",
    "resolve_verification_prompt",
]
