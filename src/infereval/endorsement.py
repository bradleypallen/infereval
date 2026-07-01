"""Endorsement function :math:`E_M`: sampling, parsing, majority vote.

The endorser issues ``n_samples`` provider calls with the same verification
prompt, parses each response into a :class:`Verdict`, and aggregates them
into a single :math:`E_M` verdict via deterministic majority vote.

Tie-break policy (the paper underdetermines this; we lock conservative
defaults):

- If :class:`Verdict.ABSTAIN` is among the tied verdicts, abstain wins
  (matches the paper's treatment of abstain as the safe fallback).
- Otherwise, a pure GOOD/BAD tie is decided by the configured
  ``tie_break`` policy (``"abstain"`` by default, also ``"good"``,
  ``"bad"``, ``"first"``).

Provider sample failures (after retries) are counted as abstain with
``parse_status = "sample_failed"`` and do not abort the endorsement.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from .context import ContextBuilder, strip_tex_math
from .evaluation import (
    EndorsementConfig,
    MajorityVote,
    ProviderParams,
    SampleRecord,
    SampleUsage,
)
from .logging_setup import log_event, prompt_hash
from .prompts import (
    DEFAULT_VERIFICATION_PROMPT,
    VerificationPrompt,
    parse_verdict,
)
from .providers.base import (
    BUDGET_FINISH_REASONS,
    Provider,
    ProviderSampleError,
    SampleRequest,
)
from .templates import (
    Template,
    VerdictRequest,
    arity_of,
    coherence_decode,
    coherence_prompt,
    resolve_template,
)
from .types import Bearer, Implication, ParseStatus, Verdict

QuestionForm = Literal["support", "coherence"]
_ExtractFn = Callable[[str], tuple[Verdict, ParseStatus]]

log = logging.getLogger(__name__)


TieBreak = Literal["abstain", "good", "bad", "first"]


# ---- Majority vote --------------------------------------------------------


def majority_vote(
    verdicts: list[Verdict],
    tie_break: TieBreak = "abstain",
) -> tuple[Verdict, bool]:
    """Aggregate per-sample verdicts into a single verdict.

    Returns ``(chosen_verdict, tie_broken_flag)``.

    Tie rules (in order):

    1. If ``verdicts`` is empty, return ``(ABSTAIN, False)``.
    2. If exactly one verdict has the max count, return it.
    3. Tie: if ABSTAIN is among the tied set, return ABSTAIN.
    4. Otherwise (pure GOOD/BAD tie), apply ``tie_break``.
    """
    if not verdicts:
        return Verdict.ABSTAIN, False

    counts = Counter(verdicts)
    max_count = max(counts.values())
    top = [v for v in counts if counts[v] == max_count]

    if len(top) == 1:
        return top[0], False

    # Tie. ABSTAIN wins any tie it is part of.
    if Verdict.ABSTAIN in top:
        return Verdict.ABSTAIN, True

    # Pure GOOD/BAD tie. Apply tie_break.
    if tie_break == "abstain":
        return Verdict.ABSTAIN, True
    if tie_break == "good":
        return Verdict.GOOD, True
    if tie_break == "bad":
        return Verdict.BAD, True
    if tie_break == "first":
        for v in verdicts:
            if v in top:
                return v, True
        return top[0], True  # unreachable, defensive
    # Unknown tie_break: fall back to abstain (Literal forbids this at type level).
    return Verdict.ABSTAIN, True


# ---- EndorsementRecord ----------------------------------------------------


@dataclass
class EndorsementRecord:
    """Result of one :func:`endorse` call.

    This is the in-memory analog of an evaluation file's per-item record;
    :func:`infereval.evaluation.evaluate` converts it to an
    :class:`infereval.evaluation.EvaluationItem` for serialization.
    """

    implication: Implication
    samples: list[SampleRecord]
    counts: dict[Verdict, int]
    verdict: Verdict
    tie_broken: bool
    premise_context: str
    """The full natural-language premise context shown to the model."""
    conclusion_context: str
    """The full natural-language conclusion context shown to the model."""
    rendered_user_prompt: str = field(default="", repr=False)

    def to_majority_vote(self) -> MajorityVote:
        """Project counts + verdict into a Pydantic :class:`MajorityVote`."""
        return MajorityVote(
            good=self.counts.get(Verdict.GOOD, 0),
            bad=self.counts.get(Verdict.BAD, 0),
            abstain=self.counts.get(Verdict.ABSTAIN, 0),
            verdict=self.verdict,
            tie_broken=self.tie_broken,
        )


# ---- Helpers -------------------------------------------------------------


def _expressions_for(
    bearer_ids: frozenset[str],
    bearers: Mapping[str, Bearer],
    *,
    strip_tex: bool,
    variant: int = 0,
) -> list[str]:
    """Return the bearer expressions for ``bearer_ids``, sorted by id.

    For ``variant=0`` (default) every bearer is rendered via its canonical
    :attr:`Bearer.expression`. For ``variant=k >= 1`` every bearer is
    rendered via ``bearer.paraphrases[k-1]`` *if it exists*, falling back
    to ``bearer.expression`` otherwise. The fallback rule lets benchmarks
    have mixed paraphrase coverage — some bearers with 3 variants, others
    with none — and higher variants quietly use the canonical for bearers
    that don't reach them.

    Phase 1.2 of the construct-validity infrastructure (R10: paraphrase
    variation under fixed inferential content).
    """
    out: list[str] = []
    for bid in sorted(bearer_ids):
        bearer = bearers[bid]
        if variant == 0:
            expr = bearer.expression
        else:
            try:
                expr = bearer.paraphrases[variant - 1]
            except IndexError:
                expr = bearer.expression
        if strip_tex:
            expr = strip_tex_math(expr)
        out.append(expr)
    return out


def _usage_from_mapping(usage: Mapping[str, int] | None) -> SampleUsage | None:
    if not usage:
        return None
    return SampleUsage.model_validate(dict(usage))


# ---- The main entry point: endorse() --------------------------------------


def _build_prompt(
    *,
    implication: Implication,
    question_form: QuestionForm,
    verification_prompt: VerificationPrompt,
    template: Template | None,
    premise_ctx: str,
    conclusion_ctx: str,
    conclusion_exprs: list[str],
) -> tuple[str, str, _ExtractFn, str]:
    """Compose the (system, user, verdict-extractor, prompt-id) for one item.

    ``support`` routes through the unchanged verification-prompt path — byte-for-byte
    the pre-generalization behaviour — and is defined only for ``|Δ| = 1``.
    ``coherence`` renders the bilateral coherence question via the template
    registry and is defined for every arity (brief §3.1).
    """
    if question_form == "support":
        if len(implication.conclusions) != 1:
            raise ValueError(
                f"question_form='support' is defined only for single-succedent items "
                f"(|Δ|=1); item {implication.id!r} has |Δ|={len(implication.conclusions)}. "
                f"Use question_form='coherence' for empty or disjunctive succedents."
            )
        parser = verification_prompt.compile_parser()

        def _support_extract(text: str) -> tuple[Verdict, ParseStatus]:
            return parse_verdict(text, parser)

        user = verification_prompt.build_user(premise_ctx, conclusion_ctx)
        return verification_prompt.system, user, _support_extract, verification_prompt.id

    tmpl = template if template is not None else resolve_template()
    req = VerdictRequest(
        arity=arity_of(sorted(implication.conclusions)),
        gamma_ctx=premise_ctx,
        delta_ctx=tuple(conclusion_exprs),
        structure="commit_deny",
    )
    rendered = coherence_prompt(req, tmpl)
    pattern = re.compile(rendered.parse_regex, re.IGNORECASE)

    def _coherence_extract(text: str) -> tuple[Verdict, ParseStatus]:
        return coherence_decode(text, pattern, req)

    return rendered.system, rendered.user, _coherence_extract, f"{tmpl.id}:coherence"


def endorse(
    implication: Implication,
    bearers: Mapping[str, Bearer],
    provider: Provider,
    config: EndorsementConfig,
    params: ProviderParams,
    *,
    premise_builder: ContextBuilder,
    conclusion_builder: ContextBuilder,
    verification_prompt: VerificationPrompt = DEFAULT_VERIFICATION_PROMPT,
    strip_tex: bool = True,
    request_id_prefix: str | None = None,
    variant: int = 0,
    question_form: QuestionForm = "support",
    template: Template | None = None,
) -> EndorsementRecord:
    """Compute :math:`E_M(\\langle \\Gamma, \\Delta \\rangle)` for one implication.

    Issues ``config.n_samples`` calls to ``provider`` with the verification
    prompt built from ``premise_builder`` and ``conclusion_builder``,
    parses each response, and aggregates via :func:`majority_vote`.

    Provider sample failures (after the provider's own retries are
    exhausted) are recorded as ``sample_failed`` and contribute an
    ``ABSTAIN`` verdict to the vote.

    The ``variant`` parameter selects which expression each bearer is
    rendered with. ``variant=0`` (the default) uses the canonical
    expressions; ``variant=k`` uses ``bearer.paraphrases[k-1]`` per
    :func:`_expressions_for`. Use this to drive the paraphrase axis
    of variation (R10) without needing to mutate the benchmark JSON
    between runs.
    """
    premise_exprs = _expressions_for(
        implication.premises, bearers, strip_tex=strip_tex, variant=variant
    )
    conclusion_exprs = _expressions_for(
        implication.conclusions, bearers, strip_tex=strip_tex, variant=variant
    )
    premise_ctx = premise_builder(premise_exprs)
    conclusion_ctx = conclusion_builder(conclusion_exprs)

    system_text, user_text, extract, prompt_id = _build_prompt(
        implication=implication,
        question_form=question_form,
        verification_prompt=verification_prompt,
        template=template,
        premise_ctx=premise_ctx,
        conclusion_ctx=conclusion_ctx,
        conclusion_exprs=conclusion_exprs,
    )

    sample_records: list[SampleRecord] = []
    verdicts: list[Verdict] = []
    user_prompt_hash = prompt_hash(user_text)
    premise_ids = sorted(implication.premises)
    conclusion_ids = sorted(implication.conclusions)

    log_event(
        log,
        "item.started",
        item_id=implication.id,
        n_samples=config.n_samples,
        tie_break=config.tie_break,
        premise_ids=premise_ids,
        conclusion_ids=conclusion_ids,
        prompt_hash=user_prompt_hash,
        verification_prompt_id=prompt_id,
        question_form=question_form,
    )

    for i in range(config.n_samples):
        rid = f"{request_id_prefix}:sample-{i}" if request_id_prefix else None
        req = SampleRequest(
            prompt=user_text,
            system=system_text,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            top_p=params.top_p,
            seed=params.seed,
            stop=params.stop,
            request_id=rid,
        )
        try:
            result = provider.sample(req)
            verdict, status = extract(result.text)
            # Promote unparseable -> budget_clipped when the provider says the
            # response was truncated by max_tokens. The verdict stays abstain
            # (Definition 2 fallback) but the parse_status now tells the user
            # the abstain is operational, not a model decision.
            if (
                status == "unparseable"
                and result.finish_reason in BUDGET_FINISH_REASONS
            ):
                status = "budget_clipped"
            record = SampleRecord(
                sample_index=i,
                raw_response=result.text,
                parsed_verdict=verdict,
                parse_status=status,
                request_id=result.request_id,
                wall_time_ms=result.wall_time_ms,
                usage=_usage_from_mapping(result.usage),
                finish_reason=result.finish_reason,
                reasoning_tokens=result.reasoning_tokens,
            )
            log_event(
                log,
                "sample.completed",
                item_id=implication.id,
                sample_index=i,
                provider=result.provider,
                model_id=result.model_id,
                request_id=result.request_id,
                prompt_hash=user_prompt_hash,
                raw_response=result.text,
                parsed_verdict=str(verdict),
                parse_status=status,
                wall_time_ms=result.wall_time_ms,
                input_tokens=result.usage.get("input_tokens") if result.usage else None,
                output_tokens=result.usage.get("output_tokens") if result.usage else None,
                finish_reason=result.finish_reason,
                reasoning_tokens=result.reasoning_tokens,
            )
        except ProviderSampleError as exc:
            log_event(
                log,
                "sample.failed",
                item_id=implication.id,
                sample_index=i,
                prompt_hash=user_prompt_hash,
                err=str(exc),
            )
            verdict = Verdict.ABSTAIN
            # v0.15.0: provider_error carries the str of the underlying
            # exception so downstream metrics / retest / report code can
            # distinguish instrument failure from real model abstention.
            # parsed_verdict stays ABSTAIN for backward compatibility
            # with v0.14.0 consumers that don't understand the new field;
            # aggregators that DO understand it (v0.15.0+) skip the sample.
            record = SampleRecord(
                sample_index=i,
                raw_response="",
                parsed_verdict=Verdict.ABSTAIN,
                parse_status="sample_failed",
                request_id=rid,
                wall_time_ms=None,
                usage=None,
                finish_reason=None,
                reasoning_tokens=None,
                provider_error=str(exc),
            )
        sample_records.append(record)
        verdicts.append(verdict)

    # v0.15.0: skip samples whose provider call failed (provider_error set)
    # when computing the majority vote and the per-verdict counts. The
    # raw SampleRecord retains the placeholder ABSTAIN parsed_verdict so
    # the eta JSON round-trips for v0.14.0 consumers; the *aggregated*
    # majority vote and counts reflect only samples that actually
    # produced a real model response. If every sample failed, the vote
    # collapses to ABSTAIN (the existing majority_vote(empty) contract)
    # — a fuller "model_verdict = None" representation is deferred to a
    # later release per the v0.15.0 plan.
    voting_verdicts = [
        rec.parsed_verdict
        for rec in sample_records
        if rec.provider_error is None
    ]
    final, tie_broken = majority_vote(voting_verdicts, tie_break=config.tie_break)
    counts: dict[Verdict, int] = {v: 0 for v in Verdict}
    for v in voting_verdicts:
        counts[v] += 1

    log_event(
        log,
        "item.completed",
        item_id=implication.id,
        verdict=str(final),
        tie_broken=tie_broken,
        good=counts[Verdict.GOOD],
        bad=counts[Verdict.BAD],
        abstain=counts[Verdict.ABSTAIN],
    )

    return EndorsementRecord(
        implication=implication,
        samples=sample_records,
        counts=counts,
        verdict=final,
        tie_broken=tie_broken,
        premise_context=premise_ctx,
        conclusion_context=conclusion_ctx,
        rendered_user_prompt=user_text,
    )


__all__ = [
    "EndorsementRecord",
    "TieBreak",
    "endorse",
    "majority_vote",
]
