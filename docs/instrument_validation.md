# Instrument validation walkthrough

This is a standalone walkthrough of `infereval` for a **reviewer or reader who
needs to assess a study that uses it**, and for **authors defending an
infereval-based result in print**. It moves from what the instrument measures,
to how the implementation realizes that construct, to the argument that the
measurement is valid — and to the limits of what it establishes.

It is the reviewer-facing companion to the more design-oriented
[Construct validity](construct_validity.md), [Architecture](architecture.md),
and [Interpreting metrics](interpreting_metrics.md) pages; where they explain
*how the framework is built*, this page assembles *why a study built on it can
be trusted*, and hands you a one-page [reviewer checklist](reviewer_checklist.md)
to apply to a specific paper.

---

## 1. Purpose and audience

infereval is a **domain-general instrument for measuring whether a language
model endorses the material inferences of a discourse** — the moves a competent
practitioner in that domain would license or forbid. It works in any domain that
admits expert labeling: clinical reasoning, legal doctrine, discourse semantics,
ontology curation. The clinical CPE-vs-ARDS pilot and the stop-sign example are
*worked fixtures*, not the target.

A reviewer's job is to check three things, which structure this document:

1. that the **implementation faithfully realizes the formal construction** it
   claims to (§2–§4);
2. that the **study used the instrument correctly** (§5); and
3. that the **measurement supports the inference the authors draw from it** —
   and no more (§6–§10).

---

## 2. Construct and operationalization

The construct is **inferential mastery**: command of which inferences a domain's
vocabulary makes good, bad, or unsettled. infereval operationalizes it through
the Hlobil–Brandom implication-space framework as formalized in Allen (2026).

