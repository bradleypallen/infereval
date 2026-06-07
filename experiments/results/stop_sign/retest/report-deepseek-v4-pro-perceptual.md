# Construct-validity report

_Generated: 2026-06-07T05:56:53.579568+00:00_

## 1. Identity

- **Evaluation**: `retest-auto-16f4c06b-0`
- **Benchmark**: `stop-sign-perceptual`
- **Model**: `openrouter` / `deepseek/deepseek-v4-pro`
- **Run started**: 2026-06-07T01:51:09.486831+00:00
- **Items**: 4
- **Analysts**: 1

## 2. Summary metrics

### Agreement

- **Coverage**: 1.0000
- **Cohen's κ_C (vs consensus)**: +0.5000
- **Fleiss' κ_F**: +0.4667
- **Inter-analyst κ_F\***: undefined

### Reliability (R22)

- **Baseline run**: `retest-auto-16f4c06b-0` (benchmark `stop-sign-perceptual`).

| Interval (s) | Later run | κ vs baseline | Flips | Verdict |
|---:|---|---:|---:|---|
| 88 | `retest-auto-16f4c06b-1` | +1.0000 | 0/4 | stable |
| 3779 | `retest-auto-16f4c06b-2` | +0.5000 | 1/4 | substantively unstable |

- **Overall verdict**: substantively unstable (worst-case across 2 intervals; driven by interval 3779s).
- *Every pair compared under the declared identity criterion (`provider+model_id, cross-update identity asserted, scaffolding constant`).*

## 3. Construct-validity claims (R16–R20)

**Mastery sense (R16)**: evaluative

> Mastery is operationalised as agreement with the analyst column on the stop-sign benchmark (Example 1 of Allen 2026), under the perceptual δ(ra) variant. The v0.14.0 Phase 1 R22 captures characterize within-day reliability for the cell.

**Scope (R17)**: items_in_benchmark

> The stop-sign demonstration benchmark is small (n=4, m=1); the v0.14.0 R22 retrofit demonstrates the within-day reliability discipline at the items_in_benchmark scope. The headline cross-family agreement claim from v0.5.18 (11/13 models reproduce Simonelli's analyst row under the original δ(ra) at κ_C = +1.00) is the empirical anchor; Phase 1 R22 supplies its reliability gloss.

**Constitution vs. evidence (R18)**: evidence_of_mastery

> Agreement on the stop-sign cells is evidence bearing on a mastery attribution (Allen 2026, Remark 8), not a measurement of mastery.

**Carving-indexed framing (R19)**: not acknowledged

**Reliability — identity criterion (R22, doubly-relative)**:

- Framework-substantiated: same_benchmark_hash=`True`, same_endorsement_config=`True`, same_paraphrase_variant=`True`.
- Analyst-substantiated: same_provider_model_id=`True`, cross_update_identity_asserted=`True`, same_scaffolding=`True`.

> _Unverifiable caveats:_ OpenRouter does not expose model-version snapshots for the DeepSeek path; cross_update_identity_asserted is recorded on faith for the 1h window. The Phase 1 1h drift result on this cell (κ=+1.000 → +0.500) is presumptive evidence that the analyst-substantiated portion of the criterion does not hold across the 1h elapsed window for this provider/model/variant combination.

> _Rationale:_ All three captures of this cell run within the same Python orchestrator invocation against the same OpenRouter deepseek/deepseek-v4-pro model_id, with identical EndorsementConfig (defeasible-explicit-v1 prompt via DEFEASIBLE_PROMPT, n_samples=3, temperature=0.0, max_tokens=2048) and ProviderParams. The variant benchmark is constructed once and reused identically across all three captures.

## 4. Evidence

Auto-collected from optional Phase 2 artifacts:

- **Structural coherence checks** (R13): NOT SUPPLIED.
- **Sensitivity sweep** (R11): NOT SUPPLIED.
- **Factor-effects model fit** (R7, R12): NOT SUPPLIED.
- **Test-retest reliability** (R22): ? (0 item(s) flipped between runs).

## 4b. Negative findings

The framework auto-collects negative findings from the supplied Phase 2 artifacts. Each item below represents a check that ran but returned a finding that *weakens or complicates* the mastery claim.

### Test-retest anomalies (R22) (2 flagged)
- Test-retest reliability (R22) at interval 3779s: test-retest reliability is substantively unstable under the declared identity criterion (κ = +0.500); 25.0% of items flipped between runs — model output for this benchmark is not reliable enough for the headline κ_C to be interpreted as signal. [κ = +0.500, flip rate = 25.0%]
- `row-1`: verdict flipped good → bad [first seen at interval 3779s]


## 5. Unaddressed competing explanations

The following checks were NOT run. Each omission weakens the defensibility of the corresponding mastery claim:

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
- `test_retest_run` is marked True, but the supplied multi-interval retest result has a substantively-unstable pair at interval 3779s (κ = +0.500, flip rate = 25.0%); the headline κ_C cannot be interpreted as signal under this reliability across the time scales captured. Verdict capped at partially_defensible.

---

*Generated by `infereval report` (Phase 3.1, R16–R20). The verdict is computed deterministically from the claims file; the framework refuses to render a 'defensible' verdict without the corresponding competing-explanation checks.*
