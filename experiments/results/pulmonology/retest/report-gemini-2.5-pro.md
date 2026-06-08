# Construct-validity report

> ## ⚠️ ARTIFACT WARNING — the day-out pair (interval 101843s) in this report is instrumentation artifact, not real model behavior.
>
> This report was rendered against `gemini-2.5-pro-multi-retest.json` which contains 3 pairs (Phase 1 back-to-back + Phase 1 1h + Phase 2 day-out). The day-out pair shows κ=undefined / 29-of-30 flips and the R22 audit cap fires correctly *given the data*. But the data is artifact: 86 of 90 day-out samples are silent API failures (empty `raw_response`, `wall_time_ms=0`) that the v0.14.0 framework's provider code returned during a burst-parallel sweep that exceeded OpenRouter's rate limits. The framework's endorsement parser maps empty responses to ABSTAIN; the aggregator counted 29 fake abstentions as real model decisions.
>
> The first two pairs (back-to-back + 1h) are clean (0 + 1 silent failures). The Gemini 2.5 Pro cell's actual day-out reliability is currently unknown.
>
> See `KNOWN_ISSUES_v0.14.0.md` at the repo root for the three underlying framework bugs and the v0.15.0 fix plan. After v0.15.0 ships, this cell will be re-captured with `--max-parallel 1` (sequential) and the day-out evidence becomes measurable.
>
> The report itself demonstrates a real property — the v0.13.0 retest-aware report's R22 audit cap fires correctly on the worst-case interval — but the audit-cap demonstration here is technically a demonstration of the cap firing on artifact data, not on real model drift.
>
> ---

_Generated: 2026-06-08T01:51:36.767308+00:00_

## 1. Identity

- **Evaluation**: `retest-auto-0f33413c-0`
- **Benchmark**: `pulmonary-edema-differential-v0.2`
- **Model**: `openrouter` / `google/gemini-2.5-pro`
- **Run started**: 2026-06-06T21:24:59.126599+00:00
- **Items**: 30
- **Analysts**: 1

## 2. Summary metrics

### Agreement

- **Coverage**: 1.0000
- **Cohen's κ_C (vs consensus)**: +0.5714
- **Fleiss' κ_F**: +0.5694
- **Inter-analyst κ_F\***: undefined

### Reliability (R22)

- **Baseline run**: `retest-auto-0f33413c-0` (benchmark `pulmonary-edema-differential-v0.2`).

| Interval (s) | Later run | κ vs baseline | Flips | Verdict |
|---:|---|---:|---:|---|
| 1203 | `retest-auto-0f33413c-1` | +1.0000 | 0/30 | stable |
| 5814 | `retest-auto-0f33413c-2` | +1.0000 | 0/30 | stable |
| 101843 | `retest-append-f987ca5b-3` | undefined | 29/30 | undefined |

- **Overall verdict**: undefined (worst-case across 3 intervals; driven by interval 101843s).
- *Every pair compared under the declared identity criterion (`provider+model_id, cross-update identity asserted, scaffolding constant`).*

## 3. Construct-validity claims (R16–R20)

**Mastery sense (R16)**: evaluative

> Mastery is operationalised as agreement with the analyst column on the pulmonary edema benchmark v0.2 (n=30, m=1 placeholder). The v0.14.0 Phase 1 R22 captures characterize within-day reliability for the v0.10.0 cross-family Gemini drift cell.

**Scope (R17)**: items_in_benchmark

> The pulmonology benchmark is still scoped narrowly (n=30, m=1 placeholder); the v0.14.0 R22 retrofit demonstrates the within-day reliability discipline at the items_in_benchmark scope.

**Constitution vs. evidence (R18)**: evidence_of_mastery

> Agreement on the pulmonology cells is evidence bearing on a mastery attribution (Allen 2026, Remark 8), not a measurement of mastery.

**Carving-indexed framing (R19)**: not acknowledged

**Reliability — identity criterion (R22, doubly-relative)**:

- Framework-substantiated: same_benchmark_hash=`True`, same_endorsement_config=`True`, same_paraphrase_variant=`True`.
- Analyst-substantiated: same_provider_model_id=`True`, cross_update_identity_asserted=`True`, same_scaffolding=`True`.

> _Unverifiable caveats:_ OpenRouter Gemini routing does not expose model-version snapshots; cross_update_identity_asserted is recorded on faith for the 1h window. The v0.10.0 2.5-week 0.21 κ_C drift is presumptive evidence of cross-update routing changes at longer time scales.

