# Cross-model frame replication — the frame results generalize; the magnitudes were snapshot-relative

**Question.** Every 2026-07-02/03 frame finding was captured on one gpt-4.1
snapshot. Does the core 2×2×2 — {support, coherence} × {thin, anchored} ×
{plain, epistemic} — reproduce on other model families?

**Setup.** Three families: claude-opus-4-7 (Anthropic), gemini-2.5-pro and
deepseek-v4-pro (OpenRouter). 35 clinical-pilot single-succedent items, 6
samples/item, temperature 0. Support cells reuse the factorial prompt
machinery byte-identically (verified: same `prompt_hash` as the gpt-4.1
support cells); coherence cells run through the released v0.17.6
`coherence_frame` API (thin-v1 vs defeasible-coherence-explicit-v1, recorded
in each η's `endorsement_config` — this run is the API's first cross-model
exercise).

## Results (good/bad/abstain of 35; plain → epistemic)

| cell | gpt-4.1* | opus-4.7 | gemini-2.5-pro | deepseek-v4-pro |
|---|---|---|---|---|
| support, thin | 23 → 15 | 19/13/3 → 17/17/1 | 22/12/1 → 21/14/0 | 18/14/3 → 8/25/2 |
| support, anchored | 24 → 21 | 22/9/4 → 21/11/3 | 23/10/2 → 22/11/2 | 26/8/1 → 24/9/2 |
| coherence, thin | 21 → 7 | 20/14/1 → 12/21/2 | 19/15/1 → 11/23/1 | 7/25/3 → 2/29/4 |
| coherence, anchored | 24 → 23 | 21/14/0 → 22/12/1 | 21/13/1 → 19/16/0 | 18/15/2 → 13/18/4 |

\* gpt-4.1 rows are from the committed 2026-07-02/03 captures. The **support**
rows are a legitimate descriptive reference: byte-identical prompts (matching
`prompt_hash`) and the same 2048-token budget, so the comparison crosses only
model and capture day. The **coherence** rows are *separately-constructed
orientation only*: they were hand-elicited before the frame API existed, at a
16-token budget, with a different recorded configuration axis — the
framework's own setup-conformance discipline refuses that comparison, and we
do not compute or imply any gpt-4.1-vs-new-model coherence delta.

## Findings

1. **Thin coherence is unreliable in each of the four families examined — the
   strongest cross-model result of the program.** Three families collapse
   under the epistemic rendering (gpt-4.1 Δ14, opus Δ8, gemini Δ8); deepseek
   is at the floor already at the plain rendering (7 → 2, confirmed genuine
   at the 8192-token budget — not a clipping artifact). The failure modes
   differ; the upshot is uniform: no family delivers a stable material
   reading of the bilateral question under the thin frame. This retroactively
   supports the v0.17.6 decision to ship without the coherence default.
2. **Anchored support is the most robust configuration in the design space.**
   Rendering-stable (Δ ≤ 3) in each of the four snapshots, with an observed
   4-snapshot spread at the epistemic stress rendering of 21–24 (an
   observation, not a tolerance). Stated precisely: the *repair* is
   positively evidenced only where thin support actually collapsed (gpt-4.1
   Δ8, deepseek Δ10); opus (Δ2) and gemini (Δ1) had stable thin baselines, so
   for them anchoring shows non-harm, not rescue.
3. **Anchoring never hurts in aggregate, but it is not item-wise monotone and
   the coherence recovery is model-dependent.** The anchored good-count ≥
   thin in all 16 new-model cells (strictly higher in 12; a single-item +1 in
   4). Anchoring flips 1–2 thin-good items to non-good in 5 cells, so the
   dominance is aggregate, not Pareto. On the coherence side the anchored
   epistemic cells span 13–23 across families and deepseek retains a Δ5
   slope: the coherence recovery is real (deepseek +11/+11 over thin) but
   weaker and wider than the support-side stability.
4. **Where thin frames fail is model-relative; that explicit norm-statement
   confers robustness they lack held everywhere examined.** The thin-support
   collapse reproduces in 2 of 4 families; the thin-coherence unreliability
   in 4 of 4; the anchored-support stability in 4 of 4. The day-2 magnitudes
   were snapshot-relative; the practice-selection structure was not.
5. **The elicitation budget is itself elicitation surface.** Deepseek's thin
   cells *fell* when re-run with more reasoning room (support plain 21 → 18,
   epistemic 13 → 8 between the clipped 2048 and clean 8192 batches, with
   clipping only partially explaining the difference): extended deliberation
   appears to amplify the thin-frame drift toward the formal reading. Not a
   controlled comparison (the 2048 batch was contaminated); recorded as an
   observation for a budget-axis cell if ever needed.

## Instrument integrity (symmetric disclosure)

- **Budget artifacts, caught and remediated.** The initial 64-token coherence
  budget clipped every gemini coherence sample and 40 opus samples
  (`finish_reason=length` / `parse_status=budget_clipped`); those cells were
  re-run at 2048. Deepseek then showed 45 residual clipped samples at 2048
  (2 verdicts were tie-break artifacts of clipping), so its full grid was
  re-run at 8192. Final acceptance sweep: **0 budget-clipped samples and 0
  provider errors across all 24 final ηs.** The re-run triggers were the
  mechanically-identifiable artifact flags, not verdict direction; the
  recorded finish reasons made each incident diagnosable before any
  conclusion was drawn.
- **Reproducibility limits.** `seed=7` is not honored by the Anthropic API
  and is not delivering determinism via OpenRouter→deepseek. At temperature
  0, opus is 95% and gemini 86% sample-unanimous, but deepseek only 60% —
  its exact counts carry real sampling noise; treat Δ ≤ 3 comparisons
  involving deepseek as within noise. No per-cell confidence intervals are
  provided.
- **Scope.** Four model families (a convenience sample), one pinned snapshot
  each, one benchmark domain (35 single-succedent clinical items). Claims are
  enumerated ("in each of the four families examined"), not universal. No
  analyst row exists for these items (panel pending): everything here is
  agreement structure, not accuracy.

## Artifacts

- `{claude-opus-4-7,gemini-2.5-pro,deepseek-v4-pro}/<cell>-eta.json` + per-run
  `.jsonl` logs (8 cells each; opus/gemini coherence cells and the full
  deepseek grid are budget-clean re-runs, superseding in place)
- `<model>/summary.json` — mixes, per-item verdicts, gpt-4.1 reference rows
