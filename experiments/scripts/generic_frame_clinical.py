"""Generic anchored frame on the clinical items — the domain-generality completion cell.

The frame x rendering factorial showed frame anchoring dominates: an explicit
defeasibility instruction in the system prompt confers near-complete immunity to
practice-stripping renderings. The stop-sign fixture was protected by a fully
GENERIC anchored frame (`defeasible-explicit-v1`: "ordinary reasoner",
bird-flies example, no domain lexicon), while the clinical fixture used its
domain-flavored frame (`defeasible-clinical-v1`).

This run settles the domain-generality question the R3-R5 series left open:
generality is unrecoverable at the RENDERING level — is it fully recoverable at
the FRAME level? Cells (one batch, `gpt-4.1`, temp 0, seed 7, 6 samples/item):

    clinical--genericanchored--{plain, situational, epistemic, domain}
    clinical--anchoredclinical--plain     (re-run of the factorial cell, as the
                                           cross-batch drift anchor)

Read-out against the factorial rows (thin: 23/18/15/18; anchored-clinical:
24/23/22/22 of 35): if the generic-anchored row matches the clinical-anchored
row, one generic frame suffices for any domain and the instrument's
domain-general story is restored in its strongest form; if it sits nearer the
thin row, the anchoring must be domain-flavored and per-domain frames join
per-domain templates as required equipment.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/generic_frame_clinical.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --out experiments/results/clinical_pilot/generic_frame_2026-07-02
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

REPO_ROOT = Path(__file__).resolve().parents[2]
CLINICAL = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REPO_ROOT / "experiments"))
from frame_by_rendering import _single_succedent, _vp  # noqa: E402
from paraphrase_axis_triangulation import DEFEASIBLE_PROMPT  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", required=True)
    p.add_argument("--n-samples", type=int, default=6)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=2048)
    args = p.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        print(f"ERROR: {args.key_env} is not set.", file=sys.stderr)
        return 1

    provider = get_provider(args.provider, args.model, api_key=api_key)
    params = ProviderParams(temperature=0.0, max_tokens=args.max_tokens, seed=7)
    args.out.mkdir(parents=True, exist_ok=True)

    bench = _single_succedent(Benchmark.load(CLINICAL))
    assert bench.verification_prompt is not None
    clinical_system = bench.verification_prompt.system
    assert clinical_system is not None
    generic_system = DEFEASIBLE_PROMPT.system

    cells = [
        ("clinical--genericanchored--plain", generic_system, "plain"),
        ("clinical--genericanchored--situational", generic_system, "situational"),
        ("clinical--genericanchored--epistemic", generic_system, "epistemic"),
        ("clinical--genericanchored--domain", generic_system, "domain"),
        # Cross-batch drift anchor: re-run of the factorial's anchored-plain cell.
        ("clinical--anchoredclinical--plain-anchorrun", clinical_system, "plain"),
    ]

    summary: dict = {"model": args.model, "n_samples": args.n_samples, "cells": {}}
    for label, system, rendering in cells:
        print(f"  running {label} ...", flush=True)
        frame_id = label.split("--")[1]
        eta = evaluate(
            bench, provider,
            config=EndorsementConfig(n_samples=args.n_samples, question_form="support"),
            params=params,
            verification_prompt=_vp(frame_id, system, rendering),
            run_id=f"{args.model}:{label}",
            log_path=args.out / f"{label}.jsonl",
        )
        eta.dump(args.out / f"{label}-eta.json")
        mix = Counter(it.model_verdict.value for it in eta.items)
        summary["cells"][label] = {
            "good": mix.get("good", 0), "bad": mix.get("bad", 0),
            "abstain": mix.get("abstain", 0),
            "verdicts": {it.id: it.model_verdict.value for it in eta.items},
        }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== endorsement (good, of 35) ===")
    for label in summary["cells"]:
        c = summary["cells"][label]
        print(f"  {label:48s} good={c['good']} bad={c['bad']} abstain={c['abstain']}")
    print("  [factorial reference] thin row:              23 / 18 / 15 / 18")
    print("  [factorial reference] anchored-clinical row: 24 / 23 / 22 / 22")
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
