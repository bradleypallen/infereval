"""Qualtrics ``.qsf`` survey-file generator.

Produces a Qualtrics Survey Format (``.qsf``) JSON document the
recruiter uploads to Qualtrics (Account → Tools → Import Survey). The
imported survey has:

1. A first-block expertise free-text question (DataExportTag
   ``"expertise"``).
2. One multiple-choice (Good / Bad / Abstain) question per benchmark
   item, force-response, DataExportTag = sanitized item.id.
3. When ``include_rationales=True``, an optional free-text rationale
   question follows each MC, DataExportTag =
   ``f"{sanitized_item_id}_rationale"``.
4. When ``randomize_items=True``, the items block carries a
   `Randomization.RandomizeAll` payload listing the item QIDs (the
   expertise question stays at position 0 and is excluded from
   randomization).

The ``.qsf`` format is JSON but Qualtrics's documentation is sparse;
the field shapes below are reverse-engineered from real Qualtrics
exports + the Qualtrics community wiki. The known-good fragment at
``tests/fixtures/qualtrics/qsf_known_good.json`` is the structural
golden the tests validate against.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .render import (
    DEFAULT_EXPERTISE_PROMPT,
    DEFAULT_QUESTION_HEADER,
    DEFAULT_RATIONALE_PROMPT,
    DEFAULT_VERDICT_CHOICES,
    render_implication_text,
    sanitize_export_tag,
)

if TYPE_CHECKING:
    from ..benchmark import Benchmark

log = logging.getLogger(__name__)

# Stable fake IDs for the boilerplate Qualtrics fields. Real Qualtrics
# imports regenerate these on the server side; the importer only cares
# that they're internally consistent across the file.
_SURVEY_ID = "SV_infereval_recruit"
_BLOCK_ID = "BL_items"


def build_qsf(
    benchmark: Benchmark,
    *,
    title: str | None = None,
    randomize_items: bool = True,
    include_rationales: bool = True,
    expertise_prompt: str = DEFAULT_EXPERTISE_PROMPT,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a Qualtrics ``.qsf`` document for ``benchmark``.

    Returns
    -------
    qsf_dict
        The full ``.qsf`` document as a Python dict. The caller is
        responsible for ``json.dumps`` to disk (the CLI does this).
    mapping
        List of per-item mapping records, one dict per benchmark item:

        - ``item_id``
        - ``verdict_data_export_tag``
        - ``rationale_data_export_tag`` (``None`` when
          ``include_rationales=False``)
        - ``was_hashed`` (``True`` when the item id triggered the
          sha256-hash fallback)

        The CLI writes this alongside the ``.qsf`` as
        ``<output>.mapping.json`` when any item id was hashed.
    """
    effective_title = title if title is not None else f"Analyst recruitment for {benchmark.id}"

    elements: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []

    # Expertise question at QID1 — outside randomization.
    expertise_qid = "QID1"
    expertise_export_tag = "expertise"
    elements.append(
        _text_entry_question(
            qid=expertise_qid,
            label=expertise_prompt,
            prompt=expertise_prompt,
            data_export_tag=expertise_export_tag,
            force_response=False,
        )
    )

    # Per-item questions: verdict (MC) + optional rationale (TE).
    # QIDs allocated 2, 3, ... in stable order.
    item_question_qids: list[str] = []  # for the Randomization payload.
    block_elements: list[dict[str, str]] = [
        {"Type": "Question", "QuestionID": expertise_qid},
        {"Type": "PageBreak"},
    ]
    next_qid = 2
    for item in benchmark.items:
        tag, was_hashed = sanitize_export_tag(item.id)
        verdict_qid = f"QID{next_qid}"
        next_qid += 1

        verdict_prompt = (
            DEFAULT_QUESTION_HEADER
            + "\n\n"
            + render_implication_text(benchmark, item)
        )
        elements.append(
            _mc_question(
                qid=verdict_qid,
                label=f"Verdict on {item.id}",
                prompt=verdict_prompt,
                choices=list(DEFAULT_VERDICT_CHOICES),
                data_export_tag=tag,
                force_response=True,
            )
        )
        block_elements.append({"Type": "Question", "QuestionID": verdict_qid})

        rationale_qid: str | None = None
        rationale_tag: str | None = None
        if include_rationales:
            rationale_qid = f"QID{next_qid}"
            next_qid += 1
            rationale_tag = f"{tag}_rationale"
            elements.append(
                _text_entry_question(
                    qid=rationale_qid,
                    label=f"Rationale on {item.id}",
                    prompt=DEFAULT_RATIONALE_PROMPT,
                    data_export_tag=rationale_tag,
                    force_response=False,
                )
            )
            block_elements.append({"Type": "Question", "QuestionID": rationale_qid})

        block_elements.append({"Type": "PageBreak"})

        item_question_qids.append(verdict_qid)
        if rationale_qid is not None:
            item_question_qids.append(rationale_qid)

        mapping.append(
            {
                "item_id": item.id,
                "verdict_data_export_tag": tag,
                "rationale_data_export_tag": rationale_tag,
                "was_hashed": was_hashed,
            }
        )

    # Single block holding the page-broken elements; randomization on items only.
    block_payload: dict[str, Any] = {
        "Type": "Default",
        "Description": "Items",
        "ID": _BLOCK_ID,
        "BlockElements": block_elements,
    }
    if randomize_items and item_question_qids:
        block_payload["Options"] = {
            "BlockLocking": "false",
            "RandomizeQuestions": "RandomWithXPrior",
            "BlockVisibility": "Collapsed",
            "Randomization": {
                "Advanced": None,
                "TotalRandSubset": str(len(item_question_qids)),
                "EvenPresentation": False,
                "QuestionsPerPage": "0",
                "RandomizeAll": item_question_qids,
            },
        }

    blocks_element: dict[str, Any] = {
        "SurveyID": _SURVEY_ID,
        "Element": "BL",
        "PrimaryAttribute": "Survey Blocks",
        "SecondaryAttribute": None,
        "TertiaryAttribute": None,
        "Payload": [block_payload],
    }

    qsf: dict[str, Any] = {
        "SurveyEntry": _survey_entry(effective_title),
        "SurveyElements": [blocks_element, *elements],
    }
    return qsf, mapping


