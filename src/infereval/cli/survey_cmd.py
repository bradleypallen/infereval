"""``infereval survey {export,import}`` — analyst-recruitment via
Qualtrics, Google Forms, or SurveyMonkey.

Two subcommands under the ``survey`` Click group:

- ``infereval survey export <benchmark.json>`` — produces the
  platform-specific artifact (``.qsf`` / ``.gs`` / live API call).
- ``infereval survey import <benchmark.json>`` — ingests the
  platform's CSV response export and writes a new benchmark with the
  respondents added as new analyst columns.

See ``docs/surveys.md`` for the end-to-end workflow + platform-specific
caveats (notably the Google Forms randomization limitation).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from infereval.benchmark import Benchmark
from infereval.survey.google_forms_csv import parse_google_forms_csv
from infereval.survey.google_forms_gas import build_gas_script
from infereval.survey.qualtrics_csv import (
    IncompleteRespondentError,
    merge_respondents,
    parse_qualtrics_csv,
)
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import (
    DEFAULT_EXPERTISE_PROMPT,
    SurveyRespondent,
)
from infereval.survey.surveymonkey_api import (
    SurveyMonkeyApiError,
    SurveyMonkeyAuthError,
    build_surveymonkey_payload,
    publish_to_surveymonkey,
)
from infereval.survey.surveymonkey_csv import parse_surveymonkey_csv

log = logging.getLogger(__name__)

_PLATFORM_CHOICES = ["qualtrics", "google_forms", "surveymonkey"]


@click.group(
    "survey",
    help=(
        "Export a benchmark as a survey (Qualtrics, Google Forms, or "
        "SurveyMonkey) and import the response CSV back into the benchmark "
        "as new analyst columns."
    ),
)
def survey_group() -> None:
    """Survey-platform recruitment subcommands."""


# ---- export -------------------------------------------------------------


@click.command(
    "export",
    help=(
        "Generate a survey artifact from a benchmark. Output shape "
        "depends on --platform: .qsf (Qualtrics), .gs Apps Script "
        "(Google Forms), or a live API call (SurveyMonkey)."
    ),
)
@click.argument(
    "benchmark_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-o", "--output",
    "output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Output path (or, for --platform surveymonkey, the file where "
        "the API response — including survey id and edit/share URLs — "
        "will be written)."
    ),
)
@click.option(
    "--platform",
    type=click.Choice(_PLATFORM_CHOICES),
    default="qualtrics",
    show_default=True,
)
@click.option(
    "--title",
    type=str,
    default=None,
    help='Survey title. Default: "Analyst recruitment for <benchmark.id>".',
)
@click.option(
    "--randomize-items/--no-randomize-items",
    default=True,
    show_default=True,
    help=(
        "Randomize item order per respondent. Note: Google Forms "
        "cannot randomize a subset of questions; the flag is honored "
        "by Qualtrics and SurveyMonkey, ignored (with a warning) by "
        "Google Forms. See docs/surveys.md."
    ),
)
@click.option(
    "--include-rationales/--no-include-rationales",
    default=True,
    show_default=True,
    help="Include an optional free-text rationale field after each item.",
)
@click.option(
    "--expertise-prompt",
    type=str,
    default=DEFAULT_EXPERTISE_PROMPT,
    show_default=False,
    help="Prompt rendered above the survey's first (expertise) text field.",
)
@click.option(
    "--question-form",
    type=click.Choice(["support", "coherence"]),
    default="support",
    show_default=True,
    help=(
        "Which logical question to ask. 'support' renders the classic "
        "good/bad/abstain diagnostic-inference question (single-succedent "
        "only). 'coherence' renders the bilateral coherence question at "
        "any arity; import with the same --question-form to decode."
    ),
)
# SurveyMonkey-only:
@click.option(
    "--surveymonkey-token",
    type=str,
    default=None,
    help=(
        "SurveyMonkey API access token. Else reads SURVEYMONKEY_ACCESS_TOKEN "
        "from env. Required for --platform surveymonkey."
    ),
)
@click.option(
    "--surveymonkey-base-url",
    type=str,
    default="https://api.surveymonkey.com/v3",
    show_default=True,
    help="SurveyMonkey API base URL (override for EU datacenter).",
)
def export_cmd(
    benchmark_path: Path,
    output: Path,
    platform: str,
    title: str | None,
    randomize_items: bool,
    include_rationales: bool,
    expertise_prompt: str,
    question_form: str,
    surveymonkey_token: str | None,
    surveymonkey_base_url: str,
) -> None:
    log.info(
        "survey.export.start benchmark=%s output=%s platform=%s",
        benchmark_path, output, platform,
    )
    try:
        benchmark = Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)

    output.parent.mkdir(parents=True, exist_ok=True)

    if platform == "qualtrics":
        qsf, mapping = build_qsf(
            benchmark,
            title=title,
            randomize_items=randomize_items,
            include_rationales=include_rationales,
            expertise_prompt=expertise_prompt,
            question_form=question_form,
        )
        output.write_text(json.dumps(qsf, indent=2), encoding="utf-8")
        click.echo(f"OK: wrote Qualtrics .qsf to {output}")
        _maybe_write_mapping(output, mapping)

    elif platform == "google_forms":
        gas, mapping = build_gas_script(
            benchmark,
            title=title,
            randomize_items=randomize_items,
            include_rationales=include_rationales,
            expertise_prompt=expertise_prompt,
            question_form=question_form,
        )
        output.write_text(gas, encoding="utf-8")
        click.echo(f"OK: wrote Google Apps Script to {output}")
        click.echo(
            "  Next: paste into script.google.com → New Project → Run "
            "createForm(); authorize when prompted; read the form URL "
            "from the execution log."
        )
        if randomize_items:
            click.echo(
                "  NOTE: --randomize-items was requested but Google Forms "
                "cannot randomize a subset. Questions emit in canonical "
                "order. See docs/surveys.md.",
                err=True,
            )
        # v0.9.1: Google Forms importer needs the mapping sidecar to
        # resolve "Item N of M" anchors back to item ids — write always.
        _maybe_write_mapping(output, mapping, always=True)

    elif platform == "surveymonkey":
        payload, mapping = build_surveymonkey_payload(
            benchmark,
            title=title,
            randomize_items=randomize_items,
            include_rationales=include_rationales,
            expertise_prompt=expertise_prompt,
            question_form=question_form,
        )
        try:
            response = publish_to_surveymonkey(
                payload,
                access_token=surveymonkey_token,
                base_url=surveymonkey_base_url,
            )
        except SurveyMonkeyAuthError as exc:
            click.echo(f"ERROR: SurveyMonkey auth failed — {exc}", err=True)
            sys.exit(2)
        except SurveyMonkeyApiError as exc:
            click.echo(f"ERROR: SurveyMonkey API call failed — {exc}", err=True)
            sys.exit(2)
        output.write_text(json.dumps(response, indent=2), encoding="utf-8")
        click.echo(f"OK: created SurveyMonkey survey id={response.get('id')}")
        click.echo(f"  edit URL: {response.get('href')}")
        click.echo(f"  full response written to {output}")
        # v0.9.1: SurveyMonkey importer needs the mapping sidecar too.
        _maybe_write_mapping(output, mapping, always=True)

    else:  # pragma: no cover -- defended by click.Choice
        raise click.UsageError(f"Unknown platform {platform!r}")

    log.info("survey.export.done benchmark=%s output=%s", benchmark_path, output)


def _maybe_write_mapping(
    output: Path,
    mapping: list[dict[str, object]],
    *,
    always: bool = False,
) -> None:
    """Write the mapping sidecar.

    For Qualtrics the sidecar is optional (the DataExportTag carries
    the mapping inside the .qsf), so the caller writes it only when
    any item id was hashed. For Google Forms and SurveyMonkey
    (v0.9.1+) the sidecar is **required** for the importer to resolve
    ``Item N`` anchors back to item ids — the caller passes
    ``always=True``.
    """
    if not always and not any(row.get("was_hashed") for row in mapping):
        return
    sidecar = output.with_suffix(output.suffix + ".mapping.json")
    sidecar.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    click.echo(f"OK: wrote mapping sidecar to {sidecar}")


# ---- import -------------------------------------------------------------


@click.command(
    "import",
    help=(
        "Merge survey responses into a benchmark, producing a new "
        "benchmark with one analyst column per respondent."
    ),
)
@click.argument(
    "benchmark_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-r", "--responses",
    "responses_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "-o", "--output",
    "output",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--platform",
    type=click.Choice(_PLATFORM_CHOICES),
    default="qualtrics",
    show_default=True,
)
@click.option(
    "--mapping",
    "mapping_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Path to a mapping sidecar from `survey export`. When omitted, "
        "looked up automatically next to the CSV as "
        "<csv-stem>.mapping.json (or <output>.mapping.json)."
    ),
)
@click.option(
    "--analyst-id-prefix",
    type=str,
    default="clinician-",
    show_default=True,
    help="Prefix for new analyst ids; the response id is the suffix.",
)
@click.option(
    "--respondent",
    "respondent_id",
    type=str,
    default=None,
    help="Filter to a single respondent by response id. Default: import all rows.",
)
@click.option(
    "--require-complete/--allow-partial",
    default=True,
    show_default=True,
    help=(
        "When True (default), reject any respondent who didn't finish "
        "the survey or whose verdicts don't cover all items. "
        "Pass --allow-partial to import partials with ABSTAIN for "
        "missing verdicts."
    ),
)
@click.option(
    "--question-form",
    type=click.Choice(["support", "coherence"]),
    default="support",
    show_default=True,
    help=(
        "Which logical question the survey asked. Must match the "
        "--question-form used at export time so the choice cells decode "
        "correctly (coherence applies the Incoherent→good inversion)."
    ),
)
def import_cmd(
    benchmark_path: Path,
    responses_path: Path,
    output: Path,
    platform: str,
    mapping_path: Path | None,
    analyst_id_prefix: str,
    respondent_id: str | None,
    require_complete: bool,
    question_form: str,
) -> None:
    log.info(
        "survey.import.start benchmark=%s responses=%s platform=%s",
        benchmark_path, responses_path, platform,
    )
    try:
        benchmark = Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)

    # v0.9.1: load the mapping sidecar before parsing so
    # Google Forms / SurveyMonkey importers can resolve their
    # ``Item N`` column-header anchors via mapping[N-1].
    mapping = _load_mapping_sidecar(mapping_path, responses_path)

    if platform == "qualtrics":
        respondents = parse_qualtrics_csv(responses_path, question_form=question_form)
    elif platform == "google_forms":
        respondents = parse_google_forms_csv(
            responses_path, mapping=mapping, question_form=question_form
        )
    elif platform == "surveymonkey":
        respondents = parse_surveymonkey_csv(
            responses_path, mapping=mapping, question_form=question_form
        )
    else:  # pragma: no cover -- defended by click.Choice
        raise click.UsageError(f"Unknown platform {platform!r}")

    if respondent_id is not None:
        respondents = [r for r in respondents if r.response_id == respondent_id]
        if not respondents:
            click.echo(
                f"ERROR: no respondent matched --respondent={respondent_id!r}",
                err=True,
            )
            sys.exit(2)

    if not respondents:
        click.echo("ERROR: no respondents found in the supplied responses file.", err=True)
        sys.exit(2)

    try:
        merged = merge_respondents(
            benchmark,
            respondents,
            mapping=mapping,
            analyst_id_prefix=analyst_id_prefix,
            require_complete=require_complete,
        )
    except IncompleteRespondentError as exc:
        click.echo(f"ERROR: incomplete respondent — {exc}", err=True)
        sys.exit(2)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(merged.model_dump_json(indent=2), encoding="utf-8")
    click.echo(
        f"OK: wrote merged benchmark to {output} "
        f"(m={len(merged.analysts)} analysts, +{len(respondents)} new)"
    )
    log.info("survey.import.done output=%s", output)


def _load_mapping_sidecar(
    mapping_path: Path | None,
    responses_path: Path,
) -> list[dict[str, object]] | None:
    if mapping_path is not None:
        raw = json.loads(mapping_path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else None

    # Auto-discovery: look next to the CSV.
    auto_candidate = responses_path.with_suffix(responses_path.suffix + ".mapping.json")
    if auto_candidate.is_file():
        log.info("survey.import.mapping_auto_discovered path=%s", auto_candidate)
        raw = json.loads(auto_candidate.read_text(encoding="utf-8"))
        return raw if isinstance(raw, list) else None
    return None


# Wire children into the group.
survey_group.add_command(export_cmd)
survey_group.add_command(import_cmd)


# Re-export for the SurveyRespondent type (used by integration tests).
__all__ = ["SurveyRespondent", "import_cmd", "export_cmd", "survey_group"]
