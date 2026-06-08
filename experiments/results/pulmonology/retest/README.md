# Pulmonology R22 retest captures (2026-06-07, v0.14.0)

Multi-interval test-retest reliability evidence for the 6 bundled
pulmonary-edema cross-family models against the v0.2 30-item
benchmark (`examples/pulmonary_edema/benchmark.json`). Captured under
the same `defeasible-clinical-v1` prompt and EndorsementConfig the
v0.10.0 cross-family sweep used, so the R22 evidence is directly
comparable to the v0.10.0 agreement measurements at
`experiments/results/pulmonology/<model>-eta.json`.

The methodological motivation: cross-update drift on the order of
0.2 κ_C observed in earlier captures of the same model–benchmark
pair across multi-week intervals suggested cross-update drift but
didn't characterize the drift's time-scale signature. Phase 1
captures the within-day component (back-to-back floor + 1h drift)
for each cell; Phase 2 captures extend that to day-out and week-out
time scales. The bundled `*-multi-retest.json` artifacts compose
those intervals into one `MultiIntervalRetestResult`. (Bundled
data pending v0.16.0 fresh re-capture.)

## Per-cell layout

```
pulmonology/retest/
  claims-r22-phase1.json                 # Phase 1 identity criterion
  README.md                              # this file
  claude-opus-4.7/
    eta-0.json + eta-0.run.jsonl         # baseline capture
    eta-1.json + eta-1.run.jsonl         # back-to-back (interval 0s)
    eta-2.json + eta-2.run.jsonl         # 1h-later (interval 3600s)
  claude-opus-4.7-multi-retest.json      # MultiIntervalRetestResult
  ...
  gemini-2.5-pro/                        # the methodologically central cell
    eta-0.json ...
  gemini-2.5-pro-multi-retest.json
```

Each `<model>-multi-retest.json` is a `MultiIntervalRetestResult`
wrapping:

- `baseline_run_id` — the `id` of `eta-0`.
- `pairs[0]` — `IntervalPair(interval_s=0, retest=compute_retest(eta-0, eta-1))`.
- `pairs[1]` — `IntervalPair(interval_s=~3600, retest=compute_retest(eta-0, eta-2))`.
- `identity_criterion` — the criterion from `claims-r22-phase1.json`.

The `interval_s` on `pairs[1]` reflects the *actual* elapsed wall
clock from `eta-0.started_at` to `eta-2.started_at` (computed via
`compute_interval_s`), not the nominal 3600s — so the value is
typically a few seconds over 3600 due to per-capture LLM call time.

## Identity criterion

`claims-r22-phase1.json` declares:

- **Framework-substantiated** (mechanically verified by the parity
  check): `same_benchmark_hash`, `same_endorsement_config`,
  `same_paraphrase_variant`. All three are guaranteed by the
  orchestrator (same benchmark loaded for every capture, same
  EndorsementConfig threaded in, no paraphrase axis on pulmonology).
- **Analyst-substantiated** (recorded without mechanical verification):
  `same_provider_model_id`, `cross_update_identity_asserted`,
  `same_scaffolding`. The 1h window is short enough that
  cross-update model swaps would be exceptional on Anthropic / OpenAI
  / OpenRouter, but the framework can't mechanically verify the
  absence of one — see the v0.10.0 Gemini drift result for the
  scenario where this commitment is contested at longer windows.
- **Rationale**: documents the within-orchestrator-invocation
  framework-substantiated portions.

## Generation

```sh
# Set up API keys:
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export OPENROUTER_API_KEY=...

# Phase 1 sweep (~$5-15, ~1.5h wall clock parallelized via
# ThreadPoolExecutor across the 6 cells):
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py

# Smoke-test or retry one cell:
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py --only gemini-2.5-pro

# Dry-run (no LLM calls, lists planned invocations + env-var status):
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py --dry-run
```

The full analysis + interpretation will land as a fresh top-level
writeup at `experiments/results/pulmonology_2026-XX-XX.md` after the
v0.16.0 re-capture completes.

## v0.14.0 Phase 2: staged-composition appends

The v0.14.0 staged-composition CLI surface (`--baseline-from`,
`--append-to`) lets day-out and week-out R22 evidence ship as
incremental commits to `main` without the orchestrator process
needing to stay alive for the elapsed window. To append a new pair
to any Phase 1 multi-retest artifact:

```sh
infereval retest --auto \
  --benchmark examples/pulmonary_edema/benchmark.json \
  --provider openrouter --model google/gemini-2.5-pro \
  --n-samples 3 --temperature 0.0 --max-tokens 2048 \
  --append-to experiments/results/pulmonology/retest/gemini-2.5-pro-multi-retest.json
```

The append resolves the baseline eta from sibling `eta-0.json`
automatically and computes `interval_s` from the elapsed wall clock
between the saved baseline's `started_at` and the fresh capture's
`started_at`. The loaded artifact's `identity_criterion` is preserved
verbatim across the append.

The recommended cadence for the Gemini cell specifically:

1. Day-out append (~24h after Phase 1) — captures the daily
   across-update component.
2. Week-out append (~7 days after Phase 1) — closes in on the
   2.5-week v0.10.0 timeline.
3. Two-week-out append — completes the comparison to the v0.10.0
   0.21 κ_C drift result.

Each append takes a few minutes regardless of the elapsed window.

## Caveats

- **Placeholder labels**: the analyst column is a single non-clinical
  placeholder. R22 evidence is independent of this caveat (reliability
  is intrinsic to the model's behavior), but the interpretation of
  flipped items needs to be revisited once a real pulmonologist
  panel is recruited.
- **m=1**: pulmonology's single-analyst column makes `κ_F*(β)`
  undefined; the v0.13.0 report's R22 audit cap acts only on
  worst-case across pairs.
- **Identity criterion at 1h**: the Phase 1 commitment that
  cross-update identity is asserted over the 1h window is recorded
  on faith. The v0.10.0 Gemini result is presumptive evidence that
  cross-update routing changes happen at OpenRouter at the
  multi-week scale; whether they also happen at the 1h scale is
  what Phase 1's Gemini cell will tell us.
