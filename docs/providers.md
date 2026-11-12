# Providers

The framework supports four providers out of the box: **Anthropic**, **OpenAI**, **OpenRouter**, and **mock** (`ScriptedProvider` for tests, `ReplayProvider` for deterministic replay against a JSONL fixture).

This page is the operational reference for the three real providers — credentials, model id conventions, and the per-provider quirks that have actually bitten us.

## Quick reference

| Provider | API key env var | `pip install` extras | Best for |
|---|---|---|---|
| `anthropic` | `ANTHROPIC_API_KEY` | `infereval[anthropic]` | Claude models (Opus, Sonnet, Haiku families). Messages API. |
| `openai` | `OPENAI_API_KEY` | `infereval[openai]` | OpenAI models. Chat Completions API. |
| `openrouter` | `OPENROUTER_API_KEY` | `infereval[openai]` (shared SDK) | DeepSeek, Mistral, Llama, Qwen, and any other model OpenRouter aggregates. Also Anthropic / OpenAI models if you want a unified billing flow. |
| `mock` | — | (always present) | Tests; the `--replay-from` flow for deterministic CI / demo runs. |

## Anthropic

```
pip install 'infereval[anthropic]'
export ANTHROPIC_API_KEY=sk-ant-...
infereval evaluate bench.json \
    --provider anthropic \
    --model claude-haiku-4-5-20251001 \
    --output eta.json --n-samples 5 --log run.jsonl
```

Model id conventions (as of 2026-05): `claude-haiku-4-5-20251001`, `claude-sonnet-4-5-20250929`, `claude-opus-4-7-20260201`, plus dated variants. The shorter aliases (`claude-haiku-4-5`, `claude-sonnet-4-5`, `claude-opus-4-7`, etc.) also work and point at the latest version of each model line. Opus 4.7+ engages extended thinking and benefits from a larger `--max-tokens` cap (the framework default of 1024 handles it; bump to 2048-4096 if you observe `parse_status: budget_clipped`). The recorded fixture filenames in `experiments/results/stop_sign/` use the human shorthand `claude-opus-4.7-…` (with a dot) — that's a filename convention, not an Anthropic model id; the actual id sent to the API is always the dashed form.

### Quirks

- **`seed` is ignored.** Anthropic's Messages API does not honor a `seed` parameter. If you supply one, the framework records it in `Evaluation.model.params.seed` (so you can see what was requested) and emits a one-time warning on the `infereval.providers.anthropic` logger: `provider.anthropic.seed_ignored`. The seed has no effect on the model's output. A lower `temperature` is the closest approximation of determinism, where the model and SDK can still send it (next item).
- **`temperature` / `top_p` depend on the SDK and the model.** The provider picks a route at construction time and logs it as `provider.anthropic.sampling_route`; each sample's log event records `sampling_route` and `sampling_sent`.

  | Installed `anthropic` SDK | API version it sends | How sampling is sent |
  |---|---|---|
  | 0.x | `2023-06-01` | keyword arguments (as before) |
  | 1.x | `2023-06-01` | `extra_body` (1.x removed the keyword arguments) |
  | 2.x and later | `2026-10-21` | not sent: that API version rejects them on every model, even `temperature=1` |

  On the 2.x route the default (`temperature=1.0`, no `top_p`) is omitted, which samples identically. A non-default value raises `ProviderConfigError` before any API call. Install `'anthropic<2'` if a run needs one. Models that don't accept non-default sampling (Opus 4.7/4.8, the Claude 5 generation, Fable, Mythos) never get these parameters whatever the SDK; a non-default request logs one `provider.anthropic.sampling_ignored` warning. Claude 4.6-and-earlier models such as Haiku 4.5 still honour them on the 0.x and 1.x routes.
- **`stop` sequences** are passed through as `stop_sequences=[...]`. The default-v1 verification prompt doesn't need them.
- **Per-call cost is small** for typical evaluations: each sample is ~80 input tokens + ~6 output tokens. A 4-item × 5-sample run is ~$0.001 on Haiku.

### Recommended defaults

```python
EndorsementConfig(n_samples=5)
ProviderParams(temperature=1.0, max_tokens=1024)   # framework default; works on every SDK route
```

The framework defaults to `max_tokens=1024` at both the Python API and the CLI (`--max-tokens 1024`), which is sufficient for Haiku, Sonnet, and Opus on the `default-v1` prompt (Opus 4.7+ engages extended thinking, which consumes part of the budget). Older Anthropic models emit only a handful of tokens for a one-word verdict regardless of this cap.

## OpenAI

