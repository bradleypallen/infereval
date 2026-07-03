# Stop-sign rendering-gradient control — and the cross-update drift it uncovered

**Intended question.** The clinical R-series showed material judgment collapsing
under practice-stripped renderings. The internalization hypothesis predicts the
stop-sign benchmark — a maximally ambient practice — shows a *flat* gradient:
rewording cannot strip a practice the model carries internally. This capture ran
the full 3-frame (support / coherence / normative) × 3-rendering (plain /
situational / epistemic) grid on the 4 stop-sign items (`gpt-4.1`, temperature 0,
seed 7, 6 samples/item; per-item grid, not κ, at n=4).

**What it found instead.** The control's intended reading is unevaluable as
designed, because **the baseline itself has drifted**: today's `gpt-4.1` no
longer reproduces the analyst row even in the legacy configuration.

## The grid (analyst row: good, good, good, bad)

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

No clinical-style monotone rendering collapse is visible (within-frame match
counts are non-monotone), but neither is the predicted "flat at the analyst
row": rows 0–1 wobble item-locally across frames and renderings, and row-2 is
uniformly bad. Interpretation of the *gradient* is deferred — the signal is
swamped by a baseline shift, documented next.

## Forensic chain: the baseline moved

1. **June 8 (v0.16.0 bundled capture, day-out stable through June 9):**
   `good, good, good, bad` — the analyst row — at temperature 0, n=3,
   max_tokens 2048, no seed, default support prompt.
2. **Today, byte-exact same configuration** (same prompt constants — verified
   byte-identical to the v0.16.0 tree — same params, same benchmark, same API
   string): `good, bad, bad, bad`, unanimous 3/3 votes per item.
3. **Mechanism candidate #1 — construal flip on the ambiguous "a is red"
   (intrinsic → perceptual default): REFUTED.** Today's canonical row matches
   June's *perceptual*-variant row exactly (`good, bad, bad, bad`), which
   suggested a default-reading shift — but re-running today under the
   disambiguated δ variants gives `good, bad, bad, bad` for **both** the
   intrinsic wording ("a has the standard color of stop signs") and the
   perceptual wording. Nighttime is patently irrelevant to intrinsic color;
   June's model knew it (good); today's does not.
4. **Mechanism, as localized:** today's model endorses **only the zero-side-
   premise item** (row-0) and treats *any* premise addition — irrelevant
   (nighttime), stress-test (non-reflective at night), or genuine defeater
   (painted blue) — as defeating. The June model discriminated irrelevant
   additions from genuine defeaters; the July model does not. In the
   framework's terms this is an **RSR collapse**: the range of subjunctive
   robustness of the stop-sign→red inference has contracted to (near) empty.

Instrument-side causes are excluded: prompt constants byte-identical since
v0.16.0, the v0.17.2 back-compat gate pins the support path's rendered prompt,
configs byte-matched, all parses clean and unanimous. This is **model-side
cross-update drift under the fixed "gpt-4.1" API string** between 2026-06-08 and
2026-07-02.

## Implications

1. **The headline replication claim is snapshot-relative.** "12 of 13 frontier
   models reproduce the analyst row" was true of the June 8–9 snapshots; it is
   false of today's `gpt-4.1` under identical elicitation. Any use of that
   result must carry its capture date — precisely the discipline the identity
   criterion / R22 machinery imposes, now vindicated on the flagship example
   itself (the prior precedent was the pulmonology across-update drift).
2. **A unifying observation across today's evidence:** the July model is
   globally more denial-prone than the June model. The R-series showed added
   *epistemic hedges* suppress endorsement; the drift shows added *premises*
   suppress endorsement; the grid shows the coherence/normative frames suppress
   further. One candidate description: a raised endorsement threshold — any
   complication (extra premise, uncertainty marker, abstraction) now reads as
   grounds to withhold. Hypothesis only; discriminating it from a targeted RSR
   change needs the cross-model re-capture.
3. **The internalization control must be re-run as a same-snapshot comparison.**
   Comparing today's stop-sign gradient to June's baseline confounds drift with
   rendering. The valid design compares the stop-sign gradient to the clinical
   gradient *within* today's snapshot — on that comparison, note, stop-sign
   shows no monotone collapse where clinical did, which is weakly consistent
   with internalization, but the row-2 floor and small n forbid a strong claim.
4. **Within-day R-series conclusions are unaffected.** Every R0–R5/S-cell
   comparison was same-day, same-snapshot, drift-anchored (κ 0.88–1.0 anchors).
   The drift finding *strengthens* the case for that discipline.

## Proposed follow-up

Re-run the 13-model stop-sign suite (12 calls per model) against today's
snapshots to re-index the replication table by date — turning the flagship
result into what the methodology says it must be: a time-series of
snapshot-indexed measurements rather than a standing fact.

## Artifacts

- `{support,coherence,normative}-{plain,situational,epistemic}-eta.json` + run
  logs — the 9-cell grid
- `drift-check-historical-config-eta.json` — today's model, June's byte-exact
  configuration
- `drift-check-variant-{1,2}-eta.json` — no-op paraphrase-flag runs (canonical
  δ; the benchmark carries no paraphrases — retained for completeness)
- `drift-check-{intrinsic,perceptual}-delta-eta.json` — the δ-disambiguated
  mechanism test
- `summary.json` — the grid + match counts
