# Clinical pilot — contested items for clinical review

**For:** the clinician reviewer  
**Date:** 2026-06-30  
**Benchmark:** clinical_pilot v0.5 (35 items, ladders A/B/C/D/F/G)  
**Pre-clinician dry-run:** 6 frontier LLMs (Anthropic, OpenAI, Google, DeepSeek, Qwen) endorsed each item once; n_samples=3 each, temperature=0.

## Why this packet

The dry-run gate had a job: locate the items where the model panel splits, so your time is spent on items where it pays back. **29 of 35 items were unanimous across all 6 models** — those don't need your verdict yet (we'll come back to them with the full panel if needed). The 6 items below are where the panel split. Each one is a clinical reasoning question worth ~2 minutes of your time. Your verdict (good / bad / abstain) plus one sentence of rationale becomes the analyst label and replaces the placeholder.

Verdict conventions:
- **good** — granting the premises and absent further information, you would endorse the conclusion as defeasibly supported
- **bad** — the premises do not support the conclusion (either unrelated or defeated)
- **abstain** — the question is ill-formed or you cannot judge

---

## Item A0 — ladder A, variation `base`

**Clinical scenario (premises):**  
> the patient has acute dyspnea; the patient has moderate bilateral pulmonary infiltrates on imaging.

**Question:** Granting the premises above, is the inference to *"the patient has cardiogenic pulmonary edema"* defeasibly supported (good), unsupported / defeated (bad), or ill-formed (abstain)?

**Pre-clinician design intent (placeholder):** `abstain`

**Model panel verdicts (1G/4B/1A):**

| Model | Verdict |
|---|---|
| GPT-4.1 | `bad` |
| GPT-5.5 | `bad` |
| Claude Opus 4.7 | `bad` |
| Gemini 2.5 Pro | **`good`** |
| DeepSeek v4-pro | `bad` |
| Qwen3-Max | **`abstain`** |

**Your verdict:** ___________ (good / bad / abstain)

**Your rationale (one sentence):** ____________________________________________

---

## Item A4 — ladder A, variation `strengthen`

**Clinical scenario (premises):**  
> the patient has acute dyspnea; the patient has moderate bilateral pulmonary infiltrates on imaging; the patient received large-volume intravenous fluids and had a very positive fluid balance in the past 24 hours.

**Question:** Granting the premises above, is the inference to *"the patient has cardiogenic pulmonary edema"* defeasibly supported (good), unsupported / defeated (bad), or ill-formed (abstain)?

**Pre-clinician design intent (placeholder):** `good`

**Model panel verdicts (4G/2B):**

| Model | Verdict |
|---|---|
| GPT-4.1 | **`bad`** |
| GPT-5.5 | `good` |
| Claude Opus 4.7 | **`bad`** |
| Gemini 2.5 Pro | `good` |
| DeepSeek v4-pro | `good` |
| Qwen3-Max | `good` |

**Your verdict:** ___________ (good / bad / abstain)

**Your rationale (one sentence):** ____________________________________________

---

## Item A8 — ladder A, variation `contested`

**Clinical scenario (premises):**  
> the patient has acute dyspnea; the patient has moderate bilateral pulmonary infiltrates on imaging; the patient received diuretics in the past 24 hours and has a negative fluid balance; the patient has no pleural effusions.

**Question:** Granting the premises above, is the inference to *"the patient has cardiogenic pulmonary edema"* defeasibly supported (good), unsupported / defeated (bad), or ill-formed (abstain)?

**Pre-clinician design intent (placeholder):** `bad`
  → rationale: diuresed-negative + no effusion: against active CPE, or the treated-CPE picture

**Model panel verdicts (1G/5B):**

| Model | Verdict |
|---|---|
| GPT-4.1 | `bad` |
| GPT-5.5 | `bad` |
| Claude Opus 4.7 | `bad` |
| Gemini 2.5 Pro | `bad` |
| DeepSeek v4-pro | **`good`** |
| Qwen3-Max | `bad` |

**Your verdict:** ___________ (good / bad / abstain)

**Your rationale (one sentence):** ____________________________________________

---

## Item B7 — ladder B, variation `defeat`

