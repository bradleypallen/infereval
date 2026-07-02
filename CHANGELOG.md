# Changelog

All notable changes to `infereval` are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the additional commitment that the benchmark and evaluation JSON
schemas are versioned independently (`schema_version: "1.0"`) and promised
stable from 1.0 onward, regardless of the framework version.

## [Unreleased]

No changes yet.

## [0.17.3] — 2026-07-02

**Validity guards, cross-run comparison, and the provenance tuple for the question-form / rendering evaluation (brief §8, §10.1, §12.3).** The default `question_form` stays `support` — the flip to `coherence` is deferred until the human survey is aligned (v0.17.4), so the two elicitation surfaces never disagree.

### Added — cross-run comparison (`infereval.comparison`)

- `compare_runs` aligns two same-item evaluations and reports per-item total-variation distance between their sample verdict distributions, the mean, and a cross-run κ (Cohen's, two runs as two annotators) over items substantive in **both** runs. A coverage floor (§12.4) reports "insufficient overlap" rather than a low-N κ; a §12.1 setup guard rejects a comparison across a different model snapshot or sampler config unless overridden.

### Added — validity guards (`infereval.guards`)

- `distribution_agreement` is the shared gate (per-item TV distance below a tolerance — default 0.10 — at a sample floor — default 30). `template_equivalence` (§8, the CI gate on any new template) and `shuffle_invariance` (§12.7 premise-order robustness) are thin wrappers.

### Added — R0/R1/R2 harness

- `experiments/scripts/r0r1r2_clinical.py` runs the same `|Δ|=1` items three ways with sampler config + model snapshot pinned: R0 support/plain, R1 coherence/plain, R2 coherence/domain (a `ClinicalTemplate`). R0→R1 isolates the question-form effect; R1→R2 the rendering effect. The live capture is a user-gated step.

### Changed — provenance (§12.3)

- `question_form` moves onto `EndorsementConfig`, so an evaluation records which question was asked (persisted in η; additive — pre-existing η load as `support`). The per-item run-log event now carries the full composed prompt + system text alongside the per-sample raw completion + parsed verdict, making `run.jsonl` a complete §12.3 audit trail. `evaluate()` gains an explicit `template` override.

### Added — deferred-cut seam

- `frame.derive_closure` is the single `NotImplementedError` seam where a multisuccedent cut / RSR-closure would attach (brief §9).

## [0.17.2] — 2026-07-01

**Multi-succedent core: the item generalizes to `⟨Γ, Δ⟩` with `|Δ| ∈ {0, 1, ≥2}`, and a `question_form` switch adds a bilateral coherence judgment alongside the legacy support question.** Conservative by construction — single-succedent is exactly the `|Δ|=1` case, the support path is byte-for-byte unchanged, and the measurement layer is untouched.

### Added — bilateral template registry (`infereval.templates`)

- `VerdictRequest` + a `Template` protocol that renders only *content scaffolding* (the commit/deny position) and never sees bearer ids, plus `DefaultTemplate` for arities 0/1/`"many"` and a per-domain registry keyed by benchmark id (`register_template` / `resolve_template`).
- The `coherence` question form frames the scaffolding ("Is this position coherent?") and decodes with a **uniform** polarity — `INCOHERENT → good`, `COHERENT → bad`, `UNCLEAR → abstain`. At `|Δ|=0` this reads as "the committed bearers are incompatible → good"; at `|Δ|=1` as "commit Γ, deny ψ is untenable, so the inference holds → good". The inversion lives entirely server-side (the participant only answers a plain coherence question).

### Added — `question_form` switch

- `evaluate(...)` and `endorse(...)` accept `question_form` (`"support"` | `"coherence"`, default `"support"`). `support` routes through the unchanged verification-prompt path and raises on `|Δ|≠1`; `coherence` is defined for every arity. `evaluate` resolves the per-benchmark template from the registry; prompt composition and `question_form` are logged.

### Added — deferred-cut seam

- `frame.derive_closure` is the single `NotImplementedError` seam where a multisuccedent cut / RSR-closure would attach (brief §9) — EM-elicit-and-score needs no cut.

### Notes

- The data model already admitted every arity; frame Containment (Definition 3) is correct for `|Δ| ∈ {0, 1, ≥2}` with no logic change (empty-succedent items get no free Containment inclusion; `⟨∅, ∅⟩` stays excluded).

## [0.17.1] — 2026-07-01

**Monotonicity scoring for ordinal-ladder items, resolving the brief's §12.2 blocker** ("non-decreasing endorsement over {good, bad, abstain}" is undefined because `abstain` is not between `bad` and `good`). Adds the scorer, a stratified reporting surface, and an `infereval monotonicity` command. The measurement layer (Definitions 6–10) is untouched — this is a separately-reported diagnostic.

### Added — monotonicity scorer (`infereval.monotonicity`)

- `score_all_ladders` / `score_ladder` join an evaluation's `model_verdict` with the benchmark's native `monotonicity_step`, grouping by `(ladder, family, fixed)`. Scoring rule: order `bad < good`; `abstain` is a skipped gap (never interpolated); a violation is a strict inversion of the substantive subsequence (`good → bad` for `non_decreasing`, symmetric for `non_increasing`); fewer than two substantive steps is `insufficient`, explicitly not a pass. `MonotonicityResult` exposes `steps` / `substantive` / `violations` / `n_gaps` / `status`, and `render_markdown` renders the per-ladder verdict sequences.

### Added — reporting stratification (`infereval.stratify`)

- `variation_breakdown` reports the model-verdict mix and coverage per variation type (base / strengthen / contested / defeat / abstain_anchor / monotonicity_step), joined on item id. `arity_partition` groups items by succedent arity (exclusivity `|Δ|=0` / single `|Δ|=1` / exhaustivity `|Δ|≥2`); it is forward-compat — every item is single-succedent today, and the §7 exclusivity/exhaustivity report split becomes load-bearing when multi-succedent items land.

### Added — `infereval monotonicity` CLI

- `infereval monotonicity <eta> <benchmark>` renders the ladder table + variation breakdown and exits non-zero on any strict-inversion violation, so scripts/CI can gate on monotonicity.

### Changed — bundled clinical pilot analysis

- The bundled dry-run analysis's monotonicity finding (ladders C/F/G monotone for all six models) is now scored by the native scorer rather than by hand; ladder C's informative `bad → good` BNP transition is surfaced explicitly.

## [0.17.0] — 2026-07-01

**Native support for the v0.5 benchmark schema: ordinal families, monotonicity ladders, a variation typology, and bearer-file structure declarations become first-class fields.** Previously a stopgap converter smuggled these concepts through `construction_metadata.source`; v0.17.0 gives each one a native home, adds a bearers-file loader and a constraint compiler, and firewalls the author's dry-run `placeholder` marker out of the measurement layer. All changes are additive — pre-v0.17.0 benchmarks validate and evaluate unchanged, and the entire κ layer is untouched.

### Added — native schema fields

- `BenchmarkItem`: `ladder`, `variation` (`base` / `strengthen` / `contested` / `defeat` / `abstain_anchor` / `monotonicity_step`), `target`, `placeholder` (a `Verdict` superset with a `contested` marker), `construction_note`, and `monotonicity_step` (family / tier / tier_index / expected / fixed).
- `Benchmark`: `ordinal_families`, `copresence_rules`, `entailment_rules`, `regularities`, `targets`. `BearerModel` gains `ordinal_family`.
- `Benchmark._check_consistency` now validates that ordinal-family tiers, bearer `ordinal_family` annotations, copresence/entailment references, per-item `target` and `monotonicity_step`, and regularity item ids all resolve.

### Added — bearers-file loader (`infereval.bearers`)

- `parse_bearers_file` / `load_bearers_file` parse the v0.5 bearers grammar (`@ordinal` / `@mutex` / `@entails` / `@copresent` / `~regularity` annotations plus `id "expression"` definitions) into a `BearersDoc`. Annotations are recognised only as the leading token of a comment, so prose mentioning a marker mid-sentence is not misread. Enforces an additive-only bearer-versioning contract (redefining an id with a changed expression is an error).

### Added — constraint compiler (`infereval.compiler`)

- `compile_constraints` turns family declarations into pairwise within-family exclusivity sequents `⟨{x_i, x_j}, ∅⟩`, optional exhaustivity sequents (for `@copresent` rules flagged `exhaustivity=True` — off by default), optional entailment sequents, and the `@copresent` admissibility rules; `is_saturated` checks a Γ against a co-presence rule. Domain-agnostic: ordinal and mutex families are treated identically for exclusivity.

### Added — `infereval bearers-import` CLI

- Builds a validated benchmark from a bearers file + a v0.5 items document, mapping every concept onto its native field. A pre-recruitment items document (no analyst panel) gets a synthesized `pending-analyst-panel` stopgap so it loads; each item's provisional read stays in its firewalled `placeholder` field.

### Changed — placeholder firewall

- The measurement layer is now mechanically barred from reading `BenchmarkItem.placeholder` (`analyst_verdicts` is the sole κ source). `placeholder` never enters an evaluation / η, and a CI gate (`test_placeholder_firewall.py`) fails if any measurement module accesses a `.placeholder` attribute.

### Changed — bundled clinical pilot fixture

- The bundled clinical pilot fixture (CPE vs. ARDS oxygenation differential) is regenerated through the native loader — the `construction_metadata.source` hack is gone and the `contested` placeholder is preserved without normalization. Rendered prompts are identical to the previous converter output across all 35 items, so evaluation semantics are unchanged. Its example/results directories use a neutral label.

### Schema

- `benchmark.schema.json` regenerated to include the new fields (backward compatible; all new fields optional / default-empty).

## [0.16.0] — 2026-06-09

**Clean re-capture of the bundled cross-family demonstration suite under the v0.15.2 framework.** v0.14.0 shipped three framework bugs that v0.15.0/v0.15.1/v0.15.2 fixed. v0.16.0 deletes all v0.14.0-era bundled artifacts and re-captures the entire 45-cell demonstration suite (39 stop-sign × 3 paraphrase variants + 6 pulmonology) from scratch with three-interval R22 evidence per cell. Pre-release software: this clears the bundled distribution of any tainted data so early adopters see only clean exemplars.

### Why

The v0.15.0 "preserve as audit trail with retraction banners" approach was internally consistent but created confusion risk: a user landing on a retracted writeup could skim past the banner and read bug-period findings as valid. For pre-release software the cleaner move is to delete every tainted artifact and replace with fresh captures — git history preserves the historical record, KNOWN_ISSUES_v0.14.0.md + the v0.15.x CHANGELOG entries serve as the canonical retraction record.

### Captured

45 cells × 4 captures each = 180 etas + 45 multi-retest artifacts. All captured under v0.15.2 framework with three time-scales of R22 evidence per cell:

- **eta-0**: baseline
- **eta-1**: back-to-back retest (≈45 s elapsed)
- **eta-2**: 1h drift retest (≈3 600 s)
- **eta-3**: day-out retest (≈126 700 s ≈ 35 h)

In-band audit: 4032 total samples scanned, 81 known `provider_error` (OpenRouter 429 rate-limits, mostly on qwen3-max), **0 suspected silent failures**. Published metrics == recomputed metrics on every cell — the v0.15.2 aggregator-skip handles provider failures correctly in real burst conditions.

### Added — bundled demonstration artifacts

- `experiments/results/pulmonology/retest/<cell>/eta-{0..3}.json` for 6 cells: claude-opus-4.7, deepseek-v4-pro, gemini-2.5-pro, gpt-4.1, gpt-5.5, qwen3-max
- `experiments/results/stop_sign/retest/<cell>/eta-{0..3}.json` for 39 cells (13 models × 3 paraphrase variants)
- `experiments/results/pulmonology/retest/<cell>-multi-retest.json` (6) + same for stop-sign (39)

### Added — analysis writeups

- `experiments/results/pulmonology_2026-06-09.md` — 6-model pulmonary edema analysis. Headline: deepseek-v4-pro shows monotone κ decay across all three intervals (0.867 → 0.792 → 0.729) — the clearest published example of detectable across-update model drift via R22 staged composition. Five other cells held κ = 1.000 across every interval.
- `experiments/results/stop_sign_2026-06-09.md` — 13-model × 3-variant analysis. Headline: under the paper-aligned δ(ra), 12 of 13 frontier LLMs reproduce Simonelli's analyst row exactly (κ_C = +1.000) — replicates the v0.5.18 sweep's headline under fresh v0.15.2 captures. Perceptual variant is the cleavage axis exactly as R10 predicts.

### Removed (tainted v0.14.0-era artifacts)

- 3 retracted analysis writeups (`pulmonology_2026-06-07.md`, `stop_sign_2026-06-07.md`, `pulmonology/retest/report-gemini-2.5-pro.md`)
- 2 pre-bug writeups superseded by fresh analyses (`pulmonology_2026-06-06.md`, `stop_sign_2026-05-18.md`, `stop_sign_2026-06-06.md`)
- 51 bundled cross-family etas + run.jsonl
- 53 retest cell subdirectories under both benchmarks
- 45 multi-retest artifacts containing v0.14.0-era Phase 2 day-out pairs
- 2 bundled retest report markdowns
- 5 macOS Finder duplicate `* 2/` directories
- v0.10.0 qwen3-max pulm eta (the 8-silent-failure historical case)
- All 12 stop-sign Phase 1 qwen3-max retest etas

Total: ~470 files deleted in Stage 1; ~270 new files added in Stages 2–5. Net diff is a clean swap.

### Updated

- `KNOWN_ISSUES_v0.14.0.md`: RESOLVED header pointing at v0.16.0 release; pre-existing bug analysis preserved as historical record
- `CLAUDE.md`: banner replaced from "v0.14.0 RELEASE-BLOCKING ISSUES" → "v0.16.0 fresh demonstration suite landed" with pointers to the new writeups
- `README.md`: "Findings" section restored with substantive 2–3 sentence summary citing the new analyses
- `examples/pulmonary_edema/README.md`: pointer to the new cross-family analysis
- Retest-directory READMEs (`experiments/results/{pulm,stop_sign}/retest/README.md`): describe the v0.16.0 capture flow rather than v0.14.0 Phase 2 plans

### Methodology paper material

The v0.16.0 re-capture closes the methodological loop:

1. v0.14.0 ships a silent-failure bug
2. v0.14.0's R22 discipline catches the bug via implausibly-uniform coverage-collapse
3. v0.15.0/v0.15.1/v0.15.2 fix the bug + add an audit CLI + a live stress harness
4. v0.16.0 deletes the tainted data and re-captures under the fixed framework — producing 81 *observable* provider failures and 0 silent failures, validating the fix end-to-end under live OpenRouter burst conditions

The v0.10.0 Gemini "across-update drift" finding that originally motivated R22 is replaced/superseded by the v0.16.0 deepseek-v4-pro pulmonology finding: clear monotone κ decay across three time-scales on a single bundled multi-retest artifact, captured under the fixed framework.

### Reproducing the v0.16.0 captures

```bash
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...
export OPENROUTER_API_KEY=...

# Phase 1 (baseline + back-to-back + 1h drift), ~1.5 h wall, ~$10–25:
python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py
python experiments/scripts/stop_sign_multiinterval_r22_retrofit.py --max-parallel 39

# Phase 2 (day-out append, after >24 h elapsed), ~30–60 min wall, ~$5–10:
python experiments/scripts/phase2_append.py

# Audit verification across all 180 eta files:
for eta in experiments/results/*/retest/*/eta-?.json; do
  infereval audit "$eta" --json | jq '.n_suspected_silent_failures'
done | sort | uniq -c
```

## [0.15.2] — 2026-06-07

**Live-validation harness for the v0.15.x silent-failure fixes.** Adds `experiments/scripts/v0151_silent_failure_stress.py` — a permanent regression-test harness that replicates the v0.14.0 silent-failure bug conditions against the live OpenRouter API and verifies the v0.15.0/v0.15.1 framework fixes hold under real burst pressure.

### Why

The v0.15.0 / v0.15.1 unit tests validate the fix logic in isolation (with mocked providers). The audit CLI validates the historical reconciliation math. Neither proves the fix holds under **live network conditions** — burst-parallel calls against real OpenRouter rate limits. v0.15.2 ships a harness to close that gap.

### What it does

Runs three OpenRouter cells (gemini-2.5-pro, qwen3-max, deepseek-v4-pro — the same three that exhibited the worst v0.14.0 silent-failure collapse per `KNOWN_ISSUES_v0.14.0.md`) concurrently under `ThreadPoolExecutor(max_workers=3)` against the bundled pulmonology benchmark. After the run, calls `infereval audit --json` on each capture and prints a per-cell summary table comparing published vs recomputed coverage and κ_C.

### First-run validation results (v0.15.1 framework, 2026-06-07)

| Cell | Samples | Real failures caught | Suspected | Coverage | κ_C |
|---|---:|---:|---:|---:|---:|
| gemini-2.5-pro | 150 | 0 | 1 (budget-clipped) | 1.0000 | 0.5714 |
| qwen3-max | 150 | **13** | 0 | 0.8000 | 0.8235 |
| deepseek-v4-pro | 150 | 0 | 3 (all budget-clipped) | 0.9333 | 0.6500 |

The qwen3-max burst caught 13 real OpenRouter `429 Rate limit exceeded` failures, all correctly recorded with `provider_error` set and surfaced by the audit as **known** (0 suspected). Coverage held in the 0.80–1.00 range vs the v0.14.0 day-out collapse to 1/30, 10/30, 5/30 — sensible model behavior, no instrument-artifact collapse. All "suspected" flags resolved to real `parse_status="budget_clipped"` calls (reasoning models exhausting token budget on silent CoT), documented audit-heuristic false-positives.

### Usage

```bash
export OPENROUTER_API_KEY=...
python experiments/scripts/v0151_silent_failure_stress.py
```

`--out-dir`, `--cell`, `--bench`, `--max-workers` flags supported. Default cell list and burst pattern matches the v0.14.0 bug condition exactly.

### Cost / wall time

~$0.20 against OpenRouter list pricing; 5–25 minutes wall time depending on which reasoning models are slowest. Single-cell smoke test ~$0.05.

## [0.15.1] — 2026-06-07

**Patch: validation-test-discovered race in `configure_run_logging`.** While writing post-v0.15.0 validation tests to answer the "how do we really know this works" question, the new `ThreadPoolExecutor` isolation test caught a secondary race in the logger setup code (separate from the v0.14.0 cross-contamination bug fixed in v0.15.0): when one thread exited its `configure_run_logging` block and restored the logger level, concurrent threads' INFO events could drop at the logger gate. The level-restore now reference-counts active calls and only restores when the last one exits.

### Fixed

- **`configure_run_logging` level-restore race.** Multiple concurrent `with configure_run_logging(...):` blocks no longer drop each other's events during exit. The level raise/restore is now reference-counted and serialized under a module-level lock. Cross-contamination guarantees from v0.15.0 unchanged.

### Added (validation tests)

- **`tests/unit/test_provider_openai.py::test_empty_content_recovers_on_retry`** — first call returns empty body (triggers `EmptyResponseError`), second call returns clean "GOOD". Verifies the retry path actually delivers the recovered text rather than just suppressing the failure.
- **`tests/unit/test_endorsement.py::test_empty_response_retry_recovers_cleanly`** — end-to-end through real `OpenAIProvider` + endorsement: 3 samples, each first-call-empty then-succeed. All three samples must end up as clean GOOD with `provider_error is None`.
- **`tests/unit/test_logging_setup.py::test_thread_pool_executor_isolation`** — four concurrent `evaluate()`-pattern calls under `ThreadPoolExecutor`. Each file must contain exactly its own run's events (no contamination, no drops). This is the test that caught the level-reset race above.

951/951 unit tests pass.

## [0.15.0] — 2026-06-07

**Framework instrumentation fixes for the three v0.14.0 silent-failure bugs caught by the framework's own R22 discipline.** v0.14.0's Phase 2 day-out staged-composition sweep produced an implausibly uniform "coverage collapse" finding in the pulmonology cells. Forensic audit (the framework's R22 cap firing correctly) revealed it was an instrumentation artifact: the framework had three latent bugs — silent empty-response → ABSTAIN; cross-thread logger contamination; no rate-limit retry on burst-parallel OpenRouter calls — composing to fabricate "model behavior" out of provider failures. v0.15.0 fixes all three, adds an `infereval audit` CLI to post-hoc characterize legacy captures, and ships backfill audit reports for the qwen3-max cells that were meaningfully affected. **The canonical bug-analysis doc lives at [`KNOWN_ISSUES_v0.14.0.md`](./KNOWN_ISSUES_v0.14.0.md) at the repo root.**

### Why the change

v0.14.0 Phase 2 day-out pulmonology results showed Gemini 2.5 Pro losing 29 of 30 substantive verdicts, Qwen3-max losing 20 of 30, DeepSeek v4-pro losing 25 of 30 — all OpenRouter-mediated, all "coverage collapse" matching no real model behavior. Inspection of the run.jsonl logs found 86/90 Gemini-pulm samples with `wall_time_ms=0` + `raw_response=""` — silent HTTP failures that the endorsement regex parsed as ABSTAIN, the aggregator counted as model abstention, and the metrics treated as real evidence. Audit of historical etas found the same bug firing at lower rates across every prior capture: 0.64% on v0.5.18, 1.85% on v0.10.0, 1.5–2.6% on v0.14.0 Phase 1.

The framework's R22 cap caught the implausibly uniform burst-failure signal and forced the investigation. The fix below restores R22's distinguishing power between model failure and instrument failure.

### Added

- **`infereval.providers.base.EmptyResponseError`** raised by providers when the HTTP call returned 200 + an empty/whitespace body. Treated as always-transient by `BaseProvider.sample()`'s retry loop — every provider subclass inherits the classification without overriding `_is_transient`. After retry exhaustion, surfaces as `ProviderSampleError`.
- **`SampleRecord.provider_error: str | None`** — a new optional field on the per-sample record carrying the string of the underlying provider exception. Aggregators that understand the field skip the sample entirely (no spurious ABSTAIN credit); aggregators that don't (v0.14.0 consumers) see the legacy placeholder ABSTAIN and round-trip the eta as before.
- **`infereval audit <eta.json>`** — new CLI subcommand. Scans an evaluation JSON for silent-failure samples using two detection paths: (a) known failures via `provider_error` for v0.15.0+ captures; (b) heuristic flagging via `parsed_verdict == ABSTAIN AND (raw_response empty OR wall_time_ms in (0, None))` for pre-v0.15.0 etas. Reports published vs recomputed coverage and κ_C side-by-side. `--verbose` adds a per-item breakdown; `--json` emits a machine-readable report.
- **`infereval.logging_setup.current_run_id()`** diagnostic helper exposing the per-thread run_id contextvar.

### Changed

- **`OpenAIProvider._sample_once`** raises `EmptyResponseError` when `text.strip() == ""` AND `finish_reason != "length"` (the latter is real budget-clipped output, not API failure).
- **`AnthropicProvider._sample_once`** raises `EmptyResponseError` when the joined content text is empty AND `stop_reason != "max_tokens"`. Symmetric to the OpenAI change.
- **`endorse()`** now skips samples with non-None `provider_error` when computing the majority vote and per-verdict counts. A 2-good-1-API-failure item now resolves to a clean GOOD with count 2, not GOOD-with-an-abstain. If every sample fails, the vote falls through `majority_vote([])` → ABSTAIN per the existing empty-list contract; a fuller `model_verdict = None` representation is deferred to a later release.
- **`verdict_distribution()` fallback path** mirrors the same skip — provider_error samples drop out of good/bad/abstain counts when an item lacks a pre-computed `MajorityVote`.
- **`configure_run_logging`** now scopes each FileHandler to its own run via a `contextvars.ContextVar`. Concurrent `evaluate()` calls in different threads no longer cross-contaminate each other's JSONL log files (the v0.14.0 cross-thread logger bug). Single-evaluate use is unchanged; the contextvar is set on entry and reset on exit.

### Backfill audit & retractions on `main`

- **`KNOWN_ISSUES_v0.14.0.md`** at the repo root — single source of truth on the three bugs, audit results across framework history, retraction list, fix plan.
- **`experiments/results/pulmonology_2026-06-07.md`** — RETRACTED banner on Phase 2 day-out section.
- **`experiments/results/stop_sign_2026-06-07.md`** — partial-retraction banners on Shape 4 (qwen3-max-intrinsic) and Phase 2 day-out (qwen3.6-flash-perceptual).
- **`experiments/results/pulmonology/retest/report-gemini-2.5-pro.md`** — ARTIFACT WARNING banner.
- **`experiments/results/pulmonology_2026-06-06.md`** — appended `Silent-failure audit (v0.15.0)` section with recomputed κ_C for the qwen3-max v0.10.0 capture (8 silent failures, coverage 0.6667 → 0.7333, κ_C 0.8864 → 0.8053).
- **`experiments/results/stop_sign_2026-05-18.md`** — appended `Silent-failure audit (v0.15.0)` section covering all 12 qwen3-max retest etas across 3 variants × 4 intervals. Recomputed κ_C is uniformly equal to or higher than published on every tainted cell — the qwen3-max variant-sensitivity claim is strengthened, not weakened, by the audit.

### Tests

941 → 948 unit tests pass.

- `tests/unit/test_provider_openai.py` — empty-response + finish_reason='stop' raises after retries (the v0.14.0 bug); empty + 'length' returns clean budget-clipped.
- `tests/unit/test_provider_anthropic.py` — symmetric empty-response coverage.
- `tests/unit/test_endorsement.py` — failed samples excluded from majority vote and per-verdict counts; partial-failure item resolves to clean substantive verdict.
- `tests/unit/test_logging_setup.py` — concurrent `configure_run_logging` calls in two threads write to separate files without cross-contamination; no-run-id callers preserve legacy behavior.
- `tests/unit/test_audit_cmd.py` — 7 cases covering both detection paths, both output modes, and edge cases (real-abstain not flagged, recomputed coverage recovers under all-silent-failure substitution).

### Not in scope for v0.15.0

- **Re-running Phase 2 day-out for pulmonology cells.** v0.15.0 ships the framework fixes + audit CLI; running Phase 2 day-out cleanly under `--max-parallel 1` against v0.15.0 comes as a follow-on commit (planned for v0.16.0).
- **Migrating historical eta JSONs to include the `provider_error` field.** The legacy etas retain their original schema; the audit CLI heuristically re-classifies silent failures on the fly.
- **Re-running v0.14.0 Phase 1 captures.** Phase 1 had 1.5–2.6% silent failure rates — low enough that published findings for non-qwen3-max cells remain valid. Only qwen3-max cells are re-examined.

## [0.14.0] — 2026-06-07

**Staged-composition R22 + bundled cross-family retrofit**: two new `infereval retest --auto` flags (`--baseline-from <eta-path>` primitive, `--append-to <multi.json>` composer) enable Phase 2 day-out / week-out R22 evidence to ship as separate CLI invocations days or weeks after Phase 1, without the CLI process needing to stay alive for the elapsed window. Every bundled cross-family experiment (39 stop-sign cells + 6 pulmonology cells) gains companion Phase 1 R22 evidence (back-to-back + 1h drift) under the v0.14.0 methodology so the bundled distribution is conformant.

### Why the change

v0.11.0 added `retest --auto`, v0.12.0 made `--interval-s` repeatable, v0.13.0 made `infereval report` surface the multi-interval shape — but two methodological gaps remained:

1. **`--interval-s 86400` is operationally fragile.** Capturing day-out drift required the CLI process to stay alive 24+ hours: a tmux session has to survive, no checkpointing, all-or-nothing. The v0.12.0 plan explicitly punted a `--baseline-from <existing-eta>` mode that would enable staged composition.

2. **The bundled experimental record had no R22 backing.** The v0.5.18 stop-sign 13-model × 3-paraphrase-variant sweep (39 cells under `experiments/results/stop_sign/`) and the v0.10.0 pulmonology 6-model sweep (`experiments/results/pulmonology/`) shipped without companion R22 evidence. The bundled distribution wasn't yet conformant with the v0.13.0 retest-aware report layout it was designed to render.

v0.14.0 closes both gaps.

### Added

- **`--baseline-from <eta-path>` (primitive).** Load a saved baseline eta via `Evaluation.load`, run ONE fresh capture via `evaluate`, compute retest, and emit a **one-pair `MultiIntervalRetestResult`** whose `pairs[0].interval_s` is computed from the actual elapsed wall clock between `baseline.started_at` and the fresh capture's `started_at` (via the new `infereval.retest.compute_interval_s` helper). Mutually exclusive with multi `--interval-s` (the interval is auto-computed). Requires `--auto`.
- **`--append-to <multi.json>` (composer).** Load an existing `MultiIntervalRetestResult`, resolve the baseline eta from sibling `eta-0.json` by default (or `--baseline-from <override>` for non-canonical layouts), run ONE fresh capture, append a new `IntervalPair` to the existing pairs tuple, and write back in place (or `-o <override>`). The loaded artifact's `identity_criterion` is preserved verbatim — the criterion is a one-shot claim-level declaration that applies to every pair, including each Phase 2 append.
- **`compute_interval_s(eta_a, eta_b) -> int`** in `infereval.retest`. Single source of truth for the `interval_s` field on `IntervalPair` when the framework synthesizes a pair from two evaluations whose timestamps are known. Returns 0 if either `started_at` is None (degenerate metadata) or the delta is negative (clock skew); otherwise integer seconds.
- **Run-id provenance markers.** `--append-to` mints `retest-append-<hex8>` prefixes (distinct from Phase 1's `retest-auto-<hex8>` prefixes) so each invocation's staged provenance is traceable in logs and audit trails. The appended eta is named `eta-{N+1}.json` next to the existing pair etas.
- **Baseline-id verification on `--append-to`.** The existing artifact's `baseline_run_id` must match the loaded baseline eta's `id`. Catches the wrong-baseline-file mistake at source rather than silently composing pairs against the wrong anchor.
- **Two Phase 1 orchestrator scripts** (Python, parallelized via `concurrent.futures.ThreadPoolExecutor`):
  - `experiments/scripts/stop_sign_multiinterval_r22_retrofit.py` — 39 cells (13 models × 3 paraphrase variants), `--interval-s 0 --interval-s 3600`, ~1404 LLM calls. Uses the v0.5.18 `defeasible-explicit-v1` prompt and `make_variant_benchmark` from `paraphrase_axis_triangulation.py` so the R22 captures are taken under identical endorsement conditions to the original cross-family sweep.
  - `experiments/scripts/pulmonology_multiinterval_r22_retrofit.py` — 6 cells, `--interval-s 0 --interval-s 3600`, ~1620 LLM calls. Uses the benchmark-embedded `defeasible-clinical-v1` prompt.
  - Both support `--dry-run` (lists planned invocations + env-var status without LLM calls), `--only <label>` (filter to subset, repeatable), and `--max-parallel N` (default 8).
- **Phase 1 identity-criterion declarations** at `experiments/results/{stop_sign,pulmonology}/retest/claims-r22-phase1.json`. Each declares the doubly-relative R22 commitment (same provider+model id, cross-update identity asserted, same scaffolding) with rationale explaining the within-CLI-invocation framework-substantiated + analyst-substantiated portions.
- **45 Phase 1 multi-retest artifacts** committed at:
  - `experiments/results/stop_sign/retest/<model>-<variant>-multi-retest.json` × 39
  - `experiments/results/pulmonology/retest/<model>-multi-retest.json` × 6
  - Plus per-cell saved etas at `<cell>/{eta-0,eta-1,eta-2}.{json,run.jsonl}` for full audit-grade reproducibility.
- **Refreshed analysis markdowns**:
  - `experiments/results/stop_sign_2026-06-07.md` — 39-cell multi-interval R22 analysis grouped by variant; complements the v0.5.18 paraphrase-axis findings with within-day reliability evidence per cell.
  - `experiments/results/pulmonology_2026-06-07.md` — 6-cell multi-interval R22 analysis; reads the v0.10.0 Gemini 2.5 Pro 0.21 κ_C drift result through the within-day timeline.
- **Bundled retest-aware reports** for one representative cell per benchmark, demonstrating the v0.13.0 §2 Reliability layout against real multi-interval Phase 1 data.

### What did not change

- **`infereval retest` manual mode** (positional `<eta_a> <eta_b>`) — untouched.
- **`MultiIntervalRetestResult`, `IntervalPair`, `RetestResult` schemas** — unchanged; v0.12.0 model is sufficient.
- **`infereval report` rendering** — v0.13.0 layout consumes Phase 1 artifacts unchanged.
- **Existing v0.5.18 / v0.10.0 cross-family eta files** — retained as historical agreement record. v0.14.0 adds R22 reliability evidence alongside; it does NOT regenerate the agreement evidence.
- **All JSON content schemas** — only `framework_version.default` bumps to `0.14.0`.

### Methodological framing

The staged-composition pattern operationalizes what the methodology paper has been pointing at all along: reliability is not a single back-to-back floor measurement but a *time-scale-indexed* commitment that the analyst grows over the time scales relevant to their scope claim. Phase 1 captures the within-day floor; Phase 2 appends day-out / week-out evidence as the analyst's time budget allows. Each `--append-to` invocation is the analyst recommitting to the same individuation criterion across the elapsed wall clock — the act of appending IS the methodological commitment that R22 requires. Without the staged-composition machinery, capturing week-scale R22 evidence requires a week-long process lifetime; with it, week-scale R22 evidence ships as a one-minute invocation after the week has elapsed.

The 45 Phase 1 artifacts are the bundled demonstration that this discipline is operationally cheap. They sit at v0.14.0 as the "every cell has R22 backing" anchor of the conformant distribution; subsequent Phase 2 appends will ship as commits to `main` over the following weeks.

**What Phase 1 surfaced**: 37 of 45 cells are perfectly stable at both intervals (82%); 8 cells show methodologically interesting non-stable behavior split across four shapes — within-session burstiness that resolves at 1h (3 cells, all smaller / distilled models on the 1-2 stop-sign variants where the larger sibling is stable), persistent self-disagreement at both intervals (2 perceptual cells where the model defeasibly disagrees with itself on a single ambiguous item), **one real short-horizon cross-update drift** (deepseek-v4-pro on the stop-sign perceptual variant: κ=+1.000 back-to-back, +0.500 at 1h — the textbook R22 failure mode), and degenerate-but-consistent verdict columns where Cohen's κ is undefined despite perfect reproducibility (2 cells: claude-haiku-4.5-original, qwen3-max-intrinsic). The pulmonology Gemini-2.5-Pro cell that motivated R22 (v0.10.0's 0.21 κ_C drift across 2.5 weeks) is **perfectly stable at both 0s and 1h**, definitively ruling out within-1h drift as the explanation and sharpening the Phase 2 question to "where between 1 hour and 2.5 weeks does the drift first emerge?" Cross-cutting reading: reliability and agreement track together rather than as independent measurement axes — the perceptual δ(ra) variant produces 4 of 8 stop-sign non-stable cells (twice the rate of either other variant), aligning with the v0.5.18 paraphrase-axis finding that the perceptual reading is where cross-family disagreement concentrates.

### Docs

- `docs/construct_validity.md` — Phase 2 section: new "v0.14.0+ staged-composition pattern" sub-paragraph documenting `--baseline-from` and `--append-to` semantics, run-id minting, identity-criterion threading.
- `CLAUDE.md` — new locked-defaults entry on the staged-composition CLI surface.
- `README.md` — one-sentence mention in the existing R22 paragraph.
- `experiments/results/{stop_sign,pulmonology}/retest/README.md` — refreshed (stop-sign) / new (pulmonology) with Phase 1 layout + reproducibility command.

### Schemas

- `framework_version.default` bumped to `0.14.0`. No content-schema changes.

### Tests

- New `tests/unit/test_cli_retest_auto.py::TestBaselineFrom` (6 tests) — one-pair MultiIntervalRetestResult emission, interval_s computation, parity-check fail-on-mismatch, identity-criterion threading, output-path writing, mutual exclusion with multi `--interval-s`.
- New `tests/unit/test_cli_retest_auto.py::TestAppendTo` (6 tests) — pairs-count growth, identity-criterion preservation, parity-check fail-on-config-mismatch, sibling `eta-0.json` resolution, distinct `retest-append-` run-id prefix, in-place write-back.
- New `tests/unit/test_retest.py` — 3 `compute_interval_s` tests (basic delta, missing `started_at` → 0, negative delta → 0).
- All 935 tests pass (920 prior + 15 new).

## [0.13.0] — 2026-06-06

**Retest-aware `infereval report`**: §2 of the construct-validity report is restructured into two co-equal `###` subheaded blocks — **Agreement** (cov / κ_C / κ_F / κ_F\*) and **Reliability (R22)** (test-retest κ) — so test-retest reliability sits at the same visual level as agreement, the "co-equal §2 metric" framing the methodology paper has been pointing at. `--retest` auto-detects single (v0.11.0 `RetestResult`) vs multi-interval (v0.12.0 `MultiIntervalRetestResult`) artifact shape and renders accordingly: a single bullet under the Reliability subhead for single-interval (verbatim from v0.12.0), or a per-interval markdown table plus an `Overall verdict` line for multi-interval. The R22 audit cap and negative-findings collection both extend to multi-interval with a **worst-case across pairs** rule: if ANY captured interval is substantively unstable or has undefined κ, the cap fires and the bad pair surfaces as a corpus-level finding (annotated with its interval); per-item flipped findings are pooled across pairs by `item_id`.

### Why the change

v0.11.0 added `retest --auto`. v0.12.0 added multi-interval `--interval-s`, producing `MultiIntervalRetestResult` artifacts with N retest pairs anchored on a common baseline. But the report surface had not caught up:

1. **Test-retest κ was buried as a single bullet** in §2 Summary metrics, rendered after cov / κ_C / κ_F / κ_F\*. The methodology paper treats R22 as a *co-equal* construct-validity dimension to per-evaluation agreement, but the report's visual hierarchy did not reflect that.
2. **`MultiIntervalRetestResult` was invisible to `infereval report`**: `--retest` and `render_markdown()` both assumed the single-`RetestResult` shape; a multi-interval JSON would render as a single broken bullet.
3. **Verdict gating + negative findings had no multi-interval logic.** `compute_verdict()` and `collect_negative_findings()` read `retest_result["test_retest_kappa"]` at the top level — for multi-interval those fields live inside each `pairs[i].retest`. No cap fired, no negative findings emitted.

v0.13.0 closes all three gaps. Additive renderer changes only; no flag changes, no JSON-schema changes.

### Added

- **§2 restructure**: `## 2. Summary metrics` header preserved (anchor `#2-summary-metrics` unchanged). Now contains two `###` subheaded blocks:
  - `### Agreement` — coverage, κ_C, κ_F, κ_F\* (and primary-panel sub-bullet on panelled benchmarks).
  - `### Reliability (R22)` — test-retest κ. When `--retest` is omitted, emits "Not measured (R22 not run for this evaluation)" rather than hiding the subhead.
- **Multi-interval rendering**: `--retest <path>` auto-detects shape via the presence of a `pairs` field. Multi-interval artifacts render a per-interval table (`Interval (s) | Later run | κ vs baseline | Flips | Verdict`) plus an `Overall verdict` line reporting the worst stability across all pairs. Identity-criterion clause rendered once under the subhead (not per row).
- **Worst-case R22 audit cap**: `compute_verdict()`'s existing R22 audit cap (capping verdict at `partially_defensible` when `test_retest_run=True` but the supplied retest is substantively unstable or has undefined κ) now reduces multi-interval artifacts via worst-case across pairs. The mastery claim has to hold at every captured time scale; a clean back-to-back pair does not lift the cap if a later interval drifted.
- **Pooled negative findings for multi-interval**: `collect_negative_findings()` emits one corpus-level finding per non-stable pair (annotated with its interval) and pools per-item flipped findings across pairs by `item_id` (each item is one bullet, annotated with the earliest interval where it flipped). The 50-item cap from v0.11.0 still applies to the pooled set.
- **`_short_stability_label` + `_stability_rank` + `_retest_worst_pair` + `_retest_is_multi_interval` helpers** in `infereval.report` for shape detection, ranking, and worst-case selection. The single-interval / multi-interval dispatch lives in three places (`_render_retest_section`, `compute_verdict`'s R22 branch, `collect_negative_findings`'s retest branch) and is uniform across all three.
- **Bundled demo report**: `experiments/results/stop_sign/retest/report-demo-opus47.md` + `claims-demo.json` — a real-data render against the v0.11.0 opus47 R22 capture, showing the new §2 layout. No new live captures. v0.14.0 will add multi-interval R22 evidence for the bundled demos.

### What did not change

- **Manual-mode `infereval retest <eta_a> <eta_b>`** — untouched.
- **`RetestResult`, `MultiIntervalRetestResult`, `compute_retest`** and the retest CLI surface — untouched.
- **§3 `ReliabilityClaim` rendering** — unchanged. The analyst's `IdentityCriterion` is a one-shot declaration regardless of single vs multi-interval result shape.
- **Single-interval report output** — JSON-schema-stable. The single-bullet `Test-retest κ` line is byte-identical to v0.12.0; the only change in single-interval mode is that it now appears under the new `### Reliability (R22)` parent.
- **All JSON content schemas** — only `framework_version.default` bumps to `0.13.0`.
- **`MetricsReport.to_dict()`** — no retest slot added; retest continues to flow independently into `render_markdown()`.

### Methodological framing

The methodology paper's central claim about R22 — "any cross-family κ comparison without a retest discipline is reporting a point on an unknown distribution" — is now backed by a report surface that gives test-retest reliability the same visual prominence as agreement. The worst-case multi-interval rule makes the methodological commitment concrete: the mastery claim has to hold at every time scale the analyst captured, not just the back-to-back floor. The pulmonology drift result (Gemini 2.5 Pro shifting κ_C by 0.21 across 2.5 weeks, v0.10.0) is the shape this report layout was designed to surface clearly.

### Docs

- `docs/construct_validity.md` — Phase 6 (report rendering) section: §2 restructure description, multi-interval table example, worst-case verdict rule, multi-interval negative-findings pooling rule.
- `docs/interpreting_metrics.md` — new `### R22 — test-retest reliability` subsection alongside `κ_C` / `κ_F` / `κ_F*`, signalling co-equal status with the agreement metrics.
- `CLAUDE.md` — new locked-defaults entry on the retest-aware report (shape auto-detection, §2 subhead layout, worst-case verdict rule, pooled negative findings).
- `README.md` — one-sentence mention in the existing R22 paragraph.
- `experiments/results/stop_sign/retest/README.md` — new "v0.13.0 demo" subsection documenting `report-demo-opus47.md` + `claims-demo.json`.

### Schemas

- `framework_version.default` bumped to `0.13.0`. No content-schema changes.

### Tests

- New `tests/unit/test_report.py::TestMarkdownRendering` (5 tests) — §2 subhead order, single-interval bullet preservation, multi-interval table rendering, no-retest "not measured" bullet, worst-case overall-verdict line.
- New `tests/unit/test_report.py::TestCollectNegativeFindings` (3 tests) — one finding per non-stable pair, per-item pooling across pairs, 50-item cap on pooled set.
- New `tests/unit/test_report_r22.py` (4 tests) — multi-interval audit cap: all-stable does not cap, one substantively-unstable pair caps, one undefined-κ pair caps, worst-case drives cap when back-to-back is clean.
- All 920 tests pass (908 prior + 12 new).

## [0.12.0] — 2026-06-06

**Multi-interval `infereval retest --auto`**: `--interval-s` becomes repeatable. Each invocation adds one cumulative-anchor interval; the framework orchestrates N+1 captures in one CLI call and emits a `MultiIntervalRetestResult` with N retest pairs, all comparing baseline (capture 0) to each later capture. Closes the "we have one across-update data point and one within-session data point; we need more across-update data points" gap from v0.11.0's `stop_sign_2026-06-06.md`.

### Why the change

v0.11.0's stop-sign R22 capture established the within-session reliability floor at zero (all three models κ = +1.000 back-to-back). The companion methodological reading was that v0.10.0's Gemini drift (κ_C dropping 0.21 across 2.5 weeks) is genuinely cross-capture, not sampling noise — but that argument rested on **one** within-session data point and **one** across-update data point. v0.12.0 makes capturing more across-update data points operationally trivial: one CLI call orchestrates baseline + N timed follow-up captures + N anchored retests.

### Added

- **Repeatable `--interval-s` flag** on `infereval retest --auto`. Pass once (default `(0,)`) reproduces v0.11.0 back-to-back single retest, with the same `RetestResult` output JSON shape. Pass N ≥ 2 times → orchestrates N+1 captures and emits a `MultiIntervalRetestResult` with N retest pairs.
- **`MultiIntervalRetestResult` frozen dataclass** in `infereval.retest`. Carries the baseline run id and a tuple of `IntervalPair` (one per non-baseline capture, each embedding a `compute_retest` result against the baseline). Mirrors the existing `RetestResult` shape; serialized via the new `multi_interval_retest_result_to_dict`.
- **`IntervalPair` frozen dataclass** — `(interval_s, run_id, retest)` triple. `interval_s` is the cumulative seconds since the baseline started, not the gap from the previous capture.
- **`--save-etas DIR` multi-interval naming**: writes `eta-0.json` … `eta-N.json` (and matching `.run.jsonl` files) for multi-interval mode. Single-interval mode keeps `eta-a.json` / `eta-b.json` for v0.11.0 backward compatibility.

### Semantics: anchored on baseline, not pairwise-consecutive

`--interval-s 0 --interval-s 86400 --interval-s 604800` produces:

- Capture 0 (baseline)
- Capture 1 (back-to-back) → `compute_retest(baseline, capture-1)` → 1st pair
- 86400s sleep → Capture 2 → `compute_retest(baseline, capture-2)` → 2nd pair
- 604800s sleep → Capture 3 → `compute_retest(baseline, capture-3)` → 3rd pair

Every pair compares back to the same baseline — *cumulative drift since baseline*, not pairwise-adjacent drift. The methodology paper's discussion section can directly cite "κ shifted by X from baseline over interval Y" without conflating baseline drift with sample-pair noise.

### Backward compatibility

- Single-interval calls (default, or `--interval-s 0` once) emit a single `RetestResult` JSON byte-identical to v0.11.0 output. Regression-guarded by an explicit test.
- Manual-mode `infereval retest <eta_a.json> <eta_b.json>` unchanged.
- `--save-etas` directory layout is preserved for single-interval mode (`eta-a` / `eta-b`).

### Methodological framing

R22 evidence at multiple time scales is now operationally one CLI call. The methodology paper's "any cross-family κ comparison without a retest discipline is reporting a point on an unknown distribution" framing can be strengthened: *with multi-interval retest, the distribution can be characterized at the time scales the analyst cares about (back-to-back, day-apart, week-apart), in one orchestrated run.* v0.14.0 will use this to retrofit the bundled pulmonology and stop-sign demos with multi-interval R22 evidence.

### Docs

- `docs/construct_validity.md` — R22 entry gains a v0.12.0 multi-interval sub-paragraph.
- `CLAUDE.md` — new locked-defaults entry on multi-interval semantics and `--save-etas` naming.
- `README.md` — one-sentence mention.

### Schemas

- `framework_version.default` bumped to `0.12.0`. No content-schema changes; no benchmark / evaluation / claims / retest persisted-artifact shape change.

### Tests

- New `tests/unit/test_retest.py::TestMultiIntervalRetestResult` (6 tests) — model construction, serializer round-trip, frozen contract, identity-criterion threading, `__all__` exposure.
- New `tests/unit/test_cli_retest_auto.py::TestMultiInterval` (6 tests) — multi-interval orchestration, single-interval regression guard, `--save-etas` naming convention, `--interval-s` sleep timing, drift-between-captures lowers κ on pair 2, `interval_s` field matches input.
- All 908 tests pass (896 prior + 12 new).

## [0.11.0] — 2026-06-06

**`infereval retest --auto`**: collapses the historical four-step manual R22 workflow (evaluate, evaluate again, retest, optionally thread `--claims`) into one CLI invocation. Adds the bundled stop-sign R22 capture against the 4-item paper-aligned benchmark — backfilling the R22 evidence the v0.5.18 cross-family sweep lacked.

### Why the change

The v0.10.0 pulmonology cross-family rerun produced an unexpected methodological finding: Gemini 2.5 Pro shifted κ_C by **0.21** between captures 2.5 weeks apart with *identical params* (`temperature=0`, `n_samples=3`, same provider/model_id). Two captures of the same panel were enough to demonstrate that **single-capture cross-family numbers are reporting a point on an unknown distribution** — exactly the kind of result the v0.6.0 R22 retest discipline was designed to surface.

But getting test-retest κ today required a three-step manual workflow + optional fourth step for `--claims`. The result: R22 evidence was missing from every captured run in `experiments/results/` despite being load-bearing for any cross-family interpretation. v0.11.0 makes it one CLI call so the discipline can be made routine.

### Added

- **`infereval retest --auto` flag** on the existing retest command. In auto mode, takes `--benchmark / --provider / --model` plus the evaluate-shared parameter flags (`--n-samples / --temperature / --max-tokens / --top-p / --seed / --tie-break / --strip-tex / --http-referer / --x-title / --paraphrase-variant`) plus two retest-specific flags:
  - `--interval-s N` — wall-clock seconds to sleep between the two captures. Default `0` (back-to-back) captures provider-side stochasticity + sampling noise; larger values capture caching effects, silent server-side updates, and longer-term drift.
  - `--save-etas DIR` — persist both `eta-{a,b}.json` + `eta-{a,b}.run.jsonl` for audit-grade reproducibility. Default writes to a tmpdir which is removed after the retest is computed.
- **Auto-mode internals**: builds one provider client and reuses it for both captures (models the realistic "same client, two requests" shape); calls `infereval.evaluation.evaluate` programmatically (no subprocess); threads the two `Evaluation` objects through the unchanged `compute_retest`. Run ids auto-generated per capture (`f"retest-auto-{uuid4hex8}-{a,b}"`) so the two captures are stably distinguishable in logs.
- **Argument-shape validation**: `--auto` + positional eta paths is a `UsageError`; `--auto` without `--benchmark/--provider/--model` is a `UsageError`; manual mode without eta paths is a `UsageError`. All three fail fast with clear messages.
- **Seed handling**: no seed by default — the point of retest is to surface stochastic spread. Supplying `--seed N` pins both captures to the same RNG state, which on seed-honoring providers (OpenAI) collapses spread to zero — useful for pipeline validation only.
- **Bundled stop-sign R22 capture** at `experiments/results/stop_sign/retest/`. Three representative models (Claude Opus 4.7, GPT-4.1, Gemini 2.5 Pro), one per family. Per-model: 2 etas + 2 run.jsonl files + 1 RetestResult JSON. Generated by `experiments/scripts/stop_sign_r22_captures.sh`. ~72 LLM calls total (under US$1).
- **`experiments/scripts/stop_sign_r22_captures.sh`** — reproducible R22 capture harness for the stop-sign benchmark. Same shape as `rerun_pulmonology_cross_family.sh`: per-provider env-var checks, accumulated success/failure summary.
- **Refreshed stop-sign analysis** at `experiments/results/stop_sign_2026-06-06.md` — R22 retest table + R12 under-powered decomposition rendering (the v0.8.0 fix applied to the v0.5.18 cross-family findings, which were the canonical small-n case). The paraphrase-axis findings from `stop_sign_2026-05-18.md` remain valid; that file gains a snapshot caveat pointing at the new analysis.

### Changed

- **Backward-compatible CLI**: the manual-mode `infereval retest <eta_a.json> <eta_b.json>` call signature is unchanged. Existing scripts continue to work.

### Docs

- `docs/construct_validity.md` — R22 entry gains a v0.11.0 auto-mode sub-paragraph cross-referencing the pulmonology rerun's motivating finding.
- `CLAUDE.md` — new locked-defaults entry on the auto-mode shape, no-seed default, and the bundled stop-sign R22 capture.
- `README.md` — one-paragraph mention of `--auto` in the quickstart section.

### Methodological framing

R22 was elevated in v0.6.0 from "important hygiene" to "verdict-gating at scope ≥ `domain_D_as_sampled`". v0.11.0 lowers the operational cost of satisfying it from four CLI calls to one — and the v0.10.0 evidence (Gemini's 0.21 κ_C drift) argues for treating it as **load-bearing for any cross-family κ comparison**, not optional. Any model-vs-model number without retest evidence is reporting a single draw from an unknown distribution.

### Schemas

- `framework_version.default` bumped to `0.11.0`. No content-schema changes; no benchmark / evaluation / claims / retest persisted-artifact shape change.

### Tests

- New `tests/unit/test_cli_retest.py` (5 tests) — backfills the manual-mode CLI coverage the codebase was missing.
- New `tests/unit/test_cli_retest_auto.py` (8 tests) — argument-shape validation, happy paths, `--save-etas`, `--interval-s`, provider-error handling.
- All 896 tests pass (883 prior + 13 new).

## [0.10.0] — 2026-06-06

**Pulmonology demonstration benchmark bumped to v0.2** (30 items, n added: `x3` = ARDS + sepsis → elevated BNP). Cross-family evaluations refreshed against the 30-item shape; v0.1 capture archived. No library code surface changes.

### Why the change

The bundled pulmonology demonstration benchmark was a clean 29 items. The cross-cutting family already had an `x3`-shaped gap in its id sequence (x1, x2, x4, x5, x6, x7, x8) where an earlier marker-inference probe had been left vacant. Rounding up to 30 items by filling that slot lets the demo present a cleaner numeric story *and* extends the cross-cutting marker-inference probe family in a methodologically symmetric way: now both T1- and T2-side marker rules have a dialectical-medium probe targeting a known confounder.

### Added

- **`x3` item**: ARDS + sepsis → elevated BNP (`["cross-cutting", "marker-inference", "dialectical-medium"]`). Placeholder verdict `bad` with a FLAG FOR PULMONOLOGIST REVIEW reference noting the sepsis-induced-cardiomyopathy confounder. Cites Charpentier 2004 (Crit Care Med 32(3):660–665). Slots in between `x2` (ARDS → BNP, BAD) and `x4` (CPE + Kerley B + ↓LVEF → BNP, GOOD).
- **Benchmark id bumped**: `pulmonary-edema-differential-v0.1` → `pulmonary-edema-differential-v0.2`. The benchmark hash changes accordingly; downstream consumers pinning by id are explicitly signalled to refresh their captured evaluations.
- **Six refreshed cross-family evaluations** at `experiments/results/pulmonology/` against benchmark v0.2: GPT-4.1, GPT-5.5, Claude Opus 4.7, DeepSeek v4-pro, Gemini 2.5 Pro, Qwen3-max. Same provider + model_id combinations as the v0.1 capture, same `n_samples=3 / max_tokens=1024 / T=0.0` parameters — comparable to the archived v0.1 etas modulo benchmark version.
- **`experiments/scripts/rerun_pulmonology_cross_family.sh`**: reproducible cross-family rerun script. Mirrors the v0.1 capture for diff-of-runs analysis.
- **`experiments/results/pulmonology_2026-06-06.md`**: refreshed cross-family analysis against benchmark v0.2.

### Changed

- `examples/pulmonary_edema/README.md`: item count 29 → 30; added `x3` to the `FLAG FOR PULMONOLOGIST REVIEW` paragraph alongside `a9`.
- `docs/construct_validity.md`: pulmonology demo cross-reference 29 → 30 items.
- `tests/unit/test_cli_describe.py`: updated `cross-cutting (N items)` assertion 7 → 8.

### Preserved

- `experiments/results/pulmonology/archive-29-items-v0.1/`: the six v0.1 etas + run.jsonl files. They remain tied to benchmark id `pulmonary-edema-differential-v0.1` and a different `benchmark_hash`; useful for longitudinal comparison once the v0.2 reruns settle. See the directory's README for re-analysis instructions.
- `experiments/results/pulmonology_2026-05-19.md`: original v0.1 analysis, retained with a snapshot caveat at the top noting v0.10.0 supersedes it for the bundled demo.

### Schemas

- `framework_version.default` in `evaluation.schema.json` bumped to `0.10.0`. No content-schema changes; no benchmark / evaluation / claims / retest persisted-artifact shape change.

### Library code surface

Unchanged. v0.10.0 is a bundled-asset release (benchmark + experimental artifacts + rerun script + analysis) on top of v0.9.2's code surface. `pip install --upgrade infereval` brings down the 30-item bundled benchmark; everything else is identical to v0.9.2.

## [0.9.2] — 2026-06-03

**Bug fix**: shorten the Google Forms / SurveyMonkey question titles so CSV column headers are scannable.

### Why the change

Reported in conversation (with screenshot) immediately after v0.9.1: when a generated Google Form's responses are routed to a Google Sheet, each *column header* in the Sheet is the literal question title — and v0.9.0 / v0.9.1 put the entire premises-and-conclusion prompt into the question title. Result: column headers running to 200+ characters of medical prose, painful to filter, sort, or paste into anything else. SurveyMonkey had the same problem because its CSV export also uses the question title as the column header.

### Fix

- **Google Forms** (`build_gas_script`): the full prompt now lives in the **PageBreak's `setHelpText`** (section description); the MC question title is short — `"Item N verdict"` — so the linked-Sheet column header is `"Item N verdict"`. Same for rationales: title is `"Item N rationale (optional)"`, with the optional-rationale guidance prose in the question's helpText.
- **SurveyMonkey** (`build_surveymonkey_payload`): restructured the payload from one items-page to **one page per item**. The full prompt lives in the page's `description` field; question titles are `"Item N verdict"` / `"Item N rationale (optional)"`. Randomization promoted from `presentation_options.randomize_questions` on the items page to a top-level `page_randomization` block that skips the Welcome page.
- **Importers** (`google_forms_csv`, `surveymonkey_csv`): primary anchor regex is now `^Item (\d+) verdict\b`. The v0.9.1 anchor `^Item (\d+) of \d+` is preserved as a *secondary* fallback, and the v0.9.0 `[item:<tag>]` regex remains as a tertiary fallback. CSVs from v0.9.0-, v0.9.1-, and v0.9.2+-generated forms all import.

### Backward compatibility

- CSVs from v0.9.1-generated forms import via the secondary anchor fallback (`^Item N of M`). A new regression-guard fixture at `tests/fixtures/google_forms/responses_v0_9_1_legacy.csv` + matching test asserts this.
- CSVs from v0.9.0-generated forms continue to import via the tertiary `[item:<tag>]` regex (unchanged from v0.9.1).
- Python API callers passing `parse_*_csv(path)` without `mapping=` still work (tertiary fallback fires).

### Qualtrics unaffected

Qualtrics's CSV column headers are the `DataExportTag`, not the question title, so v0.9.0/v0.9.1 Qualtrics surveys already produced clean column headers. Visual cleanup of the in-survey Qualtrics layout (moving the prompt into a section description) is a possible future improvement but not a v0.9.2 fix.

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
