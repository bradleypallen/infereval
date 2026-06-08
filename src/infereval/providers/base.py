"""Provider abstraction: the contract every LLM backend must satisfy.

Concrete providers live in sibling modules (``anthropic``, ``openai``,
``openrouter``, ``mock``). They all expose a single :meth:`Provider.sample`
method that takes a :class:`SampleRequest` and returns a :class:`SampleResult`.

:class:`BaseProvider` provides a shared retry-with-exponential-backoff loop,
timing, and logging. Concrete providers inherit from it and implement
:meth:`BaseProvider._sample_once` plus :meth:`BaseProvider._is_transient`
to participate in the retry machinery.

Reproducibility: every sample is logged. After ``max_attempts`` transient
failures, :class:`ProviderSampleError` is raised; the endorser (M4) maps
that to ``abstain`` with ``parse_status = "sample_failed"``.
"""

from __future__ import annotations

import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from infereval.logging_setup import log_event

log = logging.getLogger(__name__)


# ---- Errors --------------------------------------------------------------


class ProviderError(Exception):
    """Base class for all provider-related errors."""


class ProviderConfigError(ProviderError):
    """Raised when a provider is constructed without required configuration.

    Examples: missing API key, missing optional dependency (anthropic / openai
    SDK not installed).
    """


class ProviderSampleError(ProviderError):
    """Raised when sampling fails after the retry policy is exhausted.

    The endorser treats this as a single failed sample and maps the verdict
    to ``abstain`` (the paper's Definition 2, "Unparseable responses are
    mapped to abstain"). v0.15.0+: the resulting ``SampleRecord`` carries
    ``provider_error`` (the str of this exception) so downstream metrics
    can distinguish instrument failure from real model abstention.
    """


class EmptyResponseError(ProviderError):
    """v0.15.0+: raised when the provider returned HTTP 200 with an empty
    or whitespace-only response body.

    Treated as **always transient** by :meth:`BaseProvider.sample` —
    triggers the retry loop. If all retries exhaust, surfaces as
    :class:`ProviderSampleError`, which the endorser then records with
    ``provider_error`` set. This catches the v0.14.0 silent-empty-response
    bug (see ``KNOWN_ISSUES_v0.14.0.md``): OpenRouter rate-limit responses
    that returned 200 + empty body previously got parsed as ABSTAIN by
    the endorsement regex, masquerading as real model abstentions.
    """


# ---- Request / response types -------------------------------------------


@dataclass(frozen=True)
class SampleRequest:
    """A single completion request issued to a provider.

    The ``max_tokens`` default of 1024 is sized for current frontier models
    that consume budget on silent internal reasoning (DeepSeek v4-flash,
    OpenAI o-series, Gemini 2.5 Pro). Pre-reasoning models will only emit
    a handful of tokens for a one-word verdict regardless of this cap, so
    the higher default is cheap insurance against budget-clipping. See
    ``docs/providers.md`` for per-provider guidance.
    """

    prompt: str
    system: str | None = None
    temperature: float = 1.0
    max_tokens: int = 1024
    top_p: float | None = None
    seed: int | None = None
    stop: tuple[str, ...] = ()
    request_id: str | None = None
    """Client-side correlation id propagated to logs and to :attr:`SampleResult.request_id`."""


#: Provider-side finish reasons that signal the response was cut off by the
#: ``max_tokens`` budget rather than the model deciding to stop. OpenAI uses
#: ``"length"`` (Chat Completions API and Responses API); Anthropic Messages
#: uses ``"max_tokens"``. The set is the union so callers can detect budget
#: clipping without per-provider branching.
BUDGET_FINISH_REASONS: frozenset[str] = frozenset({"length", "max_tokens"})


@dataclass(frozen=True)
class SampleResult:
    """One completed sample from a provider.

    The ``finish_reason`` and ``reasoning_tokens`` fields surface
    provider-side stop-reason and reasoning-token-consumption metadata so
    that downstream code (the endorser, the JSONL log, the evaluation
    JSON) can distinguish *budget-clipped* abstains (model ran out of
    tokens on silent internal reasoning) from *genuine* abstains (model
    declined to commit). The values are passed through verbatim from
    each provider — see :data:`BUDGET_FINISH_REASONS` for the canonical
    union of values that signal a budget hit.
    """

    text: str
    provider: str
    model_id: str
    request_id: str | None = None
    wall_time_ms: float = 0.0
    usage: Mapping[str, int] = field(default_factory=dict)
    raw: Mapping[str, Any] | None = None
    """Provider-native response payload, when available, for forensic inspection."""
    finish_reason: str | None = None
    """Provider-side stop reason. OpenAI: ``"stop"`` / ``"length"`` / ...;
    Anthropic: ``"end_turn"`` / ``"max_tokens"`` / ``"stop_sequence"`` / ....
    ``None`` if the provider didn't report one."""
    reasoning_tokens: int | None = None
    """Count of tokens consumed by silent internal reasoning, where the
    provider exposes it (OpenAI: ``usage.completion_tokens_details.reasoning_tokens``).
    ``None`` if not reported."""


