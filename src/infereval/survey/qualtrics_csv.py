"""Qualtrics CSV response-export reader + shared respondent merger.

Two surfaces here:

1. :func:`parse_qualtrics_csv` reads the 3-header-row Qualtrics
   ``Data + Choice Text`` CSV export and yields a list of
   :class:`~infereval.survey.render.SurveyRespondent`.
2. :func:`merge_respondents` takes a benchmark and a list of
   ``SurveyRespondent`` from any platform (Qualtrics, Google Forms,
   SurveyMonkey) and returns a new validated benchmark with one new
   analyst column per respondent. This is the *shared* merger — the
   Google Forms and SurveyMonkey CSV parsers import it from here.

The CSV format the Qualtrics user must export:

- Format → ``CSV``
- Format options → ``Use choice text`` (the cell value is the visible
  choice label, e.g. ``"Good — follows from premises"``)
- Include the first three header rows (the Qualtrics default).
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..types import Verdict
from .render import SurveyRespondent, verdict_from_choice_text

if TYPE_CHECKING:
    from ..benchmark import Benchmark

log = logging.getLogger(__name__)


# Reserved DataExportTags the parser knows about (everything else is an
# item verdict or rationale column).
_EXPERTISE_TAG = "expertise"
_RATIONALE_SUFFIX = "_rationale"

# Qualtrics's stock columns (also appear in the CSV; we use these to
# extract the respondent metadata).
_RESPONSE_ID_COL = "ResponseId"
_START_DATE_COL = "StartDate"
_FINISHED_COL = "Finished"

# Qualtrics's standard CSV export columns that are NOT verdict/rationale
# columns. We skip these unconditionally to avoid mis-parsing
# timestamps, progress percentages, etc., as verdict choice text.
_QUALTRICS_STOCK_COLUMNS: frozenset[str] = frozenset({
    "StartDate", "EndDate", "Status", "IPAddress",
    "Progress", "Duration (in seconds)", "Finished", "RecordedDate",
    "ResponseId", "RecipientLastName", "RecipientFirstName",
    "RecipientEmail", "ExternalReference", "LocationLatitude",
    "LocationLongitude", "DistributionChannel", "UserLanguage",
})


def parse_qualtrics_csv(
    path: Path,
    *,
    question_form: str = "coherence",
) -> list[SurveyRespondent]:
    """Parse a Qualtrics CSV export into a list of
    :class:`SurveyRespondent`.

    Skips the two question-text / metadata header rows that Qualtrics
    inserts after the column-name header. Maps each verdict cell's
    "Good …" / "Bad …" / "Abstain …" choice text back to
    :class:`~infereval.types.Verdict` via first-word match.

    Tolerant of missing rationale columns (rationales are optional);
    strict on malformed verdict values (anything that doesn't begin
    with one of the three keywords → :class:`ValueError` with the cell
    location).
    """
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration as exc:  # pragma: no cover -- defensive
            raise ValueError(f"Qualtrics CSV {path} is empty") from exc
        # Skip the next two metadata rows.
        try:
            next(reader)
            next(reader)
        except StopIteration:
            log.warning(
                "qualtrics.csv.short_header path=%s — expected 3 header rows; "
                "proceeding with what's available",
                path,
            )
        rows = list(reader)

    return _rows_to_respondents(header, rows, path=path, question_form=question_form)


def _rows_to_respondents(
    header: list[str],
    rows: list[list[str]],
    *,
    path: Path,
    question_form: str = "coherence",
) -> list[SurveyRespondent]:
    """Convert parsed CSV rows to ``SurveyRespondent``s."""
    col_index = {name: i for i, name in enumerate(header)}
    respondents: list[SurveyRespondent] = []
    for row_n, row in enumerate(rows, start=4):  # human-friendly 1-based + 3 header rows
        if not any(cell.strip() for cell in row):
            continue  # skip blank trailing rows

        response_id = _cell(row, col_index, _RESPONSE_ID_COL, default=f"row{row_n}")
        started_at = _parse_started_at(_cell(row, col_index, _START_DATE_COL))
        finished = _cell(row, col_index, _FINISHED_COL, default="True").strip().lower() in {
            "true", "1", "yes",
        }
        expertise_raw = _cell(row, col_index, _EXPERTISE_TAG, default="").strip() or None

        verdicts: dict[str, Verdict] = {}
        rationales: dict[str, str | None] = {}
        for col_name, col_idx in col_index.items():
            if col_name in _QUALTRICS_STOCK_COLUMNS or col_name == _EXPERTISE_TAG:
                continue
            cell = row[col_idx] if col_idx < len(row) else ""
            if col_name.endswith(_RATIONALE_SUFFIX):
                tag = col_name[: -len(_RATIONALE_SUFFIX)]
                rationales[tag] = cell.strip() or None
            else:
                tag = col_name
                if not cell.strip():
                    # Missing verdict — leave it out of the dict; the
                    # merger's require_complete check picks this up.
                    continue
                try:
                    verdicts[tag] = _verdict_from_choice_text(cell, question_form=question_form)
                except ValueError as exc:
                    raise ValueError(
                        f"{path}: row {row_n} column {col_name!r}: {exc}"
                    ) from None

        respondents.append(
            SurveyRespondent(
                response_id=response_id,
                started_at=started_at,
                finished=finished,
                expertise=expertise_raw,
                verdicts=verdicts,
                rationales=rationales,
            )
        )
    return respondents


def _cell(row: list[str], col_index: dict[str, int], name: str, *, default: str = "") -> str:
    idx = col_index.get(name)
    if idx is None or idx >= len(row):
        return default
    return row[idx]


def _parse_started_at(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)  # noqa: DTZ007 -- Qualtrics uses local time
        except ValueError:
            continue
    log.warning("qualtrics.csv.bad_start_date raw=%r — leaving None", raw)
    return None


def _verdict_from_choice_text(cell: str, *, question_form: str = "coherence") -> Verdict:
    """Map an MC choice label back to a :class:`Verdict`.

    Thin wrapper over the shared
    :func:`~infereval.survey.render.verdict_from_choice_text` (the single
    source of the choice→verdict mapping, including the coherence polarity
    inversion). Kept as a module-local name because the Google Forms and
    SurveyMonkey CSV parsers import it from here."""
    return verdict_from_choice_text(cell, question_form=question_form)


# ---- Shared merger (used by all three platforms' importers) --------------


class IncompleteRespondentError(ValueError):
    """Raised by :func:`merge_respondents` when ``require_complete=True``
    and a respondent has missing verdicts or didn't finish the survey."""


