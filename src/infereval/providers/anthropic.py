"""Anthropic Claude provider.

Wraps :class:`anthropic.Anthropic` and its Messages API. The ``anthropic``
SDK is an optional dependency: ``pip install 'infereval[anthropic]'``.

Anthropic's API does not honor a ``seed`` parameter. If a seed is supplied
in :class:`SampleRequest`, we log a one-time warning and proceed; the seed
is recorded in the evaluation file as supplied so analysts can see what was
intended, even though the model did not act on it.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import TYPE_CHECKING, Any

from infereval.logging_setup import log_event

from .base import (
    BaseProvider,
    EmptyResponseError,
    ProviderConfigError,
    RetryPolicy,
    SampleRequest,
    SampleResult,
)

if TYPE_CHECKING:
    import anthropic

log = logging.getLogger(__name__)

ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"


def _rejects_temperature(model_id: str) -> bool:
    """Detect Claude models that reject the ``temperature`` parameter outright.

    As of 2026-05, ``claude-opus-4-7`` (and later Opus versions, presumably)
    deprecate ``temperature`` and return a 400 if it is supplied. Sonnet
    and Haiku still accept it.
    """
    if not model_id:
        return False
    bare = model_id.split("/", 1)[-1].lower()
    # claude-opus-4-7, claude-opus-4-8, etc.
    if bare.startswith(("claude-opus-4-7", "claude-opus-4.7")):
        return True
    # Generation-agnostic: claude-opus-5+ likely keeps the same posture.
    return any(bare.startswith(f"claude-opus-{n}") for n in range(5, 10))


class AnthropicProvider(BaseProvider):
    """Anthropic Claude backend (Messages API)."""

    name = "anthropic"

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        client: anthropic.Anthropic | None = None,
        retry_policy: RetryPolicy | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(model_id, retry_policy=retry_policy, rng=rng)
        self._client = client if client is not None else self._build_client(api_key)
        self._seed_warning_emitted = False

    @staticmethod
    def _build_client(api_key: str | None) -> anthropic.Anthropic:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderConfigError(
                "anthropic SDK not installed. Install with: pip install 'infereval[anthropic]'"
            ) from exc
        key = api_key if api_key is not None else os.environ.get(ANTHROPIC_API_KEY_ENV)
        if not key:
            raise ProviderConfigError(
                f"{ANTHROPIC_API_KEY_ENV} not set and no api_key provided"
            )
        return anthropic.Anthropic(api_key=key)

    def _sample_once(self, req: SampleRequest) -> SampleResult:
        if req.seed is not None and not self._seed_warning_emitted:
            log.warning(
                "provider.anthropic.seed_ignored",
                extra={
                    "model_id": self.model_id,
                    "reason": (
                        "Anthropic API does not honor 'seed'; recording the "
                        "requested value but the model did not use it"
                    ),
                },
            )
            self._seed_warning_emitted = True

        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": req.max_tokens,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        # Claude Opus 4.7+ has deprecated the ``temperature`` parameter and
        # rejects requests that include it. Skip it for those models;
        # everything else still accepts it.
        if not _rejects_temperature(self.model_id):
            kwargs["temperature"] = req.temperature
        if req.top_p is not None:
            kwargs["top_p"] = req.top_p
        if req.system:
            kwargs["system"] = req.system
        if req.stop:
            kwargs["stop_sequences"] = list(req.stop)

        start = time.monotonic()
        response = self._client.messages.create(**kwargs)
        wall_time_ms = (time.monotonic() - start) * 1000.0

        text_parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            block_text = getattr(block, "text", None)
            if isinstance(block_text, str):
                text_parts.append(block_text)
        text = "".join(text_parts)

        # Anthropic's stop_reason vocabulary: "end_turn", "max_tokens",
        # "stop_sequence", "tool_use", "pause_turn", "refusal". Read it
        # here (before the empty-response guard) so we can distinguish a
        # budget-clipped real response (stop_reason="max_tokens") from a
        # silent API failure.
        finish_reason = getattr(response, "stop_reason", None)
        if not isinstance(finish_reason, str):
            finish_reason = None

        # v0.15.0: raise EmptyResponseError if the response body is empty
        # or whitespace-only — but ONLY when stop_reason isn't "max_tokens"
        # (a budget-clipped response is real model behavior, not an API
        # failure). Triggers BaseProvider's always-transient retry path;
        # if all retries fail, surfaces as ProviderSampleError that the
        # endorser records with `provider_error` set. See
        # KNOWN_ISSUES_v0.14.0.md for the v0.14.0 silent-failure context.
        if not text.strip() and finish_reason != "max_tokens":
            raise EmptyResponseError(
                f"{self.name} returned empty response body "
                f"(stop_reason={finish_reason!r}, model={self.model_id!r}). "
                f"Likely a rate-limit or transient provider failure that "
                f"returned a content-less response."
            )

        usage_obj = getattr(response, "usage", None)
        usage: dict[str, int] = {}
        reasoning_tokens: int | None = None
        if usage_obj is not None:
            in_tok = getattr(usage_obj, "input_tokens", None)
            out_tok = getattr(usage_obj, "output_tokens", None)
            if isinstance(in_tok, int):
                usage["input_tokens"] = in_tok
            if isinstance(out_tok, int):
                usage["output_tokens"] = out_tok
            # Anthropic's extended-thinking models expose a ``thinking_tokens``
            # subfield in some SDK versions; fall back to None when absent.
            think_tok = getattr(usage_obj, "thinking_tokens", None)
            if isinstance(think_tok, int):
                reasoning_tokens = think_tok

        raw: dict[str, Any] | None = None
        if hasattr(response, "model_dump"):
            try:
                raw = response.model_dump()
            except Exception:  # noqa: BLE001 -- raw is best-effort, never fatal
                raw = None

        provider_request_id = getattr(response, "id", None)
        request_id = req.request_id if req.request_id is not None else provider_request_id

        log_event(
            log,
            "provider.anthropic.sample",
            model_id=self.model_id,
            request_id=request_id,
            wall_time_ms=wall_time_ms,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            finish_reason=finish_reason,
            reasoning_tokens=reasoning_tokens,
        )

        return SampleResult(
            text=text,
            provider=self.name,
            model_id=self.model_id,
            request_id=request_id,
            wall_time_ms=wall_time_ms,
            usage=usage,
            raw=raw,
            finish_reason=finish_reason,
            reasoning_tokens=reasoning_tokens,
        )

    # HTTP status codes that should be retried as transient server-side
    # capacity problems. 503 ServiceUnavailable, 504 DeadlineExceeded, and
    # 529 Overloaded are all classes of "the server is busy, try again";
    # the corresponding Anthropic SDK subclasses (``ServiceUnavailableError``,
    # ``DeadlineExceededError``, ``OverloadedError``) live under
    # ``anthropic._exceptions`` in current SDKs and are not exported at
    # the top-level namespace, so we match by status code on the public
    # ``APIStatusError`` base class.
    _TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({503, 504, 529})

    def _is_transient(self, exc: Exception) -> bool:
        try:
            import anthropic
        except ImportError:
            return False
        transient_types: tuple[type[Exception], ...] = (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.InternalServerError,
        )
        if isinstance(exc, transient_types):
            return True
        if isinstance(exc, anthropic.APIStatusError):
            status = getattr(exc, "status_code", None)
            if isinstance(status, int) and status in self._TRANSIENT_STATUS_CODES:
                return True
        return False


__all__ = ["ANTHROPIC_API_KEY_ENV", "AnthropicProvider"]
