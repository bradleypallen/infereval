"""Template registry + bilateral coherence contract (generalization brief §5, §3.1).

The endorsement core emits a **typed, domain-free** :class:`VerdictRequest`; a
bound :class:`Template` renders its *content scaffolding* (the commit-set /
deny-set in a domain idiom), and the *question form* frames that scaffolding into
one prompt and decodes the answer back to a :class:`Verdict`:

    prompt = question_form.frame(template.render(req))

This module owns the ``coherence`` question form and the default framework
templates for all three arities (``|Δ| ∈ {0, 1, "many"}``). The legacy
``support`` question form is not here — it routes through the unchanged
:mod:`infereval.prompts` path so the single-succedent common case is byte-for-byte
preserved.

**Polarity firewall (the single most likely silent bug).** The coherence decode
is *uniform across arities*: ``INCOHERENT → good``, ``COHERENT → bad``,
``UNCLEAR → abstain``. At ``|Δ| = 0`` (deny nothing) this reads as
"the committed bearers are incompatible → good"; at ``|Δ| = 1`` it reads as
"commit Γ and deny ψ is untenable, so the inference holds → good". The
participant only ever answers a plain coherence question; the inversion
(``coherent`` maps to ``bad``) lives entirely server-side, here.

A template may branch on ``req.arity`` / ``req.structure`` but is handed only the
*rendered contexts* — never the bearer ids — so it structurally cannot re-smuggle
the domain into the verdict layer.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from .types import ParseStatus, Verdict

__all__ = [
    "Arity",
    "CoherenceFrame",
    "DEFEASIBLE_COHERENCE_FRAME",
    "DefaultTemplate",
    "RenderedPrompt",
    "THIN_COHERENCE_FRAME",
    "Template",
    "UNDERDET_COHERENCE_FRAME",
    "VerdictRequest",
    "arity_of",
    "coherence_decode",
    "coherence_frame_for_id",
    "coherence_prompt",
    "register_coherence_frame",
    "register_coherence_frame_id",
    "register_template",
    "register_template_id",
    "resolve_coherence_frame",
    "resolve_template",
    "template_for_id",
]

#: Succedent arity: ``0`` (incompatibility), ``1`` (single), ``"many"`` (disjunctive).
Arity = Literal[0, 1, "many"]


def arity_of(conclusions: Sequence[str]) -> Arity:
    """Map a conclusion set to its arity token."""
    n = len(conclusions)
    return 0 if n == 0 else 1 if n == 1 else "many"


@dataclass(frozen=True)
class VerdictRequest:
    """A domain-free request to render + decode one bilateral verdict.

    ``gamma_ctx`` is the fully-rendered premise (commit) context; ``delta_ctx``
    is the per-member rendered deny context (empty for arity 0, one entry for
    arity 1, several for ``"many"``). No bearer ids appear here.
    """

    arity: Arity
    gamma_ctx: str
    delta_ctx: tuple[str, ...]
    structure: str = "commit_deny"


@dataclass(frozen=True)
class RenderedPrompt:
    """The composed prompt: system + user text, plus the answer contract."""

    system: str
    user: str
    labels: tuple[str, ...]
    parse_regex: str


@runtime_checkable
class Template(Protocol):
    """Renders a :class:`VerdictRequest`'s content scaffolding (no question, no labels)."""

    @property
    def id(self) -> str: ...

    def render(self, req: VerdictRequest) -> str: ...


@dataclass(frozen=True)
class DefaultTemplate:
    """The bare framework template: an idiom-free commit/deny position stem."""

    id: str = "framework-default-v1"

    def render(self, req: VerdictRequest) -> str:
        commit = f"commits to the following: {req.gamma_ctx}"
        if req.arity == 0:
            return f"Consider a position that {commit}."
        if req.arity == 1:
            return f"Consider a position that {commit}; and denies: {req.delta_ctx[0]}."
        joined = "; ".join(req.delta_ctx)
        return f"Consider a position that {commit}; and denies every one of: {joined}."


# ---- coherence question form ---------------------------------------------

