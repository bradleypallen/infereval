# Known Issues — v0.14.0 (and predecessors)

> **RESOLVED in v0.16.0 (2026-06-09).** All three bugs documented below were fixed in v0.15.0 / v0.15.1 / v0.15.2 (released to PyPI 2026-06-07). v0.16.0 deletes all v0.14.0-era bundled captures and re-captures the cross-family demonstration suite from scratch under the v0.15.2 framework — see [`experiments/results/pulmonology_2026-06-09.md`](experiments/results/pulmonology_2026-06-09.md) and [`experiments/results/stop_sign_2026-06-09.md`](experiments/results/stop_sign_2026-06-09.md) for the fresh analyses. The text below remains as the historical retraction record.

**Status as of 2026-06-08.** v0.14.0 is on PyPI but ships three framework bugs that produce silent measurement artifacts under provider stress (rate limits, transient errors). The bugs were caught by the framework's own R22 discipline: a Phase 2 day-out parallel sweep produced implausibly uniform coverage-collapse on multiple cells, which led to a forensic audit that surfaced the underlying instrumentation problems. **The bugs affect every historical capture to some degree, not just v0.14.0.** This document is the single source of truth on the issues; the file lives at the repo root so it survives across conversation sessions.

---

## TL;DR

- The framework's provider code returns empty `raw_response = ''` strings on API failure rather than raising. The endorsement parser maps empty → `ABSTAIN`. Result: failed API calls masquerade as legitimate model abstentions in every `eta.json` ever produced by the framework, at a rate that scales with provider rate-limit pressure and parallelism.
- The v0.14.0 Phase 2 pulm day-out sweep (45 cells × `max_parallel=8` burst) triggered the bug catastrophically: **46% of pulm day-out samples are silent failures** (250 of 540). The Phase 2 analysis writeups in `experiments/results/pulmonology_2026-06-07.md` and the bundled `report-gemini-2.5-pro.md` report this as a coverage-collapse signal. It is not.
- Stop-sign captures are mostly unaffected (smaller per-cell call volume).
- Historical captures: v0.5.18 cross-family has 0.64% silent failures (mostly qwen3-max-perceptual); v0.10.0 pulmonology has 1.85% (mostly qwen3-max + deepseek-v4-pro); v0.11.0 sequential R22 has 0% (no parallelism, no rate-limit pressure).

---

## The three bugs

### Bug A — silent empty-response → ABSTAIN

**Where:** `src/infereval/providers/openai.py` (the OpenRouter shim shares the OpenAI-compatible code path). On certain HTTP error conditions (rate limits, transient errors, empty response bodies), the provider's `sample()` method returns an empty string instead of raising.

**Effect:** Downstream, `infereval.endorsement` parses the empty string against the verification prompt's `parse_regex` (`\b(GOOD|BAD|ABSTAIN)\b`). The regex doesn't match. The endorsement default for "no parse" is `ABSTAIN`. The `sample.completed` event records `parsed_verdict="abstain"`, `parse_status="ok"` (because the parser didn't error — it just didn't match), `raw_response=""`, `wall_time_ms=0`, `finish_reason=None`. The `Evaluation.items[i].samples[j]` carries these fields. The majority-vote aggregator counts the ABSTAIN. The κ computation treats it as a real abstention.

**Forensic signature:** in any `eta-N.json`, a silent failure is `samples[j]` with:
- `parsed_verdict = "abstain"` AND
- `raw_response = ""` OR `wall_time_ms = 0` OR `finish_reason = None`

A *real* model abstention has `raw_response = "ABSTAIN"` (or contains it), `wall_time_ms > 0`, `finish_reason = "stop"`.

**Audit script** (run from repo root):

```python
import json
from pathlib import Path
def audit(path):
    e = json.loads(Path(path).read_text())
    empty = sum(1 for it in e['items'] for s in it.get('samples', [])
                if s.get('parsed_verdict') == 'abstain'
                and (s.get('raw_response', '') == '' or s.get('wall_time_ms') in (0, None)))
    total = sum(len(it.get('samples', [])) for it in e['items'])
    return empty, total
```

### Bug B — cross-thread logger contamination

**Where:** `src/infereval/evaluation.py` attaches a `logging.FileHandler` to the module-level `infereval.endorsement` / `infereval.evaluation` / `infereval.providers.*` loggers per `evaluate()` call (one handler per call, removed on exit). Module-level loggers are shared across all threads in the process.

