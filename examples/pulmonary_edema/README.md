# Pulmonary edema differential benchmark

A demonstration-stage `infereval` benchmark targeting the inferential structure of cardiogenic vs. non-cardiogenic (ARDS) pulmonary edema differential diagnosis. Twenty bearers, 30 items, one analyst panel, defeasible-clinical verification prompt.

## Status

> **THIS IS A DEMONSTRATION BENCHMARK.** Analyst verdicts in this file are placeholder guesses authored without clinical credentials. The planned study will replace them with the actual respondent's verdicts, refined through Elenchus dialectical engagement. **Not for clinical use.**

The benchmark file is reference-annotated as of v0.2.2 — every item carries a citation pointing to the guideline section, clinical-trial paper, or regulatory document that justifies the placeholder verdict. The annotations are best-effort by a non-clinician; the real respondent should treat them as a starting point and adjust freely.

Items `a9` and `x3` carry explicit `FLAG FOR PULMONOLOGIST REVIEW` references. `a9` notes that the bearer's wording ("cardiotoxic agent") points to cardiogenic, not ARDS — the unanimous cross-family model disagreement supports revisiting the verdict. `x3` (new in this benchmark's `v0.2`) probes the sepsis-induced cardiomyopathy confounder in ARDS-side BNP reasoning; the placeholder verdict is `bad` but a real pulmonologist may want to adjust depending on how strictly they read "documented sepsis" as implying possible septic cardiomyopathy.

## Bearers (20)

The bearer set covers presenting signs, biomarkers, imaging findings, hemodynamic measurements, etiologic causes, and the two target diagnoses. See the `bearers` block in `benchmark.json` for the canonical list.

## Target inferences

| target | premises          | conclusion | tags |
|--------|-------------------|------------|------|
| T1     | `{bi, ad}`        | `{cpe}`    | base cardiogenic inference |
| T2     | `{bi, ad}`        | `{ards}`   | base non-cardiogenic inference |

Items probe the RSR (range of subjunctive robustness) around each target with defeaters (e.g. ↓LVEF defeats ARDS; normal BNP defeats CPE), supporters (P/F < 300 supports ARDS; ↑BNP supports CPE), and mixed-evidence cases the methodology is expected to do dialectical work on.

Cross-cutting items (`x1`-`x8`) probe inferential relationships between the two conditions and their typical markers.

## Verification prompt

The benchmark embeds a `defeasible-clinical-v1` verification prompt that explicitly frames the task in defeasible-inference terms (with a "bird flies / penguin flies" example for grounding), overriding the framework's domain-agnostic default.

## Reference annotations

Three levels of citation provenance (per Issue #18, shipped in v0.2.2):

- **Benchmark.references** (6): Berlin definition (Ranieri 2012), Ware & Matthay NEJM 2005, Maisel NEJM 2002 (BNP), 2022 AHA/ACC/HFSA HF guideline, 2021 ESC HF guideline, Allen 2026 (this methodology).
- **Bearer.references** (7/20): the bearers whose definitions derive from a specific source — `ards`, `pf`, `el`, `nl`, `pcwp`, `kb`, `bp`.
- **BenchmarkItem.references** (30/30): every item anchored to the literature justifying its placeholder verdict.

## Run it

```bash
infereval validate examples/pulmonary_edema/benchmark.json
infereval describe examples/pulmonary_edema/benchmark.json

# Live run against any provider — requires the relevant API key in env.
infereval evaluate examples/pulmonary_edema/benchmark.json \
  --provider openai --model gpt-4.1 \
  --n-samples 3 --temperature 0.0 --max-tokens 1024 \
  --log /tmp/pulm-run.jsonl \
  -o /tmp/pulm-eta.json
```

Pre-computed evaluations against six frontier models from four families (GPT-4.1, GPT-5.5, Claude Opus 4.7, Gemini 2.5 Pro, DeepSeek v4-pro, Qwen3-max) live alongside this file in `experiments/results/pulmonology/`. See `experiments/results/pulmonology_2026-05-19.md` for the cross-family analysis.

## Reproducibility

The committed evaluation files were generated against framework versions 0.2.1 (Opus, after issue #16 fix), 0.2.3 (GPT-5.5, after issue #20 fix), and 0.2.0+ (the others). Re-running today on 0.2.4+ will produce equivalent (modulo provider non-determinism) evaluations whose `references` arrays are now correctly propagated (per issue #22) — the committed files predate that fix and therefore have empty `references` arrays at the evaluation level, even though the source benchmark carries them.

## Caveats

1. **m = 1.** Single-analyst panel; inter-analyst Fleiss `κ_F*` is undefined per the paper's Remark 4. A second pulmonologist labeling the same items would convert this from a demonstration into a research-grade dataset.
2. **Placeholder labels.** See the `analysts[0].notes` field in `benchmark.json`. The cross-family κ numbers in `pulmonology_2026-05-19.md` are about the framework producing coherent values, not about the models matching a real pulmonologist's practice.
3. **Reference annotations** are best-effort by a non-clinician. Treat them as starting points for the real respondent to adjust.
