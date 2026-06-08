"""``infereval audit`` — scan an evaluation (eta) JSON for silent-failure
samples and report recomputed reliability metrics with them excluded.

Motivation: v0.14.0 and earlier had a silent-empty-response bug where
provider HTTP failures (rate-limit, 5xx) that returned an empty body got
parsed by the endorsement regex as ABSTAIN. The corresponding
:class:`SampleRecord` looked indistinguishable from a real model
abstention, and the κ_C / coverage metrics computed from such cells
silently treated instrument failures as model behaviour.

v0.15.0 fixes the bug at capture time (see ``provider_error`` field on
:class:`infereval.evaluation.SampleRecord`). This command audits etas
captured before the fix using a heuristic — a sample is flagged as a
suspected silent failure when:

  parsed_verdict == ABSTAIN AND
  (raw_response stripped is empty OR wall_time_ms in (0, None))

A successful real-model ABSTAIN produces non-trivial wall_time_ms and
typically a non-empty ``raw_response`` (the explanation tokens the
model emitted before the verdict token). The heuristic over-flags on
some genuinely-fast pure-token-output ABSTAINs but under-flags is much
worse for the audit use case, so we err on the side of flagging.

Etas captured *with* the v0.15.0 fix carry ``provider_error`` directly,
which the audit reports as a known failure (no heuristic needed).

Output: a per-item breakdown of flagged samples + recomputed coverage
and κ_C with flagged items excluded.

See ``KNOWN_ISSUES_v0.14.0.md`` for the underlying bug analysis.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

from infereval.evaluation import Evaluation, SampleRecord
from infereval.metrics import (
    cohens_kappa,
    consensus_reference,
    coverage,
)
from infereval.types import Verdict

log = logging.getLogger(__name__)


def _is_suspected_silent_failure(sample: SampleRecord) -> bool:
    """Heuristic detector for v0.14.0-era silent provider failures.

    True when the sample's parsed_verdict is ABSTAIN AND the sample
    looks instrument-failed: empty/whitespace ``raw_response`` OR
    near-zero ``wall_time_ms``. See module docstring for rationale.
    """
    if sample.parsed_verdict != Verdict.ABSTAIN:
        return False
    raw = (sample.raw_response or "").strip()
    if not raw:
        return True
    wt = sample.wall_time_ms
    return wt is None or wt == 0


def _is_known_failure(sample: SampleRecord) -> bool:
    """True for v0.15.0+ samples that explicitly carry ``provider_error``."""
    return sample.provider_error is not None


def _audit_item(item) -> tuple[int, int, int]:  # noqa: ANN001 -- EvaluationItem
    """Return ``(n_samples, n_known_failures, n_suspected_failures)`` for ``item``."""
    known = 0
    suspected = 0
    for s in item.samples:
        if _is_known_failure(s):
            known += 1
        elif _is_suspected_silent_failure(s):
            suspected += 1
    return len(item.samples), known, suspected


def _recompute_with_failures_excluded(eta: Evaluation) -> tuple[float, float | None]:
    """Recompute coverage and κ_C as if failed samples had been correctly
    excluded at capture time.

    Approach: rebuild each item's majority vote from the non-failed
    samples and substitute the resulting ``model_verdict``. If all of an
    item's samples are failed, the item's recomputed verdict becomes
    ABSTAIN (preserving the v0.15.0 behaviour where an all-failed item
    falls through the empty-list contract of ``majority_vote``).

    Returns ``(recomputed_coverage, recomputed_kappa_c)`` — κ_C is
    ``None`` when the substantive subset is empty after the rebuild
    (the existing ``cohens_kappa`` contract).
    """
    from collections import Counter

    rebuilt_items = []
    for item in eta.items:
        valid_verdicts: list[Verdict] = []
        for s in item.samples:
            if _is_known_failure(s) or _is_suspected_silent_failure(s):
                continue
            valid_verdicts.append(s.parsed_verdict)
        if not valid_verdicts:
            new_verdict = Verdict.ABSTAIN
        else:
            counts = Counter(valid_verdicts)
            max_n = max(counts.values())
            top = [v for v in counts if counts[v] == max_n]
            if len(top) == 1:
                new_verdict = top[0]
            elif Verdict.ABSTAIN in top:
                new_verdict = Verdict.ABSTAIN
            else:
                # Pure GOOD/BAD tie: use the conservative default
                # (matches the framework's "abstain" tie-break default).
                new_verdict = Verdict.ABSTAIN
        # Build a shallow copy with model_verdict overridden.
        rebuilt_items.append(item.model_copy(update={"model_verdict": new_verdict}))
    rebuilt_eta = eta.model_copy(update={"items": rebuilt_items})
    cov = coverage(rebuilt_eta)
    ref = consensus_reference(rebuilt_eta)
    k = cohens_kappa(rebuilt_eta, ref)
    return cov, k


@click.command(
    "audit",
    help="Audit an evaluation (eta) JSON for silent-failure samples and "
    "report recomputed κ_C / coverage with them excluded. See "
    "KNOWN_ISSUES_v0.14.0.md for context on the v0.14.0 silent-failure bug.",
)
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit a JSON report instead of human-readable text.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Include per-item breakdown of flagged samples (text mode only).",
)
def audit_cmd(path: Path, as_json: bool, verbose: bool) -> None:
    """Audit ``path`` for silent provider failures.

    Exit code is always 0 — this is a diagnostic, not a gate. Use the
    output (coverage delta + κ_C delta) to decide whether the
    historical capture's published metrics need a retraction or
    re-computation note.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        eta = Evaluation.model_validate(raw)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: cannot load {path}: {exc}", err=True)
        raise click.exceptions.Exit(2) from exc

    total_samples = 0
    total_known = 0
    total_suspected = 0
    per_item: list[tuple[str, int, int, int]] = []
    for item in eta.items:
        n, k, s = _audit_item(item)
        total_samples += n
        total_known += k
        total_suspected += s
        if k or s:
            per_item.append((item.id, n, k, s))

    # Published metrics (as-is, from the eta).
    pub_coverage = coverage(eta)
    pub_kappa = cohens_kappa(eta, consensus_reference(eta))

    # Recomputed metrics with failed samples excluded.
    rec_coverage, rec_kappa = _recompute_with_failures_excluded(eta)

    if as_json:
        report = {
            "eta_path": str(path),
            "eta_id": eta.id,
            "benchmark_id": eta.benchmark_id,
            "model_id": eta.model.model_id,
            "n_items": len(eta.items),
            "n_samples_scanned": total_samples,
            "n_known_provider_errors": total_known,
            "n_suspected_silent_failures": total_suspected,
            "n_items_with_any_failure": len(per_item),
            "published": {
                "coverage": pub_coverage,
                "kappa_c": pub_kappa,
            },
            "recomputed_failures_excluded": {
                "coverage": rec_coverage,
                "kappa_c": rec_kappa,
            },
            "per_item_failures": [
                {
                    "id": iid,
                    "n_samples": n,
                    "known_provider_errors": k,
                    "suspected_silent_failures": s,
                }
                for (iid, n, k, s) in per_item
            ],
        }
        click.echo(json.dumps(report, indent=2, default=str))
        return

    # Human-readable text output.
    click.echo(f"infereval audit — {path}")
    click.echo(f"  eta id           : {eta.id}")
    click.echo(f"  benchmark id     : {eta.benchmark_id}")
    click.echo(f"  model id         : {eta.model.model_id}")
    click.echo(f"  items            : {len(eta.items)}")
    click.echo(f"  samples scanned  : {total_samples}")
    click.echo(f"  known provider errors    : {total_known}")
    click.echo(f"  suspected silent failures: {total_suspected}")
    click.echo(f"  items with any failure   : {len(per_item)}")
    click.echo("")
    click.echo("Reliability metrics (published vs recomputed):")
    click.echo(f"  coverage  published   : {pub_coverage:.4f}")
    click.echo(f"  coverage  recomputed  : {rec_coverage:.4f}")
    pub_k_str = "undefined" if pub_kappa is None else f"{pub_kappa:.4f}"
    rec_k_str = "undefined" if rec_kappa is None else f"{rec_kappa:.4f}"
    click.echo(f"  κ_C       published   : {pub_k_str}")
    click.echo(f"  κ_C       recomputed  : {rec_k_str}")
    if verbose and per_item:
        click.echo("")
        click.echo("Per-item failure breakdown (only items with flagged samples):")
        click.echo("  item_id                                  n  known  suspected")
        for iid, n, k, s in per_item:
            click.echo(f"  {iid:<40} {n:>3}  {k:>5}  {s:>9}")


__all__ = ["audit_cmd"]
