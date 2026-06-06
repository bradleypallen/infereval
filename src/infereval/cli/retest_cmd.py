"""``infereval retest`` — test-retest reliability (R22).

Two modes:

- **Manual mode** (the historical shape):
  ``infereval retest <eta_a.json> <eta_b.json>`` — compares two
  evaluations the user has already produced. The user owns the two
  capture steps and the retest step is a third call.
- **Auto mode** (v0.11.0+):
  ``infereval retest --auto --benchmark <bench> --provider X --model Y``
  — calls :func:`infereval.evaluation.evaluate` twice internally with an
  optional inter-capture sleep, then runs the retest comparison in one
  shot. Collapses the historical three-step manual workflow into one
  CLI invocation so the R22 discipline can be made routine.

The emitted :class:`~infereval.retest.RetestResult` is the within-model
analog of κ_F* (the inter-analyst peer baseline): it quantifies how
much of the headline κ_C is shared signal across replications, vs.
how much is run-specific noise. Required at scope ≥
``domain_D_as_sampled`` per R22; informational at narrower scope.
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import click

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, Evaluation, ProviderParams, evaluate
from infereval.report import ConstructValidityClaims
from infereval.retest import (
    RetestConfigMismatchError,
    compute_retest,
    retest_result_to_dict,
)

if TYPE_CHECKING:
    from infereval.providers.base import Provider

log = logging.getLogger(__name__)

PROVIDER_CHOICES = ["anthropic", "openai", "openrouter"]
TIE_BREAK_CHOICES = ["abstain", "good", "bad", "first"]

#: Sentinel for ``--auto`` mode without an explicit run-id base — when
#: the user doesn't supply one, the two captures get
#: ``f"{uuid4()}-{a,b}"`` so they're stably distinguishable in logs.
_AUTO_RUN_ID_PREFIX = "retest-auto-"


@click.command(
    "retest",
    help=(
        "Compare two evaluations of the same benchmark to assess "
        "test-retest reliability (R22). With --auto, runs evaluate twice "
        "internally and computes the retest in one shot."
    ),
)
@click.argument(
    "eta_a_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
)
@click.argument(
    "eta_b_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
)
@click.option(
    "--auto",
    "auto",
    is_flag=True,
    default=False,
    help=(
        "Auto-evaluate mode. Run `infereval evaluate` twice against the "
        "supplied --benchmark / --provider / --model, then compute the "
        "retest from the two captures. Mutually exclusive with supplying "
        "two eta paths."
    ),
)
@click.option(
    "--benchmark",
    "benchmark_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Benchmark JSON. In auto mode this is the benchmark each "
        "capture evaluates against (required). In manual mode this is "
        "optional and used only for factor-level annotation of flipped "
        "items."
    ),
)
@click.option(
    "--claims",
    "claims_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Optional claims JSON (the same file consumed by `infereval "
        "report`). When supplied, the analyst's declared identity "
        "criterion (from `reliability.identity_criterion`) is "
        "threaded into the RetestResult so the test-retest κ travels "
        "with what it's reliability-of. Required at scope >= "
        "domain_D_as_sampled to satisfy R22."
    ),
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Optional path to persist the RetestResult JSON. The report "
        "renderer (`infereval report --retest`) consumes this artifact "
        "to surface test-retest κ in section 2 and flipped items in "
        "section 4b."
    ),
)
# --- auto-mode: provider / model + evaluate-shared flags ----------------
@click.option(
    "--provider",
    "provider_name",
    type=click.Choice(PROVIDER_CHOICES, case_sensitive=False),
    default=None,
    help="LLM provider for auto mode. Required with --auto.",
)
@click.option(
    "--model",
    "model_id",
    type=str,
    default=None,
    help="Provider-specific model id for auto mode. Required with --auto.",
)
@click.option("--n-samples", type=click.IntRange(min=1), default=5, show_default=True)
@click.option("--temperature", type=float, default=1.0, show_default=True)
@click.option("--max-tokens", type=click.IntRange(min=1), default=1024, show_default=True)
@click.option("--top-p", type=float, default=None)
@click.option(
    "--seed",
    type=int,
    default=None,
    help=(
        "Random seed for both auto-mode captures. Default (None) is "
        "intentional: the point of retest is to surface stochastic "
        "spread, so no seed means each capture samples freely. "
        "Supplying a seed pins both captures to the same RNG state, "
        "which on seed-honoring providers (OpenAI) collapses the spread "
        "to zero — useful for pipeline-validation only."
    ),
)
@click.option(
    "--tie-break",
    type=click.Choice(TIE_BREAK_CHOICES),
    default="abstain",
    show_default=True,
)
@click.option("--strip-tex/--no-strip-tex", default=True, show_default=True)
@click.option(
    "--http-referer",
    type=str,
    default=None,
    help="OpenRouter attribution: HTTP-Referer header (auto mode only).",
)
@click.option(
    "--x-title",
    type=str,
    default=None,
    help="OpenRouter attribution: X-Title header (auto mode only).",
)
@click.option(
    "--paraphrase-variant",
    "paraphrase_variant",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help=(
        "Paraphrase variant to evaluate in auto mode. Defaults to the "
        "canonical (variant 0). --paraphrase-cycle (from evaluate_cmd) "
        "is deliberately not exposed — retest measures variance within "
        "one variant, not across them."
    ),
)
# --- auto-mode: retest-specific flags -----------------------------------
@click.option(
    "--interval-s",
    "interval_s",
    type=click.IntRange(min=0),
    default=0,
    show_default=True,
    help=(
        "Wall-clock seconds to sleep between the two auto-mode "
        "captures. Default 0 (back-to-back) captures provider-side "
        "stochasticity + sampling noise. Larger values (60, 3600, "
        "86400, ...) capture caching effects, silent server-side "
        "updates, and longer-term drift."
    ),
)
@click.option(
    "--save-etas",
    "save_etas_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help=(
        "Auto mode only. Directory to persist the two captured etas. "
        "Default: write to a tmpdir which is removed after the retest "
        "is computed. Supply a real path for audit-grade reproducibility."
    ),
)
def retest_cmd(  # noqa: PLR0913 -- cumulative CLI option set
    eta_a_path: Path | None,
    eta_b_path: Path | None,
    auto: bool,
    benchmark_path: Path | None,
    claims_path: Path | None,
    output_path: Path | None,
    provider_name: str | None,
    model_id: str | None,
    n_samples: int,
    temperature: float,
    max_tokens: int,
    top_p: float | None,
    seed: int | None,
    tie_break: str,
    strip_tex: bool,
    http_referer: str | None,
    x_title: str | None,
    paraphrase_variant: int,
    interval_s: int,
    save_etas_dir: Path | None,
) -> None:
    """Run the test-retest comparison and print a summary."""
    # ---- Argument-shape validation: auto vs manual ----------------------
    if auto:
        if eta_a_path is not None or eta_b_path is not None:
            raise click.UsageError(
                "--auto is mutually exclusive with positional eta paths. "
                "In auto mode the framework runs evaluate twice internally; "
                "in manual mode you supply the two pre-computed etas."
            )
        if benchmark_path is None:
            raise click.UsageError(
                "--auto requires --benchmark to drive the two captures."
            )
        if provider_name is None or model_id is None:
            raise click.UsageError(
                "--auto requires --provider and --model to drive the two captures."
            )
    else:
        if eta_a_path is None or eta_b_path is None:
            raise click.UsageError(
                "Manual mode requires two positional eta paths "
                "(or pass --auto with --benchmark / --provider / --model)."
            )

    # ---- Manual mode: load both etas from disk --------------------------
    if not auto:
        assert eta_a_path is not None and eta_b_path is not None  # noqa: S101
        log.info(
            "retest.cli.manual.start eta_a=%s eta_b=%s benchmark=%s",
            eta_a_path, eta_b_path, benchmark_path,
        )
        try:
            eta_a = Evaluation.load(eta_a_path)
            eta_b = Evaluation.load(eta_b_path)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"ERROR: could not load evaluation: {exc}", err=True)
            sys.exit(2)
        bench = _maybe_load_benchmark(benchmark_path)

    # ---- Auto mode: run evaluate twice ----------------------------------
    else:
        assert benchmark_path is not None  # noqa: S101 -- validated above
        assert provider_name is not None and model_id is not None  # noqa: S101
        log.info(
            "retest.cli.auto.start benchmark=%s provider=%s model=%s interval_s=%d",
            benchmark_path, provider_name, model_id, interval_s,
        )
        try:
            bench = Benchmark.load(benchmark_path)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
            sys.exit(2)

        eta_a, eta_b = _run_auto_captures(
            benchmark=bench,
            provider_name=provider_name,
            model_id=model_id,
            n_samples=n_samples,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            seed=seed,
            tie_break=tie_break,
            strip_tex=strip_tex,
            http_referer=http_referer,
            x_title=x_title,
            paraphrase_variant=paraphrase_variant,
            interval_s=interval_s,
            save_etas_dir=save_etas_dir,
        )

    # ---- Identity criterion threading (v0.6.1) --------------------------
    identity_criterion = _maybe_load_identity_criterion(claims_path)

    # ---- Compute + emit --------------------------------------------------
    try:
        result = compute_retest(
            eta_a, eta_b, benchmark=bench, identity_criterion=identity_criterion
        )
    except RetestConfigMismatchError as exc:
        click.echo(f"ERROR: incompatible runs — {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: unexpected failure during retest: {exc}", err=True)
        sys.exit(1)

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(retest_result_to_dict(result), indent=2) + "\n",
            encoding="utf-8",
        )

    _print_summary(result)
    log.info(
        "retest.cli.done n=%d agree=%d flips=%d kappa=%s",
        result.n_items, result.n_agreements, result.n_disagreements,
        result.test_retest_kappa,
    )


# ---- Internal helpers ------------------------------------------------------


def _maybe_load_benchmark(benchmark_path: Path | None) -> Benchmark | None:
    if benchmark_path is None:
        return None
    try:
        return Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)


def _maybe_load_identity_criterion(claims_path: Path | None) -> Any:
    if claims_path is None:
        return None
    try:
        claims_raw = json.loads(claims_path.read_text(encoding="utf-8"))
        claims = ConstructValidityClaims.model_validate(claims_raw)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not parse claims file: {exc}", err=True)
        sys.exit(2)
    if claims.reliability is None:
        click.echo(
            "NOTE: --claims was supplied but the claims file does not "
            "declare reliability.identity_criterion; the retest will run "
            "without it, and the report's verdict gate may cap the "
            "verdict at scope >= domain_D_as_sampled.",
            err=True,
        )
        return None
    return claims.reliability.identity_criterion


def _run_auto_captures(
    *,
    benchmark: Benchmark,
    provider_name: str,
    model_id: str,
    n_samples: int,
    temperature: float,
    max_tokens: int,
    top_p: float | None,
    seed: int | None,
    tie_break: str,
    strip_tex: bool,
    http_referer: str | None,
    x_title: str | None,
    paraphrase_variant: int,
    interval_s: int,
    save_etas_dir: Path | None,
) -> tuple[Evaluation, Evaluation]:
    """Run :func:`evaluate` twice and persist the etas.

    Returns the two :class:`~infereval.evaluation.Evaluation` objects
    ready for :func:`compute_retest`.
    """
    # Local imports — keep CLI import cost low for the manual-mode path.
    from infereval.providers import get_provider
    from infereval.providers.base import ProviderConfigError, ProviderError

    # Build a single provider client and reuse it for both captures —
    # this models the realistic "same client, two requests" shape.
    provider_kwargs: dict[str, object] = {}
    if provider_name.lower() == "openrouter":
        if http_referer is not None:
            provider_kwargs["http_referer"] = http_referer
        if x_title is not None:
            provider_kwargs["x_title"] = x_title
    try:
        provider: Provider = get_provider(provider_name, model_id, **provider_kwargs)
    except ProviderConfigError as exc:
        click.echo(f"ERROR: provider configuration: {exc}", err=True)
        sys.exit(2)

    config = EndorsementConfig(
        n_samples=n_samples,
        tie_break=cast(Any, tie_break),  # Click choice string → TieBreak literal
    )
    params = ProviderParams(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        seed=seed,
    )

    # Auto-generate run ids per capture so the two etas are distinguishable
    # in logs and in the saved-etas directory.
    base_run_id = f"{_AUTO_RUN_ID_PREFIX}{uuid.uuid4().hex[:8]}"
    run_id_a = f"{base_run_id}-a"
    run_id_b = f"{base_run_id}-b"

    # Persist etas to either the user-supplied dir or a tmpdir.
    if save_etas_dir is not None:
        save_etas_dir.mkdir(parents=True, exist_ok=True)
        ctx = _NoopCtx(save_etas_dir)
    else:
        ctx = tempfile.TemporaryDirectory()  # type: ignore[assignment]

    with ctx as etas_dir_str:
        etas_dir = Path(etas_dir_str)
        eta_a_path = etas_dir / "eta-a.json"
        eta_b_path = etas_dir / "eta-b.json"
        log_a_path = etas_dir / "eta-a.run.jsonl"
        log_b_path = etas_dir / "eta-b.run.jsonl"

        click.echo(
            f"retest --auto: capture A starting "
            f"(benchmark={benchmark.id!r}, run_id={run_id_a!r})",
            err=True,
        )
        try:
            eta_a = evaluate(
                benchmark, provider,
                config=config, params=params,
                strip_tex=strip_tex, run_id=run_id_a,
                log_path=log_a_path, variant=paraphrase_variant,
            )
        except ProviderError as exc:
            click.echo(f"ERROR: provider error during capture A: {exc}", err=True)
            sys.exit(1)
        eta_a.dump(eta_a_path)
        log.info("retest.cli.auto.capture_a_done run_id=%s items=%d",
                 eta_a.id, eta_a.n)

        if interval_s > 0:
            click.echo(
                f"retest --auto: sleeping {interval_s}s between captures",
                err=True,
            )
            time.sleep(interval_s)

        click.echo(
            f"retest --auto: capture B starting (run_id={run_id_b!r})",
            err=True,
        )
        try:
            eta_b = evaluate(
                benchmark, provider,
                config=config, params=params,
                strip_tex=strip_tex, run_id=run_id_b,
                log_path=log_b_path, variant=paraphrase_variant,
            )
        except ProviderError as exc:
            click.echo(
                f"ERROR: provider error during capture B: {exc} "
                f"(capture A is at {eta_a_path})",
                err=True,
            )
            sys.exit(1)
        eta_b.dump(eta_b_path)
        log.info("retest.cli.auto.capture_b_done run_id=%s items=%d",
                 eta_b.id, eta_b.n)

        # Inside the with-block: re-load from disk so the returned objects
        # are independent of the (possibly transient) etas_dir context.
        eta_a = Evaluation.load(eta_a_path)
        eta_b = Evaluation.load(eta_b_path)

    return eta_a, eta_b


class _NoopCtx:
    """Tiny context manager that mimics ``TemporaryDirectory`` for a
    persistent directory — returns the supplied path on enter and is a
    no-op on exit. Lets the same with-block handle both
    ``--save-etas <persistent-dir>`` and the tmpdir default uniformly."""

    def __init__(self, path: Path) -> None:
        self._path = str(path)

    def __enter__(self) -> str:
        return self._path

    def __exit__(self, *exc: object) -> None:
        return None


def _print_summary(result: Any) -> None:  # RetestResult
    click.echo("test-retest reliability")
    click.echo("=======================")
    click.echo("")
    click.echo(f"benchmark:   {result.benchmark_id}")
    click.echo(f"run A:       {result.run_a_id}")
    click.echo(f"run B:       {result.run_b_id}")
    click.echo(f"items:       {result.n_items}")
    click.echo(
        f"agreement:   {result.n_agreements} "
        f"({result.agreement_rate * 100:.1f}%)"
    )
    click.echo(
        f"flips:       {result.n_disagreements} "
        f"({result.flip_rate * 100:.1f}%)"
    )
    if result.test_retest_kappa is None:
        click.echo("test-retest κ: undefined")
    else:
        click.echo(f"test-retest κ: {result.test_retest_kappa:+.4f}")
    click.echo("")

    if result.flipped_items:
        click.echo(f"Flipped items ({len(result.flipped_items)}):")
        for fi in result.flipped_items[:20]:
            fl_note = (
                f"  [{', '.join(f'{k}={v}' for k, v in fi.factor_levels.items())}]"
                if fi.factor_levels
                else ""
            )
            click.echo(
                f"  - {fi.item_id}: {fi.verdict_a} -> {fi.verdict_b}{fl_note}"
            )
        if len(result.flipped_items) > 20:
            click.echo(
                f"  ... ({len(result.flipped_items) - 20} more — see output JSON)"
            )
        click.echo("")

    click.echo(result.stability_verdict)