_COHERENCE_SYSTEM = (
    "You are judging the coherence of a position in everyday reasoning. A position "
    "commits to some claims and may deny others. "
    "Answer with exactly one of: COHERENT, INCOHERENT, UNCLEAR. No other text.\n\n"
    "COHERENT means the whole position can be held together without conflict.\n"
    "INCOHERENT means the position is untenable — its commitments and denials "
    "conflict (for a position that only commits and denies nothing, INCOHERENT "
    "means those claims cannot all hold together).\n"
    "UNCLEAR means the question is ill-formed or you cannot judge."
)
_COHERENCE_LABELS = ("INCOHERENT", "COHERENT", "UNCLEAR")
# INCOHERENT first so the alternation never matches the COHERENT substring of it.
_COHERENCE_PARSE = r"\b(INCOHERENT|COHERENT|UNCLEAR)\b"


@dataclass(frozen=True)
class CoherenceFrame:
    """A versioned system prompt for the coherence question form.

    The frame is the coherence-side analogue of the support path's
    :class:`infereval.prompts.VerificationPrompt`: it states the norms of the
    assessment (what COHERENT/INCOHERENT/UNCLEAR are to mean) while the
    template controls the rendering of the position and the library controls
    the question line, labels, parse regex, and decode. A frame carries ONLY
    the system text --- the answer contract and the polarity firewall
    (:func:`coherence_decode`) are deliberately not frame-configurable, so no
    frame can silently invert verdicts.

    Frames are versioned by id; redefining a frame's text under an existing
    id breaks provenance --- mint a new id instead, mirroring the
    additive-only bearer-versioning contract.

    ``survey_header`` is the frame's *human-facing* surface: the survey
    instruction text stating the same assessment norms in respondent
    voice. It changes ONLY the header --- the choice labels and the
    importer decode stay library-controlled at every frame, exactly as the
    question line/labels/decode do on the model side. ``None`` means the
    frame has no survey surface, and rendering a survey under it fails
    loudly rather than silently eliciting humans under a different frame
    than the one recorded.

    ``survey_stem`` is the header's own closing question line, declared
    separately so an exporter's instructions header mode can render the
    full header ONCE as a survey-level instructions page and repeat only
    this line per item. It must be a verbatim trailing substring of
    ``survey_header`` (tested for the built-ins): the stem introduces no
    wording that is not already part of the frame's reviewed surface.
    ``None`` means the frame declares no stem and the instructions mode
    fails loudly for it.
    """

    id: str
    system: str
    survey_header: str | None = None
    survey_stem: str | None = None


#: The library's original coherence system prompt, unchanged: the label
#: contract with no material norms. This is the default frame; every
#: coherence evaluation produced by :func:`infereval.evaluation.evaluate`
#: before frames existed was elicited under exactly this text.
THIN_COHERENCE_FRAME = CoherenceFrame(
    id="thin-v1",
    system=_COHERENCE_SYSTEM,
    # Canonical text of the v0.17.4 coherence survey header, unchanged:
    # survey.render.COHERENCE_QUESTION_HEADER aliases this field.
    survey_header=(
        "Consider the position described below. Could this whole position be "
        "held at once without conflict, or is it untenable?"
    ),
    survey_stem=(
        "Could this whole position be held at once without conflict, or is "
        "it untenable?"
    ),
)

