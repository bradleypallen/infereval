<!--
v0.14.0 Stage 5 — DRAFT SKELETON. Pre-drafted during the v0.14.0
implementation push for the analysis to be filled in once Stage 4
(the 6-cell Phase 1 capture run) lands. Sections marked
"<!-- v0.14.0 Stage 5 TODO -->" are placeholders for actual
measurement results; numbers/verdicts are NOT to be invented before
the captures complete. Sections without TODO markers are framework /
methodology prose that does not depend on the measurements.
-->

# Pulmonary edema multi-interval R22 retrofit (2026-06-07, v0.14.0)

The v0.10.0 cross-family sweep against the pulmonary-edema differential benchmark v0.2 (`pulmonology_2026-06-06.md`) characterized agreement (κ_C vs placeholder) for 6 models. It contained the headline result that motivated the methodology paper's R22 framing: **Gemini 2.5 Pro shifted κ_C by 0.21 across captures 2.5 weeks apart with identical params** (v0.5.x → v0.10.0, `−0.207` in the v0.10.0 Δ vs v0.1 κ_C column). That single 2.5-week-elapsed-time-apart data point is suggestive of cross-update drift but doesn't characterize the drift's time-scale signature: was it monotonic across 18 days, or did it land in one update window?

v0.14.0 adds Phase 1 R22 evidence (back-to-back + 1h drift) for all 6 cells under the same `defeasible-clinical-v1` prompt and EndorsementConfig the v0.10.0 sweep used. The Phase 2 staged-composition pattern lets day-out and week-out captures append to this baseline incrementally, building a multi-interval drift signature for the Gemini cell (and the other 5) without requiring a multi-day CLI process lifetime.

> **The benchmark labels remain placeholder, not clinical.** See `examples/pulmonary_edema/README.md` for the full caveat. The v0.14.0 R22 evidence below characterizes the *framework's reliability of measuring the model's behavior*, not model agreement with a real pulmonologist's practice. Interpretation paragraphs would change substantially once the real respondent's labels arrive — but the R22 evidence itself is independent of the analyst column's identity (a model's behavior either reproduces twice or it doesn't, regardless of which column the analyst draws).

## Setup

- **Benchmark**: `examples/pulmonary_edema/benchmark.json` v0.2 (30 items, 20 bearers, m=1 placeholder). Identical to the v0.10.0 capture.
- **Verification prompt**: the benchmark's embedded `defeasible-clinical-v1` template (unchanged from v0.1 / v0.10.0).
- **R22 capture parameters**: `--n-samples 3 --temperature 0.0 --max-tokens 2048` (matches v0.10.0 endorsement_config exactly).
- **Intervals**: `--interval-s 0 --interval-s 3600` per cell. Three captures: baseline → back-to-back (within-session floor) → 1h-later (short-horizon across-update drift). Each cell produces a `MultiIntervalRetestResult` with two pairs.
- **Identity criterion**: declared once in `experiments/results/pulmonology/retest/claims-r22-phase1.json`, threaded into every cell's `MultiIntervalRetestResult.identity_criterion`.
- **Capture harness**: `experiments/scripts/pulmonology_multiinterval_r22_retrofit.py`. Parallelized across cells via `concurrent.futures.ThreadPoolExecutor` (default `max_parallel=8`). Each cell's wall clock is ~1.5h (dominated by the 3600s sleep).
- **Cost**: 6 cells × 3 captures × 30 items × 3 samples ≈ 1620 LLM calls. <!-- v0.14.0 Stage 5 TODO: actual cost. -->

Output per cell: `experiments/results/pulmonology/retest/<model>/{eta-0,eta-1,eta-2}.{json,run.jsonl}` + `experiments/results/pulmonology/retest/<model>-multi-retest.json`.

## R22 results

<!-- v0.14.0 Stage 5 TODO: fill in the table. Columns:
- κ vs baseline @ 0s — within-session floor.
- flips @ 0s — number of items whose majority verdict flipped back-to-back.
- κ vs baseline @ 3600s — 1h drift.
- flips @ 3600s — items flipped at 1h.
- Overall verdict — worst-case across pairs.
-->

| Model | κ vs baseline @ 0s | flips @ 0s | κ vs baseline @ 3600s | flips @ 3600s | Overall verdict |
|---|---:|---:|---:|---:|---|
| GPT-4.1 (anchor) | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> |
| GPT-5.5 | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> |
| Claude Opus 4.7 | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> |
| DeepSeek v4-pro | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> |
| Gemini 2.5 Pro | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> |
| Qwen3-max | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> | <!-- TODO --> |

## Reading the Gemini cell

