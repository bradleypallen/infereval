"""S3/S4: the support-side rendering contrast — is R3/R4 fragility bilateral-specific?

The coherence question collapsed under generic renderings (R3 situational,
R4 epistemic), suggesting rendering selects between a *material* and a *logical*
reading of the bilateral clash. Before concluding anything about bilateralism,
the missing contrast: apply the SAME two rendering perturbations to the
**unilateral support question** ("does the conclusion follow?").

Three cells, one pinned session:

    S0b  support / plain        — drift anchor (re-run of R0's configuration)
    S3   support / situational  — "You are presented with a situation in which
                                   the following holds: Γ. Does it follow that,
                                   in this situation, ψ?"
    S4   support / epistemic    — "Consider a case about which the following has
                                   been established: Γ. Other facts about the
                                   case may be unknown. Does it follow that, in
                                   this case, ψ?"

Read-out against the coherence-side effect sizes (R1b→R3 TV=0.214,
R1b→R4 TV=0.371): if S0b→S3/S4 sit near the drift floor (~0.04), the fragility
is specific to the coherence question and the material/logical account gains an
asymmetry; if they collapse comparably, rendering fragility is a general
property of elicitation and the bilateral form is off the hook.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/s3s4_support_rendering.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 \
        --r0r1r2 experiments/results/clinical_pilot/r0r1r2_2026-07-02 \
        --out experiments/results/clinical_pilot/s3s4_support_2026-07-02
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.comparison import compare_runs
from infereval.evaluation import EndorsementConfig, Evaluation, ProviderParams, evaluate
from infereval.prompts import (
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_VERIFICATION_PROMPT,
    VerificationPrompt,
)
from infereval.providers import get_provider

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"

#: Support question under the R3-style constitutive-situational scaffolding.
SUPPORT_SITUATIONAL = VerificationPrompt(
    id="support-situational-v1",
    system=DEFAULT_SYSTEM_PROMPT,
    user_template=(
        "You are presented with a situation in which the following holds: "
        "{premise_context}.\n"
        "Does it follow that, in this situation, {conclusion_context}?\n"
        "Verdict:"
    ),
)

#: Support question under the R4-style open-world epistemic scaffolding.
SUPPORT_EPISTEMIC = VerificationPrompt(
    id="support-epistemic-v1",
    system=DEFAULT_SYSTEM_PROMPT,
    user_template=(
        "Consider a case about which the following has been established: "
        "{premise_context}. Other facts about the case may be unknown.\n"
        "Does it follow that, in this case, {conclusion_context}?\n"
        "Verdict:"
    ),
)


def _single_succedent(benchmark: Benchmark) -> Benchmark:
    items = [it for it in benchmark.items if len(it.conclusions) == 1]
    return benchmark.model_copy(update={"items": items})


def _cmp_dict(c) -> dict:
    return {
        "cross_run_kappa": c.cross_run_kappa,
        "mean_tv_distance": c.mean_tv_distance,
        "n_both_substantive": c.n_both_substantive,
        "coverage_a": c.coverage_a,
        "coverage_b": c.coverage_b,
        "insufficient_overlap": c.insufficient_overlap,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", required=True)
    p.add_argument("--n-samples", type=int, default=6)
    p.add_argument("--r0r1r2", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=16)
    args = p.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        print(f"ERROR: {args.key_env} is not set.", file=sys.stderr)
        return 1

    provider = get_provider(args.provider, args.model, api_key=api_key)
    bench = _single_succedent(Benchmark.load(BENCHMARK))
    params = ProviderParams(temperature=0.0, max_tokens=args.max_tokens, seed=7)
    args.out.mkdir(parents=True, exist_ok=True)

    cells = {
        "S0b-support-plain": DEFAULT_VERIFICATION_PROMPT,
        "S3-support-situational": SUPPORT_SITUATIONAL,
        "S4-support-epistemic": SUPPORT_EPISTEMIC,
    }
    etas: dict[str, Evaluation] = {}
    for label, vp in cells.items():
        print(f"  running {label} ...", flush=True)
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=args.n_samples, question_form="support"),
            params=params,
            verification_prompt=vp,
            run_id=f"{args.model}:{label}",
            log_path=args.out / f"{label}.jsonl",
        )
        eta.dump(args.out / f"{label}-eta.json")
        etas[label] = eta

    r0 = Evaluation.load(args.r0r1r2 / "R0-support-plain-eta.json")
    s0b = etas["S0b-support-plain"]

    comparisons = {
        "R0_to_S0b_drift_anchor": compare_runs(r0, s0b),
        "S0b_to_S3_situational_effect": compare_runs(s0b, etas["S3-support-situational"]),
        "S0b_to_S4_epistemic_effect": compare_runs(s0b, etas["S4-support-epistemic"]),
    }
    summary = {
        "model": args.model,
        "n_samples": args.n_samples,
        "coherence_side_reference": {
            "R1b_to_R3_situational": {"cross_run_kappa": 0.614, "mean_tv_distance": 0.214},
            "R1b_to_R4_epistemic": {"cross_run_kappa": 0.298, "mean_tv_distance": 0.371},
            "drift_floor_R1_to_R1b": {"cross_run_kappa": 0.879, "mean_tv_distance": 0.043},
        },
        "comparisons": {k: _cmp_dict(c) for k, c in comparisons.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
