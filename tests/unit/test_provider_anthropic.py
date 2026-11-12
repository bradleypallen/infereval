"""Tests for ``infereval.providers.anthropic.AnthropicProvider`` (SDK mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from infereval.providers.anthropic import ANTHROPIC_API_KEY_ENV, AnthropicProvider
from infereval.providers.base import ProviderConfigError, RetryPolicy, SampleRequest


def _fake_response(
    *,
    text: str = "GOOD",
    input_tokens: int = 7,
    output_tokens: int = 1,
    resp_id: str = "msg_test_123",
    stop_reason: str | None = "end_turn",
    thinking_tokens: int | None = None,
):
    """A SimpleNamespace mimicking the bits of an anthropic.types.Message we read."""
    usage_kwargs: dict[str, object] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if thinking_tokens is not None:
        usage_kwargs["thinking_tokens"] = thinking_tokens
    return SimpleNamespace(
        id=resp_id,
        content=[SimpleNamespace(text=text, type="text")],
        usage=SimpleNamespace(**usage_kwargs),
        stop_reason=stop_reason,
        model_dump=lambda: {"id": resp_id, "content": [{"text": text}]},
    )


def _provider_with_mock_client(
    create_returns, *, retry_policy: RetryPolicy | None = None
) -> tuple[AnthropicProvider, MagicMock]:
    """Build an AnthropicProvider backed by a MagicMock client.

    Pinned to the SDK 0.x ``kwarg`` sampling route so request-shape tests do
    not depend on the installed SDK; ``TestSamplingRoutes`` covers the others.
    """
    mock_client = MagicMock()
    mock_client.messages.create.return_value = create_returns
    return (
        AnthropicProvider(
            "claude-haiku-4-5-20251001",
            client=mock_client,
            retry_policy=retry_policy,
            sampling_route="kwarg",
        ),
        mock_client,
    )


# ---- Configuration --------------------------------------------------------


class TestConfig:
    def test_missing_api_key_raises_config_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)
        with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
            AnthropicProvider("claude-haiku-4-5-20251001")

    def test_explicit_api_key_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ANTHROPIC_API_KEY_ENV, raising=False)
        # Construct with explicit api_key; should not raise. We verify the client is built
        # by checking that the instance exists.
        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-ant-test")
        assert p.name == "anthropic"
        assert p.model_id == "claude-haiku-4-5-20251001"

    def test_uses_env_when_no_explicit_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ANTHROPIC_API_KEY_ENV, "sk-ant-from-env")
        p = AnthropicProvider("claude-haiku-4-5-20251001")
        assert p.name == "anthropic"

    def test_sdk_not_installed_raises_config_error(self) -> None:
        # Simulate the SDK being unavailable
        with (
            patch.dict("sys.modules", {"anthropic": None}),
            pytest.raises(ProviderConfigError, match="anthropic SDK not installed"),
        ):
            AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")


# ---- Request construction -------------------------------------------------


class TestRequestConstruction:
    def test_minimal_request_shape(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Premises: X. Conclusion: Y. Verdict:"))
        client.messages.create.assert_called_once()
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-haiku-4-5-20251001"
        assert kwargs["max_tokens"] == 1024
        assert kwargs["temperature"] == 1.0
        assert kwargs["messages"] == [
            {"role": "user", "content": "Premises: X. Conclusion: Y. Verdict:"}
        ]
        # No system / stop / top_p in minimal request
        assert "system" not in kwargs
        assert "stop_sequences" not in kwargs
        assert "top_p" not in kwargs

    def test_system_message_passed_top_level(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", system="You are an evaluator."))
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["system"] == "You are an evaluator."

    def test_stop_sequences_translated(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", stop=("\n\n", "###")))
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["stop_sequences"] == ["\n\n", "###"]

    def test_top_p_forwarded(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", top_p=0.9))
        assert client.messages.create.call_args.kwargs["top_p"] == 0.9

    def test_seed_emits_warning_once(self, caplog: pytest.LogCaptureFixture) -> None:
        p, _ = _provider_with_mock_client(_fake_response())
        with caplog.at_level("WARNING", logger="infereval.providers.anthropic"):
            p.sample(SampleRequest(prompt="Q", seed=42))
            p.sample(SampleRequest(prompt="Q2", seed=42))
        warnings = [r for r in caplog.records if "seed_ignored" in r.getMessage()]
        assert len(warnings) == 1, "seed warning should be emitted at most once"

    def test_seed_not_passed_to_anthropic(self) -> None:
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", seed=42))
        assert "seed" not in client.messages.create.call_args.kwargs

    def test_temperature_skipped_for_claude_opus_4_7(self) -> None:
        # Opus 4.7 rejects 'temperature' as a 400 invalid_request_error.
        # The provider should detect this and skip the parameter entirely.
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _fake_response()
        p = AnthropicProvider("claude-opus-4-7", client=mock_client)
        p.sample(SampleRequest(prompt="Q", temperature=0.5))
        kwargs = mock_client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs

    def test_temperature_kept_for_haiku(self) -> None:
        # Haiku still accepts temperature; the skip should not apply.
        p, client = _provider_with_mock_client(_fake_response())
        p.sample(SampleRequest(prompt="Q", temperature=0.7))
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["temperature"] == 0.7


# ---- Sampling parameters across SDK generations -----------------------------


def _routed_provider(
    route: str, model: str = "claude-haiku-4-5-20251001"
) -> tuple[AnthropicProvider, MagicMock]:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_response()
    return AnthropicProvider(model, client=mock_client, sampling_route=route), mock_client  # type: ignore[arg-type]


class TestSamplingRoutes:
    def test_kwarg_route_passes_sampling_as_kwargs(self) -> None:
        p, client = _routed_provider("kwarg")
        p.sample(SampleRequest(prompt="Q", temperature=0.3, top_p=0.9))
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["temperature"] == 0.3
        assert kwargs["top_p"] == 0.9
        assert "extra_body" not in kwargs

    def test_extra_body_route_moves_sampling_into_extra_body(self) -> None:
        # anthropic 1.x: kwargs removed from messages.create, API 2023-06-01 still accepts them.
        p, client = _routed_provider("extra_body")
        p.sample(SampleRequest(prompt="Q", temperature=0.3, top_p=0.9))
        kwargs = client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs and "top_p" not in kwargs
        assert kwargs["extra_body"] == {"temperature": 0.3, "top_p": 0.9}

    def test_omit_route_default_sampling_sends_nothing(self) -> None:
        # anthropic 2.x / API 2026-10-21: omitting == the default temperature 1.0.
        p, client = _routed_provider("omit")
        p.sample(SampleRequest(prompt="Q", temperature=1.0))
        kwargs = client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs and "top_p" not in kwargs
        assert "extra_body" not in kwargs
        assert kwargs["max_tokens"] == 1024

    @pytest.mark.parametrize("req_kwargs", [{"temperature": 0.2}, {"top_p": 0.9}])
    def test_omit_route_non_default_sampling_raises_config_error(self, req_kwargs) -> None:
        # Must surface as a config error before any API call, not as a
        # non-transient sample failure that the endorser records as ABSTAIN.
        p, client = _routed_provider("omit")
        with pytest.raises(ProviderConfigError, match="2026-10-21"):
            p.sample(SampleRequest(prompt="Q", **req_kwargs))
        client.messages.create.assert_not_called()

    @pytest.mark.parametrize("route", ["kwarg", "extra_body", "omit"])
    @pytest.mark.parametrize(
        "model", ["claude-opus-4-7", "claude-opus-4-8", "claude-opus-5-5", "claude-sonnet-5-5",
                  "claude-haiku-5-5", "claude-fable-5-2"],
    )
    def test_models_that_reject_sampling_never_get_it(self, route: str, model: str) -> None:
        p, client = _routed_provider(route, model)
        p.sample(SampleRequest(prompt="Q", temperature=0.5, top_p=0.9))
        kwargs = client.messages.create.call_args.kwargs
        assert "temperature" not in kwargs and "top_p" not in kwargs
        assert "extra_body" not in kwargs

    def test_ignored_sampling_warns_once(self, caplog: pytest.LogCaptureFixture) -> None:
        p, _ = _routed_provider("kwarg", "claude-opus-4-7")
        with caplog.at_level("WARNING", logger="infereval.providers.anthropic"):
            p.sample(SampleRequest(prompt="Q", temperature=0.5))
            p.sample(SampleRequest(prompt="Q2", temperature=0.5))
        assert sum("sampling_ignored" in r.getMessage() for r in caplog.records) == 1


class TestSamplingRouteDetection:
    @pytest.mark.parametrize(
        ("sdk_major", "api_version", "expected"),
        [
            (0, "2023-06-01", "kwarg"),
            (None, None, "kwarg"),
            (1, "2023-06-01", "extra_body"),
            (1, None, "extra_body"),
            (2, "2026-10-21", "omit"),
            (2, None, "omit"),
            (1, "2026-10-21", "omit"),  # version overridden upward on a 1.x client
            (2, "2023-06-01", "extra_body"),  # version pinned back on a 2.x client
        ],
    )
    def test_route(self, sdk_major, api_version, expected) -> None:
        from infereval.providers import anthropic as mod

        client = SimpleNamespace(
            default_headers={} if api_version is None else {"anthropic-version": api_version}
        )
        with patch.object(mod, "_sdk_major", return_value=sdk_major):
            assert mod._detect_sampling_route(client) == expected


class TestInstalledSdkCompatibility:
    """Regression: the provider's call must bind to the *installed* SDK's
    ``Messages.create`` signature (SDK 1.x+ dropped ``temperature``, and every
    call failed with a TypeError that was recorded as ABSTAIN)."""

    @pytest.mark.parametrize("temperature", [1.0, 0.5])
    def test_create_kwargs_bind_to_installed_signature(self, temperature: float) -> None:
        import inspect

        anthropic = pytest.importorskip("anthropic")
        from anthropic.resources.messages import Messages

        sig = inspect.signature(Messages.create)
        client = anthropic.Anthropic(api_key="test-key")
        p = AnthropicProvider("claude-haiku-4-5-20251001", client=client)
        if temperature != 1.0 and p.sampling_route == "omit":
            with pytest.raises(ProviderConfigError):
                p.sample(SampleRequest(prompt="Q", temperature=temperature))
            return

        def fake_create(**kwargs):
            sig.bind(client.messages, **kwargs)  # TypeError on an unknown kwarg
            return _fake_response()

        with patch.object(client.messages, "create", side_effect=fake_create) as create:
            p.sample(SampleRequest(prompt="Q", system="S", temperature=temperature, stop=("x",)))
        create.assert_called_once()


# ---- Response parsing -----------------------------------------------------


class TestResponseParsing:
    def test_text_extracted_from_blocks(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(text="BAD"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.text == "BAD"
        assert result.provider == "anthropic"
        assert result.model_id == "claude-haiku-4-5-20251001"

    def test_usage_recorded(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(input_tokens=42, output_tokens=3))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.usage == {"input_tokens": 42, "output_tokens": 3}

    def test_wall_time_recorded(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response())
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.wall_time_ms >= 0.0

    def test_request_id_from_response_when_not_set_on_req(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(resp_id="msg_aaa"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.request_id == "msg_aaa"

    def test_req_request_id_overrides_response_id(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(resp_id="msg_bbb"))
        result = p.sample(SampleRequest(prompt="Q", request_id="client-correlation-id"))
        assert result.request_id == "client-correlation-id"

    def test_raw_payload_attached(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(text="GOOD"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.raw is not None
        assert "id" in result.raw

    def test_finish_reason_populated_from_stop_reason(self) -> None:
        p, _ = _provider_with_mock_client(_fake_response(stop_reason="end_turn"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.finish_reason == "end_turn"

    def test_finish_reason_max_tokens_signals_budget_clip(self) -> None:
        # When Anthropic truncates by max_tokens, the field is the canonical
        # "budget hit" indicator for downstream code.
        p, _ = _provider_with_mock_client(_fake_response(stop_reason="max_tokens"))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.finish_reason == "max_tokens"

    def test_reasoning_tokens_from_thinking_tokens(self) -> None:
        # Extended-thinking models expose thinking_tokens on usage.
        p, _ = _provider_with_mock_client(_fake_response(thinking_tokens=128))
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.reasoning_tokens == 128

    def test_reasoning_tokens_none_when_absent(self) -> None:
        # Default usage object has no thinking_tokens field; should be None.
        p, _ = _provider_with_mock_client(_fake_response())
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.reasoning_tokens is None

    def test_multi_block_content_concatenated(self) -> None:
        resp = SimpleNamespace(
            id="msg_multi",
            content=[
                SimpleNamespace(text="GO", type="text"),
                SimpleNamespace(text="OD", type="text"),
            ],
            usage=SimpleNamespace(input_tokens=5, output_tokens=2),
            model_dump=lambda: {"id": "msg_multi"},
        )
        p, _ = _provider_with_mock_client(resp)
        result = p.sample(SampleRequest(prompt="Q"))
        assert result.text == "GOOD"

    def test_empty_content_with_end_turn_raises(self) -> None:
        """v0.15.0+: empty response body with stop_reason='end_turn' is
        treated as a silent API failure (rate-limit or transient provider
        failure), not as success-with-empty-text. The provider raises
        EmptyResponseError, which BaseProvider's retry loop classifies
        as always-transient and retries; after exhausted retries surfaces
        as ProviderSampleError. The v0.14.0 silent-failure bug fix — see
        KNOWN_ISSUES_v0.14.0.md."""
        from infereval.providers.base import ProviderSampleError

        resp = SimpleNamespace(
            id="x",
            content=[SimpleNamespace(text="", type="text")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=0),
            stop_reason="end_turn",
            model_dump=lambda: {},
        )
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

    def test_empty_content_with_max_tokens_returns_empty(self) -> None:
        """v0.15.0+: empty response body with stop_reason='max_tokens' is
        a *real* budget-clipped model response, not an API failure.
        Returns empty text (existing v0.14.0 behavior); endorsement
        handles via the budget-clipped detection path."""
        resp = SimpleNamespace(
            id="x",
            content=[SimpleNamespace(text="", type="text")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=0),
            stop_reason="max_tokens",
            model_dump=lambda: {},
        )
        p, _ = _provider_with_mock_client(resp)
        r = p.sample(SampleRequest(prompt="Q"))
        assert r.text == ""
        assert r.finish_reason == "max_tokens"


# ---- Transient classification ---------------------------------------------


class TestTransientClassification:
    def test_rate_limit_is_transient(self) -> None:
        import anthropic

        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        # Use the real class, no body required since _is_transient only does isinstance
        exc = anthropic.RateLimitError.__new__(anthropic.RateLimitError)
        assert p._is_transient(exc)

    def test_value_error_is_not_transient(self) -> None:
        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        assert not p._is_transient(ValueError("nope"))

    def test_overloaded_529_is_transient(self) -> None:
        # 529 OverloadedError is the symptom we saw on long Opus runs:
        # Anthropic returns ``{"type": "overloaded_error", ...}`` and the
        # framework must classify it as transient so RetryPolicy can back
        # off and retry instead of failing the sample outright.
        import anthropic

        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
        # ``status_code`` is what the SDK populates on real errors; we set
        # it directly because we are not exercising __init__.
        exc.status_code = 529
        assert p._is_transient(exc)

    def test_service_unavailable_503_is_transient(self) -> None:
        import anthropic

        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
        exc.status_code = 503
        assert p._is_transient(exc)

    def test_deadline_exceeded_504_is_transient(self) -> None:
        import anthropic

        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
        exc.status_code = 504
        assert p._is_transient(exc)

    def test_bad_request_400_is_not_transient(self) -> None:
        # 400 BadRequest must remain non-transient: retrying a malformed
        # request would just burn budget for the same failure.
        import anthropic

        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        exc = anthropic.APIStatusError.__new__(anthropic.APIStatusError)
        exc.status_code = 400
        assert not p._is_transient(exc)

    def test_overloaded_real_subclass_is_transient(self) -> None:
        # Sanity check against the SDK's real OverloadedError subclass
        # (lives under anthropic._exceptions in 0.10x). If a future SDK
        # rev moves it, we still classify by status_code on the base.
        from anthropic._exceptions import OverloadedError  # type: ignore[import-untyped]

        p = AnthropicProvider("claude-haiku-4-5-20251001", api_key="sk-test")
        exc = OverloadedError.__new__(OverloadedError)
        exc.status_code = 529
        assert p._is_transient(exc)
