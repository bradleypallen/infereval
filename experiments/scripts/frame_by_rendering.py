"""Frame x rendering factorial: decomposing the two materiality-anchoring mechanisms.

The 2026-07-02 program identified two levers that hold the MATERIAL reading of an
inference question in place against collapse into formal readings:

- **frame anchoring** — an explicit defeasibility instruction in the system
  prompt ("granting the premises and absent further information ... BAD means
  the premises positively rule out / defeat the conclusion"). Discovered
  decisive on the stop-sign items: thin frame loses the irrelevant-premise rows,
  anchored frame holds the full analyst row.
- **rendering embedding** — practice-embedded scaffolding in the user prompt
  (the patient-framed template). Discovered decisive on the clinical items
  (R2 vs R3/R4).

This factorial crosses them within ONE snapshot and ONE batch (no cross-batch
comparisons — the lesson of the retracted drift claim), support form throughout
(labels GOOD/BAD/ABSTAIN constant, so the two levers are isolated from the
question-form variable):

    clinical fixture (35 items):  frame {thin, anchored-clinical}
                                  x rendering {plain, situational, epistemic, domain}
    stop-sign fixture (4 items):  frame {thin, anchored-explicit}
                                  x rendering {plain, situational, epistemic}

Pre-registered readings of the anchored row's slope across renderings:
  H-frame-dominant : flat  -> the frame instruction overrides scaffolding cues;
  H-additive       : shifted up, slope persists -> independent contributions;
  H-interaction    : plain/situational protected, epistemic punches through
                     (the hedge sits in the user prompt, adjacent to content).

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/frame_by_rendering.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --out experiments/results/clinical_pilot/frame_by_rendering_2026-07-02
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, Evaluation, ProviderParams, evaluate
from infereval.prompts import (
    DEFAULT_PARSE_REGEX,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_USER_TEMPLATE,
    VerificationPrompt,
)
from infereval.providers import get_provider

REPO_ROOT = Path(__file__).resolve().parents[2]
CLINICAL = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"
STOP_SIGN = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(REPO_ROOT / "experiments"))
from paraphrase_axis_triangulation import DEFEASIBLE_PROMPT  # noqa: E402
from s3s4_support_rendering import SUPPORT_EPISTEMIC, SUPPORT_SITUATIONAL  # noqa: E402

#: Rendering user-templates (support form). plain/situational/epistemic are
#: byte-identical to the earlier program; domain is the patient-framed support
#: analog of the R2 template (clinical fixture only).
USER_TEMPLATES = {
    "plain": DEFAULT_USER_TEMPLATE,
    "situational": SUPPORT_SITUATIONAL.user_template,
    "epistemic": SUPPORT_EPISTEMIC.user_template,
    "domain": (
        "Consider a patient for whom this clinical picture holds: "
        "{premise_context}.\n"
        "Does it follow that, for this patient, {conclusion_context}?\n"
        "Verdict:"
    ),
}


def _single_succedent(benchmark: Benchmark) -> Benchmark:
    items = [it for it in benchmark.items if len(it.conclusions) == 1]
    return benchmark.model_copy(update={"items": items})


def _vp(frame_id: str, system: str, rendering: str) -> VerificationPrompt:
    return VerificationPrompt(
        id=f"{frame_id}--{rendering}",
        system=system,
        user_template=USER_TEMPLATES[rendering],
        parse_regex=DEFAULT_PARSE_REGEX,
    )


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

    clinical = _single_succedent(Benchmark.load(CLINICAL))
    stop_sign = Benchmark.load(STOP_SIGN)
    assert clinical.verification_prompt is not None
    anchored_clinical = clinical.verification_prompt.system
    assert anchored_clinical is not None

    fixtures = {
        "clinical": {
            "bench": clinical,
            "frames": {"thin": DEFAULT_SYSTEM_PROMPT, "anchored": anchored_clinical},
            "renderings": ["plain", "situational", "epistemic", "domain"],
        },
        "stopsign": {
            "bench": stop_sign,
            "frames": {"thin": DEFAULT_SYSTEM_PROMPT, "anchored": DEFEASIBLE_PROMPT.system},
            "renderings": ["plain", "situational", "epistemic"],
        },
    }

    etas: dict[str, Evaluation] = {}
    for fx_name, fx in fixtures.items():
        for frame_name, system in fx["frames"].items():
            for rendering in fx["renderings"]:
                label = f"{fx_name}--{frame_name}--{rendering}"
                print(f"  running {label} ...", flush=True)
                eta = evaluate(
                    fx["bench"], provider,
                    config=EndorsementConfig(n_samples=args.n_samples, question_form="support"),
                    params=params,
                    verification_prompt=_vp(f"{frame_name}-{fx_name}", system, rendering),
                    run_id=f"{args.model}:{label}",
                    log_path=args.out / f"{label}.jsonl",
                )
                eta.dump(args.out / f"{label}-eta.json")
                etas[label] = eta

    # Summaries: endorsement counts per cell; per-item grid for stop-sign.
    summary: dict = {"model": args.model, "n_samples": args.n_samples, "cells": {}}
    for label, eta in etas.items():
        mix = Counter(it.model_verdict.value for it in eta.items)
        summary["cells"][label] = {
            "good": mix.get("good", 0), "bad": mix.get("bad", 0),
            "abstain": mix.get("abstain", 0),
            "verdicts": {it.id: it.model_verdict.value for it in eta.items},
        }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== endorsement (good) per cell ===")
    for fx_name, fx in fixtures.items():
        n = fx["bench"].n
        for frame_name in fx["frames"]:
            row = [summary["cells"][f"{fx_name}--{frame_name}--{r}"]["good"] for r in fx["renderings"]]
            cells = dict(zip(fx["renderings"], row, strict=True))
            print(f"  {fx_name:9s} {frame_name:9s} {cells} (of {n})")
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
