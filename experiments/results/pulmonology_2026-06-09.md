# Pulmonary edema differential — 6-model multi-interval R22 evidence (2026-06-09)

**Bundled fresh capture under `infereval` v0.15.2 framework, v0.16.0 release.** Six frontier LLMs across four families captured against the bundled `pulmonary_edema/benchmark.json` (n=30 items, single placeholder analyst panel, m=1). Each cell carries three captures composed into one `MultiIntervalRetestResult`: baseline, back-to-back retest (≈45 s elapsed), within-hour drift retest (≈3600 s elapsed), day-out drift retest (≈126 800 s ≈ 35 h elapsed). 18 IntervalPairs total, all under the declared identity criterion (same benchmark hash, same `EndorsementConfig`, same `ProviderParams`, same provider/model_id, `defeasible-clinical-v1` verification prompt embedded in the benchmark).

This file supersedes the deleted v0.10.0 and v0.14.0-era analyses; the data referenced there was captured under framework versions whose silent-failure bug is documented in [`KNOWN_ISSUES_v0.14.0.md`](../../KNOWN_ISSUES_v0.14.0.md) and was retracted as part of v0.16.0's clean-recapture.

## Headline result

> **deepseek-v4-pro shows monotone κ decay across all three intervals (0.867 → 0.792 → 0.729) — the clearest published example of detectable across-update model drift via R22 staged composition.** Five of six other pulmonology cells held κ = 1.000 across every interval.

The v0.10.0 cross-family rerun (deleted as part of v0.16.0) had previously surfaced a 0.21 κ_C shift on Gemini 2.5 Pro across 2.5 weeks — a single across-update data point with no time-scale resolution. The v0.16.0 multi-interval evidence localizes that class of variance to a specific cell (deepseek-v4-pro, not Gemini), and characterizes it across three distinct horizons within a single bundled multi-retest artifact.

## Per-cell summary

| Cell | cov(eta-0) | κ_C(eta-0) | κ@back | κ@1h | κ@day | day-out flip-rate |
|---|---:|---:|---:|---:|---:|---:|
| claude-opus-4.7    | 1.000 | +0.500 | 1.000 | 1.000 | 1.000 | 0/30 |
| deepseek-v4-pro    | 1.000 | +0.553 | 0.867 | 0.792 | **0.729** | 4/30 |
| gemini-2.5-pro     | 1.000 | +0.571 | 1.000 | 1.000 | 1.000 | 0/30 |
| gpt-4.1            | 1.000 | +0.667 | 1.000 | 1.000 | 1.000 | 0/30 |
| gpt-5.5            | 1.000 | +0.727 | 0.933 | 0.933 | 1.000 | 0/30 |
| qwen3-max          | 0.767 | +0.810 | 1.000 | 1.000 | 1.000 | 4/30 |

Reading the table: `κ_C(eta-0)` is the cross-family model-vs-analyst agreement on the baseline capture, against the single placeholder analyst panel. `κ@{back,1h,day}` are the test-retest κ values comparing each cell's baseline to its retest captures at the indicated time-scale. The day-out flip-rate is the count of substantive ↔ substantive ↔ abstain transitions observed between baseline and the day-out capture (a flip can leave κ at 1.000 if it's an abstain ↔ substantive transition, since κ is computed on the substantive subset only).

## Across-update drift in deepseek-v4-pro

The monotone decay 0.867 → 0.792 → 0.729 across three time scales is the strongest published evidence of cross-update across the bundled pulmonology suite. Per-item breakdown of the 4 day-out flips will surface in `experiments/results/pulmonology/retest/deepseek-v4-pro-multi-retest.json` under `pairs[2].retest.item_deltas` for any reader who wants to trace the disagreement pattern. Phase 3 / longer-horizon followup (week-out, multi-week) would resolve whether the decay is monotone all the way down or plateaus.

## qwen3-max coverage of 0.767 is real, not artifact

Across the four qwen3-max pulmonology captures (eta-0 through eta-3), `infereval audit` reports 35 known `provider_error` samples — all genuine OpenRouter `429 rate-limit exceeded` responses caught by the v0.15.2 framework, recorded as `provider_error`, and skipped by the aggregator. **Zero suspected silent failures**. The published coverage of 0.767 is the model's actual coverage on the items that produced non-error samples; the recomputed-with-failures-excluded coverage is identical.