**Clinical scenario (premises):**  
> the patient has acute dyspnea; the patient has extensive, diffuse bilateral airspace opacities on imaging; the patient recently received chemotherapy with a cardiotoxic agent such as an anthracycline or trastuzumab; the patient has a PaO2/FiO2 ratio of 100-200; the patient receives invasive ventilation with PEEP 5-10 cmH2O.

**Question:** Granting the premises above, is the inference to *"the patient has acute respiratory distress syndrome"* defeasibly supported (good), unsupported / defeated (bad), or ill-formed (abstain)?

**Pre-clinician design intent (placeholder):** `bad`
  → rationale: deck worked example: cardiotoxic -> cardiogenic, not ARDS

**Model panel verdicts (2G/4B):**

| Model | Verdict |
|---|---|
| GPT-4.1 | **`good`** |
| GPT-5.5 | `bad` |
| Claude Opus 4.7 | `bad` |
| Gemini 2.5 Pro | `bad` |
| DeepSeek v4-pro | `bad` |
| Qwen3-Max | **`good`** |

**Your verdict:** ___________ (good / bad / abstain)

**Your rationale (one sentence):** ____________________________________________

---

## Item B8 — ladder B, variation `contested`

**Clinical scenario (premises):**  
> the patient has acute dyspnea; the patient has extensive, diffuse bilateral airspace opacities on imaging; the patient received large-volume intravenous fluids and had a very positive fluid balance in the past 24 hours; the patient has a PaO2/FiO2 ratio of 100-200; the patient receives invasive ventilation with PEEP 5-10 cmH2O.

**Question:** Granting the premises above, is the inference to *"the patient has acute respiratory distress syndrome"* defeasibly supported (good), unsupported / defeated (bad), or ill-formed (abstain)?

**Pre-clinician design intent (placeholder):** `abstain`
  → rationale: very positive balance -> fluid-overload exclusion (Global Definition)

**Model panel verdicts (1G/5B):**

| Model | Verdict |
|---|---|
| GPT-4.1 | **`good`** |
| GPT-5.5 | `bad` |
| Claude Opus 4.7 | `bad` |
| Gemini 2.5 Pro | `bad` |
| DeepSeek v4-pro | `bad` |
| Qwen3-Max | `bad` |

**Your verdict:** ___________ (good / bad / abstain)

**Your rationale (one sentence):** ____________________________________________

---

## Item D1 — ladder D, variation `abstain_anchor`

**Clinical scenario (premises):**  
> the patient has acute dyspnea; the patient has cardiovascular risk factors or treated hypertension.

**Question:** Granting the premises above, is the inference to *"the patient has cardiogenic pulmonary edema"* defeasibly supported (good), unsupported / defeated (bad), or ill-formed (abstain)?

**Pre-clinician design intent (placeholder):** `abstain`

**Model panel verdicts (1G/4B/1A):**

| Model | Verdict |
|---|---|
| GPT-4.1 | `bad` |
| GPT-5.5 | `bad` |
| Claude Opus 4.7 | `bad` |
| Gemini 2.5 Pro | **`good`** |
| DeepSeek v4-pro | `bad` |
| Qwen3-Max | **`abstain`** |

**Your verdict:** ___________ (good / bad / abstain)

**Your rationale (one sentence):** ____________________________________________

---

## Quick-fill summary table (for return email or copy-paste)

| Item | Verdict | Rationale (one sentence) |
|---|---|---|
| A0 | | |
| A4 | | |
| A8 | | |
| B7 | | |
| B8 | | |
| D1 | | |

## What happens after your verdicts come back

Each verdict overwrites the `placeholder` field for that item in `benchmark_v0.5.json`. The rationale is added to a `rationales` array alongside the verdict. The benchmark is regenerated via `examples/clinical_pilot/convert.py` and downstream metrics (κ_C model-vs-clinician, monotonicity across the C/F/G ladders) become meaningful.

If any of these items strikes you as so poorly framed that no verdict is defensible — say so explicitly. That's important methodological evidence about how the benchmark needs to be repaired, and it's exactly the kind of correction the Q1/Q2 round captured for the oxygenation set.
