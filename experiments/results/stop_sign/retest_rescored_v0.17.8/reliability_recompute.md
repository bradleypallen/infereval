# Stop-sign R22 reliability, recomputed from stored etas

Framework 0.17.7. No provider calls. Test–retest κ via `compute_retest` (eta-0 vs eta-1/2/3).

| | original captures | re-scored (v0.17.8 parser) |
|---|---:|---:|
| κ = 1 | 95/117 | 97/117 |
| κ undefined | 8/117 | 5/117 |
| κ ∈ (0, 1) | 13/117 | 13/117 |
| κ ≤ 0 | 1/117 | 2/117 |
| cells κ = 1 at every interval | 29/39 | 29/39 |
| samples with provider_error | 36 | 36 |

## Cells not κ = 1 at every interval (re-scored)

| cell | κ@back | κ@1h | κ@day | rows eta-0…3 |
|---|---:|---:|---:|---|
| claude-haiku-4.5-original | 0.000 | 1.000 | 1.000 | G B B B / B B B B / G B B B / G B B B |
| deepseek-v4-flash-perceptual | 0.500 | 1.000 | 1.000 | G G B B / G G G B / G G B B / G G B B |
| deepseek-v4-pro-perceptual | 0.500 | 0.500 | 0.500 | G G B B / G B B B / G B B B / G B B B |
| gemini-2.5-pro-perceptual | 0.500 | 0.500 | 1.000 | G B B B / G G B B / G G B B / G B B B |
| gpt-5.4-mini-intrinsic | und | und | 0.000 | G G G G / G G G G / G G G G / G G B B |
| gpt-5.4-mini-original | 0.500 | 0.500 | 1.000 | G G G B / G G B B / G G B B / G G G B |
| gpt-5.4-mini-perceptual | 0.500 | 0.500 | 0.500 | G G G B / G G B B / G G B B / G G B B |
| qwen3-max-intrinsic | und | 1.000 | und | G G G B / A G G A / G G G B / G G G A |
| qwen3-max-original | und | 1.000 | 1.000 | G G G B / A G G A / G G G B / G G G B |
| qwen3.6-flash-perceptual | 0.500 | 1.000 | 0.500 | G G B B / G B B B / G G B B / G B B B |

## Provider failures by cell

- claude-haiku-4.5-perceptual: 1
- qwen3-max-intrinsic: 11
- qwen3-max-original: 12
- qwen3-max-perceptual: 12
