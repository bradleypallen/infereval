# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository contents

This repository is the **`infereval`** Python package (`src/infereval/`) — an executable implementation of the methodology specified in *Note on Simonelli's Stop Sign Dialogue: An Implication-Space Instrument for Probing LLM Endorsement of Material Inferential Rules* (Bradley P. Allen, University of Amsterdam). Distributed on PyPI as `infereval`.

The paper is the normative spec; this package is its executable companion. **The paper source is maintained separately** — it was extracted (with full history) into its own repository. This repo began as a combined paper+package repository seeded from an Overleaf import; the package outgrew the paper and was split off under the package's own name. Definition / Section / Remark references throughout the code and docs cite that paper symbolically (no in-repo file).

**Documentation map** (`docs/`):

The docs render as a live MkDocs Material site at **<https://www.bradleypallen.org/infereval/>** (deployed from `main` via `.github/workflows/docs.yml`). Source pages:

- `docs/README.md` — GitHub-folder index (also rendered as the site's home).
- `docs/concepts.md` — methodology mental model (pedagogical complement to the paper, §3–4).
- `docs/authoring_benchmarks.md` — writing a `benchmark.json` for a new domain.
- `docs/interpreting_metrics.md` — reading κ_C / κ_F / κ_F\* output, by-tag and factor-effects decompositions, sensitivity-sweep verdicts.
- `docs/providers.md` — per-provider quirks (Anthropic seed ignore, DeepSeek silent reasoning tokens, etc.).
- `docs/construct_validity.md` — single source of truth for the construct-validity methodology: the R1–R22 requirements catalogue, how the framework supports each, the end-to-end workflow, and the disposition the instrument embodies. (Consolidated from the former `construct_validity_workflow.md` + `closing_the_construct_validity_gap.md` pair in v0.6.0; the docs there now present the methodology as a coherent integrated whole, without version-by-version history markers.)
- `docs/architecture.md` — Mermaid dataflow diagram (analyst → β → η → analytical commands → report) with a layer-by-layer tour.
- `docs/glossary.md` — every paper symbol (B, δ, ctx_Γ, ctx_Δ, E_M, β, η, κ_C, κ_F, κ_F\*, RSR, …) with its in-code counterpart and a one-liner. The analyst-vs-annotator distinction lives here.
- `docs/schemas.md` — hand-written field-table reference for `benchmark.schema.json` + `evaluation.schema.json`, including cross-field validation rules.
- `docs/api.md` — auto-rendered API reference (mkdocstrings) for every public symbol.
- `docs/tutorials/*.ipynb` — four runnable Jupyter notebooks (quickstart, authoring, paraphrase-axis, pulmonology visualization). All run without API keys via the bundled `ReplayProvider` fixture; rendered inline on the site by `mkdocs-jupyter`.

The site has a custom domain (`www.bradleypallen.org` is the user's user-Pages custom domain, so project pages redirect there from `bradleypallen.github.io/infereval/`). Always link the `www.bradleypallen.org/infereval/` URL directly — the github.io redirect can lag HTTPS enforcement.

## Build & run

The paper lives in a separate repository (see "Repository contents"); this repo builds and tests the Python package only.

### Package

Editable install with dev tools:

```
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Optional extras:

- `[anthropic]` — Anthropic SDK
- `[openai]` — OpenAI SDK (also covers OpenRouter — OpenAI-API-compatible)
- `[stats]` — `statsmodels` for `infereval model` (factor-effects logistic regression, added in v0.4.1)
- `[docs]` — `mkdocs`, `mkdocs-material`, `mkdocstrings[python]`, `mkdocs-jupyter`. Install when working on the docs site; `mkdocs build` / `mkdocs serve` need these.
- `[all]` — union of the three provider/stats extras above (does **not** include `[docs]`)
- `[dev]` — the three provider/stats extras + pytest, pytest-cov, ruff, mypy, build, twine. Does **not** include `[docs]` — install `[dev,docs]` when working on both code and the site.

Run tests:

```
pytest
```

CLI sanity check:

```
infereval --version
```

Live-provider tests (opt-in) require `RUN_LIVE_PROVIDER_TESTS=1` and the relevant API key in env.

## Paper conventions (the paper is maintained separately)

The paper source lives in its own repository now; its LaTeX-authoring conventions (document class, theorem environments, commented-out material, `\cite` keys) travel with it and are not reproduced here. What remains below is the **code/paper contract** — the notation, core claim, and methodological trajectory the package must keep faithful to the spec. Treat these as invariants when editing the package.

- **Methodological lineage:** the paper builds on Hlobil & Brandom (2025) machinery (implication frames, Containment, RSR, NMMS, ≈, implicational roles, conceptual content, Corollary 77) and formalizes Simonelli's (2026) stop-sign dialogue. The code tracks these without restating their definitions.
- **Notation invariants — keep stable across paper and code:**
  - $B$ — bearer set; $V$ vocabulary, $L = V^*$ token sequences
  - $\langle B, I \rangle$ / $\langle B, I_M \rangle$ — implication frame / derived from $M$
  - $\delta : B \to L$ — analyst-supplied expression function
  - $\mathrm{ctx}_\Gamma, \mathrm{ctx}_\Delta : \wp(B) \to L$ — analyst-supplied context construction
  - $E_M(\langle\Gamma,\Delta\rangle) \in \{\text{good}, \text{bad}, \text{abstain}\}$ — endorsement verdict
  - $\beta$ — benchmark; $\eta$ — evaluation; $V_i = (v_{i,1},\ldots,v_{i,m})$ — analyst verdict tuple; $c_i$ — analyst consensus
  - $\mathrm{cov}, \mathrm{cov}_j$ — coverage; $S$ — substantive index
  - $\kappa_C$ — Cohen's kappa; $\kappa_F$ — Fleiss' kappa with $M$ as $(m+1)$th annotator; $\kappa_F^*$ — inter-analyst Fleiss baseline
  - $\mathrm{RSR}$ — range of subjunctive robustness
  - **analyst** = human labeler; **annotator** = human-plus-$M$ ensemble. Load-bearing in the Fleiss definition — preserve it in code and prose.
- **Core claim:** $\langle B, I_M \rangle$ obeys Containment by construction via clause (i) of the paper's Definition 3 — implemented as the lazy membership rule in `frame.py`. Changes to the derived-frame membership logic must preserve clause (i).
- **Trajectory:** formalization of Simonelli's stop-sign dialogue → general inferentialist evaluation methodology (binary classification with abstention, scored by coverage + Cohen's/Fleiss' kappa) → carving-relativity of content-attribution, evaluative vs. generative behavior, two axes of variation, and the carving-indexed form of in-principle claims. This arc is the package's reason for existing; preserve it when restructuring.

## Python package conventions

- **Package layout:** `src/infereval/` (src-layout). Top-level modules:
  - **Core (0.1.0):** `types`, `frame`, `benchmark`, `evaluation`, `endorsement`, `context`, `prompts`, `metrics`, `logging_setup`, `providers/`, `schemas/`, `cli/`.
  - **Construct-validity analytical extensions (0.4.x):** `structure` (Phase 2.1, R13), `modeling` (Phase 2.2, R10), `sweep` (Phase 2.3, R11), `report` (Phase 3, R16–R21).
  - **CLI subcommands** in `cli/`: `validate_cmd`, `describe_cmd`, `evaluate_cmd`, `metrics_cmd`, `structure_cmd` (0.4.0), `model_cmd` (0.4.1), `sweep_cmd` (0.4.2), `report_cmd` (0.5.0).
- **Code names track paper symbols:** `Verdict` enum (`GOOD`/`BAD`/`ABSTAIN`), `Bearer`, `Implication`, `DerivedFrame`, `Benchmark`/`Evaluation` (Pydantic for JSON I/O), `endorse()` (the function that computes $E_M$, in `infereval.endorsement`), `cohens_kappa`, `fleiss_kappa`, `inter_analyst_fleiss`. The analyst/annotator distinction lives in `fleiss_kappa` (annotators = m + 1) vs `inter_analyst_fleiss` (analysts = m). Construct-validity additions: `Panel`, `inter_analyst_fleiss_per_panel`, `cross_panel_kappa` (0.3.3), `FactorEffect` / `ModelFit` (0.4.1), `SweepResult` with `stability_verdict` (0.4.2), `StructureReport` (0.4.0), `ConstructValidityClaims` / `ReportVerdict` (0.5.0), `collect_negative_findings` (0.5.1).
- **Build:** `hatchling`. Single-source version at `src/infereval/__init__.py:__version__`.
- **Python:** `>=3.10`. Strict mypy. `statsmodels` / `pandas` imports require `# type: ignore[import-untyped]`.
- **Lint:** `ruff` (E, F, I, B, UP, N, SIM; line-length 100). Statistical conventions that violate ruff N (e.g. `X` for a design matrix) get an inline `# noqa: N806 -- statistical convention` comment.

## Locked methodology defaults (settled in conversation)

These are framework defaults, overridable per evaluation:

- **Package name:** `infereval` (PyPI distribution + import).
- **License:** MIT.
- **Verification prompt:** fresh `default-v1` template (GOOD/BAD/ABSTAIN tokens with brief glosses). Follows `allen2025nesy` methodology but is not a literal quote.
- **`n_samples`:** 5 (odd, clean 3-way majority).
- **`max_tokens`:** 1024 at both the Python API (`ProviderParams.max_tokens`) and the CLI (`--max-tokens`). Aligned in v0.5.2 — earlier CLI default of 32 was a holdover that silently budget-clipped reasoning models. Bump to 2048–4096 for `o1-pro` / `o3-pro` / `qwen3-max-thinking` and other heavy-reasoning variants.
- **Verdict-audit caps (v0.5.3):** `compute_verdict` is *not* a function of the claims file alone — it consults the structure report and the benchmark. Two audit rules cap the verdict at `partially_defensible`: any structural anomaly in a check marked `_run=True` ("ran but did not pass"), and `m < 2` analysts at `items_in_benchmark` scope ("no inter-analyst baseline to certify against"). Future analytical checks that produce artifacts should follow the same pattern: thread the artifact into `compute_verdict` and cap when the artifact reveals the check didn't pass.
- **Tie-break:** `abstain` (matches paper's treatment of abstain as safe fallback). Configurable: `abstain` / `good` / `bad` / `first`.
- **$\delta$ / $\mathrm{ctx}_\Gamma$ / $\mathrm{ctx}_\Delta$ placement:** both JSON template form (default) and Python plugin form (escape hatch).
- **TeX in `expression` strings:** **strip TeX-math `$...$` delimiters at prompt construction time.** Expressions stay LaTeX-source-friendly in benchmark JSON; prompts see the de-TeX'd form.
- **Concurrency:** sequential by default; no `--workers` flag ships yet. Async / batched provider calls and bootstrap CIs on metrics remain unshipped — both are tracked but not yet scheduled.
- **Cohen's kappa default reference:** consensus $c_i$. Override with `--reference analyst:<id>`.
- **Logging:** stdlib `logging` + JSONL formatter (zero-dep, grep/jq friendly).
- **OpenAI SDK surface:** Chat Completions (max OpenRouter coverage).
- **OpenRouter:** thin subclass of `OpenAIProvider` overriding `base_url`.
- **$\kappa_F^*$ in CLI output:** always shown ("undefined" per paper's Remark 4 when $m<2$ or unanimous).
- **$\kappa_F^*$ scope on panelled benchmarks (v0.7.0+):** `inter_analyst_fleiss(benchmark)` computes Fleiss' kappa over the **full** analyst pool whose verdicts the benchmark records — *not* the primary panel only, which was the v0.3.3–v0.6.x silent default. Panels are an additive convergent-validity device: `inter_analyst_fleiss_per_panel` provides the per-panel breakdown and `cross_panel_kappa` provides the cross-panel agreement metric, both alongside the headline all-analyst κ_F\*. The construct-validity report's section 2 renders both the headline and the primary-panel sub-figure on panelled benchmarks. The v0.6.x narrowing inflated κ_F\* when the primary panel was internally unanimous (returning +1.0 even when the second panel disagreed on items) — see [issue #82](https://github.com/bradleypallen/infereval/issues/82) for the failure mode that motivated the v0.7.0 default change. Callers who need the pre-0.7.0 value can pass `analyst_indices=bench.analyst_indices_in_panel(bench.resolved_primary_panel())`.
- **Decomposition rendering (v0.8.0+):** cells in `infereval metrics --by-tag` / `--by-rsr-target` render their substantive-n and per-class M / reference verdict counts; cells with substantive-n below `MIN_K_FOR_SUBSAMPLING_CI = 10` carry an `[under-powered: n < 10]` annotation on the κ_C and κ_F lines, and surface as a "Decomposition under-powered (R12)" group in section 4b of `infereval report --by-tag …` / `--by-rsr-target …`. Headline κ_C / κ_F / κ_F\* rendering is unchanged (the headline already has `--ci` for reliability). The κ *value* is still rendered (its *direction* on a small subset can be a diagnostic lead); only the Landis-Koch-style interpretive *label* is gated. See [issue #84](https://github.com/bradleypallen/infereval/issues/84) for the failure mode that motivated the change — the live Haiku M9 example at `docs/interpreting_metrics.md` shows the canonical case.
- **Survey export / import (v0.9.0+):** `infereval survey {export, import} --platform {qualtrics,google_forms,surveymonkey}` is the async-recruitment surface. Shared question template: free-text expertise question at position 0 (not randomized) + one MC per item (Good / Bad / Abstain, force-response) + optional TE rationale per item. Expertise lands on `Analyst.expertise_description` (additive field; pre-v0.9.0 benchmarks validate unchanged); rationales land on the existing `BenchmarkItem.analyst_rationales[j]` (with `""` as the "this analyst gave no reason on this item" sentinel — pre-existing semantics). Item randomization is on by default; honored natively by Qualtrics and SurveyMonkey, a documented no-op on Google Forms (whole-form-only API). Qualtrics emits `.qsf` offline; Google Forms emits `.gs` Apps Script offline; SurveyMonkey requires `SURVEYMONKEY_ACCESS_TOKEN` for the live `POST /v3/surveys` call. CSV importers parse Qualtrics's 3-header-row format, Google Forms' single-header CSV, and SurveyMonkey's 2-header CSV (with optional "Response" second header) via a shared `merge_respondents` that calls through `Benchmark.model_validate` for validation. See [`docs/surveys.md`](docs/surveys.md) and [`src/infereval/survey/`](src/infereval/survey/).
- **R22 retest auto-mode (v0.11.0+):** `infereval retest --auto --benchmark <b> --provider X --model Y [--interval-s N] [--save-etas DIR]` is the canonical capture path. Collapses the historical four-step workflow (evaluate, evaluate again, retest, threading `--claims`) into one CLI call. Internals reuse `infereval.evaluation.evaluate` programmatically; the two captures get auto-generated run ids; results threaded unchanged through `compute_retest`. Default `--interval-s 0` (back-to-back; captures provider-side stochasticity + sampling noise); higher intervals capture caching, silent updates, longer-term drift. No seed by default (the whole point is to surface stochastic spread; supplying `--seed N` on seed-honoring providers collapses spread to zero and is only useful for pipeline validation). `--save-etas DIR` persists both etas + jsonl logs for audit-grade reproducibility; default tmpdir is removed after retest computed. The motivating result: the v0.10.0 pulmonology rerun's 0.21 κ_C drift on Gemini 2.5 Pro across 2.5 weeks with identical params demonstrated that single-capture cross-family numbers are reporting a point on an unknown distribution. The stop-sign 2026-06-06 R22 capture at `experiments/results/stop_sign/retest/` is the bundled minimal-shape demonstration.
- **Multi-interval `--interval-s N` (v0.12.0+):** `--interval-s` is **repeatable**; each invocation adds one cumulative-anchor interval. Pass once (default `(0,)`) reproduces v0.11.0 back-to-back single retest with the same `RetestResult` output JSON shape. Pass N ≥ 2 times → emits `MultiIntervalRetestResult` (one `IntervalPair` per non-baseline capture, all anchored on capture 0; total N+1 captures, total wall time = sum of intervals). Semantics is anchored-on-baseline (not pairwise-consecutive) — the methodology paper's "cumulative drift since baseline" framing. Multi-interval `--save-etas DIR` uses `eta-0.json` … `eta-N.json` naming; single-interval keeps `eta-a.json` / `eta-b.json` for v0.11.0 backward compat. The CLI sleeps in-process, so `--interval-s 86400` requires the CLI process to stay alive 24+ hours; typical use is "back-to-back + minutes/hours" not the multi-day extreme.
- **Schema versioning:** independent of framework (`schema_version: "1.0"`). Schema stability promised from 1.0 onward, not 0.x. **The 0.3.x–0.5.x construct-validity series added optional fields only** — every pre-0.3.0 benchmark continues to validate against the current schema, and that additive-only invariant must be preserved for further benchmark-schema changes within the 1.0 line.
- **`DerivedFrame` materialization:** lazy (membership via Def. 3 iff). Full $I_M$ over $\wp(B)\times\wp(B)$ is unbounded.

## Construct-validity infrastructure (v0.3.0–v0.5.4)

The construct-validity programme addresses the R1–R22 requirements catalogued in [`docs/construct_validity.md`](docs/construct_validity.md) (the consolidated methodology doc that replaced the former `construct_validity_workflow.md` + `closing_the_construct_validity_gap.md` pair in v0.6.0). Quick map for future work:

**Optional benchmark schema fields added (all additive):**

| Field | Release | What it enables |
|---|---|---|
| `factors`, `factor_constraints` (benchmark-level) + `factor_levels` (per item) | 0.3.0 | Crossed factorial design with `min_items_per_cell` validation; consumed by `infereval model`. |
| `paraphrases` runtime activation via `--paraphrase-variant K` / `--paraphrase-cycle` | 0.3.1 | Paraphrase-axis robustness becomes a one-flag operation. `paraphrases` field was already permitted in 0.1.0 but ignored at runtime. |
| `construction_metadata` per item (`authored_by`, `authored_on`, `authored_blind_to_models`, `source`) | 0.3.2 | Item-level provenance for held-out / training-data-separation arguments. |
| `analyst.panel` + `benchmark.primary_panel` | 0.3.3 | Reference-panel declaration for cross-panel convergent-validity checks; validator enforces all-or-none on the `panel` field. |
| `factor_kinds` (benchmark-level) | 0.5.3 | Per-factor valence label (`"substantive"` vs `"experimentally_controlled"`). Used by `collect_negative_findings` to render null Wald-test findings with the correct valence — substantive nulls weaken the claim, controlled nulls strengthen it. |
| `analyst_rationales` (per item) | 0.5.4 | Optional `list[str] \| None` of natural-language rationales positionally aligned to `analyst_verdicts`. Propagated through `EvaluationItem` (and therefore covered by `benchmark_hash`). `None` ≠ empty-string entry. The substrate for the deferred disagreement-diagnosis workstream. Metric / structural-check outputs are byte-identical with and without rationales (AR2 regression test). |

**New analytical CLI commands (all consume `eta.json` + `benchmark.json` and feed `infereval report`):**

| Command | Release | What it does |
|---|---|---|
| `infereval structure` | 0.4.0 | Three deterministic checks on the benchmark — Containment, RSR role consistency, base-case stability. Content-validity gate. |
| `infereval model` | 0.4.1 | Logistic regression of per-sample agreement on declared `factors`, item-clustered SEs, per-factor joint Wald tests + per-level coefficients. Requires `[stats]`. |
| `infereval sweep` | 0.4.2 | Re-runs `metrics` across a swept parameter (e.g. `--vary tie_break --values abstain,good,bad`); emits a stability verdict based on κ_C range (`<0.05` stable, `<0.10` moderately sensitive, `≥0.10` substantively variable). |
| `infereval report` | 0.5.0 | Combines claims file + the four analytical outputs into a Markdown report with a deterministic five-tier verdict. Auto-collects negative findings (0.5.1); `--suppress-negatives` downgrades the verdict one tier. v0.5.3 added verdict audit caps (structural anomalies and m<2 cap the verdict at `partially_defensible`) and `factor_kinds` valence labels on negative findings. |

**Notes for future work in this area:**

- The "all four analytical commands feed `report`" pattern is load-bearing — when adding new analytical capabilities, prefer extending one of the existing four or wiring a new one into `collect_negative_findings()` / the report renderer over standing up a sibling CLI surface.
- Construct-validity is **constitutively partial**. Requirements that the source document calls *irreducibly outside the framework* (independent analyst panels, held-out item construction with bona-fide blinding, training-data temporal separation, cross-domain replication, the in-principle interpretive commitments) cannot be moved inside it. The framework can declare and check that an analyst made these commitments; it cannot vet them.
- The deterministic verdict in `report` is a function of declared claims plus measured evidence — never a free-text summary. Any change to the verdict logic must be specified in `compute_verdict()` and tested.

## Working style for this repo

- The paper is in a separate repository; this repo is package-only. If a change touches the methodology spec, coordinate with the paper repo — don't try to edit the paper here.
- Code edits go in `src/infereval/`. Run `pytest` after changes; type-check with `mypy src/infereval/`. The full test suite is ~637 tests and finishes in under 5 seconds.
- The methodology defaults above are locked in conversation. Don't drift from them without checking with the user first.
- Per user-global instruction: **always include structured logging for post-experimental run analysis and reporting.** Every model call, every sample, every majority-vote outcome should be auditable from the JSONL log.
- **Schemas are generated, not hand-edited.** After any change to the Pydantic models in `benchmark.py` or `evaluation.py`, regenerate the committed Draft 2020-12 schemas with `python -c "from infereval.schemas import emit_static_schemas; emit_static_schemas()"`. A drift test keeps these in sync; CI will flag a hand-edit. Version bumps also flow into `evaluation.schema.json:framework_version.default` via the same regeneration step.
- **CI** (three workflows):
  - `.github/workflows/ci.yml` — runs `ruff check src tests`, `mypy src/infereval`, and `pytest -q` on every push to `main` and every PR (Python 3.12). The README "CI" badge tracks it. **Test/lint only** — does not build or publish.
  - `.github/workflows/docs.yml` — runs `mkdocs build` on every push to `main` and every PR; **deploys** the built site to GitHub Pages on push to `main` only. The README "Docs" badge tracks it. Requires Pages source = "GitHub Actions" in repo settings (set; survives indefinitely).
  - `.github/workflows/publish.yml` — builds sdist + wheel (and runs `twine check`), then publishes via PyPI **Trusted Publishing** (OIDC, no tokens in GitHub secrets). Triggers: `release: published` → real PyPI; `workflow_dispatch` with `target: testpypi|pypi` → manual run for TestPyPI rehearsal or a manual PyPI push. Uses GitHub deployment environments named `pypi` and `testpypi`. **One-time prerequisite** before the first run on each index: register a trusted publisher at <https://pypi.org/manage/account/publishing/> and the TestPyPI equivalent, with project name `infereval`, repo `bradleypallen/infereval`, workflow filename `publish.yml`, and environment name `pypi` (or `testpypi`). Without that registration the publish step fails authentication. The publish workflow does **not** re-run lint/test — `ci.yml` already gated the merge commit the tag points at.
- **Release flow** (matches v0.3.0–v0.5.9; v0.5.6 was tagged then retired before publication and is documented as superseded in CHANGELOG; v0.5.7–v0.5.9 were the manual-`twine`-era releases): bump `src/infereval/__init__.py:__version__`, update `CHANGELOG.md` (Keep-a-Changelog format), regenerate schemas, open + rebase-merge a PR, then tag (`git tag -a vX.Y.Z <merge-sha> -m "..."` and `git push origin vX.Y.Z`). From here you have two paths:
  - **Automated path (preferred, requires trusted-publisher registration on PyPI/TestPyPI)**: `gh release create vX.Y.Z --title "..." --notes "..."` — `publish.yml` fires on `release: published`, builds, and uploads to real PyPI. For TestPyPI rehearsal before tagging, fire `gh workflow run publish.yml -f target=testpypi` against the branch under test.
  - **Manual fallback (works without trusted publishers)**: `python -m build && twine upload -r {testpypi,pypi} dist/*`, run from a venv that has `twine` (`[dev]` extras include it). `~/.pypirc` has both `[testpypi]` and `[pypi]` index-servers wired to `__token__` + the respective API tokens, so twine picks them up non-interactively.
  Either path requires the **release-hygiene check** first: inspect the wheel's `METADATA` to confirm `Summary`, `Classifier: Development Status`, and the bundled README are current — including that every link in the bundled README is an absolute `https://...` URL (PyPI does not resolve relative `LICENSE` / `CHANGELOG.md` / `docs/*.md` links the way GitHub does; this is why v0.5.7 → v0.5.8 → v0.5.9 happened in succession, peeling off METADATA framing, then relative `docs/*.md` links, then `LICENSE` / `CHANGELOG.md` / `experiments/...` relative links). For the automated path you can do this locally before tagging (`python -m build` and inspect `dist/*.whl`) or download the workflow's `dist` artifact after the `build` job runs.
- **PR merge style**: rebase-merge via `gh api -X PUT repos/<owner>/<repo>/pulls/<num>/merge -f merge_method=rebase`. Worktree-safe (doesn't require switching the local HEAD).
- **macOS UF_HIDDEN gotcha**: if an editable install seems to disappear from `.venv`, run `chflags -R nohidden .venv` before pytest. Documented in the user's `MEMORY.md`.
