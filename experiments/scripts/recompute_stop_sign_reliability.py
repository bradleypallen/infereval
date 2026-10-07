"""Recompute the stop-sign R22 reliability figures from the stored etas.

Recomputes, for both the original captures (``stop_sign/retest/``) and the
v0.17.8 re-scored captures (``stop_sign/retest_rescored_v0.17.8/``):

- test–retest κ for every cell × interval pair (eta-0 vs eta-1/2/3) via
  :func:`infereval.retest.compute_retest`, binned as κ = 1, undefined,
  κ ∈ (0, 1), κ ≤ 0;
- the cells that are κ = 1 at every interval;
- the cells that are not, with their κ per interval;
- per-capture κ_C against the analyst consensus and verdict rows;
- provider-failure counts (samples with ``provider_error`` set).

No provider calls. Writes ``reliability_recompute.{json,md}`` and a JSONL log
into ``experiments/results/stop_sign/retest_rescored_v0.17.8/``.

Usage::

    PYTHONPATH=src python experiments/scripts/recompute_stop_sign_reliability.py
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

from infereval import __version__
from infereval.evaluation import Evaluation
from infereval.logging_setup import configure_run_logging
from infereval.metrics import cohens_kappa, consensus_reference
from infereval.retest import compute_retest
from infereval.types import Verdict

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "original": ROOT / "experiments" / "results" / "stop_sign" / "retest",
    "rescored_v0.17.8": ROOT / "experiments" / "results" / "stop_sign" / "retest_rescored_v0.17.8",
}
OUT = SOURCES["rescored_v0.17.8"]
LABELS = ["back-to-back", "1h", "day-out"]
LETTER = {Verdict.GOOD: "G", Verdict.BAD: "B", Verdict.ABSTAIN: "A"}

log = logging.getLogger("infereval.experiments.recompute_reliability")


def _bin(k: float | None) -> str:
    if k is None:
        return "undefined"
    if k >= 1.0 - 1e-9:
        return "kappa=1"
    if k <= 0.0:
        return "kappa<=0"
    return "0<kappa<1"


def analyse(source: str, root: Path) -> dict[str, object]:
    cells: list[dict[str, object]] = []
    bins: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    for cell_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        etas = [Evaluation.model_validate_json(p.read_text()) for p in sorted(cell_dir.glob("eta-[0-9].json"))]
        if len(etas) != 4:
            log.warning("cell has %d etas, expected 4", len(etas), extra={"event": "cell_skipped", "cell": cell_dir.name})
            continue
        kappas = [compute_retest(etas[0], etas[j]).test_retest_kappa for j in (1, 2, 3)]
        for k in kappas:
            bins[_bin(k)] += 1
        n_fail = sum(
            1 for eta in etas for it in eta.items for s in it.samples if s.provider_error is not None
        )
        failures[cell_dir.name] = n_fail
        rows = [" ".join(LETTER[Verdict(it.model_verdict)] for it in eta.items) for eta in etas]
        kc = [cohens_kappa(eta, consensus_reference(eta)) for eta in etas]
        cell = {
            "cell": cell_dir.name,
            "retest_kappa": dict(zip(LABELS, kappas, strict=True)),
            "perfect_everywhere": all(k is not None and k >= 1.0 - 1e-9 for k in kappas),
            "rows": rows,
            "kappa_c": kc,
            "provider_failures": n_fail,
        }
        cells.append(cell)
        log.info("cell", extra={"event": "cell", "source": source, **{k: v for k, v in cell.items() if k != "retest_kappa"}, "retest_kappa": kappas})
    n_pairs = sum(bins.values())
    return {
        "source": source,
        "n_cells": len(cells),
        "n_pairs": n_pairs,
        "bins": dict(bins),
        "perfect_cells": sum(1 for c in cells if c["perfect_everywhere"]),
        "non_perfect": [c for c in cells if not c["perfect_everywhere"]],
        "provider_failures_total": sum(failures.values()),
        "provider_failures_by_cell": {k: v for k, v in failures.items() if v},
        "cells": cells,
    }


def fmt(k: float | None) -> str:
    return "und" if k is None else f"{k:.3f}"


def main() -> int:
    with configure_run_logging(
        OUT / "reliability_recompute.log.jsonl",
        run_id="reliability-recompute",
        extra_context={"framework_version": __version__},
    ):
        log.setLevel(logging.INFO)
        results = {name: analyse(name, root) for name, root in SOURCES.items()}
        (OUT / "reliability_recompute.json").write_text(json.dumps(results, indent=2, default=str))

        lines = [
            "# Stop-sign R22 reliability, recomputed from stored etas",
            "",
            f"Framework {__version__}. No provider calls. Test–retest κ via `compute_retest` (eta-0 vs eta-1/2/3).",
            "",
            "| | original captures | re-scored (v0.17.8 parser) |",
            "|---|---:|---:|",
        ]
        o, r = results["original"], results["rescored_v0.17.8"]
        for key, label in [
            ("kappa=1", "κ = 1"),
            ("undefined", "κ undefined"),
            ("0<kappa<1", "κ ∈ (0, 1)"),
            ("kappa<=0", "κ ≤ 0"),
        ]:
            lines.append(f"| {label} | {o['bins'].get(key, 0)}/{o['n_pairs']} | {r['bins'].get(key, 0)}/{r['n_pairs']} |")
        lines += [
            f"| cells κ = 1 at every interval | {o['perfect_cells']}/{o['n_cells']} | {r['perfect_cells']}/{r['n_cells']} |",
            f"| samples with provider_error | {o['provider_failures_total']} | {r['provider_failures_total']} |",
            "",
            "## Cells not κ = 1 at every interval (re-scored)",
            "",
            "| cell | κ@back | κ@1h | κ@day | rows eta-0…3 |",
            "|---|---:|---:|---:|---|",
        ]
        for c in r["non_perfect"]:  # type: ignore[union-attr]
            k = c["retest_kappa"]
            lines.append(
                f"| {c['cell']} | {fmt(k['back-to-back'])} | {fmt(k['1h'])} | {fmt(k['day-out'])} | {' / '.join(c['rows'])} |"
            )
        lines += ["", "## Provider failures by cell", ""]
        lines += [f"- {cell}: {n}" for cell, n in r["provider_failures_by_cell"].items()]  # type: ignore[union-attr]
        lines.append("")
        (OUT / "reliability_recompute.md").write_text("\n".join(lines))
        log.info("done", extra={"event": "done"})
    print((OUT / "reliability_recompute.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