**Effect:** When N `evaluate()` calls run concurrently (e.g. via `ThreadPoolExecutor` in the v0.14.0 orchestrator scripts), the shared logger has N `FileHandler`s attached simultaneously. Every log call from any thread is broadcast to *every* attached handler. The per-cell `run.jsonl` files end up containing events from every cell that was running concurrently.

Additionally, `logging` context binding (e.g. `extra={"run_id": "..."}`) is last-writer-wins across threads. Events emitted from thread A can carry thread B's `run_id` / `benchmark_id` if B bound the context between A's call site and A's handler emit.

**Forensic signature:** any cell's `eta-N.run.jsonl` containing events with `model_id` values from other cells.

**Verification:**

```bash
.venv/bin/python -c "
import json
seen = set()
with open('experiments/results/pulmonology/retest/gemini-2.5-pro/eta-0.run.jsonl') as f:
    for line in f:
        d = json.loads(line)
        if 'model_id' in d:
            seen.add(d['model_id'])
print(seen)
# Expected if clean: {'google/gemini-2.5-pro'}
# Actual (Phase 1, 6-parallel): {'google/gemini-2.5-pro', 'gpt-5.5', 'claude-opus-4-7', ...}
"
```

**What it doesn't affect:** the `eta-N.json` measurement files. Those are built from in-thread Python state during the `evaluate()` call, not parsed from the log output. The κ values, verdict columns, and flip counts are all computed from clean per-thread data.

### Bug C — no rate-limit retry

**Where:** `src/infereval/providers/openai.py`. When the HTTP request returns 429 (rate limited) or 5xx, the provider doesn't retry with exponential backoff. It either returns empty (composing with Bug A) or surfaces the error in a way that doesn't propagate to the caller.

**Effect:** Bursty parallel sweeps that exceed provider rate limits silently fail rather than retrying. Combined with Bug A, the failure presents as ABSTAIN samples in the eta JSON.

---

## Audit: who's affected, how badly

Empty-response rate by capture set:

| Capture set | Total samples | Empty (silent failures) | Rate |
|---|---:|---:|---:|
| v0.11.0 stop-sign R22 (sequential) | 72 | 0 | **0.00%** |
| v0.5.18 stop-sign cross-family | 468 | 3 | 0.64% |
| v0.10.0 pulmonology cross-family | 540 | 10 | 1.85% |
| v0.14.0 Phase 1 stop-sign baseline (8-parallel + 1h sleep) | 468 | 11 | 2.35% |
| v0.14.0 Phase 1 stop-sign back-to-back | 468 | 12 | 2.56% |
| v0.14.0 Phase 1 stop-sign 1h | 468 | 12 | 2.56% |
| v0.14.0 Phase 1 pulm baseline (6-parallel + 1h sleep) | 540 | 10 | 1.85% |
| v0.14.0 Phase 1 pulm back-to-back | 540 | 12 | 2.22% |
| v0.14.0 Phase 1 pulm 1h | 540 | 8 | 1.48% |
| **v0.14.0 Phase 2 pulm day-out (45-parallel burst, NO sleep)** | **540** | **250** | **46.30%** |
| v0.14.0 Phase 2 stop-sign day-out | 468 | 2 | 0.43% |

The bug fires in inverse proportion to call-pacing. Sequential captures are clean. Parallel-with-sleep captures have ~2% failure rates concentrated on specific OpenRouter cells (Qwen3-max especially). Burst-parallel captures with high call volume per provider hit catastrophic failure rates.

### Concentrated failure cells (across all capture sets)

The bug doesn't fire uniformly — it concentrates on specific (provider × model) combinations under load:

- **qwen3-max across all benchmarks**: bug-prone in v0.5.18, v0.10.0, AND v0.14.0 Phase 1 + 2. The `qwen3-max-intrinsic` stop-sign Phase 1 was published as "degenerate-but-consistent" (κ=undefined at both intervals) but 12 of its 36 samples across 3 intervals are silent failures.
- **gemini-2.5-pro pulmonology day-out**: 86/90 silent failures — the headline "v0.10.0 drift sharpens" finding in `pulmonology_2026-06-07.md` is artifact.
- **deepseek-v4-pro pulmonology day-out**: 76/90 silent failures — the "25-of-30 ABSTAIN-boundary movement" claim is artifact.
- **qwen3-max pulmonology day-out**: 88/90 silent failures — same.

---

## Published findings to retract

### v0.14.0 — released to PyPI, on `main`

