"""infereval CLI entry point.

In M0 this provides only `--version`. Subcommands are wired in M2, M5, M6.
"""

from __future__ import annotations

import logging

import click

from infereval import __version__
from infereval.cli.describe_cmd import describe_cmd
from infereval.cli.evaluate_cmd import evaluate_cmd
from infereval.cli.metrics_cmd import metrics_cmd
from infereval.cli.model_cmd import model_cmd
from infereval.cli.report_cmd import report_cmd
from infereval.cli.retest_cmd import retest_cmd
from infereval.cli.structure_cmd import structure_cmd
from infereval.cli.survey_cmd import survey_group
from infereval.cli.sweep_cmd import sweep_cmd
from infereval.cli.validate_cmd import validate_cmd


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Inferentialist evaluation of LLMs (per Allen 2026).",
)
@click.version_option(__version__, "-V", "--version", prog_name="infereval")
def cli() -> None:
    """Top-level command group."""
    # CLI users get clean output by default; the metrics module emits
    # "undefined" reasons as WARNING-level logs that bloat terminal output.
    # M7 will replace this with proper structured logging.
    logging.getLogger("infereval.metrics").setLevel(logging.ERROR)
    logging.getLogger("infereval.providers").setLevel(logging.ERROR)


cli.add_command(validate_cmd)
cli.add_command(describe_cmd)
cli.add_command(evaluate_cmd)
cli.add_command(metrics_cmd)
cli.add_command(structure_cmd)
cli.add_command(model_cmd)
cli.add_command(sweep_cmd)
cli.add_command(retest_cmd)
cli.add_command(report_cmd)
cli.add_command(survey_group)


if __name__ == "__main__":
    cli()