# ---- Retry policy --------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential-backoff-with-jitter retry policy.

    Sleep before attempt ``i+1`` (after the ``i``-th transient failure) is

    .. math::
       s_i = b \\cdot f^{\\,i} \\cdot (1 + j \\cdot u)

    where :math:`b` is ``backoff_initial_s``, :math:`f` is ``backoff_factor``,
    :math:`j` is ``jitter``, and :math:`u \\sim U[-1, 1]`.
    """

    max_attempts: int = 4
    backoff_initial_s: float = 0.5
    backoff_factor: float = 2.0
    jitter: float = 0.25

    def sleep_for(self, attempt_index: int, rng: random.Random) -> float:
        """Return the sleep duration in seconds before the next attempt."""
        base = self.backoff_initial_s * (self.backoff_factor**attempt_index)
        jitter_mul = 1.0 + self.jitter * (rng.random() * 2.0 - 1.0)
        return max(0.0, base * jitter_mul)


# ---- Protocol ------------------------------------------------------------


@runtime_checkable
class Provider(Protocol):
    """The structural contract every LLM backend must satisfy."""

    name: str
    model_id: str

    def sample(self, req: SampleRequest) -> SampleResult: ...


# ---- BaseProvider (concrete base for real providers) --------------------


class BaseProvider(ABC):
    """Abstract base providing the retry loop, timing, and logging.

    Subclasses set the class-level :attr:`name`, implement
    :meth:`_sample_once` (one provider call), and implement
    :meth:`_is_transient` (which exceptions warrant a retry).
    """

    name: str = ""  # subclasses override at class level

    def __init__(
        self,
        model_id: str,
        *,
        retry_policy: RetryPolicy | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.model_id = model_id
        self.retry_policy = retry_policy or RetryPolicy()
        self._rng = rng or random.Random()

    # ---- API surface ----

    def sample(self, req: SampleRequest) -> SampleResult:
        """Sample once with retries.

        Raises
        ------
        ProviderSampleError
            If all retry attempts fail with transient errors, or the first
            attempt fails with a non-transient error.
        """
        last_exc: Exception | None = None
        for attempt in range(self.retry_policy.max_attempts):
            try:
                result = self._sample_once(req)
                if attempt > 0:
                    log_event(
                        log,
                        "provider.sample.recovered",
                        provider=self.name,
                        model_id=self.model_id,
                        request_id=req.request_id,
                        attempt=attempt + 1,
                    )
                return result
            except Exception as exc:  # noqa: BLE001 -- intentional broad catch; classified below
                last_exc = exc
                # v0.15.0: EmptyResponseError is always-transient — every
                # subclass provider inherits this classification without
                # needing to override _is_transient. Catches the v0.14.0
                # silent-empty-response failure mode.
                if isinstance(exc, EmptyResponseError):
                    transient = True
                else:
                    transient = self._is_transient(exc)
                log.warning(
                    "provider.sample.error",
                    extra={
                        "provider": self.name,
                        "model_id": self.model_id,
                        "request_id": req.request_id,
                        "attempt": attempt + 1,
                        "transient": transient,
                        "err": str(exc),
                    },
                )
                if not transient:
                    raise ProviderSampleError(
                        f"{self.name} sample failed (non-transient): {exc}"
                    ) from exc
                if attempt + 1 >= self.retry_policy.max_attempts:
                    break  # exhausted -- raise below
                sleep_for = self.retry_policy.sleep_for(attempt, self._rng)
                log_event(
                    log,
                    "provider.sample.retry",
                    provider=self.name,
                    request_id=req.request_id,
                    sleep_s=sleep_for,
                )
                self._sleep(sleep_for)

        raise ProviderSampleError(
            f"{self.name} sample failed after {self.retry_policy.max_attempts} "
            f"attempts: {last_exc}"
        ) from last_exc

    # ---- Subclass extension points ----

    @abstractmethod
    def _sample_once(self, req: SampleRequest) -> SampleResult:
        """One provider call. Raise on any error; the base class classifies it."""

    def _is_transient(self, exc: Exception) -> bool:
        """Return True if ``exc`` should be retried. Default: false."""
        return False

    # ---- Test seam ----

    def _sleep(self, seconds: float) -> None:
        """Indirection over :func:`time.sleep` so tests can avoid real sleeps."""
        time.sleep(seconds)


__all__ = [
    "BaseProvider",
    "Provider",
    "ProviderConfigError",
    "ProviderError",
    "ProviderSampleError",
    "RetryPolicy",
    "SampleRequest",
    "SampleResult",
]
