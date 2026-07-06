# Human lay factorial — design v2 (panel-reviewed)

*v1 drafted and panel-reviewed 2026-07-06 (statistics, survey methodology,
instrument fit — three independent reviewers); this v2 incorporates every
must-fix and the accepted should-fixes. Status: DESIGN — nothing is built,
recruited, or pre-registered. Execution gates: (i) user approval of scope
and budget (§4, §10), (ii) the author's institutional ethics process,
(iii) pre-registration.*

## 1. Research question

Ledger item **D4** (and pre-stated program defeat condition 3): if humans
show qualitatively similar frame/rendering sensitivity to models, the
configuration-sensitivity mapped in B1–B3 is a property of eliciting
defeasible-inference verdicts as such; if humans are flat where models
swing, it is an LLM-specific liability the instrument must report.

- **H1 (rendering, thin frame).** Under the thin frame, the epistemic
  rendering shifts lay verdicts away from the material reading.
- **H2 (frame, at the stress rendering).** At the epistemic rendering, the
  anchored frame shifts verdicts toward the material reading relative to
  thin.
- **H2b (flattening, estimated).** The frame × rendering interaction
  (anchored flattens the rendering slope). Reported with its own disclosed
  power; not a confirmatory gate (§5).
- **H3 (dissociation, descriptive vs the item-matched model grid).**

## 2. Scope decision: coherence form first (Phase 1)

**Phase 1 is the coherence-form 2×2 only** — {thin, anchored} × {plain,
epistemic}, four cells. Rationale:

1. The 4/4-family model finding (thin-coherence unreliability; anchored
   recovery) is coherence-side — it is where "humans flat where models
   swing" bites hardest.
2. The instrument-fit review established that the support-form cells
   cannot currently be built: the support survey body has **no rendering
   axis** (fixed bullet form; the template registry is ignored under
   support), the anchored support prompt (`defeasible-explicit-v1`) is
   experiment-side with no `survey_header`, and the locked v0.9.0
   thin-support header contains clinical vocabulary ("diagnostic
   inference") inappropriate for a lay benchmark. Support cells are
   **Phase 2**, gated on that instrument work (§9).
3. Four cells at properly-powered n costs what eight underpowered cells
   would have.

Elicitation surfaces are the instrument's own: headers =
`thin-v1.survey_header` (released v0.17.4 wording) and
`defeasible-coherence-explicit-v1.survey_header` (panel-reviewed);
bodies = `framework-default-v1` (plain) and `case-open-world-v1`
(epistemic) through the template registry; choice labels and decode
library-owned in every cell. The underdetermination frame is excluded
(not instrument-grade, ledger D2).

## 3. Materials — the lay benchmark (to be built and normed)

- **Target inferences (5–6 everyday ladders).** stop-sign/red,
  match-struck/lights, ice-on-road/slippery, kettle-on/water-heats,
  dropped-glass/breaks (+1 spare from norming). **bird/flies is
  excluded**, and a pre-registered authoring rule applies: *frame-exemplar
  content must be disjoint from all scored-item content* — the anchored
  header's bird/penguin worked examples would otherwise hand anchored-cell
  respondents the answers for that ladder (answer-key leakage; caught
  independently by two reviewers). Exemplars are not editable instead:
  changing them mints new frame ids and breaks the mirror to the model
  captures.
- **Item budget, reallocated for MRI stability:** per ladder — 1 base,
  **2 irrelevant-addition variants, 2 genuine-defeater variants**
  (distinct side-premise content), giving ~20–24 diagnostic items on 5–6
  ladders (one contaminated side-premise is then ≤5% of the index, and the
  item random effect has ~20+ clusters). Contested items reduced to 2–3,
  exploratory only. **No abstain-designed items in the scored set**
  (channel unsolved, ledger D2); lay Unclear-usage is a companion outcome.
- **Norming wave (pre-launch, required).** n ≈ 25 lay raters (same
  screens, excluded from the main study via Prolific exclusion chaining)
  judge each side-premise directly, outside all study surfaces: "does
  knowing this change whether the conclusion holds?" Pre-registered
  retention thresholds (e.g. ≥75% "no change" for an irrelevant addition;
  ≥75% "defeats" for a defeater); items failing norming are replaced
  before launch. Designer irrelevance-judgments are not self-certifying —
  the program's own standard is that phrasing variants are usually
  substantive perturbations.
- **Attention/quality items:** ONE exclusion-grade check — an
  instructed-response item with *positional* wording ("for this item,
  ignore the text above and select the second option"; choice order is
  fixed, so position is well-defined and form-neutral). The
  Containment-style trivial-good and trivial-bad items are **demoted to
  per-cell calibration outcomes**, not exclusion criteria: under the
  coherence form their expected answers invert (trivial-good → Incoherent,
  the negative-valence label) and an attentive lay respondent can
  legitimately stumble — their per-cell pass rates are themselves a
  polarity-comprehension measure worth reporting.
- Construction expectations in `placeholder` (firewall applies). The human
  distributions are the measurement; norming + design give them their
  diagnostic structure.

## 4. Sample and assignment

- **Assignment: ONE Prolific study → ONE Qualtrics survey** whose
  Randomizer element assigns each respondent evenly to one of the four
  cell blocks, each block built from its cell's export with sidecar
  `question_form` + `frame_id` (+ `template_id`, §9) provenance intact.
  Separate studies per cell are not random assignment (recruitment-time
  confounds; repeat workers). Consent and demographics come **before**
  randomization so attrition is observable per cell; dropout-by-cell and a
  completer covariate balance check are pre-registered.
- **Screens:** fluent English (Prolific screener), single-country pool,
  desktop-only, approval ≥98% + ≥100 submissions (acknowledged weak; the
  substantive screens are the instructed item and the norming-based item
  quality), exclusion chaining pilot → norming → main.
- **n = 70 per cell; N = 280.** Power basis rebuilt per review: MRI over
  ~20 diagnostic items; beta-binomial with p ≈ 0.6, respondent propensity
  τ ≈ 0.18, family clustering allowance → **conservative SD 0.25**.
  Primary simple-effect contrasts (H1, H2) at δ = 0.15: power ≈ 0.94
  (α = .025 per test, Holm within the 3-test family). The H2b interaction
  at δ = 0.15: power ≈ 0.70 — **disclosed**, reported as an estimate with
  CI, not a confirmatory gate. (Budget option: n = 50/cell ≈ £800 total,
  primary power ≈ 0.85, interaction ≈ 0.55.)
- **Session ≈ 30 items, 12–16 min.** Pay set to the platform fair-pay
  floor at the **slowest piloted cell's median duration** (anchored cells
  read more), single pay level for all cells.
