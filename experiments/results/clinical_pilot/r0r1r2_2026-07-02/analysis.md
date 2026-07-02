# R0/R1/R2 question-form × rendering evaluation — clinical pilot, 2026-07-02

**What this is.** The generalization brief's §10.1 evaluation, run live: the same
35 single-succedent (|Δ|=1) clinical-pilot items evaluated three ways with the
model snapshot and sampler config pinned identically across all three runs
(§12.1), in one session.

| run | question form | rendering | isolates |
|---|---|---|---|
| R0 | support | plain (framework default prompt) | the pre-generalization baseline |
| R1 | coherence | plain (framework default template) | the **question-form** effect (R0→R1) |
| R2 | coherence | domain (patient-framed clinical template) | the **rendering** effect (R1→R2) |

**Setup.** `gpt-4.1`, temperature 0, seed 7, max_tokens 16, 6 samples/item,
630 calls total, zero provider errors. Harness:
`experiments/scripts/r0r1r2_clinical.py`. Note R0 deliberately uses the
*framework-plain* support prompt, not the benchmark's clinical
`verification_prompt` override — plain rendering is the controlled cell, so R0
here is not byte-identical to the 2026-06-30 dry-run configuration.

## Headline numbers

| comparison | cross-run κ | mean TV | both-substantive | coverage |
|---|---|---|---|---|
| R0→R1 (question form) | **0.814** | 0.095 | 33/35 | 0.97 / 0.97 |
| R1→R2 (rendering) | **0.755** | 0.110 | 34/35 | 0.97 / **1.00** |
| R0→R2 (net) | — | — | — | 2 verdict flips |

Per §10.1 there is no accuracy key here — these are agreement measures between
configurations, and a divergence is *not* evidence that either configuration is
wrong.

## Finding 1 — the question form does real work (R0→R1: 5/35 flip)

| item | variation | R0 (support) | R1 (coherence) |
|---|---|---|---|
| A1 | strengthen | good | **bad** |
| A2 | strengthen | good | **abstain** |
| C3 | monotonicity_step | good | **bad** |
| C4 | monotonicity_step | good | **bad** |
| B6 | contested | abstain | **good** |

Under the *plain* rendering, the bilateral coherence question is systematically
**stricter** than the support question: four placeholder-good items (two
strengthen, two mid-ladder BNP tiers) lose their endorsement. Asked whether
"commit Γ and deny ψ" is incoherent, the model grants more room to deny than it
did when asked whether ψ "follows." Per §10.1, this settles the design
question empirically: **the comfortable support surface is not verdict-equivalent
to the coherence question and cannot be offered as a mere convenience.** The
framework's standardization on `coherence` (v0.18.0) is the response the brief
prescribed for exactly this outcome.

## Finding 2 — rendering does comparable work, in the opposite direction (R1→R2: 5/35 flip)

| item | variation | R1 (plain) | R2 (domain) |
|---|---|---|---|
| A1 | strengthen | bad | **good** |
| A2 | strengthen | abstain | **good** |
| A9 | contested | bad | **good** |
| C3 | monotonicity_step | bad | **good** |
| C4 | monotonicity_step | bad | **good** |

The patient-framed clinical template **recovers four of the five R0→R1 flips**
(A1, A2, C3, C4 all return to good). The extra strictness of coherence-plain is
largely an artifact of the bare framework scaffolding ("Consider a position that
commits to…"), not of the coherence question itself: dressed as a single
clinical picture, the same question yields nearly the support-question verdicts.
The domain rendering also lifts coverage to 1.00 (no abstains).

Mean TV distance 0.110 exceeds the §8 template-equivalence tolerance (0.10):
for this model and domain, **plain vs. domain rendering are not
verdict-equivalent** — a reportable rendering effect, measured on the axis the
run was designed to isolate. (The §8 CI gate proper applies to templates offered
as interchangeable *within* a domain; plain-vs-domain is the experimental
contrast itself.)

## Finding 3 — the net effect concentrates on the contested items (R0→R2: 2/35)

Comparing the old default stack to coherence-with-domain-rendering end to end,
only two verdicts differ — and both are **contested** items, the ones authored
precisely because expert judgment was expected to split:

| item | variation | R0 | R2 |
|---|---|---|---|
| A9 | contested | bad | good |
| B6 | contested | abstain | good |

On the 29 uncontested-by-design items plus the ladders, the generalized
instrument with a domain template reproduces the legacy instrument's verdicts.

## Finding 4 — the monotonicity result is invariant to question form and rendering

Ladder verdict sequences (ascending tier order; `G`/`B`/`·` = good/bad/abstain):

| run | C (BNP) | F (fluid) | G (RS @ fixed PF) |
|---|---|---|---|
| R0 | `BBGGG` | `GGG` | `GGGGG` | 
| R1 | `BBBBG` | `GGG` | `GGGGG` |
| R2 | `BBGGG` | `GGG` | `GGGGG` |

All three ladders are **monotone under every configuration**. The coherence-plain
run moves the C-ladder's bad→good transition point up two tiers (stricter, per
Finding 1) but never inverts it. The graded-evidence finding from the dry-run is
robust to the entire elicitation axis.

## Practical implications

1. **Bind a domain template for this benchmark.** With domain rendering, the
   v0.18.0 coherence default is a near-noop on this fixture (2/35 net, both
   contested); with plain rendering it is measurably stricter (5/35). The
   clinical template used for R2 lives in the harness
   (`r0r1r2_clinical.py::ClinicalTemplate`) and should be promoted to a
   registered template for the pilot benchmark before any κ-bearing capture.
2. **Analyst verdicts should be collected under `coherence`** (the survey side
   already defaults to it, v0.17.4/v0.18.0), so the model-vs-analyst comparison
   is like-for-like on the standardized question.
3. **The contested items behave as designed** — they are where every
   configuration axis (question form, rendering) shows its residual effect, and
   they remain the items awaiting the clinician panel's verdicts.

*Diagnostic only (never a κ source, per the placeholder firewall): agreement
with the author's provisional placeholders is 19/34 (R0), 15/34 (R1),
19/34 (R2).*

## Artifacts

- `R{0,1,2}-*-eta.json` — the three evaluations (full per-sample records)
- `R{0,1,2}-*.jsonl` — per-call §12.3 audit logs (composed prompt, raw
  completion, parsed verdict, snapshot, sampler config, question_form)
- `summary.json` — the cross-run comparison numbers as computed by
  `infereval.comparison.compare_runs`
