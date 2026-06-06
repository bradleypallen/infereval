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
    "intervals_s",
    type=click.IntRange(min=0),
    multiple=True,
    default=(0,),
    show_default=True,
    help=(
        "Wall-clock seconds between captures. Repeatable: each "
        "invocation adds one cumulative-anchor interval. Pass once "
        "(default) = back-to-back single retest, v0.11.0-compatible. "
        "Pass N>=2 times = baseline capture + N later captures, each "
        "compared to the baseline (cumulative drift since baseline). "
        "Total wall time = sum of intervals. `--interval-s 86400` "
        "requires the CLI process to stay alive 24+ hours."
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
@click.option(
    "--baseline-from",
    "baseline_from_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "v0.14.0+ staged-composition primitive. Path to a saved baseline "
        "eta (typically `eta-0.json` from an earlier `--save-etas` "
        "directory). When supplied, auto mode loads the baseline, runs ONE "
        "fresh capture, and emits a one-pair MultiIntervalRetestResult "
        "with `interval_s` computed from the actual elapsed wall-clock "
        "seconds between baseline.started_at and the fresh capture's "
        "started_at. Mutually exclusive with multi `--interval-s` (the "
        "interval is auto-computed, not supplied)."
    ),
)
@click.option(
    "--append-to",
    "append_to_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "v0.14.0+ staged-composition composer. Path to an existing "
        "MultiIntervalRetestResult JSON. When supplied, auto mode loads the "
        "existing artifact, resolves the baseline eta from the sibling "
        "`eta-0.json` (override via `--baseline-from`), runs ONE fresh "
        "capture, computes retest against the baseline, appends the "
        "resulting IntervalPair to the existing pairs tuple, and writes "
        "the updated MultiIntervalRetestResult back to the same path "
        "(override via `-o`). The loaded artifact's identity_criterion "
        "is preserved across the append. Mutually exclusive with multi "
        "`--interval-s`."
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
    intervals_s: tuple[int, ...],
    save_etas_dir: Path | None,
    baseline_from_path: Path | None,
    append_to_path: Path | None,
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
        # v0.14.0: staged-composition flags are mutually exclusive with
        # each other and with multi-interval (the interval is computed
        # from baseline.started_at, not user-supplied).
        if baseline_from_path is not None and append_to_path is not None:
            raise click.UsageError(
                "--baseline-from and --append-to are mutually exclusive. "
                "Use --baseline-from for the staged-composition primitive "
                "(one fresh capture against a saved baseline → one-pair "
                "MultiIntervalRetestResult). Use --append-to for the "
                "composer (load existing multi-result, append one new "
                "pair). Each runs exactly one fresh capture."
            )
        # Multi-interval (N>=2) is incompatible with both staged flags —
        # those flags imply a one-fresh-capture flow, and the interval
        # is computed from elapsed wall clock, not from --interval-s.
        # Single-interval default (intervals_s == (0,)) is compatible
        # (the default is ignored on the staged paths).
        if (
            (baseline_from_path is not None or append_to_path is not None)
            and len(intervals_s) > 1
        ):
            raise click.UsageError(
                "--baseline-from / --append-to are incompatible with "
                "multiple --interval-s flags. The staged-composition "
                "paths run exactly one fresh capture; the interval is "
                "computed from baseline.started_at to the fresh capture's "
                "started_at, not supplied by the user. Drop the multiple "
                "--interval-s arguments."
            )
    else:
        if eta_a_path is None or eta_b_path is None:
            raise click.UsageError(
                "Manual mode requires two positional eta paths "
                "(or pass --auto with --benchmark / --provider / --model)."
            )
        if baseline_from_path is not None or append_to_path is not None:
            raise click.UsageError(
                "--baseline-from and --append-to require --auto."
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

    # ---- Auto mode: run evaluate N+1 times -------------------------------
    else:
        assert benchmark_path is not None  # noqa: S101 -- validated above
        assert provider_name is not None and model_id is not None  # noqa: S101
        log.info(
            "retest.cli.auto.start benchmark=%s provider=%s model=%s "
            "intervals_s=%s baseline_from=%s append_to=%s",
            benchmark_path, provider_name, model_id, list(intervals_s),
            baseline_from_path, append_to_path,
        )
        try:
            bench = Benchmark.load(benchmark_path)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
            sys.exit(2)

        # v0.14.0: staged-composition dispatch — `--baseline-from` and
        # `--append-to` short-circuit the N+1-capture orchestration
        # because they run exactly one fresh capture against a
        # pre-existing baseline. Both helpers handle their own output
        # + summary, so they return early.
        if baseline_from_path is not None:
            _run_auto_with_baseline_from(
                baseline_path=baseline_from_path,
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
                save_etas_dir=save_etas_dir,
                claims_path=claims_path,
                output_path=output_path,
            )
            return

        if append_to_path is not None:
            _run_auto_append_to(
                multi_path=append_to_path,
                baseline_override=baseline_from_path,
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
                save_etas_dir=save_etas_dir,
                output_path=output_path,
            )
            return

        captures = _run_auto_captures(
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
            intervals_s=intervals_s,
            save_etas_dir=save_etas_dir,
        )

        # Dispatch: single-interval keeps v0.11.0 backward-compat shape;
        # multi-interval emits MultiIntervalRetestResult.
        if len(intervals_s) == 1:
            eta_a, eta_b = captures[0], captures[1]
        else:
            _emit_multi_interval(
                captures=captures,
                intervals_s=intervals_s,
                bench=bench,
                claims_path=claims_path,
                output_path=output_path,
            )
            return  # multi-interval emission handles output + summary

    # ---- Identity criterion threading (v0.6.1) --------------------------
    identity_criterion = _maybe_load_identity_criterion(claims_path)

    # ---- Compute + emit (single-pair path; v0.11.0 backward compat) -----
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
    intervals_s: tuple[int, ...],
    save_etas_dir: Path | None,
) -> list[Evaluation]:
    """Run :func:`evaluate` N+1 times and persist all captures.

    With N intervals supplied, takes N+1 captures: baseline (capture 0),
    then capture i after sleeping ``intervals_s[i-1]`` seconds before
    each. Returns the list of N+1 :class:`Evaluation` objects ready for
    :func:`compute_retest`.

    Saved-etas directory naming:

    - Single-interval (N=1, v0.11.0 backward compat): ``eta-a.json``,
      ``eta-b.json``, plus ``.run.jsonl`` siblings.
    - Multi-interval (N>=2, v0.12.0+): ``eta-0.json`` … ``eta-N.json``
      and the same ``.run.jsonl`` pattern.

    Run-ids are generated as ``f"{base_run_id}-{label}"`` where label
    follows the same naming convention.
    """
    # Local imports — keep CLI import cost low for the manual-mode path.
    from infereval.providers import get_provider
    from infereval.providers.base import ProviderConfigError, ProviderError

    n_intervals = len(intervals_s)
    n_captures = n_intervals + 1
    # Single-interval mode keeps v0.11.0's eta-a / eta-b naming; multi
    # uses eta-0 … eta-N.
    labels = (
        ["a", "b"] if n_intervals == 1
        else [str(i) for i in range(n_captures)]
    )

    # Build a single provider client and reuse it for all captures —
    # this models the realistic "same client, N requests" shape.
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

    # Auto-generate run ids per capture so each is distinguishable in
    # logs and in the saved-etas directory.
    base_run_id = f"{_AUTO_RUN_ID_PREFIX}{uuid.uuid4().hex[:8]}"
    run_ids = [f"{base_run_id}-{lbl}" for lbl in labels]

    # Persist etas to either the user-supplied dir or a tmpdir.
    if save_etas_dir is not None:
        save_etas_dir.mkdir(parents=True, exist_ok=True)
        ctx = _NoopCtx(save_etas_dir)
    else:
        ctx = tempfile.TemporaryDirectory()  # type: ignore[assignment]

    captures: list[Evaluation] = []
    with ctx as etas_dir_str:
        etas_dir = Path(etas_dir_str)

        for i in range(n_captures):
            label = labels[i]
            eta_path = etas_dir / f"eta-{label}.json"
            log_path = etas_dir / f"eta-{label}.run.jsonl"
            run_id_i = run_ids[i]

            # Sleep before captures 1..N according to the supplied
            # intervals. Capture 0 (baseline) starts immediately.
            if i > 0:
                interval_s = intervals_s[i - 1]
                if interval_s > 0:
                    click.echo(
                        f"retest --auto: sleeping {interval_s}s before "
                        f"capture {label}",
                        err=True,
                    )
                    time.sleep(interval_s)
                log.info("retest.cli.auto.interval_s=%d", interval_s)

            click.echo(
                f"retest --auto: capture {label} starting "
                f"(benchmark={benchmark.id!r}, run_id={run_id_i!r})",
                err=True,
            )
            try:
                eta = evaluate(
                    benchmark, provider,
                    config=config, params=params,
                    strip_tex=strip_tex, run_id=run_id_i,
                    log_path=log_path, variant=paraphrase_variant,
                )
            except ProviderError as exc:
                # On failure mid-sequence, surface the failure with a
                # pointer to the preceding captures already on disk
                # under --save-etas.
                preceding = [str(etas_dir / f"eta-{labels[j]}.json")
                             for j in range(i)]
                preceding_note = (
                    f" (preceding captures at {preceding})" if preceding else ""
                )
                # Backward-compat: v0.11.0 single-interval mode used
                # the "capture A" / "capture B" labels in error strings;
                # preserve those exact strings to keep tests stable.
                cap_label = label.upper() if n_intervals == 1 else label
                click.echo(
                    f"ERROR: provider error during capture {cap_label}: "
                    f"{exc}{preceding_note}",
                    err=True,
                )
                sys.exit(1)
            eta.dump(eta_path)
            log.info("retest.cli.auto.capture_done label=%s run_id=%s items=%d",
                     label, eta.id, eta.n)
            captures.append(eta)

        # Inside the with-block: re-load from disk so the returned
        # objects are independent of the (possibly transient) etas_dir
        # context.
        captures = [
            Evaluation.load(etas_dir / f"eta-{labels[i]}.json")
            for i in range(n_captures)
        ]

    return captures


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


def _emit_multi_interval(
    *,
    captures: list[Evaluation],
    intervals_s: tuple[int, ...],
    bench: Benchmark | None,
    claims_path: Path | None,
    output_path: Path | None,
) -> None:
    """Compute the N anchored-on-baseline retest pairs and emit them.

    Baseline is ``captures[0]``; each ``captures[i+1]`` is compared back
    to baseline and packaged as :class:`IntervalPair`. The wrapper is
    a :class:`MultiIntervalRetestResult`. Output:

    - ``-o <path>``: writes ``multi_interval_retest_result_to_dict``
      JSON to the path.
    - stdout: a per-interval summary table.
    """
    from infereval.retest import (
        IntervalPair,
        MultiIntervalRetestResult,
        multi_interval_retest_result_to_dict,
    )

    identity_criterion = _maybe_load_identity_criterion(claims_path)
    baseline = captures[0]

    pairs: list[IntervalPair] = []
    for i, later in enumerate(captures[1:], start=1):
        interval_s = intervals_s[i - 1]
        try:
            retest = compute_retest(
                baseline, later,
                benchmark=bench, identity_criterion=identity_criterion,
            )
        except RetestConfigMismatchError as exc:
            click.echo(
                f"ERROR: incompatible runs at interval index {i}: {exc}",
                err=True,
            )
            sys.exit(1)
        pairs.append(IntervalPair(
            interval_s=interval_s, run_id=later.id, retest=retest,
        ))
        log.info(
            "retest.cli.auto.multi_pair_done interval_s=%d kappa=%s flips=%d",
            interval_s, retest.test_retest_kappa, retest.n_disagreements,
        )

    from infereval import __version__ as framework_version
    result = MultiIntervalRetestResult(
        schema_version="1.0",
        framework_version=framework_version,
        benchmark_id=baseline.benchmark_id,
        benchmark_hash=baseline.benchmark_hash,
        baseline_run_id=baseline.id,
        pairs=tuple(pairs),
        identity_criterion=identity_criterion,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                multi_interval_retest_result_to_dict(result), indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    _print_multi_summary(result)
    log.info(
        "retest.cli.auto.multi_done baseline_run_id=%s n_pairs=%d",
        result.baseline_run_id, len(result.pairs),
    )


# ---- v0.14.0: staged-composition helpers (--baseline-from / --append-to) ----


def _run_one_fresh_capture(
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
    save_etas_dir: Path | None,
    eta_filename: str,
    run_id_prefix: str,
) -> Evaluation:
    """Run ONE :func:`evaluate` against the supplied benchmark + provider.

    Factored out of :func:`_run_auto_captures`'s per-capture loop so the
    staged-composition entry points (:func:`_run_auto_with_baseline_from`
    and :func:`_run_auto_append_to`) can reuse the exact same provider-
    client construction, run-id minting, eta-dump-and-reload, and
    error-handling shape as the existing multi-capture path. The single
    behavioral difference is that we run one capture (not N+1) and the
    caller chooses the filename + run-id-prefix that's appropriate for
    the staged-composition slot.

    Returns the fresh :class:`Evaluation`, already dumped to disk under
    ``save_etas_dir`` (or a tmpdir) and reloaded for independence from
    the tmpdir context.
    """
    # Local imports — keep CLI import cost low.
    from infereval.providers import get_provider
    from infereval.providers.base import ProviderConfigError, ProviderError

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
        tie_break=cast(Any, tie_break),
    )
    params = ProviderParams(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        seed=seed,
    )

    fresh_run_id = f"{run_id_prefix}{uuid.uuid4().hex[:8]}"

    if save_etas_dir is not None:
        save_etas_dir.mkdir(parents=True, exist_ok=True)
        ctx = _NoopCtx(save_etas_dir)
    else:
        ctx = tempfile.TemporaryDirectory()  # type: ignore[assignment]

    with ctx as etas_dir_str:
        etas_dir = Path(etas_dir_str)
        # Strip extension to derive the log filename — eta-1.json
        # gives eta-1.run.jsonl, etc.
        stem = Path(eta_filename).stem
        eta_path = etas_dir / eta_filename
        log_path = etas_dir / f"{stem}.run.jsonl"

        click.echo(
            f"retest --auto: fresh capture starting "
            f"(benchmark={benchmark.id!r}, run_id={fresh_run_id!r})",
            err=True,
        )
        try:
            eta = evaluate(
                benchmark, provider,
                config=config, params=params,
                strip_tex=strip_tex, run_id=fresh_run_id,
                log_path=log_path, variant=paraphrase_variant,
            )
        except ProviderError as exc:
            click.echo(
                f"ERROR: provider error during fresh capture: {exc}",
                err=True,
            )
            sys.exit(1)
        eta.dump(eta_path)
        # Re-load for independence from the tmpdir context. Mirrors the
        # final reload in :func:`_run_auto_captures`.
        eta = Evaluation.load(eta_path)
        log.info(
            "retest.cli.auto.fresh_capture_done run_id=%s items=%d eta_path=%s",
            eta.id, eta.n, eta_path,
        )

    return eta


def _run_auto_with_baseline_from(
    *,
    baseline_path: Path,
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
    save_etas_dir: Path | None,
    claims_path: Path | None,
    output_path: Path | None,
) -> None:
    """v0.14.0 staged-composition primitive: one fresh capture vs saved baseline.

    Loads the baseline eta from ``baseline_path``, runs ONE fresh
    capture via :func:`_run_one_fresh_capture`, computes the retest
    against the baseline via :func:`compute_retest`, and emits a
    **one-pair** :class:`MultiIntervalRetestResult` whose
    ``pairs[0].interval_s`` is the actual elapsed wall-clock seconds
    between ``baseline.started_at`` and the fresh capture's
    ``started_at`` (via :func:`compute_interval_s`).

    The emitted shape is the multi-result wrapper (not a bare
    ``RetestResult``) because the staged-composition workflow's whole
    point is to compose more pairs later via ``--append-to``; the
    artifact starts at one pair and grows. The v0.11.0 bare-shape is
    reserved for the default-`--auto --interval-s 0` path where no
    staged composition is involved.
    """
    from infereval.retest import (
        IntervalPair,
        MultiIntervalRetestResult,
        compute_interval_s,
        multi_interval_retest_result_to_dict,
    )

    log.info(
        "retest.cli.auto.baseline_from.start baseline=%s", baseline_path,
    )
    try:
        baseline = Evaluation.load(baseline_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(
            f"ERROR: could not load baseline eta from {baseline_path}: {exc}",
            err=True,
        )
        sys.exit(2)

    identity_criterion = _maybe_load_identity_criterion(claims_path)

    # Filename convention: when staging composition, the fresh capture
    # sits at the "pair 1" slot relative to the baseline (which is
    # conceptually `eta-0.json`). Even if the user pointed at a
    # baseline outside the conventional layout, naming the fresh eta
    # `eta-1.json` makes the subsequent --append-to path (which would
    # write `eta-2.json`) read coherently.
    fresh = _run_one_fresh_capture(
        benchmark=benchmark,
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
        save_etas_dir=save_etas_dir,
        eta_filename="eta-1.json",
        run_id_prefix="retest-baseline-from-",
    )

    try:
        retest = compute_retest(
            baseline, fresh,
            benchmark=benchmark, identity_criterion=identity_criterion,
        )
    except RetestConfigMismatchError as exc:
        click.echo(f"ERROR: incompatible runs — {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: unexpected failure during retest: {exc}", err=True)
        sys.exit(1)

    interval_s = compute_interval_s(baseline, fresh)
    pair = IntervalPair(interval_s=interval_s, run_id=fresh.id, retest=retest)

    from infereval import __version__ as framework_version
    result = MultiIntervalRetestResult(
        schema_version="1.0",
        framework_version=framework_version,
        benchmark_id=baseline.benchmark_id,
        benchmark_hash=baseline.benchmark_hash,
        baseline_run_id=baseline.id,
        pairs=(pair,),
        identity_criterion=identity_criterion,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                multi_interval_retest_result_to_dict(result), indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    _print_multi_summary(result)
    log.info(
        "retest.cli.auto.baseline_from.done baseline_run_id=%s "
        "fresh_run_id=%s interval_s=%d kappa=%s",
        result.baseline_run_id, fresh.id, interval_s,
        retest.test_retest_kappa,
    )


def _run_auto_append_to(
    *,
    multi_path: Path,
    baseline_override: Path | None,
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
    save_etas_dir: Path | None,
    output_path: Path | None,
) -> None:
    """v0.14.0 staged-composition composer: append a new pair to existing multi.

    Loads the existing :class:`MultiIntervalRetestResult` from
    ``multi_path``. Resolves the baseline eta:

    - Default: sibling ``eta-0.json`` in the directory containing
      ``multi_path``.
    - Override: ``baseline_override`` (passed via ``--baseline-from``
      alongside ``--append-to`` when the baseline lives elsewhere).

    Runs ONE fresh capture, computes retest against the baseline,
    constructs an :class:`IntervalPair` with the elapsed-wall-clock
    ``interval_s``, appends to the existing pairs tuple, and writes
    the updated multi-result back to ``multi_path`` (or ``-o``).

    The loaded multi-result's ``identity_criterion`` is preserved on
    the output verbatim: the criterion is a one-shot claim-level
    declaration that applies to every pair, including the appended
    one (the analyst commits to the same individuation across the
    Phase 1 + Phase 2 captures by the act of appending).
    """
    from infereval.retest import (
        IntervalPair,
        MultiIntervalRetestResult,
        compute_interval_s,
        multi_interval_retest_result_to_dict,
    )

    log.info(
        "retest.cli.auto.append_to.start multi=%s baseline_override=%s",
        multi_path, baseline_override,
    )

    # 1. Load the existing MultiIntervalRetestResult JSON. We
    # reconstruct the dataclass shape so the identity criterion
    # threads through unmodified and the existing pairs are
    # immutable (frozen-dataclass semantics).
    try:
        existing_raw = json.loads(multi_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        click.echo(
            f"ERROR: could not read existing multi-result from "
            f"{multi_path}: {exc}",
            err=True,
        )
        sys.exit(2)

    existing = _load_multi_interval_result(existing_raw, multi_path)

    # 2. Resolve the baseline eta path. Default: sibling `eta-0.json`
    # in the directory containing the multi.json (the canonical
    # `--save-etas` convention from v0.12.0). Override: the
    # `baseline_override` path (the --baseline-from flag carries
    # this when supplied alongside --append-to for non-canonical
    # layouts).
    if baseline_override is not None:
        baseline_path = baseline_override
    else:
        baseline_path = multi_path.parent / "eta-0.json"

    if not baseline_path.is_file():
        click.echo(
            f"ERROR: baseline eta not found at {baseline_path}. "
            f"Pass --baseline-from <path> to point at it explicitly "
            f"if the multi.json was moved post-hoc, or recreate the "
            f"`eta-0.json` sibling next to the multi.json.",
            err=True,
        )
        sys.exit(2)

    try:
        baseline = Evaluation.load(baseline_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(
            f"ERROR: could not load baseline eta from {baseline_path}: {exc}",
            err=True,
        )
        sys.exit(2)

    # 3. Verify the existing artifact's baseline_run_id matches the
    # loaded baseline's id. If they don't, the user pointed at the
    # wrong baseline file — abort rather than silently composing
    # pairs against the wrong anchor.
    if existing.baseline_run_id != baseline.id:
        click.echo(
            f"ERROR: baseline-id mismatch — the existing multi-result's "
            f"baseline_run_id={existing.baseline_run_id!r} does not "
            f"match the loaded baseline eta's id={baseline.id!r}. "
            f"Pass --baseline-from <path> to point at the correct "
            f"baseline eta file.",
            err=True,
        )
        sys.exit(2)

    # 4. Run the fresh capture. The eta filename slot is the next
    # numerical index after the existing pairs (eta-1, eta-2, ...).
    # If the user didn't pass --save-etas, default to the same
    # directory as the existing multi.json so the appended eta sits
    # naturally next to the baseline + existing-pair etas.
    next_slot = len(existing.pairs) + 1
    eta_filename = f"eta-{next_slot}.json"
    effective_save_dir = (
        save_etas_dir if save_etas_dir is not None else multi_path.parent
    )

    fresh = _run_one_fresh_capture(
        benchmark=benchmark,
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
        save_etas_dir=effective_save_dir,
        eta_filename=eta_filename,
        # Distinct hex-8 prefix per --append-to invocation so the
        # provenance is traceable: Phase 1 pairs share their original
        # `retest-auto-<hex>` prefix; each --append-to mints its own.
        run_id_prefix="retest-append-",
    )

    # 5. Compute the retest against the baseline, threading the
    # existing criterion unmodified.
    try:
        retest = compute_retest(
            baseline, fresh,
            benchmark=benchmark,
            identity_criterion=existing.identity_criterion,
        )
    except RetestConfigMismatchError as exc:
        click.echo(f"ERROR: incompatible runs — {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: unexpected failure during retest: {exc}", err=True)
        sys.exit(1)

    # 6. Build the appended IntervalPair and stamp a new wrapper.
    interval_s = compute_interval_s(baseline, fresh)
    new_pair = IntervalPair(
        interval_s=interval_s, run_id=fresh.id, retest=retest,
    )
    from infereval import __version__ as framework_version
    updated = MultiIntervalRetestResult(
        schema_version=existing.schema_version,
        # Stamp the current framework version on the updated artifact
        # so the audit trail reflects when the append happened. Each
        # pair's embedded retest still records its original
        # framework_version.
        framework_version=framework_version,
        benchmark_id=existing.benchmark_id,
        benchmark_hash=existing.benchmark_hash,
        baseline_run_id=existing.baseline_run_id,
        pairs=existing.pairs + (new_pair,),
        identity_criterion=existing.identity_criterion,
    )

    # 7. Write back. Default: overwrite the input path in place
    # (canonical "grow the artifact" semantics). Override: `-o` to
    # write the updated result to a different path (useful for
    # before/after comparisons or dry-run workflows).
    target_path = output_path if output_path is not None else multi_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(
            multi_interval_retest_result_to_dict(updated), indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    _print_multi_summary(updated)
    log.info(
        "retest.cli.auto.append_to.done baseline_run_id=%s "
        "fresh_run_id=%s interval_s=%d new_n_pairs=%d kappa=%s",
        updated.baseline_run_id, fresh.id, interval_s,
        len(updated.pairs), retest.test_retest_kappa,
    )


def _load_multi_interval_result(
    raw: dict[str, Any], src_path: Path,
) -> Any:  # MultiIntervalRetestResult
    """Reconstruct a MultiIntervalRetestResult from its dict form.

    Mirrors :func:`infereval.retest.multi_interval_retest_result_to_dict`'s
    shape exactly. On malformed input, prints a user-facing error
    naming ``src_path`` and exits with code 2 rather than letting a
    deep KeyError / Pydantic validation traceback escape.
    """
    from infereval.report import IdentityCriterion
    from infereval.retest import (
        FlippedItem,
        IntervalPair,
        ItemDelta,
        MultiIntervalRetestResult,
        RetestResult,
    )

    def _reconstruct_retest(d: dict[str, Any]) -> RetestResult:
        flipped = tuple(
            FlippedItem(
                item_id=f["item_id"],
                verdict_a=f["verdict_a"],
                verdict_b=f["verdict_b"],
                factor_levels=(
                    dict(f["factor_levels"])
                    if isinstance(f.get("factor_levels"), dict)
                    else None
                ),
            )
            for f in (d.get("flipped_items") or [])
        )
        item_deltas = tuple(
            ItemDelta(
                item_id=it["item_id"],
                verdict_a=it["verdict_a"],
                verdict_b=it["verdict_b"],
                entropy_a=it["entropy_a"],
                entropy_b=it["entropy_b"],
                margin_a=it["margin_a"],
                margin_b=it["margin_b"],
            )
            for it in (d.get("item_deltas") or [])
        )
        crit_dict = d.get("identity_criterion")
        crit = (
            IdentityCriterion(**crit_dict)
            if isinstance(crit_dict, dict)
            else None
        )
        return RetestResult(
            schema_version="1.0",
            framework_version=d.get("framework_version", "unknown"),
            benchmark_id=d["benchmark_id"],
            benchmark_hash=d.get("benchmark_hash"),
            run_a_id=d["run_a_id"],
            run_b_id=d["run_b_id"],
            n_items=d["n_items"],
            n_agreements=d["n_agreements"],
            n_disagreements=d["n_disagreements"],
            test_retest_kappa=d.get("test_retest_kappa"),
            flipped_items=flipped,
            item_deltas=item_deltas,
            identity_criterion=crit,
        )

    try:
        pairs = tuple(
            IntervalPair(
                interval_s=int(p["interval_s"]),
                run_id=p["run_id"],
                retest=_reconstruct_retest(p["retest"]),
            )
            for p in raw.get("pairs", [])
        )
        crit_dict = raw.get("identity_criterion")
        wrapper_crit = (
            IdentityCriterion(**crit_dict)
            if isinstance(crit_dict, dict)
            else None
        )
        return MultiIntervalRetestResult(
            schema_version="1.0",
            framework_version=raw.get("framework_version", "unknown"),
            benchmark_id=raw["benchmark_id"],
            benchmark_hash=raw.get("benchmark_hash"),
            baseline_run_id=raw["baseline_run_id"],
            pairs=pairs,
            identity_criterion=wrapper_crit,
        )
    except (KeyError, TypeError, ValueError) as exc:
        click.echo(
            f"ERROR: malformed MultiIntervalRetestResult JSON at "
            f"{src_path}: {exc}",
            err=True,
        )
        sys.exit(2)


def _print_multi_summary(result: Any) -> None:  # MultiIntervalRetestResult
    """Per-interval table for ``MultiIntervalRetestResult``."""
    click.echo("test-retest reliability (multi-interval, anchored on baseline)")
    click.echo("=" * 60)
    click.echo("")
    click.echo(f"benchmark:        {result.benchmark_id}")
    click.echo(f"baseline run id:  {result.baseline_run_id}")
    click.echo("")
    click.echo(
        f"{'interval (s)':>12}  {'run b':<24}  {'agree':>5}  "
        f"{'flips':>5}  {'κ':>8}  verdict"
    )
    click.echo("-" * 75)
    for pair in result.pairs:
        r = pair.retest
        k_str = (
            f"{r.test_retest_kappa:+8.4f}"
            if r.test_retest_kappa is not None
            else "undefined"
        )
        # Shortened verdict for the table — first 30 chars.
        verdict = r.stability_verdict.split(";")[0].strip()
        click.echo(
            f"{pair.interval_s:>12}  {pair.run_id:<24}  "
            f"{r.n_agreements:>5}  {r.n_disagreements:>5}  {k_str}  {verdict}"
        )


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
