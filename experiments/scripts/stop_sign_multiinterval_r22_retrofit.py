"""v0.14.0 Phase 1: stop-sign multi-interval R22 retrofit.

Captures baseline + back-to-back + 1h-later evidence for all 39
bundled stop-sign cross-family cells (13 models × 3 paraphrase
variants) against the stop-sign benchmark. Produces one
``<model>-<variant>-multi-retest.json`` per cell under
``experiments/results/stop_sign/retest/`` + the three saved etas
per cell.

This script deliberately uses the framework's programmatic API rather
than the ``retest --auto`` CLI for two reasons:

1. The v0.5.18 cross-family captures used the
   ``defeasible-explicit-v1`` verification prompt (defined in
   ``experiments/paraphrase_axis_triangulation.py:DEFEASIBLE_PROMPT``)
   which the CLI doesn't expose. The R22 captures need to be taken
   under the same prompt for the evidence to be comparable.

2. Stop-sign paraphrase variants are runtime-constructed by swapping
   the ``δ(ra)`` expression in the benchmark JSON — they aren't
   declared by ``--paraphrase-variant`` indexing. The orchestrator
   imports ``make_variant_benchmark`` from the triangulation script
   and uses one variant-benchmark per cell.

Each cell takes ~1.5 hours wall clock (most of which is the 3600s
sleep between captures 1 and 2). The orchestrator fans the cells out
in parallel via ``concurrent.futures.ThreadPoolExecutor`` so the
total wall clock is bounded by the longest single cell.

Cost estimate: 39 cells × 3 captures × 4 items × 3 samples ≈ 1404
LLM calls. ~$10–25 at current pricing (mix of frontier + flash/mini
tiers across six families).

Usage:

    export ANTHROPIC_API_KEY=...
    export OPENAI_API_KEY=...
    export OPENROUTER_API_KEY=...

    # Dry-run (validates script + lists planned invocations without
    # calling LLMs):
    python experiments/scripts/stop_sign_multiinterval_r22_retrofit.py --dry-run

    # Real run (~1.5h wall clock under parallelism cap of 8 workers):
    python experiments/scripts/stop_sign_multiinterval_r22_retrofit.py

    # Only specific cells (smoke-testing):
    python experiments/scripts/stop_sign_multiinterval_r22_retrofit.py --only claude-opus-4.7

Output (per cell, e.g. claude-opus-4.7-original):

    experiments/results/stop_sign/retest/claude-opus-4.7-original/{eta-0,eta-1,eta-2}.json
    experiments/results/stop_sign/retest/claude-opus-4.7-original/{eta-0,eta-1,eta-2}.run.jsonl
    experiments/results/stop_sign/retest/claude-opus-4.7-original-multi-retest.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

# Allow importing helpers from the triangulation script.
sys.path.insert(0, str(REPO_ROOT / "experiments"))

from infereval import __version__ as FRAMEWORK_VERSION  # noqa: E402
from infereval.benchmark import Benchmark  # noqa: E402
from infereval.evaluation import (  # noqa: E402
    EndorsementConfig,
    Evaluation,
    ProviderParams,
    evaluate,
)
from infereval.report import IdentityCriterion  # noqa: E402
from infereval.retest import (  # noqa: E402
    IntervalPair,
    MultiIntervalRetestResult,
    compute_interval_s,
    compute_retest,
    multi_interval_retest_result_to_dict,
)

# Reuse the canonical defeasible-explicit prompt and variant-construction
# helper from the v0.5.18 paraphrase-axis script so the R22 captures
# use the same endorsement conditions as the original cross-family sweep.
from paraphrase_axis_triangulation import (  # noqa: E402
    DEFEASIBLE_PROMPT,
    VARIANTS,
    make_variant_benchmark,
)

RESULTS_DIR = REPO_ROOT / "experiments" / "results" / "stop_sign" / "retest"
CLAIMS_PATH = RESULTS_DIR / "claims-r22-phase1.json"

# v0.5.18 stop-sign cross-family endorsement config — matches the
# bundled eta files at experiments/results/stop_sign/<cell>.json so the
# R22 captures are taken under identical conditions.
N_SAMPLES = 3
TEMPERATURE = 0.0
MAX_TOKENS = 2048
INTERVAL_DRIFT_S = 3600  # 1 hour


class ModelSpec(NamedTuple):
    label: str
    provider_name: str
    model_id: str
    env_var: str
    extra_kwargs: dict[str, object]


_OPENROUTER_EXTRAS: dict[str, object] = {
    "http_referer": "https://github.com/bradleypallen/infereval",
    "x_title": "infereval-v0.14.0-phase1-r22-retrofit",
}

# Thirteen models matching the v0.5.18 cross-family sweep at
# experiments/results/stop_sign/<model>-<variant>.json.
MODELS: list[ModelSpec] = [
    ModelSpec("gpt-4.1",            "openai",     "gpt-4.1",                       "OPENAI_API_KEY",     {}),
    ModelSpec("gpt-5.4",            "openai",     "gpt-5.4",                       "OPENAI_API_KEY",     {}),
    ModelSpec("gpt-5.4-mini",       "openai",     "gpt-5.4-mini",                  "OPENAI_API_KEY",     {}),
    ModelSpec("claude-opus-4.7",    "anthropic",  "claude-opus-4-7",               "ANTHROPIC_API_KEY",  {}),
    ModelSpec("claude-haiku-4.5",   "anthropic",  "claude-haiku-4-5-20251001",     "ANTHROPIC_API_KEY",  {}),
    ModelSpec("deepseek-v4-pro",    "openrouter", "deepseek/deepseek-v4-pro",      "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("deepseek-v4-flash",  "openrouter", "deepseek/deepseek-v4-flash",    "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("qwen3-max",          "openrouter", "qwen/qwen3-max",                "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("qwen3.6-flash",      "openrouter", "qwen/qwen3.6-flash",            "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("gemini-2.5-pro",     "openrouter", "google/gemini-2.5-pro",         "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("gemini-2.5-flash",   "openrouter", "google/gemini-2.5-flash",       "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("mistral-large",      "openrouter", "mistralai/mistral-large-2512",  "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("mistral-small",      "openrouter", "mistralai/mistral-small-2603",  "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
]


def _load_identity_criterion() -> IdentityCriterion:
    """Load the Phase 1 identity criterion declaration from claims JSON."""
    if not CLAIMS_PATH.is_file():
        raise SystemExit(
            f"ERROR: missing identity-criterion claims file at {CLAIMS_PATH}. "
            f"Stage 3 of the v0.14.0 plan writes this file alongside the "
            f"capture scripts; check that the file was committed."
        )
    data = json.loads(CLAIMS_PATH.read_text())
    crit_dict = data["reliability"]["identity_criterion"]
    return IdentityCriterion(**crit_dict)


def _capture_one_cell(
    spec: ModelSpec,
    variant_name: str,
    variant_ra_expr: str,
    *,
    dry_run: bool,
    identity_criterion: IdentityCriterion,
) -> dict[str, object]:
    """Run baseline + back-to-back + 1h-later for one (model, variant) cell.

    Returns a status dict. On 'ok' (non-dry), also persists the
    `MultiIntervalRetestResult` JSON + saved etas to disk.
    """
    from infereval.providers import get_provider
    from infereval.providers.base import ProviderConfigError, ProviderError

    cell_label = f"{spec.label}-{variant_name}"

    if dry_run:
        env_status = "set" if os.environ.get(spec.env_var) else "NOT set"
        print(
            f"[dry-run] cell={cell_label} provider={spec.provider_name} "
            f"model={spec.model_id} variant={variant_name} "
            f"intervals=[0, {INTERVAL_DRIFT_S}] {spec.env_var}={env_status}"
        )
        return {
            "label": cell_label,
            "status": "ok",
            "message": f"dry-run ({spec.env_var} {env_status})",
        }

    if not os.environ.get(spec.env_var):
        return {
            "label": cell_label,
            "status": "skipped",
            "message": f"{spec.env_var} not set",
        }

    bench = make_variant_benchmark(variant_name, variant_ra_expr)

    try:
        provider = get_provider(
            spec.provider_name, spec.model_id, **spec.extra_kwargs,
        )
    except ProviderConfigError as exc:
        return {
            "label": cell_label,
            "status": "failed",
            "message": f"provider configuration: {exc}",
        }

    # Default endorsement config — n_samples set explicitly; the
    # verification_prompt is supplied via the kwarg below
    # (DEFEASIBLE_PROMPT.id == "defeasible-explicit-v1"). The config's
    # verification_prompt_id default doesn't matter because evaluate()
    # uses the supplied prompt object directly.
    config = EndorsementConfig(n_samples=N_SAMPLES)
    params = ProviderParams(temperature=TEMPERATURE, max_tokens=MAX_TOKENS)

    cell_dir = RESULTS_DIR / cell_label
    cell_dir.mkdir(parents=True, exist_ok=True)
    base_run_id = f"retest-auto-{uuid.uuid4().hex[:8]}"

    captures: list[Evaluation] = []

    try:
        for capture_idx in range(3):
            if capture_idx == 2:
                # Heartbeat every 300s during the 3600s sleep so the
                # parent harness sees periodic stdout activity and
                # doesn't treat the process as hung. Each heartbeat
                # also reports remaining sleep time for visibility.
                print(
                    f"[{cell_label}] sleeping {INTERVAL_DRIFT_S}s before "
                    f"capture {capture_idx}…",
                    flush=True,
                )
                heartbeat_s = 300
                slept = 0
                while slept < INTERVAL_DRIFT_S:
                    chunk = min(heartbeat_s, INTERVAL_DRIFT_S - slept)
                    time.sleep(chunk)
                    slept += chunk
                    if slept < INTERVAL_DRIFT_S:
                        print(
                            f"[{cell_label}] heartbeat: slept {slept}s of "
                            f"{INTERVAL_DRIFT_S}s",
                            flush=True,
                        )

            run_id_i = f"{base_run_id}-{capture_idx}"
            eta_path = cell_dir / f"eta-{capture_idx}.json"
            log_path = cell_dir / f"eta-{capture_idx}.run.jsonl"

            print(
                f"[{cell_label}] capture {capture_idx} starting "
                f"(run_id={run_id_i!r})",
                flush=True,
            )
            eta = evaluate(
                bench, provider,
                config=config, params=params,
                verification_prompt=DEFEASIBLE_PROMPT,
                run_id=run_id_i,
                log_path=log_path,
            )
            eta.dump(eta_path)
            captures.append(Evaluation.load(eta_path))
    except ProviderError as exc:
        return {
            "label": cell_label,
            "status": "failed",
            "message": f"provider error during capture: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "label": cell_label,
            "status": "failed",
            "message": f"unexpected error: {exc}",
        }

    baseline = captures[0]
    pairs: list[IntervalPair] = []
    for later in captures[1:]:
        retest = compute_retest(
            baseline, later, benchmark=bench,
            identity_criterion=identity_criterion,
        )
        interval_s = compute_interval_s(baseline, later)
        pairs.append(IntervalPair(
            interval_s=interval_s, run_id=later.id, retest=retest,
        ))

    multi = MultiIntervalRetestResult(
        schema_version="1.0",
        framework_version=FRAMEWORK_VERSION,
        benchmark_id=baseline.benchmark_id,
        benchmark_hash=baseline.benchmark_hash,
        baseline_run_id=baseline.id,
        pairs=tuple(pairs),
        identity_criterion=identity_criterion,
    )

    multi_path = RESULTS_DIR / f"{cell_label}-multi-retest.json"
    multi_path.write_text(
        json.dumps(multi_interval_retest_result_to_dict(multi), indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "label": cell_label,
        "status": "ok",
        "message": (
            f"3 captures + 2 pairs (kappa={[p.retest.test_retest_kappa for p in pairs]})"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help=(
            "Repeatable. Restrict to model label(s) — runs all 3 variants "
            "per selected model. To restrict to a specific (model, variant) "
            "cell, post-filter the output."
        ),
    )
    parser.add_argument("--max-parallel", type=int, default=8)
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help=(
            "Skip cells whose <cell>-multi-retest.json already exists. "
            "Use this to resume after an interrupted run without redoing "
            "the cells that finished. The skip check uses the bundled "
            "filename convention: experiments/results/stop_sign/retest/"
            "<model>-<variant>-multi-retest.json."
        ),
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    selected_models = MODELS
    if args.only:
        selected_models = [m for m in MODELS if m.label in args.only]
        if not selected_models:
            print(
                f"ERROR: --only filtered to empty. Valid: "
                f"{[m.label for m in MODELS]}",
                file=sys.stderr,
            )
            return 2

    if not args.dry_run:
        identity_criterion = _load_identity_criterion()
    else:
        identity_criterion = IdentityCriterion(
            same_provider_model_id=True,
            cross_update_identity_asserted=True,
            same_scaffolding=True,
            unverifiable_caveats="dry-run",
            rationale="dry-run",
        )

    # Cartesian product: (model, variant) for each selected model and
    # each declared variant.
    cells = [
        (spec, vname, vexpr)
        for spec in selected_models
        for vname, vexpr in VARIANTS.items()
    ]

    if args.skip_completed:
        skipped_completed: list[str] = []
        remaining_cells = []
        for spec, vname, vexpr in cells:
            cell_label = f"{spec.label}-{vname}"
            multi_path = RESULTS_DIR / f"{cell_label}-multi-retest.json"
            if multi_path.is_file():
                skipped_completed.append(cell_label)
            else:
                remaining_cells.append((spec, vname, vexpr))
        if skipped_completed:
            print(
                f"--skip-completed: skipping {len(skipped_completed)} "
                f"cells with existing multi-retest.json "
                f"({skipped_completed[:3]}{'...' if len(skipped_completed) > 3 else ''})"
            )
        cells = remaining_cells

    print(
        f"Stop-sign Phase 1 R22 retrofit: {len(cells)} cells "
        f"(of {len(selected_models)} models × {len(VARIANTS)} variants, "
        f"max_parallel={args.max_parallel})"
    )
    if args.dry_run:
        print("(dry-run: no LLM calls)")

    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.max_parallel,
    ) as pool:
        futures = {
            pool.submit(
                _capture_one_cell,
                spec, variant_name, variant_ra_expr,
                dry_run=args.dry_run,
                identity_criterion=identity_criterion,
            ): (spec, variant_name)
            for spec, variant_name, variant_ra_expr in cells
        }
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            results.append(result)
            print(
                f"[{result['label']}] {result['status']}: {result['message']}",
                flush=True,
            )

    print("\n=== summary ===")
    successes = [r for r in results if r["status"] == "ok"]
    failures = [r for r in results if r["status"] == "failed"]
    skipped = [r for r in results if r["status"] == "skipped"]
    print(f"  successes: {len(successes)}")
    print(f"  failures:  {len(failures)}: "
          f"{[r['label'] for r in failures]}")
    print(f"  skipped:   {len(skipped)}: "
          f"{[r['label'] for r in skipped]}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
