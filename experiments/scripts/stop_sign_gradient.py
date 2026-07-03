"""Stop-sign rendering-gradient control: is ambient practice strippable?

The clinical R-series showed material judgment collapsing under practice-
stripped renderings (endorsement 22->15->7 under coherence; ladders breaking),
under every frame lexicon. The internalization hypothesis explains the collapse:
the model depends on the prompt to supply the practice. The stop-sign benchmark
is the natural CONTROL — everyday traffic vocabulary is a maximally ambient,
maximally internalized practice (for humans and, via training saturation,
plausibly for the model).

**Prediction (internalization account):** the gradient is FLAT on stop-sign —
the same situational/epistemic perturbations that collapsed the clinical
verdicts leave the stop-sign analyst row (good, good, good, bad) intact,
because rewording cannot strip a practice the model carries internally.
**Falsifier:** if stop-sign collapses too, the fragility is a property of the
elicitation itself, not of practice internalization.

Runs the full 3x3 grid on the 4 stop-sign items, one pinned session:

    frames:     support (GOOD/BAD/ABSTAIN), coherence (COHERENT/INCOHERENT/
                UNCLEAR), normative (OUT-OF-BOUNDS/PERMISSIBLE/UNCLEAR)
    renderings: plain, situational, epistemic
                (byte-identical scaffolding to the clinical program — imported)

With n=4 items the read-out is the per-item verdict grid, not kappa.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/stop_sign_gradient.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --out experiments/results/stop_sign/rendering_gradient_2026-07-02
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, ProviderParams, evaluate
from infereval.prompts import DEFAULT_VERIFICATION_PROMPT
from infereval.providers import get_provider
from infereval.templates import DefaultTemplate

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"

sys.path.insert(0, str(Path(__file__).parent))
from r3_situational import SituationalTemplate  # noqa: E402
from r4_epistemic import EpistemicTemplate  # noqa: E402
from r5_normative import run_normative_cell  # noqa: E402
from s3s4_support_rendering import SUPPORT_EPISTEMIC, SUPPORT_SITUATIONAL  # noqa: E402

RENDERINGS = {
    "plain": DefaultTemplate(),
    "situational": SituationalTemplate(),
    "epistemic": EpistemicTemplate(),
}
SUPPORT_PROMPTS = {
    "plain": DEFAULT_VERIFICATION_PROMPT,
    "situational": SUPPORT_SITUATIONAL,
    "epistemic": SUPPORT_EPISTEMIC,
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", required=True)
    p.add_argument("--n-samples", type=int, default=6)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=16)
    args = p.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        print(f"ERROR: {args.key_env} is not set.", file=sys.stderr)
        return 1

    provider = get_provider(args.provider, args.model, api_key=api_key)
    bench = Benchmark.load(BENCHMARK)
    params = ProviderParams(temperature=0.0, max_tokens=args.max_tokens, seed=7)
    args.out.mkdir(parents=True, exist_ok=True)

    etas = {}
    # Support frame — via verification-prompt overrides (the legacy path).
    for rend, vp in SUPPORT_PROMPTS.items():
        label = f"support-{rend}"
        print(f"  running {label} ...", flush=True)
        eta = evaluate(bench, provider,
                       config=EndorsementConfig(n_samples=args.n_samples, question_form="support"),
                       params=params, verification_prompt=vp,
                       run_id=f"{args.model}:{label}",
                       log_path=args.out / f"{label}.jsonl")
        eta.dump(args.out / f"{label}-eta.json")
        etas[label] = eta
    model_info = etas["support-plain"].model

    # Coherence frame — via the template registry path.
    for rend, tmpl in RENDERINGS.items():
        label = f"coherence-{rend}"
        print(f"  running {label} ...", flush=True)
        eta = evaluate(bench, provider,
                       config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
                       params=params, template=tmpl,
                       run_id=f"{args.model}:{label}",
                       log_path=args.out / f"{label}.jsonl")
        eta.dump(args.out / f"{label}-eta.json")
        etas[label] = eta

    # Normative frame — direct elicitation (r5 machinery).
    for rend, tmpl in RENDERINGS.items():
        label = f"normative-{rend}"
        print(f"  running {label} ...", flush=True)
        eta = run_normative_cell(provider, bench, params, tmpl, args.n_samples, model_info, label)
        eta.dump(args.out / f"{label}-eta.json")
        etas[label] = eta

    # Per-item verdict grid (4 items — grid, not kappa).
    item_ids = [it.id for it in bench.items]
    analyst = {it.id: it.analyst_verdicts[0].value for it in bench.items}
    grid = {
        label: {it.id: it.model_verdict.value for it in eta.items}
        for label, eta in etas.items()
    }
    matches = {
        label: sum(1 for iid in item_ids if grid[label][iid] == analyst[iid])
        for label in grid
    }
    summary = {"model": args.model, "n_samples": args.n_samples,
               "analyst_row": analyst, "grid": grid, "matches_of_4": matches}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n  analyst row: {[analyst[i] for i in item_ids]}")
    for label in etas:
        row = [grid[label][i] for i in item_ids]
        print(f"  {label:24s} {row}  matches={matches[label]}/4")
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
