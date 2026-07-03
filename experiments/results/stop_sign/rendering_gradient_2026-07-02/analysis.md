# Stop-sign rendering-gradient control — CORRECTED analysis

> **Correction.** An earlier revision of this analysis claimed cross-update
> drift ("RSR collapse") in `gpt-4.1` between 2026-06-08 and 2026-07-02. That
> claim was an **instrumentation error in the comparison, not a model change**:
> the June captures used the `defeasible-explicit-v1` verification prompt, while
> the "byte-exact" re-check used the thin `default-v1` prompt. Re-run under the
> true June frame, today's model reproduces the analyst row exactly. The git
> history preserves the erroneous revision; this file states the corrected
> findings.

## The correction test

| configuration | row-0 | row-1 | row-2 | row-3 |
|---|---|---|---|---|
| June 8, `defeasible-explicit-v1` (day-out stable) | good | good | good | bad |
| **Today, `defeasible-explicit-v1` (true June frame)** | **good** | **good** | **good** | **bad** |
| Today, thin `default-v1` frame | good | bad | bad | bad |

**No drift.** Same model, same day: the difference between the second and third
rows is entirely the *frame*. `defeasible-explicit-v1` instructs that BAD means
the premises **positively rule out** the conclusion (with a bird-flies example
of default reasoning); `default-v1` says BAD means the premises "do not
support" it. Under the thin frame the nighttime rows (1–2) fail; under the
explicit-defeasibility frame the full analyst row locks in.

## How the error happened, and why it matters methodologically

The erroneous comparison verified that the *default prompt constants* were
unchanged since v0.16.0 — true but irrelevant, since the June captures did not
use the default prompt. The June η records
`endorsement_config.verification_prompt_id = "defeasible-explicit-v1"`; the
re-check η records `"default-v1"`. **The framework's retest compatibility check
(`RetestConfigMismatchError`) refuses to compare exactly this pair** — the
error was only possible because the comparison was done by hand, outside the
guardrail. The lesson is the instrument's own: cross-run claims must go through
the setup-conformance machinery, not analyst eyeball.

## Corrected findings

1. **The flagship replication is stable across the June→July model updates**
   under the elicitation frame it was defined by. The analyst row
   (good/good/good/bad) reproduces today, unanimous.
2. **The support question's material reading is frame-anchored, on the
   flagship items.** The thin default frame loses the irrelevant-premise rows
   (nighttime; nighttime + non-reflective) — the model treats added premises
   as undermining "support" — while the explicit-defeasibility frame holds
   them. This extends the day's materiality-anchoring theme (R3–R5: rendering
   and frame select between material and formal readings) to the **support**
   form and the **stop-sign** domain: even a maximally ambient practice does
   not, by itself, hold the material reading of a *thin* question frame.
3. **The 9-cell gradient grid must be reinterpreted**: all nine cells used thin
   frames (default support / bare coherence / bare normative), so the grid
   characterizes thin-frame behavior — its wobble is not evidence about
   internalization, and no drift is needed to explain any of it.
4. **The internalization hypothesis, in its strong form, is not supported**:
   ambient practice alone (stop-sign) did not keep rows 1–2 material under
   thin frames. What demonstrably holds material readings in place, on current
   evidence, is explicit materiality-anchoring in the frame (this file) and/or
   practice-embedding in the rendering (R2 vs R3/R4). Their relative
   contributions are separable in a frame × rendering design within one
   snapshot — future work.

## The grid (retained; thin-frame characterization)

Analyst row: good, good, good, bad. All cells `gpt-4.1`, temp 0, seed 7, n=6.

| cell | row-0 | row-1 | row-2 | row-3 | match |
|---|---|---|---|---|---|
| support-plain | good | bad | bad | bad | 2/4 |
| support-situational | good | good | bad | bad | 3/4 |
| support-epistemic | bad | bad | bad | bad | 1/4 |
| coherence-plain | bad | bad | bad | bad | 1/4 |
| coherence-situational | bad | good | bad | bad | 2/4 |
| coherence-epistemic | bad | good | bad | bad | 2/4 |
| normative-plain | bad | good | bad | bad | 2/4 |
| normative-situational | bad | bad | bad | bad | 1/4 |
| normative-epistemic | bad | good | bad | bad | 2/4 |

## Artifacts

- `{support,coherence,normative}-{plain,situational,epistemic}-eta.json` + logs
  — the thin-frame 9-cell grid
- `drift-check-historical-config-eta.json` — today, June *params* but the
  wrong (default) frame: the artifact that generated the retracted claim
- `drift-check-{intrinsic,perceptual}-delta-eta.json` — δ-variant runs, also
  under the wrong frame (retained; reinterpret as thin-frame δ-sensitivity)
- `drift-check-true-june-prompt-eta.json` — the correction test: today's model,
  the true June frame, analyst row reproduced
- `summary.json` — the grid + match counts