# ---- Internal builders ---------------------------------------------------


def _survey_entry(title: str) -> dict[str, Any]:
    """Minimal SurveyEntry boilerplate. Qualtrics fills in / overrides
    most of these at import time on the server side; we just need the
    field shapes to be present."""
    return {
        "SurveyID": _SURVEY_ID,
        "SurveyName": title,
        "SurveyDescription": None,
        "SurveyOwnerID": None,
        "SurveyBrandID": None,
        "DivisionID": None,
        "SurveyLanguage": "EN",
        "SurveyActiveResponseSet": "RS_default",
        "SurveyStatus": "Inactive",
        "SurveyStartDate": "0000-00-00 00:00:00",
        "SurveyExpirationDate": "0000-00-00 00:00:00",
        "SurveyCreationDate": "2026-01-01 00:00:00",
        "CreatorID": None,
        "LastModified": "2026-01-01 00:00:00",
        "LastAccessed": "0000-00-00 00:00:00",
        "LastActivated": "0000-00-00 00:00:00",
        "Deleted": None,
    }


def _text_entry_question(
    *,
    qid: str,
    label: str,
    prompt: str,
    data_export_tag: str,
    force_response: bool,
) -> dict[str, Any]:
    """An open-text (essay) question element."""
    return {
        "SurveyID": _SURVEY_ID,
        "Element": "SQ",
        "PrimaryAttribute": qid,
        "SecondaryAttribute": label,
        "TertiaryAttribute": None,
        "Payload": {
            "QuestionText": prompt,
            "DefaultChoices": False,
            "DataExportTag": data_export_tag,
            "QuestionID": qid,
            "QuestionType": "TE",
            "Selector": "ESTB",
            "DataVisibility": {"Private": False, "Hidden": False},
            "Configuration": {"QuestionDescriptionOption": "UseText"},
            "QuestionDescription": label,
            "Validation": {
                "Settings": {
                    "ForceResponse": "ON" if force_response else "OFF",
                    "Type": "None",
                },
            },
            "Language": [],
        },
    }


def _mc_question(
    *,
    qid: str,
    label: str,
    prompt: str,
    choices: list[str],
    data_export_tag: str,
    force_response: bool,
) -> dict[str, Any]:
    """A multiple-choice (single-answer, vertical) question element."""
    choice_dict = {str(i + 1): {"Display": c} for i, c in enumerate(choices)}
    choice_order = [str(i + 1) for i in range(len(choices))]
    return {
        "SurveyID": _SURVEY_ID,
        "Element": "SQ",
        "PrimaryAttribute": qid,
        "SecondaryAttribute": label,
        "TertiaryAttribute": None,
        "Payload": {
            "QuestionText": prompt,
            "DataExportTag": data_export_tag,
            "QuestionID": qid,
            "QuestionType": "MC",
            "Selector": "SAVR",
            "SubSelector": "TX",
            "Configuration": {"QuestionDescriptionOption": "UseText"},
            "QuestionDescription": label,
            "Choices": choice_dict,
            "ChoiceOrder": choice_order,
            "Validation": {
                "Settings": {
                    "ForceResponse": "ON" if force_response else "OFF",
                    "Type": "None",
                },
            },
            "Language": [],
            "DataVisibility": {"Private": False, "Hidden": False},
            "NextChoiceId": len(choices) + 1,
            "NextAnswerId": 1,
        },
    }
