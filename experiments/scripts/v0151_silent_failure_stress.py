"""v0.15.1+ silent-failure validation harness.

Replicates the v0.14.0 silent-failure bug conditions against the live
OpenRouter API and verifies that the v0.15.0/v0.15.1 framework fixes
hold under real burst pressure. Intended as a regression test before
every release that touches provider error handling, retry logic, or
the per-evaluate logger.

What the test does
------------------

1. Loads the bundled pulmonology benchmark
   (``examples/pulmonary_edema/benchmark.json``).
2. Builds three OpenRouter providers — by default the same three cells
   that exhibited the worst v0.14.0 silent-failure collapse:
   ``google/gemini-2.5-pro``, ``qwen/qwen3-max``,
   ``deepseek/deepseek-v4-pro``.
3. Runs ``evaluate()`` against each concurrently via
   ``ThreadPoolExecutor(max_workers=N)``. The default ``max_workers=3``
   matches the burst pattern that triggered the original bug under
   OpenRouter rate-limit pressure.
4. Writes one eta JSON + one run.jsonl per cell to the configured
   output directory (default ``/tmp/v0151-stress/<timestamp>/``).
5. Runs ``infereval audit`` on each capture and prints a per-cell
   summary table comparing published vs recomputed metrics.

Pass criteria
-------------

For each cell, after the run:

- ``audit`` reports **0 suspected silent failures** that are not
  ``parse_status == "budget_clipped"`` (which is real model behavior,
  not an instrument failure).
- ``provider_error`` is set on every sample that had a provider
  failure (any failure must be observable, not silent).
- ``majority_vote`` counts on items with failures sum only over
  surviving samples (the v0.15.0 aggregator-skip contract).
- Cell-level coverage is ``>= 0.5`` (no catastrophic instrument-
  artifact collapse like the v0.14.0 1/30 day-out result). This is a
  conservative floor — substantive cells under v0.14.0 with similar
  benchmark difficulty cleared 0.7+.

The harness does NOT enforce these pass criteria automatically — it
prints the per-cell audit output and leaves the verdict to the
reviewer. A future enhancement could thread the criteria into a
``--fail-on-regression`` flag.

Cost / wall time
----------------

Per cell: 30 items × 5 samples = 150 LLM calls (the default
benchmark uses ``n_samples=5``). Across 3 cells: 450 calls. Wall
time depends on the model's reasoning-token consumption and
OpenRouter rate limits — typically 5–25 minutes per cell with
high variance across reasoning-model cells. Cost: ~$0.20 against
OpenRouter list pricing as of June 2026.

Usage
-----

    export OPENROUTER_API_KEY=...
    python experiments/scripts/v0151_silent_failure_stress.py

    # Custom output directory + cells:
    python experiments/scripts/v0151_silent_failure_stress.py \\
        --out-dir /tmp/v0151-stress/2026-06-08 \\
        --cell openrouter:google/gemini-2.5-pro:gemini-2.5-pro \\
        --cell openrouter:qwen/qwen3-max:qwen3-max \\
        --max-workers 3

    # Single-cell smoke test (~$0.05):
    python experiments/scripts/v0151_silent_failure_stress.py \\
        --cell openrouter:google/gemini-2.5-pro:gemini-2.5-pro \\
        --max-workers 1

Output
------

Per cell:

- ``<out-dir>/<label>-eta.json`` — the evaluation file
- ``<out-dir>/<label>-run.jsonl`` — the JSONL run log (used to verify
  per-evaluate logger isolation: each file must contain only its
  own run's events).

Plus:

- ``<out-dir>/summary.json`` — per-cell wall time + status
- ``<out-dir>/audit-<label>.json`` — ``infereval audit --json`` output
  for each cell, capturing the published-vs-recomputed metrics that
  are the primary pass-criterion evidence.

See ``KNOWN_ISSUES_v0.14.0.md`` for the underlying bug analysis and
``CHANGELOG.md`` entries for v0.15.0 / v0.15.1 for the fixes this
harness validates.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from infereval import __version__
from infereval.benchmark import Benchmark
from infereval.evaluation import evaluate
from infereval.providers import get_provider

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BENCH = REPO_ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

# The three cells that exhibited the worst v0.14.0 silent-failure collapse
# per KNOWN_ISSUES_v0.14.0.md. All OpenRouter-mediated.
DEFAULT_CELLS = [
    "openrouter:google/gemini-2.5-pro:gemini-2.5-pro",
    "openrouter:qwen/qwen3-max:qwen3-max",
    "openrouter:deepseek/deepseek-v4-pro:deepseek-v4-pro",
]

OPENROUTER_EXTRAS: dict[str, object] = {
    "http_referer": "https://github.com/bradleypallen/infereval",
    "x_title": "infereval-v0.15.1-silent-failure-stress",
}


def _parse_cell(spec: str) -> tuple[str, str, str]:
    """Parse ``provider:model_id:label`` triples from --cell."""
    parts = spec.split(":", 2)
    if len(parts) != 3:
        raise SystemExit(
            f"ERROR: --cell must be 'provider:model_id:label', got {spec!r}"
        )
    return parts[0], parts[1], parts[2]


def _provider_env_var(provider_name: str) -> str:
    return {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }.get(provider_name, f"{provider_name.upper()}_API_KEY")


def run_one_cell(
    provider_name: str,
    model_id: str,
    label: str,
    *,
    bench_path: Path,
    out_dir: Path,
) -> dict[str, object]:
    """Run one pulm cell. Return summary dict."""
    bench = Benchmark.load(bench_path)
    extras: dict[str, object] = {}
    if provider_name == "openrouter":
        extras = dict(OPENROUTER_EXTRAS)
    provider = get_provider(provider_name, model_id, **extras)

    eta_path = out_dir / f"{label}-eta.json"
    log_path = out_dir / f"{label}-run.jsonl"
    run_id = f"v0151-stress-{label}-{uuid.uuid4().hex[:8]}"

    start = time.monotonic()
    try:
        eta = evaluate(
            bench,
            provider,
            run_id=run_id,
            log_path=log_path,
        )
        wall_s = time.monotonic() - start
        eta.dump(eta_path)
        return {
            "label": label,
            "provider": provider_name,
            "model_id": model_id,
            "status": "ok",
            "wall_s": wall_s,
            "eta_path": str(eta_path),
            "log_path": str(log_path),
        }
    except Exception as exc:  # noqa: BLE001 -- diagnostic harness
        wall_s = time.monotonic() - start
        return {
            "label": label,
            "provider": provider_name,
            "model_id": model_id,
            "status": "failed",
            "wall_s": wall_s,
            "error": str(exc),
        }


def run_audit(eta_path: Path, out_dir: Path, label: str) -> dict[str, object]:
    """Run `infereval audit --json` on the eta and return the parsed report."""
    audit_json = out_dir / f"audit-{label}.json"
    try:
        result = subprocess.run(
            ["infereval", "audit", str(eta_path), "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        return {"error": "infereval CLI not on PATH"}
    except subprocess.CalledProcessError as exc:
        return {"error": f"audit failed: {exc.stderr}"}
    audit_json.write_text(result.stdout)
    parsed: dict[str, object] = json.loads(result.stdout)
    return parsed


def print_summary_table(audits: dict[str, dict[str, object]]) -> None:
    """Print the per-cell pass-criteria summary table."""
    print()
    print("=== Per-cell audit summary ===")
    print(
        f"{'cell':<25} {'samples':>8} {'known':>6} {'suspected':>10} "
        f"{'cov_pub':>8} {'cov_rec':>8} {'κ_pub':>8} {'κ_rec':>8}"
    )
    for label, audit in audits.items():
        if "error" in audit:
            print(f"{label:<25} ERROR: {audit['error']}")
            continue
        kp = audit["published"]["kappa_c"]
        kr = audit["recomputed_failures_excluded"]["kappa_c"]
        kp_s = "undef" if kp is None else f"{kp:.4f}"
        kr_s = "undef" if kr is None else f"{kr:.4f}"
        print(
            f"{label:<25} {audit['n_samples_scanned']:>8} "
            f"{audit['n_known_provider_errors']:>6} "
            f"{audit['n_suspected_silent_failures']:>10} "
            f"{audit['published']['coverage']:>8.4f} "
            f"{audit['recomputed_failures_excluded']['coverage']:>8.4f} "
            f"{kp_s:>8} {kr_s:>8}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="v0.15.1+ silent-failure validation harness."
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=(
            "Output directory for etas + logs. Defaults to "
            "/tmp/v0151-stress/<UTC timestamp>/."
        ),
    )
    parser.add_argument(
        "--cell",
        action="append",
        default=None,
        help=(
            "Cell spec 'provider:model_id:label' (repeatable). Defaults "
            "to the three OpenRouter cells from KNOWN_ISSUES_v0.14.0.md."
        ),
    )
    parser.add_argument(
        "--bench",
        type=Path,
        default=DEFAULT_BENCH,
        help=f"Benchmark JSON path (default: {DEFAULT_BENCH}).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help=(
            "ThreadPoolExecutor max_workers — sets the burst-parallelism. "
            "Default 3 matches the original v0.14.0 bug condition."
        ),
    )
    args = parser.parse_args()

    out_dir: Path = args.out_dir or Path(
        "/tmp/v0151-stress"
    ) / datetime.utcnow().strftime("%Y-%m-%dT%H%M%SZ")
    cells = [_parse_cell(c) for c in (args.cell or DEFAULT_CELLS)]

    print(f"infereval v{__version__} — v0.15.1+ silent-failure stress harness")
    print(f"benchmark: {args.bench}")
    print(f"output dir: {out_dir}")
    print(f"cells: {[c[2] for c in cells]}")
    print(f"max_workers: {args.max_workers}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Validate env vars before launching.
    missing = []
    for prov, _, _ in cells:
        env = _provider_env_var(prov)
        if not os.environ.get(env):
            missing.append(env)
    if missing:
        print(
            f"\nERROR: missing API keys: {sorted(set(missing))}", file=sys.stderr
        )
        return 2

    # Launch cells concurrently.
    print(
        f"\nRunning {len(cells)} cells concurrently via "
        f"ThreadPoolExecutor (max_workers={args.max_workers})..."
    )
    start = time.monotonic()
    results: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.max_workers
    ) as pool:
        futures = {
            pool.submit(
                run_one_cell,
                prov,
                model_id,
                label,
                bench_path=args.bench,
                out_dir=out_dir,
            ): label
            for (prov, model_id, label) in cells
        }
        for fut in concurrent.futures.as_completed(futures):
            label = futures[fut]
            res = fut.result()
            print(f"  [{label}] {res['status']} in {res['wall_s']:.1f}s")
            results.append(res)
    total_wall = time.monotonic() - start
    print(f"\nTotal wall time: {total_wall:.1f}s")

    (out_dir / "summary.json").write_text(json.dumps(results, indent=2))

    # Audit each successful cell.
    audits: dict[str, dict[str, object]] = {}
    for res in results:
        label_str = str(res["label"])
        if res.get("status") != "ok":
            audits[label_str] = {"error": str(res.get("error", "unknown"))}
            continue
        audits[label_str] = run_audit(
            Path(str(res["eta_path"])), out_dir, label_str
        )

    print_summary_table(audits)

    print(f"\nAll outputs under: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
