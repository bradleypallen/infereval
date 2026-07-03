# R5: normative-frame cell — the lability is the concept, not the word

**Question.** R3/R4 showed the coherence question drifting under generic
renderings, with the "coherent / without conflict" lexicon implicated as a
consistency-attractor. If that lexical story is right, replacing the frame with
Restall/Brandom **normative** vocabulary — "out of bounds", entitlement, no
consistency words — while keeping the identical bilateral commit/deny structure
and the identical three renderings, should restore robustness. It does not.

**Setup.** Same pinned session (`gpt-4.1`, temperature 0, seed 7, 6 samples/item,
35 |Δ|=1 items). Normative frame: system prompt asks whether a position is "out
of bounds by the standards of competent reasoning"; labels OUT-OF-BOUNDS /
PERMISSIBLE / UNCLEAR; decode OUT-OF-BOUNDS→good, PERMISSIBLE→bad,
UNCLEAR→abstain (same polarity as coherence's INCOHERENT→good). The three
renderings are imported byte-identical from the R0/R1/R2 and R3/R4 scripts; only
the frame differs. Same-batch coherence-plain anchor R1c↔R1b: κ = 0.94,
TV = 0.019 — the effects below are ~15–20× the drift floor.

## The two curves

Items endorsed (good = out-of-bounds/incoherent = inference holds), of 35:

| rendering | coherence frame | normative frame |
|---|---|---|
| plain | 22 | 19 |
| situational | 15 | 9 |
| epistemic | 7 | 5 |

Slope from each frame's own plain baseline:

| | coherence | normative |
|---|---|---|
| plain → situational | κ 0.614, TV 0.214 | **κ 0.451, TV 0.276** |
| plain → epistemic | κ 0.298, TV 0.371 | **κ 0.246, TV 0.395** |

**The normative frame is not more robust — it is marginally *less* robust.** The
material→permissive drift under decontextualization survives the swap to
out-of-bounds/entitlement vocabulary intact, and slightly steepens. Ladders
break under it too (F violated even at N1-plain; C/F/G degrade under N3/N4).

## The frames agree at baseline, and collapse together

At plain rendering the two bilateral lexicons agree closely (N1↔R1c: κ 0.884,
TV 0.081), differing on only three items (A1, C4, F2 — the normative frame
slightly more permissive). So "out of bounds" and "coherent" are *reading the
same bilateral judgment* when the practice is in view; they then **collapse in
the same direction** when it is stripped.

That direction is the key: both frames, decontextualized, drift toward judging
the **denial permissible** — coherence says "the position is coherent (you may
hold it)", normative says "the position is permissible (you may hold it)", and
both therefore score *bad* / fail-to-endorse. The shared attractor is not the
word "coherent"; it is that **with no practice to supply material
incompatibility, there is no ground on which denying a non-entailed ψ is out of
bounds** — under any wording. Consistency and permission are simply the two
default answers a reasoner falls back to when the material relations are not
furnished by a practice.

## What this settles

- **Rejects the lexical hypothesis.** The R3/R4 fragility is *not* an artifact
  of "coherent" ≈ consistent. Restall/Brandom's own normative vocabulary is at
  least as labile. The instability attaches to the **bilateral commit/deny
  judgment under practice-stripping**, not to a bad choice of word.
- **Strengthens the pragmatist reading of material incompatibility.** That no
  re-wording recovers the material judgment once the practice cue is removed is
  exactly what a thoroughgoing practice-constitution of material incompatibility
  predicts: material incompatibility is not detachable from practice, so it is
  not lexically rescuable either.
- **Locates the naturalness deficit precisely.** The bilateral primitive does
  not self-fix the modality, and the reason is structural, not lexical: the
  primitive is a judgment *about a position*, and a position's out-of-boundsness
  is materially underdetermined until a practice supplies the incompatibilities.

## Caveats and the next cut

One model, one domain, one polarity mapping; the normative frame is itself a
touch noisier at baseline (F ladder violated at N1-plain). The decisive
remaining test is now unambiguously the **between-subjects human factorial** — if
domain practitioners hold the material reading across renderings where the model
(under *both* framings) does not, the deficit is the model's grip on
practice-constituted incompatibility, not a fact about the bilateral form as
such. The 2×2×3 (question-form × frame × rendering) is fully specified by this
program and cheap on the stop-sign lay benchmark.

## Artifacts

- `R1c-coherence-plain-eta.json` — same-batch coherence drift anchor
- `N{1,3,4}-normative-*-eta.json` — normative frame × three renderings
- `summary.json` — the six cross-run comparisons
- Note: the normative etas record `endorsement_config.question_form = "coherence"`
  as a family marker (the library fixes the coherence question form); the run_id
  and this file identify them as the normative-lexicon variant, elicited
  directly (`experiments/scripts/r5_normative.py`).
