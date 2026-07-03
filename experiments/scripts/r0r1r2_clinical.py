"""R0/R1/R2 question-form × rendering evaluation (generalization brief §10.1).

Runs the same single-succedent (|Δ|=1) items three ways, with sampler config and
model snapshot pinned identically across all three (§12.1):

    R0  support  / plain   — the legacy support question, framework-plain surface
    R1  coherence / plain   — the bilateral coherence question, framework-plain
    R2  coherence / domain  — the coherence question, clinical (domain) template

R0→R1 isolates the **question-form** effect; R1→R2 isolates the **rendering**
(template-equivalence) effect. Both are read as cross-run agreement
(:mod:`infereval.comparison`) — there is no ground-truth key.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/r0r1r2_clinical.py \
        --provider anthropic --model claude-opus-4-7 --key-env ANTHROPIC_API_KEY \
        --n-samples 8 --out experiments/results/clinical_pilot/r0r1r2_<date>

Keys are read from the environment; never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.comparison import compare_runs
from infereval.evaluation import EndorsementConfig, ProviderParams, evaluate
from infereval.prompts import DEFAULT_VERIFICATION_PROMPT
from infereval.providers import get_provider
from infereval.templates import DefaultTemplate

# The R2 domain template lives in the library since the 2026-07-02 capture
# promoted it (same id, byte-identical wording — provenance carries over).
from infereval.templates_clinical import ClinicalTemplate

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"

_OPENROUTER_EXTRAS = {
    "http_referer": "https://allen.is/infereval",
    "x_title": "infereval",
}


def _single_succedent(benchmark: Benchmark) -> Benchmark:
    """Restrict to |Δ|=1 items (R0 support is defined only there)."""
    items = [it for it in benchmark.items if len(it.conclusions) == 1]
    return benchmark.model_copy(update={"items": items})


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    p.add_argument("--model", required=True, help="Provider-specific model id (a pinned snapshot)")
    p.add_argument("--key-env", required=True, help="Env var holding the API key")
    p.add_argument("--n-samples", type=int, default=8)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=16)
    args = p.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        print(f"ERROR: {args.key_env} is not set in the environment.", file=sys.stderr)
        return 1

    extras = dict(_OPENROUTER_EXTRAS) if args.provider == "openrouter" else {}
    provider = get_provider(args.provider, args.model, api_key=api_key, **extras)

    bench = _single_succedent(Benchmark.load(BENCHMARK))
    params = ProviderParams(temperature=0.0, max_tokens=args.max_tokens, seed=7)
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"R0/R1/R2 on {bench.n} single-succedent items, {args.n_samples} samples each.")

    runs = {
        "R0-support-plain": dict(
            config=EndorsementConfig(n_samples=args.n_samples, question_form="support"),
            verification_prompt=DEFAULT_VERIFICATION_PROMPT,
            template=None,
        ),
        "R1-coherence-plain": dict(
            config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
            verification_prompt=None,
            template=DefaultTemplate(),
        ),
        "R2-coherence-domain": dict(
            config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
            verification_prompt=None,
            template=ClinicalTemplate(),
        ),
    }

    etas = {}
    for label, kw in runs.items():
        print(f"  running {label} ...", flush=True)
        eta = evaluate(
            bench,
            provider,
            config=kw["config"],
            params=params,
            verification_prompt=kw["verification_prompt"],
            template=kw["template"],
            run_id=f"{args.model}:{label}",
            log_path=args.out / f"{label}.jsonl",
        )
        eta.dump(args.out / f"{label}-eta.json")
        etas[label] = eta

    # Cross-run comparisons: R0→R1 (question form), R1→R2 (rendering).
    comparisons = {
        "R0_to_R1_question_form": compare_runs(etas["R0-support-plain"], etas["R1-coherence-plain"]),
        "R1_to_R2_rendering": compare_runs(etas["R1-coherence-plain"], etas["R2-coherence-domain"]),
    }
    summary = {
        "model": args.model,
        "provider": args.provider,
        "n_items": bench.n,
        "n_samples": args.n_samples,
        "comparisons": {
            k: {
                "cross_run_kappa": c.cross_run_kappa,
                "mean_tv_distance": c.mean_tv_distance,
                "n_both_substantive": c.n_both_substantive,
                "coverage_a": c.coverage_a,
                "coverage_b": c.coverage_b,
                "insufficient_overlap": c.insufficient_overlap,
            }
            for k, c in comparisons.items()
        },
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