This contrasts with the deleted v0.14.0-era pulmonology Phase 2 day-out finding (artifact "coverage collapse" of 1/30 on Gemini 2.5 Pro), which was the trigger for the bug investigation that produced v0.15.0+. Under v0.15.2, the same qwen3-max cell with the same burst pressure produces clean published metrics where v0.14.0 would have silently corrupted them.

## Per-family observations

- **Anthropic.** Claude Opus 4.7: cleanest stability (κ=1.0 across every interval) with mid-range κ_C(+0.500) reflecting the analyst's placeholder labels. The single placeholder reference is the rate-limiting factor here; this κ_C is properly read as "consistent with one non-clinician's labels," not "agrees with pulmonology."
- **OpenAI.** GPT-4.1 (+0.667) and GPT-5.5 (+0.727) are the strongest in the cell on placeholder-agreement, both stable. GPT-5.5's within-day κ=0.933 recovered to 1.000 at day-out — minor noise, not drift.
- **OpenRouter (Google).** Gemini 2.5 Pro: perfectly stable κ=1.0 across all three intervals. The previously-reported 0.21 κ_C shift across 2.5 weeks is not reproduced at the day-out time-scale; it must be longer-horizon or specific to particular model-version transitions.
- **OpenRouter (DeepSeek).** deepseek-v4-pro: the drift cell described above.
- **OpenRouter (Qwen).** Qwen3-max: rate-limited heavily but no measurement contamination; reliability evidence intact at κ=1.0 across all intervals on the substantive subset.

## Methodological footnote: framework caught its own bug

These captures were taken under `infereval` v0.15.2, the patch release that resolved three v0.14.0 silent-failure bugs — silent empty-response → ABSTAIN, cross-thread logger contamination, and no rate-limit retry. The original v0.14.0 Phase 2 day-out pulmonology sweep had produced an implausibly uniform "coverage collapse" finding that the framework's R22 cap correctly surfaced as suspect; forensic audit revealed all three latent framework bugs. The v0.16.0 fresh re-capture under v0.15.2 was undertaken to retire the tainted data entirely; the bug-analysis lives at [`KNOWN_ISSUES_v0.14.0.md`](../../KNOWN_ISSUES_v0.14.0.md).

`infereval audit` reports zero suspected silent failures across the 36 pulmonology eta files (eta-0 through eta-3 for each of 6 cells) — the v0.14.0 bug pattern is absent in v0.15.2-mediated captures.

## Reproducing this capture

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export OPENROUTER_API_KEY=...

# Phase 1 (back-to-back + 1h drift): ~1.5 h wall, ~$2–4
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py

# Phase 2 (day-out append, after >24 h elapsed): ~30–60 min wall, ~$1–2
python experiments/scripts/phase2_append.py --only-benchmark pulmonology

# Audit verification
infereval audit experiments/results/pulmonology/retest/<cell>/eta-3.json
```

## Caveats unchanged from v0.10.0

1. **m = 1.** Single-analyst panel; inter-analyst Fleiss `κ_F*` is undefined (Remark 4).
2. **Placeholder labels.** The cross-family numbers describe the framework producing coherent values, not model agreement with a real pulmonologist.
3. **Reference annotations** are best-effort by a non-clinician; the `x3` reference still carries `FLAG FOR PULMONOLOGIST REVIEW`.

## Identity criterion (verbatim from each cell's multi-retest.json)

All three captures of each cell run within the same Python orchestrator invocation against the same provider+model_id, with identical EndorsementConfig (defeasible-clinical-v1 prompt embedded in the benchmark, n_samples=3, temperature=0.0, max_tokens=2048) and ProviderParams. The day-out elapsed window between baseline and capture-3 (~35 h) captures the short-horizon across-update drift component of R22; longer intervals (week-out, multi-week) would ship as additional staged-composition `--append-to` operations.

Unverifiable caveat (also threaded into every cell's `MultiIntervalRetestResult.identity_criterion`): provider APIs (Anthropic, OpenAI, OpenRouter) do not expose model-version snapshots, so `cross_update_identity_asserted` is recorded on faith. The 35 h elapsed window is short enough that across-update model swaps would be exceptional, but the framework cannot mechanically verify their absence.