```
pip install 'infereval[openai]'
export OPENAI_API_KEY=sk-...
infereval evaluate bench.json \
    --provider openai \
    --model gpt-4.1 \
    --output eta.json --n-samples 5 --log run.jsonl
```

Model id conventions: `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-5`, `gpt-5-mini`, etc., plus dated variants (`gpt-4.1-2025-04-14`, …). Reasoning-family models (`o1`, `o3`, `o4-mini`) work but consume tokens silently — see the reasoning-tokens caveat below.

### Quirks

- **`seed` is honored** for most chat-completion models. Passes through as-is. Reproducibility under fixed `seed + temperature` is the best you'll get from any provider.
- **API surface choice**: the framework uses Chat Completions, not the newer Responses API. This was a deliberate decision to maximize OpenRouter compatibility (Chat Completions is the shared interface). If you need Responses-API-specific features (e.g. structured outputs with strict schemas), drop to the OpenAI SDK directly and pass a `client=` kwarg to `OpenAIProvider`.
- **Reasoning models** (`o1`, `o3`, `o4-mini`, ...) use internal reasoning tokens that consume the `max_tokens` budget invisibly. See the OpenRouter section below for the canonical case (DeepSeek v4-flash); the OpenAI reasoning models exhibit the same behavior. The framework default of 1024 handles the common case; bump to 2048–4096 for `o1-pro` / `o3-pro` / heavy thinking variants.

### Recommended defaults

```python
# Default — works for both reasoning and non-reasoning OpenAI models:
EndorsementConfig(n_samples=5)
ProviderParams(temperature=0.0, max_tokens=1024, seed=42)   # framework default

# Heavy-reasoning models (o3-pro, o1-pro, gpt-5.4-pro) — raise the cap:
ProviderParams(temperature=0.0, max_tokens=4096, seed=42)
```

## OpenRouter

```
pip install 'infereval[openai]'   # shared SDK with OpenAI
export OPENROUTER_API_KEY=sk-or-...
infereval evaluate bench.json \
    --provider openrouter \
    --model deepseek/deepseek-v4-flash \
    --output eta.json --n-samples 5 --max-tokens 512 --log run.jsonl \
    --http-referer https://github.com/your-org/your-repo \
    --x-title your-experiment-name
```

OpenRouter is OpenAI-API-compatible at the protocol level; the framework uses the OpenAI SDK with `base_url="https://openrouter.ai/api/v1"` and the OpenRouter API key. Any of the hundreds of models OpenRouter aggregates is reachable through this single provider.

Model id conventions: `<vendor>/<model>` (`anthropic/claude-3.5-sonnet`, `openai/gpt-4o-mini`, `deepseek/deepseek-v4-flash`, `meta-llama/llama-3.3-70b-instruct`, `qwen/qwen-2.5-72b-instruct`, ...).

### Quirks

- **Attribution headers** (`HTTP-Referer`, `X-Title`) are recommended for accountability and show up in your OpenRouter dashboard. The framework supports them as `--http-referer` and `--x-title` flags (or `http_referer=`, `x_title=` kwargs in the Python API).
- **The API key env var is `OPENROUTER_API_KEY`**, *not* `OPENAI_API_KEY`. The framework explicitly does not fall back to the OpenAI key (and a test enforces this), so you can have both set without cross-contamination.
- **DeepSeek v4-flash uses silent reasoning tokens.** This is the canonical reasoning-tokens case. At a low `max_tokens` (e.g. 32, which was the framework default before v0.5.2), the model returns `content=None`, `finish_reason="length"`, and `reasoning_tokens` equal to the cap. The framework now: (a) defaults `max_tokens` to **1024** at both the Python API and the CLI, which clears this case for v4-flash and most reasoning models; (b) **distinguishes budget-clipped abstains from genuine ones**: when `finish_reason ∈ {"length", "max_tokens"}` and no verdict could be parsed, the resulting `SampleRecord.parse_status` is `"budget_clipped"` (not `"unparseable"`). Inspect that field in your evaluation JSON to spot any remaining budget issues. For heavy-reasoning models (`openai/o1-pro`, `openai/o3-pro`, `qwen3-max-thinking`), bump `--max-tokens` further (2048-4096).
- **Per-model pricing varies enormously.** Check the OpenRouter model page before launching a large benchmark. `deepseek/deepseek-v4-flash` is cheap (~$0.10 per million input tokens); `openai/o3` is not.

### Recommended defaults

```python
# Default works for both reasoning and non-reasoning models:
ProviderParams(temperature=0.0, max_tokens=1024)   # framework default

# Heavy reasoning (deepseek-r1, openai/o1-pro, qwen3-max-thinking):
ProviderParams(temperature=0.0, max_tokens=4096)
```

