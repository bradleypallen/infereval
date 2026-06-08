"""Tests for ``infereval.providers.openai.OpenAIProvider`` (SDK mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infereval.providers.base import ProviderConfigError, RetryPolicy, SampleRequest
from infereval.providers.openai import OPENAI_API_KEY_ENV, OpenAIProvider


def _fake_response(
    *,
    text: str = "GOOD",
    prompt_tokens: int = 10,
    completion_tokens: int = 1,
    resp_id: str = "chatcmpl_test_123",
    finish_reason: str = "stop",
    reasoning_tokens: int | None = None,
):
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    if reasoning_tokens is not None:
        usage.completion_tokens_details = SimpleNamespace(
            reasoning_tokens=reasoning_tokens,
        )
    return SimpleNamespace(
        id=resp_id,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, role="assistant"),
                index=0,
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
        model_dump=lambda: {"id": resp_id, "choices": [{"message": {"content": text}}]},
    )


def _provider_with_mock_client(
    create_returns, *, retry_policy: RetryPolicy | None = None
) -> tuple[OpenAIProvider, MagicMock]:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = create_returns
    return (
        OpenAIProvider("gpt-4o", client=mock_client, retry_policy=retry_policy),
        mock_client,
    )


# ---- Configuration --------------------------------------------------------


class TestConfig:
    def test_missing_api_key_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
        with pytest.raises(ProviderConfigError, match="OPENAI_API_KEY"):
            OpenAIProvider("gpt-4o")

    def test_explicit_api_key_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(OPENAI_API_KEY_ENV, raising=False)
        p = OpenAIProvider("gpt-4o", api_key="sk-test")
        assert p.name == "openai"
        assert p.model_id == "gpt-4o"

    def test_sdk_not_installed_raises(self) -> None:
        with (
            patch.dict("sys.modules", {"openai": None}),
            pytest.raises(ProviderConfigError, match="openai SDK not installed"),
        ):
            OpenAIProvider("gpt-4o", api_key="sk-test")


# ---- Request construction -------------------------------------------------


class TestRequestConstruction:
    def test_user_message_only_when_no_system(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q?"))
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["messages"] == [{"role": "user", "content": "Q?"}]
        assert kwargs["max_tokens"] == 1024
        assert kwargs["temperature"] == 1.0

    def test_system_message_prepended(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q?", system="You are an evaluator."))
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["messages"] == [
            {"role": "system", "content": "You are an evaluator."},
            {"role": "user", "content": "Q?"},
        ]

    def test_seed_forwarded(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", seed=42))
        assert client.chat.completions.create.call_args.kwargs["seed"] == 42

    def test_stop_forwarded(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", stop=("###",)))
        assert client.chat.completions.create.call_args.kwargs["stop"] == ["###"]

    def test_top_p_forwarded(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", top_p=0.9))
        assert client.chat.completions.create.call_args.kwargs["top_p"] == 0.9

    def test_gpt5_uses_max_completion_tokens(self) -> None:
        # gpt-5.x and the o-series reject 'max_tokens' as unsupported.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("gpt-5.4", client=mock_client)
        p.sample(SampleRequest(prompt="Q", max_tokens=512))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 512
        assert "max_tokens" not in kwargs

    def test_o4_mini_uses_max_completion_tokens(self) -> None:
        # The o-series reasoning models behave the same way.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("o4-mini", client=mock_client)
        p.sample(SampleRequest(prompt="Q", max_tokens=128))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["max_completion_tokens"] == 128
        assert "max_tokens" not in kwargs

    def test_gpt4o_uses_legacy_max_tokens(self) -> None:
        # Pre-5.x non-reasoning models still expect 'max_tokens'.
        p, client = _provider_with_mock_client(_fake_response())  # uses gpt-4o
        p.sample(SampleRequest(prompt="Q", max_tokens=32))
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["max_tokens"] == 32
        assert "max_completion_tokens" not in kwargs

    # --- Temperature handling for GPT-5+/o-series (Issue #20) ---

    def test_temperature_skipped_for_gpt5(self) -> None:
        # GPT-5.x rejects 'temperature' at any non-default value with 400
        # invalid_request_error. The provider must skip the parameter
        # entirely for these models so the request still goes through.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("gpt-5.5", client=mock_client)
        p.sample(SampleRequest(prompt="Q", temperature=0.0))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_skipped_for_gpt5_4(self) -> None:
        # Same rule applies to the 5.4 generation that's been in the wild
        # for the cross-family experiment.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("gpt-5.4", client=mock_client)
        p.sample(SampleRequest(prompt="Q", temperature=0.7))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_skipped_for_o_series(self) -> None:
        # The o-series reasoning models share the constraint.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("o4-mini", client=mock_client)
        p.sample(SampleRequest(prompt="Q", temperature=0.5))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_skipped_for_openrouter_prefixed_gpt5(self) -> None:
        # The vendor-prefixed model id used by OpenRouter should match.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("openai/gpt-5.5", client=mock_client)
        p.sample(SampleRequest(prompt="Q", temperature=0.0))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_kept_for_gpt4o(self) -> None:
        # Pre-5.x non-reasoning models still accept temperature; the skip
        # must NOT apply (regression guard).
        p, client = _provider_with_mock_client(_fake_response())  # uses gpt-4o
        p.sample(SampleRequest(prompt="Q", temperature=0.3))
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 0.3

    def test_temperature_kept_for_gpt41(self) -> None:
        # GPT-4.1 (the baseline model in the paraphrase-axis experiment)
        # still accepts temperature.
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_response()
        p = OpenAIProvider("gpt-4.1", client=mock_client)
        p.sample(SampleRequest(prompt="Q", temperature=1.0))
        kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert kwargs["temperature"] == 1.0


# ---- Response parsing -----------------------------------------------------


class TestResponseParsing:
    def test_text_extracted(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(text="ABSTAIN"))
        r = p.sample(SampleRequest(prompt="Q"))
        assert r.text == "ABSTAIN"
        assert r.provider == "openai"
        assert r.model_id == "gpt-4o"

    def test_usage_recorded(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(prompt_tokens=100, completion_tokens=5))
        r = p.sample(SampleRequest(prompt="Q"))
        assert r.usage == {"input_tokens": 100, "output_tokens": 5}

    def test_request_id_propagation(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(resp_id="chatcmpl_abc"))
        r1 = p.sample(SampleRequest(prompt="Q"))
        assert r1.request_id == "chatcmpl_abc"

        r2 = p.sample(SampleRequest(prompt="Q", request_id="client-id"))
        assert r2.request_id == "client-id"

    def test_finish_reason_populated(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(finish_reason="stop"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.finish_reason == "stop"

    def test_finish_reason_length_signals_budget_clip(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(finish_reason="length"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.finish_reason == "length"

    def test_reasoning_tokens_from_completion_tokens_details(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(reasoning_tokens=256))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.reasoning_tokens == 256

    def test_reasoning_tokens_none_when_absent(self) -> None:
        # Default response has no completion_tokens_details on usage.
        p, _ = _provider_with_mock_client(_fake_response())
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.reasoning_tokens is None

    def test_empty_content_with_stop_finish_reason_raises(self) -> None:
        """v0.15.0+: empty response body with finish_reason='stop' is
        treated as a silent API failure (likely rate-limit), not as
        success-with-empty-text. The provider raises EmptyResponseError,
        which BaseProvider's retry loop classifies as always-transient
        and retries; after exhausted retries surfaces as
        ProviderSampleError. The v0.14.0 silent-failure bug fix:
        previously this case got parsed as ABSTAIN by the endorsement
        regex, masquerading as a real model abstention. See
        KNOWN_ISSUES_v0.14.0.md."""
        from infereval.providers.base import ProviderSampleError

        resp = SimpleNamespace(
            id="x",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None),
                    index=0,
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=0),
            model_dump=lambda: {},
        )
        # RetryPolicy is a frozen dataclass — construct with reduced
        # max_attempts + zero backoff so the test runs quickly.
        p, _ = _provider_with_mock_client(
            resp,
            retry_policy=RetryPolicy(max_attempts=2, backoff_initial_s=0.0),
        )
        try:
            p.sample(SampleRequest(prompt="Q"))
        except ProviderSampleError as exc:
            assert "empty response body" in str(exc).lower()
        else:
            raise AssertionError(
                "Expected ProviderSampleError from empty response body"
            )

    def test_empty_content_recovers_on_retry(self) -> None:
        """v0.15.0+: when the first call returns an empty body
        (transient OpenRouter rate-limit) and the retry succeeds,
        the SampleResult should carry the real model response — NOT
        the empty placeholder. This is the partial-recovery scenario
        the v0.14.0 silent-failure bug never reached: the retry path
        must actually deliver the recovered text, not just suppress
        the failure."""
        empty_resp = SimpleNamespace(
            id="empty",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None),
                    index=0,
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=0),
            model_dump=lambda: {},
        )
        good_resp = _fake_response(text="GOOD", finish_reason="stop")
        mock_client = MagicMock()
        # First call returns empty body (triggers EmptyResponseError);
        # second call returns a clean GOOD response.
        mock_client.chat.completions.create.side_effect = [empty_resp, good_resp]
        p = OpenAIProvider(
            "gpt-4o",
            client=mock_client,
            retry_policy=RetryPolicy(max_attempts=3, backoff_initial_s=0.0),
        )
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.text == "GOOD"
        assert result.finish_reason == "stop"
        # And the provider should have been called exactly twice — once
        # for the failed empty body, once for the successful retry.
        assert mock_client.chat.completions.create.call_count == 2

    def test_empty_content_with_length_finish_reason_returns_empty(self) -> None:
        """v0.15.0+: empty response body with finish_reason='length' is
        a *real* budget-clipped model response, not an API failure.
        Returns empty text (existing v0.14.0 behavior); endorsement
        handles via the budget-clipped detection path."""
        resp = SimpleNamespace(
            id="x",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None),
                    index=0,
                    finish_reason="length",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=0),
            model_dump=lambda: {},
        )
        p, _ = _provider_with_mock_client(resp)
        r = p.sample(SampleRequest(prompt="Q"))
        assert r.text == ""
        assert r.finish_reason == "length"


# ---- Transient classification ---------------------------------------------


class TestTransientClassification:
    def test_rate_limit_is_transient(self) -> None:
        import openai

        p = OpenAIProvider("gpt-4o", api_key="sk-test")
        exc = openai.RateLimitError.__new__(openai.RateLimitError)
        assert p._is_transient(exc)

    def test_value_error_is_not_transient(self) -> None:
        p = OpenAIProvider("gpt-4o", api_key="sk-test")
        assert not p._is_transient(ValueError("nope"))