class FrameMismatchError(ValueError):
    """Raised by :func:`merge_respondents` when the coherence frame recorded
    in the export mapping sidecar conflicts with the frame the caller
    declares, or when the sidecar's rows record conflicting frames.

    Responses elicited under one norm-statement frame cannot be composed
    into a benchmark as if they were elicited under another — the frame
    is part of the instrument's identity (the survey-side analogue of the
    retest path's refusal to compose across ``question_form``)."""


def merge_respondents(
    benchmark: Benchmark,
    respondents: list[SurveyRespondent],
    *,
    mapping: list[dict[str, Any]] | None = None,
    analyst_id_prefix: str = "clinician-",
    require_complete: bool = True,
    frame_id: str | None = None,
) -> Benchmark:
    """Extend ``benchmark`` with one new analyst column per respondent.

    Parameters
    ----------
    benchmark
        The benchmark to extend. Not mutated; returned as a new
        validated model.
    respondents
        From any platform's CSV parser (Qualtrics, Google Forms,
        SurveyMonkey).
    mapping
        Optional explicit ``item_id ↔ export_tag`` mapping (the sidecar
        ``mapping.json`` written at export time). When ``None``, the
        merger derives the mapping by calling
        :func:`~infereval.survey.render.sanitize_export_tag` on each
        ``item.id`` — works when no hashed-id mapping sidecar was
        written.
    analyst_id_prefix
        Prefix for the new analyst ids. Final id is
        ``f"{prefix}{response_id}"``. Default ``"clinician-"``.
    require_complete
        When ``True`` (default), reject any respondent who didn't
        ``finished=True`` or whose verdicts cover fewer than all items.
    frame_id
        The frame the caller declares the responses were elicited under.
        Compared against the ``frame_id`` recorded per row in the export
        mapping sidecar: a mismatch raises :class:`FrameMismatchError`
        instead of silently merging analyst columns elicited under a
        different instrument. ``None`` means no declaration — the guard
        then only checks that the sidecar's own rows agree with each
        other. Decode is untouched: this guards composition, not the
        choice→verdict mapping.

    Returns
    -------
    Benchmark
        A new benchmark with ``m_old + len(respondents)`` analyst
        columns. Validated via :meth:`Benchmark.model_validate` — any
        merger bug surfaces with a clear error.

    Raises
    ------
    IncompleteRespondentError
        When ``require_complete=True`` and a respondent fails the
        completeness check.
    FrameMismatchError
        When the sidecar-recorded frame conflicts with ``frame_id`` (or
        the sidecar rows conflict with each other).
    """
    from ..benchmark import Benchmark as _Benchmark  # local import; avoid TYPE_CHECKING cycle

    _check_frame_consistency(mapping, declared_frame_id=frame_id)

    tag_for_item: dict[str, str] = _build_tag_lookup(benchmark, mapping)

    # Work with dicts throughout — model_validate runs at the end and
    # surfaces any merger bug with the existing Benchmark validator's
    # error messages.
    new_analysts: list[dict[str, Any]] = [a.model_dump() for a in benchmark.analysts]
    new_items_dicts = [item.model_dump() for item in benchmark.items]

    # The any_rationales flag drives whether we have to expand the
    # analyst_rationales list (None) into a populated [str|None] list.
    any_rationales = any(
        v for r in respondents for v in r.rationales.values() if v is not None
    )

    for respondent in respondents:
        if require_complete:
            if not respondent.finished:
                raise IncompleteRespondentError(
                    f"respondent {respondent.response_id!r} did not finish the survey; "
                    "pass --allow-partial to import anyway"
                )
            missing = [
                item.id for item in benchmark.items
                if tag_for_item[item.id] not in respondent.verdicts
            ]
            if missing:
                raise IncompleteRespondentError(
                    f"respondent {respondent.response_id!r} is missing verdicts on "
                    f"{len(missing)} item(s): {missing[:5]}{'…' if len(missing) > 5 else ''}; "
                    "pass --allow-partial to import anyway"
                )

        new_analysts.append({
            "id": f"{analyst_id_prefix}{respondent.response_id}",
            "display_name": None,
            "notes": None,
            "expertise_description": respondent.expertise,
            "panel": None,
        })

        for item_dict, item in zip(new_items_dicts, benchmark.items, strict=True):
            tag = tag_for_item[item.id]
            verdict = respondent.verdicts.get(tag, Verdict.ABSTAIN)
            item_dict["analyst_verdicts"].append(verdict)

            if any_rationales:
                # ``analyst_rationales`` semantics: the WHOLE list is
                # None (no rationale discipline on this benchmark) or a
                # ``list[str]`` where empty string ``""`` is the
                # "this analyst gave no reason on this item" sentinel.
                # Per-entry ``None`` is deliberately not supported by
                # the model — see ``BenchmarkItem.analyst_rationales``
                # docstring.
                existing_rationales = item_dict.get("analyst_rationales")
                if existing_rationales is None:
                    # Expand the previously-None list to populated:
                    # all prior analysts get the empty-string sentinel.
                    existing_rationales = [""] * len(benchmark.analysts)
                    item_dict["analyst_rationales"] = existing_rationales
                rationale = respondent.rationales.get(tag)
                existing_rationales.append(rationale if rationale is not None else "")

    # Build and validate the new benchmark.
    merged = _Benchmark.model_validate(
        {
            **benchmark.model_dump(),
            "analysts": new_analysts,
            "items": new_items_dicts,
        }
    )
    return merged


