# Stop-sign R22 retest captures (2026-06-06, v0.11.0)

Test-retest reliability evidence for three representative frontier models
against the stop-sign demonstration benchmark (`examples/stop_sign/benchmark.json`,
n=4, m=1). One model per family:

- **opus47/** — Claude Opus 4.7 (anthropic)
- **gpt41/** — GPT-4.1 (openai, the v0.5 paper-aligned anchor)
- **gemini25pro/** — Gemini 2.5 Pro (openrouter / google)

## Files

Per model:

- `<model>/eta-a.json` + `<model>/eta-a.run.jsonl` — first capture
- `<model>/eta-b.json` + `<model>/eta-b.run.jsonl` — second capture
- `<model>-retest.json` — `RetestResult` artifact from `compute_retest`

## Generation

```sh
experiments/scripts/stop_sign_r22_captures.sh
```

Uses `infereval retest --auto` (v0.11.0+) with `--n-samples 3
--temperature 0.0 --max-tokens 1024 --interval-s 0` (back-to-back).
Total cost ~72 LLM calls, under US$1.

## Headline result

All three models produced **κ = +1.000, 0 flips, stable** retests at
the back-to-back interval. The full analysis at
`experiments/results/stop_sign_2026-06-06.md` discusses what
`--interval-s 0` captures and what it doesn't — the v0.10.0
pulmonology Gemini drift result (0.21 κ_C shift across 2.5 weeks) is
a different class of variance, one that requires longer-interval
captures to surface.

## Identity criterion

Captured without `--claims`. The benchmark + endorsement config are
mechanically identical across captures (the parity check verifies
that); the analyst-substantiated portion (provider snapshot
stability, scaffolding constancy across the two back-to-back calls)
is satisfied trivially by the same-process execution of the script.
At scope ≥ `domain_D_as_sampled`, the verdict gate would cap to
`partially_defensible` until a `claims.json` declaring the
`reliability.identity_criterion` is supplied; for the demo we report
the retest κ without that machinery — the artifact's `stable`
verdict is correct as-is at `items_in_benchmark` scope, which is the
right scope for the paper's worked example.

## v0.13.0 demo: retest-aware report layout

`report-demo-opus47.md` (added in v0.13.0) shows the new §2 layout
applied to the opus47 capture: §2 is split into two co-equal
subheaded blocks — `### Agreement` (cov / κ_C / κ_F / κ_F\*) and
`### Reliability (R22)` (test-retest). The bundled `claims-demo.json`
is the claims file used to generate it (single-interval back-to-back
shape; `MultiIntervalRetestResult` rendering will be demonstrated
with real captures in v0.14.0). Regenerate with:

```sh
infereval report \
  --evaluation experiments/results/stop_sign/retest/opus47/eta-a.json \
  --benchmark examples/stop_sign/benchmark.json \
  --claims experiments/results/stop_sign/retest/claims-demo.json \
  --retest experiments/results/stop_sign/retest/opus47-retest.json \
  -o experiments/results/stop_sign/retest/report-demo-opus47.md
```