- **Bearers** `B` — the atomic contents of the discourse (e.g. *"the patient has
  BNP < 100"*, *"a is a stop sign"*). Each bearer has a canonical natural-language
  expression `δ(φ)`.
- **Implication** `⟨Γ, Δ⟩` — a candidate material inference from a premise set
  `Γ` to a succedent set `Δ`, both drawn from `B`.
- **Endorsement verdict** `E_M(⟨Γ, Δ⟩) ∈ {good, bad, abstain}` — the model `M`'s
  judgment of that inference, elicited by repeated sampling and majority vote.
- **Derived implication frame** `⟨B, I_M⟩` — the model's implication space:
  `⟨Γ, Δ⟩ ∈ I_M` iff `Γ ∩ Δ ≠ ∅` (Containment) **or** `E_M(⟨Γ, Δ⟩) = good`.

The measurement compares `E_M` against a panel of human **analyst verdicts**
`V_i`. Agreement is the evidence of mastery; the framework never claims the model
"has" mastery in a metaphysical sense — see §10.

**Arity.** As of v0.17.2 the succedent `Δ` is a *set*, so the instrument covers
`|Δ| = 1` (the classic "does ψ follow?"), `|Δ| = 0` (incompatibility — "can Γ be
committed at all?"), and `|Δ| ≥ 2` (disjunction — "committing Γ while denying all
of Δ is incoherent?"). Single-succedent is exactly the `|Δ| = 1` special case, so
every pre-v0.17.2 benchmark and result is unchanged.

---

## 3. Formal grounding and code correspondence

A reviewer can check that the code realizes the definitions by reading this
table. Each formal object has one authoritative implementation site.

| Formal object (Allen 2026) | Code |
|---|---|
| Bearer set `B`, expression `δ(φ)` | `types.Bearer` (`id`, `expression`, `paraphrases`) |
| Context functions `ctx_Γ`, `ctx_Δ` | `context.py` builders (premise join `" and "`, conclusion join `" or "`) |
| Implication `⟨Γ, Δ⟩` | `types.Implication` (`premises`, `conclusions` as `frozenset[str]`) |
| Endorsement `E_M` (Def. 2) | `endorsement.endorse()` — n-sample verification prompt → parse → `majority_vote` |
| Unparseable → abstain (Def. 2) | `prompts.parse_verdict` returns `(ABSTAIN, "unparseable")` |
| Frame membership `I_M` (Def. 3) | `frame.DerivedFrame.contains()` |
| Containment, clause (i): `Γ ∩ Δ ≠ ∅` | `types.Implication.intersects()`; `⟨∅,∅⟩` excluded via `is_empty_empty` |
| Coverage `cov`, per-analyst `cov_j` (Def. 6) | `metrics.coverage`, `coverage_per_analyst` |
| Substantive index `S` (Def. 7) | `metrics.substantive_index` |
| Analyst consensus `c_i` (Def. 8) | `metrics.consensus_verdict` / `consensus_reference` |
| Cohen's `κ_C` (Def. 9) | `metrics.cohens_kappa` |
| Fleiss' `κ_F`, inter-analyst `κ_F*` (Def. 10) | `metrics.fleiss_kappa`, `inter_analyst_fleiss` |

The measurement layer (`metrics.py`, Definitions 6–10) is **shape-blind**: it
reads only the three-valued `Verdict`, never the arity or bearer structure of an
item. That isolation is what lets the multi-succedent generalization land under a
live benchmark without touching κ.

---

## 4. End-to-end data flow

One item, from benchmark to metric:

```
benchmark item ⟨Γ, Δ⟩ + bearers
   │  δ(φ) per bearer → ctx_Γ(Γ), ctx_Δ(Δ)               (context.py)
   ▼
prompt = question_form.frame( template.render(request) )  (endorsement.py + templates.py)
   │  n_samples provider calls (repeated sampling)         (providers/*)
   ▼
parse each completion → Verdict ; provider failure → provider_error (NOT abstain)
   ▼
majority_vote → E_M(⟨Γ, Δ⟩)                                 (endorsement.py)
   ▼
EvaluationItem in η  ── written with full provenance to run.jsonl
   ▼
coverage / substantive index / κ_C / κ_F* ; frame membership ; monotonicity  (metrics/frame/monotonicity)
```

The prompt is composed from **two independent axes** (v0.17.2):
`prompt = question_form.frame(template.render(req))`. The `template` renders the
*content scaffolding* (the commit/deny position, in a domain idiom, never seeing
bearer ids); the `question_form` supplies the *logical question* asked about it
(`support`: "does the conclusion follow?"; `coherence`: "is this position
coherent?") and the answer labels. There is **no hidden "core semantics" behind
the prompt** — a model verdict is a majority vote over responses to one prompt,
and both axes write to that single prompt. A reviewer should read a study's
reported `question_form` and template id as jointly defining what was asked.

---

## 5. Correct use

**Authoring.** A benchmark declares bearers, an analyst panel, and items with
analyst verdicts. Ordinal families, monotonicity ladders, a variation typology
(base / strengthen / contested / defeat / abstain_anchor / monotonicity_step),
and `@copresent` / `@entails` / `~regularity` structure can be declared in a
bearers file and loaded with `infereval bearers-import` (v0.17.0). See
[Authoring benchmarks](authoring_benchmarks.md).

**Evaluating.** `infereval evaluate` (or `evaluation.evaluate`) issues
`n_samples` completions per item, parses and majority-votes. The reviewer should
confirm the study **pinned the model snapshot and sampler config** — model
behavior drifts under a fixed API string, so the exact snapshot must be recorded,
not just the family name.

**Choosing the question form.** `support` is the classic single-succedent
question; `coherence` is the arity-uniform bilateral question. Whatever form the
model is evaluated under, the **human survey must use the same form** (v0.17.4) —
otherwise `κ_C(model vs analyst)` compares two different questions. Both
`infereval survey export` and `import` take `--question-form`.

**Reading outputs.** Report `κ_C` **against the inter-analyst baseline `κ_F*`**,
not against 1.0 — a model can only be as reliable as the panel it is measured
against. Report coverage per run. State the R22 interval for any reliability
claim.

---

## 6. The validity argument

Each design decision defends a specific threat to construct validity.

- **Reliability (R22).** `infereval retest` recomputes `E_M` after an interval and
  reports test–retest `κ`; the bundled demonstrations capture three intervals
  (back-to-back, ~1 h, day-out ~35 h). An **identity criterion** (`report.py`)
  records what "same instrument" means for the comparison (same benchmark hash,
  endorsement config, paraphrase variant; same model snapshot). A mastery claim
  that does not survive R22 at the relevant interval is not defensible.
- **Content / paraphrase robustness.** The paraphrase axis (Remark 9) varies
  `δ(φ)` under fixed inferential content; the **template-equivalence guard**
  (`guards.template_equivalence`, v0.17.3) lifts the same check to the verdict
  layer — two templates over the same items must agree within a tolerance
  (default per-item TV distance `< 0.10` at `N ≥ 30`), or the template is doing
  semantic work and must be fixed before shipping.
- **Discriminant validity / competing explanations.** `report.py` records
  explicit checks for the alternative explanations of agreement (independent
  reference, held-out items, training-data separation, sensitivity, structural
  coherence, etc.); unaddressed ones are surfaced in the report, not hidden.
- **Baselines.** `κ_F*` (`inter_analyst_fleiss`) is the ceiling: model–analyst
  `κ_C` is read against how well the analysts agree with each other.
- **Graded-evidence mastery.** The monotonicity scorer (`monotonicity.py`,
  v0.17.1) checks that endorsement moves monotonically along an ordinal family
  (`bad < good`, `abstain` a skipped gap, a violation is a strict inversion) — a
  probe of inferential mastery beyond flat κ.
- **Instrumentation integrity.** A failed provider call is a **distinct state,
  not an abstain**: `providers` raise `EmptyResponseError` / retry, and
  `SampleRecord.provider_error` marks instrument failures so aggregators skip
  them (v0.15.0). The **placeholder firewall** (v0.17.0) mechanically bars the
  measurement layer from reading an author's provisional `placeholder` marker —
  `analyst_verdicts` is the sole κ source, enforced by a CI gate. This is the
  same discipline that let the framework catch its own silent-failure bug (see
  `KNOWN_ISSUES_v0.14.0.md`).

---

## 7. Threats to validity and their mitigations

| Threat | Mitigation | Where |
|---|---|---|
| Surface-form sensitivity read as content judgment | paraphrase axis + template-equivalence gate | `guards.py`, Remark 9 |
| Silent API failure counted as model abstention | `provider_error` state; failed calls excluded, not scored | `providers/base.py`, `metrics.py` |
| Abstain conflated with error | three-valued `Verdict` + separate `provider_error` | `evaluation.SampleRecord` |
| Author's guess leaking into the reference | placeholder firewall (CI-enforced) | `test_placeholder_firewall.py` |
| Cross-run comparison over different setups | §12.1 setup guard (same snapshot + sampler) | `comparison._assert_same_setup` |
| κ read over too little overlap | coverage floor → "insufficient overlap", not a low-N κ | `comparison.compare_runs` |
| Model drift under a fixed API name | R22 test–retest + pinned snapshot in provenance | `retest.py`, `logging_setup.py` |
| κ misread against 1.0 | report against `κ_F*` baseline | `metrics.inter_analyst_fleiss` |
| Exhaustivity items inflating a "respects the partition" number | exclusivity/exhaustivity stratification | `stratify.arity_partition` |

---

## 8. Reproducibility and audit trail

Every run writes a `run.jsonl` alongside η recording, per model call: the full
composed prompt + system text, the raw completion, the parsed verdict, the model
id + snapshot, the sampler config, and the `question_form` (v0.17.3, §12.3). η
itself carries the benchmark hash, endorsement config (including `question_form`),
and framework version. A reviewer can therefore:

- re-derive every `E_M` verdict from the logged completions;
- confirm the model snapshot and sampler config were pinned across compared runs;
- run `infereval audit` to detect legacy silent-failure samples heuristically;
- confirm the same `(item, question_form, template, sampler, snapshot)` yields the
  same prompt string (determinism).

---

## 9. Worked examples

- **Clinical pilot (CPE vs ARDS).** A single-succedent clinical fixture with
  ordinal families and monotonicity ladders. The bundled dry-run shows all three
  ladders (C/F/G) monotone across six frontier models, with ladder C carrying an
  informative `bad → good` BNP transition — positive evidence of graded-evidence
  mastery, scored natively by `infereval monotonicity`.
- **Stop sign (Simonelli).** The paper's Example 1: most frontier models
  reproduce the analyst row, with the documented exceptions surfaced as negative
  findings rather than smoothed over.

Both are shipped end to end (benchmark → η → metrics → report) so a reviewer can
run the whole pipeline and reproduce the reported numbers.

---

## 10. Limitations and scope of claims

- **Operational, not metaphysical.** Agreement with an expert panel is evidence
  that the model *endorses* the domain's material inferences as the panel does;
  it is not a claim that the model *understands* or *possesses* mastery. The
  report's mastery-sense and constitution claims (R16, R18) make this explicit.
- **Scope is the sampled domain.** A result licenses a claim about the benchmark
  and, with care, the domain as sampled — not "general reasoning capacity"
  (the R17 scope claim).
- **Reliability is interval-relative.** An R22 result holds for the interval and
  identity criterion stated; cross-model-update stability is a stronger, separate
  claim.
- **Single- vs multi-succedent readings.** The instrument elicits and scores
  verdicts; it does not *compose* them. Multisuccedent cut / RSR-closure is
  deferred by design (`frame.derive_closure` is an explicit `NotImplementedError`
  seam) — classical vs substructural readings of disjunctive content diverge
  exactly there, and no result here depends on that choice.
- **`κ_F*` bounds what is knowable.** Where analysts disagree, the model cannot be
  shown more reliable than the panel; a low `κ_F*` limits the strength of any
  model claim in that domain.

For a study using infereval, the [reviewer checklist](reviewer_checklist.md)
turns this section into a set of yes/no questions.
