# Simonelli-nr sweep (2026-10-31): diff summary

New: `simonelli_nr_2026-10-31` (delta(nr) = Simonelli's clause verbatim). Old: `physical_wording_2026-10-28` merged n=5 etas (delta(nr) = 'retroreflective sheeting'). Same frame, parser, budgets, roster.

## 1. nr wording effect: 28 Oct vs 31 Oct (shared wordings)

| Model | wording | retroreflective (28 Oct) | Simonelli (31 Oct) | changed items | majority differs? |
|---|---|---|---|---|---|
| claude-opus-4.7 | original | G G G B | G G G B | — | no |
| claude-opus-4.7 | physical | G G G B | G G B B | row-2 | **YES** |
| claude-opus-4.7 | perceptual | G B B B | G B B B | — | no |
| claude-haiku-4.5 | original | G B B B | G B B B | — | no |
| claude-haiku-4.5 | physical | G G B B | G G B B | — | no |
| claude-haiku-4.5 | perceptual | G B B B | G B B B | — | no |
| deepseek-v4-flash | original | G G G B | G G G B | — | no |
| deepseek-v4-flash | physical | G G B B | G G B B | — | no |
| deepseek-v4-flash | perceptual | G G B B | G G B B | — | no |
| deepseek-v4-pro | original | G G G B | G G G B | — | no |
| deepseek-v4-pro | physical | G A A B | G G G B | row-1, row-2 | **YES** |
| deepseek-v4-pro | perceptual | G B B B | G A B B | row-1 | **YES** |
| gemini-2.5-flash | original | G G G B | G G G B | — | no |
| gemini-2.5-flash | physical | G G B B | G G G B | row-2 | **YES** |
| gemini-2.5-flash | perceptual | G G B B | G G B B | — | no |
| gemini-2.5-pro | original | G G G B | G G G B | — | no |
| gemini-2.5-pro | physical | G G G B | G G G B | — | no |
| gemini-2.5-pro | perceptual | G G B B | G G B B | — | no |
| gpt-4.1 | original | G G G B | G G G B | — | no |
| gpt-4.1 | physical | G G B B | G G B B | — | no |
| gpt-4.1 | perceptual | G B G B | G B B B | row-2 | **YES** |
| gpt-5.4 | original | G G G B | G G G B | — | no |
| gpt-5.4 | physical | G G G G | G G G G | — | no |
| gpt-5.4 | perceptual | G B B B | G B B B | — | no |
| gpt-5.4-mini | original | G G G B | G G G B | — | no |
| gpt-5.4-mini | physical | G G B B | G G B B | — | no |
| gpt-5.4-mini | perceptual | G G G B | G G G B | — | no |
| mistral-small | original | G G G B | G G G B | — | no |
| mistral-small | physical | G G G G | G G G G | — | no |
| mistral-small | perceptual | G G G B | G G G B | — | no |
| qwen3.8-max | original | G G G B | G G G B | — | no |
| qwen3.8-max | physical | G G G B | G G G B | — | no |
| qwen3.8-max | perceptual | G B B B | G B B B | — | no |
| qwen3.6-flash | original | G G G B | G G G B | — | no |
| qwen3.6-flash | physical | G G G B | G G G B | — | no |
| qwen3.6-flash | perceptual | G B B B | G B B B | — | no |

## 2. physical vs physical-indicative (31 Oct)

| Model | physical | physical-indicative | changed items |
|---|---|---|---|
| claude-opus-4.7 | G G B B | G G B B | — |
| claude-haiku-4.5 | G G B B | G B B B | row-1 |
| deepseek-v4-flash | G G B B | G G B B | — |
| deepseek-v4-pro | G G G B | G G G B | — |
| gemini-2.5-flash | G G G B | G G G B | — |
| gemini-2.5-pro | G G G B | G G G B | — |
| gpt-4.1 | G G B B | G G B B | — |
| gpt-5.4 | G G G G | G G G G | — |
| gpt-5.4-mini | G G B B | G G B B | — |
| mistral-small | G G G G | G G G G | — |
| qwen3.8-max | G G G B | G G G B | — |
| qwen3.6-flash | G G G B | G G G B | — |

### Pre-registered predictions (sweep_manifest.json)

- (i) physical-indicative row-1 = bad for most models: **1/12** models have row-1 bad under physical-indicative.
- (ii) gpt-5.4: physical G G G G -> physical-indicative G G G G.
- (ii) mistral-small: physical G G G G -> physical-indicative G G G G.

## 3. Thin default-frame addendum (gpt-4.1, July config)

| wording | 28 Oct (retroreflective) | 31 Oct (Simonelli) | note |
|---|---|---|---|
| original | G B B B | G B B B | no change |
| physical | G G B B | G G B B | no change |
| physical-indicative | — | G G B B | new condition (no 28 Oct counterpart) |
| perceptual | G B B B | G B B B | no change |
