"""OpenAI provider (Chat Completions API).

Wraps :class:`openai.OpenAI` against the Chat Completions endpoint. Chat
Completions is chosen over the newer Responses API for breadth of model
coverage across OpenRouter — :class:`infereval.providers.openrouter.OpenRouterProvider`
inherits from this class with only a base-URL swap.

The ``openai`` SDK is an optional dependency: ``pip install 'infereval[openai]'``.
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
    import openai as _openai_sdk

log = logging.getLogger(__name__)

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _uses_max_completion_tokens(model_id: str) -> bool:
    """Detect models that require ``max_completion_tokens`` instead of ``max_tokens``.

    Applies to GPT-5.x and the o-series reasoning models (o1, o3, o4-*). The
    same rule applies via OpenRouter when the upstream is OpenAI; for other
    OpenRouter vendors (deepseek/qwen/etc) the legacy ``max_tokens`` is fine.
    """
    if not model_id:
        return False
    # Strip OpenRouter vendor prefix so "openai/gpt-5.4" and "gpt-5.4" both match.
    bare = model_id.split("/", 1)[-1].lower()
    # gpt-5* and gpt-6* (defensive for future generations).
    for n in range(5, 10):
        if bare.startswith(f"gpt-{n}"):
            return True
    # o-series reasoning models: o1, o1-pro, o3, o3-mini, o4-mini, ...
    return bare.startswith(("o1", "o3", "o4", "o5"))


def _rejects_temperature(model_id: str) -> bool:
    """Detect OpenAI models that reject any ``temperature`` other than the default 1.

    As of 2026-05, GPT-5.x and the o-series reasoning models (o1, o3, o4-*)
    return ``400 invalid_request_error`` if ``temperature`` is supplied at
    any value other than 1.0. The framework's default decoding params use
    ``temperature=1.0``, but evaluations frequently set 0.0 for
    determinism; we strip the parameter for these models so the rest of
    the API call still goes through. The set matches
    :func:`_uses_max_completion_tokens` — same generation of models.
    """
    return _uses_max_completion_tokens(model_id)


class OpenAIProvider(BaseProvider):
    """OpenAI Chat Completions backend.

    Subclasses may override the class attributes :attr:`name`,
    :attr:`DEFAULT_BASE_URL`, and :attr:`API_KEY_ENV` to target
    OpenAI-API-compatible services (see :class:`OpenRouterProvider`).
    """

    name = "openai"
    DEFAULT_BASE_URL = OPENAI_DEFAULT_BASE_URL
    API_KEY_ENV = OPENAI_API_KEY_ENV

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
        client: _openai_sdk.OpenAI | None = None,
        retry_policy: RetryPolicy | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(model_id, retry_policy=retry_policy, rng=rng)
        self._client = (
            client
            if client is not None
            else self._build_client(api_key, base_url, default_headers)
        )

    @classmethod
    def _build_client(
        cls,
        api_key: str | None,
        base_url: str | None,
        default_headers: dict[str, str] | None,
    ) -> _openai_sdk.OpenAI:
        try:
            import openai
        except ImportError as exc:
            raise ProviderConfigError(
                "openai SDK not installed. Install with: pip install 'infereval[openai]'"
            ) from exc
        key = api_key if api_key is not None else os.environ.get(cls.API_KEY_ENV)
        if not key:
            raise ProviderConfigError(
                f"{cls.API_KEY_ENV} not set and no api_key provided"
            )
        return openai.OpenAI(
            api_key=key,
            base_url=base_url if base_url is not None else cls.DEFAULT_BASE_URL,
            default_headers=default_headers or None,
        )

    def _sample_once(self, req: SampleRequest) -> SampleResult:
        messages: list[dict[str, str]] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        kwargs: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
        }
        # GPT-5.x and the o-series reasoning models (o1, o3, o4-...) reject
        # any temperature other than the default 1.0 -- skip the parameter
        # for those models so the rest of the request still goes through.
        if not _rejects_temperature(self.model_id):
            kwargs["temperature"] = req.temperature
        # The same generation requires ``max_completion_tokens`` and rejects
        # the legacy ``max_tokens`` param.
        if _uses_max_completion_tokens(self.model_id):
            kwargs["max_completion_tokens"] = req.max_tokens
        else:
            kwargs["max_tokens"] = req.max_tokens
        if req.top_p is not None:
            kwargs["top_p"] = req.top_p
        if req.seed is not None:
            kwargs["seed"] = req.seed
        if req.stop:
            kwargs["stop"] = list(req.stop)

        start = time.monotonic()
        response = self._client.chat.completions.create(**kwargs)
        wall_time_ms = (time.monotonic() - start) * 1000.0

        text = ""
        finish_reason: str | None = None
        choices = getattr(response, "choices", None) or []
        if choices:
            choice = choices[0]
            msg = getattr(choice, "message", None)
            text = (getattr(msg, "content", None) or "") if msg is not None else ""
            fr = getattr(choice, "finish_reason", None)
            if isinstance(fr, str):
                finish_reason = fr

        # v0.15.0: raise EmptyResponseError if the response body is empty
        # or whitespace-only — but ONLY when finish_reason isn't "length"
        # (a budget-clipped response is a *real* model behavior, not an
        # API failure; the endorsement code already handles that case via
        # _BudgetClippedProvider-style detection). The empty-response case
        # this catches: HTTP 200 with no content choice, which OpenRouter
        # was returning under rate-limit pressure in the v0.14.0 silent-
        # failure incident. Triggers BaseProvider's always-transient retry
        # path; if all retries fail, surfaces as ProviderSampleError that
        # the endorser records with `provider_error` set.
        if not text.strip() and finish_reason != "length":
            raise EmptyResponseError(
                f"{self.name} returned empty response body "
                f"(finish_reason={finish_reason!r}, model={self.model_id!r}). "
                f"Likely a rate-limit or transient provider failure that "
                f"returned HTTP 200 with no content."
            )

        usage_obj = getattr(response, "usage", None)
        usage: dict[str, int] = {}
        reasoning_tokens: int | None = None
        if usage_obj is not None:
            in_tok = getattr(usage_obj, "prompt_tokens", None)
            out_tok = getattr(usage_obj, "completion_tokens", None)
            if isinstance(in_tok, int):
                usage["input_tokens"] = in_tok
            if isinstance(out_tok, int):
                usage["output_tokens"] = out_tok
            # Reasoning models expose this as a nested field on usage.
            ctd = getattr(usage_obj, "completion_tokens_details", None)
            if ctd is not None:
                rt = getattr(ctd, "reasoning_tokens", None)
                if isinstance(rt, int):
                    reasoning_tokens = rt

        raw: dict[str, Any] | None = None
        if hasattr(response, "model_dump"):
            try:
                raw = response.model_dump()
            except Exception:  # noqa: BLE001
                raw = None

        provider_request_id = getattr(response, "id", None)
        request_id = req.request_id if req.request_id is not None else provider_request_id

        log_event(
            log,
            f"provider.{self.name}.sample",
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

    def _is_transient(self, exc: Exception) -> bool:
        try:
            import openai
        except ImportError:
            return False
        transient_types: tuple[type[Exception], ...] = (
            openai.RateLimitError,
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
        )
        return isinstance(exc, transient_types)


__all__ = ["OPENAI_API_KEY_ENV", "OPENAI_DEFAULT_BASE_URL", "OpenAIProvider"]