#: Materiality-anchored coherence frame: states the defeasibility norms
#: explicitly (material coherence, NOT strict consistency, defeater
#: semantics), with the commit/deny transposition of the bird/penguin
#: exemplar. Byte-identical to the ``defeasible-coherence-explicit-v1``
#: system of the 2026-07-02 anchored-coherence capture.
DEFEASIBLE_COHERENCE_FRAME = CoherenceFrame(
    id="defeasible-coherence-explicit-v1",
    system=(
        "You are judging whether a position is coherent in everyday defeasible "
        "reasoning. A position commits to some claims and may deny others.\n\n"
        "This is NOT a question of strict logical consistency. It is a question of "
        "material coherence: granting the commitments as stated, with typical "
        "background conditions and standard kinds, can the whole position be held "
        "together in the ordinary course of things?\n\n"
        "Answer with exactly one of: COHERENT, INCOHERENT, UNCLEAR. No other text.\n\n"
        "COHERENT means the whole position can be held together under default "
        "conditions — including when a commitment defeats what would otherwise "
        "ordinarily follow.\n"
        "INCOHERENT means the position is untenable: it denies something its "
        "commitments would ordinarily settle, or its commitments cannot all hold "
        "together in the ordinary course of things. A strict logical contradiction "
        "is not required.\n"
        "UNCLEAR means the question is ill-formed or you cannot judge.\n\n"
        "For example:\n"
        "  Consider a position that commits to the following: a is a bird; and "
        "denies: a can fly.\n"
        "  Verdict: INCOHERENT  (typical birds fly; absent further information, the "
        "denial clashes with what the commitment ordinarily settles)\n\n"
        "  Consider a position that commits to the following: a is a bird and a is "
        "a penguin; and denies: a can fly.\n"
        "  Verdict: COHERENT  (the second commitment is a defeater; the position "
        "holds together)"
    ),
    survey_header=(
        "Consider the position described below. A position commits to some "
        "claims and may deny others. This is not a question about strict "
        "logical contradiction: judge whether the whole position can be held "
        "together in the ordinary course of things, granting its commitments "
        "as stated and assuming typical circumstances and standard kinds of "
        "things. A position is untenable when it denies something its "
        "commitments would ordinarily settle, even without a strict "
        "contradiction, or when its commitments cannot all hold together in "
        "the ordinary course of things; it can be held together when its "
        "commitments leave room for what it denies — including when one "
        "commitment defeats what would otherwise ordinarily follow.\n\n"
        'For example: a position that commits to "a is a bird" and denies '
        '"a can fly" is untenable in the ordinary course of things (typical '
        'birds fly). A position that commits to "a is a bird and a is a '
        'penguin" and denies "a can fly" can be held together (penguins are '
        "birds that do not fly, so the denial fits).\n\n"
        "Could this whole position be held at once without conflict, is it "
        "untenable, or can you not judge?"
    ),
    survey_stem=(
        "Could this whole position be held at once without conflict, is it "
        "untenable, or can you not judge?"
    ),
)

#: The anchored frame extended with an underdetermination clause in the
#: UNCLEAR gloss plus a parallel third exemplar. Byte-identical to the
#: ``defeasible-coherence-underdet-v1`` system of the 2026-07-03
#: underdetermination-clause capture. Its abstain channel opens without
#: flooding but is not yet instrument-grade (see that capture's analysis);
#: shipped for provenance continuity and further study, not as a default.
UNDERDET_COHERENCE_FRAME = CoherenceFrame(
    id="defeasible-coherence-underdet-v1",
    system=(
        "You are judging whether a position is coherent in everyday defeasible "
        "reasoning. A position commits to some claims and may deny others.\n\n"
        "This is NOT a question of strict logical consistency. It is a question of "
        "material coherence: granting the commitments as stated, with typical "
        "background conditions and standard kinds, can the whole position be held "
        "together in the ordinary course of things?\n\n"
        "Answer with exactly one of: COHERENT, INCOHERENT, UNCLEAR. No other text.\n\n"
        "COHERENT means the whole position can be held together under default "
        "conditions — including when a commitment defeats what would otherwise "
        "ordinarily follow.\n"
        "INCOHERENT means the position is untenable: it denies something its "
        "commitments would ordinarily settle, or its commitments cannot all hold "
        "together in the ordinary course of things. A strict logical contradiction "
        "is not required.\n"
        "UNCLEAR means the question is ill-formed or you cannot judge — or the "
        "matter is genuinely underdetermined: the commitments bear on what the "
        "position denies but neither ordinarily settle it nor defeat it, so "
        "competent reasoners could disagree about whether the position holds "
        "together.\n\n"
        "For example:\n"
        "  Consider a position that commits to the following: a is a bird; and "
        "denies: a can fly.\n"
        "  Verdict: INCOHERENT  (typical birds fly; absent further information, the "
        "denial clashes with what the commitment ordinarily settles)\n\n"
        "  Consider a position that commits to the following: a is a bird and a is "
        "a penguin; and denies: a can fly.\n"
        "  Verdict: COHERENT  (the second commitment is a defeater; the position "
        "holds together)\n\n"
        "  Consider a position that commits to the following: a is a bird and a is "
        "unusually heavy for its kind; and denies: a can fly.\n"
        "  Verdict: UNCLEAR  (the commitments pull in different directions without "
        "settling the matter; competent reasoners could disagree)"
    ),
    survey_header=(
        "Consider the position described below. A position commits to some "
        "claims and may deny others. This is not a question about strict "
        "logical contradiction: judge whether the whole position can be held "
        "together in the ordinary course of things, granting its commitments "
        "as stated and assuming typical circumstances and standard kinds of "
        "things. A position is untenable when it denies something its "
        "commitments would ordinarily settle, even without a strict "
        "contradiction, or when its commitments cannot all hold together in "
        "the ordinary course of things; it can be held together when its "
        "commitments leave room for what it denies — including when one "
        "commitment defeats what would otherwise ordinarily follow. If the "
        "commitments bear on what the position denies but neither ordinarily "
        "settle it nor override it — so that competent judges could "
        "reasonably disagree — treat it as a case you cannot settle either "
        "way.\n\n"
        'For example: a position that commits to "a is a bird" and denies '
        '"a can fly" is untenable in the ordinary course of things (typical '
        'birds fly). A position that commits to "a is a bird and a is a '
        'penguin" and denies "a can fly" can be held together (penguins are '
        'birds that do not fly, so the denial fits). A position that commits '
        'to "a is a bird and a is unusually heavy for its kind" and denies '
        '"a can fly" is one where competent judges could reasonably disagree '
        "(a case you could not settle either way).\n\n"
        "Could this whole position be held at once without conflict, is it "
        "untenable, or is this a case you cannot settle either way?"
    ),
    survey_stem=(
        "Could this whole position be held at once without conflict, is it "
        "untenable, or is this a case you cannot settle either way?"
    ),
)


