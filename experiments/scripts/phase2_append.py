"""v0.14.0+ Phase 2 staged-composition append orchestrator.

For every Phase 1 multi-retest artifact under
``experiments/results/{stop_sign,pulmonology}/retest/<cell>-multi-retest.json``,
runs ONE fresh capture against the saved baseline (`eta-0.json` next to
the multi-retest), computes retest via `compute_retest`, and appends a
new `IntervalPair` to the existing `MultiIntervalRetestResult`. The new
pair's `interval_s` is computed from the actual elapsed wall clock
between `baseline.started_at` and the fresh capture's `started_at` via
`compute_interval_s`.

Handles both bundled benchmarks:

- **Pulmonology**: the `defeasible-clinical-v1` verification prompt is
  embedded in the benchmark JSON, so `evaluate(verification_prompt=None)`
  loads it automatically. No special handling needed.
- **Stop-sign**: the v0.5.18 cross-family captures (and the v0.14.0
  Phase 1 retrofit) used the script-injected `DEFEASIBLE_PROMPT` from
  `paraphrase_axis_triangulation.py:DEFEASIBLE_PROMPT`. The variant
  benchmark is constructed at runtime via `make_variant_benchmark`.
  This orchestrator imports both and dispatches on benchmark.

Identity criterion: the loaded multi-retest's `identity_criterion` is
preserved verbatim — appending IS the analyst recommitting to the same
individuation across the elapsed wall clock, exactly as the v0.14.0
release plan documented.

Parallelism: cells fan out via `concurrent.futures.ThreadPoolExecutor`
(default `max_parallel=8`). Each cell is a single evaluate + a
compute_retest + a JSON write — typically a few seconds per cell — so
the whole sweep finishes in a few minutes wall clock.

Cost estimate: one fresh capture per cell = (4–30 items) × n_samples
LLM calls per cell. For all 45 cells: ~1500 LLM calls total. ~$5–10 at
current pricing.

Usage:

    # Set up API keys:
    export ANTHROPIC_API_KEY=...
    export OPENAI_API_KEY=...
    export OPENROUTER_API_KEY=...

    # Dry-run (lists planned appends + env-var status, no LLM calls):
    python experiments/scripts/phase2_append.py --dry-run

    # Run all 45 cells:
    python experiments/scripts/phase2_append.py

    # Subset (only one benchmark / only one cell):
    python experiments/scripts/phase2_append.py --only-benchmark pulmonology
    python experiments/scripts/phase2_append.py --only-cell deepseek-v4-pro-perceptual

The orchestrator can be safely re-run; each invocation appends ONE new
pair to each selected cell. If you don't want to double-append, run
once per intended cadence (e.g. once for day-out, once for week-out).

Output: each cell's `<cell>-multi-retest.json` grows from N pairs to
N+1 pairs in place. The new eta is written as
`<cell>/eta-{N+1}.json` + `eta-{N+1}.run.jsonl` next to the existing
pair etas.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "experiments"))

# Reuse the canonical defeasible-explicit prompt + variant-construction
# helper from the v0.5.18 paraphrase-axis script so stop-sign Phase 2
# appends are conducted under identical conditions to Phase 1.
from paraphrase_axis_triangulation import (  # noqa: E402
    DEFEASIBLE_PROMPT,
    VARIANTS,
    make_variant_benchmark,
)

from infereval import __version__ as FRAMEWORK_VERSION  # noqa: E402, N812
from infereval.benchmark import Benchmark  # noqa: E402
from infereval.cli.retest_cmd import _load_multi_interval_result  # noqa: E402
from infereval.evaluation import (  # noqa: E402
    Evaluation,
    evaluate,
)
from infereval.retest import (  # noqa: E402
    IntervalPair,
    MultiIntervalRetestResult,
    compute_interval_s,
    compute_retest,
    multi_interval_retest_result_to_dict,
)

STOP_SIGN_RETEST_DIR = REPO_ROOT / "experiments" / "results" / "stop_sign" / "retest"
PULMONOLOGY_RETEST_DIR = REPO_ROOT / "experiments" / "results" / "pulmonology" / "retest"
PULMONOLOGY_BENCH = REPO_ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

# OpenRouter-specific headers (mirrors Phase 1 orchestrators).
_OPENROUTER_EXTRAS: dict[str, object] = {
    "http_referer": "https://github.com/bradleypallen/infereval",
    "x_title": "infereval-v0.14.0-phase2-append",
}


def _provider_env_var(provider_name: str) -> str:
    return {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }[provider_name]


def _enumerate_cells() -> list[dict[str, object]]:
    """Discover all Phase 1 multi-retest artifacts under both benchmarks.

    Returns a list of dicts, one per cell, with keys:
      - benchmark: "stop_sign" | "pulmonology"
      - cell_label: e.g. "deepseek-v4-pro-perceptual" or "gemini-2.5-pro"
      - multi_path: Path to <cell>-multi-retest.json
      - baseline_eta_path: Path to <cell>/eta-0.json
    """
    cells: list[dict[str, object]] = []
    for retest_dir, bench_kind in (
        (STOP_SIGN_RETEST_DIR, "stop_sign"),
        (PULMONOLOGY_RETEST_DIR, "pulmonology"),
    ):
        for multi_path in sorted(retest_dir.glob("*-multi-retest.json")):
            cell_label = multi_path.stem.replace("-multi-retest", "")
            baseline_eta = retest_dir / cell_label / "eta-0.json"
            if not baseline_eta.is_file():
                print(
                    f"[skip] {bench_kind}/{cell_label}: no eta-0.json next "
                    f"to multi-retest.json at {baseline_eta}",
                    file=sys.stderr,
                )
                continue
            cells.append({
                "benchmark": bench_kind,
                "cell_label": cell_label,
                "multi_path": multi_path,
                "baseline_eta_path": baseline_eta,
            })
    return cells


def _resolve_benchmark_for_cell(cell: dict[str, object]) -> tuple[Benchmark, object]:
    """Build the right benchmark for a cell, and decide whether to inject DEFEASIBLE_PROMPT.

    Stop-sign cells need a runtime-constructed variant benchmark (the
    Phase 1 captures used make_variant_benchmark to swap δ(ra)). The
    variant name is parsed from the cell label suffix.

    Pulmonology cells load the bundled benchmark JSON directly; the
    `defeasible-clinical-v1` prompt is embedded and the framework loads
    it automatically.

    Returns (benchmark, verification_prompt_or_None).
    """
    bench_kind = cell["benchmark"]
    cell_label = cell["cell_label"]

    if bench_kind == "pulmonology":
        return Benchmark.load(PULMONOLOGY_BENCH), None

    # Stop-sign: parse variant suffix from the cell label.
    variant_name = None
    for vname in VARIANTS:
        if cell_label.endswith(f"-{vname}"):
            variant_name = vname
            break
    if variant_name is None:
        raise SystemExit(
            f"ERROR: could not parse variant suffix from stop-sign cell "
            f"label {cell_label!r}. Expected one of "
            f"{[f'-{v}' for v in VARIANTS]}."
        )
    return make_variant_benchmark(variant_name, VARIANTS[variant_name]), DEFEASIBLE_PROMPT


def _append_one_cell(cell: dict[str, object], *, dry_run: bool) -> dict[str, object]:
    """Run one fresh capture, append a new IntervalPair to the existing multi-retest.

    Returns a status dict with `cell`, `status` ('ok'|'skipped'|'failed'),
    `message`, and (on ok) `interval_s` + `kappa`.
    """
    from infereval.providers import get_provider
    from infereval.providers.base import ProviderConfigError, ProviderError

    cell_label = cell["cell_label"]
    bench_kind = cell["benchmark"]
    multi_path = cell["multi_path"]
    baseline_eta_path = cell["baseline_eta_path"]

    # Load baseline eta + existing multi-retest to determine provider /
    # model / endorsement_config (we mirror exactly what Phase 1 used).
    try:
        baseline = Evaluation.load(baseline_eta_path)
        existing_raw = json.loads(multi_path.read_text(encoding="utf-8"))
        existing = _load_multi_interval_result(existing_raw, multi_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "cell": cell_label,
            "status": "failed",
            "message": f"could not load baseline or existing multi-retest: {exc}",
        }

    provider_name = baseline.model.provider
    model_id = baseline.model.model_id
    env_var = _provider_env_var(provider_name)

    if dry_run:
        env_status = "set" if os.environ.get(env_var) else "NOT set"
        n_existing = len(existing.pairs)
        return {
            "cell": cell_label,
            "status": "ok",
            "message": (
                f"dry-run ({bench_kind}, {provider_name}/{model_id}, "
                f"{n_existing}→{n_existing + 1} pairs, {env_var} {env_status})"
            ),
        }

    if not os.environ.get(env_var):
        return {
            "cell": cell_label,
            "status": "skipped",
            "message": f"{env_var} not set",
        }

    # Resolve the right benchmark + prompt for this cell.
    try:
        bench, verification_prompt = _resolve_benchmark_for_cell(cell)
    except SystemExit as exc:
        return {"cell": cell_label, "status": "failed", "message": str(exc)}

    # Build provider client with the right extras.
    extras: dict[str, object] = {}
    if provider_name == "openrouter":
        extras = dict(_OPENROUTER_EXTRAS)
    try:
        provider = get_provider(provider_name, model_id, **extras)
    except ProviderConfigError as exc:
        return {
            "cell": cell_label,
            "status": "failed",
            "message": f"provider configuration: {exc}",
        }

    # Mirror the baseline's endorsement_config + provider params so the
    # parity check in compute_retest passes. Pull both off the loaded
    # baseline eta.
    config = baseline.endorsement_config
    params = baseline.model.params

    cell_dir = baseline_eta_path.parent
    next_slot = len(existing.pairs) + 1
    fresh_eta_path = cell_dir / f"eta-{next_slot}.json"
    log_path = cell_dir / f"eta-{next_slot}.run.jsonl"
    fresh_run_id = f"retest-append-{uuid.uuid4().hex[:8]}-{next_slot}"

    try:
        eta = evaluate(
            bench, provider,
            config=config, params=params,
            verification_prompt=verification_prompt,
            run_id=fresh_run_id,
            log_path=log_path,
        )
    except ProviderError as exc:
        return {
            "cell": cell_label,
            "status": "failed",
            "message": f"provider error during fresh capture: {exc}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "cell": cell_label,
            "status": "failed",
            "message": f"unexpected error during fresh capture: {exc}",
        }
    eta.dump(fresh_eta_path)
    # Re-load for independence (mirrors Phase 1 orchestrator pattern).
    fresh = Evaluation.load(fresh_eta_path)

    # Compute retest against baseline, threading the existing criterion.
    try:
        retest = compute_retest(
            baseline, fresh,
            benchmark=bench,
            identity_criterion=existing.identity_criterion,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "cell": cell_label,
            "status": "failed",
            "message": f"compute_retest failed: {exc}",
        }

    interval_s = compute_interval_s(baseline, fresh)
    new_pair = IntervalPair(
        interval_s=interval_s, run_id=fresh.id, retest=retest,
    )
    updated = MultiIntervalRetestResult(
        schema_version=existing.schema_version,
        framework_version=FRAMEWORK_VERSION,
        benchmark_id=existing.benchmark_id,
        benchmark_hash=existing.benchmark_hash,
        baseline_run_id=existing.baseline_run_id,
        pairs=existing.pairs + (new_pair,),
        identity_criterion=existing.identity_criterion,
    )
    multi_path.write_text(
        json.dumps(multi_interval_retest_result_to_dict(updated), indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "cell": cell_label,
        "status": "ok",
        "message": (
            f"appended pair {next_slot}: interval_s={interval_s}, "
            f"κ={retest.test_retest_kappa}, "
            f"flips={retest.n_disagreements}/{retest.n_items}"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--only-benchmark",
        choices=("stop_sign", "pulmonology"),
        default=None,
        help="Restrict to one benchmark's cells.",
    )
    parser.add_argument(
        "--only-cell",
        action="append",
        default=None,
        help=(
            "Repeatable. Restrict to specific cell labels "
            "(e.g. `deepseek-v4-pro-perceptual` or `gemini-2.5-pro`)."
        ),
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=8,
        help="Maximum concurrent cells (default 8).",
    )
    args = parser.parse_args()

    cells = _enumerate_cells()
    if args.only_benchmark:
        cells = [c for c in cells if c["benchmark"] == args.only_benchmark]
    if args.only_cell:
        cells = [c for c in cells if c["cell_label"] in args.only_cell]

    if not cells:
        print("ERROR: no cells selected. Check --only-benchmark / --only-cell.",
              file=sys.stderr)
        return 2

    print(
        f"Phase 2 append orchestrator: {len(cells)} cells "
        f"(max_parallel={args.max_parallel})"
    )
    if args.dry_run:
        print("(dry-run: no LLM calls)")

    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.max_parallel,
    ) as pool:
        futures = {
            pool.submit(_append_one_cell, cell, dry_run=args.dry_run): cell
            for cell in cells
        }
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            results.append(result)
            print(
                f"[{result['cell']}] {result['status']}: {result['message']}",
                flush=True,
            )

    print("\n=== summary ===")
    successes = [r for r in results if r["status"] == "ok"]
    failures = [r for r in results if r["status"] == "failed"]
    skipped = [r for r in results if r["status"] == "skipped"]
    print(f"  successes: {len(successes)}")
    if failures:
        print(f"  failures:  {len(failures)}: "
              f"{[r['cell'] for r in failures]}")
    if skipped:
        print(f"  skipped:   {len(skipped)}: "
              f"{[r['cell'] for r in skipped]}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
