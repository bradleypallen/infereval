# AUMC pilot dry-run gate (2026-06-30)

**Benchmark:** `examples/AUMC_pilot/benchmark.json` (v0.5, 35 items, designed in collaboration with Dr. Lieuwe Bos, Amsterdam UMC). 11 ordinal families across CPE-supporting (BNP, EF, fluid, PV) and ARDS-supporting (PF, RS) axes. Six "ladders" organize the items: A (CPE RSR, 10), B (ARDS RSR, 9), C (BNP monotonicity, 5), F (fluid monotonicity, 3), G (RS-at-fixed-PF monotonicity, 5), D (abstain anchors, 3).

**Framework:** `infereval` v0.16.0 (v0.15.2 framework + clean re-capture distribution). The v0.5 benchmark schema isn't yet natively supported; the stopgap converter at `examples/AUMC_pilot/convert.py` maps it onto the current `Benchmark` Pydantic model with v0.5 extras JSON-encoded into `construction_metadata.source`.

**Pre-clinician status.** All `analyst_verdicts` are placeholder `abstain`. Model-vs-analyst metrics against this stopgap panel are not meaningful and are not reported here. The dry-run's job was: (a) confirm instrument health on a fresh benchmark, (b) confirm coherent rendering of (pf, rs) clinical scenarios, (c) verify monotonicity ladders behave as designed, (d) locate the items where the model panel splits so clinician time is rationed effectively.

## Cross-family panel

Six frontier LLMs, n_samples=3 per item, temperature=0.0, max_tokens=2048:

| Provider | Model | Wall time |
|---|---|---:|
| Anthropic | claude-opus-4-7 | 250 s |
| OpenAI | gpt-4.1 | 105 s |
| OpenAI | gpt-5.5 | 594 s |
| OpenRouter | deepseek/deepseek-v4-pro | 1144 s |
| OpenRouter | google/gemini-2.5-pro | 2283 s |
| OpenRouter | qwen/qwen3-max | 456 s |

Total wall time: 38 minutes (parallel, bottlenecked by gemini-2.5-pro). Total cost: ~$4 OpenRouter list pricing.

## Instrument health: clean

`infereval audit` across all six etas:

```
samples_scanned       = 1050   (6 cells × 35 items × ~5 samples after retries)
known_provider_errors =   10   (all qwen3-max OpenRouter 429s; v0.15.2 caught them)
suspected_silent      =    0
```

Zero silent failures. Aggregator-skip excludes the 10 known qwen3-max rate-limit failures from per-item majority votes.

## Headline results

### 1. Cross-family convergence is strong: 29/35 items unanimous

29 of 35 items receive the same verdict from all six models. That's a striking convergence on a fresh, clinician-co-designed benchmark and indicates the construction is methodologically coherent — the items pick out the inferences they were designed to pick out, across vendors.

### 2. All 3 monotonicity ladders pass for all 6 models

| Ladder | Family | Target | gpt-4.1 | gpt-5.5 | opus-4.7 | gemini | dseek | qwen |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| C (5 items) | BNP up | CPE up | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| F (3 items) | fluid up | CPE up | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| G (5 items) | RS up at fixed PF=pf_mild | ARDS up | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**Zero monotonicity violations across 6 models × 3 ladders.** Every model correctly tracks the ordinal structure of evidence Bos's clinical intuition encodes: support for CPE non-decreases as BNP grades up, non-decreases as fluid balance climbs, and support for ARDS non-decreases as respiratory support escalates at fixed PaO2/FiO2. This is positive evidence about model defeasible-inferential mastery on graded clinical evidence.

The G ladder is methodologically the most interesting: it tests Bos's regularity (more support → higher P/F), explicitly recorded in `bearers_v0.5.txt` as a defeasible empirical pattern. Holding PF fixed at `pf_mild` and walking RS from hfnc → niv → imvlow → imvmiddle → imvhigh, every model treats "same P/F, escalating support" as at-least-as-severe. None of the six models commits the diagnostic error the ladder was designed to catch ("the high-support patient is less ARDS because P/F sits at mild").

### 3. The 6 contested items locate where clinician time is needed

| Item | Ladder | Variation | Placeholder | Split | What's at stake |
|---|---|---|---|---|---|
| **A0** | A | base | abstain | 1G/4B/1A | Is the CPE base inference (acute dyspnea + moderate bilateral infiltrates) too weak, or strong enough to endorse? |
| **A4** | A | strengthen | good | 4G/2B | Does fluid_verypos (very positive 24h balance) suffice as a CPE-supporting marker? GPT-4.1 + Opus reject. |
| **A8** | A | contested | bad | 5B/1G | Diuresed-negative + no effusion — DeepSeek alone endorses the "treated-CPE picture" reading. |
| **D1** | D | abstain_anchor | abstain | 1G/4B/1A | cv_minor + ad as only evidence. Designed as abstain-anchor; most models confidently reject CPE. Does the abstain anchor actually anchor abstain? |
| **B7** | B | defeat | bad | 2G/4B | **Cardiotoxic agent added — the deck's worked example.** GPT-4.1 and Qwen3-max ENDORSE ARDS despite the cardiotoxic defeater. This is the clearest defeasibility-mastery failure in the panel. |
| **B8** | B | contested | abstain | 1G/5B | Fluid_verypos as Berlin Global Definition exclusion. GPT-4.1 endorses ARDS; rest reject. |

The contested-items packet at `examples/AUMC_pilot/contested_items_for_bos_2026-06-30.md` renders each of these six in natural language with the model panel split and an empty verdict line for Bos to fill in.

## What this tells us about the panel

- **GPT-4.1** is the most aggressive endorser. It's on the GOOD side of three of the six splits (A4 BAD-reject, B7 ARDS-endorse-despite-cardiotoxic, B8 ARDS-endorse-despite-hydrostatic). Worth flagging to Bos as "model that misses defeaters."
- **Qwen3-max** is the only model that uses `abstain` non-trivially (A0, D1). Other models commit confidently even when the construction places the item at an abstain anchor.
- **Gemini 2.5 Pro** is the only model endorsing CPE on the bare A0 base. Its perceptual / generous-endorsement default surfaces here.
- **DeepSeek v4-pro** holds the unique CPE-endorsement on A8 (treated-CPE picture). May reflect a clinically valid minority reading or a model anomaly — Bos's verdict resolves.

## What's next

1. Bos reviews the 6-item packet (~15 min); his verdicts replace the placeholders for those items.
2. Re-run `convert.py` to regenerate `benchmark.json` with the new analyst verdicts.
3. Optionally extend the contested set if Bos flags additional items as worth labeling.
4. Schedule a cross-family R22 capture (Phase 1 + Phase 2 day-out) on the AUMC pilot, mirroring the existing pulmonology cell shape.

## Reproducing this dry-run

```bash
# Set provider keys; verify OpenRouter quota
curl -sS -H "Authorization: Bearer $OPENROUTER_API_KEY" https://openrouter.ai/api/v1/auth/key | jq .data.limit_remaining

# Regenerate the framework-compatible benchmark.json from v0.5 sources
python examples/AUMC_pilot/convert.py

# Run the 6-cell dry-run (~38 min wall, ~$4)
bash /tmp/aumc-dryrun/run.sh   # script preserved at experiments/results/AUMC_pilot/dryrun_2026-06-30/run.sh

# Audit each cell
for eta in experiments/results/AUMC_pilot/dryrun_2026-06-30/*-eta.json; do
  infereval audit "$eta"
done
```
