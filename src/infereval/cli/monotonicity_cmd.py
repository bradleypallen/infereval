"""``infereval monotonicity`` — score ordinal-ladder items of an evaluation.

Joins an evaluation :math:`\\eta` with its benchmark, scores every monotonicity
ladder (brief §12.2 rule: ``bad < good``, ``abstain`` a skipped gap, a violation
is a strict inversion), and renders the per-ladder verdict sequences plus a
model-verdict breakdown by variation type.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from infereval.benchmark import Benchmark
from infereval.evaluation import Evaluation
from infereval.monotonicity import render_markdown, score_all_ladders
from infereval.stratify import variation_breakdown

log = logging.getLogger(__name__)


@click.command("monotonicity", help="Score ordinal-ladder items of an evaluation.")
@click.argument("eta_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument(
    "benchmark_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--variation/--no-variation",
    default=True,
    help="Also print the model-verdict breakdown by variation type.",
)
def monotonicity_cmd(eta_path: Path, benchmark_path: Path, variation: bool) -> None:
    """Score the monotonicity ladders in ETA_PATH against BENCHMARK_PATH."""
    log.info("monotonicity.start eta=%s benchmark=%s", eta_path, benchmark_path)
    eta = Evaluation.load(eta_path)
    bench = Benchmark.load(benchmark_path)

    results = score_all_ladders(eta, bench)
    click.echo(render_markdown(results))

    if not results:
        return

    n_mono = sum(1 for r in results if r.status == "monotone")
    n_viol = sum(1 for r in results if r.status == "violated")
    n_insuf = sum(1 for r in results if r.status == "insufficient")
    click.echo(
        f"Ladders: {len(results)} "
        f"({n_mono} monotone, {n_viol} violated, {n_insuf} insufficient)"
    )
    if n_viol:
        # Non-zero exit so CI / scripts can gate on a monotonicity violation.
        log.warning("monotonicity.violations n=%d", n_viol)

    if variation:
        cells = variation_breakdown(eta, bench)
        click.echo("\n## Variation breakdown\n")
        click.echo("| variation | n | good | bad | abstain | coverage |")
        click.echo("|---|---|---|---|---|---|")
        for c in cells:
            click.echo(
                f"| {c.variation} | {c.n} | {c.good} | {c.bad} | {c.abstain} | "
                f"{c.coverage:.2f} |"
            )

    if n_viol:
        sys.exit(1)
    log.info("monotonicity.ok ladders=%d", len(results))
