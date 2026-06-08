# Pulmonary edema cross-family sweep (2026-06-06, benchmark v0.2)

A refreshed 6-model evaluation against the demonstration-stage pulmonary-edema differential benchmark (`examples/pulmonary_edema/benchmark.json`) after the v0.10.0 edit that added one cross-cutting marker-inference item (`x3` = ARDS + sepsis → elevated BNP). Same provider + model_id panel and same parameters as the v0.1 capture at `pulmonology_2026-05-19.md`, so the two analyses are directly comparable modulo benchmark version.

> **The benchmark labels are placeholder, not clinical.** See `examples/pulmonary_edema/README.md` for the full caveat. Everything below describes the *framework producing coherent values* against `pulmonary-edema-differential-v0.2`, **not** model agreement with a real pulmonologist's practice. Interpretation paragraphs would change substantially once the real respondent's labels arrive.

> **Comparison to v0.1**: see `pulmonology_2026-05-19.md` for the prior snapshot. The archived 29-item etas + run.jsonl files are at `experiments/results/pulmonology/archive-29-items-v0.1/`.

## Setup

- **Benchmark**: `examples/pulmonary_edema/benchmark.json` v0.2 (**30 items**, 20 bearers, m = 1). One new cross-cutting item over v0.1: `x3` (ARDS + sepsis → ↑BNP, placeholder verdict `bad`, dialectical-medium).
- **Verification prompt**: the benchmark's embedded `defeasible-clinical-v1` template (unchanged from v0.1).
- **Parameters**: `n_samples=3`, `max_tokens=1024`, `temperature=0.0` (provider-side patches from v0.1 still applied — see Framework patches in the v0.1 analysis).
- **Models** (identical panel to v0.1):

| Model | Provider | Wall time |
|---|---|---:|
| GPT-4.1 | openai | 0:49 |
| Claude Opus 4.7 | anthropic | 2:19 |
| Qwen3-max | openrouter | 3:30 |
| GPT-5.5 | openai | 5:50 |
| DeepSeek v4-pro | openrouter | 14:28 |
| Gemini 2.5 Pro | openrouter | 15:35 |

Total wall time ~42 min sequential, vs ~30 min in the v0.1 capture — the OpenRouter providers (DeepSeek, Gemini) were noticeably slower today.

## Headline metrics

| Model | Coverage | κ_C (vs placeholder) | κ_F | Substantive agreement | Δ vs v0.1 κ_C |
|---|---:|---:|---:|---:|---:|
| **GPT-5.5** | 1.0000 | **+0.6667** | +0.6571 | **25/30 (83.3%)** | −0.046 |
| **GPT-4.1** (anchor) | 1.0000 | +0.6667 | +0.6571 | 25/30 (83.3%) | +0.016 |
| **Gemini 2.5 Pro** | 1.0000 | +0.5714 | +0.5694 | 24/30 (80.0%) | **−0.207** |
| **Claude Opus 4.7** | 1.0000 | +0.5532 | +0.5286 | 23/30 (76.7%) | +0.018 |
| **DeepSeek v4-pro** | 1.0000 | +0.5000 | +0.4643 | 22/30 (73.3%) | −0.036 |
| **Qwen3-max** | 0.6667 | **+0.8864** | +0.8860 | 19/20 substantive | +0.068 |

`κ_F*` (inter-analyst Fleiss baseline) is **undefined** for all rows — m = 1.

The headline movers from v0.1 → v0.2:

- **Gemini 2.5 Pro drops 0.207 κ_C** — the largest single-model shift. v0.1 had Gemini at 26/29 (89.7%); v0.2 has it at 24/30 (80.0%). The disagreement set widened by 2 items (most notably `x3 = GOOD` against placeholder `BAD`, and `x7 = GOOD` against placeholder `BAD`). Whether this is genuine recapture variance against an unchanged prompt or a shift in Gemini's underlying behavior since 2026-05-19 is impossible to tell from one snapshot; the `n_samples=3` majority vote does not give us per-sample CIs at this scale. Worth a follow-up retest run.
- **GPT-4.1 and GPT-5.5 are now tied** at +0.6667 / 25 agreements. In v0.1 GPT-5.5 led GPT-4.1 by 0.06; the v0.2 capture has them converged. GPT-4.1 made the same call as v0.1 on every old item plus chose `bad` on the new `x3` (matching placeholder). GPT-5.5 also said `bad` on x3 but flipped one other item relative to v0.1.
- **Qwen3-max's κ_C climbs to +0.8864** — the highest in the panel and a slight increase over v0.1's +0.8189. But coverage *dropped* from 0.7931 to 0.6667: Qwen now abstains on **10 of 30 items**, including the new `x3`. The κ-vs-coverage tension flagged in the v0.1 analysis is even more acute here.

## The new x3 item: panel breakdown

`x3` = `{ards, sep}` → `{el}` ("ARDS + sepsis → elevated BNP"), placeholder verdict `bad`.

