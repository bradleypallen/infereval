"""Per-respondent quality report: attention checks, repeated items, duration.

Built by ``infereval survey import --quality-checks FILE`` from a survey
exported with the same file (see :class:`~infereval.survey.session.QualitySpec`).
Every measure uses only the respondent's own answers, never agreement with
a model or with other analysts, so applying an exclusion rule to it cannot
build a model's answers into the reference standard.

The report excludes no one. Which respondents to drop is the study's
pre-registered decision; the CLI's ``--exclude-respondent`` applies it.
"""

from __future__ import annotations

import logging
import statistics
from typing import TYPE_CHECKING, Any

from .qualtrics_csv import _build_tag_lookup

if TYPE_CHECKING:
    from ..benchmark import Benchmark
    from .render import SurveyRespondent
    from .session import QualitySpec

log = logging.getLogger(__name__)


def quality_report(
    benchmark: Benchmark,
    respondents: list[SurveyRespondent],
    spec: QualitySpec,
    *,
    mapping: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One row per respondent, plus a summary.

    Per respondent:

    - ``attention``: each check's chosen label, expected label and
      ``passed``; ``attention_passed`` of ``attention_total``.
    - ``repeats``: for each repeated item, the verdict (and confidence)
      on the first and second showing and whether the verdicts are the
      same; ``repeats_same`` of ``repeats_answered`` (both showings
      answered).
    - ``duration_seconds`` from the platform export.
    """
    spec.check_items([item.id for item in benchmark.items])
    tag_for_item = _build_tag_lookup(benchmark, mapping)
    rows: list[dict[str, Any]] = []
    for r in respondents:
        passed = {c.id: c.passed(r.check_answers.get(c.id)) for c in spec.attention_checks}
        attention = {
            c.id: {
                "answer": r.check_answers.get(c.id),
                "expected": c.answer,
                "passed": passed[c.id],
            }
            for c in spec.attention_checks
        }
        repeats: dict[str, dict[str, Any]] = {}
        for item_id in spec.repeats:
            tag = tag_for_item[item_id]
            first, second = r.verdicts.get(tag), r.repeat_verdicts.get(tag)
            repeats[item_id] = {
                "first": first.value if first is not None else None,
                "second": second.value if second is not None else None,
                "first_confidence": r.confidences.get(tag),
                "second_confidence": r.repeat_confidences.get(tag),
                "same": None if first is None or second is None else first == second,
            }
        answered = [v["same"] for v in repeats.values() if v["same"] is not None]
        row = {
            "response_id": r.response_id,
            "finished": r.finished,
            "duration_seconds": r.duration_seconds,
            "attention": attention,
            "attention_passed": sum(passed.values()),
            "attention_total": len(attention),
            "repeats": repeats,
            "repeats_same": sum(answered),
            "repeats_answered": len(answered),
        }
        rows.append(row)
        log.info(
            "survey.quality.respondent response_id=%s attention=%d/%d repeats_same=%d/%d "
            "duration_seconds=%s",
            r.response_id, row["attention_passed"], row["attention_total"],
            row["repeats_same"], row["repeats_answered"], r.duration_seconds,
        )

    durations = [r["duration_seconds"] for r in rows if r["duration_seconds"] is not None]
    answered_total = sum(r["repeats_answered"] for r in rows)
    summary = {
        "respondents": len(rows),
        "attention_checks": [c.id for c in spec.attention_checks],
        "repeats": list(spec.repeats),
        "failed_any_attention_check": sum(
            r["attention_passed"] < r["attention_total"] for r in rows
        ),
        "repeat_agreement": (
            sum(r["repeats_same"] for r in rows) / answered_total if answered_total else None
        ),
        "median_duration_seconds": statistics.median(durations) if durations else None,
    }
    log.info(
        "survey.quality.summary respondents=%d failed_any_attention_check=%d "
        "repeat_agreement=%s median_duration_seconds=%s",
        summary["respondents"], summary["failed_any_attention_check"],
        summary["repeat_agreement"], summary["median_duration_seconds"],
    )
    return {"summary": summary, "respondents": rows}