- **Cost estimate (n = 70): ~£1,150–1,400 including fees + ~£120 norming
  wave + ~£60 pilot.** Requires explicit approval.

## 5. Measures and analysis plan (to be pre-registered)

- **Outcome coding.** Verdicts decoded by the library (inversion
  server-side). Binary per-item outcome = *matches the material design
  expectation* (irrelevant addition → verdict preserved; defeater →
  verdict withdrawn). **Abstain/Unclear handling pre-specified:** the
  primary MRI is computed over substantive responses only, with a
  substantive-floor (≥ 2/3 of diagnostic items answered substantively;
  else the respondent is excluded from MRI analyses but retained for the
  abstain companion analysis). Sensitivity analysis: abstains scored 0.
  Companion analysis: abstain rate by cell (epistemic and anchored
  surfaces plausibly shift abstention; the MRI effect must be
  decomposable into verdict-flips vs abstention).
- **Primary analysis: logistic mixed model** on the binary outcome —
  `match ~ frame * rendering * item_type + (1|respondent) + (1|item)` —
  with the two pre-registered confirmatory contrasts as marginal effects:
  H1 = rendering within thin; H2 = frame within epistemic. Holm correction
  within the 3-test family {H1, H2, H2b}. The aggregated-MRI ANOVA is
  reported as descriptive only; if model and ANOVA disagree, the mixed
  model governs (pre-stated).
- **Compliance-vs-norm-selection discriminator (pre-registered).** The
  anchored header states the desired norms with worked answers, so H2
  could reflect instruction compliance rather than practice selection. The
  discriminating signature is the **frame × item-type interaction**:
  compliance predicts a roughly uniform shift across item types
  (including contested and calibration items); norm-selection predicts a
  shift concentrated on the diagnostic items. Reported as the primary
  interpretive check on H2; a placebo-instruction arm is deferred to a
  follow-up if this is inconclusive.
- **Dissociation decision rules (symmetric, formal, single estimator).**
  Estimator: the mixed-model marginal contrast; direction pre-specified
  (epistemic reduces material reading; anchored increases it).
  - *Phenomenon-level sensitivity:* minimal-effects test — one-sided
    H0: effect ≤ 0.05; conclude sensitivity if the 95% CI lower bound
    > 0.05.
  - *Dissociation (flat):* TOST with margin 0.15 — conclude flatness if
    the 90% CI lies within (−0.15, 0.15).
  - Neither → indeterminate/attenuated, reported as such. **The design is
    not claimed to distinguish attenuated (0.05–0.15) from absent** — at
    this precision it cannot (review finding); the bands are conclusions
    of the tests, not a measurement of the band.
  - *Comparator precondition:* the model-side comparator is the observed
    effect on the **item-matched, same-batch lay model grid** (§7), with a
    pre-registered minimum-swing precondition (model contrast ≥ 0.15) —
    without a model swing there is nothing to dissociate from, and that
    outcome is reported as such.