> _Rationale:_ All three captures of this cell run within the same Python orchestrator invocation against the same OpenRouter google/gemini-2.5-pro model_id, with identical EndorsementConfig (defeasible-clinical-v1 prompt embedded in benchmark, n_samples=3, temperature=0.0, max_tokens=2048) and ProviderParams. The 1h elapsed window between baseline and capture-2 captures the short-horizon across-update drift component of R22; the cleanly-stable κ=+1.000 result rules out provider-side routing changes inside the 1h window.

## 4. Evidence

Auto-collected from optional Phase 2 artifacts:

- **Structural coherence checks** (R13): NOT SUPPLIED.
- **Sensitivity sweep** (R11): NOT SUPPLIED.
- **Factor-effects model fit** (R7, R12): NOT SUPPLIED.
- **Test-retest reliability** (R22): ? (0 item(s) flipped between runs).

## 4b. Negative findings

The framework auto-collects negative findings from the supplied Phase 2 artifacts. Each item below represents a check that ran but returned a finding that *weakens or complicates* the mastery claim.

### Test-retest anomalies (R22) (30 flagged)
- Test-retest reliability (R22) at interval 101843s: test-retest κ is undefined on this comparison (degenerate agreement structure); reliability cannot be assessed from this run pair under the declared identity criterion [κ undefined, flip rate = 96.7%]
- `a1`: verdict flipped good → abstain [first seen at interval 101843s]
- `a10`: verdict flipped bad → abstain [first seen at interval 101843s]
- `a2`: verdict flipped good → abstain [first seen at interval 101843s]
- `a3`: verdict flipped good → abstain [first seen at interval 101843s]
- `a4`: verdict flipped good → abstain [first seen at interval 101843s]
- `a5`: verdict flipped good → abstain [first seen at interval 101843s]
- `a6`: verdict flipped bad → abstain [first seen at interval 101843s]
- `a7`: verdict flipped bad → abstain [first seen at interval 101843s]
- `a8`: verdict flipped bad → abstain [first seen at interval 101843s]
- `a9`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c10`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c11`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c12`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c2`: verdict flipped good → abstain [first seen at interval 101843s]
- `c3`: verdict flipped good → abstain [first seen at interval 101843s]
- `c4`: verdict flipped good → abstain [first seen at interval 101843s]
- `c5`: verdict flipped good → abstain [first seen at interval 101843s]
- `c6`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c7`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c8`: verdict flipped bad → abstain [first seen at interval 101843s]
- `c9`: verdict flipped good → abstain [first seen at interval 101843s]
- `x1`: verdict flipped good → abstain [first seen at interval 101843s]
- `x2`: verdict flipped bad → abstain [first seen at interval 101843s]
- `x3`: verdict flipped good → abstain [first seen at interval 101843s]
- `x4`: verdict flipped good → abstain [first seen at interval 101843s]
- `x5`: verdict flipped good → abstain [first seen at interval 101843s]
- `x6`: verdict flipped good → abstain [first seen at interval 101843s]
- `x7`: verdict flipped good → abstain [first seen at interval 101843s]
- `x8`: verdict flipped good → abstain [first seen at interval 101843s]


## 5. Unaddressed competing explanations

The following checks were NOT run. Each omission weakens the defensibility of the corresponding mastery claim:

- **Paraphrase sweep run** (`paraphrase_sweep_run`)
- **Sensitivity sweep run** (`sensitivity_sweep_run`)
- **Structural check run** (`structural_check_run`)
- **Cross panel check run** (`cross_panel_check_run`)
- **Independent reference panel used** (`independent_reference_panel_used`)
- **Held out items used** (`held_out_items_used`)
- **Training data separation verified** (`training_data_separation_verified`)
- **Cross domain comparison run** (`cross_domain_comparison_run`)
- **Replication attempted** (`replication_attempted`)

## 6. Summary verdict

### ⚠️ Mastery claim partially defensible at scope='items_in_benchmark' — see Unaddressed competing explanations.

- 2 of 2 required checks NOT run: ['sensitivity_sweep_run', 'structural_check_run'].
- Benchmark has m=1 analyst(s); κ_F\*(β) is undefined and there is no independent reference column. A green verdict at items_in_benchmark scope would certify agreement with a single labeler — capped at partially_defensible.
- `test_retest_run` is marked True, but the supplied multi-interval retest result has undefined κ at interval 101843s (degenerate agreement structure on the comparison column) — the check ran across 3 intervals but at least one did not produce a usable reliability estimate. Verdict capped at partially_defensible.

---

*Generated by `infereval report` (Phase 3.1, R16–R20). The verdict is computed deterministically from the claims file; the framework refuses to render a 'defensible' verdict without the corresponding competing-explanation checks.*
