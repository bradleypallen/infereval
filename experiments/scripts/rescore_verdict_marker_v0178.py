"""v0.17.8: re-score stored captures under the marker-aware verdict parser.

Before v0.17.8, ``parse_verdict`` took the first GOOD/BAD/ABSTAIN token in a
response. claude-haiku-4.5 ignores the "No other text" instruction on the
stop-sign benchmark: it opens with a provisional token, reasons, and closes
with ``Verdict: <TOKEN>`` or a bare token on the final line. Where those
disagree, the first-match rule recorded the provisional token. v0.17.8 lets
the committed (closing) answer win.

This script makes **no provider calls**. It:

1. Scans every stored evaluation JSON under ``experiments/results/`` and
   re-parses each sample's ``raw_response`` with the v0.17.8 parser,
   reporting every sample whose parsed verdict changes (blast radius).
2. For the stop-sign R22 sweep (``experiments/results/stop_sign/retest/``),
   writes re-scored copies of every eta into
   ``experiments/results/stop_sign/retest_rescored_v0.17.8/<cell>/`` —
   originals are never modified — with recomputed ``parsed_verdict``,
   ``majority_vote`` and ``model_verdict``. Samples with ``provider_error``
   are left as-is and excluded from the vote, exactly as in
   :func:`infereval.endorsement.endorse`.
3. Recomputes κ_C against the analyst consensus for every capture and the
   multi-interval test–retest κ (eta-0 vs eta-1/2/3) for every cell, and
   writes ``rescore_report.json`` + ``rescore_report.md`` beside them.

All decisions are logged as JSONL to ``rescore.log.jsonl`` for post-run
analysis.

Usage::

    PYTHONPATH=src python experiments/scripts/rescore_verdict_marker_v0178.py
"""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

from infereval import __version__
from infereval.endorsement import majority_vote
from infereval.evaluation import Evaluation, MajorityVote
from infereval.logging_setup import configure_run_logging
from infereval.metrics import cohens_kappa, consensus_reference
from infereval.prompts import DEFAULT_PARSE_REGEX, parse_verdict
from infereval.retest import compute_retest
from infereval.types import Verdict

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "experiments" / "results"
SWEEP = RESULTS / "stop_sign" / "retest"
OUT = RESULTS / "stop_sign" / "retest_rescored_v0.17.8"
LETTER = {Verdict.GOOD: "G", Verdict.BAD: "B", Verdict.ABSTAIN: "A"}

log = logging.getLogger("infereval.experiments.rescore_v0178")


def _first_match(text: str, pattern: re.Pattern[str]) -> Verdict | None:
    m = pattern.search(text)
    if m is None:
        return None
    try:
        return Verdict(m.group(1).lower())
    except ValueError:
        return None


def blast_radius() -> list[dict[str, object]]:
    """Every stored sample whose verdict differs between first-match and v0.17.8."""
    pattern = re.compile(DEFAULT_PARSE_REGEX, re.IGNORECASE)
    changed: list[dict[str, object]] = []
    n_files = n_samples = 0
    for path in sorted(RESULTS.rglob("*.json")):
        if OUT in path.parents:
            continue
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict) or "items" not in data:
            continue
        n_files += 1
        for item in data["items"]:
            for s in item.get("samples") or []:
                raw = s.get("raw_response") or ""
                if not raw or s.get("provider_error"):
                    continue
                n_samples += 1
                old = _first_match(raw, pattern)
                new, _ = parse_verdict(raw)
                if old is not None and old != new:
                    rec = {
                        "file": str(path.relative_to(ROOT)),
                        "item": item["id"],
                        "sample_index": s["sample_index"],
                        "stored": s.get("parsed_verdict"),
                        "first_match": old.value,
                        "v0178": new.value,
                    }
                    changed.append(rec)
                    log.info("blast_radius.sample_changed", extra={"event": "sample_changed", **rec})
    log.info(
        "blast_radius.done",
        extra={"event": "blast_radius", "files": n_files, "samples": n_samples, "changed": len(changed)},
    )
    return changed


def rescore_eta(eta: Evaluation) -> tuple[Evaluation, list[dict[str, object]]]:
    """Return a re-scored copy of ``eta`` plus a list of per-item changes."""
    data = eta.model_dump(mode="json")
    tie_break = eta.endorsement_config.tie_break
    item_changes: list[dict[str, object]] = []
    for item in data["items"]:
        for s in item["samples"]:
            if s.get("provider_error") is not None:
                continue
            new, status = parse_verdict(s["raw_response"])
            s["parsed_verdict"] = new.value
            s["parse_status"] = status
        voting = [Verdict(s["parsed_verdict"]) for s in item["samples"] if s.get("provider_error") is None]
        final, tie_broken = majority_vote(voting, tie_break=tie_break)
        counts = Counter(voting)
        old_verdict = item["model_verdict"]
        item["majority_vote"] = MajorityVote(
            good=counts[Verdict.GOOD],
            bad=counts[Verdict.BAD],
            abstain=counts[Verdict.ABSTAIN],
            verdict=final,
            tie_broken=tie_broken,
        ).model_dump(mode="json")
        item["model_verdict"] = final.value
        if old_verdict != final.value:
            item_changes.append({"item": item["id"], "old": old_verdict, "new": final.value})
    return Evaluation.model_validate(data), item_changes


