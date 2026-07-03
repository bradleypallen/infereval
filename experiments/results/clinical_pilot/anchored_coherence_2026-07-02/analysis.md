# Anchored coherence frame — rendering rescue confirmed; question-form equivalence refuted

**Question.** Every coherence cell this cycle (R1/R1b/R1c/R2/R3/R4) ran under the
library's thin `_COHERENCE_SYSTEM` (label contract, no material norms) and
collapsed under practice-stripping renderings (plain ~19–22 → situational 15 →
epistemic 7 good, of 35). Does the practice-selection move that rescued the
support form — an explicit-norms system prompt — rescue the bilateral coherence
question too?

**Setup.** System-only manipulation: `defeasible-coherence-explicit-v1`
transposes `defeasible-explicit-v1` clause-for-clause to commit/deny (material
coherence, NOT strict consistency, defeater semantics, bird/penguin example
bilateralized). Question line, labels, parse regex, and the INCOHERENT→good
decode are byte-identical to the library's coherence path. One batch, `gpt-4.1`,
temp 0, seed 7, 6 samples/item, 35 single-succedent items. Same-batch thin
drift anchor (R1d) reproduced the earlier thin-plain cells (vs R1b: κ 0.94,
TV 0.03; thin-plain band across the day's four captures: 19/22/21/21).

## Count-level result: the gradient flattens

| frame | plain | situational | epistemic | domain |
|---|---|---|---|---|
| thin coherence (same-day refs) | 21 (R1d) | 15 (R3) | 7 (R4) | 24 (R2) |
| **anchored coherence (this run)** | **24** | **23** | **23** | **25** |

Rendering slope Δ14 → Δ2. The frame effect is largest exactly where the thin
frame collapsed (AC4 vs R4: κ 0.27, TV 0.41) and near-zero where the domain
template already carried the practice (AC2 vs R2: κ 0.93, TV 0.02). The
mechanism is selective, not a blanket shift: AC4 restores 14 of the 15 items
that collapsed R1d→R4 (all but B5), introduces **zero** bads no thin cell had,
and leaves the 11-item thin-unanimous-bad core intact (A5 and C2 are the only
escapes, one cell each). At the count level, the practice-selection result
carries to the coherence form.

## What the flat count hides

Adversarial checks on the per-item grid put four qualifications on the record:

1. **One sub-domain is a ceiling, not a judgment.** All discrimination (the
   10–12 bads per anchored cell) lives on the A/C/D ladders. The B/F/G ladders
   (17 items) are near-uniformly INCOHERENT→good — including the
   defeat-variation item B7 (24/24 samples) and the abstain-anchored B0/B8/G1
   (variation metadata cited as construction expectations only; per the
   placeholder firewall it carries no evidential weight, and the analyst
   panel's verdicts are pending). Roughly 40% of the flat good count comes
   from a sub-ladder where the anchored coherence frame makes no distinctions.
   The thin R4 cell called B6/B7 bad, but as part of calling 26/35 bad — a
   formal-reading regime, not discrimination either; the two regimes fail on
   this sub-ladder in opposite directions.
2. **No underdetermination channel.** 0 UNCLEAR in 840 anchored samples, 0
   abstains in every anchored cell — vs the generic *support* frame's 4–7
   abstains per cell on the same items. The anchored coherence UNCLEAR gloss
   ("ill-formed or you cannot judge") licenses no *underdetermined* verdict, so
   abstain-designed items are forced substantive, inflating the good count and
   any agreement measure. This is a mechanism, not a texture note.
3. **Anchored ≠ question-form equivalent.** The contested item B6 is the
   diagnostic: **bad** under the anchored-clinical support frame (all four
   renderings), **abstain** under the generic-anchored support frame (all
   four), **good** under the anchored coherence frame (all four). B8 diverges
   similarly; B7 is a shared miss of every anchored regime. Even with explicit
   norms on both sides, the two question forms (and frame flavors) still
   embody different practices on exactly the contested/abstain-designed items.
4. **The flat count masks churn.** Anchored-rendering κ runs 0.80–0.94; four
   single-cell wobblers (A5, A9, B5, C2) offset each other so the aggregate
   stays ~24 while composition shifts.

## Conclusion

**Rendering-robustness is recovered at the frame level for the coherence form**
— the same practice-selection result as on the support side, and the day's
collapse story closes consistently: thin frames underdetermine the practice;
explicit norms select it, for either question form. **But frame anchoring does
not make the coherence form a drop-in for the support form.** On the items
designed to be hard (contested, defeat, abstain-anchor), verdicts still track
question form and frame flavor, and the coherence frame as glossed suppresses
the abstain channel entirely. Scope: one model, one snapshot, one batch
(gpt-4.1); no analyst row exists yet for these items, so everything above is
agreement structure, not accuracy.

**Instrument guidance.** (a) The v0.18.0 coherence default should be paired
with an anchored frame — the thin `_COHERENCE_SYSTEM` is demonstrably
rendering-fragile — but *which* anchored regime tracks the domain practice is
an empirical question the pending analyst verdicts (κ_C) must decide, not a
default to flip now. (b) If abstain-anchors are to function under the
coherence form, the UNCLEAR gloss needs an explicit underdetermination clause
— a design change warranting its own equivalence cell. (c) Cross-form verdict
divergence on contested items (B6/B8) is itself a finding for the survey side:
model and human elicitation must share question form *and* frame, or κ_C
compares different practices.

## Artifacts

- `R1d-coherence-plain-eta.json` + `.jsonl` — thin drift anchor (standard path)
- `AC{1,3,4,2}-anchoredcoherence-{plain,situational,epistemic,domain}-eta.json`
  + per-sample `.jsonl` logs (full user prompt, raw response, decode per call)
- `summary.json` — mixes, per-item verdicts, anchored system text, cross-run
  comparisons (κ/TV over both-substantive, coverage floors)
