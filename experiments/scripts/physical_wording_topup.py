"""Top up the physical-wording sweep from n_samples=3 to n_samples=5.

File conventions (appending in place would corrupt both artifact kinds:
an eta is a single-run record — run_id, timestamps, config.n_samples,
recomputed majority — and a .jsonl is a single run's event stream whose
run.started declares its own n_samples):

- ``{cell}-topup.json`` / ``{cell}-topup.jsonl`` — the raw 2-sample
  capture (sample_index 0-1 as captured), its own run record.
- ``{cell}.n5.json`` — the merged 5-sample evaluation the analysis
  consumes: original samples 0-2 + top-up samples reindexed to 3-4,
  ``model_verdict`` and ``majority_vote`` recomputed 3-of-5 with the
  framework's own ``majority_vote`` (tie-break "abstain", provider-error
  samples excluded from the vote, empty vote set -> abstain), config
  ``n_samples`` set to 5. Original ``{cell}.json`` files are untouched.

Config identity is asserted per cell before any call: same benchmark
hash, same prompt id, same max_tokens profile. Everything is logged;
the sweep manifest gains a ``topup`` block and the logging-bug note.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx  # noqa: F401 -- pre-import: parallel first-use inside
# worker threads raced httpx's module init (partially-initialized
# AttributeError, 2026-10-28 top-up); importing it on the main thread
# before the pool spins up removes the race class.

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "experiments"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "scripts"))

from physical_wording_sweep import (  # noqa: E402
    GRID_MAX_TOKENS,
    GRID_MAX_TOKENS_DEFAULT,
    SWEEP_MODELS,
    VARIANTS,
    _provider_for,
    acceptance_gate,
    make_physical_benchmark,
)

from paraphrase_axis_triangulation import DEFEASIBLE_PROMPT  # noqa: E402

from infereval import __version__ as FRAMEWORK_VERSION  # noqa: E402
from infereval.endorsement import majority_vote  # noqa: E402
from infereval.evaluation import (  # noqa: E402
    EndorsementConfig,
    Evaluation,
    ProviderParams,
    canonical_benchmark_hash,
    evaluate,
)

EXCLUDED = {"mistral-large"}
TOPUP_N = 2  # samples 3 and 4


def merge_cell(orig: Evaluation, topup: Evaluation) -> Evaluation:
    """Merge a 3-sample eta with a 2-sample top-up into a 5-sample eta."""
    assert orig.benchmark_hash == topup.benchmark_hash, "benchmark hash drift"
    topup_items = {it.id: it for it in topup.items}
    new_items = []
    for it in orig.items:
        extra = topup_items[it.id]
        reindexed = [
            s.model_copy(update={"sample_index": 3 + i})
            for i, s in enumerate(extra.samples)
        ]
        samples = list(it.samples) + reindexed
        valid = [
            s.parsed_verdict for s in samples
            if getattr(s, "provider_error", None) is None
            and s.parsed_verdict is not None
        ]
        verdict, tie_broken = majority_vote(
            list(valid), tie_break=orig.endorsement_config.tie_break
        )
        counts = {v: sum(1 for x in valid if x == v) for v in set(valid)}
        mv_type = type(it.majority_vote)
        mv = mv_type(
            good=counts.get(type(verdict).GOOD, 0),
            bad=counts.get(type(verdict).BAD, 0),
            abstain=counts.get(type(verdict).ABSTAIN, 0),
            verdict=verdict,
            tie_broken=tie_broken,
        )
        new_items.append(it.model_copy(update={
            "samples": samples, "model_verdict": verdict, "majority_vote": mv,
        }))
    return orig.model_copy(update={
        "items": new_items,
        "endorsement_config": orig.endorsement_config.model_copy(
            update={"n_samples": 5}
        ),
        "id": f"{orig.id}+topup",
    })


def run_cell(label: str, variant: str, ra_expr: str, out: Path,
             skip_completed: bool) -> tuple[str, str, float]:
    cell = f"{label}-{variant}"
    n5_path = out / f"{cell}.n5.json"
    if skip_completed and n5_path.is_file():
        try:
            json.loads(n5_path.read_text())
            return cell, "skipped (complete)", 0.0
        except (json.JSONDecodeError, OSError):
            pass
    spec = next(m for m in SWEEP_MODELS if m.label == label)
    orig = Evaluation.load(out / f"{cell}.json")
    bench = make_physical_benchmark(variant, ra_expr)
    assert canonical_benchmark_hash(bench) == orig.benchmark_hash, (
        f"{cell}: reconstructed benchmark hash differs from the captured eta"
    )
    assert orig.endorsement_config.n_samples == 3, cell
    provider = _provider_for(spec)
    t0 = time.monotonic()
    topup = evaluate(
        bench,
        provider,
        config=EndorsementConfig(n_samples=TOPUP_N, question_form="support"),
        params=ProviderParams(
            temperature=0.0,
            max_tokens=GRID_MAX_TOKENS.get(label, GRID_MAX_TOKENS_DEFAULT),
        ),
        verification_prompt=DEFEASIBLE_PROMPT,
        run_id=f"physw-topup:{cell}",
        log_path=out / f"{cell}-topup.jsonl",
    )
    topup.dump(out / f"{cell}-topup.json")
    merged = merge_cell(orig, topup)
    merged.dump(n5_path)
    return cell, "done", time.monotonic() - t0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-parallel", type=int, default=4)
    ap.add_argument("--skip-completed", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    args = ap.parse_args(argv)
    out = args.out

    manifest_path = out / "sweep_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    labels = [m for m in manifest["grid"]["models"] if m not in EXCLUDED]
    if args.only:
        labels = [m for m in labels if m in args.only]

    manifest["topup"] = {
        "date": "2026-10-28",
        "n_samples": "3 -> 5 (2 appended as sample_index 3-4)",
        "files": "{cell}-topup.json/.jsonl raw capture; {cell}.n5.json merged "
                 "5-sample eta (analysis input); originals untouched",
        "majority": "3-of-5 via infereval.endorsement.majority_vote, "
                    "tie_break=abstain, provider-error samples excluded",
        "excluded": sorted(EXCLUDED),
    }
    manifest["_comment_logging_bug"] = (
        "Pre-topup .jsonl run.started events record "
        "endorsement_config.verification_prompt_id='default-v1' while the "
        "top-level verification_prompt_id (authoritative) and the system "
        "text are defeasible-explicit-v1: evaluate() stamped the resolved "
        "prompt id into the config only after the run. Fixed in "
        "evaluation.py on branch physical-wording before the top-up runs; "
        "existing logs deliberately left as captured."
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    cells = [(m, v, e) for m in labels for v, e in VARIANTS.items()]
    print(f"top-up: {len(cells)} cells x {4 * TOPUP_N} calls, "
          f"max_parallel={args.max_parallel}, framework v{FRAMEWORK_VERSION}",
          flush=True)
    t0 = time.monotonic()
    statuses: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=args.max_parallel) as pool:
        futures = {
            pool.submit(run_cell, m, v, e, out, args.skip_completed):
                f"{m}-{v}" for m, v, e in cells
        }
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                cell, status, secs = fut.result()
                statuses[cell] = status
                print(f"  [{len(statuses):3d}/{len(futures)}] {cell:36s} "
                      f"{status} ({secs:.1f}s)", flush=True)
            except Exception as exc:  # noqa: BLE001 -- gate catches gaps
                statuses[label] = f"FAILED: {exc}"
                print(f"  [{len(statuses):3d}/{len(futures)}] {label:36s} "
                      f"FAILED: {exc}", file=sys.stderr, flush=True)

    failed = {c: s for c, s in statuses.items() if s.startswith("FAILED")}
    print(f"\ntop-up wall time: {(time.monotonic()-t0)/60:.1f} min; "
          f"{len(failed)} failed cell(s)", flush=True)
    gate = acceptance_gate(out)
    (out / "acceptance_gate.json").write_text(json.dumps(gate, indent=2) + "\n")
    n_flagged = len(gate["flagged_samples"])
    print(f"acceptance gate: {gate['etas_scanned']} etas scanned, "
          f"{n_flagged} flagged sample(s) "
          f"({'PASS' if not n_flagged and not failed else 'ATTENTION'})",
          flush=True)
    return 0 if not failed and not n_flagged else 1


if __name__ == "__main__":
    sys.exit(main())