### Listing currently available DeepSeek models

```bash
curl -s -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    https://openrouter.ai/api/v1/models | jq '.data[] | select(.id|test("deepseek")) | .id'
```

The same trick works for any other vendor: replace `deepseek` with `anthropic`, `meta-llama`, etc.

## Mock providers (testing / replay)

Two flavors live in `infereval.providers.mock`:

### `ScriptedProvider`

```python
from infereval.providers.mock import ScriptedProvider
from infereval.providers.base import SampleRequest

p = ScriptedProvider(responses=["GOOD", "GOOD", "BAD"])
p.sample(SampleRequest(prompt="anything"))  # -> SampleResult(text="GOOD", ...)
```

Cycles through `responses` indefinitely. Useful for unit tests that need to control what the "model" says without hitting an API.

### `ReplayProvider`

```python
from infereval.providers.mock import ReplayProvider

p = ReplayProvider("tests/fixtures/stop_sign_replay.jsonl")
```

Loads a JSONL fixture where each record carries a `prompt_hash` (SHA-256 of the user prompt) and a `text` field. When `sample()` is called, the prompt is hashed, the matching record (or next record sharing that hash) is returned. Missing prompt → clear `ProviderSampleError` with a diagnostic message.

The CLI exposes this as `--replay-from <path>`. It's the basis of the 60-second quickstart in the README and is the right tool for any deterministic CI / demo run.

Fixture format:

```jsonl
{"prompt_hash":"sha256:...","text":"GOOD","provider":"anthropic","model_id":"claude-haiku-4-5-20251001","wall_time_ms":120.0,"usage":{"input_tokens":60,"output_tokens":6}}
```

To author a fixture from real provider runs, the pattern is:

1. Run `infereval evaluate ... --log run.jsonl` against the real provider.
2. Process `run.jsonl` to extract one record per `sample.completed` event into the replay format.

A helper to do step 2 cleanly is on the roadmap (issue not yet open); for now `tests/fixtures/build_stop_sign_replay.py` is the canonical example.

## A common-issue checklist

| Symptom | Likely cause | Fix |
|---|---|---|
| Coverage near zero, lots of `parse_status: budget_clipped` with empty `raw_response` | `max_tokens` too low for a reasoning-capable model | Raise `--max-tokens`. The framework default (1024) clears most cases; bump to 2048-4096 for heavy reasoning models. |
| Coverage near zero, `parse_status: unparseable` (not `budget_clipped`) | Genuine unparseable output: model is talking but not producing a verdict token | Inspect a few `raw_response` strings; consider a verification prompt that's stricter about the output format |
| `ProviderConfigError: ANTHROPIC_API_KEY not set` despite `export ANTHROPIC_API_KEY=...` in `~/.bashrc` | Shell didn't re-source profile | `source ~/.bashrc` or open a new terminal; verify with `echo $ANTHROPIC_API_KEY \| head -c 8` |
| `ProviderConfigError: anthropic SDK not installed` | `infereval` installed without provider extras | `pip install 'infereval[anthropic]'` (or `[openai]` / `[all]`) |
| `provider.anthropic.seed_ignored` warning on every Anthropic run | Anthropic doesn't honor seed | Expected; either drop `seed` or accept the warning |
| `ProviderSampleError: no recorded response for prompt_hash=...` from `ReplayProvider` | Verification prompt template, bearer expressions, or context builders have changed since the fixture was generated | Regenerate the fixture (`python -m tests.fixtures.build_stop_sign_replay`) or use a real provider for new prompts |
| First sample on a long evaluation takes minutes | Anthropic / OpenAI / OpenRouter latency spike on a specific prompt; the BaseProvider retry loop is sleeping with exponential backoff | Wait it out (the retry policy caps at 4 attempts), or interrupt and inspect the partial JSONL log to confirm what happened |
| OpenRouter dashboard shows no app attribution | Missing `--http-referer` / `--x-title` | Pass both flags |

## Adding a new provider

If you want to wire up a new backend (Cohere, Together, Replicate, a self-hosted endpoint, ...), the pattern is:

1. Subclass `infereval.providers.base.BaseProvider`.
2. Set `name = "your-name"` as a class attribute.
3. Implement `_sample_once(self, req: SampleRequest) -> SampleResult` — one provider call, no retries (the base class handles them).
4. Implement `_is_transient(self, exc: Exception) -> bool` — return `True` for errors the retry loop should re-try.
5. Register in `infereval.providers.__init__.get_provider`.

The Anthropic / OpenAI implementations are ~150 lines each and serve as templates. If you write one, please open a PR.
