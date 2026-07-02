"""Evaluation :math:`\\eta` model and JSON I/O.

An evaluation, per Definition 5 of the paper, is the finite set

.. math::
   \\eta = \\{(I_1, V_1, E_M(I_1)), \\ldots, (I_n, V_n, E_M(I_n))\\}.

This module's Pydantic models extend that with the audit-trail fields a
research-grade tool needs: per-sample raw responses, majority-vote tallies,
provider/decoding identity, timing, and a benchmark hash for tamper detection.

Orchestration (running an evaluation against a benchmark) lives in M4 once the
provider abstraction and endorsement pipeline land.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
)

from . import __version__
from .benchmark import Reference, _promote_reference_shorthand
from .types import Implication, ParseStatus, Verdict

if TYPE_CHECKING:
    from .benchmark import Benchmark
    from .prompts import VerificationPrompt
    from .providers.base import Provider
    from .templates import Template

log = logging.getLogger(__name__)

SCHEMA_VERSION: Literal["1.0"] = "1.0"


TieBreak = Literal["abstain", "good", "bad", "first"]


class ProviderParams(BaseModel):
    """Decoding parameters passed to a provider sample call.

    The ``max_tokens`` default of 1024 is sized for current frontier models
    that consume budget on silent internal reasoning. See
    :class:`infereval.providers.base.SampleRequest` and
    ``docs/providers.md`` for the rationale and per-provider guidance.
    """

    model_config = ConfigDict(extra="allow")  # allow provider-specific extras

    temperature: float = 1.0
    max_tokens: int = 1024
    top_p: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] = ()


class ModelInfo(BaseModel):
    """Identity of the model under evaluation and the decoding params used."""

    model_config = ConfigDict(extra="forbid")

    provider: str  # "anthropic" / "openai" / "openrouter" / "mock" / ...
    model_id: str
    params: ProviderParams = Field(default_factory=ProviderParams)


class EndorsementConfig(BaseModel):
    """Configuration governing how :math:`E_M` is computed.

    Note on terminology: ``n_samples`` is the number of *completions
    drawn from M* per benchmark item, in the LLM-literature sense of
    "sample" (one draw from the model's output distribution). It is
    **not** the number of dataset rows — that is the benchmark's item
    count and is fixed by the benchmark. The methodology issues
    ``n_samples`` provider calls per item, parses each completion's
    verdict token, and majority-votes to compute :math:`E_M` for that
    item. See ``docs/concepts.md`` for the full terminology note.
    """

    model_config = ConfigDict(extra="forbid")

    n_samples: int = 5
    tie_break: TieBreak = "abstain"
    verification_prompt_id: str = "default-v1"
    context_builder_premise_id: str = "conjunction-and-v1"
    context_builder_conclusion_id: str = "disjunction-or-v1"
    question_form: Literal["support", "coherence"] = "support"
    """The logical question posed about each item (brief §3.1). ``support`` asks
    "does the conclusion follow?" and is defined only for single-succedent items;
    ``coherence`` asks "is committing Γ and denying Δ coherent?" and is defined
    for every arity. Persisted here so an evaluation records which question was
    asked (part of the §12.3 provenance tuple). Additive (v0.17.3): pre-existing
    evaluations load as ``support``."""

    @field_validator("n_samples")
    @classmethod
    def _positive_samples(cls, v: int) -> int:
        if v < 1:
            raise ValueError("n_samples must be >= 1")
        return v


class SampleUsage(BaseModel):
    """Token usage for a single provider call (provider-specific keys allowed)."""

    model_config = ConfigDict(extra="allow")

    input_tokens: int | None = None
    output_tokens: int | None = None


class SampleRecord(BaseModel):
    """One sampled response from the provider plus its parsed verdict."""

    model_config = ConfigDict(extra="forbid")

    sample_index: int
    raw_response: str
    parsed_verdict: Verdict
    parse_status: ParseStatus = "ok"
    request_id: str | None = None
    wall_time_ms: float | None = None
    usage: SampleUsage | None = None
    finish_reason: str | None = None
    """Provider-side stop reason, when reported. See
    :class:`infereval.providers.base.SampleResult.finish_reason`."""
    reasoning_tokens: int | None = None
    """Reasoning / thinking token count, when the provider reports it.
    See :class:`infereval.providers.base.SampleResult.reasoning_tokens`."""
    provider_error: str | None = None
    """v0.15.0+: non-None when the provider call failed (rate limit, HTTP
    error, empty response body, malformed response). When set, this
    sample represents an *instrument failure*, not a model decision —
    aggregators (:class:`MajorityVote.from_samples`) skip these samples
    rather than counting their ``parsed_verdict`` (which is left at
    ``Verdict.ABSTAIN`` for backward compatibility with v0.14.0
    consumers that don't understand the new field). The R22 audit and
    metrics paths likewise treat ``provider_error is not None`` as
    missing data, not as a model abstention.

    Pre-v0.15.0 eta JSONs without this field load with the default
    ``None`` — backward-compatible. Historical captures with silent
    empty-response failures (the v0.14.0 bug; see
    ``KNOWN_ISSUES_v0.14.0.md``) can be heuristically re-classified
    post-hoc via ``infereval audit`` (new in v0.15.0)."""


class MajorityVote(BaseModel):
    """Tally of parsed verdicts plus the resolved majority and tie-break flag."""

    model_config = ConfigDict(extra="forbid")

    good: int = 0
    bad: int = 0
    abstain: int = 0
    verdict: Verdict
    tie_broken: bool = False


class EvaluationItem(BaseModel):
    """One row of the evaluation :math:`\\eta`: implication + analyst verdicts + :math:`E_M`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    premises: list[str]
    conclusions: list[str]
    analyst_verdicts: list[Verdict]
    analyst_rationales: list[str] | None = Field(
        default=None,
        description=(
            "Optional per-analyst rationales propagated from the "
            "source benchmark item's analyst_rationales at evaluation "
            "build time. Positionally aligned to analyst_verdicts. "
            "null (or absent) when the source benchmark carried no "
            "rationale discipline; a present list (possibly containing "
            "empty strings) when it did. Covered by Evaluation.benchmark_hash."
        ),
    )
    """Optional per-analyst rationales propagated from
    :attr:`infereval.benchmark.BenchmarkItem.analyst_rationales` at
    evaluation-build time. Positionally aligned to
    :attr:`analyst_verdicts`. ``None`` (or absent) when the source
    benchmark carried no rationale discipline; a present list (possibly
    containing empty strings) when it did. Covered by the existing
    :attr:`Evaluation.benchmark_hash` integrity mechanism, so a
    rationale cannot be silently altered between evaluation and report
    without changing the hash. Added in v0.5.4 (AR8, AR9)."""
    model_verdict: Verdict
    samples: list[SampleRecord] = Field(default_factory=list)
    majority_vote: MajorityVote | None = None
    tags: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    """Per-item provenance, propagated from
    :attr:`infereval.benchmark.BenchmarkItem.references` at evaluation
    time. Carries the guideline / paper / regulatory citation that
    justifies the analyst's verdict so the evaluation JSON is a
    self-contained, auditable artifact (no need to look up the source
    benchmark separately)."""

    @field_validator("premises", "conclusions", mode="before")
    @classmethod
    def _dedup_and_sort(cls, v: object) -> object:
        if isinstance(v, list):
            return sorted({str(x) for x in v})
        return v

    @field_validator("references", mode="before")
    @classmethod
    def _promote_refs(cls, v: object) -> object:
        return _promote_reference_shorthand(v)

    @field_serializer("premises", "conclusions")
    def _serialize_sorted(self, value: list[str]) -> list[str]:
        return sorted(value)

    def to_implication(self) -> Implication:
        return Implication(
            premises=frozenset(self.premises),
            conclusions=frozenset(self.conclusions),
            id=self.id,
        )


class Evaluation(BaseModel):
    """An evaluation :math:`\\eta` of a model against a benchmark."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str  # run uuid
    benchmark_id: str
    benchmark_hash: str | None = None
    model: ModelInfo
    endorsement_config: EndorsementConfig = Field(default_factory=EndorsementConfig)
    framework_version: str = __version__
    started_at: datetime | None = None
    finished_at: datetime | None = None
    items: list[EvaluationItem]
    references: list[Reference] = Field(default_factory=list)
    """Corpus-level provenance, propagated from
    :attr:`infereval.benchmark.Benchmark.references` at evaluation
    time. Carries the paper, dialogue, or regulatory framework the
    benchmark is derived from, so an evaluation JSON read in isolation
    still names its primary sources."""
    paraphrase_variant: int = 0
    """Index of the paraphrase variant used at evaluation time. ``0``
    (default) means the canonical :attr:`BearerModel.expression` was
    used for every bearer. ``k >= 1`` means ``bearer.paraphrases[k-1]``
    was used per :func:`infereval.endorsement._expressions_for` (with
    fallback to the canonical for bearers that don't carry that
    paraphrase). Phase 1.2 of the construct-validity infrastructure
    (R10: paraphrase variation under fixed inferential content)."""

    @field_validator("references", mode="before")
    @classmethod
    def _promote_refs(cls, v: object) -> object:
        return _promote_reference_shorthand(v)

    @property
    def n(self) -> int:
        return len(self.items)

    def endorsements(self) -> dict[Implication, Verdict]:
        """Mapping ``Implication -> Verdict`` suitable for :meth:`DerivedFrame.from_endorsements`."""
        return {item.to_implication(): item.model_verdict for item in self.items}

    @classmethod
    def load(cls, path: str | Path) -> Evaluation:
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    @classmethod
    def loads(cls, text: str) -> Evaluation:
        return cls.model_validate_json(text)

    def dump(self, path: str | Path, *, indent: int = 2) -> None:
        with Path(path).open("w", encoding="utf-8") as f:
            f.write(self.dumps(indent=indent))
            f.write("\n")

    def dumps(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent, exclude_none=True)


# ---- Top-level orchestration ----------------------------------------------


def canonical_benchmark_hash(benchmark: Benchmark) -> str:
    """SHA-256 of the benchmark's canonical-JSON form, prefixed ``sha256:``.

    Recorded in :attr:`Evaluation.benchmark_hash` for tamper detection.
    Two benchmarks that round-trip to the same canonical JSON have the
    same hash; this is robust to insertion order in dicts.
    """
    canonical = json.dumps(
        benchmark.model_dump(mode="json", exclude_none=True),
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


def evaluate(
    benchmark: Benchmark,
    provider: Provider,
    *,
    config: EndorsementConfig | None = None,
    params: ProviderParams | None = None,
    verification_prompt: VerificationPrompt | None = None,
    strip_tex: bool = True,
    run_id: str | None = None,
    log_path: Path | str | None = None,
    variant: int = 0,
    template: Template | None = None,
) -> Evaluation:
    """Run a model against a benchmark and assemble the resulting :math:`\\eta`.

    Iterates over every benchmark item, calls
    :func:`infereval.endorsement.endorse` to compute :math:`E_M`, and
    packages the per-item samples + majority-vote tally into an
    :class:`Evaluation`.

    Parameters
    ----------
    benchmark
        The :math:`\\beta` to evaluate against.
    provider
        Any :class:`infereval.providers.Provider` (Anthropic, OpenAI,
        OpenRouter, or a mock).
    config
        Endorsement configuration. Defaults to ``EndorsementConfig()``
        (n_samples=5, tie_break=abstain, default verification prompt id).
    params
        Provider decoding parameters. Defaults to ``ProviderParams()``
        (temperature=1.0, max_tokens=1024).
    verification_prompt
        If supplied, overrides the framework default. If the benchmark
        has ``verification_prompt`` set, it takes precedence over the
        framework default but not over this argument.
    strip_tex
        Whether to strip ``$...$`` TeX-math delimiters from bearer
        expressions at prompt-construction time (default ``True``).
    run_id
        Stable identifier for this evaluation run, recorded as
        :attr:`Evaluation.id`. Generated as a UUID4 if not supplied.
    log_path
        Optional path for a JSONL run log; one event per line, suitable
        for ``jq`` or ``pandas.read_json(lines=True)``. If ``None`` (the
        default), no log file is written; library callers can still attach
        their own handlers to the ``infereval`` logger.

    Returns
    -------
    Evaluation
        The fully-populated :math:`\\eta` ready to serialize to JSON.
    """
    # Late imports to avoid the evaluation <-> endorsement <-> context cycle.
    from .context import resolve_context_builders
    from .endorsement import endorse
    from .logging_setup import configure_run_logging, log_event
    from .prompts import resolve_verification_prompt
    from .templates import resolve_template

    cfg = config or EndorsementConfig()
    par = params or ProviderParams()
    rid = run_id or str(uuid.uuid4())
    prompt = verification_prompt or resolve_verification_prompt(
        benchmark.verification_prompt
    )

    bearers = benchmark.runtime_bearers()
    premise_builder, conclusion_builder = resolve_context_builders(
        benchmark.context_builders
    )

    bench_hash = canonical_benchmark_hash(benchmark)

    with configure_run_logging(
        log_path,
        run_id=rid,
        extra_context={"benchmark_id": benchmark.id, "framework_version": __version__},
    ):
        started = datetime.now(timezone.utc)
        log_event(
            log,
            "run.started",
            benchmark_id=benchmark.id,
            benchmark_hash=bench_hash,
            n_items=benchmark.n,
            provider=provider.name,
            model_id=provider.model_id,
            params=par.model_dump(mode="json"),
            endorsement_config=cfg.model_dump(mode="json"),
            verification_prompt_id=prompt.id,
            strip_tex=strip_tex,
            paraphrase_variant=variant,
            framework_version=__version__,
        )

        items: list[EvaluationItem] = []
        for bench_item in benchmark.items:
            implication = bench_item.to_implication()
            record = endorse(
                implication,
                bearers,
                provider,
                cfg,
                par,
                premise_builder=premise_builder,
                conclusion_builder=conclusion_builder,
                verification_prompt=prompt,
                strip_tex=strip_tex,
                request_id_prefix=f"{rid}:{bench_item.id}",
                variant=variant,
                question_form=cfg.question_form,
                template=(
                    template if template is not None else resolve_template(benchmark.id)
                ),
            )
            items.append(
                EvaluationItem(
                    id=bench_item.id,
                    premises=sorted(bench_item.premises),
                    conclusions=sorted(bench_item.conclusions),
                    analyst_verdicts=list(bench_item.analyst_verdicts),
                    analyst_rationales=(
                        list(bench_item.analyst_rationales)
                        if bench_item.analyst_rationales is not None
                        else None
                    ),
                    model_verdict=record.verdict,
                    samples=record.samples,
                    majority_vote=record.to_majority_vote(),
                    tags=list(bench_item.tags),
                    references=list(bench_item.references),
                )
            )

        finished = datetime.now(timezone.utc)
        cfg_with_prompt_id = cfg.model_copy(
            update={"verification_prompt_id": prompt.id}
        )

        log_event(
            log,
            "run.finished",
            n_items=len(items),
            wall_time_s=(finished - started).total_seconds(),
        )

    return Evaluation(
        id=rid,
        benchmark_id=benchmark.id,
        benchmark_hash=bench_hash,
        model=ModelInfo(
            provider=provider.name,
            model_id=provider.model_id,
            params=par,
        ),
        endorsement_config=cfg_with_prompt_id,
        started_at=started,
        finished_at=finished,
        items=items,
        references=list(benchmark.references),
        paraphrase_variant=variant,
    )
