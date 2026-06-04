# Changelog

All notable changes to `infereval` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the additional commitment that the benchmark and evaluation JSON
schemas are versioned independently (`schema_version: "1.0"`) and promised
stable from 1.0 onward, regardless of the framework version.

## [Unreleased]

No changes yet.

## [0.9.1] — 2026-06-03

**Bug fix**: hide internal `[item:<tag>]` machine markers from the respondent-visible question titles on Google Forms and SurveyMonkey surveys.

### Why the change

The v0.9.0 Google Forms and SurveyMonkey generators embedded `[item:<sha8>]` directly in each question's *visible* title so the CSV importer could parse it back as the mapping key. Reported in conversation by a user running `infereval survey export` against the stop-sign benchmark: the rendered Google Form showed `Item 2 of 4 [item:item_0f719b1f]` to respondents — machine noise in a survey clinicians and other domain experts will see. Qualtrics was unaffected because its `DataExportTag` carries the mapping inside the `.qsf` payload, not the visible title.

### Fix

- **Generators** (`google_forms_gas.build_gas_script`, `surveymonkey_api.build_surveymonkey_payload`): drop the `[item:<tag>]` marker from question titles. Verdict-question titles now read `"Item N of M\n\n<prompt>"` (the `Item N of M` progress indicator is standard survey copy). Rationale-question titles now read `"Item N rationale (optional) — <prompt>"`. Same shape on both platforms.
- **Importers** (`google_forms_csv.parse_google_forms_csv`, `surveymonkey_csv.parse_surveymonkey_csv`): the parsers gain a `mapping` parameter and resolve `^Item (\d+)` anchors against `mapping[N-1]["verdict_data_export_tag"]` / `["rationale_data_export_tag"]`. The legacy `[item:<tag>]` regex remains as a fallback so CSVs from pre-v0.9.1 forms continue to import.
- **CLI** (`infereval/cli/survey_cmd.py`): the export command now **always** writes the mapping sidecar for `--platform google_forms` and `--platform surveymonkey` (was conditional on hashed ids in v0.9.0). The import command loads the sidecar once and threads it into the per-platform parser.

### Backward compatibility

CSVs collected from v0.9.0-generated forms continue to import cleanly — the legacy `[item:<tag>]` regex still fires. A regression-guard test against a captured v0.9.0-shaped fixture asserts this. Code calling `parse_google_forms_csv(path)` or `parse_surveymonkey_csv(path)` without the new `mapping=` argument also still works, falling back to the legacy regex.

### Tests

- New regression-guard tests assert `[item:` does *not* appear in v0.9.1+ generated titles.
- New v0.9.0-shape fixture at `tests/fixtures/google_forms/responses_v0_9_0_legacy.csv` + tests for the legacy backward-compat path.
- Updated fixtures `responses_known_good.csv` to the v0.9.1+ column-header shape + companion `.mapping.json` sidecars next to each.

## [0.9.0] — 2026-06-03

**New asynchronous-recruitment surface: `infereval survey {export, import}`** supporting Qualtrics, Google Forms, and SurveyMonkey. The headline-metrics surface is unchanged; the new feature is purely additive.

### Why the change

Recruiting a domain expert (clinician, lawyer, software engineer) to add their verdicts to an `infereval` benchmark previously required the recruiter to hand-build a spreadsheet, send it to the expert, and transcribe the results back into the benchmark JSON. For clinical domains where the expert pool is geographically distributed and time-constrained, the manual workflow was the rate-limiting step for benchmark growth.

