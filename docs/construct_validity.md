# Construct validity of the instrument

> **What this document is.** A single source of truth for the construct-validity methodology that `infereval` implements: what the instrument requires of an evaluation for "strong inter-annotator agreement between model M and analysts on benchmark β" to count as evidence of inferential mastery in domain D, how the framework supports producing that evidence, and what the framework deliberately leaves to the surrounding research program.
>
> Companion to the [paper's](https://github.com/bradleypallen/infereval) Section 4 evaluation methodology. Where the paper specifies the formal machinery, this document specifies the construct-validity scaffolding the formal machinery needs to support a defensible mastery claim. The two are intentionally co-engineered.

## Context

The methodology measures model–analyst agreement on labeled inference benchmarks via coverage and Cohen's / Fleiss' kappa. That measurement is, on its own, neutral about what the agreement is *evidence for*. The methodology can be used in a deflationary register where the agreement statistic is the whole claim, and in that register most construct-validity worries do not arise.

The framework's natural use case is the more ambitious one Simonelli's paper motivates: treating strong agreement as evidence of inferential mastery in the framework's structural sense. In that register, a substantial set of construct-validity requirements becomes live — requirements about analyst-pool justification, benchmark coverage, competing-explanation controls, reliability, structural coherence of the derived frame, and disciplined framing of the resulting claims. Construct validity here follows the classical psychometric formulation (Cronbach & Meehl, 1955; Messick, 1989) and its recent adaptation to LLM benchmarks (Bean et al., 2026; Salaudeen et al., 2025; Freiesleben, 2026).

Reliability — within-run dispersion of the model's sample verdicts and across-run stability of the headline κ_C — is a precondition for any of this. An evaluation that doesn't replicate is not evidence of anything, mastery or otherwise. The methodology treats reliability as a first-class requirement, not as a hygiene afterthought: an agreement number reported without uncertainty quantification and without a test-retest check is a point estimate from an unknown distribution, and a benchmark κ run once is a draw, not a measurement.

Reliability claims are **doubly relative**: to the *carving* the analyst declares in B/δ (R19), and to the *identity criterion* the analyst declares under which "the same system" is being measured (R22, second leg). The framework already treats every other methodologically-load-bearing standard as a declared commitment relative to which claims are scoped — mastery sense (R16), claim scope (R17), constitution-vs-evidence position (R18), carving (R19). v0.6.1 adds the individuation criterion to that list as a peer commitment, on the same logic Hlobil & Brandom's framework already gives consequence relations relative to a declared material base. Carving-relativity says: the framework doesn't pretend to know the right way to partition the domain; it makes that an explicit declaration the analyst stipulates. Individuation-relativity says the same thing about the system under test: the framework doesn't pretend to know what individuates "the same LLM" across two runs; it makes that an explicit declaration with caveats for the parts the framework cannot mechanically verify. The two together are the complete relativity stance — the methodology's posture is to make every load-bearing standard a stipulated commitment relative to which claims are scoped, never an inferred one.

This document catalogues the requirements, the framework's support for each, the workflow that exercises them end-to-end, and the disposition the instrument embodies toward what it can and cannot certify.

## The requirements

The requirements derive from the question: *what would need to be true of an evaluation methodology for "strong inter-annotator agreement between M and analysts on benchmark β" to constitute evidence of inferential mastery in domain D, rather than just a measurement of agreement on β?* They are grouped into three tiers reflecting how much each does in support of a mastery claim, and organised by the concern they address.

### Tier 1: necessary for any mastery claim from agreement

**Requirements on the analyst pool and reference standard**

- **R1. Documented analyst competence.** The methodology specifies and justifies the criteria by which analysts are selected as competent practitioners in the target domain, with documentation of training, credentials, or other grounds for treating their verdicts as a defensible reference for domain practice. *(Messick, 1989; Cronbach & Meehl, 1955)*

  > **How the framework addresses this:** the benchmark schema's `AnalystModel` carries `id`, `display_name`, and `notes` (a free-form text field) where analyst competence is documented. The framework validates the *presence* of analyst declarations but cannot assess whether the credentials cited are appropriate to the domain. The construct-validity report's claims file makes the analyst-panel composition part of the disclosed methodology.

- **R2. Computed and reported inter-analyst baseline.** The methodology computes κ_F*(β) and reports it alongside any agreement statistic involving M, with the baseline meeting the conditions for being defined (m ≥ 2 analysts, non-unanimous benchmark items). *(Fleiss, 1971; Allen, 2026 Remark 4 and Def. 10)*

  > **How the framework addresses this:** `infereval.metrics.inter_analyst_fleiss` computes κ_F* over the full analyst pool whose verdicts the benchmark records — surfaced by `infereval describe` (top-level baseline line), `infereval metrics` (per-decomposition), and section 2 of the construct-validity report. Returns `None` with a logged warning in the conditions Remark 4 calls out (m < 2 or unanimous analysts). For panelled benchmarks, `inter_analyst_fleiss_per_panel` returns the κ_F* per declared panel, and the construct-validity report's section 2 renders both the headline all-analyst figure and the primary-panel sub-figure so the methodological distinction is visible. `cross_panel_kappa` computes the Cohen's κ between two panels' per-item consensus columns; that's the R4 convergent check, separate from the baseline.
  >
  > **v0.7.0 behaviour change (closes [#82](https://github.com/bradleypallen/infereval/issues/82)).** Pre-v0.7.0, `inter_analyst_fleiss(benchmark)` silently restricted to the primary panel on panelled benchmarks — which inflated the headline number when the primary panel was internally unanimous (returning +1.0 even when the reviewer panel disagreed on several items). The methodological reading underwriting v0.7.0's default change: panels are an additive convergent-validity device, not a way to restrict the baseline. The full pool of analysts whose verdicts the benchmark records is the pool the Remark 4 baseline is over. The primary-panel value remains reachable via `inter_analyst_fleiss_per_panel(bench)[bench.resolved_primary_panel()]` and is rendered as an explicit sub-bullet in the report's section 2; callers who want it programmatically can pass `inter_analyst_fleiss(bench, analyst_indices=bench.analyst_indices_in_panel(bench.resolved_primary_panel()))`.

- **R3. Interpretive framing relative to the baseline.** The methodology frames agreement claims in explicit relation to κ_F*(β) — neither in isolation nor against an unstated absolute threshold — so that "strong agreement" is operationalised as a specific relationship to the analyst-internal ceiling rather than as an arbitrary kappa value. *(Landis & Koch, 1977; Allen, 2026 Remark 4)*

  > **How the framework addresses this:** `infereval describe`, `infereval metrics`, and the construct-validity report all surface κ_F* alongside κ_C / κ_F so the comparison is immediate. The report explicitly relativises the mastery verdict to the declared scope.

**Requirements on benchmark construction**

- **R5. Documented construction procedure.** The methodology specifies and documents the procedure by which β was constructed — bearer selection, item generation, inferential-type coverage, difficulty calibration — so that content-validity arguments are available rather than presumed. *(Messick, 1989; Gebru et al., 2021; Bender & Friedman, 2018)*

  > **How the framework addresses this:** `BenchmarkItem.construction_metadata` carries `authored_by`, `authored_on`, `authored_blind_to_models`, and `source`. The framework validates structure (Pydantic types, `extra="forbid"`) but does not enforce content. `infereval describe` surfaces a construction-provenance summary section plus per-item annotation in `--items` output.

- **R6. Coverage of inferential types salient in the domain.** The methodology ensures β includes the range of inferential types the framework treats as constitutive of mastery — monotonic and defeasible cases, RSR-targeted variation around target inferences, and structural relationships among inferences — rather than enumerating items of a single type. *(Hlobil & Brandom, 2025; Allen, 2026 Remark 5)*

  > **How the framework addresses this:** the `tags` field carries inferential-role identifiers (`supporter`, `defeater`, `irrelevant-addition`, `base-inference`, etc.). The factorial-design metadata (`factors` + `factor_levels`) makes the inferential-type axes first-class. `infereval structure` checks RSR role consistency against the resulting design.

- **R7. Multiple items per condition.** The methodology includes multiple distinct items instantiating each condition or inferential type, so that item-level idiosyncrasy can be separated from condition-level effects in the analysis. *(Schütze, 1996; Cowart, 1997; Baayen, Davidson & Bates, 2008; Barr et al., 2013)*

  > **How the framework addresses this:** `Benchmark.factor_constraints.min_items_per_cell`. The benchmark validator rejects designs that fall short of the declared floor, with an error message listing the underpopulated cells. `infereval describe` surfaces the populated-cell count and the floor-meeting count.

**Requirements on stimulus design**

- **R10. Paraphrase variation under fixed inferential content.** The methodology includes, for each item or each condition, multiple meaning-preserving paraphrases of δ, ctx_Γ, and ctx_Δ, so that agreement attributable to inferential content can be separated from agreement attributable to surface form. *(Allen, 2026 Remark 9; Ribeiro et al., 2020; McCoy, Pavlick & Linzen, 2019)*

  > **How the framework addresses this:** `BearerModel.paraphrases` is runtime-active. The `--paraphrase-variant K` and `--paraphrase-cycle` flags on `infereval evaluate` orchestrate the per-variant runs; outputs auto-suffix with `-vN`. Content-vs-form sensitivity is a one-flag operation.

**Requirements on the analysis**

- **R12. Per-cell or per-condition decomposition.** The methodology reports agreement statistics decomposed by inferential type, target inference, and any other design factor — not only as a single aggregate number — so that uniformity of agreement across the domain can be distinguished from agreement driven by a tractable subset. *(Sprouse & Almeida, 2012; Sprouse, Schütze & Almeida, 2013; Barr et al., 2013)*

  > **How the framework addresses this:** `infereval metrics --by-tag` and `--by-rsr-target` provide per-decomposition kappa. `infereval model` fits a logistic regression of agreement on declared factors with per-factor joint Wald tests — producing the structural characterizations ("main effect of side-premise type, p < 0.001; no main effect of paraphrase variant") that R12 motivates.
  >
  > Decomposition cells inherit the framework's reliability discipline. Each cell renders its substantive-n and per-class verdict counts; cells with substantive-n below `MIN_K_FOR_SUBSAMPLING_CI = 10` carry an `[under-powered: n < 10]` annotation on the κ_C and κ_F lines and surface as a "Decomposition under-powered (R12)" group in section 4b of the construct-validity report (via `infereval report --by-tag …` / `--by-rsr-target …`). The κ value is still rendered (the *direction* can be a diagnostic lead), but the Landis-Koch-style interpretive label is gated — on `n = 2`, `κ_F = ±1.0` is the value the formula is *forced* to take when each rater commits to a single class, not a finding. R12 doesn't license inferring "uniformity of agreement across the domain" from cells too small to support the inference. See [`interpreting_metrics.md`](interpreting_metrics.md) — *A worked reading: the live Haiku result from the M9 demo* — for the canonical case.

- **R22. Reliability of the measurement is established.** The methodology reports both within-run (verdict-sampling) dispersion and across-run (test-retest) reliability for the headline agreement statistics, and meets a stated stability criterion before treating any κ as signal. Within-run dispersion is reported as the per-item verdict distribution (good/bad/abstain counts, plurality margin, normalised Shannon entropy) and, optionally, as Politis-Romano (1994) subsampling confidence intervals on κ_C / κ_F. Across-run reliability is reported as the test-retest κ between two independent evaluations against the same benchmark, classified into stable / moderately-stable / substantively-unstable per a fixed ladder. *(Cronbach & Meehl, 1955; Bean et al., 2026 §5.6; Salaudeen et al., 2025; Freiesleben, 2026; Politis & Romano, 1994)*

  > **How the framework addresses this:**
  >
  > - **Within-run dispersion** lives in `infereval.metrics.VerdictDistribution` and the corpus-level `AggregateDispersion`. `infereval metrics` surfaces them in JSON output by default. The `--ci` flag on `infereval metrics` reports Politis-Romano subsampling CIs on κ_C and κ_F (benchmark size ≥ 10; subsample size defaults to `round(K^0.7)`). The `--weight-by-margin` flag computes the confidence-weighted κ variants that discount thin-margin agreements.
  > - **A within-run structural check** (`thin_margin_agreement_check`, part of `infereval structure`) flags items where the model agrees with analyst consensus but the agreement is supported by a thin majority over the sampled verdicts — agreements that could flip on a re-run.
  > - **Across-run reliability** is computed by `infereval retest`, which compares two evaluation JSONs against the same benchmark (the framework validates that `benchmark_hash`, `endorsement_config`, and `paraphrase_variant` all match so retest variability isn't conflated with parameter-change effects). The output `retest-result.json` carries `test_retest_kappa`, per-item `FlippedItem` records (with factor-level annotations when factors are declared), per-item dispersion deltas, and a stability_verdict drawn from a fixed ladder (κ ≥ 0.8 stable; ≥ 0.6 moderately stable; < 0.6 substantively unstable).
  > - The construct-validity report surfaces test-retest κ in section 2 alongside κ_F* / κ_C / κ_F, and surfaces flipped items in section 4b alongside structural anomalies. The verdict gate caps at `partially_defensible` if `test_retest_run` is asserted but the supplied retest is substantively unstable — the same "ran but didn't pass" audit-cap pattern used for structural anomalies and m<2.
  >
  > R22 is verdict-gating at scope ≥ `domain_D_as_sampled`. At `items_in_benchmark` scope the retest is still reported when an artifact is supplied but is not required to render a defensible verdict. This reflects the methodology's posture: at the narrowest scope the analyst is not making generalisation claims, so reliability is still good practice but is not gating; at any broader scope, generalising from an unreplicated measurement is not warranted.
  >
  > **R22 second leg — declared identity criterion (doubly-relative framing).** Reliability is by definition the agreement of distinct measurements of *the same individual*; the test-retest κ is uninterpretable without a declared identity criterion for what "the same system" means across the two runs. The framework records that declaration via `ConstructValidityClaims.reliability.identity_criterion`, a small object structurally parallel to `CarvingClaim` (R19): per-field booleans split into a *framework-substantiated* group (same `benchmark_hash`, same `endorsement_config`, same `paraphrase_variant` — the setup-conformance the parity check on `infereval retest` mechanically verifies) and an *analyst-substantiated* group (same `provider_model_id`, `cross_update_identity_asserted`, `same_scaffolding` — assertions the analyst commits to that the framework records but cannot mechanically verify on its own), plus a free-text `unverifiable_caveats` field where the analyst documents what they're committing to without framework backup and a `rationale` field that documents why these are the right individuation choices for the evaluation at hand. The same shape as the leakage-audit-gap handling for R8/R9: framework records the claim, applies the parts it can verify, flags the parts it cannot. The verdict gate at scope ≥ `domain_D_as_sampled` requires the criterion to be declared with a non-empty rationale before R22 is considered satisfied — mirrors the R19 carving-acknowledgement gate, on the same logic that you can't make this kind of claim without committing to the standard it's relative to.

**Requirements on the form of mastery claims**

- **R16. Explicit specification of the mastery sense intended.** The methodology states whether the mastery claim is about evaluative behaviour (endorsements-when-asked), generative behaviour, standing competence, or some combination, and restricts its claims to the sense the measurement supports. *(Allen, 2026 Remark 7; Brandom, 1994)*

  > **How the framework addresses this:** `ConstructValidityClaims.mastery_sense`, a required claims-file field with a `Literal["evaluative", "generative", "standing", "combination"]` discriminator plus required free-text description. `infereval report` refuses to render without this field populated.

- **R17. Explicit specification of the scope of the claim.** The methodology states whether the mastery claim is about (a) the items in β, (b) the domain D as sampled by β, or (c) inferential mastery as a general capacity, and provides arguments appropriate to the scope claimed. *(Messick, 1989; Allen, 2026 Remark 10)*

  > **How the framework addresses this:** `ConstructValidityClaims.scope`, with a `Literal["items_in_benchmark", "domain_D_as_sampled", "general_capacity"]` discriminator and a tiered set of required competing-explanation checks per scope. Broader scopes require strictly more checks; the verdict downgrades automatically when checks are missing.

**Requirements on reporting**

- **R20. Disclosure of all analyst-supplied choices.** The methodology reports B, δ, ctx_Γ, ctx_Δ, the verification prompt, the analyst-pool composition, the construction procedure for β, the sampling and aggregation choices for E_M, and any other free parameters, so that the measurement is reproducible and the carving is visible to anyone evaluating the mastery claim. *(Mitchell et al., 2019; Gebru et al., 2021; Pineau et al., 2021)*

  > **How the framework addresses this:** the benchmark and evaluation JSON schemas carry B, δ, the context builders, the verification prompt, the analyst panel, `construction_metadata`, `references`, and `paraphrase_variant`. `infereval describe` surfaces every declared choice; the construct-validity report lists them under the disclosed-methodology section.

### Tier 2: necessary for a defensible mastery claim

**Requirements on the analyst pool and reference standard**

- **R4. Independent reference check.** The methodology includes, at least once per benchmark, a comparison of agreement results against an independent reference source (a second analyst panel, an authoritative external benchmark, or domain-recognised credentialing) to guard against shared-error agreement among the primary analyst pool. *(Campbell & Fiske, 1959; Cronbach & Meehl, 1955)*

  > **How the framework addresses this (tooling complete; recruitment is research-program):** `AnalystModel.panel` and `Benchmark.primary_panel` declare multiple panels; `inter_analyst_fleiss_per_panel` and `cross_panel_kappa` compute per-panel κ_F* and Cohen's κ between two panels' per-item consensus columns. The comparison machinery is end-to-end; recruiting a second panel remains an institutional responsibility.

**Requirements on benchmark construction**

- **R8. Held-out items constructed independently of M.** The methodology includes items constructed without reference to M's outputs or behaviour, ideally by analysts who haven't observed M, to prevent the benchmark from being implicitly tailored to the model under evaluation. *(Sainz et al., 2023; Pineau et al., 2021)*

  > **How the framework addresses this (partial):** `construction_metadata.authored_blind_to_models` lets each item declare which models the author had not observed at authoring time. The construct-validity report's competing-explanation checks include `held_out_items_used` as a tracked declaration. The institutional separation between benchmark authors and model evaluators remains a research-program responsibility. The framework does not currently cross-check the per-item declaration against the `held_out_items_used` boolean (a deferred audit-cap; see "Known gaps" below).

- **R9. Training-data separation.** The methodology includes checks or controls — temporal (β constructed after training cutoff), structural (no verbatim or near-duplicate matches against training data), or both — sufficient to rule out memorisation as an alternative explanation for agreement. *(Sainz et al., 2023)*

  > **How the framework addresses this (partial):** `construction_metadata.authored_on` records the authoring date so temporal separation can be argued. The construct-validity report tracks `training_data_separation_verified` as a declared check. Verifying actual training-data overlap requires model-provider cooperation or external tooling outside the framework's scope.

**Requirements on stimulus design**

- **R11. Sensitivity analysis on free parameters.** The methodology reports agreement results under variation of analyst-supplied methodological choices — verification-prompt wording, expression-function choices, sample size for majority voting, aggregation rule — so that robustness of agreement to these choices is established rather than assumed. *(Sclar et al., 2024; Lu et al., 2022)*

  > **How the framework addresses this:** `infereval sweep` sweeps over `n_samples`, `tie_break`, `paraphrase_variant`, or `temperature`. Per-value evaluation artifacts and an aggregate `sweep-summary.json`. The `SweepResult.stability_verdict` deterministically classifies the κ_C range into stable / moderately sensitive / substantively variable.

**Requirements on the analysis**

- **R13. Structural coherence check on the derived frame.** The methodology includes a post-evaluation check that ⟨B, I_M⟩ exhibits the structural properties the inferentialist framework treats as constitutive of mastery (closure under containment, coherent RSR behaviour, appropriate defeasibility patterns), so that aggregate agreement isn't conflated with structural mastery. *(Hlobil & Brandom, 2025; Brandom, 1994; Allen, 2026 Remark 5)*

  > **How the framework addresses this:** the `infereval.structure` module ships four checks: `containment_closure_check` (sanity), `rsr_role_consistency_check`, `base_case_stability_check`, and `thin_margin_agreement_check` (R22 within-run companion, flagging agreements with thin sample-margin support). `infereval structure <eta.json> --benchmark <bench>` runs all four and prints a human-readable report flagging per-item anomalies.

- **R14. Cross-domain comparison.** The methodology includes evaluation of M on benchmarks in at least one comparison domain D′, so that domain-specific competence can be distinguished from general capability that happens to apply to D. *(Campbell & Fiske, 1959; Cronbach & Meehl, 1955)*

  > **How the framework addresses this (research-program responsibility):** the framework supports running M against any benchmark; producing the comparison is the analyst's work. The construct-validity report tracks `cross_domain_comparison_run` as a declared check and downgrades the verdict when it's missing at `scope=general_capacity`.

**Requirements on the form of mastery claims**

- **R18. Explicit position on the constitution-versus-evidence question.** The methodology states whether agreement is being treated as evidence of mastery (a deeper property) or as partially constitutive of mastery (the framework's structural-behavioural characterisation), so that the weight assigned to the agreement statistic is calibrated to the philosophical commitment being made. *(Brandom, 1994; Hlobil & Brandom, 2025; Simonelli, 2026)*

  > **How the framework addresses this:** `ConstructValidityClaims.constitution`, with a `Literal["evidence_of_mastery", "constitutive_of_mastery"]` discriminator plus required justification. The position is rendered verbatim in the report under section 3.

**Requirements on reporting**

- **R21. Disclosure of failed checks and negative results.** The methodology reports results of paraphrase sensitivity, cross-domain comparison, structural coherence checks, test-retest comparisons, and replication attempts even when they fail to support the mastery claim, so that the evidence is presented complete rather than selectively. *(Munafò et al., 2017; Pineau et al., 2021)*

  > **How the framework addresses this:** `collect_negative_findings()` scans the structure / sweep / model-fit / retest artifacts for findings that weaken the mastery claim and surfaces them in a dedicated Section 4b of the report. `--suppress-negatives` is the explicit opt-out: it replaces the body with a suppression banner naming the flag, adds a `Negative-findings suppression: ENABLED` warning to the report header, and downgrades the Summary verdict one tier. The asymmetry — cheap to surface failures, expensive to suppress them — works at three levels at once.

### Tier 3: necessary for a strong mastery claim

**Requirements on the analysis**

- **R15. Replication.** The methodology specifies replication conditions — fresh sampling from M, comparable analyst pools, freshly constructed benchmarks following the same construction procedure — and reports whether the agreement results replicate under those conditions. *(Open Science Collaboration, 2015; Munafò et al., 2017; Pineau et al., 2021)*

  > **How the framework addresses this (partial):** strict reproducibility (same benchmark, same params, fresh provider call) is covered by the SHA-256 hash and immutable JSON artifact infrastructure, and by `infereval retest` for test-retest within a single benchmark+model pair. Replication in the scientific sense (fresh analyst panel, freshly constructed benchmark, same procedure) is a research-program responsibility. The construct-validity report tracks `replication_attempted` as a declared check.

**Requirements on the form of mastery claims**

- **R19. Carving-indexed framing of in-principle claims.** The methodology frames any in-principle claims about mastery in the carving-indexed form Remark 10 specifies, rather than as unrestricted claims about concept possession, so that the relativity to analyst-supplied carving is preserved in what gets concluded from the measurement. *(Allen, 2026 Remark 10; Simonelli, 2026; Hlobil & Brandom, 2025)*

  > **How the framework addresses this:** `ConstructValidityClaims.carving`, with `acknowledges_carving_indexed: bool` plus `notes: str`. The verdict computation requires both `acknowledges_carving_indexed=True` AND non-empty `notes` when the claim's scope reaches beyond `items_in_benchmark`. Failing either condition automatically downgrades the verdict to `not_defensible`. The framework cannot enforce carving-indexed framing in third-party write-ups but can refuse to render a defensible verdict for write-ups that ignore it.

## What only a research program can do

Several requirements are workflow discipline that the framework can support but not replace:

- **Independent reference panels.** Someone has to recruit a second analyst pool with independent training, label the same benchmark, and compare. The framework supplies the comparison machinery (`cross_panel_kappa`, `inter_analyst_fleiss_per_panel`); it cannot recruit the panel.
- **Held-out items constructed independently of M.** This requires institutional separation between benchmark authors and model evaluators, with authors blind to the model's outputs. The framework records authorship metadata; the discipline itself is institutional.
- **Training-data separation.** Partly addressable through temporal metadata (constructed-after dates); deeper separation requires either model-provider cooperation or external tooling outside the framework's scope.
- **Scientific replication.** Strict reproducibility is provided by the SHA-256 hash and audit log; test-retest reliability is provided by `infereval retest`. Replication in the scientific sense — fresh analyst panels, fresh benchmarks, same construction procedure — requires additional studies the framework can lower the cost of but cannot substitute for.
- **Test-retest temporal occasions.** v0.6.1 separates two issues v0.6.0 was conflating. **(a) The temporal-occasion question:** did the two runs actually happen on different occasions? The framework records run timestamps and provider response IDs where available; it cannot enforce a minimum interval, guarantee that the two attempts are independent, or detect a re-run that's actually a copy of the first artifact under a different `run_id`. This stays a residual analyst-honesty piece — same shape as the leakage-audit-gap self-report for `held_out_items_used` / `training_data_separation_verified`. **(b) The identity-criterion question:** what counts as "the same system" being measured across the two runs? This is now a *declared methodological commitment*, not a research-program residual — the analyst records it in `ConstructValidityClaims.reliability.identity_criterion` and the framework partially substantiates it (the setup-conformance booleans are verified by the parity check on `infereval retest`; the analyst-substantiated booleans are recorded with caveats per the leakage-audit-gap pattern). v0.6.1 elevates (b) out of the research-program residual and into the framework's commitment-and-relativity surface, alongside carving (R19), scope (R17), and the other declared commitments.
- **Mastery-sense, scope, and constitution-versus-evidence claims.** These are interpretive commitments by whoever writes up results. The framework can prompt for explicit statements but cannot supply the substance.
- **Carving-indexed framing of in-principle claims.** The framing comes from the analyst's understanding of the paper's Remark 10; the framework can carry the framing forward in its documentation but cannot enforce its use in third-party write-ups.

The right response to these is to organise the research community to do the work, not to extend the tool to pretend otherwise. The framework's posture: make the work cheap enough to do, and make *undeclared* skipping visible in the report. Every workflow requirement has *infrastructure* that makes the work cheaper and *declarations* that make its presence or absence part of the public artifact. Skipping is permitted (some skips are unavoidable at any given stage of a research programme); pretending you didn't skip is not.

## The workflow

The methodology runs in nine phases. The framework handles phases 1–7; phases 0, 4 (in part), and 8 are research-program work the framework supports but cannot do for you. Each phase carries the same asymmetry the framework embodies throughout: skipping a phase is fine, but doing it without declaring you skipped it is not. The report verdict refuses to render ✅ "defensible" when the skips are not at peace with the declared scope.

| Phase | What you do | What the framework does | What you alone do |
|---|---|---|---|
| 0 | Plan the experiment | nothing — design comes first | pick D, B, δ, scope, panel |
| 1 | Author the benchmark | validate structure | author item content |
| 2 | Run the evaluation (twice) | sample M, log everything; `retest` compares the runs | provide the API key; commit to running on different occasions |
| 3 | Run analytical checks | `structure`, `model`, `sweep`, `metrics --ci` | inspect anomalies |
| 4 | Cross-panel / replication | compute cross-panel κ once panel 2 exists | recruit panel 2; rerun benchmark |
| 5 | Write the claims file | validate structure + verdict logic | declare scope, sense, position |
| 6 | Generate the report | render Markdown with auto-collected negatives | nothing |
| 7 | Publish artifacts | reproducible JSON + hashes | host & cite |
| 8 | Stand behind the claim | nothing — interpretation is yours | argue the case in your write-up |

The two demos bundled with the framework illustrate the workflow at different scales: the **stop-sign cross-family experiment** (`examples/stop_sign/`, with results at `experiments/results/stop_sign/` and a 13-model writeup at `experiments/results/stop_sign_2026-05-18.md`) is the minimal end-to-end shape — 4 items, 1 analyst panel, paper-aligned. The **pulmonology benchmark** (`examples/pulmonary_edema/`, with results at `experiments/results/pulmonology/`) is the more elaborate construction — 20 bearers, 29 items, factorial design, RSR-targeted structure, and a 6-model multi-family run.

### Phase 0: Plan the experiment

Get the design right before you write any code.

**0.1 Pick the domain D.** Domains that admit expert labeling of inferential examples: clinical reasoning (the pulmonology demo), contract law, classical logic, software engineering, electrical-circuit reasoning, chess endgames. Domains that don't: aesthetic judgment, ethical intuition, anything where "competent practice" isn't well-defined. The framework is *carving-relative*. There is no domain-independent fact about "model mastery of D"; there is only mastery of D *under the carving you supply*.

**0.2 Pick the carving — bearers B, expression function δ.** Three rules of thumb: (1) atoms, not compounds; (2) operationalisable English (every bearer must have a δ-image a domain expert reads unambiguously); (3) roughly 10–30 bearers per benchmark. The stop-sign benchmark uses 5; pulmonology uses 20. Write δ as a dictionary. If you anticipate paraphrase robustness checks (R10 — and you should), record alternative phrasings in each bearer's `paraphrases` list now.

**0.3 Decide the scope of the claim you intend to make.** Three options:

- **`items_in_benchmark`** — the narrowest. You claim mastery of the specific implications listed in β; you don't generalise to D, much less beyond. Required: structural coherence + sensitivity sweep. Appropriate for demonstration-stage work.
- **`domain_D_as_sampled`** — middle. You claim mastery of D as represented by β's coverage. Requires the above plus paraphrase robustness, cross-panel agreement, held-out items, **and test-retest reliability (R22)**.
- **`general_capacity`** — broadest. You claim mastery of inferential reasoning as a general capacity. Requires all of the above plus training-data separation, cross-domain comparison, and replication. Also requires R19 (carving-indexed framing of in-principle claims) to be acknowledged with non-empty notes, or the report's verdict auto-downgrades to `not_defensible` regardless of the rest.

Pick the narrowest scope that does the work your write-up needs. Broader scopes look more ambitious but make you do strictly more checks. Most demonstration projects should pick `items_in_benchmark` and earn `domain_D_as_sampled` only after the second analyst panel and the test-retest comparison are in place.

**0.4 Recruit the analyst panel(s).** Document competence (R1): each analyst's `AnalystModel.notes` should record training, credentials, or other grounds for treating their verdicts as a defensible reference for D's practice. For R4 (independent reference check): plan for two panels from the start; the second one need not be large.

**0.5 Decide which model(s) to evaluate.** Pick the model **before** authoring items. The `construction_metadata.authored_blind_to_models` field is the construct-validity hygiene check for R8.

**0.6 Declare the individuation criterion (R22 second leg).** Decide *before* you start measuring what counts as "the same system" being measured across the two retest runs. The criterion has both a framework-substantiated portion (same `benchmark_hash` / `endorsement_config` / `paraphrase_variant` — these are mechanically verified by the parity check on `infereval retest`) and an analyst-substantiated portion (same `provider_model_id`, `cross_update_identity_asserted`, `same_scaffolding` — the framework records the commitment but cannot mechanically verify it for providers that don't expose snapshot/fingerprint metadata). The choices have interpretive weight: a reliability number computed under `cross_update_identity_asserted=True` includes silent provider-side weight rotations in the "noise floor"; under `cross_update_identity_asserted=False` the analyst is explicitly denying that commitment and accepting that the reliability number folds cross-update drift into the measurement. The criterion is recorded at Phase 5 in `ConstructValidityClaims.reliability.identity_criterion`; deciding it here, before measurement, is what makes the test-retest κ an interpretable reliability number rather than a bare statistic. Same logic as the rest of Phase 0: every load-bearing standard the methodology relativises to gets stipulated up front.

### Phase 1: Author the benchmark

The benchmark JSON is the single source of truth. Edit it directly; validate often. See [`authoring_benchmarks.md`](authoring_benchmarks.md) for the full schema reference; the construct-validity-relevant fields are: `analysts` (with `panel` declarations for R4), `factors` + `factor_constraints` (for R7 and R12), `factor_kinds` (so substantive vs experimentally-controlled factors render with the right valence in negative findings), per-item `construction_metadata` (for R5/R8/R9), `references`, `tags`, `rsr_target`, `paraphrases` on bearers (for R10). Then:

```bash
infereval validate path/to/benchmark.json
infereval describe path/to/benchmark.json
```

`describe` shows you the summary including factorial-design population, paraphrase variants, analyst panels with per-panel κ_F* + cross-panel κ_C when ≥ 2 panels, and construction-provenance counts. Fix the JSON before going further if it doesn't show what you intended.

### Phase 2: Run the evaluation (twice)

The methodology requires two runs for R22. The reliability check is what lets the headline κ_C be interpreted as signal rather than as noise from a single draw. Running twice is *necessary* for R22 but does not by itself satisfy it: the second leg is the declared identity criterion (Phase 0.6, recorded at Phase 5) — without it, the framework has no commitment about what "the same system" means across the two runs, and the test-retest κ is uninterpretable as a reliability number.

**2.1 The first run.**

```bash
infereval evaluate path/to/benchmark.json \
  --provider openai --model gpt-5.5 \
  --n-samples 5 --temperature 0.0 --max-tokens 1024 \
  --run-id myexpt-2026-05-20-A \
  --log out/myexpt-A.jsonl \
  -o out/myexpt-eta-A.json
```

What the framework records (per R20): the benchmark's SHA-256 hash on `Evaluation.benchmark_hash`, every sample call with timestamps and token counts (in the JSONL log), the exact decoding params used, the exact verification prompt, the endorsement config, the framework version.

**2.2 The second run.** Repeat with a different run id; ideally on a different occasion to let provider-side variability surface.

```bash
infereval evaluate path/to/benchmark.json \
  --provider openai --model gpt-5.5 \
  --n-samples 5 --temperature 0.0 --max-tokens 1024 \
  --run-id myexpt-2026-05-21-B \
  --log out/myexpt-B.jsonl \
  -o out/myexpt-eta-B.json
```

The framework will validate at retest time that both runs used the same benchmark hash, the same endorsement config, and the same paraphrase variant. If you change parameters between runs, you're measuring sensitivity (use `infereval sweep` for that), not reliability.

**2.3 Compare the runs.**

```bash
infereval retest out/myexpt-eta-A.json out/myexpt-eta-B.json \
  --benchmark path/to/benchmark.json \
  --claims path/to/claims.json \
  -o out/myexpt-retest.json
```

The `--claims` flag (v0.6.1+) threads the analyst's declared identity criterion (from `reliability.identity_criterion` in the claims file) into the retest result so the test-retest κ travels with what it's reliability-of. The criterion appears in the JSON output and is rendered in the report's section 2 and section 3 alongside κ_F* / κ_C / κ_F. Without `--claims`, the retest runs but the criterion is omitted from the result — and at scope ≥ `domain_D_as_sampled` the verdict gate will then cap to `partially_defensible` because R22's second leg is unsatisfied.

The output prints the test-retest κ, the flip count, the per-item flips (capped at 20 with the full list in the JSON), and a one-sentence stability verdict. Stable means κ ≥ 0.8; moderately stable means ≥ 0.6; substantively unstable means < 0.6 — at which point the headline κ_C cannot be interpreted as signal under that reliability level. When a criterion is supplied the verdict text is appended with "under the declared identity criterion" to make the relativity explicit.

**2.4 Paraphrase-axis sweep (R10).** If your bearers have `paraphrases`, run the cycle to get one evaluation per variant:

```bash
infereval evaluate path/to/benchmark.json \
  --provider openai --model gpt-5.5 --n-samples 5 \
  --paraphrase-cycle \
  -o out/myexpt-eta.json \
  --log out/myexpt-run.jsonl \
  --run-id myexpt-paraphrase
```

This produces `myexpt-eta-v0.json`, `-v1.json`, etc. — one per variant. Each evaluation records its `paraphrase_variant`.

### Phase 3: Analytical checks

Four commands, run in any order.

**3.1 Metrics + confidence intervals.**

```bash
infereval metrics out/myexpt-eta-A.json \
  --benchmark path/to/benchmark.json \
  --by-tag base-inference \
  --ci --ci-iterations 1000 --ci-seed 42
```

Reports coverage, κ_C, κ_F, κ_F*, plus Politis-Romano subsampling CIs on κ_C and κ_F when `--ci` is set (benchmark size ≥ 10; subsample size defaults to `round(K^0.7)`). The output `--format json` also includes the per-item `verdict_distributions` block — for each item, the (good, bad, abstain) counts, the normalised entropy, the plurality margin — so consumers can read the within-run dispersion without re-running majority-vote logic. Add `--weight-by-margin` to compute the confidence-weighted κ variants (off by default; the unweighted κ remains the headline number per the locked methodology defaults).

**3.2 Structural coherence — `infereval structure` (R13, with R22's thin-margin check).**

```bash
infereval structure out/myexpt-eta-A.json \
  --benchmark path/to/benchmark.json
```

Four checks fire: containment closure, RSR role consistency, base-case stability, and thin-margin agreement (the within-run R22 companion — flags items where the model agrees with analyst consensus but the agreement is supported by a thin majority over the sampled verdicts and could flip on a re-run). `--thin-margin-threshold` defaults to 0.4 (catches 3/5 agreements; let 4/5 through as confident). If your scope is `items_in_benchmark` or higher, you must run this check before the report verdict can be defensible.

**3.3 Factor-effects model — `infereval model` (R7, R12).**

```bash
infereval model out/myexpt-eta-A.json --benchmark path/to/benchmark.json
```

Fits a fixed-effects logistic regression of agreement on the declared factor levels with item-clustered standard errors. Per-factor joint Wald tests + per-level coefficients. Read the per-factor row to tell whether the design factor explains significant variance in agreement.

**3.4 Sensitivity sweep — `infereval sweep` (R11).**

```bash
infereval sweep path/to/benchmark.json \
  --provider openai --model gpt-5.5 \
  --vary n_samples --values 1,3,5,7 \
  --out-dir out/sweep_n_samples/
```

Runs the benchmark four times — once with each value — and bundles the metrics into `sweep-summary.json`. The console output ends with a stability verdict ("κ_C range = 0.012; agreement is stable" / "moderately sensitive" / "varies substantively"). Run sweeps over parameters whose choice you can't justify a priori. Note: `sweep` measures sensitivity to *parameter changes*; `retest` measures sensitivity to *re-running with no changes*. They answer different questions and both belong in a complete construct-validity argument.

### Phase 4: Cross-panel + replication (the research-program part)

Where the framework's infrastructure meets your institutional work.

**4.1 Second analyst panel (R4).** Recruit a second domain expert (independent of the first analyst's training where possible). Have them label the same items independently of the first (blind to the first's verdicts and to any model output). Edit the benchmark JSON to add the second panel under `analysts` and re-run `infereval describe` to see the per-panel κ_F* + cross-panel κ_C. If `cross-panel κ_C` is high (above the κ_C the model achieves against the primary panel), the primary panel's signal is corroborated by the independent reviewer — R4 is satisfied.

**4.2 Replication (R15).** Strict reproducibility is already covered by re-running `infereval evaluate` (the SHA-256 hash confirms the benchmark didn't change) and by `infereval retest` (test-retest κ on the same benchmark+model pair). Scientific replication — fresh benchmark constructed independently by a second author following the same construction procedure, evaluated against the same model — is real research-program work the framework can't do for you.

**4.3 Cross-domain comparison (R14).** If your scope is `general_capacity`, evaluate M against a benchmark in a comparison domain D′. The framework can run two benchmarks against the same model; you write up the comparison.

### Phase 5: Write the claims file

```bash
infereval report --init-claims path/to/claims.json
```

This produces a stub with every required field present and `FILL IN` placeholders. Fill in every placeholder — the framework rejects the report render if any required field is missing.

- **R16 — Mastery sense:** pick one of `evaluative` / `generative` / `standing` / `combination`. Most measurement-from-prompt-response work is `evaluative`. Description in your own words, 1–3 sentences.
- **R17 — Scope:** pick the narrowest scope your evidence justifies. Broader scopes need strictly more checks. Justification explains why this scope is right for *your* benchmark.
- **R18 — Constitution vs evidence:** `evidence_of_mastery` is the standard scientific posture (high κ_C is evidence supporting a deeper claim). `constitutive_of_mastery` is Brandom's structural-behavioural reading (agreement plus structural coherence *is* mastery in the inferentialist sense).
- **R19 — Carving acknowledgement:** at `items_in_benchmark` scope, leave `acknowledges_carving_indexed=false`. At broader scopes you **must** set it true AND write non-empty `notes` explaining the carving, or the verdict auto-downgrades.
- **R4, R8, R9, R11, R13, R14, R15, R22 — Competing-explanation checks:** mark `true` only for checks you actually ran (`structural_check_run`, `sensitivity_sweep_run`, `paraphrase_sweep_run`, `cross_panel_check_run`, `independent_reference_panel_used`, `held_out_items_used`, `training_data_separation_verified`, `cross_domain_comparison_run`, `replication_attempted`, `test_retest_run`). Lying here makes the entire report dishonest; the framework can't detect dishonesty but readers will.
- **R22 second leg — Identity criterion (`reliability.identity_criterion`):** fill in the criterion you decided on at Phase 0.6. Framework-substantiated booleans (`same_benchmark_hash`, `same_endorsement_config`, `same_paraphrase_variant`) typically stay `True` — the parity check on `infereval retest` mechanically verifies them. Analyst-substantiated booleans (`same_provider_model_id`, `cross_update_identity_asserted`, `same_scaffolding`) are the substantive commitments — set them honestly based on what you know about the provider and the run window. `unverifiable_caveats` documents what you're committing to without framework backup (e.g. provider snapshot-fingerprint absence on Anthropic, with reasoning for why cross-update identity is nonetheless reasonable to assert). `rationale` is the one-to-three-sentence justification of why these are the right individuation choices. **At scope ≥ `domain_D_as_sampled` with `test_retest_run=True`, the verdict gate requires the criterion to be declared with a non-empty rationale or it caps to `partially_defensible`** — same shape as the R19 carving-acknowledgement gate.

> **Caveat on self-report fields.** `held_out_items_used` and `training_data_separation_verified` are currently self-report: the framework does not cross-check them against the per-item `construction_metadata` that should substantiate them. Honesty in setting these booleans is the substantive audit.
>
> For R22 there are *two* distinct things the framework cannot mechanically verify, and the v0.6.1 reframe separates them cleanly. **(a) Temporal-occasion question:** did the two runs actually happen on different occasions? The framework records run timestamps and provider response IDs where available; it cannot enforce a minimum interval or guarantee independence of the two measurement attempts. This remains a residual analyst-honesty piece — same shape as the leakage-audit-gap self-report. **(b) Identity-criterion question:** what counts as "the same system" across the two runs? This is a separate methodological commitment the analyst declares via `reliability.identity_criterion` (above). The framework records the per-field commitments, mechanically substantiates the setup-conformance subset via the parity check on `infereval retest`, and flags the analyst-substantiated subset with `unverifiable_caveats` for the parts it cannot verify. v0.6.0 conflated (a) and (b); v0.6.1 separates them: (b) is now a declared commitment with a verdict-gate, (a) remains the genuinely-external residual.

### Phase 6: Render the report

```bash
infereval report \
  --evaluation out/myexpt-eta-A.json \
  --benchmark path/to/benchmark.json \
  --claims path/to/claims.json \
  --structure out/structure-report.json \
  --sweep out/sweep_n_samples/sweep-summary.json \
  --model-fit out/model-fit.json \
  --retest out/myexpt-retest.json \
  -o report.md
```

(All `--structure` / `--sweep` / `--model-fit` / `--retest` inputs are optional; supply whichever you ran. Missing inputs show as `NOT SUPPLIED` in the Evidence section.)

The report has seven sections:

1. **Identity** — evaluation id, benchmark id, model, run date, item count, analyst count.
2. **Summary metrics** — coverage, κ_C, κ_F, κ_F\*, and **test-retest κ (R22)** when a retest artifact is supplied.
3. **Construct-validity claims** — your declarations from the claims file, rendered as text.
4. **Evidence** — auto-collected from the optional Phase 3 artifacts.
4b. **Negative findings** — auto-collected from structure / sweep / model-fit / retest. Each subsection lists the items: structural anomalies, sweep instability, factor-effects null findings, test-retest anomalies (per-item flips).
5. **Unaddressed competing explanations** — the list of false flags in `competing_explanations`.
6. **Summary verdict** — ✅ / ⚠️ / ❌ with rationale.

**Suppressing negatives** is deliberately expensive: `--suppress-negatives` replaces section 4b with a suppression banner naming the flag, adds a `Negative-findings suppression: ENABLED` warning to the report header, and downgrades the Summary verdict one tier. Hiding evidence is itself a negative construct-validity signal.

**The summary verdict** is deterministic from claims + artifacts:

- **✅ Defensible** — all required checks for the declared scope are marked run; carving acknowledged + documented when scope is broader than `items_in_benchmark`; no audit cap fires.
- **⚠️ Partially defensible** — some required checks missing; OR an audit cap fires (structural anomalies present despite `structural_check_run=True`; single-analyst benchmark at `items_in_benchmark` scope; substantively unstable retest despite `test_retest_run=True`).
- **❌ Not defensible** — majority of required checks missing, or carving not acknowledged at scope ≥ `domain_D_as_sampled`.

### Phase 7: Publish the artifacts

Reproducibility comes from publishing the full artifact set: benchmark JSON (with `schema_version` declared), per-model evaluation JSONs (each carries `benchmark_hash` for tamper detection), JSONL run logs (one event per sample, full audit trail), the structure / model / sweep / retest outputs (same provenance discipline), the claims file, the rendered report. A consumer with all these can re-validate the benchmark, recompute every metric, and re-render the report from scratch.

Track them in version control. The `experiments/results/stop_sign/` and `experiments/results/pulmonology/` layouts in this repo are good models. The SHA-256 hashes in the evaluation JSONs guarantee no silent rewriting of the benchmark between the evaluation and the report.

### Phase 8: Stand behind the claim

Writing up the result is yours alone. Three discipline points the framework's output gives you:

1. **Quote the verdict.** "The construct-validity report renders ⚠️ partially defensible at scope `domain_D_as_sampled`; specifically, test-retest κ is moderately stable rather than stable." Reviewers can hold you to this.
2. **Don't override the scope.** If the report says ⚠️ at `domain_D_as_sampled`, your write-up shouldn't claim mastery at `general_capacity`.
3. **Carving-indexed framing in the prose.** "GPT-5.5 demonstrates partial mastery of cardiogenic-vs-ARDS pulmonary-edema reasoning *under the B/δ carving of the v0.1 benchmark*" beats "GPT-5.5 understands pulmonary medicine."

## Coverage / current posture

| Requirement | Current posture | How addressed |
|---|---|---|
| R1 documented analyst competence | Partial | Free-text `notes` field; presence validated, content is analyst's responsibility |
| R2 inter-analyst baseline | Full | `inter_analyst_fleiss` (all-analyst default in v0.7.0+), `inter_analyst_fleiss_per_panel` for the per-panel breakdown; report section 2 renders both on panelled benchmarks |
| R3 baseline-relative framing | Full | κ_F* surfaced alongside κ_C / κ_F in every report surface |
| R4 independent reference | Full (tooling); research-program (recruitment) | `cross_panel_kappa`, `inter_analyst_fleiss_per_panel` |
| R5 documented construction | Full | `construction_metadata` per item |
| R6 inferential-type coverage | Full | tags + factorial-design metadata |
| R7 multiple items per condition | Full | `factor_constraints.min_items_per_cell` |
| R8 held-out items | Partial | `authored_blind_to_models`; self-report cross-check is deferred work |
| R9 training-data separation | Partial | `authored_on` for temporal separation; structural overlap is external |
| R10 paraphrase variation | Full | `--paraphrase-cycle` runtime support |
| R11 sensitivity analysis | Full | `infereval sweep` over n_samples / tie_break / paraphrase_variant / temperature |
| R12 per-condition decomposition | Full | `--by-tag` / `--by-rsr-target` decompositions + `infereval model` factor-effects logistic regression |
| R13 structural coherence check | Full | `infereval structure` with four checks (containment, RSR roles, base-case stability, thin-margin) |
| R14 cross-domain comparison | Research-program | tracked as a declared check; downgrades verdict at `scope=general_capacity` when missing |
| R15 replication | Partial | strict reproducibility via SHA-256 hash; test-retest within-pair via `infereval retest`; scientific replication is external |
| R16 mastery sense | Full | required field in claims file |
| R17 claim scope | Full | required field; scope determines required-checks set |
| R18 constitution vs evidence | Full | required field in claims file |
| R19 carving-indexed claims | Full (at report level) | required at scope ≥ `domain_D_as_sampled`; verdict refuses to render `defensible` when missing |
| R20 disclosure of choices | Full | every analyst-supplied choice persists in the benchmark + evaluation + report artifacts |
| R21 negative-results disclosure | Full | auto-collected from structure / sweep / model-fit / retest; `--suppress-negatives` is the explicit, costly opt-out |
| R22 reliability of the measurement | Full (within-run + across-run + declared identity criterion); research-program residual (the *temporal-occasion* question — did the two runs actually happen separately?) | `VerdictDistribution`, `AggregateDispersion`, Politis-Romano CIs via `--ci`; `infereval retest --claims` threads the declared `IdentityCriterion`; verdict-gate at scope ≥ `domain_D_as_sampled` requires both `test_retest_run=True` AND a declared criterion with non-empty rationale (doubly-relative: carving + individuation) |

Three observations from the table.

First, **the bulk of the framework's contribution is making structure visible** — declaring design factors, recording provenance, supporting paraphrase variation, separating reference panels, surfacing within-run dispersion. These are schema and presentation choices that have outsized interpretive impact.

Second, **the philosophically central additions are the structural coherence check (R13), the reliability infrastructure (R22), and the interpretive requirements (R16–R19).** Structural coherence is where the framework moves from supporting agreement measurement to supporting mastery characterisation in the inferentialist sense. Reliability is where the framework refuses to treat any single-run κ as signal without uncertainty quantification and replication. The interpretive requirements are where the framework refuses to render a defensible verdict without explicit commitments about what kind of claim is being made.

Third, **R8, R9, R14, and the institutional half of R15 remain partial or research-program after everything the framework can do.** These genuinely require external resources — independent analysts, training-corpus access, cross-domain studies, fresh replication studies — and the framework's right posture is to make them tractable rather than to claim to provide them. The report tracks each as a declared boolean and downgrades the verdict when they're false at the wrong scope.

## The disposition the instrument embodies

The framework's posture: make the work *cheap enough to do*, and make *undeclared skipping* expensive. The infrastructure handles the bookkeeping that would otherwise make construct validity prohibitively costly (factorial validation, paraphrase cycling, structural checks, dispersion surfacing, retest comparison, report generation); the report structure makes any skip part of the public record, visible to readers who can then weigh whether the missing check matters for the claim being made. **Skipping is permitted; pretending you didn't skip is not.** The cost of skipping is reputational rather than mechanical — the framework cannot stop a determined analyst from publishing whatever they want, but it can refuse to certify a defensible verdict on top of undeclared gaps, and it can make those gaps visible in the artifacts the analyst publishes alongside the claim. For a methodology aimed at supporting publishable mastery claims, reputational cost mediated by documentation is real cost. The asymmetry plays out at three concrete places:

1. **Validation refuses bad designs.** The factorial-design validator rejects under-populated benchmarks; the panel validator rejects partial-panel benchmarks; the claims file rejects missing required fields; `infereval retest` rejects pairs whose configurations differ in ways that would conflate retest variability with parameter effects.
2. **Reports refuse strong claims without evidence.** The construct-validity report deterministically downgrades the verdict when required checks are missing; at `scope=general_capacity` it requires acknowledged + documented carving (R19) or auto-downgrades to `not_defensible`; if a retest is supplied and substantively unstable, the verdict caps at `partially_defensible` regardless of how many other checks ran.
3. **Suppression is visible.** `--suppress-negatives` documents itself in the report header AND downgrades the verdict one tier. Hiding evidence is itself flagged as a negative construct-validity signal.

The research program still has to do the studies. The framework can make it harder to publish a mastery claim without them. That's the right place for a measurement tool to land — taking construct validity seriously without pretending to settle it.

## What this workflow cannot get you

After everything — two panels, structural checks, factor model, sensitivity sweeps, paraphrase robustness, test-retest reliability, cross-domain comparison, and a clean ✅ verdict — you have evidence of agreement at the stated scope, with structural coherence properties, robust to your tested methodological choices, replicated independently, with quantified uncertainty, and with the carving-indexed framing of any in-principle claim. You do not have:

- A model-independent fact about "mastery of D".
- Settlement of whether agreement is constitutive of or evidence for mastery in some deeper sense.
- Assurance that the carving you chose is the one a competent practitioner *would* choose.

The framework doesn't help with any of these — they're not the kind of thing tooling can help with. The methodology is honest about them; your write-up should be too.

## Quick reference: the full command sequence

```bash
# Phase 1: validate the benchmark
infereval validate benchmark.json
infereval describe --items benchmark.json

# Phase 2: evaluate twice for test-retest reliability (R22)
infereval evaluate benchmark.json \
  --provider openai --model gpt-5.5 \
  --n-samples 5 --temperature 0.0 \
  --run-id myexpt-A \
  --log out/run-A.jsonl -o out/eta-A.json

infereval evaluate benchmark.json \
  --provider openai --model gpt-5.5 \
  --n-samples 5 --temperature 0.0 \
  --run-id myexpt-B \
  --log out/run-B.jsonl -o out/eta-B.json

infereval retest out/eta-A.json out/eta-B.json \
  --benchmark benchmark.json --claims claims.json \
  -o out/retest.json

# Phase 3: analytical checks
infereval metrics out/eta-A.json --benchmark benchmark.json \
  --ci --weight-by-margin
infereval structure out/eta-A.json --benchmark benchmark.json
infereval model out/eta-A.json --benchmark benchmark.json -o out/model-fit.json
infereval sweep benchmark.json \
  --provider openai --model gpt-5.5 \
  --vary n_samples --values 1,3,5,7 \
  --out-dir out/sweep/

# Phase 5: claims stub
infereval report --init-claims claims.json
# (edit claims.json, fill in every FILL IN)

# Phase 6: render report
infereval report \
  --evaluation out/eta-A.json \
  --benchmark benchmark.json \
  --claims claims.json \
  --structure out/structure.json \
  --sweep out/sweep/sweep-summary.json \
  --model-fit out/model-fit.json \
  --retest out/retest.json \
  -o report.md
```

Add cross-panel (Phase 4.1) and replication (Phase 4.2) as the research-program work proceeds; re-render the report each time to update the verdict.

## Related reading

- [`concepts.md`](concepts.md) — the methodology's vocabulary and the relationship between the inferentialist framework, the implication-space machinery, and the evaluation primitives.
- [`authoring_benchmarks.md`](authoring_benchmarks.md) — full schema reference for the benchmark JSON.
- [`interpreting_metrics.md`](interpreting_metrics.md) — how to read coverage, κ_C, κ_F, κ_F\*, test-retest κ, the per-decomposition metrics, the CIs from `--ci`, and the weighted variants.
- [`providers.md`](providers.md) — Anthropic / OpenAI / OpenRouter provider configuration.
- [`tutorials/04_pulmonology_visualization.ipynb`](tutorials/04_pulmonology_visualization.ipynb) — visual analytics complementing the CLI tools (matplotlib + pandas; reads the bundled pulmonology artifacts).

## References

Allen, B. P. (2026). Note on Simonelli's Stop Sign Dialogue: An Implication-Space Instrument for Probing LLM Endorsement of Material Inferential Rules.

Baayen, R. H., Davidson, D. J., & Bates, D. M. (2008). Mixed-effects modeling with crossed random effects for subjects and items. *Journal of Memory and Language*, 59(4), 390–412.

Barr, D. J., Levy, R., Scheepers, C., & Tily, H. J. (2013). Random effects structure for confirmatory hypothesis testing: Keep it maximal. *Journal of Memory and Language*, 68(3), 255–278.

Bean, A. M., Kearns, R. O., Romanou, A., Hafner, F. S., Mayne, H., Batzner, J., … & Mahdi, A. (2026). Measuring what matters: Construct validity in large language model benchmarks. *Advances in Neural Information Processing Systems*, 38.

Bender, E. M., & Friedman, B. (2018). Data statements for natural language processing: Toward mitigating system bias and enabling better science. *Transactions of the Association for Computational Linguistics*, 6, 587–604.

Brandom, R. B. (1994). *Making It Explicit: Reasoning, Representing, and Discursive Commitment*. Harvard University Press.

Campbell, D. T., & Fiske, D. W. (1959). Convergent and discriminant validation by the multitrait-multimethod matrix. *Psychological Bulletin*, 56(2), 81–105.

Cowart, W. (1997). *Experimental Syntax: Applying Objective Methods to Sentence Judgments*. Sage.

Cronbach, L. J., & Meehl, P. E. (1955). Construct validity in psychological tests. *Psychological Bulletin*, 52(4), 281.

Fleiss, J. L. (1971). Measuring nominal scale agreement among many raters. *Psychological Bulletin*, 76(5), 378–382.

Freiesleben, T. (2026). Establishing Construct Validity in LLM Capability Benchmarks Requires Nomological Networks. *arXiv preprint* arXiv:2603.15121.

Gebru, T., Morgenstern, J., Vecchione, B., Vaughan, J. W., Wallach, H., Daumé III, H., & Crawford, K. (2021). Datasheets for datasets. *Communications of the ACM*, 64(12), 86–92.

Hlobil, U., & Brandom, R. B. (2025). *Reasons for Logic, Logic for Reasons*. Routledge.

Landis, J. R., & Koch, G. G. (1977). The measurement of observer agreement for categorical data. *Biometrics*, 33(1), 159–174.

Lu, Y., Bartolo, M., Moore, A., Riedel, S., & Stenetorp, P. (2022). Fantastically ordered prompts and where to find them. *ACL 2022*.

McCoy, R. T., Pavlick, E., & Linzen, T. (2019). Right for the wrong reasons: Diagnosing syntactic heuristics in natural language inference. *ACL 2019*.

Messick, S. (1989). Validity. In R. L. Linn (Ed.), *Educational Measurement* (3rd ed., pp. 13–103). American Council on Education.

Mitchell, M., Wu, S., Zaldivar, A., Barnes, P., Vasserman, L., Hutchinson, B., Spitzer, E., Raji, I. D., & Gebru, T. (2019). Model cards for model reporting. *FAT\* 2019*.

Munafò, M. R., et al. (2017). A manifesto for reproducible science. *Nature Human Behaviour*, 1, 0021.

Open Science Collaboration. (2015). Estimating the reproducibility of psychological science. *Science*, 349(6251).

Pineau, J., et al. (2021). Improving reproducibility in machine learning research. *JMLR* 22(164).

Politis, D. N., & Romano, J. P. (1994). Large sample confidence regions based on sub-samples under minimal assumptions. *The Annals of Statistics*, 22(4), 2031–2050.

Ribeiro, M. T., Wu, T., Guestrin, C., & Singh, S. (2020). Beyond accuracy: Behavioral testing of NLP models with CheckList. *ACL 2020*.

Sainz, O., Campos, J. A., García-Ferrero, I., Etxaniz, J., de Lacalle, O. L., & Agirre, E. (2023). NLP evaluation in trouble. *EMNLP 2023*.

Salaudeen, O., Reuel, A., Ahmed, A., Bedi, S., Robertson, Z., Sundar, S., … & Koyejo, S. (2025). Measurement to meaning: A validity-centered framework for AI evaluation. *arXiv preprint* arXiv:2505.10573.

Schütze, C. T. (1996/2016). *The Empirical Base of Linguistics*. Language Science Press.

Sclar, M., Choi, Y., Tsvetkov, Y., & Suhr, A. (2024). Quantifying language models' sensitivity to spurious features in prompt design. *ICLR 2024*.

Simonelli, R. (2026). Sapience without sentience. *Asian Journal of Philosophy*, 5(1).

Sprouse, J., & Almeida, D. (2012). Assessing the reliability of textbook data in syntax. *Journal of Linguistics*, 48(3).

Sprouse, J., Schütze, C. T., & Almeida, D. (2013). A comparison of informal and formal acceptability judgments. *Lingua*, 134.
