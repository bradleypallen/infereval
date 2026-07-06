"""Cross-model replication of the frame-anchoring results (one model per run).

Every 2026-07-02/03 frame finding was captured on a single gpt-4.1 snapshot —
a scope caveat stamped on each analysis. This script replicates the core 2x2x2
on another model family: {support, coherence} x {thin, anchored} x {plain,
epistemic}, on the clinical-pilot single-succedent items. The epistemic
rendering is the stress cell (the one that collapsed gpt-4.1 to 15/7 good under
thin frames); the anchored frames are the rescue whose generality is under
test.

Support cells reuse the factorial machinery (`frame_by_rendering._vp`) so the
prompts are byte-identical to the gpt-4.1 factorial cells. Coherence cells run
through the released v0.17.6 frame API (`coherence_frame=` on ``evaluate``),
so this run doubles as the API's first cross-model exercise; templates are
passed explicitly to override the benchmark's clinical template binding.

Cells (one batch, temp 0, seed 7 where the provider honors it, 6 samples/item):

    sup--thin--plain        sup--thin--epistemic
    sup--anchored--plain    sup--anchored--epistemic
    coh--thin--plain        coh--thin--epistemic
    coh--anchored--plain    coh--anchored--epistemic

gpt-4.1 reference rows (of 35 good, from the committed captures):
    support:   thin 23/15, anchored(generic) 24/21
    coherence: thin 21/7,  anchored 24/23

Read-out: per-model, does the thin plain->epistemic slope collapse and does the
anchored slope stay flat, on both question forms? If yes across families, the
frame-anchoring findings are model-general; if a family diverges, the finding
is snapshot-relative and the analyses' scope caveats become substantive.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/cross_model_frame_replication.py \
        --provider anthropic --model claude-opus-4-7 --key-env ANTHROPIC_API_KEY \
        --n-samples 6 --out experiments/results/clinical_pilot/cross_model_2026-07-05/claude-opus-4-7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, ProviderParams, evaluate
from infereval.providers import get_provider
from infereval.templates import (
    DEFEASIBLE_COHERENCE_FRAME,
    THIN_COHERENCE_FRAME,
    DefaultTemplate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REPO_ROOT / "experiments"))
from frame_by_rendering import (  # noqa: E402
    DEFAULT_SYSTEM_PROMPT,
    _single_succedent,
    _vp,
)
from paraphrase_axis_triangulation import DEFEASIBLE_PROMPT  # noqa: E402
from r4_epistemic import EpistemicTemplate  # noqa: E402

_OPENROUTER_EXTRAS = {
    "http_referer": "https://allen.is/infereval",
    "x_title": "infereval",
}

# gpt-4.1 reference rows (good, of 35) from the committed 2026-07-02/03 runs.
GPT41_REFERENCE = {
    "sup--thin--plain": 23,
    "sup--thin--epistemic": 15,
    "sup--anchored--plain": 24,
    "sup--anchored--epistemic": 21,
    "coh--thin--plain": 21,
    "coh--thin--epistemic": 7,
    "coh--anchored--plain": 24,
    "coh--anchored--epistemic": 23,
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    p.add_argument("--model", required=True, help="Provider-specific model id (a pinned snapshot)")
    p.add_argument("--key-env", required=True)
    p.add_argument("--n-samples", type=int, default=6)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens-support", type=int, default=2048)
    p.add_argument("--max-tokens-coherence", type=int, default=2048)
    p.add_argument("--cells", type=str, default="all",
                   help="Comma-separated cell labels to run (default: all). "
                   "Use to re-run cells invalidated by an instrument artifact.")
    args = p.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        print(f"ERROR: {args.key_env} is not set.", file=sys.stderr)
        return 1

    extras = dict(_OPENROUTER_EXTRAS) if args.provider == "openrouter" else {}
    provider = get_provider(args.provider, args.model, api_key=api_key, **extras)
    bench = _single_succedent(Benchmark.load(BENCHMARK))
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"Cross-model frame replication: {args.model}, {bench.n} items, "
          f"{args.n_samples} samples/item, 8 cells.")

    support_cells = [
        ("sup--thin--plain", DEFAULT_SYSTEM_PROMPT, "plain"),
        ("sup--thin--epistemic", DEFAULT_SYSTEM_PROMPT, "epistemic"),
        ("sup--anchored--plain", DEFEASIBLE_PROMPT.system, "plain"),
        ("sup--anchored--epistemic", DEFEASIBLE_PROMPT.system, "epistemic"),
    ]
    coherence_cells = [
        ("coh--thin--plain", THIN_COHERENCE_FRAME, DefaultTemplate()),
        ("coh--thin--epistemic", THIN_COHERENCE_FRAME, EpistemicTemplate()),
        ("coh--anchored--plain", DEFEASIBLE_COHERENCE_FRAME, DefaultTemplate()),
        ("coh--anchored--epistemic", DEFEASIBLE_COHERENCE_FRAME, EpistemicTemplate()),
    ]

    summary: dict = {
        "model": args.model,
        "provider": args.provider,
        "n_samples": args.n_samples,
        "gpt41_reference_good": GPT41_REFERENCE,
        "cells": {},
    }

    def record(label: str, eta) -> None:
        eta.dump(args.out / f"{label}-eta.json")
        mix = Counter(it.model_verdict.value for it in eta.items)
        summary["cells"][label] = {
            "good": mix.get("good", 0), "bad": mix.get("bad", 0),
            "abstain": mix.get("abstain", 0),
            "verdicts": {it.id: it.model_verdict.value for it in eta.items},
        }

    selected = None if args.cells == "all" else {c.strip() for c in args.cells.split(",")}

    for label, system, rendering in support_cells:
        if selected is not None and label not in selected:
            continue
        print(f"  running {label} ...", flush=True)
        frame_id = label.replace("--", "-")
        eta = evaluate(
            bench, provider,
            config=EndorsementConfig(n_samples=args.n_samples, question_form="support"),
            params=ProviderParams(
                temperature=0.0, max_tokens=args.max_tokens_support, seed=7
            ),
            verification_prompt=_vp(frame_id, system, rendering),
            run_id=f"{args.model}:{label}",
            log_path=args.out / f"{label}.jsonl",
        )
        record(label, eta)

    for label, frame, template in coherence_cells:
        if selected is not None and label not in selected:
            continue
        print(f"  running {label} ...", flush=True)
        eta = evaluate(
            bench, provider,
            config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
            params=ProviderParams(
                temperature=0.0, max_tokens=args.max_tokens_coherence, seed=7
            ),
            template=template,
            coherence_frame=frame,
            run_id=f"{args.model}:{label}",
            log_path=args.out / f"{label}.jsonl",
        )
        record(label, eta)

    # Partial re-runs merge into an existing summary (superseding those cells).
    summary_path = args.out / "summary.json"
    if selected is not None and summary_path.exists():
        prior = json.loads(summary_path.read_text())
        prior["cells"].update(summary["cells"])
        prior["n_samples"] = summary["n_samples"]
        summary = prior
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print(f"\n=== {args.model}: endorsement (good, of {bench.n}) ===")
    print(f"  {'cell':28s} {'this model':>10s} {'gpt-4.1':>8s}")
    for label in summary["cells"]:
        c = summary["cells"][label]
        print(f"  {label:28s} {c['good']:>4d}/{c['bad']}/{c['abstain']:<4d} "
              f"{GPT41_REFERENCE[label]:>6d}")
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