def _check_frame_consistency(
    mapping: list[dict[str, Any]] | None,
    *,
    declared_frame_id: str | None,
) -> None:
    """The merge-side frame guard (survey analogue of the retest path's
    question_form composition rule).

    Reads the ``frame_id`` recorded per row in the export mapping sidecar
    and refuses to merge when (a) the rows record conflicting frames, or
    (b) the caller declares a frame that differs from the recorded one.
    Pre-frame sidecars (no ``frame_id`` keys) and absent sidecars pass —
    there is nothing recorded to conflict with.
    """
    recorded: set[str] = set()
    if mapping is not None:
        recorded = {
            row["frame_id"]
            for row in mapping
            if isinstance(row.get("frame_id"), str)
        }
    if len(recorded) > 1:
        raise FrameMismatchError(
            f"export mapping records conflicting frame ids "
            f"{sorted(recorded)}; responses elicited under different frames "
            f"cannot be merged into one benchmark — split the artifacts and "
            f"import each under its own frame."
        )
    recorded_id = next(iter(recorded), None)
    if (
        declared_frame_id is not None
        and recorded_id is not None
        and declared_frame_id != recorded_id
    ):
        raise FrameMismatchError(
            f"declared frame_id={declared_frame_id!r} but the export mapping "
            f"records frame_id={recorded_id!r}; responses elicited under one "
            f"frame cannot be imported as another — declare the recorded "
            f"frame or re-export under the declared one."
        )
    log.info(
        "survey.merge.frame_guard declared=%s recorded=%s",
        declared_frame_id,
        recorded_id,
    )


def _build_tag_lookup(
    benchmark: Benchmark, mapping: list[dict[str, Any]] | None
) -> dict[str, str]:
    """Build ``{item.id -> sanitized_export_tag}``. Mapping sidecar
    takes precedence; fallback is :func:`sanitize_export_tag` on the
    item.id directly."""
    from .render import sanitize_export_tag

    if mapping is not None:
        out = {
            row["item_id"]: row["verdict_data_export_tag"]
            for row in mapping
            if "item_id" in row and "verdict_data_export_tag" in row
        }
        # Fill gaps with the fallback.
        for item in benchmark.items:
            if item.id not in out:
                out[item.id], _ = sanitize_export_tag(item.id)
        return out
    return {item.id: sanitize_export_tag(item.id)[0] for item in benchmark.items}