<!-- v0.14.0 Stage 5 TODO: 2-3 paragraphs specifically on Gemini's
Phase 1 result. The framing template:

The v0.10.0 → v0.5.x drift on Gemini was 0.21 κ_C over 2.5 weeks.
The Phase 1 R22 captures 1h of that timeline. Possible findings:

1. Stable at 0s + stable at 3600s: the cross-update drift component
   isn't surfacing on the 1h time scale. Phase 2 day-out + week-out
   captures are needed to characterize where the drift lives.

2. Stable at 0s + unstable at 3600s: short-horizon update drift IS
   surfacing inside a 1h window. Either provider-side weight rotation
   or cache invalidation is happening fast. Striking finding.

3. Unstable at 0s + (anything) at 3600s: the within-session floor on
   pulmonology cells is itself non-trivial for Gemini, which would
   suggest the 0.21 v0.10.0 drift is partially within-session
   stochasticity inflated by the 30-item benchmark's per-item-margin
   structure. Reconsider the v0.10.0 drift story.

Fill in based on the actual Phase 1 measurement. -->

## Cross-model aggregate

<!-- v0.14.0 Stage 5 TODO: cells-by-verdict count. Six cells; the
expected distribution is several stable + maybe 1-2 with interesting
drift signals. Specifically flag any model whose 1h R22 verdict is
worse than `stable`. -->

## Interpretation

<!-- v0.14.0 Stage 5 TODO: 2-3 paragraphs. The framing:

1. The within-session floor across the 6 models. For the four cells
   that v0.10.0 found stable (Δ vs v0.1 κ_C within ±0.07: GPT-4.1,
   GPT-5.5, Claude Opus 4.7, Qwen3-max), the back-to-back floor
   should also be stable — confirming v0.10.0's drift findings are
   genuinely cross-update on those cells.

2. The 1h drift signature. Where does it land? Gemini is the
   methodologically central cell. The other five serve as
   within-day controls.

3. Methodological framing for the v0.14.0 release: Phase 1's 1h
   evidence is necessary but not sufficient to characterize the
   2.5-week v0.10.0 finding. Phase 2 day-out / week-out captures
   are the operational complement; they'll ship as commits to main
   after this release. -->

## Reading the Phase 2 evidence (forthcoming as commits to `main`)

The v0.14.0 staged-composition pattern lets Phase 2 day-out / week-out R22 evidence ship as separate `infereval retest --auto --append-to <multi.json>` invocations days or weeks after Phase 1, without the orchestrator process needing to stay alive for the elapsed window. Each Phase 2 append grows the `MultiIntervalRetestResult` from two pairs to three or more.

For the pulmonology Gemini cell specifically, a sensible Phase 2 cadence is:
- Day-out append (~24h after Phase 1): captures the daily across-update component.
- Week-out append (~7 days after Phase 1): closes in on the 2.5-week v0.10.0 timeline.
- Two-week-out append: completes the comparison to the v0.10.0 result.

Each append takes a few minutes (one evaluation + one `compute_retest`) regardless of the elapsed window. The accumulated `MultiIntervalRetestResult` then renders as a 4-row per-interval table in `infereval report` §2 Reliability, with the worst-case overall verdict computed across all four pairs.

## Reproducibility

```sh
# Set up API keys (anthropic / openai / openrouter):
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export OPENROUTER_API_KEY=...

# Phase 1 sweep (~$5-15, ~1.5h wall clock parallelized):
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

- **Identity criterion**: Phase 1 captures assert `same_provider_model_id`, `cross_update_identity_asserted`, and `same_scaffolding` over the 1h window. The 0.21 v0.10.0 Gemini drift result is presumptive evidence that OpenRouter's Gemini routing CAN change models across longer windows, but the framework cannot mechanically verify it's the same model within the 1h Phase 1 window. The analyst commits on faith.
- **Placeholder labels**: the analyst column is a single non-clinical placeholder; κ_C readings characterize agreement with that placeholder, not with clinical practice. R22 evidence is independent of this caveat (reliability is intrinsic to the model's behavior, not relative to the analyst column).
- **m=1**: pulmonology's single-analyst column makes `κ_F*(β)` undefined; the v0.13.0 report's R22 audit cap acts only on worst-case across pairs.
- **Endorsement config matches v0.10.0 exactly** (`defeasible-clinical-v1` prompt embedded in benchmark, n_samples=3, temperature=0.0, max_tokens=2048).
- **Phase 1 is necessary but not sufficient to close out the v0.10.0 drift story.** The 1h Phase 1 captures characterize the short-horizon component; Phase 2 day-out / week-out captures will be required to fully timeline the Gemini result.
