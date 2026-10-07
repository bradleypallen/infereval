# Re-score of the stop-sign R22 sweep under the v0.17.8 verdict parser

Framework 0.17.7. No provider calls; stored `raw_response` re-parsed.
Rule: the last *committed* verdict token wins — one preceded by an explicit `Verdict:` marker or standing alone on the response's last non-empty line; otherwise the first token (pre-v0.17.8 rule).

## Blast radius across all stored results: 7 sample(s) change

| file | item | sample | first-match | v0.17.8 |
|---|---|---|---|---|
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-0.json` | row-0 | 0 | bad | good |
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-0.json` | row-0 | 1 | bad | good |
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-0.json` | row-0 | 2 | bad | good |
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-1.json` | row-0 | 1 | bad | good |
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-2.json` | row-0 | 1 | bad | good |
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-2.json` | row-0 | 2 | bad | good |
| `experiments/results/stop_sign/retest/claude-haiku-4.5-original/eta-3.json` | row-0 | 0 | bad | good |

## Cells whose verdict rows change

### claude-haiku-4.5-original

| capture | row before | row after | κ_C before | κ_C after |
|---|---|---|---|---|
| eta-0.json | B B B B | G B B B | +0.000 | +0.200 |
| eta-1.json | B B B B | B B B B | +0.000 | +0.000 |
| eta-2.json | B B B B | G B B B | +0.000 | +0.200 |
| eta-3.json | B B B B | G B B B | +0.000 | +0.200 |

| retest pair | κ before | κ after |
|---|---|---|
| eta-0 vs eta-1 | undefined | +0.000 |
| eta-0 vs eta-2 | undefined | +1.000 |
| eta-0 vs eta-3 | undefined | +1.000 |

All other 38 cells: verdict rows and κ unchanged.
