# Claims ledger — what has survived everything

*Started 2026-07-06. A living consolidation of the frame-anchoring research
program (captures of 2026-06-08 through 2026-07-06): every claim the program
currently stands behind, its full evidence base, its status, and what would
defeat it. The organizing distinction — the one the individual analyses bury —
is **within-configuration reliability vs. between-configuration sensitivity**.
The instrument is repeatable when its configuration is held fixed; the
elicitation configuration is itself a load-bearing parameter that must be
fixed by convention and reported. Neither half of that sentence is a defect of
the other.*

Statuses: **REPLICATED** (multiple independent captures / families) ·
**PARTIAL** (holds in some families or forms) · **ELIMINATED** (tested and
rejected) · **PENDING** (awaits an external gate).

---

## A. Within-configuration reliability (the instrument, held fixed, repeats)

**A1. Pinned-configuration test–retest reliability is high. — REPLICATED**
Evidence: v0.16.0 multi-interval R22 suite (45 cells × back-to-back / 1h /
day-out, under the v0.15.2 instrument, 0 suspected silent failures);
same-batch anchor cells reproducing at κ = 1.0 (AC1b = AC1 identical on all
35 items, 2026-07-03); cross-batch anchors within one item (24 vs 25,
generic-frame 2026-07-02); the drift-check (2026-07-02) in which a pinned
frame reproduced June's verdict row *exactly across a model update*.
Defeaters: a pinned-configuration R22 failure on a fresh capture; verdict
drift under an unchanged configuration across model updates.

**A2. Instrument failures are separable from model verdicts, and the
separation catches real errors. — REPLICATED (three episodes)**
(i) v0.14.0 silent-failure bug: empty provider responses scored as abstains;
surfaced by the reliability audit refusing a stability verdict; retracted,
re-captured (KNOWN_ISSUES_v0.14.0.md, CHANGELOG 0.15.x–0.16.0). (ii) The
2026-07-02 apparent-drift claim: a cross-frame comparison mistaken for
cross-time change; dissolved by the recorded elicitation configurations
within 23 minutes. (iii) The 2026-07-05/06 token-budget artifacts:
`budget_clipped` flags identified clipped reasoning-model outputs before any
false conclusion; affected cells re-run to a zero-clipping acceptance gate.
Defeater: an instrument artifact that reaches a published conclusion before
the provenance discipline surfaces it.

---

## B. Between-configuration sensitivity (the configuration is load-bearing)

**B1. Verdicts under thin frames are strongly sensitive to the elicitation
surface. — REPLICATED (renderings × question forms × domains × 4 families)**
Evidence: R1→R3→R4 coherence gradient 21/19–22/15/7 (gpt-4.1); S3/S4
support-side gradient; stop-sign thin-frame gradient; cross-model grids
(thin-coherence epistemic collapse in gpt-4.1/opus/gemini, thin-coherence
floor in deepseek; thin-support collapse in gpt-4.1 Δ8 and deepseek Δ10).
The variation is *structured*: directional (toward formal readings as
practice is stripped), concentrated on defeasible/contested items, and
family-specific in mode. Defeater: none sought — this is the mapped
phenomenon. Its correct reading is B4.

**B2. The sensitivity is concept-level, not lexeme-level. — REPLICATED
(single family)** Evidence: R5 normative-lexicon cell (out-of-bounds /
permissible framing, zero consistency vocabulary) reproduced the collapse
pattern (19/9/5): the lability follows the bilateral concept, not the word
"coherent". Single-family evidence (gpt-4.1); cross-model untested.
Defeater: a lexicon swap that removes the collapse under a thin frame.

**B3. Thin coherence is unreliable in every family examined. — REPLICATED
(4/4 families, two failure modes)** Evidence: cross_model_2026-07-05 +
the 2026-07-02/03 gpt-4.1 captures. Rendering-collapse (3 families) or
floor-depression (deepseek, confirmed at the 8192 budget). Consequence
already acted on: the coherence default was withheld from v0.17.6.
Defeater: a family whose thin-coherence row is stable and near the
anchored row across renderings.

**B4. Correct reading of B1–B3: E_M is a function of the entire elicitation
setup; the framework's carving-relativity is empirically load-bearing. —
REPLICATED** The instrument's response is standardization, not despair:
frames and templates as versioned components (v0.17.6), full provenance
per call, and mechanical refusal of cross-configuration comparisons — the
same move psychometrics made against question-wording effects. Defeater
(of the *reading*): evidence that the variation is chaotic rather than
structured — random across items, non-directional, unresponsive to
norm-statement. Current evidence is the opposite.