**Retract from `experiments/results/pulmonology_2026-06-07.md`:**
- Entire "Phase 2 day-out append (captured 2026-06-07, all 6 cells)" section's coverage-collapse framing.
- The "v0.10.0 drift sharpens to day scale" claim — the day-out data is 86/90 silent failures, not a measurement.
- The "OpenRouter-routed pulmonology cells show day-scale instability" claim — same.
- The bundled `experiments/results/pulmonology/retest/report-gemini-2.5-pro.md` audit-cap-fires demonstration. The cap fires correctly given the data, but the data is artifact, not real.

**Retract from `experiments/results/stop_sign_2026-06-07.md`:**
- The "qwen3-max-intrinsic: degenerate-but-consistent (κ=undefined both intervals)" Phase 1 finding. The cell has 3-4 silent failures per interval; the "degenerate consistent" pattern may be partly artifact, partly real degenerate model behavior. Needs re-examination with silent-failure samples excluded.
- The "claude-haiku-4.5-original: degenerate-consistent" Phase 1 finding may also have artifact contribution — has 1 silent failure across 36 samples.

**Findings that remain valid:**
- Stop-sign Phase 1 & 2 results for non-qwen3-max cells (most have 0 silent failures).
- The `deepseek-v4-pro-perceptual` 1h-drift finding (κ=+1.000 → +0.500). 0/12 silent failures. Real.
- The `gpt-5.4-mini` within-session noise pattern. 0/12 silent failures. Real.
- The `qwen3.6-flash-perceptual` progressive deterioration. 2/12 day-out silent failures need checking but the κ=+0.5 → +0.5 Phase 1 result is clean.
- The pulmonology Phase 1 captures (back-to-back + 1h) are mostly clean for the 5 non-qwen-max cells.

### v0.10.0 — pulmonology cross-family results

`experiments/results/pulmonology_2026-06-06.md`'s published κ_C values include silent failures as abstains. Most affected: `qwen3-max-eta.json` has 8/90 silent failures. The published Qwen3-max coverage of 66.67% (the lowest in the panel) is *partly* "Qwen abstains by design" and *partly* "API calls silently failed." Need to recompute κ_C with silent failures excluded vs included to see if the qualitative conclusion changes.

### v0.5.18 — stop-sign paraphrase-axis

`experiments/results/stop_sign_2026-05-18.md` only `qwen3-max-perceptual.json` is affected (3/12 silent failures). The published κ_C for that single cell may shift modestly when recomputed.

---

## v0.15.0 fix plan

### Fix 1 — provider raises on empty/error response

**File:** `src/infereval/providers/openai.py` (and any other provider in `src/infereval/providers/`).

Change `sample()` so it raises `ProviderError` on any of:
- HTTP non-200 (including 429, 5xx).
- HTTP 200 with empty response body.
- HTTP 200 with content that doesn't match the expected response shape.

Propagate the error to `infereval.endorsement.endorse_sample` which currently swallows it into an empty string. The endorsement code should record the failure as a *distinct kind of sample* — not as "model said ABSTAIN" but as "API failed."

**Schema change:** `EvaluationSample` (currently records `parsed_verdict`, `raw_response`, etc.) gains a `provider_error: str | None` field. Non-None → this sample is a provider-side failure, not a model decision. Verdict-aggregation skips these samples rather than counting them as abstains.

**Backward compat:** Old eta JSONs without `provider_error` continue to load (Pydantic optional default `None`). Old samples with `parsed_verdict="abstain" + raw_response=""` can be heuristically re-classified as `provider_error="legacy: empty response"` during load if a `--migrate` flag is passed, but that's optional.

### Fix 2 — logger context per evaluate-call

**File:** `src/infereval/evaluation.py`.

Replace module-level logger pattern (`log = logging.getLogger(__name__)` + FileHandler attach/detach around `evaluate()`) with a per-call `logging.LoggerAdapter` that scopes its handlers to the current evaluation. Options:

- Pass an explicit `logger` instance into `evaluate()`. Caller (or the framework) creates a fresh logger with a unique name per call (e.g. `f"infereval.evaluation.{run_id}"`).
- Use `contextvars` to thread the active log handler stack through concurrent invocations.

The simplest fix: scope the FileHandler attachment to a fresh logger object (not the module-level singleton). The module logger continues to handle stderr at INFO; per-evaluation file logging uses a separate logger.

### Fix 3 — retry policy for rate-limit responses

**File:** `src/infereval/providers/openai.py`.

