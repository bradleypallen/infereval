# R3: domain-general situational rendering — a diagnostic negative result

**Question.** The R0/R1/R2 capture showed the *domain* (patient-framed) template
recovers most of the question-form verdict flips relative to the *plain*
framework template. Can a **domain-general** template do the same work — i.e.,
context-indexical wording ("You are presented with a situation in which …")
without any domain lexicon — clawing back §0 generality?

**Setup.** Same pinned configuration as the morning capture (`gpt-4.1`,
temperature 0, seed 7, 6 samples/item, 35 |Δ|=1 items; 0 provider errors).
Two cells, plus cross-comparisons against the morning etas:

- **R1b** — coherence/plain re-run, hours later: the **drift anchor**.
- **R3** — coherence/situational (`situational-generic-v1`, in
  `experiments/scripts/r3_situational.py`).

## Headline numbers

| comparison | κ | mean TV | reading |
|---|---|---|---|
| R1 ↔ R1b (drift anchor) | 0.879 | **0.043** | same-config, hours apart — the noise floor |
| R1b ↔ R3 (situational effect) | 0.614 | **0.214** | ~5× the noise floor |
| R3 ↔ R2 (vs domain template) | 0.512 | 0.262 | R3 did **not** converge toward R2 |
| R0 ↔ R3 (vs legacy) | 0.602 | 0.219 | nor toward the legacy baseline |

**The answer to the design question is no — not with this wording.** The
situational-generic template is not an intermediate between plain and domain
rendering; it is a **third regime**, more divergent from every other
configuration than any of them are from each other.

## Direction of the shift, and the ladder break

Verdict mix per run: R0 22 good / 12 bad · R1b 22 / 13 · R2 24 / 11 ·
**R3 15 / 20**. Every R1b→R3 flip is good→bad (A1, A2, B5, B6, G1, G2, G4).
And the G ladder — same P/F, escalating respiratory support — records the
**first monotonicity violation observed anywhere in this program**:

| run | C | F | G |
|---|---|---|---|
| R1b | `BBBGG` monotone | `GGG` monotone | `GGGGG` monotone |
| R3 | `BBBGG` monotone | `GGG` monotone | **`BBGBG` violated** |

(The drift anchor also shows C4 flipping between the two same-config plain runs
— borderline mid-ladder items sit at drift-level stability, consistent with the
morning finding that C3/C4 are the question-form-sensitive tiers.)

## Interpretation (hypothesis, supported but not proven by this data)

"A situation **in which the following holds**" invites a **closed-world
reading**: Γ taken as an exhaustive description of the situation. Under that
reading, denying ψ is coherent almost regardless of evidential support — ψ is
simply not part of the description — so verdicts collapse toward *bad*. This
severs exactly the defeasible, "granting the premises and absent further
information" reading the instrument is built to elicit. The domain template
escapes the trap not through clinical vocabulary per se but because "a patient"
is an **open-world entity**: a patient manifestly has unstated properties, so
the denial is judged against background knowledge rather than against the
literal description. The G-ladder violation is the clearest symptom: under a
closed-world reading, escalating "support" in the description gives no
purchase on a diagnosis that the description never mentions.

**Discriminating test (R4, next).** If the closed-world account is right, a
still-domain-general but explicitly **epistemic** framing — "a case about which
the following *has been established*; other facts about the case may be
unknown" — should restore open-world defeasibility without any domain lexicon.
If R4 behaves like R2, generality is recoverable and the framework default
template should adopt epistemic wording; if R4 behaves like R3, the domain
lexicon is doing irreplaceable work and per-domain templates (§5) are
load-bearing, not optional polish.

## Method note

This is the template-equivalence discipline (§8) doing its job: a candidate
default template, screened against a pinned baseline for ~$1 *before* being
shipped, was caught changing the semantics of the question — including breaking
a finding (ladder monotonicity) that had survived every prior configuration and
all six dry-run models. Rendering is measurement-relevant; candidate templates
must be gated, not assumed innocent.

## Artifacts

- `R1b-coherence-plain-eta.json` / `.jsonl` — drift anchor
- `R3-coherence-situational-eta.json` / `.jsonl` — situational cell
- `summary.json` — the four cross-run comparisons