| Model | Verdict | Reading |
|---|---|---|
| GPT-4.1 | `bad` | matches placeholder; the strict "pure ARDS doesn't elevate BNP even with sepsis" reading |
| GPT-5.5 | `bad` | same |
| Claude Opus 4.7 | `bad` | same |
| DeepSeek v4-pro | `bad` | same |
| **Gemini 2.5 Pro** | **`good`** | minority of one; takes the sepsis-induced-cardiomyopathy path |
| Qwen3-max | `abstain` | declines to commit |

Four-of-five substantive verdicts side with the strict reading; Gemini alone takes the dialectical-medium-by-design alternative. The methodological work the x3 item was authored to do — **surface the sepsis-induced-cardiomyopathy confounder as a content-attributional split** — is visibly happening: a single model out of six reaches a defensible-but-non-strict reading on this exact pivot. Whether the *real* pulmonologist respondent will side with the strict reading (placeholder + 4 models), the defeasible reading (Gemini), or some middle ground depending on how strictly they read "documented sepsis" is exactly the dialectical refinement the Elenchus study is designed to surface.

Importantly, x3 did *not* land in the unanimous-disagreement bucket: only two items remain there.

## Unanimous model-vs-placeholder disagreements

Two items where all six models, across four families, reject the placeholder verdict. Both carry over from v0.1:

- **a9** — `{bi, ad, cd}` → `{ards}`, placeholder *good*, all six *not-good* (5 `bad`, Qwen `abstain`). v0.1 flagged this as a likely placeholder error: the bearer text `cd` reads "the patient recently received chemotherapy with a cardiotoxic agent" — cardiotoxic chemotherapy is canonically associated with **cardiogenic** edema via cardiomyopathy, not with ARDS. The unanimous v0.1 herd reading replicates in v0.2.
- **a10** — `{bi, ad, asp, lv}` → `{ards}`, placeholder *good*, all six *bad*. Genuinely contested in the literature — strict-Berlin reading (the "not fully explained by cardiac failure" exclusion) supports `bad`; defeasible-practice reading where aspiration "fully explains" the picture supports `good`. The six-model herd takes the strict reading.

The `c10` item (`{bi, ad, el, sep}` → `{cpe}`, placeholder *good*) — the BNP-in-sepsis case that the v0.1 analysis flagged as 5-vs-1 with GPT-5.5 alone siding with the placeholder — **keeps the same split in v0.2**. GPT-5.5 still says `good`; the other five say `bad` (Qwen abstains). The strict-reading-vs-defeasible-reading divide that the v0.1 analysis surfaced is stable across capture sessions.

The `x3` item (newly added) joined this dialectical-tension class but did not deepen it into unanimous disagreement.

## Inter-model herd coherence

| Quantity | v0.2 | v0.1 | Δ |
|---|---:|---:|---:|
| (A) Fleiss κ over {6 models + analyst}, 7 raters | +0.5729 | +0.6589 | −0.086 |
| (B) Fleiss κ over {6 models}, 6 raters | **+0.5805** | **+0.6760** | −0.096 |
| mean pairwise Cohen κ, model-model | +0.7467 | ≈ +0.78 | −0.03 |
| mean pairwise Cohen κ, model-analyst | +0.6407 | ≈ +0.68 | −0.04 |

The cross-family herd coherence is **lower** in v0.2 than v0.1, by ~0.10 on Fleiss. The most direct driver is Gemini 2.5 Pro: when one model in a 6-model panel drops from 0.78 κ to 0.57 against the placeholder, that mass automatically pulls the cross-model κ_F down as well. Two readings worth keeping:

1. **The benchmark remains discriminative.** The cross-family herd κ at +0.5805 is well below the LLM-as-judge canonical 0.75-0.90 band, even more so than v0.1's +0.6760. The benchmark separates models rather than washing them out, and the added x3 item didn't compress the score range.
2. **The analyst stays inside the model-spread.** Mean model-model κ (0.7467) sits close to mean model-analyst κ (0.6407), continuing v0.1's pattern — the placeholder analyst is not an outlier compared to the model panel. This cuts the same way against the deflationary "models just agree with each other because of training-data overlap" claim; whether it survives real respondent labels is a separate question.

## Qwen3-max's abstention discipline expands

| | v0.1 (29 items) | v0.2 (30 items) |
|---|---:|---:|
| Items where Qwen abstains | 6 | **10** |
| Abstain rate | 20.7% | 33.3% |
| Substantive items | 23 | 20 |
| Substantive agreement with placeholder | 19/23 = 82.6% | 19/20 = 95.0% |
| κ_C on substantive subset | +0.8189 | +0.8864 |

Qwen extends its abstention behavior in the v0.2 capture, abstaining on every item where any *other* model abstained in v0.1 *plus* four more: `c1` (base inference!), `a4`, `a5`, `x3`. On `x3` specifically, abstaining is methodologically right — it's the item designed to expose dialectical tension. On `c1` (the bare T1 base inference, `{bi, ad}` → `{cpe}`) it's striking: Qwen is now declining to commit on the canonical "bilateral infiltrates + acute dyspnea ⇒ cardiogenic edema" case that the other five models all call *good* and the placeholder labels *good*. That looks like over-cautious behavior on this specific run rather than principled abstention, and is worth a follow-up retest to see whether it replicates.

