# Frame × rendering factorial — frame anchoring dominates

**Question.** The day's program identified two levers that hold the material
reading of an inference question against collapse into formal readings:
explicit defeasibility instruction in the **frame** (system prompt), and
practice-embedding in the **rendering** (user-prompt scaffolding). This
factorial crosses them in one snapshot and one batch (no cross-batch
comparisons), support form throughout (`gpt-4.1`, temp 0, seed 7, 6
samples/item, 14 cells, ~1,800 calls).

Pre-registered outcomes: frame-dominant (anchored row flat) / additive (shifted,
slope persists) / interaction (epistemic punches through).

## Result: frame-dominant

Items endorsed (good), by cell:

**Clinical (of 35):**

| frame | plain | situational | epistemic | domain |
|---|---|---|---|---|
| thin (`default-v1`) | 23 | 18 | 15 | 18 |
| anchored (`defeasible-clinical-v1` system) | **24** | **23** | **22** | **22** |

**Stop-sign (of 4; analyst row = good/good/good/bad):**

| frame | plain | situational | epistemic |
|---|---|---|---|
| thin | 1 | 2 | 0 |
| anchored (`defeasible-explicit-v1` system) | **3** | **3** | **3** |

The stop-sign anchored cells are not merely flat — each one is the **analyst
row exactly** (`good, good, good, bad`), under all three renderings including
the epistemic hedge that collapsed everything all day. On clinical, the thin
row replicates the earlier S-series slope within-batch (23→18→15 vs 23→18→14 —
tight internal consistency), while the anchored row's slope shrinks from Δ8 to
Δ2.

## Secondary findings

1. **Rendering embedding is weak on the support form.** The patient-framed
   *domain* rendering under the thin frame (18) protects no better than the
   situational wording — practice-embedding in the user prompt alone does
   little here. (This does not contradict R2, where the patient template was
   decisive: that was the *coherence* form, whose frame has never been tested
   in an anchored variant. Open cell.)
2. **The anchored residue is item-diagnostic.** Only A4, A5 (the two weakest
   CPE strengtheners: very positive fluid balance; large effusions) and B8
   (contested-by-design) move under the anchored frame — the borderline items,
   again. Everything the thin frame lost to rendering (A1–A3, C3/C4, F2, B6,
   B8: 8 flips plain→epistemic) is recovered except these.
3. **The generic anchored frame worked perfectly on its domain.**
   `defeasible-explicit-v1` contains no traffic vocabulary (bird-flies example,
   "ordinary reasoner") and fully protected the stop-sign row. The clinical
   anchored frame is domain-flavored. Whether the *generic* anchored frame
   protects the *clinical* items is the one cell that would settle whether
   domain-generality — lost at the rendering level (R3–R5) — is recoverable at
   the frame level. Not yet run.

## Interpretation

The day's collapses were **thin-frame phenomena**. What holds the material
reading in place is not (primarily) dressing the content in a practice's
clothes, but **explicitly stating the norms of the assessment being requested**
— that the inference is to be judged defeasibly, granting the premises and
absent further information, with BAD reserved for positive defeat. Once that is
said, the rendering perturbations that dominated R3–R5 and the S-series lose
almost all their force, on both an ambient domain and a specialist one.

For the pragmatist reading this is a sharpening, not a reversal: the "practice"
a material judgment needs can be supplied by **making the norms of the game
explicit** — explicitation in Brandom's own sense — rather than by simulating
the domain's surface. The reasoner doesn't need to be dressed as a clinician;
it needs to be told, explicitly, that the assessment practice is defeasible
material inference. And this reframes the instrument guidance: the frame's
materiality instruction is the first-order validity requirement; templates are
second-order (on the support form; coherence-form anchoring untested).

## Artifacts

- `{clinical,stopsign}--{thin,anchored}--{plain,situational,epistemic[,domain]}-eta.json`
  + per-call logs — the 14 cells
- `summary.json` — endorsement mixes + full per-item verdict grids