Add exponential-backoff retry around the API call. Retry on:
- 429 (rate limit) — with `Retry-After` header if present, else exponential (1s → 2s → 4s → 8s → 16s, max 5 retries).
- 5xx (server error) — exponential (1s → 2s → 4s → 8s, max 4 retries).
- Empty response body — single retry.

On exhausted retries, raise `ProviderError` (composing with Fix 1).

### Fix 4 — recompute κ-with-failures-excluded

**File:** `src/infereval/metrics.py` and `src/infereval/retest.py`.

When `provider_error` is non-None on a sample, exclude it from the majority-vote aggregation rather than counting it. If all 3 samples for an item are provider errors, the item has no model verdict — surfaces in the `Evaluation` as `model_verdict=None` (new) rather than `model_verdict="abstain"`.

`Evaluation.coverage`, `cohens_kappa`, `fleiss_kappa`, `compute_retest` all need to handle the new `None` case. Conventionally treat the item as missing data — drop from per-item computations rather than coding as ABSTAIN.

### Fix 5 — `infereval audit` CLI command

**File:** `src/infereval/cli/audit_cmd.py` (new).

Add a CLI command that scans an eta JSON for silent-failure samples and reports the count + per-item locations. Lets analysts post-hoc verify their captures aren't artifact-tainted.

```sh
infereval audit experiments/results/pulmonology/qwen3-max-eta.json
# Output:
#   8 of 90 samples (8.9%) are silent failures (empty raw_response, wall_time_ms=0):
#     a3:sample-1
#     b7:sample-2
#     ...
#   Recomputed κ_C with failures excluded: +0.x (was +0.y published)
```

---

## Next-action checklist

In priority order:

1. **Retract pulmonology day-out coverage-collapse section** from `pulmonology_2026-06-07.md` and the bundled `report-gemini-2.5-pro.md`. Mark as artifact, point at this issue file. **Do not** quietly delete — leave a clear "RETRACTED" marker so future readers understand what happened.
2. **Same retraction for the qwen3-max stop-sign degenerate-consistent claim** in `stop_sign_2026-06-07.md`.
3. **Write a follow-up commit + push to `main`** with the retractions + this issue file. v0.14.0 PyPI release stays as-is (the bugs are baked in; v0.15.0 will fix them).
4. **Re-examine the surviving v0.14.0 findings.** The cells with 0 silent failures (most stop-sign cells, the 3 OpenAI/Anthropic pulm cells, all v0.11.0 sequential captures) remain valid. Update the analysis markdowns to make this explicit.
5. **Audit v0.10.0 and v0.5.18 historical etas** for silent failures. Recompute κ_C for the qwen3-max-perceptual stop-sign cell and the qwen3-max pulmonology cell with silent failures excluded; report the recomputed values alongside the original. If the qualitative conclusions change, retract those too.
6. **Open v0.15.0 release plan** with the four framework fixes above + the `infereval audit` CLI command + tests. Tag-blocking issue.
7. **Re-run Phase 2 day-out for the pulm cells** with `--max-parallel 2` or sequential, AFTER v0.15.0's retry logic ships. The actual day-out reliability evidence for the pulm cells is currently unknown.
8. **Methodology paper section** on "the framework's R22 discipline caught its own instrumentation bug." This is the kind of methodological self-correction the paper's central argument is supposed to demonstrate — write it up explicitly.

## How to verify after compaction

A fresh conversation session can re-validate this state with these queries:

```sh
# What's the current state of v0.14.0 on PyPI?
curl -s https://pypi.org/pypi/infereval/json | python3 -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
# Expected: 0.14.0

# Which historical captures are tainted?
.venv/bin/python -c "
import json
from pathlib import Path
for p in sorted(Path('experiments/results').rglob('*.json')):
    if 'multi-retest' in p.name or 'archive' in str(p): continue
    try:
        e = json.loads(p.read_text())
        if 'items' not in e: continue
        empty = sum(1 for it in e['items'] for s in it.get('samples', [])
                    if s.get('parsed_verdict') == 'abstain'
                    and (s.get('raw_response', '') == '' or s.get('wall_time_ms') in (0, None)))
        total = sum(len(it.get('samples', [])) for it in e['items'])
        if empty > 0:
            print(f'{empty:3d}/{total:3d} ({100*empty/total:5.1f}%)  {p}')
    except Exception:
        pass
"

# Read this issue file:
cat KNOWN_ISSUES_v0.14.0.md
```

If those produce the expected output, the post-compaction state matches the pre-compaction state. Resume from the next-action checklist above.
