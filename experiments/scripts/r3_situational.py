"""R3: domain-general *situational* rendering — follow-up to the R0/R1/R2 capture.

The R0/R1/R2 run (experiments/results/clinical_pilot/r0r1r2_2026-07-02/) found
the domain (patient-framed) template recovers 4 of the 5 question-form verdict
flips relative to the plain framework template. This follow-up separates the two
candidate ingredients of that recovery:

- **situational framing** — the premises presented as jointly realized in one
  concrete context, with the denial indexed to that same context; vs
- **domain lexicon** — the clinical vocabulary ("patient", "clinical picture").

``SituationalTemplate`` keeps the first and drops the second: fully
domain-general, context-indexical wording ("You are presented with a situation
in which ..."). It obeys the template contract (branches only on arity; never
sees bearer ids).

Runs two cells with the same pinned setup as the R0/R1/R2 capture:

    R1b  coherence / plain        — drift anchor (re-run of R1, hours later)
    R3   coherence / situational  — the domain-general candidate

and compares against the morning etas: R1↔R1b isolates temporal drift; R1b↔R3
the situational-rendering effect; R3↔R2 the residual domain-lexicon effect.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/r3_situational.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --baseline experiments/results/clinical_pilot/r0r1r2_2026-07-02 \
        --out experiments/results/clinical_pilot/r3_situational_2026-07-02
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
from infereval.providers import get_provider
from infereval.templates import DefaultTemplate, VerdictRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"


class SituationalTemplate:
    """Domain-general, context-indexical rendering of the bilateral position.

    The commit-set is presented as one concrete situation; the deny-set is
    indexed to *that same situation*. No domain lexicon anywhere — the wording
    works unchanged for a clinical, legal, or linguistic vocabulary.
    """

    id = "situational-generic-v1"

    def render(self, req: VerdictRequest) -> str:
        gamma = req.gamma_ctx
        if req.arity == 0:
            return (
                "Consider whether there could be a single situation in which all "
                f"of the following hold at once: {gamma}."
            )
        if req.arity == 1:
            return (
                "You are presented with a situation in which the following "
                f"holds: {gamma}. The position under evaluation denies that, in "
                f"this situation, {req.delta_ctx[0]}."
            )
        joined = "; ".join(req.delta_ctx)
        return (
            "You are presented with a situation in which the following holds: "
            f"{gamma}. The position under evaluation denies every one of the "
            f"following about this situation: {joined}."
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
    p.add_argument("--baseline", type=Path, required=True,
                   help="Directory holding the morning R0/R1/R2 etas")
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

    runs = {
        "R1b-coherence-plain": DefaultTemplate(),
        "R3-coherence-situational": SituationalTemplate(),
    }
    etas: dict[str, Evaluation] = {}
    for label, template in runs.items():
        print(f"  running {label} ...", flush=True)
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
            params=params,
            template=template,
            run_id=f"{args.model}:{label}",
            log_path=args.out / f"{label}.jsonl",
        )
        eta.dump(args.out / f"{label}-eta.json")
        etas[label] = eta

    r1 = Evaluation.load(args.baseline / "R1-coherence-plain-eta.json")
    r2 = Evaluation.load(args.baseline / "R2-coherence-domain-eta.json")
    r0 = Evaluation.load(args.baseline / "R0-support-plain-eta.json")
    r1b, r3 = etas["R1b-coherence-plain"], etas["R3-coherence-situational"]

    comparisons = {
        "R1_to_R1b_drift_anchor": compare_runs(r1, r1b),
        "R1b_to_R3_situational_effect": compare_runs(r1b, r3),
        "R3_to_R2_residual_domain_lexicon": compare_runs(r3, r2),
        "R0_to_R3_net_vs_legacy": compare_runs(r0, r3),
    }
    summary = {
        "model": args.model,
        "n_samples": args.n_samples,
        "comparisons": {k: _cmp_dict(c) for k, c in comparisons.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