def coherence_prompt(
    req: VerdictRequest, template: Template, frame: CoherenceFrame | None = None
) -> RenderedPrompt:
    """Frame a template's scaffolding as the bilateral coherence question.

    ``frame`` supplies the system text only; the question line, labels, and
    parse regex are the library's at every frame. ``None`` means the thin
    default frame --- byte-identical composition to the pre-frame library.
    """
    scaffold = template.render(req)
    user = (
        f"{scaffold}\n"
        "Is this position coherent? Answer COHERENT, INCOHERENT, or UNCLEAR."
    )
    return RenderedPrompt(
        system=(frame or THIN_COHERENCE_FRAME).system,
        user=user,
        labels=_COHERENCE_LABELS,
        parse_regex=_COHERENCE_PARSE,
    )


def coherence_decode(
    text: str, pattern: re.Pattern[str], req: VerdictRequest
) -> tuple[Verdict, ParseStatus]:
    """Decode a coherence answer to a :class:`Verdict` (uniform polarity).

    ``INCOHERENT → good``, ``COHERENT → bad``, ``UNCLEAR → abstain`` — the same
    mapping at every arity. ``req`` is accepted for interface symmetry with
    future arity-sensitive templates; the polarity itself does not depend on it.
    """
    match = pattern.search(text)
    if match is None:
        return Verdict.ABSTAIN, "unparseable"
    token = match.group(1).upper()
    if token == "INCOHERENT":
        return Verdict.GOOD, "ok"
    if token == "COHERENT":
        return Verdict.BAD, "ok"
    return Verdict.ABSTAIN, "ok"  # UNCLEAR — a real "cannot judge", not a parse miss


# ---- coherence-frame registry + catalog ------------------------------------

_FRAME_REGISTRY: dict[str, CoherenceFrame] = {}

# Frame catalog: frame.id -> instance, the namespace a benchmark-level
# ``coherence_frame_id`` field (or an EndorsementConfig.coherence_frame_id)
# names. All library frames are module-level constants here, so no lazy
# loading is needed.
_FRAME_CATALOG: dict[str, CoherenceFrame] = {
    f.id: f
    for f in (THIN_COHERENCE_FRAME, DEFEASIBLE_COHERENCE_FRAME, UNDERDET_COHERENCE_FRAME)
}


def register_coherence_frame(domain_id: str, frame: CoherenceFrame) -> None:
    """Bind a coherence frame to a domain (a benchmark id). Overwrites any prior binding."""
    _FRAME_REGISTRY[domain_id] = frame


def register_coherence_frame_id(frame: CoherenceFrame) -> None:
    """Catalog ``frame`` under its own ``id`` for by-id binding.

    The registration surface behind benchmark-level and config-level
    ``coherence_frame_id`` fields. Overwrites any prior frame with the same
    id --- which breaks provenance for that id; mint new ids instead.
    """
    _FRAME_CATALOG[frame.id] = frame


