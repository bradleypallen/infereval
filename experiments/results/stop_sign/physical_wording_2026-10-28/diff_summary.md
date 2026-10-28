# Physical-wording sweep: old vs new verdict rows

New: `physical_wording_2026-10-28` (v0.17.8 parser, delta(nr) = 'retroreflective sheeting').
Old grid: `retest_rescored_v0.17.8` baselines (v0.17.8 parser, delta(nr) = 'reflective material').
The `physical` column replaces the old `intrinsic` wording — that diff is an axis replacement, not a rerun of the same cell.

| Model | wording | old row | new row | changed items |
|---|---|---|---|---|
| claude-opus-4.7 | original | G G G B | G G G B | — |
| claude-opus-4.7 | intrinsic->physical | G G G B | G G G B | — |
| claude-opus-4.7 | perceptual | G B B B | G B B B | — |
| claude-haiku-4.5 | original | G B B B | G B B B | — |
| claude-haiku-4.5 | intrinsic->physical | G G B B | G G B B | — |
| claude-haiku-4.5 | perceptual | G B B B | G B B B | — |
| deepseek-v4-flash | original | G G G B | G G G B | — |
| deepseek-v4-flash | intrinsic->physical | G G G B | G G B B | row-2 |
| deepseek-v4-flash | perceptual | G G B B | G G B B | — |
| deepseek-v4-pro | original | G G G B | G G G B | — |
| deepseek-v4-pro | intrinsic->physical | G G G B | G A A B | row-1, row-2 |
| deepseek-v4-pro | perceptual | G G B B | G B B B | row-1 |
| gemini-2.5-flash | original | G G G B | G G G B | — |
| gemini-2.5-flash | intrinsic->physical | G G G B | G G B B | row-2 |
| gemini-2.5-flash | perceptual | G G B B | G G B B | — |
| gemini-2.5-pro | original | G G G B | G G G B | — |
| gemini-2.5-pro | intrinsic->physical | G G G B | G G G B | — |
| gemini-2.5-pro | perceptual | G B B B | G G B B | row-1 |
| gpt-4.1 | original | G G G B | G G G B | — |
| gpt-4.1 | intrinsic->physical | G G G B | G G B B | row-2 |
| gpt-4.1 | perceptual | G B B B | G B G B | row-2 |
| gpt-5.4 | original | G G G B | G G G B | — |
| gpt-5.4 | intrinsic->physical | G G G B | G G G G | row-3 |
| gpt-5.4 | perceptual | G B B B | G B B B | — |
| gpt-5.4-mini | original | G G G B | G G G B | — |
| gpt-5.4-mini | intrinsic->physical | G G G G | G G B B | row-2, row-3 |
| gpt-5.4-mini | perceptual | G G G B | G G G B | — |
| mistral-small | original | G G G B | G G G B | — |
| mistral-small | intrinsic->physical | G G G B | G G G G | row-3 |
| mistral-small | perceptual | G G B B | G G G B | row-2 |
| qwen3-max->qwen3.8-max | original | G G G B | G G G B | — |
| qwen3-max->qwen3.8-max | intrinsic->physical | G G G B | G G G B | — |
| qwen3-max->qwen3.8-max | perceptual | G B B B | G B B B | — |
| qwen3.6-flash | original | G G G B | G G G B | — |
| qwen3.6-flash | intrinsic->physical | G G G B | G G G B | — |
| qwen3.6-flash | perceptual | G G B B | G B B B | row-1 |

## Thin default-frame (GPT-4.1, July gradient config)

| wording | old row | new row | note |
|---|---|---|---|
| original | G B B B | G B B B | no change |
| physical | — | G G B B | new condition (no July counterpart) |
| perceptual | — | G B B B | new condition (no July counterpart) |
