"""Platform-agnostic rendering helpers for survey export / import.

The three per-platform generators (Qualtrics ``.qsf``, Google Forms
``.gs``, SurveyMonkey API) all consume the same rendered question text,
sanitize item ids the same way, and yield ``SurveyRespondent``-shaped
records from CSV imports. This module is the shared surface — keep the
platform-specific quirks out of here.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ..context import strip_tex_math
from ..templates import THIN_COHERENCE_FRAME
from ..types import Verdict

if TYPE_CHECKING:
    from ..benchmark import Benchmark, BenchmarkItem
    from ..prompts import VerificationPrompt
    from ..templates import CoherenceFrame

log = logging.getLogger(__name__)

# The thin frame always declares its survey surface; assert at import time so
# the alias below can never silently become None.
assert THIN_COHERENCE_FRAME.survey_header is not None
_THIN_SURVEY_HEADER: str = THIN_COHERENCE_FRAME.survey_header


# ---- Default question template strings ------------------------------------

#: The fixed header rendered above the premises/conclusion bullet form on
#: every MC question. Wording locked at v0.9.0; future-version override
#: via a ``--template-file`` CLI flag is a v0.9.x follow-up.
DEFAULT_QUESTION_HEADER: str = (
    "Given the following premises, is the conclusion a good "
    "diagnostic inference, a bad one, or are you unable to judge?"
)

#: The default-v1 header is a single question line, so under the
#: instructions header mode it serves verbatim as its own per-item stem.
DEFAULT_QUESTION_STEM: str = DEFAULT_QUESTION_HEADER

#: Default MC choice labels rendered in each survey platform. The first
#: word (Good / Bad / Abstain) is the parse key the importer uses to
#: map back to :class:`~infereval.types.Verdict`.
DEFAULT_VERDICT_CHOICES: tuple[str, str, str] = (
    "Good — follows from premises",
    "Bad — does not follow",
    "Abstain — cannot judge",
)

#: Default prompt rendered above the optional per-item rationale field
#: (support form; wording locked at v0.9.0).
DEFAULT_RATIONALE_PROMPT: str = (
    "Optional: briefly explain why you chose that verdict "
    "(especially helpful if you abstained or rated bad)."
)

#: Coherence-form rationale prompt. The support wording leaks support-form
#: vocabulary ("abstained", "bad") onto a surface whose choices are
#: Coherent / Incoherent / Unclear; this variant speaks the coherence
#: labels' language and never mentions the internal good/bad scale.
COHERENCE_RATIONALE_PROMPT: str = (
    "Optional: briefly explain why you chose that verdict (especially "
    "helpful if you chose Unclear or found the position untenable)."
)


def rationale_prompt(question_form: str) -> str:
    """The per-item rationale prompt for ``question_form``."""
    if question_form == "coherence":
        return COHERENCE_RATIONALE_PROMPT
    return DEFAULT_RATIONALE_PROMPT

#: Default prompt for the survey's first (expertise) free-text question.
DEFAULT_EXPERTISE_PROMPT: str = (
    "Briefly describe your clinical or domain expertise relevant to "
    "these inferences — your specialty, years in practice, role, and "
    "any board certifications."
)

#: Coherence question form (v0.17.4). Asked when the benchmark is evaluated under
#: ``question_form="coherence"``, so the human analyst and the model answer the
#: SAME question. Plainly worded — the participant judges coherence directly; the
#: ``incoherent → good`` inversion lives server-side (see
#: :func:`verdict_from_choice_text`). Since the survey frame axis landed, the
#: canonical text lives on the thin frame; this constant aliases it unchanged.
COHERENCE_QUESTION_HEADER: str = _THIN_SURVEY_HEADER

#: Coherence MC choices. First word (Coherent / Incoherent / Unclear) is the parse
#: key the importer maps back to a :class:`~infereval.types.Verdict`.
COHERENCE_VERDICT_CHOICES: tuple[str, str, str] = (
    "Coherent — the position can be held without conflict",
    "Incoherent — the position is untenable",
    "Unclear — cannot judge",
)


# ---- Item-id sanitization (export-tag derivation) ------------------------

_SAFE_TAG_RE = re.compile(r"^[A-Za-z0-9_]{1,80}$")


def sanitize_export_tag(item_id: str) -> tuple[str, bool]:
    """Derive a CSV-column-safe identifier from ``item_id``.

    Returns ``(tag, was_hashed)``. When ``item_id`` matches
    ``^[A-Za-z0-9_]{1,80}$`` (the common case for benchmark item ids
    like ``"item-001"``, ``"pulm_bnp_acute_1"``, etc., once dashes are
    handled — see note), the tag is the item id unchanged and
    ``was_hashed`` is ``False``. Otherwise the tag is
    ``f"item_{sha8(item_id)}"`` and the caller should record the
    mapping in a sidecar ``mapping.json`` for traceability.

    Note: hyphens are NOT in the safe set because Qualtrics
    ``DataExportTag`` values are surfaced as CSV column headers and
    column-header readers in pandas/csv treat hyphens fine but some
    spreadsheet tools mangle them as minus signs in formulas. Using
    underscore-only keeps every downstream tool happy.

    Used by Qualtrics for ``DataExportTag``, and as the parsed-back
    identifier in Google Forms / SurveyMonkey title-prefix encoding.
    """
    if _SAFE_TAG_RE.match(item_id):
        return item_id, False
    digest = hashlib.sha256(item_id.encode("utf-8")).hexdigest()[:8]
    return f"item_{digest}", True


# ---- Implication-text rendering ------------------------------------------


def render_implication_text(benchmark: Benchmark, item: BenchmarkItem) -> str:
    """Render the prose body of a survey question for one benchmark item.

    Looks up each premise/conclusion bearer's English ``expression`` via
    :meth:`Benchmark.bearer`, strips any ``$...$`` TeX delimiters via
    :func:`~infereval.context.strip_tex_math`, and emits the
    fixed premises/conclusion bullet form documented in
    ``docs/surveys.md``.

    The header (``DEFAULT_QUESTION_HEADER``) is *not* included here —
    each platform's generator prepends it according to the platform's
    text/markdown formatting conventions.
    """
    def _bullet_lines(bearer_ids: list[str]) -> list[str]:
        lines: list[str] = []
        for bid in bearer_ids:
            text = strip_tex_math(benchmark.bearer(bid).expression).strip()
            lines.append(f"- {text}")
        return lines

    parts: list[str] = []
    parts.append("Premises:")
    parts.extend(_bullet_lines(list(item.premises)))
    parts.append("")
    parts.append("Conclusion:")
    parts.extend(_bullet_lines(list(item.conclusions)))
    return "\n".join(parts)


# ---- Question-form-aware survey question (v0.17.4) -------------------------


@dataclass(frozen=True, slots=True)
class SurveyQuestion:
    """A rendered survey question: header + body + MC choices, for one item.

    ``question_form`` records which logical question the survey asks so the
    importer applies the matching decode (see :func:`verdict_from_choice_text`).
    Humans and the model must be asked the same ``question_form`` for
    ``κ_C(model vs analyst)`` to compare like with like.
    """

    question_form: str
    header: str
    body: str
    choices: tuple[str, str, str]
    frame_id: str | None = None
    """The frame the header renders (the norm-statement axis): the
    :class:`~infereval.templates.CoherenceFrame` id under ``coherence``, the
    :class:`~infereval.prompts.VerificationPrompt` id under ``support``.
    Recorded so the export sidecar can carry it and the merger can refuse
    mixed-frame compositions — humans and the model must share question form
    AND frame for ``κ_C`` to compare like with like. ``None`` only on
    questions rendered before the frame axis existed."""
    stem: str | None = None
    """The frame's closing question line (its ``survey_stem``), for
    exporters that render the header once as a survey-level instructions
    page and repeat only this line per item. Always a verbatim trailing
    substring of ``header`` for the built-in frames (tested), so the
    instructions mode introduces no wording beyond the frame's reviewed
    surface. ``None`` when the resolved frame declares no stem, in which
    case :meth:`body_with_stem` fails loudly."""

    def full_text(self) -> str:
        """Header + blank line + body — what each platform renders per item."""
        return f"{self.header}\n\n{self.body}"

    def body_with_stem(self) -> str:
        """Body + blank line + the frame's question stem — the per-item
        text under the instructions header mode."""
        if self.stem is None:
            raise ValueError(
                f"frame {self.frame_id!r} declares no survey_stem; the "
                f"instructions header mode cannot render per-item questions "
                f"under it. Declare the header's closing question line as "
                f"survey_stem, or export with header_mode='per-question'."
            )
        return f"{self.body}\n\n{self.stem}"


def render_survey_question(
    benchmark: Benchmark,
    item: BenchmarkItem,
    *,
    question_form: str = "support",
    coherence_frame: CoherenceFrame | None = None,
    verification_prompt: VerificationPrompt | None = None,
) -> SurveyQuestion:
    """Render one item's survey question under ``question_form``.

    ``support`` reproduces the pre-v0.17.4 support surface (single-succedent
    only). ``coherence`` renders the bilateral coherence question through the
    same template registry the model uses, so the human sees the same content
    scaffolding at every arity.

    The header is the frame surface (the norm-statement axis). Resolution
    mirrors the model path: under ``coherence``, an explicit
    ``coherence_frame`` argument, then a programmatic registration, then the
    benchmark's ``coherence_frame_id``, then the thin default; under
    ``support``, an explicit ``verification_prompt``, then the benchmark's
    ``verification_prompt`` binding, then the default prompt. A resolved
    frame without a declared ``survey_header`` raises rather than silently
    eliciting humans under different wording than the recorded frame — the
    only fallback is the locked v0.9.0 support header for ``default-v1``.
    Choice labels and the importer decode are frame-independent at every
    frame (the survey side of the polarity firewall).
    """
    if question_form == "support":
        if len(item.conclusions) != 1:
            raise ValueError(
                f"question_form='support' survey questions are single-succedent "
                f"(|Δ|=1); item {item.id!r} has |Δ|={len(item.conclusions)}. Use "
                f"question_form='coherence'."
            )
        from ..prompts import resolve_verification_prompt

        if verification_prompt is not None:
            # An explicit prompt is an explicit frame choice: it must declare
            # its human-facing wording or the render refuses.
            if verification_prompt.survey_header is None:
                raise ValueError(
                    f"verification prompt {verification_prompt.id!r} declares "
                    f"no survey_header; a survey cannot be rendered under it "
                    f"without one (declaring the human-facing wording is part "
                    f"of the frame's identity)."
                )
            header, frame_id = verification_prompt.survey_header, verification_prompt.id
            stem = verification_prompt.survey_stem
        else:
            vp = resolve_verification_prompt(benchmark.verification_prompt)
            if vp.survey_header is not None:
                header, frame_id = vp.survey_header, vp.id
                stem = vp.survey_stem
            else:
                # Pre-frame behavior, preserved: support surveys always used
                # the locked v0.9.0 header regardless of the benchmark's
                # verification-prompt binding. frame_id records what was
                # actually shown ("default-v1" wording), and the warning makes
                # a model/survey frame misalignment visible instead of hidden.
                header, frame_id = DEFAULT_QUESTION_HEADER, "default-v1"
                stem = DEFAULT_QUESTION_STEM
                if vp.id != "default-v1":
                    log.warning(
                        "survey.frame.fallback benchmark=%s verification_prompt=%s "
                        "declares no survey_header; rendering the default-v1 survey "
                        "header — the model and survey frames differ for this item.",
                        benchmark.id,
                        vp.id,
                    )
        return SurveyQuestion(
            question_form="support",
            header=header,
            body=render_implication_text(benchmark, item),
            choices=DEFAULT_VERDICT_CHOICES,
            frame_id=frame_id,
            stem=stem,
        )
    if question_form == "coherence":
        from ..templates import resolve_coherence_frame

        frame = (
            coherence_frame
            if coherence_frame is not None
            else resolve_coherence_frame(
                benchmark.id, frame_id=benchmark.coherence_frame_id
            )
        )
        if frame.survey_header is None:
            raise ValueError(
                f"coherence frame {frame.id!r} declares no survey_header; a "
                f"survey cannot be rendered under it without one (declaring "
                f"the human-facing wording is part of the frame's identity)."
            )
        return SurveyQuestion(
            question_form="coherence",
            header=frame.survey_header,
            body=_render_coherence_body(benchmark, item),
            choices=COHERENCE_VERDICT_CHOICES,
            frame_id=frame.id,
            stem=frame.survey_stem,
        )
    raise ValueError(f"unknown question_form {question_form!r}")


def _render_coherence_body(benchmark: Benchmark, item: BenchmarkItem) -> str:
    """Render the commit/deny scaffolding via the benchmark's bound template.

    Uses the same context builders + template the model's coherence path uses,
    so the human and the model see identical scaffolding.
    """
    from ..context import resolve_context_builders
    from ..templates import VerdictRequest, arity_of, resolve_template

    premise_builder, _ = resolve_context_builders(benchmark.context_builders)
    prem = [strip_tex_math(benchmark.bearer(b).expression).strip() for b in sorted(item.premises)]
    concl = [strip_tex_math(benchmark.bearer(b).expression).strip() for b in sorted(item.conclusions)]
    req = VerdictRequest(
        arity=arity_of(sorted(item.conclusions)),
        gamma_ctx=premise_builder(prem),
        delta_ctx=tuple(concl),
    )
    return resolve_template(benchmark.id, template_id=benchmark.template_id).render(req)


def verdict_from_choice_text(cell: str, *, question_form: str = "support") -> Verdict:
    """Map a chosen MC label back to a :class:`Verdict` under ``question_form``.

    ``support``: ``Good → good``, ``Bad → bad``, ``Abstain → abstain``.
    ``coherence``: the server-side inversion — ``Incoherent → good``,
    ``Coherent → bad``, ``Unclear → abstain`` — so imported ``analyst_verdicts``
    are on the identical good/bad/abstain scale as the model's :math:`E_M`.
    """
    first = cell.strip().split()[0].lower() if cell.strip() else ""
    if question_form == "coherence":
        mapping = {
            "incoherent": Verdict.GOOD,
            "coherent": Verdict.BAD,
            "unclear": Verdict.ABSTAIN,
        }
    elif question_form == "support":
        mapping = {
            "good": Verdict.GOOD,
            "bad": Verdict.BAD,
            "abstain": Verdict.ABSTAIN,
        }
    else:
        raise ValueError(f"unknown question_form {question_form!r}")
    if first not in mapping:
        raise ValueError(
            f"unrecognised verdict choice text {cell!r} for "
            f"question_form={question_form!r}; expected a cell beginning with one "
            f"of {sorted(m.capitalize() for m in mapping)}."
        )
    return mapping[first]


# ---- Respondent shape (shared by all three platforms' CSV importers) -----


@dataclass(frozen=True, slots=True)
class SurveyRespondent:
    """One respondent's verdicts as parsed from a platform CSV export.

    The three platform-specific CSV parsers
    (:func:`~infereval.survey.qualtrics_csv.parse_qualtrics_csv`,
    :func:`~infereval.survey.google_forms_csv.parse_google_forms_csv`,
    :func:`~infereval.survey.surveymonkey_csv.parse_surveymonkey_csv`)
    all return ``list[SurveyRespondent]``. The shared
    :func:`~infereval.survey.qualtrics_csv.merge_respondents` then
    extends a :class:`~infereval.benchmark.Benchmark` with one new
    analyst column per respondent.
    """

    response_id: str
    """Platform-issued respondent identifier. Used as the suffix of the
    new analyst id (e.g. ``f"clinician-{response_id}"``). Stable +
    opaque + unique per the platform's contract."""

    started_at: datetime | None
    """When the respondent started the survey. ``None`` if the platform
    CSV doesn't carry a start timestamp."""

    finished: bool
    """Whether the respondent submitted a finished response (as opposed
    to abandoning partway through). Drives ``require_complete=True``
    rejection in the merger."""

    expertise: str | None
    """The free-text expertise blurb the respondent typed in the
    survey's first block. Lands in
    :attr:`AnalystModel.expertise_description` on the merged
    benchmark. ``None`` if the respondent skipped it."""

    verdicts: dict[str, Verdict] = field(default_factory=dict)
    """Map ``{sanitized_export_tag -> Verdict}``. The tag matches what
    :func:`sanitize_export_tag` returned at export time, so the merger
    can look each item.id up unambiguously."""

    rationales: dict[str, str | None] = field(default_factory=dict)
    """Map ``{sanitized_export_tag -> rationale-or-None}``. A missing
    key means the importer didn't see a rationale column for that
    item; an explicit ``None`` means the column existed but the
    respondent left it blank."""
