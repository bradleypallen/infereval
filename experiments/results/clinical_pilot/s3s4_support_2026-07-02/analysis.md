# S3/S4: the support-side rendering contrast — completing the 2×3 factorial

**Question.** R3/R4 showed the coherence question collapsing under generic
renderings. Is that fragility *specific to the bilateral question form*, or a
general property of elicitation? This capture applies the identical two
perturbations to the **unilateral support question**, completing a 2×3
question-form × rendering factorial on one pinned snapshot (`gpt-4.1`,
temperature 0, seed 7, 6 samples/item; support drift anchor R0↔S0b:
**κ = 1.0, TV = 0.014** — the effects below are 10–25× the floor).

## The factorial

Mean TV distance from each question form's plain baseline:

| | situational | epistemic |
|---|---|---|
| **support** | 0.138 (κ 0.712) | 0.248 (κ 0.553) |
| **coherence** | 0.214 (κ 0.614) | 0.371 (κ 0.298) |

Items endorsed (of 35), by cell:

| | plain | situational | epistemic |
|---|---|---|---|
| **support** | 23 | 18 | 14 |
| **coherence** | 22 | 15 | 7 |

## Findings

**1. The fragility is NOT bilateral-specific.** The support question also
degrades substantially under both perturbations — the epistemic hedge drives it
to κ 0.553 against its own plain baseline and (new) produces ladder violations
on the support side too (F `GBG`, G `GBGGG` under S4). "Does it follow, given
that other facts may be unknown?" invites *"not deductively"* — the
uncertainty-marking suppresses defeasible endorsement under **any** question
form. The strong claim "the bilateral phrasing uniquely lacks a natural
interpretation" does not survive this contrast.

**2. But the bilateral question amplifies every perturbation, consistently
≈1.5–2×.** Same direction, largely the same items (A1, A2, C3, C4, B6 recur in
both question forms' flip lists), roughly doubled magnitude: endorsement drop
plain→epistemic is −9 under support vs −15 under coherence; TV 0.248 vs 0.371;
situational likewise 0.138 vs 0.214. And at the weaker (situational)
perturbation, the ladders separate the forms cleanly: **all three ladders stay
monotone under S3, while R3 broke ladder G** — a bilateral-specific break at a
perturbation strength the support question absorbs.

**3. Two mechanisms, not one.** The factorial supports a two-factor account:

- a **general** mechanism — foregrounding the gap between what is stated and
  what is true (constitutive "situation", explicit unknowns) pushes *any*
  elicitation from material toward formal standards, suppressing defeasible
  endorsement; and
- a **bilateral-specific** mechanism — the coherence lexicon ("coherent",
  "without conflict") is additionally attractor-ed to *logical consistency*,
  under which denial of any non-entailed conclusion is cheap. This is the
  amplifier, visible as the interaction.

## Interpretive upshot (for the naturalness question)

The defensible conclusion is **graded, not binary**: the bilateral coherence
question has a *weaker* natural interpretation than the unilateral support
question — its material reading needs more contextual anchoring and fails
earlier under decontextualization — but the unilateral question is not
rendering-invariant either. Both forms lean on practice-supplied materiality;
the bilateral form simply leans harder. On the practice-implicit reading of
where material norms live, this is expected of both; what the data add is a
measured *ordering* of how much anchoring each surface form requires.

Machine-side caveat as always: one model, one domain, 35 items. The
between-subjects human version of this factorial is now sharply motivated — if
practitioners hold the material reading across all six cells where the model
does not, rendering-robustness becomes a usable dissociation between possessing
material norms and pattern-matching their expression.

## Artifacts

- `S0b-support-plain-eta.json` / `.jsonl` — support drift anchor (R0 re-run)
- `S3-support-situational-eta.json` / `.jsonl`, `S4-support-epistemic-eta.json`
  / `.jsonl` — the perturbed support cells
- `summary.json` — comparisons + the coherence-side reference numbers
