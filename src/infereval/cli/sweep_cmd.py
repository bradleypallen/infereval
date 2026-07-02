"""``infereval sweep <benchmark.json> --vary <param> --values <list>``.

CLI front-end for :mod:`infereval.sweep`. Phase 2.3 of the
construct-validity infrastructure (R11: sensitivity analysis on free
parameters).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import cast

import click

from infereval.benchmark import Benchmark
from infereval.endorsement import QuestionForm
from infereval.evaluation import EndorsementConfig, ProviderParams, TieBreak
from infereval.providers import (
    ProviderConfigError,
    ProviderError,
    get_provider,
)
from infereval.sweep import SweepError, coerce_values, run_sweep
from infereval.templates import coherence_frame_for_id

log = logging.getLogger(__name__)


def _format_kappa(value: float | None) -> str:
    if value is None:
        return "undef"
    return f"{value:+.4f}"


@click.command("sweep", help="Sensitivity-analysis sweep over evaluation parameters.")
@click.argument(
    "benchmark_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--provider", "provider_name",
    type=click.Choice(["anthropic", "openai", "openrouter"]),
    required=True,
)
@click.option("--model", "model_id", type=str, required=True)
@click.option(
    "--out-dir", "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("./sweep-out"),
    show_default=True,
)
@click.option(
    "--vary", "parameter",
    type=click.Choice(["n_samples", "tie_break", "paraphrase_variant", "temperature"]),
    required=True,
    help="The parameter to sweep over.",
)
@click.option(
    "--values", "values_csv",
    type=str,
    required=True,
    help="Comma-separated list of values to sweep through. Type-coerced "
    "per --vary (int / float / tie-break literal).",
)
@click.option("--n-samples", type=click.IntRange(min=1), default=3, show_default=True,
              help="Baseline n_samples (ignored when --vary n_samples).")
@click.option("--temperature", type=float, default=1.0, show_default=True,
              help="Baseline temperature (ignored when --vary temperature).")
@click.option("--max-tokens", type=click.IntRange(min=1), default=1024, show_default=True)
@click.option("--tie-break",
              type=click.Choice(["abstain", "good", "bad", "first"]),
              default="abstain", show_default=True,
              help="Baseline tie_break (ignored when --vary tie_break).")
@click.option("--question-form",
              type=click.Choice(["support", "coherence"]),
              default="coherence", show_default=True,
              help="Logical question posed per item, held fixed across the sweep.")
@click.option("--coherence-frame", "coherence_frame_id", type=str, default=None,
              help="Coherence-frame id to elicit under, held fixed across the "
              "sweep (built-ins: thin-v1, defeasible-coherence-explicit-v1, "
              "defeasible-coherence-underdet-v1). Unknown ids fail before any "
              "provider call. Default: evaluate()'s normal frame resolution.")
@click.option("--strip-tex/--no-strip-tex", default=True, show_default=True)
@click.option("--run-id-prefix", type=str, default=None,
              help="Per-run id prefix; the swept parameter value is appended.")
@click.option("--http-referer", type=str, default=None,
              help="OpenRouter attribution: HTTP-Referer header.")
@click.option("--x-title", type=str, default=None,
              help="OpenRouter attribution: X-Title header.")
def sweep_cmd(
    benchmark_path: Path,
    provider_name: str,
    model_id: str,
    out_dir: Path,
    parameter: str,
    values_csv: str,
    n_samples: int,
    temperature: float,
    max_tokens: int,
    tie_break: str,
    question_form: str,
    coherence_frame_id: str | None,
    strip_tex: bool,
    run_id_prefix: str | None,
    http_referer: str | None,
    x_title: str | None,
) -> None:
    """Run the sweep and write per-value artifacts + an aggregate summary."""
    log.info(
        "sweep.cli.start benchmark=%s vary=%s out_dir=%s coherence_frame=%s",
        benchmark_path,
        parameter,
        out_dir,
        coherence_frame_id,
    )

    try:
        benchmark = Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)

    try:
        values = coerce_values(parameter, [v.strip() for v in values_csv.split(",")])
    except SweepError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)

    # Fail fast on an unknown frame id — before any provider client is
    # constructed or any sweep value is run.
    if coherence_frame_id is not None:
        try:
            coherence_frame_for_id(coherence_frame_id)
        except ValueError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(2)

    provider_kwargs: dict[str, object] = {}
    if provider_name.lower() == "openrouter":
        if http_referer is not None:
            provider_kwargs["http_referer"] = http_referer
        if x_title is not None:
            provider_kwargs["x_title"] = x_title
    try:
        provider = get_provider(provider_name, model_id, **provider_kwargs)
    except ProviderConfigError as exc:
        click.echo(f"ERROR: provider configuration: {exc}", err=True)
        sys.exit(2)

    base_config = EndorsementConfig(
        n_samples=n_samples,
        tie_break=cast(TieBreak, tie_break),
        question_form=cast(QuestionForm, question_form),
    )
    if coherence_frame_id is not None:
        # A non-default coherence_frame_id on an input config is an explicit
        # binding: evaluate() looks it up in the catalog and stamps the
        # resolved id into each per-value η it records.
        base_config = base_config.model_copy(
            update={"coherence_frame_id": coherence_frame_id}
        )
    base_params = ProviderParams(
        temperature=temperature,
        max_tokens=max_tokens,
    )

    try:
        result = run_sweep(
            benchmark,
            provider,
            parameter=parameter,
            values=values,
            out_dir=out_dir,
            config=base_config,
            params=base_params,
            run_id_prefix=run_id_prefix,
        )
    except (SweepError, ProviderError) as exc:
        click.echo(f"ERROR: sweep aborted: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: unexpected failure during sweep: {exc}", err=True)
        sys.exit(1)

    # Aggregate summary file.
    summary_path = out_dir / "sweep-summary.json"
    summary_obj = {
        "parameter": result.parameter,
        "benchmark_id": benchmark.id,
        "provider": provider_name,
        "model_id": model_id,
        "rows": [
            {
                "value": str(row.value),
                "coverage": row.coverage,
                "kappa_c": row.kappa_c,
                "kappa_f": row.kappa_f,
                "n_agreement": row.n_agreement,
                "n_total": row.n_total,
                "eta_path": str(row.eta_path),
            }
            for row in result.rows
        ],
        "kappa_c_range": result.kappa_c_range,
        "stability_verdict": result.stability_verdict,
    }
    summary_path.write_text(
        json.dumps(summary_obj, indent=2, default=str) + "\n", encoding="utf-8"
    )

    # Stdout table.
    click.echo(
        f"sensitivity sweep: {result.parameter} ∈ "
        f"{{{', '.join(str(r.value) for r in result.rows)}}}"
    )
    click.echo(f"benchmark: {benchmark.id}")
    click.echo(f"provider:  {provider_name}/{model_id}")
    click.echo("")

    # Header
    value_w = max(len(str(r.value)) for r in result.rows)
    value_w = max(value_w, len(result.parameter))
    click.echo(
        f"  {result.parameter.ljust(value_w)}  coverage   κ_C        κ_F        agreement"
    )
    for row in result.rows:
        kc = _format_kappa(row.kappa_c)
        kf = _format_kappa(row.kappa_f)
        agreement_pct = (row.n_agreement / row.n_total) * 100 if row.n_total else 0
        click.echo(
            f"  {str(row.value).ljust(value_w)}  "
            f"{row.coverage:.4f}     {kc}    {kf}    "
            f"{row.n_agreement}/{row.n_total} ({agreement_pct:.1f}%)"
        )
    click.echo("")
    click.echo(result.stability_verdict)
    click.echo("")
    click.echo(f"per-value artifacts: {out_dir}/")
    click.echo(f"summary file:        {summary_path}")
    log.info(
        "sweep.cli.done parameter=%s n_values=%d kappa_c_range=%r",
        result.parameter,
        len(result.rows),
        result.kappa_c_range,
    )
