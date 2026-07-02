# Reviewer checklist

A one-page checklist for a referee (or an author self-checking) a study that uses
`infereval`. It operationalizes the [instrument validation
walkthrough](instrument_validation.md). Each item is a yes/no a reviewer can
verify from the paper's methods + the released η / `run.jsonl`.

## Setup and provenance

- [ ] **Model snapshot pinned and recorded** — the exact snapshot, not just the
  model family (behavior drifts under a fixed API name).
- [ ] **Sampler config recorded** — `n_samples`, temperature, `max_tokens`, seed;
  identical across any runs that are compared.
- [ ] **`question_form` stated** (`support` or `coherence`) and the template id
  recorded — together they define what was asked.
- [ ] **Benchmark + bearer versions fixed** — a benchmark hash or version, so the
  items scored are the items described.

## Measurement soundness

- [ ] **`κ_C` reported against the inter-analyst baseline `κ_F*`**, not against
  1.0 — the model is only as reliable as the panel it is measured against.
- [ ] **Coverage reported per run** — and cross-run / model-vs-analyst κ is
  restricted to items substantive on both sides (the substantive index).
- [ ] **Insufficient-overlap flagged, not hidden** — a κ over a tiny both-
  substantive intersection is reported as insufficient, not as a number.
- [ ] **Failed calls distinguished from abstentions** — silent API failures are
  `provider_error`, excluded from κ, not scored as model abstention.
- [ ] **Placeholder / provisional labels excluded from κ** — `analyst_verdicts`
  is the sole reference; author guesses do not leak in.

## Reliability

- [ ] **R22 interval stated** for any reliability claim (back-to-back / hours /
  day-out / cross-update), with the identity criterion that defines "same
  instrument."
- [ ] **Claims survive R22 at the relevant interval** — a finding that flips on
  retest is not defensible.

## Robustness and consistency

- [ ] **Paraphrase / template robustness checked** — verdicts stable under
  meaning-preserving rewording (template-equivalence within tolerance).
- [ ] **Human and model asked the same question** — if the model was evaluated
  under `coherence`, the analyst survey used `--question-form coherence` too.
- [ ] **Premise-order invariance** not silently averaged over where it matters.

## Interpretation and scope

- [ ] **Operational reading, not metaphysical** — agreement is evidence of
  endorsement, not a possession-of-mastery claim.
- [ ] **Scope claim matches the sample** — benchmark / domain-as-sampled, not
  "general reasoning."
- [ ] **Monotonicity / graded-evidence findings** reported per ladder, with
  `abstain` treated as a gap (not coerced to a number).
- [ ] **Negative findings surfaced**, not smoothed over.
- [ ] **Reproducible** — η + `run.jsonl` released; the reported numbers
  recompute from them.

A study that clears this checklist has used the instrument as designed; residual
disagreement is then about the *finding*, not the *measurement*.
