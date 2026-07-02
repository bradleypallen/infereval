"""SurveyMonkey CSV response-export reader.

SurveyMonkey CSV exports look broadly like Google Forms exports:
column headers are literal question titles; choice cells hold the
literal display strings. Same ``[item:<tag>]`` regex applies — the
exporter (:mod:`surveymonkey_api`) writes the tag into each question
title for round-tripping.

Differences from Google Forms:

- SurveyMonkey adds a *second* header row labelled ``Response``
  beneath each MC question (which carries the choice text). Some
  exports collapse this; the parser tolerates either shape by skipping
  any row whose first non-empty cell is the literal ``Response``.
- The first column is usually ``Respondent ID`` (stable, unique).
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import datetime
from pathlib import Path

from ..types import Verdict
from .qualtrics_csv import _verdict_from_choice_text
from .render import SurveyRespondent

log = logging.getLogger(__name__)

_ITEM_VERDICT_RE = re.compile(r"^Item (\d+) verdict\b", re.MULTILINE)
_ITEM_RATIONALE_RE = re.compile(r"^Item (\d+) rationale\b", re.MULTILINE)
_V091_VERDICT_RE = re.compile(r"^Item (\d+) of \d+", re.MULTILINE)
_ITEM_TAG_RE = re.compile(r"\[item:([A-Za-z0-9_]+)\]")  # v0.9.0 legacy
_RATIONALE_SUFFIX = "_rationale"

_SURVEYMONKEY_STOCK_COLUMNS: frozenset[str] = frozenset({
    "Respondent ID",
    "Collector ID",
    "Start Date",
    "End Date",
    "IP Address",
    "Email Address",
    "First Name",
    "Last Name",
    "Custom Data 1",
})


def parse_surveymonkey_csv(
    path: Path,
    *,
    mapping: list[dict[str, object]] | None = None,
    question_form: str = "support",
) -> list[SurveyRespondent]:
    """Parse a SurveyMonkey CSV export into a list of
    :class:`SurveyRespondent`.

    Resolves each non-stock column header in this order:

    1. ``Item N of M`` / ``Item N rationale`` anchor (v0.9.1+ shape):
       requires the ``mapping`` sidecar to translate N → tag.
    2. ``[item:<tag>]`` regex (v0.9.0 legacy) when the title still
       carries the machine marker.
    """
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration as exc:  # pragma: no cover -- defensive
            raise ValueError(f"SurveyMonkey CSV {path} is empty") from exc
        rows = list(reader)

    # Drop the optional second-header row that SurveyMonkey writes under
    # each MC question (cell value "Response" repeated).
    while rows and rows[0] and rows[0][0].strip().lower() == "response":
        rows.pop(0)

    # Classify each column.
    col_kind: list[tuple[str, str | None]] = []
    expertise_col_idx: int | None = None
    for i, h in enumerate(header):
        if h in _SURVEYMONKEY_STOCK_COLUMNS:
            col_kind.append(("stock", None))
            continue
        kind_tag = _classify_column_header(h, mapping)
        if kind_tag is not None:
            col_kind.append(kind_tag)
        elif expertise_col_idx is None:
            col_kind.append(("expertise", None))
            expertise_col_idx = i
        else:
            col_kind.append(("stock", None))

    # Resolve where the Respondent ID column lives (used as response_id).
    respondent_id_col: int | None = None
    for i, h in enumerate(header):
        if h == "Respondent ID":
            respondent_id_col = i
            break
    start_date_col: int | None = None
    for i, h in enumerate(header):
        if h == "Start Date":
            start_date_col = i
            break

    respondents: list[SurveyRespondent] = []
    for row_n, row in enumerate(rows, start=2):
        if not any(cell.strip() for cell in row):
            continue
        response_id = (
            row[respondent_id_col].strip()
            if respondent_id_col is not None and respondent_id_col < len(row) and row[respondent_id_col].strip()
            else f"row{row_n}"
        )
        started_at: datetime | None = None
        if start_date_col is not None and start_date_col < len(row):
            started_at = _parse_timestamp(row[start_date_col])

        expertise: str | None = None
        verdicts: dict[str, Verdict] = {}
        rationales: dict[str, str | None] = {}
        for col_idx, (kind, tag) in enumerate(col_kind):
            cell = row[col_idx] if col_idx < len(row) else ""
            if kind == "stock":
                continue
            if kind == "expertise":
                expertise = cell.strip() or None
                continue
            if kind == "rationale":
                assert tag is not None
                rationales[tag] = cell.strip() or None
                continue
            if kind == "verdict":
                assert tag is not None
                if not cell.strip():
                    continue
                try:
                    verdicts[tag] = _verdict_from_choice_text(cell, question_form=question_form)
                except ValueError as exc:
                    raise ValueError(
                        f"{path}: row {row_n} column {header[col_idx]!r}: {exc}"
                    ) from None

        respondents.append(SurveyRespondent(
            response_id=response_id,
            started_at=started_at,
            finished=True,
            expertise=expertise,
            verdicts=verdicts,
            rationales=rationales,
        ))
    return respondents


def _classify_column_header(
    header: str,
    mapping: list[dict[str, object]] | None,
) -> tuple[str, str | None] | None:
    """Match a column header against ``Item N`` anchors (v0.9.1+, needs
    mapping sidecar) or the legacy ``[item:<tag>]`` regex (v0.9.0).
    Returns ``("verdict"|"rationale", tag)`` or ``None`` when no item
    classification applies."""
    if mapping is not None:
        m = _ITEM_VERDICT_RE.search(header) or _V091_VERDICT_RE.search(header)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(mapping):
                tag = mapping[idx].get("verdict_data_export_tag")
                if isinstance(tag, str):
                    return ("verdict", tag)
        m = _ITEM_RATIONALE_RE.search(header)
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(mapping):
                tag = mapping[idx].get("rationale_data_export_tag")
                if isinstance(tag, str):
                    if tag.endswith(_RATIONALE_SUFFIX):
                        tag = tag[: -len(_RATIONALE_SUFFIX)]
                    return ("rationale", tag)
    m = _ITEM_TAG_RE.search(header)
    if m:
        tag = m.group(1)
        if tag.endswith(_RATIONALE_SUFFIX):
            return ("rationale", tag[: -len(_RATIONALE_SUFFIX)])
        return ("verdict", tag)
    return None


def _parse_timestamp(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)  # noqa: DTZ007 -- SurveyMonkey uses respondent local time
        except ValueError:
            continue
    log.warning("surveymonkey.csv.bad_timestamp raw=%r — leaving None", raw)
    return None
