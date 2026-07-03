# Underdetermination clause — the abstain channel opens without flooding; not yet an instrument-grade fix

**Question.** The anchored-coherence cell (2026-07-02) produced 0 UNCLEAR in 840
samples: the frame licenses no *underdetermined* verdict, so abstain-designed
items were forced substantive. Does adding an explicit underdetermination
clause open a functioning abstain channel — without opening an R4-style
hedging floodgate?

**Setup.** `defeasible-coherence-underdet-v1` differs from
`defeasible-coherence-explicit-v1` by exactly two things (asserted by diff in
pre-flight): the UNCLEAR gloss gains an underdetermination clause ("the
commitments bear on what the position denies but neither ordinarily settle it
nor defeat it, so competent reasoners could disagree") and a parallel third
exemplar (unusually-heavy bird → UNCLEAR). One batch, `gpt-4.1`, temp 0,
seed 7, 6 samples/item. Same-batch drift anchor: explicit-v1/plain re-run
(AC1b) reproduced yesterday's AC1 **identically on all 35 items** (κ 1.0).

## Result

| frame | plain | situational | epistemic | domain |
|---|---|---|---|---|
| explicit-v1 (2026-07-02) | 24/11/**0** | 23/12/**0** | 23/12/**0** | 25/10/**0** |
| **underdet-v1 (this run)** | 23/9/**3** | 22/10/**3** | 21/11/**3** | 25/8/**2** |

(good/bad/abstain of 35.)

1. **The channel opens, and it is disciplined.** 62/840 samples UNCLEAR
   (7.4%); 2–3 item-level abstains per cell — no floodgate, including under
   the epistemic stress rendering. At plain/situational/domain there are
   **zero** substantive flips against the explicit-v1 cells (verified
   per-item): every difference is a substantive verdict moving to abstain.
   The epistemic cell has one real flip (G1 good→bad; κ 0.93). Note only the
   plain contrast has a same-batch control; the other three compare against
   yesterday's batch, so "no flips" there bounds gloss-effect *plus* any
   cross-batch drift (which the anchor measured at zero for plain).
2. **The unanimous, rendering-invariant core is one item.** C2 is 6/6 UNCLEAR
   in all four cells — and this is the strongest evidence the channel
   functions: under explicit-v1, C2's substantive verdict was
   rendering-*labile* (good at plain, bad at situational/domain); the clause
   converts an unstable forced verdict into a stable abstain. A0 and A5 are
   unanimous but epistemic-only; A4 reaches abstain twice via a 3–3 tie-break
   (fragile); D1 and C3 are single-cell 4/6.
3. **Where the channel points churns with rendering.** Only C2 is common to
   all four cells; the plain and epistemic abstain sets overlap at Jaccard
   0.2. Abstain *volume* is rendering-stable; abstain *location* is not —
   the same rendering-sensitivity the instrument exists to detect, now
   appearing inside the abstain channel.
4. **No accuracy grading is licensed.** The analyst panel's verdicts are
   pending, and the placeholder firewall bars construction-time expectations
   from carrying evidential weight. Descriptively: of the six items that ever
   abstain, three are abstain-designed by construction (A0, C2, D1) and three
   are good-designed (A4, A5, C3); seven abstain-designed items never abstain
   (A9, D2, D3, B0, B5, B8, G1). Whether any of these verdicts is *correct*
   awaits analyst κ_C.
5. **An exemplar-cue confound is unresolved — and locally inseparable.** The
   robust fires sit on quantitative-magnitude wording (grey-zone BNP ranges
   for C2/C3; large-volume fluids/effusions for A4/A5) matching the
   "unusually heavy" exemplar. In this domain those are also the genuinely
   contested grey zones, so surface cue and real underdetermination cannot be
   separated on this data (A0, with no quantifier, shows the channel is not
   purely cue-driven; max_tokens=16 leaves no rationales to inspect).
   Discriminating the two needs abstain-designed items *without* magnitude
   qualifiers — a benchmark-side follow-up.
6. **The B/F/G good-ceiling is untouched** — all four B/G abstain-designed
   items still come back good in nearly every cell. This is the pre-existing
   frame saturation documented yesterday, not a property of the abstain
   channel; no one-clause gloss was going to reach it.

## Conclusion

As *mechanics*, the design change works: a one-clause license plus one
exemplar opens an abstain channel that does not destabilize substantive
verdicts — the practice-selection lever extends to the abstain norm, and the
C2 case shows it doing exactly what an abstain channel is for (converting a
rendering-labile forced verdict into a stable "genuinely open"). As an
*instrument-grade fix* it falls short on this evidence: the rendering-stable
core is a single item, coverage of the abstain-designed set is thin and
partially off-design, the exemplar-cue confound is uncontrolled, and the
coherence frame's sub-domain ceiling is out of the clause's reach. Scope:
one model, one snapshot, one batch.

**Instrument guidance.** Do not fold `underdet-v1` into a library default
yet. The candidate path: (a) exemplars spanning non-quantitative
underdetermination (to break the cue confound), (b) higher n_samples where
tie-breaks decide abstains, (c) benchmark-side abstain items without
magnitude qualifiers, (d) the whole frame choice gated on analyst κ_C once
the panel's verdicts land — which will also adjudicate the three-way
B6-style divergences between anchored regimes.

## Artifacts

- `AC1b-anchoredcoherence-plain-anchorrun-eta.json` + `.jsonl` — same-batch
  drift anchor (reproduces AC1 exactly)
- `UD{1,3,4,2}-underdetcoherence-{plain,situational,epistemic,domain}-eta.json`
  + per-sample `.jsonl` logs
- `summary.json` — mixes, per-item verdicts, by-variation stratification,
  abstain item lists, both system texts, cross-run comparisons