---

## C. The positive invariant (one configuration behaves like an instrument)

**C1. Explicit statement of the assessment's norms confers
rendering-robustness wherever applied. — REPLICATED (support form, 4/4
families); PARTIAL (coherence form)** Evidence: factorial (anchored
stop-sign = analyst row exactly under all renderings; clinical slope
Δ8→Δ2); generic-frame cell (domain-generality at the frame level:
24/23/21/24); cross-model grids (anchored support Δ≤3 in all four
snapshots, epistemic spread 21–24; anchored good-count ≥ thin in 16/16
cells, strictly in 12). Precisions the adversarial reviews imposed: the
*repair* is positively evidenced only where thin collapsed (gpt-4.1,
deepseek); anchoring is aggregate-dominant, not item-wise monotone (1–2
thin-good items flip in 5 cells); anchored *coherence* remains
model-dependent (epistemic 13–23 across families; deepseek Δ5).
Defeaters: a family/domain where the anchored support configuration is
rendering-fragile; or divergence from analyst verdicts under κ_C (see D1).

**C2. The anchored configuration tracks content, not just flatness. —
REPLICATED (where an analyst row exists); PENDING (clinical)** Evidence:
stop-sign anchored cells reproduce the analyst verdict row *exactly*
(good/good/good/bad) across renderings, models (12 of 13 in the June
sweep), and a model update. Flat-and-tracking, not merely flat. The
clinical generalization is exactly what the pending panel κ_C tests.
Defeater: low κ_C under every anchored configuration when the clinical
verdicts land.

**C3. The norm-statement mechanism is practice selection, not content
teaching. — Interpretive claim, consistent with all evidence** The frame
states assessment norms (no object-level inferences); its efficacy across
domains and families, and the family-specific *defaults* it overrides, fit
the reading that explicit norms select among practices the model already
commands (see the corrected Brandom framing: a pragmatic metavocabulary,
not MIE-explicitation). Held to the no-overclaiming standard: this is the
best available reading, not a measurement.

---

## D. Eliminated, unsolved, and pending

**D1. Which configuration is *valid* — PENDING (the external gate).**
Robustness ≠ validity. No clinical analyst row exists yet; all clinical
results are agreement structure. The clinician's verdicts (ingestion path
ready: `experiments/scripts/ingest_panel_verdicts.py`) adjudicate between
anchored-support and anchored-coherence via κ_C. Thin coherence is already
eliminated as a default candidate (B3).

**D2. The abstain channel — UNSOLVED.** The underdetermination clause opens
a disciplined channel (2–3 abstains/cell, no substantive flips at 3/4
renderings, anchor κ = 1.0) but is not instrument-grade: one-item
rendering-stable core (C2-the-item), location churn (Jaccard 0.2),
unresolved quantitative-exemplar cue confound, and the B/F/G good-ceiling
untouched. Withheld judgment is where clinicians live; this is the
instrument's most consequential expressive gap.

**D3. Strong internalization (ambient practice alone holds the material
reading under thin frames) — ELIMINATED.** Stop-sign gradient: the
flagship items' thin-frame rows collapse like any others; the June
replication was held by its explicit frame, not by domain familiarity.

**D4. Human comparison — PENDING (the lay factorial).** If humans show
qualitatively similar frame/rendering sensitivity, B1 is a property of
eliciting defeasible-inference verdicts as such; if humans are flat where
models swing, that is a genuine LLM-specific liability to report.

**D5. Known open items.** Anchored-coherence model-dependence (C1-partial);
deepseek sampling noise (60% unanimity — Δ≤3 within noise); budget-as-
surface observation (cross-model analysis, finding 5); sweep cannot force
thin over a benchmark binding (one-parameter fix); cross-model evidence for
B2 absent.

---

## Stop rule

No further frame/rendering cells without a specific discriminating
hypothesis. The design space walked so far (question form × frame ×
rendering × domain × family) is closed as of cross_model_2026-07-05. The
remaining gates are external: the clinical panel's verdicts (D1) and the
human factorial (D4). Model-side prompt exploration beyond this point is
thrashing and should be recognized as such.

## Honest defeat conditions for the program

Stated in advance: (1) κ_C low under every anchored configuration when the
clinical verdicts land; (2) pinned-configuration R22 degrading across model
updates; (3) humans flat where models swing. Any of these would support the
conclusion that elicited verdicts of this kind cannot anchor a robust
instrument, and the program should say so in print if they occur.
