# Pulmonary edema multi-interval R22 retrofit (2026-06-07, v0.14.0)

The v0.10.0 cross-family sweep against the pulmonary-edema differential benchmark v0.2 (`pulmonology_2026-06-06.md`) characterized agreement (κ_C vs placeholder) for 6 models. It contained the headline result that motivated the methodology paper's R22 framing: **Gemini 2.5 Pro shifted κ_C by 0.21 across captures 2.5 weeks apart with identical params** (v0.5.x → v0.10.0, `−0.207` in the v0.10.0 Δ vs v0.1 κ_C column). That single across-update data point suggested cross-update drift but didn't characterize the drift's time-scale signature: was it monotonic across 18 days, or did it land in one update window?

v0.14.0 adds Phase 1 R22 evidence (back-to-back + 1h drift) for all 6 cells under the same `defeasible-clinical-v1` prompt and EndorsementConfig the v0.10.0 sweep used. **The headline finding: 1h is not the time scale of the v0.10.0 Gemini drift.** Gemini 2.5 Pro returns κ = +1.000 at both the back-to-back and 1h-later intervals — zero flips, perfectly stable. The 0.21 κ_C drift across 2.5 weeks therefore lives at a longer time scale than 1 hour; provider-side weight rotation or cache invalidation inside a 1h window is ruled out. The Phase 2 staged-composition pattern lets day-out and week-out captures append to this baseline incrementally, building the multi-interval drift signature for the Gemini cell without requiring a multi-day CLI process lifetime.

> **The benchmark labels remain placeholder, not clinical.** See `examples/pulmonary_edema/README.md` for the full caveat. The v0.14.0 R22 evidence below characterizes the *framework's reliability of measuring the model's behavior*, not model agreement with a real pulmonologist's practice. Interpretation paragraphs would change substantially once the real respondent's labels arrive — but the R22 evidence itself is independent of the analyst column's identity (a model's behavior either reproduces twice or it doesn't, regardless of which column the analyst draws).

## Setup

