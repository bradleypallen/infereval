"""v0.14.0 Phase 1: pulmonology multi-interval R22 retrofit.

Captures baseline + back-to-back + 1h-later evidence for all 6 bundled
pulmonology cross-family models against the v0.2 30-item benchmark.
Produces one ``<model>-multi-retest.json`` per model under
``experiments/results/pulmonology/retest/`` + the three saved etas
per cell (eta-0/1/2.json + matching .run.jsonl).

This script is the v0.14.0 R22 retrofit's deliberate departure from the
``retest --auto`` CLI shape: the v0.10.0 pulmonology captures used the
non-default ``defeasible-clinical-v1`` verification prompt which the
CLI doesn't expose, and threading per-prompt evidence through the CLI
would creep this release's scope. The script uses the framework's
programmatic API directly (``evaluate`` → ``compute_retest`` →
``MultiIntervalRetestResult``) so the R22 captures are taken under
the same endorsement config the v0.10.0 cross-family captures used.

Each cell takes ~1.5 hours wall clock (most of which is the 3600s
sleep between captures 1 and 2). The orchestrator fans the cells out
in parallel via ``concurrent.futures.ThreadPoolExecutor`` so the
total wall clock is bounded by the longest single cell, not the sum.

Cost estimate: 6 cells × 3 captures × 30 items × 3 samples ≈ 1620 LLM
calls. ~$5–15 at current pricing (mostly mid-tier model spend).

Usage:

    # Set up API keys (anthropic/openai/openrouter):
    export ANTHROPIC_API_KEY=...
    export OPENAI_API_KEY=...
    export OPENROUTER_API_KEY=...

    # Dry-run (validates script + lists planned invocations without
    # calling LLMs):
    python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py --dry-run

    # Real run (~1.5h wall clock under parallelism cap of 8 workers):
    python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py

    # Only one cell (for smoke-testing):
    python experiments/scripts/pulmonology_multiinterval_r22_retrofit.py --only claude-opus-4.7

Output (per cell):

    experiments/results/pulmonology/retest/<model>/{eta-0,eta-1,eta-2}.json
    experiments/results/pulmonology/retest/<model>/{eta-0,eta-1,eta-2}.run.jsonl
    experiments/results/pulmonology/retest/<model>-multi-retest.json

The identity criterion declared in
``experiments/results/pulmonology/retest/claims-r22-phase1.json`` is
threaded into every cell's ``MultiIntervalRetestResult.identity_criterion``.
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

from infereval import __version__ as FRAMEWORK_VERSION  # noqa: E402, N812
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

BENCHMARK_PATH = REPO_ROOT / "examples" / "pulmonary_edema" / "benchmark.json"
RESULTS_DIR = REPO_ROOT / "experiments" / "results" / "pulmonology" / "retest"
CLAIMS_PATH = RESULTS_DIR / "claims-r22-phase1.json"

# v0.10.0 pulmonology cross-family endorsement config — must match the
# bundled eta files at experiments/results/pulmonology/<model>-eta.json
# so the R22 captures are taken under the same conditions.
PULMONOLOGY_VERIFICATION_PROMPT_ID = "defeasible-clinical-v1"
N_SAMPLES = 3
TEMPERATURE = 0.0
MAX_TOKENS = 2048
INTERVAL_BACK_TO_BACK_S = 0
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

# Six models matching the v0.10.0 cross-family sweep at
# experiments/results/pulmonology/<model>-eta.json.
MODELS: list[ModelSpec] = [
    ModelSpec("claude-opus-4.7", "anthropic",  "claude-opus-4-7",          "ANTHROPIC_API_KEY",  {}),
    ModelSpec("gpt-4.1",          "openai",     "gpt-4.1",                  "OPENAI_API_KEY",     {}),
    ModelSpec("gpt-5.5",          "openai",     "gpt-5.5",                  "OPENAI_API_KEY",     {}),
    ModelSpec("deepseek-v4-pro",  "openrouter", "deepseek/deepseek-v4-pro", "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("gemini-2.5-pro",   "openrouter", "google/gemini-2.5-pro",    "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
    ModelSpec("qwen3-max",        "openrouter", "qwen/qwen3-max",           "OPENROUTER_API_KEY", _OPENROUTER_EXTRAS),
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
    *,
    dry_run: bool,
    identity_criterion: IdentityCriterion,
) -> dict[str, object]:
    """Run baseline + back-to-back + 1h-later for one (model) cell.

    Returns a status dict with `label`, `status` ('ok' | 'skipped' |
    'failed'), and `message`. On 'ok', also persists the
    `MultiIntervalRetestResult` JSON + saved etas to disk.
    """
    from infereval.providers import get_provider
    from infereval.providers.base import ProviderConfigError, ProviderError

    if dry_run:
        # Dry-run: report what would happen including whether keys are set.
        env_status = "set" if os.environ.get(spec.env_var) else "NOT set"
        print(
            f"[dry-run] cell={spec.label} provider={spec.provider_name} "
            f"model={spec.model_id} intervals=[{INTERVAL_BACK_TO_BACK_S}, "
            f"{INTERVAL_DRIFT_S}] {spec.env_var}={env_status}"
        )
        return {
            "label": spec.label,
            "status": "ok",
            "message": f"dry-run ({spec.env_var} {env_status})",
        }

    if not os.environ.get(spec.env_var):
        return {
            "label": spec.label,
            "status": "skipped",
            "message": f"{spec.env_var} not set",
        }

    bench = Benchmark.load(BENCHMARK_PATH)

    try:
        provider = get_provider(
            spec.provider_name, spec.model_id, **spec.extra_kwargs,
        )
    except ProviderConfigError as exc:
        return {
            "label": spec.label,
            "status": "failed",
            "message": f"provider configuration: {exc}",
        }

    config = EndorsementConfig(
        n_samples=N_SAMPLES,
        verification_prompt_id=PULMONOLOGY_VERIFICATION_PROMPT_ID,
    )
    params = ProviderParams(temperature=TEMPERATURE, max_tokens=MAX_TOKENS)

    cell_dir = RESULTS_DIR / spec.label
    cell_dir.mkdir(parents=True, exist_ok=True)
    base_run_id = f"retest-auto-{uuid.uuid4().hex[:8]}"

    captures: list[Evaluation] = []
    intervals_actually_slept: list[int] = []

    try:
        for capture_idx in range(3):  # 0 = baseline, 1 = back-to-back, 2 = 1h-later
            if capture_idx == 1:
                # back-to-back, no sleep
                intervals_actually_slept.append(0)
            elif capture_idx == 2:
                # Heartbeat every 300s during the 3600s sleep so the
                # parent harness sees periodic stdout activity and
                # doesn't treat the process as hung.
                print(
                    f"[{spec.label}] sleeping {INTERVAL_DRIFT_S}s before "
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
                            f"[{spec.label}] heartbeat: slept {slept}s of "
                            f"{INTERVAL_DRIFT_S}s",
                            flush=True,
                        )
                intervals_actually_slept.append(INTERVAL_DRIFT_S)

            run_id_i = f"{base_run_id}-{capture_idx}"
            eta_path = cell_dir / f"eta-{capture_idx}.json"
            log_path = cell_dir / f"eta-{capture_idx}.run.jsonl"

            print(
                f"[{spec.label}] capture {capture_idx} starting "
                f"(run_id={run_id_i!r})",
                flush=True,
            )
            # verification_prompt=None → framework loads the benchmark's
            # embedded `defeasible-clinical-v1` prompt automatically.
            # This is the same prompt the v0.10.0 cross-family captures
            # used, so the R22 evidence is taken under identical
            # endorsement conditions.
            eta = evaluate(
                bench, provider,
                config=config, params=params,
                run_id=run_id_i,
                log_path=log_path,
            )
            eta.dump(eta_path)
            # Re-load from disk for independence from the in-memory state.
            captures.append(Evaluation.load(eta_path))
    except ProviderError as exc:
        return {
            "label": spec.label,
            "status": "failed",
            "message": f"provider error during capture: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "label": spec.label,
            "status": "failed",
            "message": f"unexpected error: {exc}",
        }

    # Build the MultiIntervalRetestResult.
    baseline = captures[0]
    pairs: list[IntervalPair] = []
    for _i, later in enumerate(captures[1:], start=1):
        retest = compute_retest(
            baseline, later, benchmark=bench,
            identity_criterion=identity_criterion,
        )
        # interval_s reflects the actual wall-clock from baseline to this
        # capture (computed from started_at), not a nominal value.
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

    multi_path = RESULTS_DIR / f"{spec.label}-multi-retest.json"
    multi_path.write_text(
        json.dumps(multi_interval_retest_result_to_dict(multi), indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "label": spec.label,
        "status": "ok",
        "message": (
            f"3 captures + 2 pairs (kappa={[p.retest.test_retest_kappa for p in pairs]})"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the planned invocations without calling any LLM.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help=(
            "Repeatable. Restrict the run to the given model label(s). "
            "Useful for smoke-testing or retrying failed cells."
        ),
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=8,
        help=(
            "Maximum concurrent cells (default 8). Each cell takes ~1.5h "
            "wall clock; running them in parallel bounds total wall "
            "clock by the longest single cell rather than the sum."
        ),
    )
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help=(
            "Skip cells whose <model>-multi-retest.json already exists. "
            "Use to resume after an interrupted run."
        ),
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    selected = MODELS
    if args.only:
        selected = [m for m in MODELS if m.label in args.only]
        if not selected:
            print(
                f"ERROR: --only filtered the model list to empty. "
                f"Got --only={args.only!r}; valid labels: "
                f"{[m.label for m in MODELS]}",
                file=sys.stderr,
            )
            return 2

    if args.skip_completed:
        skipped_completed: list[str] = []
        remaining: list[ModelSpec] = []
        for spec in selected:
            multi_path = RESULTS_DIR / f"{spec.label}-multi-retest.json"
            if multi_path.is_file():
                skipped_completed.append(spec.label)
            else:
                remaining.append(spec)
        if skipped_completed:
            print(
                f"--skip-completed: skipping {len(skipped_completed)} "
                f"cells with existing multi-retest.json: {skipped_completed}"
            )
        selected = remaining

    if not args.dry_run:
        identity_criterion = _load_identity_criterion()
    else:
        # Cheap sentinel for dry-run mode. Carries all required
        # IdentityCriterion fields with default booleans.
        identity_criterion = IdentityCriterion(
            same_provider_model_id=True,
            cross_update_identity_asserted=True,
            same_scaffolding=True,
            unverifiable_caveats="dry-run",
            rationale="dry-run",
        )

    print(
        f"Pulmonology Phase 1 R22 retrofit: {len(selected)} cells "
        f"(max_parallel={args.max_parallel})"
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
                spec,
                dry_run=args.dry_run,
                identity_criterion=identity_criterion,
            ): spec
            for spec in selected
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
    print(f"  successes: {len(successes)} ({[r['label'] for r in successes]})")
    print(f"  failures:  {len(failures)} ({[r['label'] for r in failures]})")
    print(f"  skipped:   {len(skipped)} ({[r['label'] for r in skipped]})")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
