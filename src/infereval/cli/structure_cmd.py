"""``infereval structure <eta.json> --benchmark <bench.json>``.

CLI front-end for :mod:`infereval.structure`. Runs the three structural
coherence checks against a derived ⟨B, I_M⟩ and prints a human-readable
report. Phase 2.1 of the construct-validity infrastructure (R13).
"""

from __future__ import annotations

import logging
import sys
import textwrap
from pathlib import Path

import click

from infereval.benchmark import Benchmark
from infereval.evaluation import Evaluation
from infereval.structure import (
    DEFAULT_THIN_MARGIN_THRESHOLD,
    StructuralCheck,
    run_all_checks,
)

log = logging.getLogger(__name__)

_WRAP = 78


def _format_rate(check: StructuralCheck) -> str:
    if check.items_checked == 0:
        return "n/a (no items in scope)"
    pct = (check.items_satisfying / check.items_checked) * 100
    return f"{check.items_satisfying} / {check.items_checked} = {pct:.1f}%"


@click.command(
    "structure",
    help="Run structural coherence checks against an evaluation's derived ⟨B, I_M⟩.",
)
@click.argument(
    "evaluation_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--benchmark",
    "benchmark_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to the source benchmark JSON. Required because the "
    "structural checks need per-item rsr_target / role-tag metadata "
    "that isn't propagated into the evaluation file.",
)
@click.option(
    "--thin-margin-threshold",
    type=float,
    default=DEFAULT_THIN_MARGIN_THRESHOLD,
    show_default=True,
    help=(
        "Plurality-margin cutoff below which model-vs-analyst agreements "
        "are flagged as thin (could flip on a re-run). Catches 3/5 "
        "agreements at the default 0.4; raise to be stricter, lower to "
        "be more permissive."
    ),
)
def structure_cmd(
    evaluation_path: Path,
    benchmark_path: Path,
    thin_margin_threshold: float,
) -> None:
    """Run the three Phase 2.1 structural coherence checks and print the report."""
    log.info(
        "structure.cli.start evaluation=%s benchmark=%s",
        evaluation_path,
        benchmark_path,
    )

    try:
        evaluation = Evaluation.load(evaluation_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load evaluation: {exc}", err=True)
        sys.exit(2)

    try:
        benchmark = Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)

    if evaluation.benchmark_id != benchmark.id:
        click.echo(
            f"ERROR: evaluation references benchmark_id={evaluation.benchmark_id!r} "
            f"but the supplied --benchmark has id={benchmark.id!r}",
            err=True,
        )
        sys.exit(2)

    report = run_all_checks(
        evaluation, benchmark, thin_margin_threshold=thin_margin_threshold
    )

    click.echo("structural coherence report")
    click.echo("===========================")
    click.echo("")
    click.echo(f"evaluation:  {report.evaluation_id}")
    click.echo(f"benchmark:   {report.benchmark_id}")
    click.echo("")

    for check in report.checks:
        # Friendly section headers.
        if check.name == "containment_closure":
            click.echo("Containment closure:")
            if check.items_checked == 0:
                click.echo(
                    "  No self-implications (no item has Γ ∩ Δ ≠ ∅) — "
                    "check vacuously satisfied."
                )
            else:
                click.echo(
                    f"  Self-implications (Γ ∩ Δ ≠ ∅): {check.items_checked} item(s)"
                )
                click.echo(
                    "  All such items are in I_M by construction "
                    "(containment, clause i)."
                )
        elif check.name == "rsr_role_consistency":
            click.echo("RSR role consistency:")
            if check.items_checked == 0:
                click.echo(
                    "  No role-tagged items in scope "
                    "(need rsr_target + a base-inference reference)."
                )
            else:
                click.echo(f"  Role-consistent verdicts: {_format_rate(check)}")
                if check.anomalies:
                    click.echo(f"  Anomalies ({len(check.anomalies)}):")
                    for a in check.anomalies:
                        click.echo(
                            textwrap.fill(
                                f"    - {a.item_id}: expected {a.expected}, "
                                f"got {a.actual}. {a.explanation}",
                                width=_WRAP,
                                subsequent_indent="      ",
                                break_long_words=False,
                                break_on_hyphens=False,
                            )
                        )
        elif check.name == "base_case_stability":
            click.echo("Base-case stability:")
            if check.items_checked == 0:
                click.echo(
                    "  No target has multiple base-inference items — "
                    "check vacuously satisfied."
                )
            else:
                click.echo(
                    f"  Base-stable items: {_format_rate(check)}"
                )
                if check.anomalies:
                    click.echo(f"  Anomalies ({len(check.anomalies)}):")
                    for a in check.anomalies:
                        click.echo(
                            textwrap.fill(
                                f"    - {a.item_id}: {a.explanation}",
                                width=_WRAP,
                                subsequent_indent="      ",
                                break_long_words=False,
                                break_on_hyphens=False,
                            )
                        )
        elif check.name == "thin_margin_agreement":
            click.echo(
                f"Thin-margin agreements (threshold {thin_margin_threshold:.2f}):"
            )
            if check.items_checked == 0:
                click.echo(
                    "  No model-vs-analyst agreements in scope — "
                    "check vacuously satisfied."
                )
            else:
                click.echo(
                    f"  Confidently-supported agreements: {_format_rate(check)}"
                )
                if check.anomalies:
                    click.echo(
                        f"  Thin agreements ({len(check.anomalies)}, "
                        "could flip on a re-run):"
                    )
                    for a in check.anomalies:
                        click.echo(
                            textwrap.fill(
                                f"    - {a.item_id}: {a.actual}",
                                width=_WRAP,
                                subsequent_indent="      ",
                                break_long_words=False,
                                break_on_hyphens=False,
                            )
                        )
        click.echo("")

    if report.all_satisfied:
        click.echo("All structural checks passed.")
    else:
        click.echo(
            f"Structural anomalies: {report.total_anomalies} flagged. "
            "Review the lines above."
        )
    log.info("structure.cli.done anomalies=%d", report.total_anomalies)