The interpretive tension the v0.1 analysis flagged sharpens here: Qwen has the highest κ_C (+0.8864) but the lowest raw agreement (19/30 raw) because abstain never matches a substantive analyst label. The methodology paper section on "how should a metric reward a model that says 'I can't judge'" gains another concrete data point.

## Items that would benefit from explicit clinician adjudication

Surfaced by the cross-model pattern in v0.2; the focused list for a future Elenchus pass:

| item | placeholder | model pattern | what to ask |
|---|---|---|---|
| **a9** | good | all 5 substantive bad; Qwen abstain | Likely placeholder error per the v0.1 analysis. "Cardiotoxic" → cardiogenic (CPE), not ARDS. |
| **a10** | good | all 6 bad | Strict-Berlin reading (bad) vs defeasible reading (good). Which? |
| **c10** | good | 5/6 bad, GPT-5.5 good | BNP elevation in sepsis is confounded — clean CPE marker, or contaminated? Stable split across v0.1 and v0.2. |
| **x3** (new) | bad | 4/5 substantive bad; Gemini good, Qwen abstain | Does "documented sepsis" alongside ARDS license invoking sepsis-induced cardiomyopathy as a BNP-elevation pathway? The placeholder says no; Gemini says yes. |
| **c1, a1** | both good | mixed | Same `{bi, ad}` premises, opposite conclusions both marked good. Base-case ambiguity. Now sharper: Qwen abstains on c1, picks good on a1. |
| **Qwen-abstain set** | 10 items | Qwen abstains; others split | Six items (c1, c10, a4, a5, a6, a9, x2, x3, x5, x7) where Qwen abstains. On x3 abstention is methodologically appropriate; on c1 it looks over-cautious. |

## Reproducibility

All six evaluation JSONs and JSONL audit logs are in `experiments/results/pulmonology/`. Each carries `benchmark_id="pulmonary-edema-differential-v0.2"` and the `benchmark_hash` matching the source file at commit time. To reproduce:

```bash
# Set the API keys
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
export OPENROUTER_API_KEY=...

# Run all 6
experiments/scripts/rerun_pulmonology_cross_family.sh
```

The script is the canonical rerun harness; the v0.1 capture used the same provider/model_id combinations.

## What changed at the framework level since v0.1

The v0.1 analysis was captured against framework v0.2.x. The v0.2 capture runs against framework v0.10.0 (post v0.9.x survey + decomposition work). No provider patches were needed; the issue-#16 / #18 / #20 / #22 fixes from the v0.1 sweep are all in the v0.10.0 codebase. The framework itself produces equivalent metrics on equivalent etas across the version delta.

## Caveats unchanged from v0.1

1. **m = 1.** Single-analyst panel; inter-analyst Fleiss `κ_F*` is undefined per Remark 4.
2. **Placeholder labels.** The cross-family numbers describe the framework producing coherent values, not model agreement with a real pulmonologist.
3. **Reference annotations** are best-effort by a non-clinician; the new `x3` reference flags this explicitly with `FLAG FOR PULMONOLOGIST REVIEW`.

## Silent-failure audit (v0.15.0)

Run via `infereval audit experiments/results/pulmonology/qwen3-max-eta.json`.
Heuristic: a sample is flagged when `parsed_verdict == ABSTAIN` AND
(`raw_response` is empty OR `wall_time_ms in (0, None)`). See
[`KNOWN_ISSUES_v0.14.0.md`](../../KNOWN_ISSUES_v0.14.0.md) at the repo
root for the underlying bug analysis.

| Cell | Samples scanned | Suspected silent failures | Coverage (published) | Coverage (recomputed) | κ_C (published) | κ_C (recomputed) |
|---|---|---|---|---|---|---|
| pulmonary / qwen3-max (v0.10.0) | 90 | 8 (8.9% of samples) | 0.6667 | 0.7333 | 0.8864 | 0.8053 |
| pulmonary / qwen3-max (v0.1 archive) | 87 | 0 | 0.7931 | 0.7931 | 0.8189 | 0.8189 |

The v0.10.0 capture has 8 silent failures concentrated on 5 items
(c10, a5, a6, x3, x4). Coverage rises after exclusion because items
that flipped to ABSTAIN under the bug recover their substantive
verdict; κ_C falls because the spurious-ABSTAIN agreement with
ABSTAIN-coded analysts (none, here, so the exclusion just shrinks the
substantive denominator) is removed. The v0.1 capture predates the
burst-parallel orchestration that triggers OpenRouter rate-limit
empty bodies and is silent-failure-clean.

The non-qwen3-max pulmonology cells from v0.10.0 had silent failure
rates below 1% per the KNOWN_ISSUES_v0.14.0.md audit table; their
published findings stand unmodified.

The above table will be regenerated cleanly in v0.16.0 after the pulm
day-out re-run with `--max-parallel 1` and v0.15.0 framework
(provider_error field + per-evaluate logger + retry-on-empty); until
then this audit is the authoritative reconciliation for the qwen3-max
cell.