- **Exclusions (pre-registered, bias-audited).** (i) Instructed-item
  failure. (ii) Speed: per-item-page response times excluding the
  instructions page, median computed **per cell** (anchored cells read
  more), threshold ⅓ of cell median. (iii) **No straight-lining rule on
  scored items** — a consistent formal reader in thin-epistemic gives
  near-uniform verdicts legitimately; uniformity on scored items is
  potential signal, not noise (review finding). Reporting: exclusion
  counts by cell and rule, a differential-exclusion test, and a
  sensitivity re-analysis including all excluded-but-instructed-passing
  respondents. Approve-and-exclude payment policy (pay, exclude from
  analysis) per platform norms.
- **Secondary/descriptive:** per-item human majority vs the model
  families' verdicts — κ **descriptive with bootstrap CIs** (±~0.2 at 24
  items; never a hypothesis test); calibration-item pass rates by cell;
  contested-item splits; order/adjacency analysis (does a variant's MRI
  depend on whether its base preceded it? — the within-subject
  contrast-effect caveat on H3 is pre-stated: models answer statelessly,
  humans see ladder-mates).
- **Recruitment wave, platform-real:** "N approved submissions per cell,
  including Prolific's automatic replacement of returns/timeouts;
  analysis exclusions applied post hoc; no re-contact beyond the declared
  top-up rule."

## 6. Survey construction

1. **Instructions-block exporter change (blocking):** full frame header +
   exemplars rendered ONCE as a survey-level instructions page; per-item,
   only the one-line final question stem. Prevents ~5–7k words of repeated
   header inviting satisficing.
2. **Comprehension/practice (cell-matched, respecified):** same practice
   CONTENT rendered through each cell's own pipeline (a practice item must
   wear its cell's frame and rendering — an off-cell practice surface
   contaminates the manipulation); feedback text mechanics-only and
   byte-identical across cells; a short cell-matched instructions quiz
   with a re-read loop, no screen-out, quiz passage recorded as a
   manipulation-check covariate.
3. **Platform: Qualtrics** (working randomization); item order randomized
   per respondent; choice order fixed.
4. **Pilot: all four cells, n = 5 each** — timing per cell (pay
   calibration on the slowest), instructions-quiz and calibration-item
   pass rates. Fixed wording after pilot; pilot participants excluded
   from the main pool.

## 7. Model-side lay grid (required for H3)

The same 4 cells (plus, cheaply, the four support cells the humans won't
see) captured on the lay benchmark across the four model families,
inheriting the cross-model lessons verbatim: 8192-token budgets for
reasoning-verbose families, zero-`budget_clipped` acceptance sweep,
provider-seed caveats recorded, deepseek Δ≤3 treated as within noise.
Same-batch, item-matched — the clinical grids are not the comparator.

## 8. What this study does not do

No clinician cells (separate study once the panel's verdicts exist). No
validity claim about which reading is correct. No support-form human
cells (Phase 2, §9). No underdetermination cells. κ_C is untouched by
this study — it measures configuration sensitivity of lay verdicts.

## 9. Instrument work items

**Blocking Phase 1:**
1. Instructions-block export mode (§6.1) + tests.
2. Catalogue `case-open-world-v1` in a library module added to
   `_BUILTIN_TEMPLATE_MODULES` (byte-identical text, same id — the
   promotion discipline).
3. **Rendering provenance in surveys:** add `template_id` to
   `SurveyQuestion` + sidecar rows; extend the import/merge guard to
   refuse cross-rendering composition (two cells differing only in
   rendering currently compose silently — a gap in the survey-side mirror
   of the model-side refusal discipline).

**Phase 2 prerequisites (support form; not blocking):**
4. Support-body rendering axis for surveys (the support branch ignores
   the template registry).
5. Author + review a respondent-voice `survey_header` for
   `defeasible-explicit-v1`; promote the prompt into `infereval.prompts`
   (byte-identical system, same id).
6. A lay-appropriate thin-support header as a NEW versioned surface (the
   locked v0.9.0 header says "diagnostic inference" — clinical vocabulary
   on a lay benchmark; the locked text is not edited).

## 10. Execution checklist (post-approval)

1. Instrument items 1–3 → PR.
2. Author lay bearers + v0.5 items (authoring rule: exemplar-disjoint) →
   panel review → `bearers-import`.
3. Norming wave (n≈25) → item retention/replacement → freeze benchmark.
4. Model-side lay grid, all families, acceptance sweep (§7).
5. Pre-registration (hypotheses, contrasts, decision rules, exclusions,
   coding — §5 verbatim); ethics/consent per the author's institution.
6. Pilot (§6.4) → pay calibration → launch one randomized study.
7. Import per cell (frame + template guards), pre-registered analysis,
   write-up against ledger D4 / defeat condition 3.

## Decision points for the user

- **Approve Phase-1 scope** (coherence 2×2) and budget (n = 70/cell,
  ~£1,350 all-in; or n = 50/cell, ~£1,000 all-in with primary power 0.85
  and weaker interaction estimation).
- Ethics route and timing (institutional process).
- Whether Phase-2 support-side instrument work (items 4–6) should be
  built now or after Phase-1 results.