def row(eta: Evaluation) -> str:
    return " ".join(LETTER[Verdict(it.model_verdict)] for it in eta.items)


def kappa(eta: Evaluation) -> float | None:
    return cohens_kappa(eta, consensus_reference(eta))


def fmt(k: float | None) -> str:
    return "undefined" if k is None else f"{k:+.3f}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with configure_run_logging(
        OUT / "rescore.log.jsonl",
        run_id="rescore-v0.17.8",
        extra_context={"framework_version": __version__},
        logger_name="infereval",
    ):
        log.setLevel(logging.INFO)
        changed_samples = blast_radius()

        cells: list[dict[str, object]] = []
        for cell_dir in sorted(p for p in SWEEP.iterdir() if p.is_dir()):
            etas = sorted(cell_dir.glob("eta-[0-9].json"))
            if not etas:
                continue
            (OUT / cell_dir.name).mkdir(exist_ok=True)
            originals = [Evaluation.model_validate_json(p.read_text()) for p in etas]
            rescored: list[Evaluation] = []
            captures: list[dict[str, object]] = []
            for path, eta in zip(etas, originals, strict=True):
                new_eta, item_changes = rescore_eta(eta)
                rescored.append(new_eta)
                (OUT / cell_dir.name / path.name).write_text(new_eta.model_dump_json(indent=2))
                cap = {
                    "eta": path.name,
                    "row_before": row(eta),
                    "row_after": row(new_eta),
                    "kappa_c_before": kappa(eta),
                    "kappa_c_after": kappa(new_eta),
                    "item_changes": item_changes,
                }
                captures.append(cap)
                log.info(
                    "cell.capture",
                    extra={"event": "capture", "cell": cell_dir.name, **{k: v for k, v in cap.items() if k != "item_changes"}},
                )
            retest = []
            for j in range(1, len(originals)):
                retest.append(
                    {
                        "pair": f"eta-0 vs {etas[j].stem}",
                        "kappa_before": compute_retest(originals[0], originals[j]).test_retest_kappa,
                        "kappa_after": compute_retest(rescored[0], rescored[j]).test_retest_kappa,
                    }
                )
            cell = {
                "cell": cell_dir.name,
                "changed": any(c["item_changes"] for c in captures),
                "captures": captures,
                "retest": retest,
            }
            cells.append(cell)

        report = {
            "framework_version": __version__,
            "parser_rule": "last committed match ('Verdict:'-marked or alone on the final non-empty line), else first match",
            "blast_radius_changed_samples": changed_samples,
            "cells": cells,
        }
        (OUT / "rescore_report.json").write_text(json.dumps(report, indent=2))

        lines = [
            "# Re-score of the stop-sign R22 sweep under the v0.17.8 verdict parser",
            "",
            f"Framework {__version__}. No provider calls; stored `raw_response` re-parsed.",
            "Rule: the last *committed* verdict token wins — one preceded by an explicit `Verdict:` marker or standing alone on the response's last non-empty line; otherwise the first token (pre-v0.17.8 rule).",
            "",
            f"## Blast radius across all stored results: {len(changed_samples)} sample(s) change",
            "",
            "| file | item | sample | first-match | v0.17.8 |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| `{c['file']}` | {c['item']} | {c['sample_index']} | {c['first_match']} | {c['v0178']} |"
            for c in changed_samples
        ]
        lines += ["", "## Cells whose verdict rows change", ""]
        changed_cells = [c for c in cells if c["changed"]]
        if not changed_cells:
            lines.append("None.")
        for c in changed_cells:
            lines += [f"### {c['cell']}", "", "| capture | row before | row after | κ_C before | κ_C after |", "|---|---|---|---|---|"]
            for cap in c["captures"]:  # type: ignore[union-attr]
                lines.append(
                    f"| {cap['eta']} | {cap['row_before']} | {cap['row_after']} | "
                    f"{fmt(cap['kappa_c_before'])} | {fmt(cap['kappa_c_after'])} |"
                )
            lines += ["", "| retest pair | κ before | κ after |", "|---|---|---|"]
            for r in c["retest"]:  # type: ignore[union-attr]
                lines.append(f"| {r['pair']} | {fmt(r['kappa_before'])} | {fmt(r['kappa_after'])} |")
            lines.append("")
        lines += [
            f"All other {len(cells) - len(changed_cells)} cells: verdict rows and κ unchanged.",
            "",
        ]
        (OUT / "rescore_report.md").write_text("\n".join(lines))
        log.info(
            "rescore.done",
            extra={"event": "done", "cells": len(cells), "changed_cells": len(changed_cells)},
        )
    print((OUT / "rescore_report.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
