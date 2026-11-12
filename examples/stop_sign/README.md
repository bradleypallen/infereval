# Stop-sign benchmark

Formalization of Simonelli's GPT-4.1 stop-sign dialogue as a single-analyst RSR-targeted benchmark.

The analyst column is Simonelli's reading of his own dialogue. The benchmark's `title`, `description` and analyst metadata keep their original wording, which refers to an unpublished manuscript ("Example 1 of Allen 2026"). They are left unchanged because the benchmark hash covers the whole file, and committed evaluations and retest baselines record that hash.

## Target inference

`<{sa}, {ra}>` — "a is a stop sign implies a is red".

## Items

| id    | premises          | conclusions | analyst verdict | kind                 |
|-------|-------------------|-------------|-----------------|----------------------|
| row-0 | {sa}              | {ra}        | good            | base inference       |
| row-1 | {sa, n}           | {ra}        | good            | irrelevant addition  |
| row-2 | {sa, nr, n}       | {ra}        | good            | irrelevant addition  |
| row-3 | {sa, ba}          | {ra}        | bad             | defeater             |

The bearers are: `sa` ("a is a stop sign"), `ra` ("a is red"), `n` ("it is nighttime"), `nr` ("a is not made with reflective material"), `ba` ("a has been painted blue").

## Validate

```
infereval validate examples/stop_sign/benchmark.json
```