This release closes that loop via the three dominant research-survey platforms. Different research groups have different institutional licenses (some have Qualtrics; some use Google Forms because it's free; some have SurveyMonkey). Supporting all three from the start removes "what survey platform do you use" as a barrier to recruitment.

The merged benchmark is a regular `Benchmark` JSON file — fully validated by the existing `Benchmark.model_validator` — so it's drop-in usable in the rest of the pipeline (`describe`, `metrics`, `report`, etc.).

### Added

- **`infereval survey export <benchmark.json>`** — produces the platform-specific artifact:
  - `--platform qualtrics` (default) → `.qsf` JSON file the recruiter uploads via the Qualtrics UI; no credentials.
  - `--platform google_forms` → `.gs` Apps Script file the recruiter pastes into script.google.com; no credentials.
  - `--platform surveymonkey` → live `POST /v3/surveys` API call; requires `SURVEYMONKEY_ACCESS_TOKEN` env var (or `--surveymonkey-token`); writes the API response (including survey id, edit URL, share URL) to the output path.
  - Shared flags: `--title`, `--randomize-items/--no-randomize-items` (default on), `--include-rationales/--no-include-rationales` (default on), `--expertise-prompt`.
- **`infereval survey import <benchmark.json>`** — merges platform CSV exports back into the benchmark:
  - `--platform` dispatches to the per-platform CSV parser.
  - `-r/--responses <csv>` + `-o/--output <new-bench.json>`.
  - `--mapping <sidecar.json>` for hashed-id traceability (auto-discovered next to the CSV when present).
  - `--analyst-id-prefix` (default `"clinician-"`), `--respondent <ResponseId>` for single-respondent filter, `--require-complete/--allow-partial` (default require-complete).
- **`AnalystModel.expertise_description: str | None = None`** — new additive field on the benchmark schema. Free-text expertise blurb captured at recruitment time, distinct from the existing `notes` field (which is general analyst annotations). Pre-v0.9.0 benchmarks validate unchanged.
- **`infereval.survey/` module surface**: `render.render_implication_text`, `render.sanitize_export_tag`, `render.SurveyRespondent` (frozen dataclass shared by all platforms), plus per-platform generators (`qualtrics_qsf.build_qsf`, `google_forms_gas.build_gas_script`, `surveymonkey_api.build_surveymonkey_payload` + `publish_to_surveymonkey`), CSV importers (`qualtrics_csv.parse_qualtrics_csv`, `google_forms_csv.parse_google_forms_csv`, `surveymonkey_csv.parse_surveymonkey_csv`), and a shared `qualtrics_csv.merge_respondents` that all three platforms' importers call through.

### Platform notes

- **Qualtrics** uses its `DataExportTag` field for the QID ↔ item.id mapping; the CSV column header is the tag directly. Force-response on verdicts; optional response on rationales. Item randomization fully honored via the block-level `Randomization.RandomizeAll` payload.
- **Google Forms** has no `DataExportTag` equivalent, so the exporter encodes the sanitized item tag as `[item:<tag>]` in each question title; the importer parses it back via regex. **Caveat**: Google Forms' `FormApp.setShuffleQuestions` is whole-form (including the expertise question we want to keep first), so `--randomize-items` is a no-op on this platform — emits a warning at export time and a comment in the generated `.gs`. Documented loudly in `docs/surveys.md`.
- **SurveyMonkey** uses the same `[item:<tag>]` title-encoding as Google Forms. Randomization fully honored via `presentation_options.randomize_questions`. EU customers can override the API base URL via `--surveymonkey-base-url`.

### Docs

- `docs/surveys.md` (new) — end-to-end workflow per platform.
- `docs/authoring_benchmarks.md` — cross-reference to surveys.md in the analyst-recruitment paragraph.
- `CLAUDE.md` — new locked-default entry on the survey surface.
- `mkdocs.yml` — `Surveys: surveys.md` added to the nav.

### Schemas

- `benchmark.schema.json` gains the additive `AnalystModel.expertise_description` property. `framework_version` default bumped to `0.9.0`.

### What's out of scope for v0.9.0

- Qualtrics REST API export (alternative to the `.qsf` file). The file-only path is the v0.9.0 contract; API path is a v0.9.x follow-up.
- Google Forms REST API export (requires OAuth2 client setup; way too heavy). The Apps Script path side-steps the auth complexity by running in the user's own Google account.
- Additional platforms (Tally, Limesurvey, Microsoft Forms). The `--platform` enum is in place; adding a fourth platform is purely additive.
- Structured expertise capture (specialty / years / board-certified as separate fields). Free-text is the v0.9.0 shape; structured can land as `--expertise-form structured` later.
- Custom question templates via `--template-file`.
- Attention-check / red-herring items injected at survey time.
- Re-rendering against a changed benchmark (schema diff + survey-version annotations). The v0.9.0 contract is "generate once, recruit once, import once".

## [0.8.0] — 2026-06-03

**Reliability discipline extended into the by-tag / by-rsr-target
decomposition cells** (closes
[#84](https://github.com/bradleypallen/infereval/issues/84)). The
framework's per-cell agreement statistics now render their substantive-n
and per-class verdict counts; cells with substantive-n below
`MIN_K_FOR_SUBSAMPLING_CI = 10` are marked under-powered and surface as
section 4b negative findings in the construct-validity report. Headline
κ_C / κ_F / κ_F\* rendering is unchanged.

### Why the change

The reliability machinery in v0.6.0–v0.7.0 (Politis–Romano subsampling
CIs gated at K ≥ 10, the within-run thin-margin structural check, the
R22 test-retest verdict cap) all stopped at the headline. Decomposition
cells — produced by `infereval metrics --by-tag` and `--by-rsr-target` —
were the one place the reliability story had a seam, because
decomposition is exactly where item count collapses. On an n = 1 or
n = 2 subset, κ = ±1.0 is the value the formula is *forced* to take
when each rater commits to a single class, not a finding. The
methodology surface promoted decomposition hardest (the docs called it
"the single most useful tool the framework gives you for diagnosis"),
so it was the value a reader was most likely to over-read. The live
Haiku M9 worked example in `docs/interpreting_metrics.md` literally
showed `By tag: irrelevant-addition  κ_F = -1.0000  (n=2; perfect
anti-correlation!)` and the surrounding prose read it as "perfectly
disagrees on every item" — exactly the inferential over-reach the
existing reliability gates exist to prevent.

This is structurally the same pathology #82 fixed one level up: a
number computed over a degenerate subset reading as a strong result.
Same fix shape: don't let a number computed over a degenerate subset
carry weight it hasn't earned. The κ value is still rendered (its
*direction* can be a legitimate diagnostic lead); only the
Landis–Koch-style interpretive label is gated.

### Added

- **`CellSummary` frozen dataclass + `cell_summary()` helper** in
  `infereval.metrics`. Aggregates the substantive-n, per-class M and
  reference verdict counts, and the κ_C / κ_F on a cell;
  `is_under_powered` flag reuses `MIN_K_FOR_SUBSAMPLING_CI` as the
  threshold. Public via `MetricsReport.cell_summary()` too.
- **`infereval metrics --by-tag` / `--by-rsr-target` per-cell
  rendering** in all three formats (text, markdown, json):
  - `n (substantive)` line / row / key — the n κ is actually computed
    over (post-substantive-index, not the pre-filter cell count).
  - `M verdicts: good X / bad Y / abstain Z` and
    `reference verdicts: …` lines / rows / keys, making the marginal
    distribution that drives small-subset κ legible at a glance.
  - `[under-powered: n < 10]` annotation appended to the κ_C and κ_F
    lines when the cell's substantive-n falls below
    `MIN_K_FOR_SUBSAMPLING_CI`. The κ value still renders; only the
    Landis–Koch label discipline is gated.
  - Under-powered cells log at INFO so the run is auditable.
- **`infereval report --by-tag` / `--by-rsr-target`** computes the
  per-cell summaries and threads them into `render_markdown`'s new
  `decomposition_cells` parameter. Under-powered cells surface as a
  new "Decomposition under-powered (R12)" group in section 4b of the
  construct-validity report. The verdict cap follows automatically via
  the existing `--suppress-negatives` asymmetry and the section-4b
  weight on the summary verdict.
- **`NegativeFinding.source` Literal** extended with
  `"decomposition_under_powered"`.
- **`collect_negative_findings()`** gains a `decomposition_cells`
  parameter; pre-v0.8.0 callers (no argument) see no change.
- **`render_markdown()`** gains a `decomposition_cells` parameter.

### Docs

- `docs/interpreting_metrics.md` — the live Haiku M9 worked example is
  rewritten to show the new n + class-count rendering and the
  `[under-powered: n < 10]` annotation. The prose reframes the
  diagnostic chain from "perfectly disagrees" (an over-read of κ at
  n = 2) to "direction is a diagnostic lead; magnitude is under-powered
  — confirm via the paraphrase axis." The "When the numbers are
  surprising" diagnostic checklist gains a step: *check the cell's n
  and class counts before treating a decomposed κ as a finding*.
- `docs/construct_validity.md` — R12 entry gets a sub-paragraph
  describing the new under-powered guard and pointing at the worked
  example.
- `CLAUDE.md` — new locked-default entry on decomposition rendering.

### Schemas

- `framework_version.default` bumped to `0.8.0` in
  `evaluation.schema.json`. No content-schema changes; no benchmark /
  evaluation / claims / retest persisted-artifact shape change.

### What's out of scope

- A claims-file field declaring which cells are mastery-relevant. The
  cell-agnostic section-4b integration is the simpler single-PR fix;
  a per-cell mastery-relevance declaration can land additively in
  v0.8.x or v0.9.x if usage shows it's needed.
- A scope-gated cap on under-powered cells (the existing section-4b
  weight on the verdict is sufficient for v0.8.0).
- Bootstrap CIs on decomposed κ values. The threshold-based annotation
  reuses the existing `MIN_K_FOR_SUBSAMPLING_CI` machinery rather than
  introducing a second uncertainty-quantification surface.
- Renaming `MIN_K_FOR_SUBSAMPLING_CI` — the constant is now used in two
  places, but the existing name still names the more fundamental thing
  (subsampling validity requires it).

## [0.7.0] — 2026-05-28

**Behaviour change: `inter_analyst_fleiss` returns the all-analyst κ_F\*
on panelled benchmarks** (closes [#82](https://github.com/bradleypallen/infereval/issues/82)).
This is a backward-incompatible change to the κ_F\* number reported by
the construct-validity report's section 2, `infereval describe`, and
`infereval metrics` on benchmarks that declare `analysts[*].panel` +
`primary_panel`. Verdict labels are unaffected — the verdict gate
consumes κ_F\* only for display, with no numerical threshold.

### Why the change

Pre-v0.7.0, `inter_analyst_fleiss(bench)` silently restricted to the
primary panel on panelled benchmarks. When the primary panel happened
to be internally unanimous, the function returned +1.0 even if the
second panel disagreed on several items — actively misleading for any
caller reading the value as the Remark 4 inter-analyst baseline. The
narrowing was documented in the docstring but invisible at the call
site and at the report's section 2 where the number is rendered as the
methodologically load-bearing baseline.

The methodological reading underwriting the v0.7.0 default: panels are
an *additive* convergent-validity device, not a way to restrict the
baseline. The Remark 4 baseline is the inter-analyst agreement across
the analyst pool whose verdicts the benchmark records. Recruiting a
second panel and writing those analysts' labels into `analyst_verdicts`
makes them part of that pool; excluding them silently to inflate the
headline number is the failure mode #82 surfaced.

### Migration

Most callers see no change — on non-panelled benchmarks the function
already computed Fleiss over all analysts. Callers who explicitly want
the pre-v0.7.0 narrowed value have three paths:

- `inter_analyst_fleiss_per_panel(bench)[bench.resolved_primary_panel()]`
  — public since v0.3.3, returns the primary-panel κ_F\* exactly.
- `inter_analyst_fleiss(bench, analyst_indices=bench.analyst_indices_in_panel(bench.resolved_primary_panel()))`
  — new in v0.7.0, threads explicit analyst indices through.
- Read the primary-panel sub-bullet under the headline in the
  construct-validity report's section 2 (rendered automatically when
  the benchmark has panels declared).

### Added

- **`inter_analyst_fleiss` gains an `analyst_indices: Sequence[int] | None
  = None` keyword.** When `None`, the default, Fleiss is computed over
  all analyst columns. When supplied, restricted to those columns.
  Lets callers compute κ_F\* over any subset (primary panel, reviewer
  panel, an arbitrary slice).
- **Construct-validity report section 2 dual rendering on panelled
  benchmarks.** The headline reads "Inter-analyst κ_F\* (all
  analysts): …"; an indented sub-bullet reads "Primary panel
  (`<name>`) κ_F\* = …" so the methodological distinction (the v0.6.x
  default vs. the v0.7.0 default) is visible at the surface where it
  was previously hidden.

### Changed

- `infereval metrics` text format label: `κ_F*(β) (inter-analyst):` →
  `κ_F*(β) (inter-analyst, all):`.
- `infereval metrics` markdown format label: `κ_F*(β)` →
  `κ_F*(β) (all analysts)`.
- `infereval describe` top-line label: `κ_F*(β) (inter-analyst
  baseline):` → `κ_F*(β) (all analysts):`. The existing per-panel
  decomposition block earlier in the describe output is unchanged.
- `docs/construct_validity.md`, `docs/interpreting_metrics.md`,
  `docs/glossary.md`, `docs/authoring_benchmarks.md`, `CLAUDE.md` —
  all updated to describe the new default and the migration path; the
  v0.7.0 change is called out with explicit `What changed in v0.7.0`
  / `Locked-defaults update` framing in the construct-validity and
  interpreting-metrics docs.

### Note

No schema-content change; `framework_version` default in
`evaluation.schema.json` bumped to `0.7.0`. `src/infereval/metrics.py`
loses the v0.3.3 panel-narrowing branch (lines 697–703 in v0.6.3) and
gains the `analyst_indices` keyword on the same function. The
Evaluation path was already all-analyst and is unchanged.

## [0.6.3] — 2026-05-28

Docs-only patch. README cleanup, no behavior, schema, or API change.

### Changed

- **`README.md` — deduplicate documentation-site references (PR #80).**
  The README pointed to the docs site three separate times — the Docs
  status badge (intentional, status indicator), a `📖 **Documentation**:
  <URL>` stub line directly under the badges that the badge above
  already silently linked to, and a "Full docs site: **<URL>**." lead
  sentence opening the Documentation section. Removed the emoji stub
  line; folded the Documentation section's lead sentence into the
  opening of the "What's there:" paragraph so the URL appears once in
  flowing prose rather than as a separate stub. After: status badge
  (silent link) + one in-prose URL mention + the per-page links that
  each embed the site root. Down from three explicit URL mentions to
  one.

### Note

No code, API, or schema-content change. `framework_version` default in
`evaluation.schema.json` bumped to `0.6.3`. `src/infereval/` is
byte-identical to v0.6.1 / v0.6.2 apart from the `__version__` string.

## [0.6.2] — 2026-05-28

Docs-only patch. Two reviewer-prompted hygiene passes on
`docs/construct_validity.md` and `docs/authoring_benchmarks.md`. No
behavior, schema, or API change.

### Changed

- **`docs/construct_validity.md` — "cheap to do / expensive to skip"
  rephrasing (PR #77).** The slogan was three different things in three
  places (`cheap enough to do / expensive enough to skip` twice;
  `cheap-to-do-it-right / expensive-to-cut-corners` once) and was
  mis-stating the framework's actual posture in two ways. (1) The
  "expensive" side is reputational, not mechanical: the framework
  cannot stop a determined analyst from publishing whatever they want;
  what it does is make the skip into a documented decision via report-
  header banners, verdict downgrades, and the visibility of the
  `--suppress-negatives` flag. (2) The precise structural position is
  about *declaration*, not skipping — skipping is permitted, but
  undeclared skipping is what the verdict gate catches. All three
  occurrences rewritten to be precise about this; the "cut-corners"
  variant dropped entirely (it leaked a different normative weight
  than "skip" — cutting corners implies doing it wrong, skipping is
  just a choice). Pre-existing "cheap/expensive" uses for the
  `--suppress-negatives` mechanic itself (lines 138 and 373) left
  unchanged: those describe an actual mechanism with mechanical cost,
  not the slogan.
- **`docs/construct_validity.md`, `docs/authoring_benchmarks.md`,
  `docs/interpreting_metrics.md` — domain-neutral analyst language
  (PR #78).** Several places in the user-facing docs had slipped into
  pulmonology-specific language as if the framework's default analyst
  role were a physician. The bundled pulmonology demo is fine; the
  methodology guidance should not present a specific domain in how it
  talks about analysts. Phase 4.1 "Recruit a second pulmonologist (or
  domain expert)" → "Recruit a second domain expert (independent of
  the first analyst's training where possible)". Authoring-guide JSON
  snippets generalised from `physician-a/b/c` / `Dr. A (internal
  medicine)` / `Dr. B (infectious disease)` to `analyst-a/b/c` /
  `Analyst A` / `Analyst B`; "current clinical practice" → "competent
  practice in domain D"; the credential-documentation prose example
  rewritten from a single hardcoded pulmonologist case to a pattern
  statement illustrated by three paired domain examples (clinical-
  reasoning / contract-law / software-engineering) with the bundled
  pulmonology demo named as the clinical-reasoning illustration.
  `construction_metadata` example `authored_by` and `source` values
  generalised. `infereval metrics --reference analyst:physician-a` →
  `analyst:analyst-a`. The bundled pulmonology tutorial notebook
  (`docs/tutorials/04_pulmonology_visualization.ipynb`) is unchanged
  — appropriately scoped to that demo.

### Note

No code, API, or schema-content change. `framework_version` default in
`evaluation.schema.json` bumped to `0.6.2`. `src/infereval/` is
byte-identical to v0.6.1 apart from the `__version__` string.

## [0.6.1] — 2026-05-28

**R22 second leg: declared identity criterion.** Patch release responding
to Ulf Hlobil's individuation point on the v0.6.0 reliability
machinery. The fix strengthens v0.6.0's thesis rather than patching it:
reliability is by definition the agreement of distinct measurements of
*the same individual*, so a test-retest κ is uninterpretable without a
declared identity criterion for what "the same system" means across
the two runs. v0.6.0 built the reliability machinery correctly but
described the config-parity check on `infereval retest` as carrying
more conceptual weight than it can bear — that check verifies the two
runs use the same *measurement setup*, not that they measure the
*same system*. v0.6.1 supplies the prerequisite that makes v0.6.0's
reliability numbers interpretable: an analyst-declared
`IdentityCriterion` recorded in the claims file, partially
mechanically substantiated by the parity check, and required at scope
≥ `domain_D_as_sampled` for R22 satisfaction.

The doubly-relative framing — carving (R19) + individuation (R22
second leg) — is the methodologically complete posture: every
load-bearing standard the methodology relativises to is now a
stipulated commitment relative to which claims are scoped, never an
inferred one. Hlobil's point makes visible that v0.6.0 had the
relativity move for carving but inferred the standard for
individuation; v0.6.1 closes that asymmetry. Thanks to Ulf Hlobil
(Concordia / co-author of *Reasons for Logic, Logic for Reasons*) for
the individuation point.

### Added

- **`infereval.report.IdentityCriterion`** — analyst-declared
  individuation criterion for reliability claims. Per-field booleans
  split into a *framework-substantiated* group (`same_benchmark_hash`,
  `same_endorsement_config`, `same_paraphrase_variant`) and an
  *analyst-substantiated* group (`same_provider_model_id`,
  `cross_update_identity_asserted`, `same_scaffolding`), plus
  `unverifiable_caveats` and `rationale` free-text. Same shape as the
  leakage-audit-gap handling for R8/R9: framework records the claim,
  applies the parts it can verify, flags the parts it cannot.
- **`infereval.report.ReliabilityClaim`** — wraps `IdentityCriterion`
  on `ConstructValidityClaims.reliability` (new optional sub-block
  peer to `mastery_sense` / `scope` / `constitution` / `carving`).
  Forward-extensible for future reliability-related commitments
  without re-shaping the top-level claims schema.
- **`ConstructValidityClaims.stub()`** extended with a `reliability`
  block — framework-substantiated booleans default True,
  analyst-substantiated booleans default False (forces the analyst to
  consciously assert each one), free-text fields carry FILL IN
  placeholders.
- **`RetestResult.identity_criterion`** — optional field carrying the
  declared criterion alongside the κ. `compute_retest` gains a
  keyword parameter; `retest_result_to_dict` serializes the criterion
  when present.
- **`infereval retest --claims path/to/claims.json`** — new CLI flag
  that loads the analyst's declared `IdentityCriterion` from the
  claims file and threads it into the retest result.
- **R22 second-leg verdict gate** in `compute_verdict` — at scope ≥
  `domain_D_as_sampled`, R22 satisfaction now requires
  `test_retest_run=True` AND a declared `IdentityCriterion` with
  non-empty rationale. Without the criterion the verdict caps at
  `partially_defensible`. Mirrors the R19 carving-acknowledgement
  gate exactly.
- **Report renderer surfacing**: section 2 test-retest κ line carries
  "under the declared identity criterion (`<one-line summary>`)" when
  the retest artifact carries it; section 3 gains a "**Reliability —
  identity criterion (R22, doubly-relative)**" sub-block rendering
  the full criterion verbatim when claims include the reliability
  block.

### Changed

- **`infereval.retest._check_compatibility` docstring + all
  `RetestConfigMismatchError` messages** relabeled (text-only — code
  path unchanged): the check verifies the *setup-conformance
  portion* of an individuation criterion, not the criterion itself.
  Sameness-of-individual is a separate commitment the analyst
  declares via `ConstructValidityClaims.reliability.identity_criterion`.
- **`RetestResult.stability_verdict`** gains an "under the declared
  identity criterion" clause when the criterion is present.
- **`docs/construct_validity.md`** reframed: Context paragraph names
  the doubly-relative framing; R22 entry gains a second-leg
  sub-block; new Phase 0.6 "Declare the individuation criterion";
  Phase 2 preamble clarifies that running twice is necessary but
  not sufficient for R22; Phase 2.3 example shows `--claims`
  threading; Phase 5 gains an R22-second-leg bullet plus the
  (a) temporal-occasion vs. (b) identity-criterion cleanup the
  v0.6.0 doc had conflated; "What only a research program can do"
  section reframed accordingly; coverage table R22 row updated.
- **`docs/glossary.md`** gains `IdentityCriterion` and
  `ReliabilityClaim` entries; the retest-stability-verdict entry
  extended to mention the criterion clause.

### Compatibility

All additions are optional fields with sane defaults. Pre-v0.6.1
claims files (without the `reliability` block) continue to validate;
the verdict gate only fires when `test_retest_run=True` AND the
scope is ≥ `domain_D_as_sampled`. Pre-v0.6.1 retest result JSONs
(without `identity_criterion`) continue to round-trip. The
evaluation-JSON schema is untouched. `schema_version` stays `"1.0"`.

`framework_version` default in `evaluation.schema.json` bumped to
`0.6.1`.

## [0.6.0] — 2026-05-23

**Reliability infrastructure (R22).** Major release adding within-run
verdict-dispersion surfacing, Politis-Romano (1994) subsampling
confidence intervals on κ, a within-run thin-margin structural check,
the across-run `infereval retest` command with the `RetestResult`
artifact, and the verdict-gate that requires test-retest reliability
at scope ≥ `domain_D_as_sampled`. Substantive new behaviour in
`src/infereval/` (unlike the 0.5.7–0.5.10 docs-only sequence). The
framework version bump to 0.6.0 reflects that the headline metrics
shift meaningfully: a κ_C without uncertainty quantification and
without a test-retest check is now treated as a point estimate from
an unknown distribution, not as the measurement.

The methodology framing — articulated in the consolidated
[`docs/construct_validity.md`](https://www.bradleypallen.org/infereval/construct_validity/):
an evaluation that doesn't replicate is not evidence of anything,
mastery or otherwise. R22 is not an addition to the requirements
list — it is a precondition the existing list silently presupposed
and shouldn't have.

### Added

- **`infereval.metrics.VerdictDistribution`** — per-item dispersion
  view (good/bad/abstain counts, normalised Shannon entropy,
  plurality margin, tie-broken flag) derived from the existing
  `EvaluationItem.majority_vote` counts. No evaluation-schema change.
- **`infereval.metrics.AggregateDispersion`** — corpus-level summary
  (mean entropy, mean margin, n_thin_margin, n_tie_broken).
- **`infereval.metrics.MetricsReport.verdict_distributions`** and
  `aggregate_dispersion_summary` properties; `to_dict` includes the
  new blocks by default per the locked `report_verdict_distribution =
  true`. Pass `include_verdict_distributions=False` for the pre-0.6 shape.
- **Confidence-weighted κ variants** — `cohens_kappa` /
  `fleiss_kappa` / `MetricsReport.cohens_kappa` /
  `MetricsReport.fleiss_kappa_weighted` accept an optional
  `weights: WeightFn` parameter. `margin_weight` is the standard
  weighting (per-item plurality margin). Off by default; the
  unweighted κ remains the locked headline number.
- **`infereval.metrics.subsampling_kappa_ci`** — Politis-Romano (1994)
  item-level subsampling CIs on κ. Default subsample size
  `round(K^0.7)`; raises `SubsamplingNotApplicableError` for
  benchmark size K < 10. Convenience wrappers
  `MetricsReport.cohens_kappa_with_ci` and `fleiss_kappa_with_ci`.
  Chosen over the Efron nonparametric bootstrap because κ is a
  non-smooth functional of count data (discrete jumps at the
  majority-vote threshold) where the standard bootstrap can fail;
  Politis-Romano subsampling is valid under minimal smoothness
  assumptions.
- **`infereval.structure.thin_margin_agreement_check`** — flags items
  where the model agrees with analyst consensus but the agreement is
  supported by a thin majority over the sampled verdicts.
  `DEFAULT_THIN_MARGIN_THRESHOLD = 0.4` (catches 3/5; lets 4/5
  through). Wired into `run_all_checks` so `infereval structure`
  picks it up by default.
- **`infereval retest <eta_a.json> <eta_b.json>` (new CLI subcommand)**
  + **`infereval.retest` module** — across-run test-retest comparator.
  `compute_retest(eta_a, eta_b, benchmark=None) -> RetestResult`;
  validates `benchmark_hash` / `endorsement_config` /
  `paraphrase_variant` parity (raises `RetestConfigMismatchError`
  otherwise — retest variability cannot be conflated with
  parameter-change effects); pairs items by id; computes Cohen's κ
  over the two collapsed-verdict columns; records per-item flips
  with optional `factor_levels` annotations; records per-item
  entropy/margin deltas. `RetestResult.stability_verdict` ladder:
  κ ≥ 0.8 stable; ≥ 0.6 moderately stable; < 0.6 substantively
  unstable (explicitly tells the reader the headline κ_C cannot be
  interpreted as signal under that reliability level).
- **`CompetingExplanationChecks.test_retest_run: bool = False`** —
  new claims-file field. Required at scope ≥ `domain_D_as_sampled`
  per the locked `test_retest_required_at_scope =
  "domain_D_as_sampled"`. The `report --init-claims` stub includes
  it default-False, like every other competing-explanation check.
- **R22 verdict-gate audit cap** in `compute_verdict`: if
  `test_retest_run` is asserted but the supplied `RetestResult` is
  substantively unstable or has undefined κ, the verdict caps at
  `partially_defensible`. Same shape as the v0.5.3 structural-anomaly
  and m<2 caps.
- **Report renderer integration**: section 2 (Summary metrics) gets
  a Test-retest κ (R22) row when a retest artifact is supplied;
  section 4 (Evidence) gets a Test-retest reliability (R22) row
  (NOT SUPPLIED otherwise); section 4b (Negative findings) gets a
  new "Test-retest anomalies (R22)" subsection that lists the
  corpus-level stability_verdict and the per-item flips (capped at
  50 with an overflow line pointing at the artifact JSON).
- **CLI flags**:
  - `infereval metrics --ci [--ci-iterations N] [--ci-subsample-size B] [--ci-seed N]`
    — opt into the subsampling CI on κ_C and κ_F.
  - `infereval metrics --weight-by-margin` — opt into the
    margin-weighted κ variants.
  - `infereval structure --thin-margin-threshold F` — override the
    thin-margin cutoff.
  - `infereval report --retest <retest-result.json>` — supply the
    retest artifact to the report renderer.
- **`docs/construct_validity.md`** — consolidated source of truth for
  the construct-validity methodology, replacing the prior
  `construct_validity_workflow.md` + `closing_the_construct_validity_gap.md`
  pair. Present-tense, version-marker-free. R22 integrated as a
  Tier 1 requirement; both bundled demos (stop-sign cross-family +
  pulmonology) used as worked examples.

### Changed

- **`experiments/results/cross-family/`** renamed to
  **`experiments/results/stop_sign/`** (peer-symmetric with
  `experiments/results/pulmonology/` — domain-named).
- **`experiments/results/cross_family_2026-05-18.md`** renamed to
  **`experiments/results/stop_sign_2026-05-18.md`** (same pattern).
- **`NegativeFinding.source` Literal** extended with `"retest"`.
- **`_REQUIRED_CHECKS_BY_SCOPE`** — `test_retest_run` added at
  `domain_D_as_sampled` and `general_capacity` scopes. Not required
  at `items_in_benchmark`; informational only at that scope.
- **`MetricsReport.to_dict`** gains `include_verdict_distributions`
  and `thin_margin_threshold` keyword arguments. Defaults preserve
  the post-0.6 surfacing; setting `include_verdict_distributions=False`
  reproduces the pre-0.6 JSON shape exactly.
- **`docs/` consolidation** removed
  `closing_the_construct_validity_gap.md` and
  `construct_validity_workflow.md` (their content is integrated into
  `docs/construct_validity.md`). Cross-references in
  `docs/concepts.md`, `docs/authoring_benchmarks.md`,
  `docs/interpreting_metrics.md`, `docs/glossary.md`, and the
  per-page index in `docs/README.md` updated to point at the
  consolidated doc. `mkdocs.yml` nav updated.

### Note

`framework_version` default in `evaluation.schema.json` bumped to
`0.6.0`. All additions to `evaluation.schema.json`,
`benchmark.schema.json`, and the in-memory claims schema are
optional fields with sane defaults; pre-0.6 artifacts continue to
validate. The retest result is a new artifact shape pinned by tests
and by `retest_result_to_dict`; the dataclasses live in
`infereval.retest` (not Pydantic models) so the static-schema
emission pipeline at `schemas/__init__.py` is unaffected.

## [0.5.10] — 2026-05-23

**First publication to real PyPI.** Earlier 0.5.x releases were tagged
and rehearsed against TestPyPI; this is the version that lands on
<https://pypi.org/project/infereval/>. Source-wise the package is
byte-identical to v0.5.9 — the substantive change is publication
infrastructure.

### Added

- **`.github/workflows/publish.yml`** — build + publish workflow using
  [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
  (OIDC, no API tokens in GitHub secrets). Two triggers:
  - `release: published` → automatic publish to real PyPI on
    `gh release create vX.Y.Z`. Gated by a required-reviewer
    deployment-environment rule (`pypi`), so every PyPI push pauses for
    one-click human approval in the Actions UI before twine uploads.
  - `workflow_dispatch` with `target: testpypi|pypi` → manual
    rehearsals against TestPyPI (or a manual real-PyPI push if the
    auto-trigger needs to be bypassed). TestPyPI step sets
    `skip-existing: true` so re-dispatches against an already-published
    version don't error out.
- **GitHub deployment environments** `pypi` (with required reviewer)
  and `testpypi` (open). Registered as trusted publishers on both
  indices.

### Changed

- **`CLAUDE.md`** — CI section now documents three workflows
  (`ci.yml`, `docs.yml`, `publish.yml`). Release-flow section describes
  both the automated `gh release create` path and the manual
  `twine upload` fallback, plus the one-time trusted-publisher
  registration steps.

### Note

`framework_version` default in `evaluation.schema.json` bumped to
`0.5.10`. `src/infereval/` source is unchanged from v0.5.7 onward
apart from the `__version__` string — the 0.5.7 → 0.5.10 sequence was
all release-hygiene and publication-infrastructure work, preserved as
separate releases so the CHANGELOG records the iteration that produced
a clean inaugural PyPI publication.

## [0.5.9] — 2026-05-23

Docs-only patch. Converts the four remaining relative links in the
README to absolute GitHub URLs so they resolve on the PyPI project
page. Caught while inspecting the v0.5.8 TestPyPI publication: PyPI
does not rewrite relative `LICENSE` / `CHANGELOG.md` / `experiments/...`
paths the way GitHub does, so the badge and inline links rendered as
404s. v0.5.8 had already converted the `docs/*.md` bullet list to
absolute URLs; this release closes the loop on the rest.

### Changed

- **`README.md`** — four link href fixes, all to
  `https://github.com/bradleypallen/infereval/blob/main/...`:
  - **License badge** href (was the broken one the user spotted on the
    v0.5.8 TestPyPI page).
  - **`[CHANGELOG](CHANGELOG.md)`** in the Status section.
  - **`[experiments/results/cross_family_2026-05-18.md]`** in the
    Findings section.
  - **`[LICENSE](LICENSE)`** in the bottom License section.
- **`CLAUDE.md`** — refreshed the release-flow note: `~/.pypirc`
  actually has both `[testpypi]` and `[pypi]` index-servers wired to
  `__token__` (twine picks them up non-interactively); added the
  absolute-URLs-only requirement to the release-hygiene check, with
  the 0.5.7 → 0.5.8 → 0.5.9 sequence as the worked example for why it
  matters.

### Note

No code, API, or schema-content change. `framework_version` default
in `evaluation.schema.json` bumped to `0.5.9`. `src/infereval/` is
byte-identical to v0.5.7/v0.5.8 apart from the `__version__` string.

## [0.5.8] — 2026-05-23

Docs-only patch. Rolls the post-`v0.5.7` documentation work into a
shippable release so the PyPI project page renders correctly: the
prior README pointed at relative `docs/*.md` paths that resolve on
GitHub but break on PyPI. This release replaces those with absolute
URLs to the live MkDocs Material docs site, and bundles the docs-site
infrastructure that the new links point at.

### Changed

- **`README.md`** — added a "Docs" CI badge and a prominent
  documentation-site pointer at the top. Replaced the bullet list of
  relative `docs/concepts.md`-style links (which 404 on PyPI) with a
  paragraph of absolute `https://www.bradleypallen.org/infereval/…`
  links. This is what fixes the PyPI project-page rendering.

### Added

- **MkDocs Material docs site** (`mkdocs.yml`, `.github/workflows/docs.yml`)
  — live at <https://www.bradleypallen.org/infereval/>, deployed from
  `main` on push.
- **New docs pages** (`docs/api.md`, `docs/architecture.md`,
  `docs/glossary.md`, `docs/schemas.md`) — auto-rendered API reference
  (mkdocstrings), Mermaid dataflow diagram, paper-symbol glossary, and
  schema field reference. Existing pages refreshed for the site.

### Note

No code, API, or schema-content change. `framework_version` default in
`evaluation.schema.json` bumped to `0.5.8`. The `src/infereval/`
package is byte-identical to v0.5.7 apart from the `__version__`
string.

## [0.5.7] — 2026-05-22

Catches three pieces of PyPI-surfaced metadata that still carried the
pre-Remark-8 "measure mastery" framing and the pre-`PR #60` Alpha
maturity descriptor. Cut as a follow-up to 0.5.6 because these are
baked into the wheel METADATA (and so into the PyPI project page)
rather than just the rendered README.

### Changed

- **`pyproject.toml` description (PyPI Summary)** — *"…derive
  implication frames and measure mastery against analyst-labeled
  benchmarks"* → *"…measure model–analyst agreement on labeled
  inference benchmarks. Evidence bearing on inferential-mastery
  attribution."* This line renders directly under the project name
  on PyPI.
- **`pyproject.toml` trove classifier** — `"Development Status ::
  3 - Alpha"` → `"4 - Beta"`, matching the README Status line
  corrected in 0.5.6.
- **`src/infereval/__init__.py` module docstring** — same
  measurement-vs-evidence framing fix, with an explicit pointer to
  Remark 8 of the paper. Shown by `help(infereval)`.

### Note

No behavior, API, or schema-content change. `framework_version`
default in `evaluation.schema.json` bumped to `0.5.7`.

## [0.5.6] — 2026-05-22

> **Superseded by 0.5.7 before publication.** The `v0.5.6` tag was created and
> wheels were built locally, but a follow-up pass caught three
> wheel-METADATA strings (the PyPI Summary, the `Development Status` trove
> classifier, and the module docstring) that still carried the pre-Remark-8
> "measure mastery" framing. Rather than force-move the just-cut tag, those
> fixes were rolled into 0.5.7 and that's the version that shipped. The
> `v0.5.6` tag has been retired; the entry is preserved here as the historical
> record of what 0.5.6 was going to be, since 0.5.7's notes reference it.

Release-hygiene patch. Bundles the README, CI, and documentation changes
that landed after the `v0.5.5` tag so the first PyPI publication
launches with the current state of the repository, not a snapshot that
predates the post-tag fixups.

### Changed

- **README Status line** — replaced the never-bumped `"Alpha (0.1.0)"`
  placeholder (verbatim from the 0.1.0 commit) with `"Beta (0.x,
  pre-1.0)"`, de-pinned so it can't drift again; points readers to the
  CHANGELOG for the current release.
- **README badges** — added CI status, GitHub release version, PyPI
  version, Python 3.10+, and MIT license badges to the header.

### Added

- **`.github/workflows/ci.yml`** — first GitHub Actions workflow. Runs
  `ruff check src tests`, `mypy src/infereval`, and `pytest -q` on
  every push to `main` and every PR (Python 3.12). Test/lint only —
  no build, no publish; PyPI upload remains a manual `twine` step.
- **Documentation of the leakage-audit gap** — `closing_the_construct_validity_gap.md`
  R8 and R9 each carry a "Known gap (deferred)" subnote describing
  the missing cross-check between the `held_out_items_used` /
  `training_data_separation_verified` boolean claims and the per-item
  `construction_metadata` that should substantiate them. The Phase 5
  checklist in `construct_validity_workflow.md` carries a matching
  caveat: until the v0.5.3-style audit cap lands for these claims,
  "your honesty in setting these booleans is the audit."

### Fixed

- **Latent `ruff N817` in the AR2 rationale test** (`Verdict` aliased
  to `V`) — switched to the already-imported `Verdict` so the new CI
  workflow starts green on day one.

### Note

No behavior, API, or schema-content change. `framework_version`
default in `evaluation.schema.json` bumped to `0.5.6`.

## [0.5.5] — 2026-05-21

Documentation-conformance release. Brings all cross-references into line
with the **revised** stop-sign note (21 May 2026), which changed its
title and renumbered both Definitions and Remarks. No behavior, API, or
schema changes — the formal content (Definitions 1–10, the RSR /
Containment machinery, and the kappa math) was already implemented
exactly as specified; only the citations and framing needed updating.

### Changed

- **Paper title** updated throughout (README prose + BibTeX, CLAUDE.md,
  the references list in `closing_the_construct_validity_gap.md`, and the
  citation string in `examples/pulmonary_edema/benchmark.json`):
  *"…An Implication-Space Methodology for the Empirical Evaluation of LLM
  Inferential Mastery"* → *"…An Implication-Space Instrument for Probing
  LLM Endorsement of Material Inferential Rules"*.
- **Definition citations** corrected for the revised numbering
  (6 Coverage, **7 Substantive index**, 8 Consensus, 9 Cohen, 10 Fleiss):
  `consensus_verdict` now cites Definition 8 (was 7); the Fleiss `S_F`
  filtering cites Definition 10 (was 9), with the substantive-index
  restriction `S` attributed to Definition 7.
- **Remark citations** corrected for the revised numbering: the κ_F\*
  baseline / `m<2` / non-unanimous conditions now cite Remark 4 (was 5);
  the paraphrase axis cites Remark 9 (was 8/6); carving-indexed
  in-principle claims cite Remark 10 (was 9). RSR-targeted citations
  (Remark 5) are unchanged — still correct.
- **README framing** aligned with the paper's Remark 8: the tagline now
  describes the framework as measuring the model's *agreement* with the
  benchmark, with that agreement framed as **evidence bearing on** an
  inferential-mastery attribution rather than a measurement of mastery.

### Note

The revised paper instantiates single-bearer succedents
(`⟨Γ, {ψ}⟩`); `infereval` continues to permit multi-element
`conclusions` lists (the multisuccedent generalization the paper
defers). This is a pre-existing, intentional superset, unchanged here.

## [0.5.4] — 2026-05-20

Analyst-side rationale support. New optional, additive schema field
that captures the natural-language reason each analyst gave for their
verdict, with positional alignment to ``analyst_verdicts``. Model-side
rationale elicitation is deferred to a later stage.

### Added

- **`BenchmarkItem.analyst_rationales: list[str] | None`** —
  per-analyst, per-item rationale text. Positionally aligned to
  ``analyst_verdicts``: index ``j`` is analyst ``j``'s rationale.
  ``None`` (the default and back-compat case) means "this benchmark
  carries no rationale discipline." A present list with an empty-string
  entry means "this analyst gave a verdict but recorded no reason on
  this item" — semantically distinct from ``None``. When the field is
  present, the length must equal ``len(benchmark.analysts)`` (enforced
  in ``Benchmark._check_consistency``). The framework validates
  structure and length only; rationale content is the analyst's
  responsibility (consistent with the framework's posture on
  ``construction_metadata`` and verdicts themselves).
- **`EvaluationItem.analyst_rationales: list[str] | None`** — propagated
  from the source benchmark item at evaluation-build time. Falls under
  the existing ``Evaluation.benchmark_hash`` integrity mechanism: a
  rationale cannot be silently altered between evaluation and report
  without changing the hash.
- **`infereval describe --items` rendering** — when rationales are
  present, the per-item block now lists each analyst's rationale text;
  an empty-string entry renders as ``(no reason recorded)`` so it's
  visually distinct from the absent-field case. Items where analysts
  disagree in verdict *and* carry rationales are flagged with
  ``⚠ disagreement+rationales`` on the header line — those are the
  noise-vs-signal triage targets for downstream disagreement diagnosis.
- **JSON schemas** — both ``benchmark.schema.json`` and
  ``evaluation.schema.json`` gain the optional ``analyst_rationales``
  array (``items: string``), with a description that states the
  positional-alignment contract and the ``null``-vs-empty-string
  distinction so external tooling and hand-authors get it right.
- 23 new tests across ``test_benchmark_io.py::TestAnalystRationales``
  and a new ``test_analyst_rationales_propagation.py`` covering all
  12 acceptance requirements (AR1–AR12): length mismatch rejection
  with the right error, backward compatibility against the existing
  stop-sign benchmark, the ``None``-vs-empty-string round-trip
  distinction, carry-through into the evaluation artifact, hash
  coverage, regression assertions that ``coverage`` / ``κ_C`` / ``κ_F``
  / ``κ_F*`` / structure-check outputs are byte-identical with and
  without rationales (proving the metric path is untouched), describe
  rendering, the divergence flag firing on disagreement+rationales,
  and the divergence flag staying silent on disagreement-only.

### Backwards compatibility

- **Additive only.** Every pre-0.5.4 benchmark and evaluation continues
  to validate unchanged. The new field defaults to ``None`` and is
  dropped from JSON output via ``exclude_none=True``, so existing
  fixtures and round-trip equality are preserved.
- **Metric and structural-check outputs are byte-identical** with and
  without rationales present (regression tested in
  ``TestMetricsRegressionAR2``).
- **Hash unchanged for rationale-free benchmarks.** ``canonical_benchmark_hash``
  uses ``exclude_none=True``, so a ``None``-valued ``analyst_rationales``
  field is omitted from the hash input — pre-0.5.4 benchmarks hash to
  the same value they did under 0.5.3.

### Out of scope

Model-side rationale elicitation (verification-prompt changes, per-sample
rationale logging, the prompt-sensitivity control for whether eliciting
reasons perturbs verdicts) is deferred. The disagreement-diagnosis
tooling that consumes analyst rationales (cohort-finding, noise-vs-signal
triage) is also deferred — this release delivers the data substrate it
will read, not the diagnosis itself.

## [0.5.3] — 2026-05-20

External-review release. An independent code review identified one
design-level issue in the construct-validity layer plus one real crash
bug; this release addresses both, plus a doc/data drift on Anthropic
model naming and a feature suggestion that lets factor-level negative
findings be labelled by valence.

### Fixed

- **Issue #1 (design, construct-validity)** — `compute_verdict` now
  consults the structure report and benchmark passed by
  `render_markdown`, not just the claims file. Two new audit caps:
  1. If `structural_check_run=True` *and* the supplied structure
     report contains any anomaly, the structural check is treated as
     failing (the check *ran* but didn't *pass*). The verdict is
     capped at `partially_defensible` with a rationale line naming the
     anomaly count.
  2. If the benchmark has `m < 2` analysts *and* the claim's scope is
     `items_in_benchmark`, the verdict is capped at
     `partially_defensible` and the panel size is surfaced in the
     one-liner (κ_F\* is undefined and there is no independent reference
     column; agreement with one analyst cannot inherit the
     convergent-validity guarantee a green badge implies).
  Backwards-compatible: callers that don't pass the new optional
  arguments get the v0.5.2 behaviour plus a "verdict computed
  unaudited" rationale line. The rendered report always passes them.
- **Issue #2 (crash bug)** — `infereval.structure.rsr_role_consistency_check`
  and `base_case_stability_check` no longer raise `KeyError` when the
  evaluation is missing an item that the benchmark carries an
  `rsr_target` for. Partial evaluations (the natural output of
  `--paraphrase-cycle` per-variant runs, tag-filtered re-runs) now
  match the rest of the package's contract: missing items are skipped
  with a logged warning, not raised. `run_all_checks` against a partial
  evaluation completes cleanly.
- **Issue #3 (docs)** — `docs/providers.md` now lists `claude-opus-4-7`
  as the current Opus id (with a dated example, `claude-opus-4-7-20260201`)
  matching the artifact fixtures in `experiments/results/cross-family/`,
  and explains the `4.7` / `4-7` filename-vs-id convention.

### Added

- **Issue #4 (feature)** — new optional `Benchmark.factor_kinds: dict[str, "substantive" | "experimentally_controlled"]`.
  When set, `collect_negative_findings` labels each null Wald-test
  finding's valence: substantive nulls **weaken** the mastery claim
  (the model failed to differentiate where it should), controlled
  nulls **strengthen** it (content-not-form behavior on a paraphrase
  axis is the wanted outcome). Factors omitted from the map keep the
  historical neutral summary. Schema-additive (R7 / R12).
- Six new tests for the partial-evaluation guard; six new tests for
  the verdict audit caps; five new tests for `factor_kinds`. Suite is
  now 612 unit tests.

### Note

This release is **conservative on existing data**. A previously-shipped
report whose claims were `structural_check_run=True` and benchmark was
m=1 will now render `⚠️ partially defensible` instead of `✅ defensible`
— the verdict the framework should have rendered all along. If you've
made public claims off the prior verdict, re-render with v0.5.3 and
acknowledge the change in your write-up.

## [0.5.2] — 2026-05-20

Tiny but consequential default-alignment release. The CLI's `--max-tokens`
flag and the Python `ProviderParams.max_tokens` field now agree.

### Fixed

- **CLI `--max-tokens` default raised from 32 to 1024**, aligning with the
  Python API default. The previous CLI default (`32`) was a holdover from
  a pre-reasoning-token era; for any reasoning-capable model
  (DeepSeek v4-flash, OpenAI o-family, Qwen-thinking variants, Anthropic
  Opus 4.7+ extended thinking) it silently produced budget-clipped
  abstains unless the user remembered to pass `--max-tokens` explicitly.
  The framework already correctly classified those abstains as
  `parse_status="budget_clipped"` (since v0.2.0), so the impact was on
  novice users running the CLI with only the required flags.
- **Docstring on `infereval.evaluation.evaluate`** corrected: the default
  `ProviderParams()` is `(temperature=1.0, max_tokens=1024)`, not
  `max_tokens=32` as the docstring previously claimed.
- **Documentation cleanup** following from the default alignment:
  `docs/providers.md` no longer carries the "CLI/API default mismatch"
  callouts; `docs/authoring_benchmarks.md`, the
  `paraphrase_axis_triangulation.py` docstring, and tutorial 03 now
  reference the current 1024 default rather than the historical 32
  footgun.

### Note

This is a behavior change for CLI invocations that omit `--max-tokens` —
the provider will be asked for up to 1024 tokens per sample instead of 32.
For typical one-word verdict prompts the difference is invisible (both
return after ~6 output tokens). For reasoning-capable models that consume
budget on silent internal reasoning, evaluations that previously
budget-clipped will now complete normally.

## [0.5.1] — 2026-05-20

**The construct-validity infrastructure series closes.** Final piece —
negative-results aggregation in the report (R21). Per the source
document, this is the construct-validity infrastructure working at
the reporting level: easy to surface failures by default, expensive to
hide them.

### Added

- **Issue #46 (Phase 3.2)** — **negative-results aggregation**.
  - New `collect_negative_findings(structure_report=…, sweep_summary=…,
    model_fit=…)` scans the three Phase 2 artifacts for findings that
    weaken or complicate the mastery claim:
    - Each structural anomaly is one finding.
    - Sweep instability (anything other than "stable") is one finding.
    - Each non-significant factor (Wald p > 0.05) is one finding.
  - **New Section 4b: Negative findings** in the rendered report.
    Renders one of four bodies depending on input:
    - "No Phase 2 artifacts supplied; the auto-collection step had
      nothing to scan."
    - "No negative findings detected in the supplied Phase 2 artifacts."
    - Grouped lists per source (structural anomalies / sweep
      instability / null factors).
    - When `--suppress-negatives` is set, a single banner explaining
      the suppression.
  - **New CLI flag `--suppress-negatives`** with three asymmetric
    side-effects:
    1. The Negative findings body is replaced by a suppression banner
       documenting the flag.
    2. A `Negative-findings suppression: ENABLED` warning is added to
       the report header (visible to any reader).
    3. The Summary verdict **downgrades one tier**: defensible →
       partially_defensible → not_defensible. Hiding evidence is
       itself a negative construct-validity signal.
  - 13 new tests across `collect_negative_findings` behavior, section
    rendering for the four input cases, the suppression banner, the
    header warning, the verdict downgrade, and CLI integration.

### Construct-validity infrastructure series closes

All nine features from *Closing the Construct-Validity Gap in
infereval* are now shipped:

**Phase 1 — schema and metadata**:
- v0.3.0 — factorial-design metadata (#30, R7+R12)
- v0.3.1 — runtime paraphrase-axis support (#32, R10)
- v0.3.2 — construction-provenance metadata (#34, R5+R8+R9)
- v0.3.3 — reference-panel declaration + cross-panel κ (#36, R4)

**Phase 2 — analytical extensions**:
- v0.4.0 — structural coherence checks (#38, R13)
- v0.4.1 — factor-effects model fitting (#40, R7+R12)
- v0.4.2 — sensitivity-analysis sweeps (#42, R11)

**Phase 3 — reporting and methodological discipline**:
- v0.5.0 — construct-validity report (#44, R16-R20)
- v0.5.1 — negative-results aggregation (#46, R21)

The remaining requirements that the document calls out as
*irreducibly outside the framework* — independent analyst panels,
held-out item construction, training-data separation, cross-domain
studies, replication, the in-principle interpretive commitments — are
research-program responsibilities the framework can make tractable
but not substitute for.

### Backwards compatibility

Pure-additive. No schema changes.

## [0.5.0] — 2026-05-20

**Phase 3 of the construct-validity infrastructure series begins.**
This release ships the *most opinionated* extension in the
programme per the source document: the construct-validity report
with structured claim slots. Closes coverage of **R16** (mastery
sense), **R17** (claim scope), **R18** (constitution vs. evidence),
**R19** (carving-indexed framing), and **R20** (disclosure of
analyst-supplied choices). The 0.x.y minor bump marks the
Phase-2-to-Phase-3 transition (analytical extensions →
reporting + methodological discipline).

### Added

- **Issue #44 (Phase 3.1)** — **construct-validity report**.
  - New module `infereval.report` with a `ConstructValidityClaims`
    Pydantic model (R16-R20) and a deterministic verdict computation:
    "defensible", "partially_defensible", or "not_defensible". The
    label is derived from the claimed scope + the
    competing-explanation-checks declared as run. The carving claim
    (R19) is required when scope reaches beyond `items_in_benchmark`.
  - **New CLI command** `infereval report`:
    - `--init-claims <path>` emits a stub claims JSON for the analyst
      to fill in.
    - With `--evaluation`, `--benchmark`, and `--claims`, plus
      optional `--structure`, `--sweep`, `--model-fit`, renders the
      report as Markdown to stdout or `--output <path>`.
  - The report has six sections: Identity, Summary metrics,
    Construct-validity claims (R16-R20), Evidence, Unaddressed
    competing explanations, Summary verdict. The Summary verdict
    renders one of three badges: ✅ defensible, ⚠️ partially
    defensible, ❌ not defensible. The framework refuses to render
    the ✅ badge without the corresponding competing-explanation
    checks marked as run.
  - 19 new tests across claims-schema validation, deterministic
    verdict computation (per scope tier), Markdown rendering (all
    six sections present, evidence integration, "NOT SUPPLIED"
    fallback), and CLI integration (`--init-claims`, full report,
    mismatched-id rejection).

  This is the most opinionated extension in the construct-validity
  programme per the source document — *embeds a methodological
  position about what claims should be made on top of what evidence*.
  The asymmetry: cheap to write up correctly (each slot has a clear
  format), expensive to write up incorrectly (the verdict
  deterministically downgrades when checks are missing or carving
  is unacknowledged at the wrong scope).

### Backwards compatibility

Pure-additive. New module, new CLI command. No schema changes.

## [0.4.2] — 2026-05-19

**Phase 2 of the construct-validity infrastructure series closes.**
Final Phase 2 piece adds sensitivity-analysis sweeps over varied
evaluation parameters. Addresses **R11** (sensitivity analysis on
free parameters).

### Added

- **Issue #42 (Phase 2.3)** — **sensitivity-analysis sweeps**.
  - New module `infereval.sweep` with `run_sweep(benchmark,
    provider, parameter, values, out_dir, ...)` and `coerce_values()`
    helpers.
  - **New CLI command** `infereval sweep <benchmark.json> --vary
    <param> --values <list> --provider X --model Y --out-dir <dir>`.
    Supported sweep parameters: `n_samples`, `tie_break`,
    `paraphrase_variant`, `temperature`. Each value produces a
    full per-value evaluation file + JSONL log; an aggregate
    `sweep-summary.json` carries the row table.
  - Dataclasses `SweepRow` and `SweepResult`; `SweepResult.stability_verdict`
    classifies the κ_C range into stable (< 0.05), moderate (< 0.10),
    or substantive variability — with escalating language so an
    unstable sweep tells the reader to consider tighter parameter
    choices or a wider analyst panel.
  - 18 new tests across value coercion, end-to-end sweep
    orchestration, the three stability-verdict bands, and the CLI
    integration.

### Phase 2 closes

All three Phase 2 features from *Closing the Construct-Validity Gap
in infereval* are now shipped:
- v0.4.0 — structural coherence checks (#38)
- v0.4.1 — factor-effects model fitting (#40)
- v0.4.2 — sensitivity-analysis sweeps (#42)

Phase 3 (reporting and methodological discipline — construct-validity
report + negative-results aggregation) is next.

### Backwards compatibility

Pure-additive. New module, new CLI command. No schema changes.

## [0.4.1] — 2026-05-19

Second piece of Phase 2 (analytical extensions). Adds factor-effects
modeling of model–analyst agreement against the design factors
declared in Phase 1.1. Addresses **R7** (multiple items per condition)
and deepens **R12** (per-condition decomposition).

### Added

- **Issue #40 (Phase 2.2)** — **factor-effects model fitting**.
  - New module `infereval.modeling` with `fit_factor_model(eval, bench)`
    producing a `ModelFit` containing per-level coefficients +
    per-factor joint Wald p-values + McFadden's pseudo-R² + the
    methodology notes.
  - Implementation: logistic regression of agreement
    (`sample.parsed_verdict == analyst_reference`) on declared
    factor levels, with **item-clustered standard errors** as a
    proxy for the per-item random-effect structure of a proper GLMM.
    The CLI / module / CHANGELOG explicitly call out the caveat:
    this is not a full GLMM (bambi/PyMC), but the marginal fixed-
    effects coefficients and joint Wald tests — which is what the
    document's "main effect of side-premise type, p < 0.001" output
    most directly needs — are recoverable.
  - **New CLI command** `infereval model <eta.json> --benchmark
    <bench>` prints the coefficient table, per-factor Wald tests,
    pseudo-R², and methodology notes.
  - Outcome reference: `--reference consensus` (default, analyst
    panel majority) or `--reference analyst:<id>` to pick a single
    analyst column.
  - 8 new tests covering: predictable factor detection, error on
    benchmark without declared factors, error on all-abstain
    dataset, pseudo-R² in unit interval, CLI integration, CLI
    error on mismatched benchmark id.

### Dependency

- New optional extra `[stats]`: `statsmodels>=0.14`. Install via
  `pip install 'infereval[stats]'`. The module imports it lazily so
  the rest of the framework works without it; importing
  `fit_factor_model` raises a clear `ModelingError` with the install
  hint if statsmodels is missing.

### Backwards compatibility

Pure-additive. New module, new CLI command, new optional extra.
No schema changes. No behavior change to existing commands.

## [0.4.0] — 2026-05-19

**Phase 2 of the construct-validity infrastructure series begins.**
Phase 2 covers analytical extensions beyond schema metadata —
structural coherence checks, mixed-effects model fitting, and
sensitivity-analysis sweeps. This release ships the *philosophically
central* piece: structural coherence checks against the derived frame
⟨B, I_M⟩. The 0.x.y minor bump marks the Phase 1→2 transition.

### Added

- **Issue #38 (Phase 2.1)** — **structural coherence checks on the
  derived frame**.
  - New module `infereval.structure` with three checks:
    - `containment_closure_check` — sanity-counts self-implications
      (items with Γ ∩ Δ ≠ ∅) and confirms they're in I_M by
      construction (clause i of Definition 3).
    - `rsr_role_consistency_check` — for items carrying an
      `rsr_target` and a role tag (`supporter`, `defeater`,
      `irrelevant-addition`), compares the model's verdict against
      the verdict the role *predicts* given the base-inference
      verdict on the same target. Flags items whose verdict
      contradicts the expected role-conditional verdict.
    - `base_case_stability_check` — surfaces targets where the model
      gives different verdicts on multiple base-inference items.
  - New dataclasses `StructuralAnomaly`, `StructuralCheck`,
    `StructuralReport`.
  - Top-level `run_all_checks(evaluation, benchmark)` runs all three
    and bundles the results.
  - **New CLI command** `infereval structure <eta.json> --benchmark
    <bench.json>` runs the checks and prints a human-readable report
    with per-section anomaly lists.
  - 16 new tests covering each check independently + the bundle + the
    CLI (including a live integration against the bundled pulmonology
    artifacts that correctly surfaces the a9 anomaly).

  Per *Closing the Construct-Validity Gap*: this is the addition that
  *converts the framework from agreement measurement to mastery
  characterization in the inferentialist sense* — the structural
  checks the Hlobil–Brandom framework explicitly motivates are now
  first-class operations.

### Backwards compatibility

Pure-additive: new module, new CLI command. No schema changes, no
behavior changes to existing commands.

## [0.3.3] — 2026-05-19

**Phase 1 of the construct-validity infrastructure series closes.**
Final Phase 1 piece adds reference-panel declaration and the
cross-panel agreement metric. Addresses **R4** (independent reference
check).

### Added

- **Issue #36 (Phase 1.4)** — **reference-panel declaration**.
  - `AnalystModel.panel: str | None = None` — analysts sharing a panel
    string are members of the same panel for cross-panel agreement
    analysis.
  - `Benchmark.primary_panel: str | None = None` — names the panel
    that `κ_F*` and the cross-panel statistic report against by
    default.
  - Validation: if any analyst declares a panel, all must (no
    partial-panel benchmarks); if `primary_panel` is set, at least one
    analyst must belong to it.
  - Helpers `Benchmark.panel_names()`, `analysts_in_panel(name)`,
    `analyst_indices_in_panel(name)`, `resolved_primary_panel()`.
  - **New metric** `inter_analyst_fleiss_per_panel(benchmark)` returns
    `κ_F*` per declared panel as `{panel_name: float | None}`.
  - **New metric** `cross_panel_kappa(benchmark, primary=..., check=...)`
    computes Cohen's κ between two panels' per-item consensus
    verdicts (majority within each panel, abstain on tie), restricted
    to items where both panels yield a substantive consensus. Guards
    against shared-error agreement within the primary pool (the
    specific concern Campbell & Fiske 1959 raise).
  - `inter_analyst_fleiss(benchmark)` now returns the *primary panel's*
    κ_F* for panelled benchmarks (unpanelled behavior unchanged).
  - **CLI**: `infereval describe` adds an `analyst panels:` section
    listing each panel's members, per-panel κ_F*, and (when exactly
    two panels are declared) the cross-panel κ_C. Omitted when no
    analyst declares a panel.
  - 14 new tests across schema validation, helpers, the per-panel +
    cross-panel metrics (with hand-verified κ value), and the CLI
    rendering.

### Backwards compatibility

`AnalystModel.panel` and `Benchmark.primary_panel` both default to
`None`. Every pre-0.3.3 benchmark validates unchanged.
`inter_analyst_fleiss(benchmark)` returns the same value as before
for flat benchmarks. `schema_version` stays `"1.0"`.

### Phase 1 closes

All four Phase 1 features from *Closing the Construct-Validity Gap in
infereval* are now shipped: factorial-design metadata (#30 / v0.3.0),
runtime paraphrase-axis support (#32 / v0.3.1), construction-provenance
metadata (#34 / v0.3.2), and reference-panel declaration (#36 / v0.3.3).
Phase 2 (analytical extensions — structural coherence checks, mixed-
effects model fitting, sensitivity-analysis sweeps) is next.

## [0.3.2] — 2026-05-19

Third piece of the construct-validity infrastructure series. Adds
per-item construction provenance for benchmark audit. Addresses partial
coverage of **R5** (documented construction), **R8** (held-out items),
and **R9** (training-data separation).

### Added

- **Issue #34 (Phase 1.3)** — **construction-provenance metadata**.
  - New `ConstructionMetadata` model with optional fields
    `authored_by`, `authored_on` (ISO date), `authored_blind_to_models`,
    and `source` (free-form citation for the primary material the
    author worked from — distinct from `references` which carries the
    framework-level `Reference` objects justifying the verdict).
  - `BenchmarkItem.construction_metadata: ConstructionMetadata | None`
    — `None` by default; populate selectively for items where the
    provenance matters.
  - `infereval describe` adds a `construction provenance:` summary
    section listing the annotated-item count, unique authors,
    authored-on date range, blinded-to model count, and source-citation
    count. Omitted when no item carries metadata.
  - `infereval describe --items` adds a `construction:` line per
    annotated item, rendering author + date + blinded-models + source
    on a single wrapped line. Omitted for items without metadata.
  - Content is the analyst's responsibility — the framework validates
    structure (Pydantic types, `extra="forbid"`) but does not enforce
    that `authored_on` post-dates any training cutoff. The point is
    to make the *presence* of these declarations auditable.

### Backwards compatibility

`BenchmarkItem.construction_metadata` defaults to `None`. Every
pre-0.3.2 benchmark validates unchanged. `schema_version` stays
`"1.0"`.

## [0.3.1] — 2026-05-19

Second piece of the construct-validity infrastructure series. Promotes
the `BearerModel.paraphrases` field from documentation-only to
runtime-active and exposes it on the CLI as `--paraphrase-variant` /
`--paraphrase-cycle`. Addresses **R10** — *the single most-cited
concern in the source document about content-vs-form sensitivity*.

### Added

- **Issue #32 (Phase 1.2)** — **runtime paraphrase-axis support**.
  - `infereval.endorsement._expressions_for(..., variant=k)` now picks
    `bearer.paraphrases[k-1]` per bearer for `k >= 1`, falling back to
    `bearer.expression` when the bearer doesn't have that paraphrase.
    `variant=0` (default) preserves existing behavior.
  - `infereval.endorsement.endorse(..., variant=k)` and
    `infereval.evaluation.evaluate(..., variant=k)` thread the variant
    through.
  - New `Evaluation.paraphrase_variant: int = 0` field records which
    variant was used at evaluation time.
  - New `Benchmark.n_paraphrase_variants -> int` helper returns
    `1 + max(len(b.paraphrases) for b in bearers)`.
  - **CLI**: `infereval evaluate` gains `--paraphrase-variant K` (single
    non-default variant) and `--paraphrase-cycle` (all K variants).
    Mutually exclusive. `--paraphrase-cycle` suffixes the output path,
    log path, and run-id with `-vN` per variant so the per-variant
    artifacts are unambiguous.
  - **CLI**: `infereval describe` adds a one-line `paraphrase variants:`
    summary when any bearer carries paraphrases (`K (Y/Z bearers carry
    paraphrases; max M each)`). Omitted otherwise.
  - Validation: `--paraphrase-variant K` rejects `K >=
    benchmark.n_paraphrase_variants`; the two flags together is
    rejected with a clear error.
  - 12 new unit tests covering `_expressions_for` variant semantics
    (canonical / first / second / out-of-range), the `evaluate()`
    integration (recording / round-trip / backwards-compat), the
    `n_paraphrase_variants` helper, CLI behaviors (variant recording,
    cycle file-suffixing, log-suffixing, run-id-suffixing, out-of-range
    rejection, mutual-exclusion rejection, no-effect on benchmarks
    without paraphrases), and the `describe` rendering (omitted /
    rendered with correct variant count and coverage line).

### Backwards compatibility

`Evaluation.paraphrase_variant` defaults to `0`. Every pre-0.3.1
evaluation JSON validates unchanged. No bearer-side schema changes —
`paraphrases` was already in the schema, just unused at runtime.
`schema_version` stays `"1.0"`.

## [0.3.0] — 2026-05-19

**Construct-validity infrastructure series begins.** First piece of the
multi-release programme set out in *Closing the Construct-Validity Gap
in infereval*, which extends the framework from "agreement
measurement" into the construct-validity-supporting role the
inferentialist methodology actually needs. Subsequent Phase-1 features
will be 0.3.x patch releases.

The 0.x.y minor bump marks the methodological shift in what `infereval`
sets out to be, not a breaking schema change — all 0.2.x benchmarks
validate unchanged.

### Added

- **Issue #30 (Phase 1.1)** — **factorial-design metadata**. New
  schema fields:
  - `Benchmark.factors: dict[str, list[str]]` — declared design factors
    and their levels for crossed-design benchmarks.
  - `Benchmark.factor_constraints: FactorConstraints | None` — currently
    supports `min_items_per_cell` (enforced by the model validator).
  - `BenchmarkItem.factor_levels: dict[str, str]` — per-item position
    in the design space.
  - New helpers `Benchmark.cells()` (count items per cell of the fully
    crossed design) and `Benchmark.is_fully_crossed_at_k(k)` (boolean).
  - Validation: every key in any item's `factor_levels` must be a
    declared factor; every value must be in the declared levels list;
    if `min_items_per_cell` is set, every cell must contain at least
    that many items.
  - **`infereval describe`** gains a `factorial design:` section
    summarising the factors, the crossed-cell count, the populated
    cell count, and (when declared) the `min_items_per_cell` floor
    with explicit underpopulated-cell list. Omitted when no factors
    declared.

  Addresses R7 (multiple items per condition) and supports R12
  (per-condition decomposition). 12 new unit tests on the schema
  validators + helpers, 3 new on the CLI rendering.

### Backwards compatibility

`factors`, `factor_constraints`, and `factor_levels` all default to
empty / `None`. Every pre-0.3.0 benchmark validates unchanged.
`schema_version` stays `"1.0"` — additive-with-defaults; existing
schema-version-1.0 consumers continue to work.

## [0.2.6] — 2026-05-19

CLI improvement release. Adds an expert-readable per-implication
listing mode to `infereval describe`.

### Added

- **Issue #28** — `infereval describe --items` (also `-i`). When
  supplied, prints every implication in a self-contained form a
  domain expert can read without opening the source JSON:
  - bearer-id form on the header line (links back to the methodology paper)
  - resolved English expressions for every premise (`Γ:`) and conclusion (`Δ:`)
  - analyst verdict (or m-tuple for multi-analyst benchmarks)
  - tag annotation in `[…]`
  - full inline reference block — citation + DOI + URL + section + note,
    each wrapped to 78 cols with continuation indent
  Items are grouped by target tag (`T1` / `T2` / `cross-cutting`) when
  those tags are present, otherwise rendered as a single flat block.
  Off by default so the summary stays compact for large benchmarks.
  Eight new unit tests cover the flag, the section header, resolved
  expressions, verdict rendering, inline references (including the
  pulmonology-benchmark `FLAG FOR PULMONOLOGIST REVIEW` annotation on
  a9), target-tag grouping with sort order, flat-list fallback for
  benchmarks without target tags, and the multi-analyst verdict tuple
  format.

## [0.2.5] — 2026-05-19

CLI improvement release. Makes `infereval describe` actually useful for
non-trivial benchmarks.

### Added

- **Issue #25** — `infereval describe` now surfaces four sections that
  were previously invisible:
  - **`verification prompt`** block (id, template, system message, parse
    regex) when the benchmark embeds a `VerificationPromptOverride`;
    omitted when the benchmark uses the framework default.
  - **`bearers (<n>)`** block listing every bearer id paired with its
    expression, two-column aligned, wrapping long expressions under the
    value column. Replaces the previous "you have to open the JSON to
    know what `cd` means" workflow.
  - **`references`** summary (counts at corpus / bearer / item levels;
    bearer-annotation ratio; mean refs per annotated item; the first 3
    corpus citations). Omitted entirely when no references field is
    populated. Closes the gap from Issues #18 / #22 — references are
    now visible in the primary inspection tool.
  - **`verdict distribution by tag group`** cross-tab. Scans each
    item's `tags` for the first target-inference identifier (`T1`,
    `T2`, …) or the literal `cross-cutting` tag; groups the analyst
    verdicts under those labels. Surfaces the per-target label balance
    the flat tag-frequency list cannot. Skipped when no item has a
    recognised group tag.

### Changed

- **Long `description` strings now wrap to 78 columns** (`textwrap.fill`
  with the value column aligned to the new fixed 13-char label gutter).
  Previously the description printed on a single physical line that
  wrapped awkwardly in any narrow terminal.
- **Header lines (`id` / `title` / `domain` / `description` / `schema`)
  now share a 13-char label column** so the values line up vertically.
  Visually consistent with the rest of the report.

### Tests

8 new unit tests in `tests/unit/test_cli_describe.py::TestDescribeNewSections`
cover all four new sections + the header-alignment regression boundary
+ section-omission behavior on benchmarks that don't carry the relevant
data.

## [0.2.4] — 2026-05-19

Single-issue patch release. Completes the references work begun in
v0.2.2 (Issue #18) by propagating benchmark-side provenance into the
evaluation artifact.

### Fixed

- **Issue #22** — `Evaluation` and `EvaluationItem` now carry a
  `references: list[Reference]` field, populated by `evaluate()` from
  the source benchmark's corresponding fields. Without this fix, all
  references on a benchmark (v0.2.2+) were dropped on the floor as soon
  as `evaluate()` ran, meaning anyone reading just an evaluation JSON
  file (the primary research artifact — what gets shared, archived,
  cited, replayed) had no readable provenance trail. The
  `benchmark_hash` confirms the source benchmark was the right one at
  run time but does not tell the reader *what guidelines* anchored each
  item. Five new unit tests in
  `tests/unit/test_evaluate.py::TestReferencesPropagation` cover the
  propagation path end-to-end: corpus-level refs, per-item refs,
  dump+load round-trip, the all-empty-defaults backwards-compatibility
  regression guard, and the string-shorthand auto-promotion at the
  evaluation level. Bearer-level references are intentionally not
  propagated by this fix because `Evaluation` does not currently carry
  any bearer data — that's its own design question and a separate
  change.

## [0.2.3] — 2026-05-19

Single-issue patch release. Restores correct evaluation behavior against
GPT-5.x and the o-series reasoning models when the caller asks for a
non-default temperature (e.g. ``temperature=0.0`` for determinism).

### Fixed

- **Issue #20** — `OpenAIProvider` now skips the ``temperature`` parameter
  for GPT-5.x and the o-series reasoning models (o1, o3, o4-*), which
  reject any value other than the default 1.0 with HTTP 400
  ``invalid_request_error``. Detection uses a new
  ``_rejects_temperature(model_id: str)`` predicate that matches the same
  model set as ``_uses_max_completion_tokens`` — same generation of
  models, same set of API constraints. The requested temperature is
  still recorded in ``ProviderParams`` and the evaluation JSON for
  audit-trail purposes (same posture as Anthropic's handling of ``seed``
  for ``claude-*``). Without this fix, any evaluation against
  ``gpt-5.x`` or an o-series model with ``--temperature 0.0`` (the
  default ``-o`` flag in our experimental scripts) had every sample
  return as ``parse_status: sample_failed`` and every item abstain.
  Six new unit tests in ``tests/unit/test_provider_openai.py`` cover
  the new predicate across the GPT-5 generation, the o-series, and the
  OpenRouter vendor-prefixed model id, plus a regression guard
  confirming GPT-4o and GPT-4.1 still accept ``temperature``.

## [0.2.2] — 2026-05-19

Schema feature release. Adds first-class provenance support for benchmarks.

### Added

- **Issue #18** — **`Reference` model** and `references: list[Reference]`
  field on three schema levels: `Benchmark`, `BearerModel`, and
  `BenchmarkItem`. Motivates regulated-domain benchmarks (medical,
  legal, financial) where every non-trivial implication needs a citation
  to a guideline, statute, or peer-reviewed source. `Reference` fields:
  `citation` (required), `doi`, `url`, `section`, `note`. Authors may
  pass a plain string anywhere a `Reference` is expected — it
  auto-promotes to `Reference(citation=s)` via a `mode="before"`
  validator, so `references: ["Ranieri et al. (2012)"]` and
  `references: [{"citation": "Ranieri et al. (2012)", "doi": "..."}]`
  both work. Nine new unit tests in `tests/unit/test_benchmark_io.py`
  cover the structured form, string shorthand at both item and bearer
  levels, backwards-compatibility (all-empty defaults on existing
  benchmarks), populated-everywhere round-tripping, and the `extra
  = forbid` regression boundary.

### Changed

- **Documentation**: `docs/authoring_benchmarks.md` adds a new "Step 7b:
  Add references" subsection with a worked example showing both
  shorthand and structured forms, and a brief justification covering
  auditability, reproducibility under analyst turnover, and downstream
  tooling.
- **Static schema**: `src/infereval/schemas/benchmark.schema.json`
  regenerated to include the new `$defs.Reference` and the optional
  `references` arrays at the three levels. `schema_version` stays
  `"1.0"` — adding optional fields with defaults is the textbook
  backwards-compatible additive change, and every pre-0.2.2 benchmark
  validates unchanged.

## [0.2.1] — 2026-05-19

Single-issue patch release. Restores correct evaluation behavior against
`claude-opus-4-7` (and any Anthropic model) under platform capacity strain.

### Fixed

- **Issue #16** — `AnthropicProvider._is_transient` now classifies HTTP
  503 (`ServiceUnavailableError`), 504 (`DeadlineExceededError`), and
  529 (`OverloadedError`) as transient, in addition to the previously
  recognised `RateLimitError` / `APIConnectionError` / `APITimeoutError`
  / `InternalServerError`. The corresponding SDK exception subclasses
  live under `anthropic._exceptions` and are not exported at the
  top-level namespace, so the fix matches by status code on the public
  `APIStatusError` base class. Without this fix, 529 storms during
  capacity events were recorded as `parse_status: sample_failed`,
  occluding the analyst's verdicts from κ_C / κ_F and depressing
  coverage. Observed in the wild on 2026-05-19: a 29-item
  pulmonary-edema benchmark against Opus 4.7 dropped to coverage
  0.7241 because 22 of 87 samples 529'd; the patched run on the same
  benchmark recovered to coverage 1.0000 in ~3 minutes wall time vs
  ~16 minutes for the failed-retry-chain version. Five new unit tests
  in `tests/unit/test_provider_anthropic.py` cover the new branch and
  guard the regression boundary (400 must remain non-transient).

## [0.2.0] — 2026-05-18

Methodology- and provider-level improvements surfaced during 0.1.0 use
against real APIs (the paraphrase-axis experiment and multi-model
triangulation). All v0.2.0 milestone issues closed.

### Added

- **`experiments/paraphrase_axis_triangulation.py` cross-family sweep**:
  the script's `MODELS` list now covers 13 frontier models from six
  families (Anthropic, OpenAI, DeepSeek, Qwen, Gemini, Mistral) plus
  GPT-4.1 as the original-paper baseline. The script auto-skips models
  whose API key is missing and isolates per-(model, variant) failures so
  one bad provider doesn't kill the sweep.
- **`experiments/results/` directory**: tracked location for committed
  findings artifacts, sibling to the gitignored `experiments/out/`
  working directory.
- **Cross-family findings document** at
  `experiments/results/cross_family_2026-05-18.md`. Eleven of thirteen
  frontier models reproduce Simonelli's analyst row exactly under the
  original δ(ra), an eleven-model independent replication. Includes all
  78 (Evaluation JSON + JSONL audit log) pairs from the sweep for full
  reproducibility.

### Changed

- **`VerificationPromptOverride` gains optional `system` and `id` fields.**
  A benchmark JSON can now fully specify a custom verification prompt
  (system + user template + parse regex + identifier) without dropping
  to the Python API. The paraphrase-axis experiment in
  `experiments/paraphrase_axis_triangulation.py` is now JSON-drivable.
  Closes #6.
- **Default `max_tokens` raised from 32 to 1024** on both
  `infereval.providers.base.SampleRequest` and
  `infereval.evaluation.ProviderParams`. The old default budget-clipped
  any reasoning-capable model. The new default is generous for non-
  reasoning models (which only emit a handful of tokens for a one-word
  verdict regardless of the cap) and sufficient for current reasoning
  models. Closes #4.
- **`SampleRecord` gains `finish_reason` and `reasoning_tokens`
  fields** (both `Optional[str]` / `Optional[int]`, defaulting to
  `None`). Providers populate them where available — OpenAI from
  `choices[0].finish_reason` and `usage.completion_tokens_details.reasoning_tokens`;
  Anthropic from `response.stop_reason` and `usage.thinking_tokens`. The
  fields round-trip through the evaluation JSON. Closes #5.
- **`ParseStatus` gains `"budget_clipped"`**. The endorser promotes
  `"unparseable"` to `"budget_clipped"` whenever the provider's
  `finish_reason` is in the canonical budget-hit set (OpenAI `"length"`,
  Anthropic `"max_tokens"`). Verdict still falls back to `abstain` per
  Definition 2, but the parse_status now tells the analyst the abstain
  is operational (raise `max_tokens` and re-run), not a model decision.
- **`ParseStatus`** is now a single canonical type in
  `infereval.types` rather than two divergent definitions in
  `prompts.py` and `evaluation.py`.

### Fixed

- **OpenAIProvider**: route to `max_completion_tokens` for GPT-5.x and
  the o-series (o1, o3, o4) reasoning models; keep legacy `max_tokens`
  for pre-5.x models. OpenAI deprecated `max_tokens` for these families
  as of mid-2026, and the framework was silently failing every call
  against them. Closes #9.
- **AnthropicProvider**: skip the `temperature` parameter for Claude
  Opus 4.7 and later (the API rejects it as deprecated). Sonnet and
  Haiku still pass it through unchanged. Closes #10.

### Authors

- Bradley P. Allen, University of Amsterdam.

## [0.1.0] — 2026-05-16

First public release. Implements the methodology of *Note on Simonelli's
Stop Sign Dialogue: An Implication-Space Methodology for the Empirical
Evaluation of LLM Inferential Mastery* (Allen, 2026).

### Added

- **Core data types** (`infereval.types`): `Verdict` enum
  (`good`/`bad`/`abstain`), frozen `Bearer` and `Implication` dataclasses
  with paper-faithful semantics (id-independent equality on implications,
  paraphrase families on bearers).
- **Derived implication frame** (`infereval.frame.DerivedFrame`): lazy
  membership per Definition 3 (clause (i) Containment ∪ clause (ii)
  endorsement); excludes ⟨∅, ∅⟩ by stipulation.
- **JSON I/O** (`infereval.benchmark`, `infereval.evaluation`): Pydantic
  models for benchmark (β) and evaluation (η) files with discriminated
  context-builder union (template + Python plugin), RSR-target metadata,
  cross-field validation (unknown bearer ids, mismatched analyst-verdict
  lengths). Sets serialize as sorted lists for diff-friendly output.
- **JSON Schemas** (`infereval.schemas`): Draft 2020-12 schemas for both
  file types, generated from the Pydantic models and committed at
  `src/infereval/schemas/{benchmark,evaluation}.schema.json` for non-Python
  consumers. Drift between source-of-truth and committed files is caught
  by a test.
- **Provider abstraction** (`infereval.providers`): `Provider` Protocol +
  `BaseProvider` ABC with retry-with-exponential-backoff-and-jitter.
  Concrete backends:
  - `AnthropicProvider` (Messages API) — emits a one-time warning when
    `seed` is supplied (Anthropic does not honor it).
  - `OpenAIProvider` (Chat Completions API) — passes `seed` through where
    the model supports it.
  - `OpenRouterProvider` — thin subclass of `OpenAIProvider` with
    OpenRouter base URL and optional `HTTP-Referer` / `X-Title` headers.
  - `ScriptedProvider` and `ReplayProvider` for deterministic testing.
  Lazy SDK imports so users only pay for the backends they install.
- **Endorsement pipeline** (`infereval.endorsement`): default verification
  prompt `default-v1` with `GOOD`/`BAD`/`ABSTAIN` tokens; regex parser
  with unparseable-as-abstain fallback; majority vote with deterministic
  tie-break (default `abstain`; configurable to `good`, `bad`, `first`);
  TeX-math delimiters stripped at prompt-construction time.
- **Metrics** (`infereval.metrics`): coverage, per-analyst coverage,
  analyst consensus, substantive index, Cohen's kappa, Fleiss' kappa,
  and the inter-analyst baseline `κ_F*(β)` from Remark 5. Edge cases
  (`m < 2`, unanimity, empty substantive subset, `p_e = 1`) return
  `None` with a warning rather than raising. `MetricsReport` aggregator
  with `by_tag` and `by_rsr_target` filters.
- **Structured JSONL logging** (`infereval.logging_setup`):
  `configure_run_logging` context manager attaches a JSONL `FileHandler`
  to the `infereval` logger for the duration of a run; per-sample audit
  records carry `prompt_hash`, `raw_response`, `parsed_verdict`,
  `parse_status`, `wall_time_ms`, and `usage`. One JSON object per line,
  consumable by `jq` or `pandas.read_json(lines=True)`.
- **CLI** (`infereval`): four subcommands — `describe`, `validate`,
  `evaluate`, `metrics`. The `evaluate` subcommand supports
  `--dry-run`, `--replay-from`, and `--log` for fully-deterministic
  audit-logged runs without API access. The `metrics` subcommand renders
  in `text`, `markdown`, or `json` and supports `--by-tag` and
  `--by-rsr-target` decompositions.
- **Stop-sign benchmark** at `examples/stop_sign/benchmark.json` (Example
  1 of the paper) plus a committed replay fixture at
  `tests/fixtures/stop_sign_replay.jsonl` (4 items × 5 samples) for the
  60-second quickstart.
- **Test suite**: 392 unit tests + 3 opt-in live-provider tests, 96.9%
  line coverage with a 90% threshold enforced via `pytest-cov`.

### Methodology defaults (locked in conversation; documented in `CLAUDE.md`)

- Package name: `infereval`. License: MIT.
- Verification prompt: fresh `default-v1` template (not a literal quote of
  prior work).
- `n_samples`: 5. Tie-break: `abstain` (matches the paper's treatment of
  abstention as the safe fallback). Cohen's kappa default reference:
  consensus `c_i`.
- δ / ctx_Γ / ctx_Δ placement: both JSON template form and Python plugin
  form supported.
- TeX-math delimiters (`$...$`) stripped at prompt-construction time.
- OpenAI surface: Chat Completions (for OpenRouter coverage).
- `κ_F*(β)` always reported by the CLI (as "undefined" when the
  baseline is unavailable per Remark 5).
- `DerivedFrame` materialization: lazy (membership via Def. 3 iff;
  the full I_M over ℘(B) × ℘(B) is unbounded).

### Deferred to a later release

- Async / batched provider calls (planned for 0.2.0; 0.1.0 is sequential
  by default for reproducibility).
- Bootstrap confidence intervals on metrics.
- Threaded `--workers > 1` concurrency for `evaluate`.

### Authors

- Bradley P. Allen, University of Amsterdam.

[0.2.0]: https://github.com/bradleypallen/infereval/releases/tag/v0.2.0
[0.1.0]: https://github.com/bradleypallen/infereval/releases/tag/v0.1.0
