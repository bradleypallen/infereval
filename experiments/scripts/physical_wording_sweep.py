"""Stop-sign sweep with the physical-wording axis (branch ``physical-wording``).

Reruns the 13-model x 4-item x 3-wording grid of the paraphrase-axis
triangulation with a changed wording axis, under the v0.17.8
committed-verdict parser:

- ``intrinsic`` ("a has the standard color of stop signs") is REPLACED by
  ``physical`` ("a's surface would reflect light predominantly in the
  roughly 620-750 nm band when illuminated");
- ``original`` and ``perceptual`` are unchanged;
- delta(nr) is reworded in ALL conditions: "a is not made with reflective
  material" -> "a is not made with retroreflective sheeting". The swap is
  runtime-only (the bundled ``examples/stop_sign/benchmark.json`` is not
  modified); the reworded text is recorded in the sweep manifest and in
  each cell's benchmark id/hash.
- The analyst reference row stays good/good/good/bad for all wordings.

Grid cells reuse the June sweep's endorsement conditions verbatim
(``defeasible-explicit-v1`` prompt, n_samples=3, temperature 0,
max_tokens 2048, majority vote). A thin default-frame addendum reruns
GPT-4.1 x 3 wordings under the July rendering-gradient cell's own config
(default-v1 prompt, plain rendering, n_samples=6, max_tokens=16, seed=7)
for like-for-like diffability with ``rendering_gradient_2026-07-02``.

Network-resilient by design: cells run in a bounded thread pool
(default 6 workers), each cell checkpoints its eta + run log on
completion, and ``--skip-completed`` resumes a interrupted sweep without
re-paying finished cells. Provider errors are recorded in-band (never
silent); the post-run gate reports any provider_error or budget-clipped
sample so affected cells can be re-run before analysis.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/physical_wording_sweep.py \
        --out experiments/results/stop_sign/physical_wording_2026-10-28 \
        [--skip-completed] [--max-parallel 6] [--only MODEL ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "experiments"))

from paraphrase_axis_triangulation import (  # noqa: E402
    DEFEASIBLE_PROMPT,
    MODELS,
    ModelSpec,
)

from infereval import __version__ as FRAMEWORK_VERSION  # noqa: E402
from infereval.benchmark import Benchmark  # noqa: E402
from infereval.evaluation import (  # noqa: E402
    EndorsementConfig,
    ProviderParams,
    evaluate,
)
from infereval.prompts import DEFAULT_VERIFICATION_PROMPT  # noqa: E402
from infereval.providers import get_provider  # noqa: E402

BENCHMARK_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"

#: The changed wording axis. ``intrinsic`` is gone; ``physical`` replaces it.
VARIANTS: dict[str, str] = {
    "original":   "$a$ is red",
    "physical":   "a's surface would reflect light predominantly in the "
                  "roughly 620–750 nm band when illuminated",
    "perceptual": "a visibly appears red",
}

#: delta(nr) rewording applied in ALL conditions (runtime swap; the bundled
#: benchmark file is untouched).
NR_EXPRESSION = "a is not made with retroreflective sheeting"
NR_EXPRESSION_OLD = "$a$ is not made with reflective material"

#: Roster: June's 13 models with one forced substitution — OpenRouter
#: retired qwen/qwen3-max on 2026-10-09 (404 at call time; the deprecation
#: notice names qwen3.8-max-0902 as successor; substitution user-approved
#: 2026-10-28). Any old-vs-new comparison for this slot is cross-MODEL.
_QWEN_OLD = next(m for m in MODELS if m.label == "qwen3-max")
QWEN_SUBSTITUTE = _QWEN_OLD._replace(
    label="qwen3.8-max", model_id="qwen/qwen3.8-max-0902"
)
SWEEP_MODELS = [
    QWEN_SUBSTITUTE if m.label == "qwen3-max" else m for m in MODELS
]

#: Per-model grid max_tokens overrides (default 2048). qwen3.8-max clipped
#: a sample at 2048 (reasoning-verbose family); per the cross-model
#: replication discipline the budget escalates uniformly for that model
#: and the acceptance gate stays at zero clipped samples.
GRID_MAX_TOKENS_DEFAULT = 2048
GRID_MAX_TOKENS: dict[str, int] = {"qwen3.8-max": 8192}

#: Thin default-frame addendum config — matches the July gradient cell
#: (support-plain) exactly so old-vs-new rows diff like for like.
THIN_MODEL_LABEL = "gpt-4.1"
THIN_N_SAMPLES = 6
THIN_MAX_TOKENS = 16
THIN_SEED = 7


def make_physical_benchmark(variant_name: str, ra_expression: str) -> Benchmark:
    """Stop-sign benchmark with delta(ra) per variant and delta(nr) reworded."""
    base = Benchmark.load(BENCHMARK_PATH).model_dump(mode="json")
    base["id"] = f"stop-sign-physw-{variant_name}"
    base["bearers"]["ra"]["expression"] = ra_expression
    base["bearers"]["nr"]["expression"] = NR_EXPRESSION
    return Benchmark.model_validate(base)


def _cell_done(eta_path: Path) -> bool:
    """A cell counts as complete only if its eta exists and loads cleanly."""
    if not eta_path.is_file():
        return False
    try:
        json.loads(eta_path.read_text())
        return True
    except (json.JSONDecodeError, OSError):
        return False


def run_grid_cell(
    spec: ModelSpec,
    variant_name: str,
    ra_expr: str,
    out_dir: Path,
    skip_completed: bool,
) -> tuple[str, str, float]:
    """One (model, wording) cell of the main grid. Returns (cell, status, secs)."""
    cell = f"{spec.label}-{variant_name}"
    eta_path = out_dir / f"{cell}.json"
    if skip_completed and _cell_done(eta_path):
        return cell, "skipped (complete)", 0.0
    provider = get_provider(spec.provider_name, spec.model_id, **spec.extra_kwargs)
    bench = make_physical_benchmark(variant_name, ra_expr)
    t0 = time.monotonic()
    eta = evaluate(
        bench,
        provider,
        config=EndorsementConfig(n_samples=3, question_form="support"),
        params=ProviderParams(
            temperature=0.0,
            max_tokens=GRID_MAX_TOKENS.get(spec.label, GRID_MAX_TOKENS_DEFAULT),
        ),
        verification_prompt=DEFEASIBLE_PROMPT,
        run_id=f"physw:{cell}",
        log_path=out_dir / f"{cell}.jsonl",
    )
    eta.dump(eta_path)
    return cell, "done", time.monotonic() - t0


def run_thin_cell(
    variant_name: str,
    ra_expr: str,
    out_dir: Path,
    skip_completed: bool,
) -> tuple[str, str, float]:
    """One thin default-frame cell (GPT-4.1, July gradient config)."""
    cell = f"thin-{THIN_MODEL_LABEL}-{variant_name}"
    eta_path = out_dir / f"{cell}.json"
    if skip_completed and _cell_done(eta_path):
        return cell, "skipped (complete)", 0.0
    spec = next(m for m in MODELS if m.label == THIN_MODEL_LABEL)
    provider = get_provider(spec.provider_name, spec.model_id, **spec.extra_kwargs)
    bench = make_physical_benchmark(variant_name, ra_expr)
    t0 = time.monotonic()
    eta = evaluate(
        bench,
        provider,
        config=EndorsementConfig(n_samples=THIN_N_SAMPLES, question_form="support"),
        params=ProviderParams(
            temperature=0.0, max_tokens=THIN_MAX_TOKENS, seed=THIN_SEED
        ),
        verification_prompt=DEFAULT_VERIFICATION_PROMPT,
        run_id=f"physw:{cell}",
        log_path=out_dir / f"{cell}.jsonl",
    )
    eta.dump(eta_path)
    return cell, "done", time.monotonic() - t0


def acceptance_gate(out_dir: Path) -> dict:
    """Scan every eta for provider errors and budget-clipped samples."""
    flagged: list[dict] = []
    n_etas = 0
    for eta_path in sorted(out_dir.glob("*.json")):
        if eta_path.name == "sweep_manifest.json":
            continue
        data = json.loads(eta_path.read_text())
        if "items" not in data:
            continue
        n_etas += 1
        for item in data["items"]:
            for s in item.get("samples", []):
                err = s.get("provider_error")
                clipped = s.get("parse_status") == "budget_clipped"
                if err or clipped:
                    flagged.append({
                        "eta": eta_path.name,
                        "item": item["id"],
                        "sample": s.get("sample_index"),
                        "provider_error": err,
                        "budget_clipped": clipped,
                    })
    return {"etas_scanned": n_etas, "flagged_samples": flagged}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-parallel", type=int, default=6)
    parser.add_argument("--skip-completed", action="store_true")
    parser.add_argument(
        "--only", action="append", default=[],
        help="Run only the named model(s) in the main grid (thin cells always run).",
    )
    args = parser.parse_args(argv)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = SWEEP_MODELS if not args.only else [
        m for m in SWEEP_MODELS if m.label in args.only
    ]
    if args.only and not selected:
        print(f"ERROR: no models match --only {args.only}", file=sys.stderr)
        return 2

    # Manifest first: the sweep's full configuration on disk before any call.
    manifest = {
        "sweep": "physical-wording",
        "date": "2026-10-28",
        "branch": "physical-wording",
        "framework_version": FRAMEWORK_VERSION,
        "benchmark_source": str(BENCHMARK_PATH.relative_to(REPO_ROOT)),
        "variants": VARIANTS,
        "nr_expression": NR_EXPRESSION,
        "nr_expression_replaced": NR_EXPRESSION_OLD,
        "model_substitutions": {
            "qwen3-max": "qwen3.8-max (qwen/qwen3.8-max-0902) — OpenRouter "
                         "retired qwen3-max 2026-10-09; cross-model slot",
        },
        "analyst_row": ["good", "good", "good", "bad"],
        "grid": {
            "models": [m.label for m in selected],
            "prompt": DEFEASIBLE_PROMPT.id,
            "n_samples": 3, "temperature": 0.0,
            "max_tokens": GRID_MAX_TOKENS_DEFAULT,
            "max_tokens_overrides": GRID_MAX_TOKENS,
        },
        "thin_addendum": {
            "model": THIN_MODEL_LABEL,
            "prompt": DEFAULT_VERIFICATION_PROMPT.id,
            "n_samples": THIN_N_SAMPLES, "temperature": 0.0,
            "max_tokens": THIN_MAX_TOKENS, "seed": THIN_SEED,
        },
    }
    (out_dir / "sweep_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    grid_cells = [
        (spec, vname, vexpr)
        for spec in selected
        for vname, vexpr in VARIANTS.items()
    ]
    thin_cells = list(VARIANTS.items())
    print(
        f"physical-wording sweep: {len(grid_cells)} grid cells "
        f"(x 12 calls) + {len(thin_cells)} thin cells, "
        f"max_parallel={args.max_parallel}, framework v{FRAMEWORK_VERSION}",
        flush=True,
    )

    t0 = time.monotonic()
    statuses: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.max_parallel) as pool:
        futures = {
            pool.submit(
                run_grid_cell, spec, vname, vexpr, out_dir, args.skip_completed
            ): f"{spec.label}-{vname}"
            for spec, vname, vexpr in grid_cells
        }
        futures.update({
            pool.submit(
                run_thin_cell, vname, vexpr, out_dir, args.skip_completed
            ): f"thin-{THIN_MODEL_LABEL}-{vname}"
            for vname, vexpr in thin_cells
        })
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                cell, status, secs = fut.result()
                statuses[cell] = status
                print(f"  [{len(statuses):3d}/{len(futures)}] {cell:40s} "
                      f"{status} ({secs:.1f}s)", flush=True)
            except Exception as exc:  # noqa: BLE001 -- keep sweeping; gate catches gaps
                statuses[label] = f"FAILED: {type(exc).__name__}: {exc}"
                print(f"  [{len(statuses):3d}/{len(futures)}] {label:40s} "
                      f"FAILED: {exc}", file=sys.stderr, flush=True)

    elapsed = time.monotonic() - t0
    failed = {c: s for c, s in statuses.items() if s.startswith("FAILED")}
    print(f"\nsweep wall time: {elapsed/60:.1f} min; "
          f"{len(failed)} failed cell(s)", flush=True)
    for cell, status in sorted(failed.items()):
        print(f"  {cell}: {status}", file=sys.stderr)

    gate = acceptance_gate(out_dir)
    (out_dir / "acceptance_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    n_flagged = len(gate["flagged_samples"])
    print(f"acceptance gate: {gate['etas_scanned']} etas scanned, "
          f"{n_flagged} flagged sample(s) "
          f"({'PASS' if not n_flagged and not failed else 'ATTENTION'})", flush=True)
    return 0 if not failed and not n_flagged else 1


if __name__ == "__main__":
    sys.exit(main())