def coherence_frame_for_id(frame_id: str) -> CoherenceFrame:
    """Return the catalogued frame whose ``id`` is ``frame_id``.

    Unknown ids raise ``ValueError`` instead of silently falling back to the
    thin default --- an evaluation that declares a frame it can't get would
    otherwise be elicited under a different instrument than it records.
    """
    if frame_id not in _FRAME_CATALOG:
        raise ValueError(
            f"unknown coherence_frame_id {frame_id!r} (catalogued: "
            f"{', '.join(sorted(_FRAME_CATALOG))}). Third-party frames must be "
            f"catalogued via register_coherence_frame_id() before evaluation."
        )
    return _FRAME_CATALOG[frame_id]


def resolve_coherence_frame(
    domain_id: str | None = None, *, frame_id: str | None = None
) -> CoherenceFrame:
    """Return the coherence frame to elicit ``domain_id``'s items under.

    Precedence, most binding first:

    1. a programmatic :func:`register_coherence_frame` entry for
       ``domain_id`` --- the session-level override;
    2. ``frame_id`` --- a declared binding
       (:attr:`infereval.benchmark.Benchmark.coherence_frame_id` or an input
       config's ``coherence_frame_id``), looked up in the catalog; unknown
       ids raise;
    3. :data:`THIN_COHERENCE_FRAME`.
    """
    if domain_id is not None and domain_id in _FRAME_REGISTRY:
        return _FRAME_REGISTRY[domain_id]
    if frame_id is not None:
        return coherence_frame_for_id(frame_id)
    return THIN_COHERENCE_FRAME


# ---- per-domain registry + template-id catalog -----------------------------

_DEFAULT_TEMPLATE: Template = DefaultTemplate()
_REGISTRY: dict[str, Template] = {}

# Template catalog: template.id -> instance. A separate namespace from
# _REGISTRY (which is keyed by *benchmark* ids): the catalog is what a
# benchmark-level ``template_id`` field names. Library-shipped templates
# live in _BUILTIN_TEMPLATE_MODULES and are imported lazily on first
# lookup, so a benchmark's declared binding resolves without any caller
# having to import the defining module for its registration side effect.
_CATALOG: dict[str, Template] = {_DEFAULT_TEMPLATE.id: _DEFAULT_TEMPLATE}
_BUILTIN_TEMPLATE_MODULES = ("infereval.templates_clinical",)


def register_template(domain_id: str, template: Template) -> None:
    """Bind a template to a domain (a benchmark id). Overwrites any prior binding."""
    _REGISTRY[domain_id] = template


def register_template_id(template: Template) -> None:
    """Catalog ``template`` under its own ``id`` for ``template_id`` binding.

    This is the registration surface behind the benchmark-level
    :attr:`infereval.benchmark.Benchmark.template_id` field: a benchmark
    names a catalogued template id and :func:`resolve_template` looks it up
    here. Overwrites any prior template with the same id.
    """
    _CATALOG[template.id] = template


def template_for_id(template_id: str) -> Template:
    """Return the catalogued template whose ``id`` is ``template_id``.

    Unknown ids raise ``ValueError`` instead of silently falling back to the
    default — a benchmark that declares a binding it can't get would
    otherwise be measured under a different instrument than it records.
    """
    if template_id not in _CATALOG:
        # Built-in templates catalog themselves on import; load them before
        # giving up (idempotent — importlib caches).
        for module in _BUILTIN_TEMPLATE_MODULES:
            importlib.import_module(module)
    if template_id not in _CATALOG:
        raise ValueError(
            f"unknown template_id {template_id!r} (catalogued: "
            f"{', '.join(sorted(_CATALOG))}). Third-party templates must be "
            f"catalogued via register_template_id() before evaluation."
        )
    return _CATALOG[template_id]


def resolve_template(
    domain_id: str | None = None, *, template_id: str | None = None
) -> Template:
    """Return the template to render ``domain_id``'s items through.

    Precedence, most binding first:

    1. a programmatic :func:`register_template` entry for ``domain_id`` —
       the session-level override;
    2. ``template_id`` — a benchmark-declared binding
       (:attr:`infereval.benchmark.Benchmark.template_id`), looked up in the
       :func:`register_template_id` catalog; unknown ids raise;
    3. the framework :class:`DefaultTemplate`.
    """
    if domain_id is not None and domain_id in _REGISTRY:
        return _REGISTRY[domain_id]
    if template_id is not None:
        return template_for_id(template_id)
    return _DEFAULT_TEMPLATE
