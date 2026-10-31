"""Stop-sign sweep: Simonelli's verbatim nr clause x four delta(ra) wordings.

Fresh 2026-10-31 capture. delta(nr) = "a is not made with a reflective
material or coating to reflect car headlights" (Simonelli's clause
verbatim, p. 15) in ALL conditions, replacing the 28 Oct sweep's
"retroreflective sheeting". Four conclusion wordings (original,
physical, physical-indicative, perceptual); analyst row good/good/
good/bad for every wording. 12 models (qwen3.8-max substitution carried
over; mistral-large excluded), defeasible-explicit-v1, temperature 0,
max_tokens 2048 (8192 qwen3.8-max), n_samples=5, majority 3-of-5 with
abstain tie-break, provider-error samples excluded by the aggregator.
Thin addendum: gpt-4.1 under default-v1 at the July gradient config
(n=6, max_tokens 16, seed 7), all four wordings.

Writes ONLY to its own --out directory. The manifest (written before
any call; ``--manifest-only`` stops there) records the two predictions
this capture tests. Per-cell checkpointing + --skip-completed resume;
acceptance gate (zero provider errors, zero clipped) written at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx  # noqa: F401 -- pre-import before worker threads (import race)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "experiments"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "scripts"))

from physical_wording_sweep import (  # noqa: E402
    SWEEP_MODELS,
    _provider_for,
    acceptance_gate,
)

from paraphrase_axis_triangulation import DEFEASIBLE_PROMPT  # noqa: E402

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

VARIANTS: dict[str, str] = {
    "original": "$a$ is red",
    "physical": "a's surface would reflect light predominantly in the "
                "roughly 620–750 nm band when illuminated",
    "physical-indicative": "a's surface reflects light predominantly in "
                           "the roughly 620–750 nm band",
    "perceptual": "a visibly appears red",
}

#: Simonelli's clause verbatim (p. 15), in ALL conditions.
NR_EXPRESSION = ("a is not made with a reflective material or coating to "
                 "reflect car headlights")

EXCLUDED = {"mistral-large"}
N_SAMPLES = 5
GRID_MAX_TOKENS_DEFAULT = 2048
GRID_MAX_TOKENS = {"qwen3.8-max": 8192,
                   # escalated 2026-10-31 after repeated clipped
                   # samples on the perceptual wording (2048 in the
                   # 28 Oct sweep — budget differs for cross-sweep
                   # diffs of this model):
                   "qwen3.6-flash": 4096}

THIN_MODEL_LABEL = "gpt-4.1"
THIN_N_SAMPLES = 6
THIN_MAX_TOKENS = 16
THIN_SEED = 7


def make_benchmark(variant_name: str, ra_expression: str) -> Benchmark:
    base = Benchmark.load(BENCHMARK_PATH).model_dump(mode="json")
    base["id"] = f"stop-sign-simnr-{variant_name}"
    base["bearers"]["ra"]["expression"] = ra_expression
    base["bearers"]["nr"]["expression"] = NR_EXPRESSION
    return Benchmark.model_validate(base)


def _cell_done(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        json.loads(path.read_text())
        return True
    except (json.JSONDecodeError, OSError):
        return False


def run_grid_cell(spec, variant: str, ra_expr: str, out: Path,
                  skip: bool) -> tuple[str, str, float]:
    cell = f"{spec.label}-{variant}"
    eta_path = out / f"{cell}.json"
    if skip and _cell_done(eta_path):
        return cell, "skipped (complete)", 0.0
    provider = _provider_for(spec)
    bench = make_benchmark(variant, ra_expr)
    t0 = time.monotonic()
    eta = evaluate(
        bench, provider,
        config=EndorsementConfig(n_samples=N_SAMPLES, question_form="support"),
        params=ProviderParams(
            temperature=0.0,
            max_tokens=GRID_MAX_TOKENS.get(spec.label, GRID_MAX_TOKENS_DEFAULT),
        ),
        verification_prompt=DEFEASIBLE_PROMPT,
        run_id=f"simnr:{cell}",
        log_path=out / f"{cell}.jsonl",
    )
    eta.dump(eta_path)
    return cell, "done", time.monotonic() - t0


def run_thin_cell(variant: str, ra_expr: str, out: Path,
                  skip: bool) -> tuple[str, str, float]:
    cell = f"thin-{THIN_MODEL_LABEL}-{variant}"
    eta_path = out / f"{cell}.json"
    if skip and _cell_done(eta_path):
        return cell, "skipped (complete)", 0.0
    spec = next(m for m in SWEEP_MODELS if m.label == THIN_MODEL_LABEL)
    provider = get_provider(spec.provider_name, spec.model_id,
                            **spec.extra_kwargs)
    bench = make_benchmark(variant, ra_expr)
    t0 = time.monotonic()
    eta = evaluate(
        bench, provider,
        config=EndorsementConfig(n_samples=THIN_N_SAMPLES,
                                 question_form="support"),
        params=ProviderParams(temperature=0.0, max_tokens=THIN_MAX_TOKENS,
                              seed=THIN_SEED),
        verification_prompt=DEFAULT_VERIFICATION_PROMPT,
        run_id=f"simnr:{cell}",
        log_path=out / f"{cell}.jsonl",
    )
    eta.dump(eta_path)
    return cell, "done", time.monotonic() - t0


def write_manifest(out: Path, labels: list[str]) -> Path:
    manifest = {
        "sweep": "simonelli-nr",
        "date": "2026-10-31",
        "branch": "physical-wording",
        "framework_version": FRAMEWORK_VERSION,
        "benchmark_source": str(BENCHMARK_PATH.relative_to(REPO_ROOT)),
        "variants": VARIANTS,
        "nr_expression": NR_EXPRESSION,
        "nr_expression_note": (
            "Simonelli's clause verbatim (p. 15); replaces the 28 Oct "
            "sweep's 'a is not made with retroreflective sheeting'. All "
            "other premises unchanged (sa, n, ba)."
        ),
        "analyst_row": ["good", "good", "good", "bad"],
        "grid": {
            "models": labels,
            "prompt": DEFEASIBLE_PROMPT.id,
            "n_samples": N_SAMPLES,
            "temperature": 0.0,
            "max_tokens": GRID_MAX_TOKENS_DEFAULT,
            "max_tokens_overrides": GRID_MAX_TOKENS,
            "majority": "3-of-5, abstain tie-break, provider-error "
                        "samples excluded",
        },
        "model_substitutions": {
            "qwen3-max": "qwen3.8-max (qwen/qwen3.8-max-0902) — OpenRouter "
                         "retired qwen3-max 2026-10-09; carried over from "
                         "the 28 Oct sweep; cross-model slot",
        },
        "excluded": sorted(EXCLUDED),
        "thin_addendum": {
            "model": THIN_MODEL_LABEL,
            "prompt": DEFAULT_VERIFICATION_PROMPT.id,
            "n_samples": THIN_N_SAMPLES, "temperature": 0.0,
            "max_tokens": THIN_MAX_TOKENS, "seed": THIN_SEED,
            "wordings": list(VARIANTS),
        },
        "predictions_under_test": [
            "(i) physical-indicative flips row-1 (nighttime addition) to "
            "bad for most models: dropping the subjunctive and 'when "
            "illuminated' makes present reflection, not disposition, the "
            "asserted content.",
            "(ii) the two G G G G cells under physical (gpt-5.4, "
            "mistral-small — kind-property reading surviving repainting) "
            "become G G G B under physical-indicative.",
        ],
        "budget_note": (
            "qwen3.6-flash escalated to 4096 mid-sweep (two clipped "
            "samples at 2048 on the perceptual wording); its 28 Oct "
            "cells ran at 2048, so budget differs for that model's "
            "cross-sweep comparisons."
        ),
        "logging_note": (
            "run.started endorsement_config.verification_prompt_id records "
            "the resolved prompt (defeasible-explicit-v1) in this sweep: "
            "the stamping fix merged in PR #104 is in the executing tree."
        ),
    }
    path = out / "sweep_manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-parallel", type=int, default=4)
    ap.add_argument("--skip-completed", action="store_true")
    ap.add_argument("--manifest-only", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    ref = json.loads(
        (REPO_ROOT / "experiments/results/stop_sign/physical_wording_2026-10-28"
         / "sweep_manifest.json").read_text())
    labels = [m for m in ref["grid"]["models"] if m not in EXCLUDED]
    if args.only:
        labels = [m for m in labels if m in args.only]

    manifest_path = write_manifest(out, labels)
    print(f"manifest written: {manifest_path}")
    if args.manifest_only:
        return 0

    grid = [(next(s for s in SWEEP_MODELS if s.label == m), v, e)
            for m in labels for v, e in VARIANTS.items()]
    thin = list(VARIANTS.items())
    print(f"simonelli-nr sweep: {len(grid)} grid cells (x {4 * N_SAMPLES} "
          f"calls) + {len(thin)} thin cells (x {4 * THIN_N_SAMPLES} calls), "
          f"max_parallel={args.max_parallel}, framework v{FRAMEWORK_VERSION}",
          flush=True)
    t0 = time.monotonic()
    statuses: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.max_parallel) as pool:
        futures = {
            pool.submit(run_grid_cell, s, v, e, out, args.skip_completed):
                f"{s.label}-{v}" for s, v, e in grid
        }
        futures.update({
            pool.submit(run_thin_cell, v, e, out, args.skip_completed):
                f"thin-{THIN_MODEL_LABEL}-{v}" for v, e in thin
        })
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                cell, status, secs = fut.result()
                statuses[cell] = status
                print(f"  [{len(statuses):3d}/{len(futures)}] {cell:42s} "
                      f"{status} ({secs:.1f}s)", flush=True)
            except Exception as exc:  # noqa: BLE001 -- gate catches gaps
                statuses[label] = f"FAILED: {exc}"
                print(f"  [{len(statuses):3d}/{len(futures)}] {label:42s} "
                      f"FAILED: {exc}", file=sys.stderr, flush=True)

    failed = {c: s for c, s in statuses.items() if s.startswith("FAILED")}
    print(f"\nsweep wall time: {(time.monotonic()-t0)/60:.1f} min; "
          f"{len(failed)} failed cell(s)", flush=True)
    gate = acceptance_gate(out)
    (out / "acceptance_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    n = len(gate["flagged_samples"])
    print(f"acceptance gate: {gate['etas_scanned']} etas scanned, {n} flagged "
          f"sample(s) ({'PASS' if not n and not failed else 'ATTENTION'})",
          flush=True)
    return 0 if not failed and not n else 1


if __name__ == "__main__":
    sys.exit(main())
