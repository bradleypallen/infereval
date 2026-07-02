# Glossary

Every paper symbol the codebase tracks, with its in-code counterpart and a
one-liner meaning. The same notation is used throughout the docs and the
docstrings; this page collects it in one place so you can cross-reference
quickly.

The authoritative source is the paper. This page summarises the
**code/paper contract** the package maintains.

## Core symbols (paper Definitions 1–10)

| Symbol | Name | In code | Meaning |
|---|---|---|---|
| `V` | Vocabulary | (conceptual) | Finite set of tokens. |
| `L = V*` | Token sequences | (conceptual) | Finite sequences over `V` — natural-language statements live here. |
| `B` | Bearer set | `Benchmark.bearers` (keys); [`Bearer`](api.md#infereval.types.Bearer) at runtime | Non-empty set of bearers — the items that play implicational roles. |
| `δ : B → L` | Expression function | `BearerModel.expression` (+ `paraphrases`) | Maps each bearer to its natural-language expression. Analyst-supplied. |
| `ctx_Γ : ℘(B) → L` | Premise-set context builder | [`ContextBuilders.premise`](api.md#infereval.benchmark.ContextBuilders) | Packages a premise set as natural-language context. Default: conjunction by "and". |
| `ctx_Δ : ℘(B) → L` | Succedent-set context builder | [`ContextBuilders.conclusion`](api.md#infereval.benchmark.ContextBuilders) | Packages a succedent set as natural-language context. Any arity as of v0.17.2 (`\|Δ\|` = 0, 1, or ≥2); default join by "or". |
| `⟨B, I⟩` | Implication frame | (Hlobil–Brandom) | A bearer set plus an implication relation `I ⊆ ℘(B) × ℘(B)`. |
| `⟨B, I_M⟩` | Derived implication frame | [`DerivedFrame`](api.md#infereval.frame.DerivedFrame) | The frame derived from `M`'s endorsement verdicts (paper's Definition 3). Containment-closed by construction (clause i). |
| `E_M` | Endorsement function | [`endorse()`](api.md#infereval.endorsement.endorse) | `E_M(⟨Γ, {ψ}⟩) ∈ {good, bad, abstain}`. Computed by majority vote over `n_samples` provider calls. |
| `RSR` | Range of subjunctive robustness | (analytical) | For a target inference `⟨X, {ψ}⟩`, the side-premise extensions `Y` that preserve endorsement of `ψ` from `X`. |
| `β` | Benchmark | [`Benchmark`](api.md#infereval.benchmark.Benchmark) | `{(I_1, V_1), …, (I_n, V_n)}`. Items + analyst verdicts. Paper's Definition 4. |
| `η` | Evaluation | [`Evaluation`](api.md#infereval.evaluation.Evaluation) | `{(I_i, V_i, E_M(I_i))}`. Paper's Definition 5. |
| `V_i = (v_{i,1}, …, v_{i,m})` | Analyst verdict tuple | `BenchmarkItem.analyst_verdicts` | Verdicts of each of the `m` analysts on item `i`. |
| `m` | Number of analysts | `Benchmark.m` | `len(benchmark.analysts)`. |
| `n` | Number of items | `Benchmark.n` | `len(benchmark.items)`. |
| `c_i` | Analyst consensus | [`consensus_verdict()`](api.md#infereval.metrics.consensus_verdict) | Strict majority of `(v_{i,1}, …, v_{i,m})`; abstain on tie. Paper's Definition 8. |

## Agreement measures (paper Definitions 6–10)

| Symbol | Name | In code | Meaning |
|---|---|---|---|
| `cov(η)` | Coverage | [`coverage()`](api.md#infereval.metrics.coverage) | Fraction of items where `M` produced a substantive verdict. |
| `cov_j(η)` | Per-analyst coverage | [`coverage()`](api.md#infereval.metrics.coverage) per column | Analog for each human analyst. |
| `S(η, r)` | Substantive index | (internal filter) | Items where both `M` and reference `r` are substantive. Paper's Definition 7. |
| `S_F` | Fleiss substantive index | (internal filter) | Items where **every** annotator is substantive. Paper's Definition 10. |
| `κ_C(η, r)` | Cohen's kappa | [`cohens_kappa()`](api.md#infereval.metrics.cohens_kappa) | `M`'s agreement with reference `r` (consensus or a single analyst). Chance-corrected against `{good, bad}` marginals. Paper's Definition 9. |
| `κ_F(η)` | Fleiss' kappa | [`fleiss_kappa()`](api.md#infereval.metrics.fleiss_kappa) | Agreement across all `m + 1` annotators (analysts + `M`). Paper's Definition 10. |
| `κ_F^*(β)` | Inter-analyst Fleiss baseline | [`inter_analyst_fleiss()`](api.md#infereval.metrics.inter_analyst_fleiss) | Fleiss' kappa over analyst verdicts alone, computed across the full analyst pool whose verdicts the benchmark records (the v0.7.0 default, which fixed the pre-0.7.0 silent narrowing to the primary panel — see [#82](https://github.com/bradleypallen/infereval/issues/82)). The baseline against which `κ_C` and `κ_F` are interpreted (paper's Remark 4). Undefined when `m < 2` or analysts unanimous. On panelled benchmarks, the primary-panel value is available via [`inter_analyst_fleiss_per_panel(bench)[bench.resolved_primary_panel()]`](api.md#infereval.metrics.inter_analyst_fleiss_per_panel) or via the explicit `analyst_indices=` parameter, and is rendered as a sub-bullet under the all-analyst headline in the construct-validity report's section 2. |

## analyst vs annotator — **load-bearing**

Treat as a hard distinction in code and prose:

| Term | What it means | Count |
|---|---|---|
| **Analyst** | A human labeler whose verdicts appear in `V_i`. | `m` |
| **Annotator** | A human-plus-`M` ensemble member. The `(m+1)`th annotator in `κ_F` is `M`. | `m + 1` |

`fleiss_kappa(η)` operates on `m + 1` annotators (analysts plus `M`).
`inter_analyst_fleiss(β)` operates on `m` analysts (no `M`). This is the
load-bearing distinction in the Fleiss definition (paper's Definition 10).

## Construct-validity terminology

See [Construct validity of the instrument](construct_validity.md) for the
end-to-end requirements catalogue and workflow.

| Term | In code | Meaning |
|---|---|---|
| **Carving** | (analyst-chosen) | The way the discursive practice is partitioned into bearers + `δ` + context builders. Content-attribution is relative to it (paper's Remark 6). |
| **Mastery sense** | `MasterySenseClaim.sense` | One of `evaluative` / `generative` / `standing` / `combination`. Declares which sense of mastery the claim concerns (paper's Remark 7). |
| **Scope** | `ScopeClaim.scope` | One of `items_in_benchmark` / `domain_D_as_sampled` / `general_capacity`. The breadth of the claim. Broader scopes require strictly more competing-explanation checks. |
| **Constitution** | `ConstitutionClaim.position` | One of `evidence_of_mastery` / `constitutive_of_mastery`. The philosophical position the analyst is taking. |
| **Carving-indexed claim** | `CarvingClaim.acknowledges_carving_indexed` | Required `True` at non-`items_in_benchmark` scopes — in-principle claims must take the carving-indexed form (paper's Remark 10). |
| **`κ_F^*`-stability** | `SweepResult.stability_verdict` | The sensitivity-sweep verdict: `stable` / `moderately sensitive` / `substantively variable`. |
| **Verdict distribution** | `VerdictDistribution` (in `infereval.metrics`) | Per-item (good, bad, abstain) count over the n_samples model verdicts, plus the post-tie-break verdict and derived `entropy` (normalised Shannon) and `margin` (plurality margin). Surfaces the within-run dispersion the standard majority-vote pipeline collapses. |
| **Plurality margin** | `VerdictDistribution.margin` | `(top - runner_up) / n_samples` in `[0, 1]`. 0 on ties; 1 on unanimous sampling. Used as the per-item confidence weight in the `--weight-by-margin` κ variants. |
| **Verdict entropy** | `VerdictDistribution.entropy` | Normalised Shannon entropy of the verdict distribution, in `[0, 1]`. 0 for single-class, 1 for uniform 3-way distribution. |
| **Aggregate dispersion** | `AggregateDispersion` | Corpus-level summary: mean entropy, mean margin, `n_thin_margin` (count of items below the thin-margin threshold), `n_tie_broken`. |
| **Subsampling CI** | `subsampling_kappa_ci` | Politis-Romano (1994) item-level subsampling CI on κ. Resamples items WITHOUT replacement at size `b = round(K^0.7)`, recomputes κ on each subsample, constructs a basic-percentile CI with the `√(b/K)` rate correction. Valid for κ's non-smooth functional form where the Efron bootstrap can fail. |
| **Test-retest κ** | `RetestResult.test_retest_kappa` | Cohen's κ between the collapsed-verdict columns of two evaluations of the same benchmark+model pair. Within-model analog of κ_F* — quantifies how much of the headline κ_C is shared signal across replications vs. run-specific noise. |
| **Retest stability verdict** | `RetestResult.stability_verdict` | The R22 reliability ladder: κ ≥ 0.8 stable; ≥ 0.6 moderately stable; < 0.6 substantively unstable (at which point the headline κ_C cannot be interpreted as signal). v0.6.1: when an identity criterion is supplied, the verdict text appends "under the declared identity criterion" to make the relativity explicit. |
| **Identity criterion** | `IdentityCriterion` (in `infereval.report`) | R22 second leg (v0.6.1+). The analyst-declared individuation criterion under which a test-retest κ is interpretable as reliability. Per-field booleans split into framework-substantiated (`same_benchmark_hash`, `same_endorsement_config`, `same_paraphrase_variant` — mechanically verified by `infereval retest`'s parity check) and analyst-substantiated (`same_provider_model_id`, `cross_update_identity_asserted`, `same_scaffolding` — assertions the framework records with caveats per the leakage-audit-gap pattern), plus `unverifiable_caveats` and `rationale` free-text. Required at scope ≥ `domain_D_as_sampled` when `test_retest_run=True` for R22 satisfaction. |
| **Reliability claim** | `ReliabilityClaim` (in `infereval.report`) | R22 claims-file block wrapping `IdentityCriterion`. Sub-block on `ConstructValidityClaims.reliability`, peer to `mastery_sense` / `scope` / `constitution` / `carving`. Optional at the top level for backward compatibility with pre-v0.6.1 claims files. |

## Role tags (RSR-targeted benchmarks)

When an item declares an `rsr_target` and a role tag, the structural check
[`infereval structure`](api.md#infereval.structure.run_all_checks)
compares `M`'s verdict to the role-predicted verdict.

| Tag | Predicted verdict | Meaning |
|---|---|---|
| `base-inference` | (anchors the target) | Items establishing the unconditional inference `⟨X, {ψ}⟩`. |
| `irrelevant-addition` | Same as base | A side premise that should preserve the inference under RSR. |
| `supporter` | `good` when base is `good` | A side premise that strengthens the inference. |
| `defeater` | `bad` when base is `good` | A side premise that defeats the inference. |

## Construction-metadata fields

Per-item provenance for the construct-validity audit (paper-aligned with
R5 / R8 / R9 in [Construct validity](construct_validity.md)).

| Field | Type | Meaning |
|---|---|---|
| `authored_by` | `str \| None` | Identifier of the author of this item (R5). |
| `authored_on` | `date \| None` | ISO date the item was authored — substrate for temporal training-data separation arguments (R9). |
| `authored_blind_to_models` | `list[str]` | Models the author had not observed on a draft of this item — the held-out declaration (R8). |
| `source` | `str \| None` | Free-form citation for the primary material the author worked from. |
| `analyst_rationales` | `list[str] \| None` | Optional per-analyst, per-item natural-language rationale, positionally aligned to `analyst_verdicts`. `None` (or absent) means "no rationale discipline"; an empty string means "verdict given, no reason recorded" — semantically distinct (paper-aligned with the AR1–AR12 spec). |

## Multi-succedent generalization (v0.17.x)

See the [instrument validation walkthrough](instrument_validation.md) for how
these fit the validity argument.

| Term | In code | Meaning |
|---|---|---|
| Arity of `Δ` | `len(item.conclusions)` | `\|Δ\| = 1` single-succedent (the classic case), `0` incompatibility, `≥2` disjunctive. |
| `question_form` | `EndorsementConfig.question_form` | `support` ("does the conclusion follow?", `\|Δ\|=1` only) or `coherence` ("is committing Γ and denying Δ coherent?", any arity). Persisted in η. |
| Coherence polarity | [`templates.coherence_decode`](api.md#infereval.templates) | Server-side inversion: incoherent → good, coherent → bad, unclear → abstain — uniform across arities (at `\|Δ\|=0` reads as "incompatible → good"). |
| Template | [`templates.Template`](api.md#infereval.templates) | Renders the content scaffolding (never sees bearer ids); bound per benchmark id. `prompt = question_form.frame(template.render(req))`. |
| Ordinal family / monotonicity | [`monotonicity`](api.md#infereval.monotonicity) | An ordered tier family; the scorer checks non-decreasing endorsement (`bad < good`, `abstain` a gap, strict inversion = violation). |
| Constraint compiler | [`compiler.compile_constraints`](api.md#infereval.compiler) | Family declarations → pairwise exclusivity sequents + `@copresent` admissibility rules. |
| Cross-run κ / guards | [`comparison`](api.md#infereval.comparison), [`guards`](api.md#infereval.guards) | Cross-run agreement (TV distance + κ over both-substantive) and the template-equivalence / shuffle gates. |
