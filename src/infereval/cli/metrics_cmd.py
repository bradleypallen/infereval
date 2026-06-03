"""``infereval metrics`` -- compute and report metrics from a saved evaluation.

Three output formats:

- ``text`` (default): plain prose summary for terminals.
- ``markdown``: tables suitable for embedding in reports.
- ``json``: machine-readable, the output of :meth:`MetricsReport.to_dict`.

Filters ``--by-tag`` and ``--by-rsr-target`` decompose the report by item
subset, matching the decomposition language of the paper, Section 4. Each
filter takes the same reference (``--reference``) which defaults to
analyst consensus.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from infereval.benchmark import Benchmark
from infereval.evaluation import Evaluation
from infereval.metrics import (
    MIN_K_FOR_SUBSAMPLING_CI,
    CellSummary,
    MetricsReport,
    SubsamplingNotApplicableError,
    WeightFn,
    analyst_reference,
    cell_summary,
    cohens_kappa,
    consensus_reference,
    fleiss_kappa,
    margin_weight,
    subsampling_kappa_ci,
)
from infereval.types import Verdict

log = logging.getLogger(__name__)


FORMAT_CHOICES = ["text", "markdown", "json"]


def _parse_reference(spec: str, report: MetricsReport) -> tuple[str, object]:
    """Parse ``--reference`` spec into (label, ReferenceFn).

    ``consensus``      -> analyst consensus :math:`c_i`
    ``analyst:<id>``   -> single analyst by id (requires benchmark)
    ``analyst:<idx>``  -> single analyst by 0-based index
    """
    if spec == "consensus":
        return "consensus", consensus_reference(report.eta)
    if spec.startswith("analyst:"):
        rest = spec.removeprefix("analyst:")
        # Try numeric index first
        try:
            idx = int(rest)
        except ValueError:
            if report.benchmark is None:
                raise click.UsageError(
                    f"--reference analyst:{rest!r} requires --benchmark to resolve the analyst id"
                ) from None
            idx = report.benchmark.analyst_index(rest)
        return f"analyst[{idx}]", analyst_reference(report.eta, idx)
    raise click.UsageError(
        f"Unknown reference spec {spec!r}. Use 'consensus' or 'analyst:<id>' / 'analyst:<index>'."
    )


def _format_kappa(value: float | None) -> str:
    return "undefined" if value is None else f"{value:+.4f}"


def _format_ci(ci: tuple[float, float, float] | None) -> str:
    """Render the CI as ``[lo, hi]`` (one decimal place per the κ format)."""
    if ci is None:
        return ""
    _, lo, hi = ci
    return f" [{lo:+.4f}, {hi:+.4f}]"


def _is_decomposition_title(title: str | None) -> bool:
    """A title designates a decomposition cell (under-powered guard applies)
    when it begins with ``By tag:`` or ``By RSR target``. The ``Overall``
    headline is excluded (it has its own ``--ci`` reliability machinery)."""
    if title is None:
        return False
    return title.startswith("By tag:") or title.startswith("By RSR target")


def _under_powered_suffix(cell_sum: CellSummary | None) -> str:
    """Append ``  [under-powered: n < 10]`` to the κ value rendering when
    the cell is below :data:`MIN_K_FOR_SUBSAMPLING_CI`. Empty otherwise."""
    if cell_sum is None or not cell_sum.is_under_powered:
        return ""
    return f"  [under-powered: n < {MIN_K_FOR_SUBSAMPLING_CI}]"


def _format_class_counts(counts: dict[Verdict, int]) -> str:
    return (
        f"good {counts[Verdict.GOOD]} / "
        f"bad {counts[Verdict.BAD]} / "
        f"abstain {counts[Verdict.ABSTAIN]}"
    )


def _format_text(
    report: MetricsReport,
    reference_label: str,
    kappa_C: float | None,
    *,
    title: str | None = None,
    kappa_C_ci: tuple[float, float, float] | None = None,
    kappa_F_ci: tuple[float, float, float] | None = None,
    cell_sum: CellSummary | None = None,
) -> str:
    lines: list[str] = []
    if title:
        lines.append(title)
        lines.append("=" * len(title))
    lines.append(f"n (items)              : {report.n}")
    lines.append(f"coverage (M)           : {report.coverage:.4f}")
    cov_per = report.coverage_per_analyst
    if cov_per:
        lines.append(
            "coverage (per analyst) : " + ", ".join(f"{c:.4f}" for c in cov_per)
        )
    if cell_sum is not None:
        lines.append(f"n (substantive)        : {cell_sum.n_substantive}")
        lines.append(
            f"M verdicts             : {_format_class_counts(cell_sum.m_counts)}"
        )
        lines.append(
            f"reference verdicts     : {_format_class_counts(cell_sum.r_counts)}"
        )
    suffix = _under_powered_suffix(cell_sum)
    lines.append(
        f"κ_C(η, {reference_label})       : "
        f"{_format_kappa(kappa_C)}{_format_ci(kappa_C_ci)}{suffix}"
    )
    lines.append(
        f"κ_F(η)                 : "
        f"{_format_kappa(report.fleiss_kappa)}{_format_ci(kappa_F_ci)}{suffix}"
    )
    lines.append(
        f"κ_F*(β) (inter-analyst, all): "
        f"{_format_kappa(report.inter_analyst_fleiss)}"
    )
    return "\n".join(lines)


def _format_markdown(
    report: MetricsReport,
    reference_label: str,
    kappa_C: float | None,
    *,
    title: str | None = None,
    kappa_C_ci: tuple[float, float, float] | None = None,
    kappa_F_ci: tuple[float, float, float] | None = None,
    cell_sum: CellSummary | None = None,
) -> str:
    lines: list[str] = []
    if title:
        lines.append(f"## {title}")
        lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| n | {report.n} |")
    lines.append(f"| coverage(M) | {report.coverage:.4f} |")
    cov_per = report.coverage_per_analyst
    if cov_per:
        per = ", ".join(f"{c:.4f}" for c in cov_per)
        lines.append(f"| coverage per analyst | {per} |")
    if cell_sum is not None:
        lines.append(f"| n (substantive) | {cell_sum.n_substantive} |")
        lines.append(
            f"| M verdicts | {_format_class_counts(cell_sum.m_counts)} |"
        )
        lines.append(
            f"| reference verdicts | {_format_class_counts(cell_sum.r_counts)} |"
        )
    suffix = _under_powered_suffix(cell_sum)
    lines.append(
        f"| κ_C(η, {reference_label}) | "
        f"{_format_kappa(kappa_C)}{_format_ci(kappa_C_ci)}{suffix} |"
    )
    lines.append(
        f"| κ_F(η) | "
        f"{_format_kappa(report.fleiss_kappa)}{_format_ci(kappa_F_ci)}{suffix} |"
    )
    lines.append(
        f"| κ_F*(β) (all analysts) | {_format_kappa(report.inter_analyst_fleiss)} |"
    )
    return "\n".join(lines)


def _format_json(
    report: MetricsReport,
    reference_label: str,
    kappa_C: float | None,
    *,
    title: str | None = None,
    kappa_C_ci: tuple[float, float, float] | None = None,
    kappa_F_ci: tuple[float, float, float] | None = None,
    cell_sum: CellSummary | None = None,
) -> str:
    out = report.to_dict()
    # Replace cohens_kappa_consensus with the actual reference label used.
    out.pop("cohens_kappa_consensus", None)
    out[f"cohens_kappa[{reference_label}]"] = kappa_C
    if kappa_C_ci is not None:
        _, lo, hi = kappa_C_ci
        out[f"cohens_kappa[{reference_label}]_ci"] = {"lo": lo, "hi": hi}
    if kappa_F_ci is not None:
        _, lo, hi = kappa_F_ci
        out["fleiss_kappa_ci"] = {"lo": lo, "hi": hi}
    if cell_sum is not None:
        out["n_substantive"] = cell_sum.n_substantive
        out["m_counts"] = {v.value: c for v, c in cell_sum.m_counts.items()}
        out["r_counts"] = {v.value: c for v, c in cell_sum.r_counts.items()}
        out["under_powered"] = cell_sum.is_under_powered
        out["under_powered_threshold"] = MIN_K_FOR_SUBSAMPLING_CI
    if title is not None:
        out["title"] = title
    return json.dumps(out, indent=2)


def _emit(
    report: MetricsReport,
    reference_label: str,
    reference_fn: object,
    output_format: str,
    *,
    title: str | None = None,
    weights: WeightFn | None = None,
    ci: bool = False,
    ci_iterations: int = 1000,
    ci_subsample_size: int | None = None,
    ci_seed: int | None = None,
) -> None:
    kappa_C = cohens_kappa(
        report.eta, reference_fn, weights=weights  # type: ignore[arg-type]
    )

    # Per-cell summary on decomposition cells (issue #84, v0.8.0).
    # The Overall headline already has --ci for reliability; no need to
    # double-count. The reference here is the same reference the κ_C value
    # above is computed against, so substantive_index matches.
    cell_sum: CellSummary | None = None
    if _is_decomposition_title(title):
        cell_sum = cell_summary(report.eta, reference_fn)  # type: ignore[arg-type]
        if cell_sum.is_under_powered:
            log.info(
                "metrics.cli.under_powered_cell title=%r n_substantive=%d "
                "threshold=%d kappa_C=%s kappa_F=%s",
                title,
                cell_sum.n_substantive,
                MIN_K_FOR_SUBSAMPLING_CI,
                cell_sum.cohens_kappa,
                cell_sum.fleiss_kappa,
            )

    kappa_C_ci: tuple[float, float, float] | None = None
    kappa_F_ci: tuple[float, float, float] | None = None
    if ci:
        try:
            kappa_C_ci = subsampling_kappa_ci(
                lambda e: cohens_kappa(e, reference_fn, weights=weights),  # type: ignore[arg-type]
                report.eta,
                iterations=ci_iterations,
                subsample_size=ci_subsample_size,
                seed=ci_seed,
            )
        except SubsamplingNotApplicableError as exc:
            click.echo(f"NOTE: κ_C CI not computed — {exc}", err=True)
        except ValueError as exc:
            click.echo(f"NOTE: κ_C CI not computed — {exc}", err=True)
        try:
            kappa_F_ci = subsampling_kappa_ci(
                lambda e: fleiss_kappa(e, weights=weights),
                report.eta,
                iterations=ci_iterations,
                subsample_size=ci_subsample_size,
                seed=ci_seed,
            )
        except (SubsamplingNotApplicableError, ValueError) as exc:
            click.echo(f"NOTE: κ_F CI not computed — {exc}", err=True)

    if output_format == "text":
        click.echo(
            _format_text(
                report, reference_label, kappa_C, title=title,
                kappa_C_ci=kappa_C_ci, kappa_F_ci=kappa_F_ci,
                cell_sum=cell_sum,
            )
        )
    elif output_format == "markdown":
        click.echo(
            _format_markdown(
                report, reference_label, kappa_C, title=title,
                kappa_C_ci=kappa_C_ci, kappa_F_ci=kappa_F_ci,
                cell_sum=cell_sum,
            )
        )
    elif output_format == "json":
        click.echo(
            _format_json(
                report, reference_label, kappa_C, title=title,
                kappa_C_ci=kappa_C_ci, kappa_F_ci=kappa_F_ci,
                cell_sum=cell_sum,
            )
        )
    else:  # pragma: no cover -- defended by click.Choice
        raise click.UsageError(f"Unknown format {output_format!r}")


@click.command("metrics", help="Compute metrics from an evaluation JSON file.")
@click.argument("evaluation_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--benchmark",
    "benchmark_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Benchmark JSON. Required for --by-rsr-target, analyst-id references, and named coverage.",
)
@click.option(
    "--reference",
    "reference_spec",
    type=str,
    default="consensus",
    show_default=True,
    help="Reference for Cohen's kappa: 'consensus' or 'analyst:<id>' / 'analyst:<index>'.",
)
@click.option(
    "--by-tag",
    "tags",
    type=str,
    multiple=True,
    help="Repeat to add a per-tag decomposition.",
)
@click.option(
    "--by-rsr-target",
    "rsr_target_json",
    type=str,
    default=None,
    help='JSON of {"X": [...], "A": [...]} bearer-id sets. Requires --benchmark.',
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(FORMAT_CHOICES),
    default="text",
    show_default=True,
)
@click.option(
    "--ci",
    "report_ci",
    is_flag=True,
    default=False,
    help=(
        "Report Politis-Romano (1994) subsampling confidence intervals on "
        "κ_C and κ_F alongside the point estimates. Requires benchmark "
        "size K >= 10."
    ),
)
@click.option(
    "--ci-iterations",
    type=int,
    default=1000,
    show_default=True,
    help="Number of subsamples drawn for the --ci procedure.",
)
@click.option(
    "--ci-subsample-size",
    type=int,
    default=None,
    help=(
        "Items per subsample. Default round(K^0.7) per Politis-Romano "
        "rule of thumb (b/K -> 0, b -> inf as K -> inf)."
    ),
)
@click.option(
    "--ci-seed",
    type=int,
    default=None,
    help="Optional seed for reproducible CI computation.",
)
@click.option(
    "--weight-by-margin",
    is_flag=True,
    default=False,
    help=(
        "Compute κ_C and κ_F with per-item weights equal to the "
        "plurality margin of the model's sample distribution. Down-weights "
        "thin-margin items so 3/5 agreements count less than 5/5. Off by "
        "default — the unweighted κ remains the headline number."
    ),
)
def metrics_cmd(
    evaluation_path: Path,
    benchmark_path: Path | None,
    reference_spec: str,
    tags: tuple[str, ...],
    rsr_target_json: str | None,
    output_format: str,
    report_ci: bool,
    ci_iterations: int,
    ci_subsample_size: int | None,
    ci_seed: int | None,
    weight_by_margin: bool,
) -> None:
    """Compute and print metrics from a saved evaluation."""
    log.info("metrics.cli.start evaluation=%s benchmark=%s", evaluation_path, benchmark_path)

    try:
        eta = Evaluation.load(evaluation_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load evaluation: {exc}", err=True)
        sys.exit(2)

    bench: Benchmark | None = None
    if benchmark_path is not None:
        try:
            bench = Benchmark.load(benchmark_path)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
            sys.exit(2)

    report = MetricsReport(eta=eta, benchmark=bench)
    reference_label, reference_fn = _parse_reference(reference_spec, report)
    weights: WeightFn | None = margin_weight if weight_by_margin else None
    if weight_by_margin:
        reference_label = f"{reference_label},margin-weighted"

    # Overall
    _emit(
        report, reference_label, reference_fn, output_format, title="Overall",
        weights=weights, ci=report_ci, ci_iterations=ci_iterations,
        ci_subsample_size=ci_subsample_size, ci_seed=ci_seed,
    )

    # By tag
    for tag in tags:
        click.echo("")
        sub = report.by_tag(tag)
        sub_label, sub_ref = _parse_reference(reference_spec, sub)
        if weight_by_margin:
            sub_label = f"{sub_label},margin-weighted"
        _emit(
            sub, sub_label, sub_ref, output_format, title=f"By tag: {tag}",
            weights=weights, ci=report_ci, ci_iterations=ci_iterations,
            ci_subsample_size=ci_subsample_size, ci_seed=ci_seed,
        )

    # By rsr-target
    if rsr_target_json is not None:
        if bench is None:
            click.echo(
                "ERROR: --by-rsr-target requires --benchmark to read rsr_target fields.",
                err=True,
            )
            sys.exit(2)
        try:
            spec = json.loads(rsr_target_json)
            X = frozenset(spec["X"])
            A = frozenset(spec["A"])
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            click.echo(
                f"ERROR: --by-rsr-target must be JSON like "
                f'\'{{"X": ["sa"], "A": ["ra"]}}\': {exc}',
                err=True,
            )
            sys.exit(2)
        click.echo("")
        sub = report.by_rsr_target(X, A)
        sub_label, sub_ref = _parse_reference(reference_spec, sub)
        if weight_by_margin:
            sub_label = f"{sub_label},margin-weighted"
        title = f"By RSR target: ⟨{{{','.join(sorted(X))}}}, {{{','.join(sorted(A))}}}⟩"
        _emit(
            sub, sub_label, sub_ref, output_format, title=title,
            weights=weights, ci=report_ci, ci_iterations=ci_iterations,
            ci_subsample_size=ci_subsample_size, ci_seed=ci_seed,
        )

    log.info("metrics.cli.done evaluation=%s", evaluation_path)
