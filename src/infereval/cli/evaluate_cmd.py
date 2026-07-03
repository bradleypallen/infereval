"""``infereval evaluate`` -- run a model against a benchmark, write the evaluation JSON.

Wraps :func:`infereval.evaluation.evaluate` with click-level argument
parsing, provider construction, and ``--dry-run`` support (prints the
prompts that would be sent without calling the provider).

Threaded concurrency (``--workers``), JSONL run logs (``--log``), and
replay providers (``--replay-from``) land in M7 / M8.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import cast

import click

from infereval.benchmark import Benchmark
from infereval.context import resolve_context_builders
from infereval.endorsement import QuestionForm
from infereval.evaluation import (
    EndorsementConfig,
    ProviderParams,
    TieBreak,
    evaluate,
)
from infereval.prompts import resolve_verification_prompt
from infereval.providers import (
    Provider,
    ProviderConfigError,
    ProviderError,
    get_provider,
)
from infereval.templates import CoherenceFrame, coherence_frame_for_id

log = logging.getLogger(__name__)

PROVIDER_CHOICES = ["anthropic", "openai", "openrouter"]
TIE_BREAK_CHOICES = ["abstain", "good", "bad", "first"]


def _variant_path(path: Path, variant: int) -> Path:
    """Insert a ``-vN`` suffix before the final file extension.

    >>> _variant_path(Path("out/eval.json"), 2)
    PosixPath('out/eval-v2.json')
    >>> _variant_path(Path("run.jsonl"), 0)
    PosixPath('run-v0.jsonl')

    Compound extensions like ``.tar.gz`` are not handled specially —
    only the final ``.gz`` is preserved (``eval.tar.gz`` becomes
    ``eval.tar-v0.gz``). Evaluation outputs use single-suffix paths
    (``.json``, ``.jsonl``) where this isn't an issue.

    Used by :func:`evaluate_cmd` when ``--paraphrase-cycle`` writes one
    output per variant; single-variant runs keep the user-supplied
    filename unchanged.
    """
    return path.with_name(f"{path.stem}-v{variant}{path.suffix}")


def _print_dry_run(benchmark: Benchmark) -> None:
    """Build and print the per-item prompts without calling any provider."""
    from infereval.endorsement import _expressions_for

    prompt = resolve_verification_prompt(benchmark.verification_prompt)
    premise_builder, conclusion_builder = resolve_context_builders(
        benchmark.context_builders
    )
    bearers = benchmark.runtime_bearers()

    click.echo(f"# Dry run for benchmark {benchmark.id!r}")
    click.echo(f"# verification_prompt_id={prompt.id}")
    click.echo("")
    click.echo("## System prompt")
    click.echo(prompt.system)
    click.echo("")

    for item in benchmark.items:
        implication = item.to_implication()
        prem_exprs = _expressions_for(implication.premises, bearers, strip_tex=True)
        conc_exprs = _expressions_for(implication.conclusions, bearers, strip_tex=True)
        premise_ctx = premise_builder(prem_exprs)
        conclusion_ctx = conclusion_builder(conc_exprs)
        user_text = prompt.build_user(premise_ctx, conclusion_ctx)
        click.echo(f"## Item {item.id}")
        click.echo(user_text)
        click.echo("")


@click.command("evaluate", help="Run a model against a benchmark and write the evaluation JSON.")
@click.argument("benchmark_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--provider",
    "provider_name",
    type=click.Choice(PROVIDER_CHOICES, case_sensitive=False),
    help="LLM provider to use. Required unless --dry-run.",
)
@click.option(
    "--model",
    "model_id",
    type=str,
    help="Provider-specific model id (e.g. claude-opus-4-7, gpt-4o, anthropic/claude-3.5-sonnet).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to write the evaluation JSON. Required unless --dry-run.",
)
@click.option("--n-samples", type=click.IntRange(min=1), default=5, show_default=True)
@click.option("--temperature", type=float, default=1.0, show_default=True)
@click.option("--max-tokens", type=click.IntRange(min=1), default=1024, show_default=True)
@click.option("--top-p", type=float, default=None)
@click.option("--seed", type=int, default=None,
              help="Random seed. Honored by OpenAI; ignored (with warning) by Anthropic.")
@click.option(
    "--tie-break",
    type=click.Choice(TIE_BREAK_CHOICES),
    default="abstain",
    show_default=True,
)
@click.option(
    "--question-form",
    type=click.Choice(["support", "coherence"]),
    default="support",
    show_default=True,
    help="Logical question posed per item: the single-succedent 'support' "
    "question (default) or the arity-uniform bilateral 'coherence' "
    "question.",
)
@click.option(
    "--coherence-frame",
    "coherence_frame_id",
    type=str,
    default=None,
    help="Coherence-frame id to elicit the coherence question under "
    "(built-ins: thin-v1, defeasible-coherence-explicit-v1, "
    "defeasible-coherence-underdet-v1). Unknown ids fail before any provider "
    "call. Default: evaluate()'s frame resolution (a programmatic "
    "registration, then the benchmark's coherence_frame_id, then thin-v1). "
    "Meaningful only with --question-form coherence.",
)
@click.option(
    "--strip-tex/--no-strip-tex",
    default=True,
    show_default=True,
    help="Strip $...$ TeX-math delimiters from bearer expressions at prompt time.",
)
@click.option(
    "--run-id",
    type=str,
    default=None,
    help="Stable id for this run. Generated as a UUID4 if not supplied.",
)
@click.option(
    "--log",
    "log_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Path for the JSONL run log. One event per line; parseable with "
    "`jq` or `pandas.read_json(lines=True)`. Disabled if not given.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Build and print prompts; do not call any provider.",
)
@click.option(
    "--replay-from",
    "replay_from",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a JSONL ReplayProvider fixture. When supplied, --provider "
    "and --model are ignored; the replay fixture drives all sample responses.",
)
@click.option(
    "--http-referer",
    type=str,
    default=None,
    help="OpenRouter attribution: HTTP-Referer header.",
)
@click.option(
    "--x-title",
    type=str,
    default=None,
    help="OpenRouter attribution: X-Title header.",
)
@click.option(
    "--paraphrase-variant",
    "paraphrase_variant",
    type=click.IntRange(min=0),
    default=None,
    help="Select a single paraphrase variant (0 = canonical expressions; "
    "k >= 1 = bearer.paraphrases[k-1] with fallback to canonical). Mutually "
    "exclusive with --paraphrase-cycle. Phase 1.2 of the construct-validity "
    "infrastructure (R10).",
)
@click.option(
    "--paraphrase-cycle",
    "paraphrase_cycle",
    is_flag=True,
    default=False,
    help="Run the benchmark once per declared paraphrase variant; output "
    "paths gain a '-vN' suffix per variant. Mutually exclusive with "
    "--paraphrase-variant. Useful for paraphrase-axis robustness analysis.",
)
def evaluate_cmd(
    benchmark_path: Path,
    provider_name: str | None,
    model_id: str | None,
    output: Path | None,
    n_samples: int,
    temperature: float,
    max_tokens: int,
    top_p: float | None,
    seed: int | None,
    tie_break: str,
    question_form: str,
    coherence_frame_id: str | None,
    strip_tex: bool,
    run_id: str | None,
    log_path: Path | None,
    dry_run: bool,
    replay_from: Path | None,
    http_referer: str | None,
    x_title: str | None,
    paraphrase_variant: int | None = None,
    paraphrase_cycle: bool = False,
) -> None:
    """Run a model against a benchmark and write the evaluation JSON."""
    log.info(
        "evaluate.cli.start benchmark=%s dry_run=%s coherence_frame=%s",
        benchmark_path, dry_run, coherence_frame_id,
    )

    try:
        benchmark = Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001 -- surface load error to user
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)

    if dry_run:
        _print_dry_run(benchmark)
        return

    # Resolve an explicit --coherence-frame up front: an unknown id fails
    # fast, before any provider client is constructed. None defers to
    # evaluate()'s default frame resolution.
    coherence_frame: CoherenceFrame | None = None
    if coherence_frame_id is not None:
        try:
            coherence_frame = coherence_frame_for_id(coherence_frame_id)
        except ValueError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(2)

    provider: Provider
    if replay_from is not None:
        if output is None:
            click.echo("ERROR: --output is required.", err=True)
            sys.exit(2)
        try:
            from infereval.providers.mock import ReplayProvider

            provider = ReplayProvider(replay_from)
        except ProviderConfigError as exc:
            click.echo(f"ERROR: replay fixture: {exc}", err=True)
            sys.exit(2)
    else:
        if provider_name is None or model_id is None or output is None:
            click.echo(
                "ERROR: --provider, --model, and --output are required "
                "unless --dry-run or --replay-from is used.",
                err=True,
            )
            sys.exit(2)

        # Build the provider with provider-specific kwargs only when relevant.
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

    config = EndorsementConfig(
        n_samples=n_samples,
        tie_break=cast(TieBreak, tie_break),
        question_form=cast(QuestionForm, question_form),
    )
    params = ProviderParams(
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        seed=seed,
    )

    # Resolve which paraphrase variant(s) to run. Mutually-exclusive flags;
    # default (neither supplied) preserves existing behavior (variant 0,
    # single run). --paraphrase-cycle expands to the list [0..K-1] where K
    # is benchmark.n_paraphrase_variants. --paraphrase-variant K runs a
    # single variant and validates that K is in range.
    if paraphrase_cycle and paraphrase_variant is not None:
        click.echo(
            "ERROR: --paraphrase-variant and --paraphrase-cycle are mutually exclusive.",
            err=True,
        )
        sys.exit(2)
    if paraphrase_cycle:
        variants = list(range(benchmark.n_paraphrase_variants))
        if len(variants) == 1:
            click.echo(
                "NOTE: --paraphrase-cycle had no effect — no bearer in this "
                "benchmark carries paraphrases (only canonical variant 0 in play).",
            )
    elif paraphrase_variant is not None:
        if paraphrase_variant >= benchmark.n_paraphrase_variants:
            click.echo(
                f"ERROR: --paraphrase-variant={paraphrase_variant} out of range; "
                f"benchmark admits variants 0..{benchmark.n_paraphrase_variants - 1}.",
                err=True,
            )
            sys.exit(2)
        variants = [paraphrase_variant]
    else:
        variants = [0]

    for v in variants:
        # Suffix per-variant paths only when actually cycling, so single-
        # variant runs retain the user-supplied filenames unchanged.
        out_path = _variant_path(output, v) if len(variants) > 1 else output
        log_path_v = (
            _variant_path(log_path, v)
            if (len(variants) > 1 and log_path is not None)
            else log_path
        )
        run_id_v = f"{run_id}-v{v}" if (len(variants) > 1 and run_id is not None) else run_id

        try:
            eta = evaluate(
                benchmark,
                provider,
                config=config,
                params=params,
                strip_tex=strip_tex,
                run_id=run_id_v,
                log_path=log_path_v,
                variant=v,
                coherence_frame=coherence_frame,
            )
        except ProviderError as exc:
            click.echo(
                f"ERROR: provider error during evaluation (variant={v}): {exc}",
                err=True,
            )
            sys.exit(1)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        eta.dump(out_path)

        suffix = f", variant={v}" if len(variants) > 1 else ""
        msg = (
            f"OK: wrote {out_path} "
            f"(run_id={eta.id!r}, items={eta.n}, samples_per_item={n_samples}{suffix})"
        )
        if log_path_v is not None:
            msg += f"; log -> {log_path_v}"
        click.echo(msg)
        log.info(
            "evaluate.cli.done benchmark=%s output=%s run_id=%s variant=%d",
            benchmark_path,
            out_path,
            eta.id,
            v,
        )
