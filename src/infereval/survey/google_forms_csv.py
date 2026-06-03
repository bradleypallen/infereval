"""Google Forms CSV response-export reader.

Google Forms doesn't have a ``DataExportTag`` equivalent — the linked
Google Sheet's column headers are the literal question titles. So the
exporter encodes the item.id (sanitized) as ``[item:<tag>]`` inside
the question title; this parser extracts the tag via regex.

CSV shape produced by Google Forms ``File → Download → CSV``:

- Single header row (column names = literal question titles).
- One row per respondent.
- The standard ``Timestamp`` column is the first column.
- Google does not include a ``ResponseId`` column natively; we
  synthesize ``f"row{n}"`` if absent.
- Choice values are the literal display strings (``"Good — follows from
  premises"`` etc.), matching what
  :func:`~infereval.survey.qualtrics_csv._verdict_from_choice_text`
  expects.
"""

from __future__ import annotations

import csv
import logging
import re
from datetime import datetime
from pathlib import Path

from ..types import Verdict
from .qualtrics_csv import _verdict_from_choice_text  # reuse the choice-text mapper
from .render import SurveyRespondent

log = logging.getLogger(__name__)


# Matches the `[item:<tag>]` substring the Apps Script generator
# embeds in each question's title. The tag respects
# ``sanitize_export_tag``'s output: ``[A-Za-z0-9_]+``.
_ITEM_TAG_RE = re.compile(r"\[item:([A-Za-z0-9_]+)\]")
_RATIONALE_SUFFIX = "_rationale"

# Stock Google Forms columns to skip when scanning for verdict columns.
_GOOGLE_FORMS_STOCK_COLUMNS: frozenset[str] = frozenset({
    "Timestamp",
    "Email Address",
    "Email address",
    "Score",
    "Username",
})


def parse_google_forms_csv(path: Path) -> list[SurveyRespondent]:
    """Parse a Google Forms CSV export into a list of
    :class:`SurveyRespondent`.

    Maps each column header through :data:`_ITEM_TAG_RE` to recover the
    sanitized item tag. Verdict cells follow the same first-word-match
    contract as Qualtrics: ``"Good …"``, ``"Bad …"``, ``"Abstain …"``.
    """
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration as exc:  # pragma: no cover -- defensive
            raise ValueError(f"Google Forms CSV {path} is empty") from exc
        rows = list(reader)

    # For each header, attempt to extract a [item:<tag>] match.
    # When a header has _rationale-suffixed tag, route it to rationales.
    col_kind: list[tuple[str, str | None]] = []  # (kind, tag)
    expertise_col_idx: int | None = None
    for i, h in enumerate(header):
        if h in _GOOGLE_FORMS_STOCK_COLUMNS:
            col_kind.append(("stock", None))
            continue
        m = _ITEM_TAG_RE.search(h)
        if m:
            tag = m.group(1)
            if tag.endswith(_RATIONALE_SUFFIX):
                col_kind.append(("rationale", tag[: -len(_RATIONALE_SUFFIX)]))
            else:
                col_kind.append(("verdict", tag))
        elif expertise_col_idx is None:
            # First non-stock, non-item column is treated as expertise.
            col_kind.append(("expertise", None))
            expertise_col_idx = i
        else:
            col_kind.append(("stock", None))

    respondents: list[SurveyRespondent] = []
    for row_n, row in enumerate(rows, start=2):  # 1-based + 1 header row
        if not any(cell.strip() for cell in row):
            continue
        started_at: datetime | None = None
        expertise: str | None = None
        verdicts: dict[str, Verdict] = {}
        rationales: dict[str, str | None] = {}
        for col_idx, (kind, tag) in enumerate(col_kind):
            cell = row[col_idx] if col_idx < len(row) else ""
            if kind == "stock":
                if header[col_idx] == "Timestamp" and cell.strip():
                    started_at = _parse_timestamp(cell)
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
                    verdicts[tag] = _verdict_from_choice_text(cell)
                except ValueError as exc:
                    raise ValueError(
                        f"{path}: row {row_n} column {header[col_idx]!r}: {exc}"
                    ) from None

        respondents.append(SurveyRespondent(
            response_id=f"row{row_n}",
            started_at=started_at,
            finished=True,  # Google Forms always submits completed responses.
            expertise=expertise,
            verdicts=verdicts,
            rationales=rationales,
        ))
    return respondents


def _parse_timestamp(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in (
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)  # noqa: DTZ007 -- Google Forms uses local time
        except ValueError:
            continue
    log.warning("google_forms.csv.bad_timestamp raw=%r — leaving None", raw)
    return None
