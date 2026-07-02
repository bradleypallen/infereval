"""R4: domain-general *epistemic* rendering — the discriminating follow-up to R3.

R3 (situational-generic wording) diverged sharply from every other
configuration and broke the G-ladder's monotonicity; the working hypothesis is a
closed-world reading ("a situation in which the following holds" ⇒ Γ read as an
exhaustive description, making any denial cheaply coherent). R4 keeps full
domain-generality but makes the openness explicit — **epistemic** framing:

    "Consider a case about which the following has been established: Γ.
     Other facts about the case may be unknown. The position under evaluation
     denies that, in this case, ψ."

If R4 tracks R2 (domain template), generality is recoverable and the framework
default template should adopt epistemic wording; if R4 tracks R3, the domain
lexicon does irreplaceable work and per-domain templates are load-bearing.

Compares R4 against the same-day pinned captures (R0/R1/R2 from the morning run,
R1b/R3 from the midday run).

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/r4_epistemic.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 \
        --r0r1r2 experiments/results/clinical_pilot/r0r1r2_2026-07-02 \
        --r3dir experiments/results/clinical_pilot/r3_situational_2026-07-02 \
        --out experiments/results/clinical_pilot/r4_epistemic_2026-07-02
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
from infereval.templates import VerdictRequest

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"


class EpistemicTemplate:
    """Domain-general, open-world rendering of the bilateral position.

    The commit-set is what has been *established about* a case (explicitly not
    an exhaustive description); the deny-set is indexed to the same case. No
    domain lexicon — works unchanged for clinical, legal, or linguistic
    vocabularies.
    """

    id = "case-open-world-v1"

    def render(self, req: VerdictRequest) -> str:
        gamma = req.gamma_ctx
        if req.arity == 0:
            return (
                "Consider whether there could be a single case in which all of "
                f"the following hold at once: {gamma}."
            )
        if req.arity == 1:
            return (
                "Consider a case about which the following has been "
                f"established: {gamma}. Other facts about the case may be "
                "unknown. The position under evaluation denies that, in this "
                f"case, {req.delta_ctx[0]}."
            )
        joined = "; ".join(req.delta_ctx)
        return (
            "Consider a case about which the following has been established: "
            f"{gamma}. Other facts about the case may be unknown. The position "
            "under evaluation denies every one of the following about this "
            f"case: {joined}."
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
    p.add_argument("--r3dir", type=Path, required=True)
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

    print("  running R4-coherence-epistemic ...", flush=True)
    r4 = evaluate(
        bench,
        provider,
        config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
        params=params,
        template=EpistemicTemplate(),
        run_id=f"{args.model}:R4-coherence-epistemic",
        log_path=args.out / "R4-coherence-epistemic.jsonl",
    )
    r4.dump(args.out / "R4-coherence-epistemic-eta.json")

    r0 = Evaluation.load(args.r0r1r2 / "R0-support-plain-eta.json")
    r2 = Evaluation.load(args.r0r1r2 / "R2-coherence-domain-eta.json")
    r1b = Evaluation.load(args.r3dir / "R1b-coherence-plain-eta.json")
    r3 = Evaluation.load(args.r3dir / "R3-coherence-situational-eta.json")

    comparisons = {
        "R1b_to_R4_epistemic_effect": compare_runs(r1b, r4),
        "R4_to_R2_vs_domain_template": compare_runs(r4, r2),
        "R4_to_R3_vs_situational": compare_runs(r4, r3),
        "R0_to_R4_net_vs_legacy": compare_runs(r0, r4),
    }
    summary = {
        "model": args.model,
        "n_samples": args.n_samples,
        "comparisons": {k: _cmp_dict(c) for k, c in comparisons.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote eta + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
