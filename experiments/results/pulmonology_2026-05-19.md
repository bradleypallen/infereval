# Pulmonary edema cross-family sweep (2026-05-19)

A 6-model evaluation against the demonstration-stage pulmonary-edema differential benchmark (`examples/pulmonary_edema/benchmark.json`). Three frontier-model families, two OpenAI generations, one cross-family panel.

> **The benchmark labels are placeholder, not clinical.** See `examples/pulmonary_edema/README.md` for the full caveat. Everything below describes the *framework producing coherent values*, **not** model agreement with a real pulmonologist's practice. The interpretation paragraphs below would change substantially once the real respondent's labels arrive.

> **Snapshot caveat (v0.10.0):** this analysis describes the 6-model sweep against the **29-item v0.1** of the benchmark. v0.10.0 added a 30th item (`x3` — ARDS + sepsis → elevated BNP, dialectical-medium marker-inference) and bumped the benchmark id to `pulmonary-edema-differential-v0.2`. The captured eta + run.jsonl files are preserved at `experiments/results/pulmonology/archive-29-items-v0.1/`. A refreshed 30-item cross-family sweep against benchmark v0.2 is **pending** — see `experiments/scripts/rerun_pulmonology_cross_family.sh`.

## Setup

- **Benchmark**: `examples/pulmonary_edema/benchmark.json` **v0.1** (29 items, 20 bearers, m = 1). v0.10.0+ ships v0.2 (30 items); see snapshot caveat above.
- **Verification prompt**: the benchmark's embedded `defeasible-clinical-v1` template, which spells out defeasible-not-deductive semantics in the clinical idiom and includes a bird-flies / penguin-flies grounding example.
- **Parameters**: `n_samples=3`, `max_tokens=1024`, `temperature=0.0` (except where the provider rejected it — see "Framework patches" below).
- **Models** (one flagship per family, plus GPT-4.1 as anchor and GPT-5.5 as the newest OpenAI generation):

| Model | Provider | Wall time |
|---|---|---:|
| GPT-4.1 | openai | 1:13 |
| GPT-5.5 | openai | 5:46 |
| Claude Opus 4.7 | anthropic | 2:54 |
| Gemini 2.5 Pro | openrouter | 16:01 |
| DeepSeek v4-pro | openrouter | 17:21 |
| Qwen3-max | openrouter (throttled) | 6:50 |

## Headline metrics

| Model | Coverage | κ_C | κ_F | Agreement | Notes |
|---|---:|---:|---:|---:|---|
| **Gemini 2.5 Pro** | 1.0000 | **+0.7786** | +0.7761 | **26/29 (89.7%)** | closest to placeholder labels |
| **GPT-5.5** | 1.0000 | +0.7129 | +0.7071 | 25/29 (86.2%) | breaks the unanimous c10 disagreement vs. its predecessor |
| **GPT-4.1** (anchor) | 1.0000 | +0.6506 | — | 24/29 (82.8%) | baseline |
| **Claude Opus 4.7** | 1.0000 | +0.5355 | +0.5079 | 22/29 (75.9%) | conservative-bad bias |
| **DeepSeek v4-pro** | 1.0000 | +0.5355 | +0.5079 | 22/29 (75.9%) | idiosyncratic disagreement pattern (4 unique items) |
| **Qwen3-max** | 0.7931 | **+0.8189** | +0.7981 | 21/29 (72.4%) | highest κ but only 23/29 substantive — Qwen genuinely uses ABSTAIN |

`κ_F*` (inter-analyst Fleiss baseline) is **undefined** for all rows — m = 1.

## Unanimous model-vs-placeholder disagreements

Two items where all six models, across four families, reject the placeholder verdict:

- **a9** — `{bi, ad, cd}` → `{ards}`, placeholder *good*, all six *bad*. The bearer text `cd` reads "the patient recently received chemotherapy with a cardiotoxic agent". Cardiotoxic chemotherapy (anthracyclines, trastuzumab) typically causes chemotherapy-induced **cardiomyopathy** → cardiogenic edema; drug-induced ARDS-like toxicity is associated with a different agent class (bleomycin, gemcitabine, methotrexate). The literal wording of the bearer argues *against* ARDS. **Likely a placeholder error**; the unanimous model herd appears to be reading the bearer correctly.
- **a10** — `{bi, ad, asp, lv}` → `{ards}`, placeholder *good*, all six *bad*. Genuinely contested: aspiration is a canonical ARDS etiology AND reduced LVEF triggers the Berlin "not fully explained by cardiac failure" exclusion. Strict-Berlin reading: *bad* (what the models do). Defeasible-practice reading where aspiration "fully explains" the picture: *good* (the placeholder). Both have weight in the literature.

A third item, **c10** (`{bi, ad, el, sep}` → `{cpe}`, placeholder *good*), was unanimously *bad* across the five-model sweep until GPT-5.5 was added. GPT-5.5 sides with the placeholder, breaking the unanimity. The clinical wrinkle: BNP elevation in sepsis is contaminated by sepsis-induced myocardial depression — ↑BNP in a septic patient is *not* a clean CPE indicator, so the strict reading is *bad*. GPT-5.5 took the defeasible-could-still-be-CPE path; the other five took the strict-confounded path. Worth asking the real respondent.

