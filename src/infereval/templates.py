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
    "DefaultTemplate",
    "RenderedPrompt",
    "Template",
    "VerdictRequest",
    "arity_of",
    "coherence_decode",
    "coherence_prompt",
    "register_template",
    "register_template_id",
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


def coherence_prompt(req: VerdictRequest, template: Template) -> RenderedPrompt:
    """Frame a template's scaffolding as the bilateral coherence question."""
    scaffold = template.render(req)
    user = (
        f"{scaffold}\n"
        "Is this position coherent? Answer COHERENT, INCOHERENT, or UNCLEAR."
    )
    return RenderedPrompt(
        system=_COHERENCE_SYSTEM,
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
