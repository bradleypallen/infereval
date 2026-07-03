# Generic anchored frame on the clinical items — domain-generality recovered

**Question.** R3–R5 showed domain-generality is unrecoverable at the *rendering*
level. The frame×rendering factorial showed frame anchoring dominates. Does a
fully **generic** anchored frame (`defeasible-explicit-v1`: "ordinary reasoner",
bird-flies example, zero domain lexicon) protect the *clinical* items as well as
the domain-flavored clinical frame does?

**Answer: yes.** (`gpt-4.1`, temp 0, seed 7, 6 samples/item, one batch;
cross-batch anchor cell reproduced the factorial's anchored-clinical-plain
within noise: 25 vs 24 of 35.)

Items endorsed (good, of 35):

| frame | plain | situational | epistemic | domain |
|---|---|---|---|---|
| thin (factorial) | 23 | 18 | 15 | 18 |
| anchored-clinical (factorial) | 24 | 23 | 22 | 22 |
| **anchored-generic (this run)** | **24** | **23** | **21** | **24** |

The generic row tracks the domain-flavored row cell-for-cell (max gap 1–2
items); its rendering slope is Δ3 vs the thin row's Δ8. One texture difference:
the generic frame produces a few abstains (4–7 per cell) where the clinical
frame produced none — slightly more hedging at equal endorsement.

## Conclusion

**One generic materiality-anchored frame serves both domains tested.** The §0
domain-generality ambition, lost at the rendering level, is recovered at the
frame level: what the material reading needs is an explicit statement of the
assessment's norms (defeasible, absent-further-information, BAD = positively
defeated), not domain vocabulary. Per-domain frames and templates become
refinement, not validity equipment — on the support form; the anchored
*coherence* frame remains the open cell.

**Instrument recommendation:** adopt a generic defeasibility-anchored system
prompt as the framework's default support frame (a deliberate default change —
its own release + back-compat notes), and extend the same explicit
norm-statement (practice-selection) move to the coherence frame, gated by its
own R-cell.

## Artifacts

- `clinical--genericanchored--{plain,situational,epistemic,domain}-eta.json` + logs
- `clinical--anchoredclinical--plain-anchorrun-eta.json` — cross-batch anchor
- `summary.json` — mixes + per-item verdicts
