# R4: epistemic-generic rendering — the discriminating test, and what it revealed

**Question.** R3 showed constitutive-generic wording ("a situation in which the
following holds") collapses endorsement, hypothesized as a closed-world reading
of Γ. R4 tests the repair that keeps full domain-generality: explicitly
**open-world epistemic** wording — "a case about which the following has been
established; **other facts about the case may be unknown**." If the closed-world
account were the whole story, R4 should behave like the domain template (R2).

**Setup.** Same pinned configuration as the day's other captures (`gpt-4.1`,
temperature 0, seed 7, 6 samples/item, 35 |Δ|=1 items, 0 provider errors).
Template `case-open-world-v1` in `experiments/scripts/r4_epistemic.py`.

## Result: the repair failed, in the same direction — and further

| comparison | κ | mean TV |
|---|---|---|
| R1b ↔ R4 (epistemic vs plain) | 0.298 | 0.371 |
| R4 ↔ R2 (vs domain template) | **0.237** | **0.438** |
| R4 ↔ R3 (vs situational) | 0.586 | 0.195 |
| R0 ↔ R4 (vs legacy) | 0.288 | 0.395 |

R4 is *closest to R3* and *farthest from the domain template it was supposed to
recover*. Endorsement across the four renderings of the **identical coherence
question** forms a clean monotone ordering:

| rendering | good | bad | abstain |
|---|---|---|---|
| R2 — "a patient with this clinical picture" | **24** | 11 | 0 |
| R1b — bare "a position that commits / denies" | 22 | 13 | 0 |
| R3 — "a situation in which the following holds" | 15 | 20 | 0 |
| R4 — "a case … other facts may be unknown" | **7** | 26 | 2 |

Under R4: all six contested items go bad, both base items go bad, the F ladder
degenerates to insufficient (`·B·`), and the G ladder goes uniformly bad. The
strengthen backbone splits: the five items whose premises include a strong
specific driver (aspiration, sepsis, transfusion, structural heart disease)
survive; the two whose added premise is weaker contextual evidence (A1, A2) do
not.

## Interpretation: the coherence question has two readings, and rendering selects between them

The pattern across R2 → R1b → R3 → R4 tracks one variable: **how strongly the
rendering foregrounds the gap between what is stated and what is true.**

- Judged **materially** — could a competent reasoner in this domain sensibly
  hold this position, granting the stated facts as defeasible evidence? —
  denying a well-supported conclusion is *out of bounds*, and the coherence
  question reproduces support-like behavior. The patient framing anchors this
  reading: a patient is an open-world entity embedded in a practice with norms
  about what clinical pictures license.
- Judged **logically** — is the position free of contradiction? — denying any
  non-entailed conclusion is *always* coherent, so endorsement collapses toward
  bad. Generic renderings drift here, and the more explicitly they mark
  epistemic openness ("other facts may be unknown"), the harder they drift:
  the hedge reads as a license for the denial.

This is a finding about the bilateral coherence question itself, not about any
one template: **material incompatibility — the notion the Hlobil–Brandom frame
is built on — is exactly what generic wording fails to hold in place.** The
model defaults to classical logical consistency unless the surface anchors the
domain's material norms. (R0's support question never faced this: its system
prompt already asks about everyday-reasoning support directly.)

## Consequences

1. **Per-domain templates are load-bearing, not polish.** The §5 registry is
   the mechanism, and the finding is the justification: a domain template's job
   is precisely to anchor the material reading of coherence. Register the
   clinical template for this benchmark before any κ-bearing capture.
2. **Do not ship either generic wording** (`situational-generic-v1`,
   `case-open-world-v1`) as a default. Both are retained in the harness scripts
   as documented negative controls.
3. **The one untested generality route** is to move the materiality anchor out
   of the template and into the *question form's frame* (system prompt) — e.g.
   instructing that coherence be judged by the standards of competent reasoning
   in the relevant domain, with stated facts taken as defeasible evidence. That
   modifies the fixed coherence framing rather than the per-domain surface, so
   it must be treated as a question-form revision (its own R-cell and
   template-equivalence gate), not a casual wording tweak.
4. **Method note.** Four renderings × one pinned model, ~$4 total, produced an
   interpretable one-variable ordering and caught two plausible default
   templates doing semantic work before shipping. This is the §8/§10.1
   discipline operating as designed, and it generalizes: any new domain's
   template should be screened this way against the plain baseline.

## Artifacts

- `R4-coherence-epistemic-eta.json` / `.jsonl` — the capture
- `summary.json` — the four cross-run comparisons
