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
from infereval.survey.quality import quality_report
from infereval.survey.qualtrics_csv import (
    FrameMismatchError,
    IncompleteRespondentError,
    merge_respondents,
    parse_qualtrics_csv,
)
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import (
    DEFAULT_EXPERTISE_PROMPT,
    SurveyRespondent,
)
from infereval.survey.session import load_consent, load_practice, load_quality
from infereval.survey.surveymonkey_api import (
    SurveyMonkeyApiError,
    SurveyMonkeyAuthError,
    build_surveymonkey_payload,
    publish_to_surveymonkey,
)
from infereval.survey.surveymonkey_csv import parse_surveymonkey_csv
from infereval.templates import CoherenceFrame, coherence_frame_for_id

log = logging.getLogger(__name__)

_PLATFORM_CHOICES = ["qualtrics", "google_forms", "surveymonkey"]

#: Frame ids whose survey surface is the pre-frame default wording:
#: ``default-v1`` (the locked v0.9.0 support header) and ``thin-v1`` (the
#: v0.17.4 coherence header, canonical on the thin frame). Exports under
#: these need no frame provenance on disk to be reproducible — every
#: pre-frame artifact was rendered under exactly this wording — so the
#: Qualtrics sidecar-writing rule treats them as "nothing to record".
_DEFAULT_SURVEY_FRAME_IDS: frozenset[str] = frozenset({"default-v1", "thin-v1"})


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
@click.option(
    "--coherence-frame",
    "coherence_frame_id",
    type=str,
    default=None,
    help=(
        "Coherence-frame id whose survey header the exported questions "
        "render (built-ins: thin-v1, defeasible-coherence-explicit-v1, "
        "defeasible-coherence-underdet-v1). Unknown ids fail before any "
        "artifact is written. The resolved frame id is recorded in the "
        "mapping sidecar; import with the same --coherence-frame to pass "
        "the merge guard. Meaningful only with --question-form coherence. "
        "Default: render_survey_question's frame resolution (a "
        "programmatic registration, then the benchmark's "
        "coherence_frame_id, then thin-v1)."
    ),
)
@click.option(
    "--header-mode",
    type=click.Choice(["per-question", "instructions"]),
    default="per-question",
    show_default=True,
    help=(
        "Where the frame's survey header renders. 'per-question' repeats "
        "the full header above every item. 'instructions' renders it once "
        "as a survey-level instructions page (before the expertise "
        "question, outside randomization) and repeats only the frame's "
        "closing question line per item — required for long anchored "
        "headers, which invite satisficing when repeated. Qualtrics only; "
        "recorded in the mapping sidecar."
    ),
)
@click.option(
    "--prolific-completion-code",
    type=str,
    default=None,
    help=(
        "Add the Prolific hand-off: capture PROLIFIC_PID, STUDY_ID and "
        "SESSION_ID from the study link as Embedded Data, and end the "
        "survey with a redirect to Prolific's completion URL carrying "
        "this code (from the Prolific study page). Qualtrics only."
    ),
)
@click.option(
    "--consent",
    "consent_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "JSON consent page (information, statements, agree, decline). "
        "Shown first; declining or leaving a statement unticked ends the "
        "survey before any item. Qualtrics only."
    ),
)
@click.option(
    "--practice",
    "practice_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "JSON practice items (items of id/premises/conclusion, optional "
        "intro and outro), rendered like the benchmark items after the "
        "instructions, outside randomization, no feedback. Qualtrics only."
    ),
)
@click.option(
    "--prolific-no-consent-code",
    type=str,
    default=None,
    help=(
        "With --consent: send participants who do not consent to Prolific "
        "with this code (set up in Prolific to ask them to return the "
        "study), instead of the default end message."
    ),
)
@click.option(
    "--quality-checks",
    "quality_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "JSON quality checks: attention_checks (id/text/answer) shown among the "
        "items, and repeats (item ids) shown again after all items. Qualtrics only."
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
    coherence_frame_id: str | None,
    header_mode: str,
    prolific_completion_code: str | None,
    consent_path: Path | None,
    practice_path: Path | None,
    prolific_no_consent_code: str | None,
    quality_path: Path | None,
    surveymonkey_token: str | None,
    surveymonkey_base_url: str,
) -> None:
    log.info(
        "survey.export.start benchmark=%s output=%s platform=%s "
        "question_form=%s coherence_frame=%s header_mode=%s prolific=%s "
        "consent=%s practice=%s prolific_no_consent=%s quality=%s",
        benchmark_path, output, platform, question_form, coherence_frame_id,
        header_mode, prolific_completion_code is not None, consent_path,
        practice_path, prolific_no_consent_code is not None, quality_path,
    )
    session_opts = {
        "--consent": consent_path,
        "--practice": practice_path,
        "--prolific-no-consent-code": prolific_no_consent_code,
        "--quality-checks": quality_path,
    }
    for flag, value in session_opts.items():
        if value is not None and platform != "qualtrics":
            raise click.UsageError(
                f"{flag} is implemented for --platform qualtrics only, not {platform}."
            )
    if prolific_no_consent_code is not None and consent_path is None:
        raise click.UsageError("--prolific-no-consent-code requires --consent.")
    if prolific_completion_code is not None and platform != "qualtrics":
        raise click.UsageError(
            f"--prolific-completion-code is implemented for --platform "
            f"qualtrics only, not {platform}."
        )
    if header_mode != "per-question" and platform != "qualtrics":
        raise click.UsageError(
            f"--header-mode {header_mode} is implemented for --platform "
            f"qualtrics only; {platform} exports render the header "
            f"per-question."
        )
    try:
        benchmark = Benchmark.load(benchmark_path)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: could not load benchmark: {exc}", err=True)
        sys.exit(2)

    # Resolve an explicit --coherence-frame up front: an unknown id fails
    # fast, before any artifact is written (mirrors `infereval evaluate`).
    # None defers to render_survey_question's default frame resolution.
    coherence_frame: CoherenceFrame | None = None
    if coherence_frame_id is not None:
        try:
            coherence_frame = coherence_frame_for_id(coherence_frame_id)
        except ValueError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(2)

    # The prompt's confidence rating (survey_confidence) renders only in
    # Qualtrics; refuse elsewhere before writing anything.
    from infereval.prompts import resolve_verification_prompt

    survey_confidence = (
        resolve_verification_prompt(benchmark.verification_prompt).survey_confidence
        if question_form == "support"
        else None
    )
    if survey_confidence is not None and platform != "qualtrics":
        click.echo(
            "ERROR: the benchmark's verification prompt declares survey_confidence; "
            f"the confidence rating is qualtrics only, not {platform}.",
            err=True,
        )
        sys.exit(2)

    output.parent.mkdir(parents=True, exist_ok=True)

    if platform == "qualtrics":
        try:
            consent = load_consent(consent_path) if consent_path is not None else None
            practice = load_practice(practice_path) if practice_path is not None else None
            quality = load_quality(quality_path) if quality_path is not None else None
        except ValueError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(2)
        handoff = any(
            v is not None
            for v in (
                prolific_completion_code, consent, practice, prolific_no_consent_code, quality
            )
        )
        try:
            qsf, mapping = build_qsf(
                benchmark,
                title=title,
                randomize_items=randomize_items,
                include_rationales=include_rationales,
                expertise_prompt=expertise_prompt,
                question_form=question_form,
                coherence_frame=coherence_frame,
                header_mode=header_mode,
                prolific_completion_code=prolific_completion_code,
                consent=consent,
                practice=practice,
                prolific_no_consent_code=prolific_no_consent_code,
                quality=quality,
            )
        except ValueError as exc:
            if not handoff:
                raise
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(2)
        output.write_text(json.dumps(qsf, indent=2), encoding="utf-8")
        click.echo(f"OK: wrote Qualtrics .qsf to {output}")
        if prolific_completion_code is not None:
            click.echo(
                "  Prolific: set the study URL to <anonymous link>"
                "?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}"
                "&SESSION_ID={{%SESSION_ID%}} — the survey redirects to "
                "Prolific's completion page at the end."
            )
        if consent is not None:
            click.echo(
                f"  Consent: first page, {len(consent.statements)} statements; "
                "anyone who does not consent "
                + (
                    "is sent to Prolific with the no-consent code."
                    if prolific_no_consent_code is not None
                    else "sees the default end message."
                )
            )
        if practice is not None:
            click.echo(
                f"  Practice: {len(practice.items)} items after the instructions "
                "(exported as practice_<id>; not imported as verdicts)."
            )
        if quality is not None:
            click.echo(
                f"  Quality checks: {len(quality.attention_checks)} attention checks among "
                f"the items, {len(quality.repeats)} items repeated after them (exported as "
                "check_<id> / repeat_<tag>; import with --quality-checks for the report)."
            )
        if any(row["confidence_data_export_tag"] is not None for row in mapping):
            assert survey_confidence is not None
            click.echo(
                f"  Confidence: asked after every verdict ({len(survey_confidence.labels)} "
                "labels; imported as analyst_confidences)."
            )
        _maybe_write_mapping(output, mapping)

    elif platform == "google_forms":
        gas, mapping = build_gas_script(
            benchmark,
            title=title,
            randomize_items=randomize_items,
            include_rationales=include_rationales,
            expertise_prompt=expertise_prompt,
            question_form=question_form,
            coherence_frame=coherence_frame,
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
            coherence_frame=coherence_frame,
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
    any item id was hashed — or, since the survey frame axis, when the
    export rendered under a non-default frame or header mode: the sidecar
    is where the resolved ``frame_id`` / ``header_mode`` live on disk, and
    the import-side merge guard can only check what was recorded.
    Default-frame exports stay sidecar-free so pre-frame outputs are
    byte-unchanged. For Google
    Forms and SurveyMonkey (v0.9.1+) the sidecar is **required** for the
    importer to resolve ``Item N`` anchors back to item ids — the caller
    passes ``always=True``.
    """
    non_default_frame = any(
        isinstance(row.get("frame_id"), str)
        and row["frame_id"] not in _DEFAULT_SURVEY_FRAME_IDS
        for row in mapping
    )
    non_default_header_mode = any(
        row.get("header_mode") not in (None, "per-question") for row in mapping
    )
    if (
        not always
        and not any(row.get("was_hashed") for row in mapping)
        and not non_default_frame
        and not non_default_header_mode
    ):
        return
    sidecar = output.with_suffix(output.suffix + ".mapping.json")
    sidecar.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    log.info(
        "survey.export.mapping_sidecar path=%s rows=%d non_default_frame=%s",
        sidecar, len(mapping), non_default_frame,
    )
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
    "--exclude-respondent",
    "exclude_ids",
    multiple=True,
    help=(
        "Response id to leave out of the merge (repeatable), e.g. after "
        "applying a pre-registered exclusion rule to the quality report."
    ),
)
@click.option(
    "--quality-checks",
    "quality_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help=(
        "JSON quality checks: attention_checks (id/text/answer) shown among the "
        "items, and repeats (item ids) shown again after all items. Writes <output stem>.quality.json per respondent (checks passed, repeat consistency, duration); excludes no one. Qualtrics only."
    ),
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
@click.option(
    "--coherence-frame",
    "coherence_frame_id",
    type=str,
    default=None,
    help=(
        "Frame id you declare the survey was exported under. When the "
        "mapping sidecar records a frame_id, the merge refuses on a "
        "mismatch (responses elicited under one frame cannot be imported "
        "as another). Compared as an id string — decode is "
        "frame-independent, so no catalog lookup is needed here."
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
    exclude_ids: tuple[str, ...],
    quality_path: Path | None,
    require_complete: bool,
    question_form: str,
    coherence_frame_id: str | None,
) -> None:
    log.info(
        "survey.import.start benchmark=%s responses=%s platform=%s "
        "question_form=%s coherence_frame=%s",
        benchmark_path, responses_path, platform, question_form, coherence_frame_id,
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

    # A support prompt that declares its own survey labels was exported with
    # them; decode those exact labels (good, bad, abstain by position).
    from infereval.prompts import resolve_verification_prompt

    vp = resolve_verification_prompt(benchmark.verification_prompt)
    choices = (
        vp.survey_choices
        if question_form == "support" and vp.survey_header is not None
        else None
    )
    log.info("survey.import.choices prompt=%s choices=%s", vp.id, choices)
    # Likewise its confidence rating (Qualtrics only; the other exporters
    # refuse a prompt that declares one).
    confidence = (
        vp.survey_confidence
        if question_form == "support" and vp.survey_header is not None
        else None
    )
    if confidence is not None:
        log.info("survey.import.confidence prompt=%s labels=%s", vp.id, confidence.labels)

    if platform == "qualtrics":
        respondents = parse_qualtrics_csv(
            responses_path, question_form=question_form, choices=choices,
            confidence=confidence,
        )
    elif platform == "google_forms":
        respondents = parse_google_forms_csv(
            responses_path, mapping=mapping, question_form=question_form, choices=choices
        )
    elif platform == "surveymonkey":
        respondents = parse_surveymonkey_csv(
            responses_path, mapping=mapping, question_form=question_form, choices=choices
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

    if quality_path is not None:
        if platform != "qualtrics":
            raise click.UsageError(
                f"--quality-checks is implemented for --platform qualtrics only, not {platform}."
            )
        try:
            quality = load_quality(quality_path)
            report = quality_report(benchmark, respondents, quality, mapping=mapping)
        except ValueError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(2)
        report_path = output.with_suffix(".quality.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        summ = report["summary"]
        agreement = summ["repeat_agreement"]
        click.echo(
            f"OK: wrote quality report to {report_path} ({summ['respondents']} respondents; "
            f"{summ['failed_any_attention_check']} failed an attention check; repeat "
            f"agreement {'n/a' if agreement is None else f'{agreement:.2f}'}; median "
            f"duration {summ['median_duration_seconds']} s)"
        )
        log.info("survey.import.quality_report path=%s", report_path)

    if exclude_ids:
        unknown = sorted(set(exclude_ids) - {r.response_id for r in respondents})
        if unknown:
            click.echo(f"ERROR: --exclude-respondent ids not in the responses: {unknown}", err=True)
            sys.exit(2)
        respondents = [r for r in respondents if r.response_id not in set(exclude_ids)]
        log.info("survey.import.excluded ids=%s", ",".join(sorted(exclude_ids)))
        click.echo(f"  Excluded {len(exclude_ids)} respondent(s): {', '.join(sorted(exclude_ids))}")

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
            frame_id=coherence_frame_id,
        )
    except FrameMismatchError as exc:
        click.echo(f"ERROR: frame mismatch — {exc}", err=True)
        sys.exit(2)
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