- **Benchmark**: `examples/pulmonary_edema/benchmark.json` v0.2 (30 items, 20 bearers, m=1 placeholder). Identical to the v0.10.0 capture.
- **Verification prompt**: the benchmark's embedded `defeasible-clinical-v1` template (unchanged from v0.1 / v0.10.0).
- **R22 capture parameters**: `--n-samples 3 --temperature 0.0 --max-tokens 2048` (matches v0.10.0 endorsement_config exactly).
- **Intervals**: `--interval-s 0 --interval-s 3600` per cell. Three captures: baseline → back-to-back (within-session floor) → 1h-later (short-horizon across-update drift). Each cell produces a `MultiIntervalRetestResult` with two pairs.
- **Identity criterion**: declared once in `experiments/results/pulmonology/retest/claims-r22-phase1.json`, threaded into every cell's `MultiIntervalRetestResult.identity_criterion`.
- **Capture harness**: `experiments/scripts/pulmonology_multiinterval_r22_retrofit.py`. Parallelized across cells via `concurrent.futures.ThreadPoolExecutor` (default `max_parallel=8`); all 6 cells fit in one batch. Total wall clock: ~1h 35min (dominated by the 3600s sleep + the slowest cell's evaluation time).
- **Cost**: 6 cells × 3 captures × 30 items × 3 samples ≈ 1620 LLM calls. Mix of frontier (Opus 4.7, GPT-5.5, Gemini 2.5 Pro) + mid-tier (GPT-4.1, DeepSeek v4-pro, Qwen3-max). Estimated spend ~$5–10.

Output per cell: `experiments/results/pulmonology/retest/<model>/{eta-0,eta-1,eta-2}.{json,run.jsonl}` + `experiments/results/pulmonology/retest/<model>-multi-retest.json`.

## R22 results

| Model | interval @ 0s (actual) | κ @ 0s | flips @ 0s | interval @ 3600s (actual) | κ @ 3600s | flips @ 3600s | Overall verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Claude Opus 4.7 | 122s | **+1.0000** | 0/30 | 3865s | **+1.0000** | 0/30 | stable |
| Qwen3-max | 208s | **+1.0000** | 2/30 | 4076s | **+1.0000** | 3/30 | stable |
| **Gemini 2.5 Pro** | 1203s | **+1.0000** | 0/30 | 5814s | **+1.0000** | 0/30 | **stable** |
| GPT-4.1 (anchor) | 42s | +0.9333 | 1/30 | 3708s | +0.9333 | 1/30 | stable |
| GPT-5.5 | 366s | +0.9333 | 1/30 | 4377s | **+1.0000** | 0/30 | stable |
| DeepSeek v4-pro | 888s | +0.8612 | 3/30 | 5271s | +0.9315 | 1/30 | stable |

All six cells classify as **stable** under the v0.6.0 verdict ladder (κ ≥ 0.8). The `interval @ Ns (actual)` columns are the actual elapsed wall-clock seconds from `baseline.started_at` to the later capture's `started_at` (computed via `compute_interval_s`), reflecting per-capture evaluation time + the nominal sleep. The back-to-back interval ranges from 42s (GPT-4.1, fast) to 1203s (Gemini 2.5 Pro, slow on OpenRouter); the 1h interval ranges from 3708s (~62 min) to 5814s (~97 min) depending on the cell's per-capture evaluation time.

## Reading the Gemini cell

The v0.10.0 → v0.5.x drift on Gemini was −0.207 κ_C over 2.5 weeks. The Phase 1 R22 captures 1h of that timeline at 0s + 3600s elapsed:

- **Back-to-back (1203s elapsed)**: κ = +1.0000, 0/30 flips. The model returns the same 30-item verdict column twice in sequence.
- **1h-later (5814s elapsed)**: κ = +1.0000, 0/30 flips. The model returns the same 30-item verdict column 5814 seconds after the baseline.

**Both within-1h captures are perfectly stable.** The v0.10.0 0.21 κ_C drift cannot be explained by short-horizon (sub-hour) provider-side weight rotation or cache invalidation. The drift must live at a longer time scale — at least the multi-week scale where v0.10.0 originally observed it.

This is methodologically valuable in two ways:

1. **Negative result, clean.** A short-horizon drift would have collapsed the v0.10.0 finding into "sampling noise inflated by a 30-item count." The 1h-later κ = +1.0000 rules out that explanation: the within-session and 1h-elapsed columns are *identical*, and the v0.10.0 0.21 difference is genuinely across-update.

2. **Sharpens the Phase 2 question.** Where between 1 hour and 2.5 weeks does the Gemini drift first emerge? Phase 2 day-out / week-out `--append-to` captures (forthcoming as commits to `main`) will narrow the window.

## Cross-cell pattern

Six cells, six stable verdicts. The within-session floor is essentially zero for the three frontier models (Opus 4.7, GPT-5.5, Gemini 2.5 Pro all κ ≥ +0.933 at 0s) and modestly noisy for two cells worth flagging:

- **DeepSeek v4-pro**: κ = +0.861 back-to-back (3/30 flips), κ = +0.932 at 1h (1/30 flip). Mildly unstable within-session that *partially resolves* at 1h. Two of the three back-to-back flips were items that came back identical at 1h. This is interesting: a back-to-back evaluation of DeepSeek is noisier than a 1h-elapsed evaluation. Plausible explanation: the back-to-back capture coincides with OpenRouter's burstier rate-limit-shaped distribution; once load smooths out by the 1h-later capture, the sampling is more consistent.

- **Qwen3-max**: κ = +1.000 at both intervals, but 2–3 of 30 items flipped between captures at *each* interval. The flips don't show up as κ disagreements because they're items that went GOOD↔ABSTAIN or BAD↔ABSTAIN — moving in and out of Qwen's substantive intersection. Qwen3-max's notorious abstention discipline (flagged in `pulmonology_2026-06-06.md` as "Qwen3-max's abstention discipline expands") *does* wobble across short time scales, even though the items it commits substantively to are perfectly consistent.

The other four cells are clean either at both intervals (Opus 4.7, Gemini 2.5 Pro: κ = +1.000) or identically-imperfect at both intervals (GPT-4.1: same single flip in both pairs, suggesting a single genuinely-ambiguous item). GPT-5.5's "0s noisy, 1h stable" pattern matches DeepSeek's shape at a smaller magnitude.

## Methodological framing

The v0.14.0 Phase 1 evidence answers one question and surfaces another:

**Answered**: the v0.10.0 Gemini drift is not within-1h. The within-session and 1h-elapsed reliability floors are both zero on the cell that motivated R22 in the first place.

**Surfaced**: where between 1 hour and 2.5 weeks does the Gemini drift first emerge? Phase 2 captures via `--append-to` will narrow this. A reasonable cadence:

- Day-out append (~24h after Phase 1): captures the daily across-update component.
- Week-out append (~7 days): closes in on the 2.5-week timeline.
- Two-week-out append: completes the comparison to v0.10.0.

Each append takes a few minutes (one evaluation + one `compute_retest`) regardless of the elapsed window. The accumulated `MultiIntervalRetestResult` renders as a 4-row per-interval table in `infereval report` §2 Reliability with worst-case overall verdict computed across all four pairs.

## Reading the Phase 2 evidence (forthcoming as commits to `main`)

The v0.14.0 staged-composition pattern lets Phase 2 day-out / week-out R22 evidence ship as separate `infereval retest --auto --append-to <multi.json>` invocations days or weeks after Phase 1, without the orchestrator process needing to stay alive for the elapsed window. Each Phase 2 append grows the `MultiIntervalRetestResult` from two pairs to three or more.

When Phase 2 captures land they will be summarized in a follow-up section here or in dated `pulmonology_<later-date>.md` markdowns. The R22 audit cap is computed worst-case across all captured pairs, so a Phase 2 substantively-unstable pair will downgrade the v0.13.0 `infereval report --retest` verdict for that cell.

## Reproducibility

```sh
# Set up API keys (anthropic / openai / openrouter):
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export OPENROUTER_API_KEY=...

# Phase 1 sweep (~$5-10, ~1.5h wall clock parallelized):
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py

# Subset (smoke-test or retry):
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py --only gemini-2.5-pro

# Dry-run (no LLM calls):
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py --dry-run
```

Phase 2 append (run days or weeks after Phase 1):

```sh
infereval retest --auto \
  --benchmark examples/pulmonary_edema/benchmark.json \
  --provider openrouter --model google/gemini-2.5-pro \
  --n-samples 3 --temperature 0.0 --max-tokens 2048 \
  --append-to experiments/results/pulmonology/retest/gemini-2.5-pro-multi-retest.json
```

The append finds `eta-0.json` next to the multi.json automatically and computes `interval_s` from elapsed wall clock between the saved baseline's `started_at` and the fresh capture's `started_at`.

## Caveats

- **Identity criterion**: Phase 1 captures assert `same_provider_model_id`, `cross_update_identity_asserted`, and `same_scaffolding` over the 1h window. The 0.21 v0.10.0 Gemini drift result is presumptive evidence that OpenRouter's Gemini routing can change models across longer windows; whether it ALSO does so inside a 1h window is what Phase 1's Gemini cell tells us — and the answer is no, at least at this measurement.
- **Placeholder labels**: the analyst column is a single non-clinical placeholder; κ_C readings characterize agreement with that placeholder, not with clinical practice. R22 evidence is independent of this caveat (reliability is intrinsic to the model's behavior, not relative to the analyst column).
- **m=1**: pulmonology's single-analyst column makes `κ_F*(β)` undefined; the v0.13.0 report's R22 audit cap acts only on worst-case across pairs.
- **Endorsement config matches v0.10.0 exactly** (`defeasible-clinical-v1` prompt embedded in benchmark, n_samples=3, temperature=0.0, max_tokens=2048).
- **Phase 1 is necessary but not sufficient to close out the v0.10.0 drift story.** The 1h Phase 1 captures characterize the short-horizon component; Phase 2 day-out / week-out captures will be required to fully timeline the Gemini result. The cleanly-negative Phase 1 finding sharpens that question rather than answering it.
- **n=30, m=1, 3 samples**: each flip is 1/30 = 3.3% flip rate. Single flips on Cohen's κ over the substantive intersection can drop κ from +1.000 to +0.933 (as observed on GPT-4.1) — that's not a wholesale instability, it's one item in the model's responses that flips between defeasible and definitive readings.
