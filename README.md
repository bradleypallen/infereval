# infereval

[![CI](https://github.com/bradleypallen/infereval/actions/workflows/ci.yml/badge.svg)](https://github.com/bradleypallen/infereval/actions/workflows/ci.yml)
[![Docs](https://github.com/bradleypallen/infereval/actions/workflows/docs.yml/badge.svg)](https://www.bradleypallen.org/infereval/)
[![Release](https://img.shields.io/github/v/release/bradleypallen/infereval)](https://github.com/bradleypallen/infereval/releases)
[![PyPI](https://img.shields.io/pypi/v/infereval)](https://pypi.org/project/infereval/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/bradleypallen/infereval/blob/main/LICENSE)

Inferentialist evaluation of LLMs: derive an implication frame from a language model's endorsement verdicts, then measure the model's agreement with an analyst-labeled benchmark via coverage and Cohen's / Fleiss' kappa. The agreement is **evidence bearing on** an inferential-mastery attribution — not a measurement of mastery itself (per the paper's Remark 8).

`infereval` is the executable companion to *Note on Simonelli's Stop Sign Dialogue: An Implication-Space Instrument for Probing LLM Endorsement of Material Inferential Rules* (Allen, 2026), which is maintained as a separate paper. The framework formalizes the procedure β → η → (cov, κ_C, κ_F, κ_F\*) for any analyst-supplied benchmark.

## Status

Beta (0.x, pre-1.0). The public Python API and CLI surface may shift between minor releases until 1.0. Methodology defaults are locked, and the JSON schemas are versioned independently (`schema_version: "1.0"`) and promised stable from 1.0 onward regardless of the framework version. See the [CHANGELOG](https://github.com/bradleypallen/infereval/blob/main/CHANGELOG.md) for the current release.

## Documentation

The docs site at <https://www.bradleypallen.org/infereval/> covers a [Concepts](https://www.bradleypallen.org/infereval/concepts/) page (methodology mental model), [Authoring benchmarks](https://www.bradleypallen.org/infereval/authoring_benchmarks/), [Interpreting metrics](https://www.bradleypallen.org/infereval/interpreting_metrics/) (κ_C / κ_F / κ_F\*, test-retest κ, decompositions, subsampling CIs, sensitivity sweeps), [Providers](https://www.bradleypallen.org/infereval/providers/) (Anthropic seed handling, DeepSeek reasoning-token budgets, OpenRouter attribution), and [Construct validity of the instrument](https://www.bradleypallen.org/infereval/construct_validity/) — the R1–R22 requirements catalogue and end-to-end workflow in one place. Four executable tutorial notebooks (quickstart, authoring, paraphrase-axis triangulation, pulmonology visualization). Plus an auto-generated [API reference](https://www.bradleypallen.org/infereval/api/), an [Architecture](https://www.bradleypallen.org/infereval/architecture/) dataflow diagram, a [Glossary](https://www.bradleypallen.org/infereval/glossary/) of paper symbols, and a [JSON-schema](https://www.bradleypallen.org/infereval/schemas/) reference.

## Findings

A 13-model cross-family sweep (2026-05-18) of the stop-sign paraphrase-axis experiment is committed at [`experiments/results/stop_sign_2026-05-18.md`](https://github.com/bradleypallen/infereval/blob/main/experiments/results/stop_sign_2026-05-18.md). Headline: 11 of 13 frontier LLMs across six families reproduce Simonelli's analyst row exactly under the original δ(ra) (κ_C = +1.00) — an eleven-model independent replication of the paper's empirical anchor ten months after publication. The two outliers (Claude Haiku 4.5, Mistral Large) default to a *perceptual* reading of `is red` rather than the analyst's *intrinsic* reading, and the framework localizes this to specific (item, δ-variant) cells in the result tables.

## Install

```
pip install infereval
```

Provider SDKs are optional extras (the framework runs without them — use the mock or replay providers):

```
pip install 'infereval[anthropic]'   # Anthropic Claude
pip install 'infereval[openai]'      # OpenAI + OpenRouter (OpenAI-API-compatible)
pip install 'infereval[all]'
```

From source (editable):

```
git clone https://github.com/bradleypallen/infereval
cd infereval
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## 60-second quickstart

Inspect the bundled stop-sign benchmark (Example 1 of the paper), then run an evaluation against the deterministic replay fixture — no API key needed:

```
# 1. Look at the benchmark.
infereval describe examples/stop_sign/benchmark.json

# 2. Validate it against the JSON schema.
infereval validate examples/stop_sign/benchmark.json

# 3. Run a deterministic evaluation against the committed replay fixture.
infereval evaluate examples/stop_sign/benchmark.json \
    --replay-from tests/fixtures/stop_sign_replay.jsonl \
    --output /tmp/eta.json \
    --n-samples 5 \
    --log /tmp/run.jsonl

# 4. Compute metrics.
infereval metrics /tmp/eta.json --benchmark examples/stop_sign/benchmark.json
```

To run against a real model, replace step 3 with:

```
export ANTHROPIC_API_KEY=...
infereval evaluate examples/stop_sign/benchmark.json \
    --provider anthropic --model claude-haiku-4-5-20251001 \
    --output /tmp/eta.json --n-samples 5 --log /tmp/run.jsonl
```

The JSONL run log under `/tmp/run.jsonl` records one event per provider call (prompt hash, raw response, parsed verdict, usage, timing) so the evaluation is auditable end to end.

For the R22 test-retest discipline, `infereval retest --auto --benchmark <b> --provider X --model Y [--interval-s N] [--save-etas DIR]` (v0.11.0+) collapses the four-step manual workflow (evaluate, evaluate again, retest, optionally `--claims`) into one CLI call — runs the same evaluation twice with an optional inter-capture sleep and emits the standard `RetestResult` directly. v0.12.0+ accepts `--interval-s` multiple times for cumulative drift-since-baseline analysis in one orchestrated call. See the [stop-sign R22 capture](experiments/results/stop_sign/retest/) for the worked end-to-end demo.

## What this is and isn't

**This is:** a research tool that formalizes Simonelli's stop-sign dialogue into a repeatable evaluation procedure. Given (i) a bearer set, (ii) expression and context-construction functions, (iii) a benchmark of implications labeled by one or more analysts, the framework drives an LLM through endorsement-probing for each implication and reports the resulting agreement with analyst practice along three axes:

- **Coverage** — how often the model takes a substantive position (`cov(η)`).
- **Cohen's kappa** — agreement against a chosen reference (analyst consensus `c_i` or a single analyst `v_{:,j}`).
- **Fleiss' kappa** — agreement with the model treated as the `(m+1)`th annotator, alongside the inter-analyst baseline `κ_F*(β)` (Remark 4 of the paper).

Each metric can be decomposed by tag or by RSR target.

**This is not:** a factuality benchmark, a leaderboard, or an answer to whether LLMs are sapient. The methodology is *carving-relative*: results depend on the analyst-supplied bearer carving, context construction, and benchmark. The framework provides the machinery; the analyst supplies the practice the machinery is comparing against. See the Discussion in the paper for what carving-relativity buys and costs.

## API surface

```python
from infereval import (
    Verdict, Bearer, Implication,           # core data types
    DerivedFrame,                            # ⟨B, I_M⟩ per Definition 3
)
from infereval.benchmark import Benchmark
from infereval.evaluation import Evaluation, evaluate, EndorsementConfig, ProviderParams
from infereval.providers import get_provider
from infereval.metrics import MetricsReport

bench = Benchmark.load("examples/stop_sign/benchmark.json")
provider = get_provider("anthropic", "claude-haiku-4-5-20251001")
eta = evaluate(bench, provider,
               config=EndorsementConfig(n_samples=5),
               params=ProviderParams(temperature=1.0),
               log_path="/tmp/run.jsonl")
report = MetricsReport(eta=eta, benchmark=bench)
print(report.to_dict())
```

## Locked methodology defaults

These are framework defaults, overridable per evaluation:

| Setting | Default |
|---|---|
| `n_samples` | 5 (odd, clean 3-way majority) |
| Tie-break | `abstain` (configurable: `good`, `bad`, `first`) |
| Verification prompt | `default-v1` (GOOD/BAD/ABSTAIN tokens with brief glosses) |
| TeX in expressions | Stripped at prompt time; LaTeX-source-friendly in benchmark JSON |
| Cohen's kappa reference | Analyst consensus `c_i` (override with `--reference analyst:<id>`) |
| Provider seed | Honored by OpenAI; ignored (with one-time warning) by Anthropic |

See `CLAUDE.md` and the paper for the full list and the rationale behind each choice.

## Development

```
pip install -e '.[dev]'
pytest                                # all unit + replay tests
pytest -m live                        # opt-in live provider tests (requires API keys)
mypy src/infereval
ruff check src tests
```

Live provider tests require `RUN_LIVE_PROVIDER_TESTS=1` and the relevant API key in the environment. They are skipped by default.

## Citation

```bibtex
@unpublished{allen2026inferential,
  author = {Allen, Bradley P.},
  title  = {Note on {S}imonelli's Stop Sign Dialogue: An Implication-Space Instrument for Probing {LLM} Endorsement of Material Inferential Rules},
  year   = {2026},
  note   = {University of Amsterdam}
}
```

## License

MIT — see [LICENSE](https://github.com/bradleypallen/infereval/blob/main/LICENSE).