## Inter-model herd coherence

Two complementary computations across the six-model panel:

| Quantity | Value | Reading |
|---|---:|---|
| (A) Fleiss κ over {6 models + analyst}, 7 raters | +0.6589 | adding the analyst *lowers* the panel agreement |
| (B) Fleiss κ over {6 models}, 6 raters | **+0.6760** | cross-family herd coherence |
| mean pairwise Cohen κ, model–model | ≈ +0.78 | |
| mean pairwise Cohen κ, analyst–model | ≈ +0.68 | |

Two readings worth keeping:

1. **The benchmark is discriminative.** Most LLM-as-judge work reports cross-family herd κ in the 0.75-0.90 range; +0.676 is genuinely below that band. The benchmark separates models rather than washing them out.
2. **The analyst sits inside the model-spread, not far outside it.** Mean model-model κ (0.78) is close to mean model-analyst κ (0.68), which cuts against the deflationary "models just agree with each other because of training-data overlap" claim. Caveat: this is against placeholder labels — could move substantially when real labels arrive.

Detailed pairwise matrix in the per-evaluation JSON files.

## Qwen3-max: genuine use of ABSTAIN

Six items (c1, a4, a5, a9, x5, x7) on which Qwen3-max returns the literal string `ABSTAIN` rather than picking GOOD/BAD. Not a parse failure, not a rate-limit artifact — this is the model choosing the verification prompt's ABSTAIN option meaningfully. Five of the six items are ones where the placeholder is *good* and the other five models split or are mixed. Qwen is the only model in the panel that uses the ABSTAIN option as the verification prompt intends.

This produces an interpretive tension in the metrics: Qwen has the *highest* κ_C (+0.8189, on the 23 items where it commits) but the *lowest* raw agreement (21/29, because abstain never matches a substantive analyst label). Worth documenting in the methodology paper: how should the metric reward a model that honestly says "I can't judge"?

## Framework patches surfaced during this sweep

Three issues uncovered + fixed during these runs, each in its own patch release:

- **Issue #16 / v0.2.1**: Anthropic 503 / 504 / 529 misclassified as non-transient. First Opus run lost 22/87 samples to capacity-event 529s; coverage dropped to 0.7241. Post-fix re-run: 1.0000 coverage, 16:11 → 2:54 wall time.
- **Issue #20 / v0.2.3**: OpenAI GPT-5+ and o-series reject any non-default `temperature`. First GPT-5.5 run lost every sample to HTTP 400 until the OpenAIProvider was patched to strip the parameter for those models.
- **Issue #18 + #22 / v0.2.2 + v0.2.4**: `references` as first-class on benchmarks (#18) and propagating into the evaluation JSON (#22), so the demonstration corpus can be lifted toward research-grade provenance in-place.

## Reproducibility

All six evaluation JSONs and their JSONL audit logs are in `experiments/results/pulmonology/`. Each carries the `benchmark_hash` matching the source file at commit time. To reproduce:

```bash
# Anthropic / OpenAI (sequential, no rate-limit concern)
infereval evaluate examples/pulmonary_edema/benchmark.json \
  --provider anthropic --model claude-opus-4-7 \
  --n-samples 3 --temperature 0.0 --max-tokens 1024 \
  -o /tmp/opus-eta.json --log /tmp/opus-run.jsonl

# Qwen3-max via OpenRouter: needs throttling. OpenRouter rate-limits
# qwen/qwen3-max to 20 rpm. The CLI alone can't do this; use the
# wrapper script committed at experiments/run_pulm_qwen_throttled.py
# (forthcoming) or set min_interval_s=3.5 in a Python harness.
```

## Items that would benefit from explicit clinician adjudication

Surfaced by the cross-model pattern; collected here so a future Elenchus pass has a focused starting list:

| item | placeholder | model pattern | what to ask |
|---|---|---|---|
| **a9** | good | all 6 bad | Did you intend "cardiotoxic" (→ CPE) or "any chemotherapy" (→ possibly ARDS)? Probable placeholder error. |
| **a10** | good | all 6 bad | Strict-Berlin reading (bad, "not fully explained by cardiac failure") vs defeasible reading where aspiration is the precipitant (good). Which? |
| **a8** | bad | all 6 bad | Defensible bad; just confirm the strict-Berlin reading is your intent. |
| **c10** | good | 5/6 bad, GPT-5.5 good | BNP in sepsis is confounded — is ↑BNP a clean CPE marker here, or contaminated? |
| **c1, a1** | both good | mixed | Same `{bi, ad}` premises, opposite conclusions both marked good. Defeasible "could be either" — worth flagging as the base-case ambiguity the carving is designed to expose. |
| **Qwen-abstain items** | good (5/6) | Qwen abstains | If the placeholder is correct, Qwen's abstention is methodologically appropriate (uncertainty-honest). Worth noting. |
