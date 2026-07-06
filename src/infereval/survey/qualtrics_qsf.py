"""Qualtrics ``.qsf`` survey-file generator.

Produces a Qualtrics Survey Format (``.qsf``) JSON document the
recruiter uploads to Qualtrics (Projects → Create a new project →
Survey → "Import a QSF file"). The imported survey has:

1. A first-block expertise free-text question (DataExportTag
   ``"expertise"``), always shown first and outside randomization.
2. One multiple-choice verdict question per benchmark item,
   force-response, DataExportTag = sanitized item.id.
3. When ``include_rationales=True``, an optional free-text rationale
   question follows each MC on the same page, DataExportTag =
   ``f"{sanitized_item_id}_rationale"``.
4. When ``randomize_items=True``, each item's questions live in their
   own survey block and the flow presents those blocks through a
   ``BlockRandomizer`` node (all items, random order). Randomization
   is over item *units*, never individual questions, so a rationale
   can never be separated from its verdict.

The ``.qsf`` format is JSON but Qualtrics's documentation is sparse;
the shapes below follow real Qualtrics survey exports and two
import-proven reference files. The importer needs more than blocks
and questions: a Survey Flow (``FL``) element that instantiates the
blocks (a flow-less file is rejected outright), Survey Options
(``SO``), the companion ``SCO``/``PROJ``/``STAT``/``QC``/``RS``
elements, and strictly formatted ids (``SV_``/``BL_``/``RS_``/``UR_``
plus exactly 15 alphanumerics). All ids are derived deterministically
from the benchmark id via sha256 — no randomness, no timestamps — so
identical inputs yield byte-identical artifacts, the property the
golden tests pin. :func:`_validate_qsf` re-checks the structural
contract on every build and logs an element census for post-run
analysis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from .render import (
    DEFAULT_EXPERTISE_PROMPT,
    rationale_prompt,
    render_survey_question,
    sanitize_export_tag,
)

if TYPE_CHECKING:
    from ..benchmark import Benchmark
    from ..prompts import VerificationPrompt
    from ..templates import CoherenceFrame

log = logging.getLogger(__name__)


def _qsf_id(prefix: str, seed: str) -> str:
    """Deterministic Qualtrics-format id: ``prefix`` + 15 hex chars.

    Real Qualtrics ids match ``^XX_[a-zA-Z0-9]{15}$``; lowercase hex
    from sha256 satisfies that grammar while keeping the artifact
    reproducible for the golden byte-identity tests.
    """
    return prefix + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:15]


#: Fixed owner/creator id — Qualtrics regenerates ownership at import
#: time; the importer only requires a format-valid value, not a real one.
_OWNER_ID = _qsf_id("UR_", "infereval|owner")

_ID_GRAMMAR = {
    "SurveyID": re.compile(r"SV_[a-zA-Z0-9]{15}"),
    "BlockID": re.compile(r"BL_[a-zA-Z0-9]{15}"),
    "ResponseSetID": re.compile(r"RS_[a-zA-Z0-9]{15}"),
    "OwnerID": re.compile(r"UR_[a-zA-Z0-9]{15}"),
    "QuestionID": re.compile(r"QID[0-9]+"),
    "FlowID": re.compile(r"FL_[0-9]+"),
}


def build_qsf(
    benchmark: Benchmark,
    *,
    title: str | None = None,
    randomize_items: bool = True,
    include_rationales: bool = True,
    expertise_prompt: str = DEFAULT_EXPERTISE_PROMPT,
    question_form: str = "support",
    coherence_frame: CoherenceFrame | None = None,
    verification_prompt: VerificationPrompt | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a Qualtrics ``.qsf`` document for ``benchmark``.

    ``coherence_frame`` / ``verification_prompt`` are passed straight
    through to :func:`~infereval.survey.render.render_survey_question`,
    where ALL frame resolution happens (explicit argument, then the
    benchmark's binding, then the library default) — the exporter never
    resolves a frame itself. The resolved frame id, uniform across every
    item in one export (asserted), is recorded on each mapping row so the
    sidecar carries the frame provenance the import guard checks.

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
        - ``question_form`` (the logical question the survey asks)
        - ``frame_id`` (the resolved norm-statement frame the header
          renders; uniform across all rows of one export)

        The CLI writes this alongside the ``.qsf`` as
        ``<output>.mapping.json`` when any item id was hashed or when
        the export rendered under a non-default frame.
    """
    effective_title = title if title is not None else f"Analyst recruitment for {benchmark.id}"

    survey_id = _qsf_id("SV_", f"infereval|{benchmark.id}|survey")
    rs_id = _qsf_id("RS_", f"infereval|{benchmark.id}|rs")

    sq_elements: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []

    # Expertise question at QID1 — always first, outside randomization.
    expertise_qid = "QID1"
    sq_elements.append(
        _text_entry_question(
            survey_id=survey_id,
            qid=expertise_qid,
            label=expertise_prompt,
            prompt=expertise_prompt,
            data_export_tag="expertise",
            force_response=False,
        )
    )

    # Per-item questions: verdict (MC) + optional rationale (TE).
    # QIDs allocated 2, 3, ... in stable order.
    item_qids: list[tuple[str, list[str]]] = []  # (item.id, its QIDs)
    next_qid = 2
    resolved_frame_ids: set[str | None] = set()
    for item in benchmark.items:
        tag, was_hashed = sanitize_export_tag(item.id)
        verdict_qid = f"QID{next_qid}"
        next_qid += 1

        sq = render_survey_question(
            benchmark,
            item,
            question_form=question_form,
            coherence_frame=coherence_frame,
            verification_prompt=verification_prompt,
        )
        resolved_frame_ids.add(sq.frame_id)
        sq_elements.append(
            _mc_question(
                survey_id=survey_id,
                qid=verdict_qid,
                label=f"Verdict on {item.id}",
                prompt=sq.full_text(),
                choices=list(sq.choices),
                data_export_tag=tag,
                force_response=True,
            )
        )
        qids = [verdict_qid]

        rationale_tag: str | None = None
        if include_rationales:
            rationale_qid = f"QID{next_qid}"
            next_qid += 1
            rationale_tag = f"{tag}_rationale"
            sq_elements.append(
                _text_entry_question(
                    survey_id=survey_id,
                    qid=rationale_qid,
                    label=f"Rationale on {item.id}",
                    prompt=rationale_prompt(question_form),
                    data_export_tag=rationale_tag,
                    force_response=False,
                )
            )
            qids.append(rationale_qid)

        item_qids.append((item.id, qids))
        mapping.append(
            {
                "item_id": item.id,
                "verdict_data_export_tag": tag,
                "rationale_data_export_tag": rationale_tag,
                "was_hashed": was_hashed,
                "question_form": sq.question_form,
                "frame_id": sq.frame_id,
            }
        )

    # One export = one frame: every item's header renders the same
    # norm-statement surface, so the sidecar's per-row frame_id is a
    # single value. A violation is a render.py resolution bug.
    assert len(resolved_frame_ids) <= 1, (
        f"survey export resolved multiple frame ids in one export: "
        f"{sorted(str(f) for f in resolved_frame_ids)}"
    )
    log.info(
        "survey.export.frame platform=qualtrics benchmark=%s question_form=%s frame_id=%s",
        benchmark.id,
        question_form,
        next(iter(resolved_frame_ids), None),
    )

    blocks, flow_nodes = _blocks_and_flow(
        benchmark_id=benchmark.id,
        expertise_qid=expertise_qid,
        item_qids=item_qids,
        randomize_items=randomize_items,
    )
    # Properties.Count = total flow nodes including Root and nested
    # block nodes under a randomizer.
    def _count_nodes(nodes: list[dict[str, Any]]) -> int:
        return sum(1 + _count_nodes(n.get("Flow", [])) for n in nodes)

    flow_count = 1 + _count_nodes(flow_nodes)

    def _envelope(
        element: str,
        primary: str,
        payload: Any,
        secondary: str | None = None,
        tertiary: str | None = None,
    ) -> dict[str, Any]:
        return {
            "SurveyID": survey_id,
            "Element": element,
            "PrimaryAttribute": primary,
            "SecondaryAttribute": secondary,
            "TertiaryAttribute": tertiary,
            "Payload": payload,
        }

    qsf: dict[str, Any] = {
        "SurveyEntry": _survey_entry(effective_title, survey_id=survey_id, rs_id=rs_id),
        "SurveyElements": [
            _envelope("BL", "Survey Blocks", blocks),
            _envelope(
                "FL",
                "Survey Flow",
                {
                    "Type": "Root",
                    "FlowID": "FL_1",
                    "Flow": flow_nodes,
                    "Properties": {"Count": flow_count},
                },
            ),
            _envelope("SO", "Survey Options", _survey_options()),
            _envelope(
                "SCO",
                "Scoring",
                {
                    "ScoringCategories": [],
                    "ScoringCategoryGroups": [],
                    "ScoringSummaryCategory": None,
                    "ScoringSummaryAfterQuestions": 0,
                    "ScoringSummaryAfterSurvey": 0,
                    "DefaultScoringCategory": None,
                    "AutoScoringCategory": None,
                },
            ),
            _envelope(
                "PROJ",
                "CORE",
                {"ProjectCategory": "CORE", "SchemaVersion": "1.1.0"},
                tertiary="1.1.0",
            ),
            _envelope(
                "STAT",
                "Survey Statistics",
                {"MobileCompatible": True, "ID": "Survey Statistics"},
            ),
            _envelope("QC", "Survey Question Count", None, secondary=str(len(sq_elements))),
            _envelope("RS", rs_id, None, secondary="Default Response Set"),
            *sq_elements,
        ],
    }
    _validate_qsf(qsf, benchmark_id=benchmark.id)
    return qsf, mapping


# ---- Internal builders ---------------------------------------------------


def _blocks_and_flow(
    *,
    benchmark_id: str,
    expertise_qid: str,
    item_qids: list[tuple[str, list[str]]],
    randomize_items: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the BL payload (list of blocks) and the Root flow's nodes.

    ``randomize_items=False``: one Default block holding every question
    with explicit page breaks, plus the Trash block; the flow is a
    single Block node — this shape matches the import-proven reference
    files node-for-node.

    ``randomize_items=True``: an Introduction block (expertise only),
    one Standard block per item (verdict + rationale; block boundaries
    paginate), and a ``BlockRandomizer`` flow node over the item blocks
    with ``SubSet = n`` (present all items, random order).
    """
    trash_block = {
        "Type": "Trash",
        "Description": "Trash / Unused Questions",
        "ID": _qsf_id("BL_", f"infereval|{benchmark_id}|block|trash"),
        "BlockElements": [],
    }

    if randomize_items and item_qids:
        intro_id = _qsf_id("BL_", f"infereval|{benchmark_id}|block|intro")
        blocks: list[dict[str, Any]] = [
            {
                "Type": "Default",
                "Description": "Introduction",
                "ID": intro_id,
                "BlockElements": [{"Type": "Question", "QuestionID": expertise_qid}],
            }
        ]
        item_nodes: list[dict[str, Any]] = []
        flow_n = 4  # FL_1 Root, FL_2 intro, FL_3 randomizer, then items.
        for item_id, qids in item_qids:
            block_id = _qsf_id("BL_", f"infereval|{benchmark_id}|block|{item_id}")
            blocks.append(
                {
                    "Type": "Standard",
                    "Description": f"Item {item_id}",
                    "ID": block_id,
                    "BlockElements": [
                        {"Type": "Question", "QuestionID": qid} for qid in qids
                    ],
                }
            )
            item_nodes.append({"ID": block_id, "Type": "Standard", "FlowID": f"FL_{flow_n}"})
            flow_n += 1
        blocks.append(trash_block)
        flow_nodes: list[dict[str, Any]] = [
            {"ID": intro_id, "Type": "Block", "FlowID": "FL_2"},
            {
                "Type": "BlockRandomizer",
                "FlowID": "FL_3",
                "SubSet": len(item_qids),
                "EvenPresentation": False,
                "Flow": item_nodes,
            },
        ]
        return blocks, flow_nodes

    items_id = _qsf_id("BL_", f"infereval|{benchmark_id}|block|items")
    block_elements: list[dict[str, str]] = [
        {"Type": "Question", "QuestionID": expertise_qid},
        {"Type": "Page Break"},
    ]
    for _item_id, qids in item_qids:
        block_elements.extend({"Type": "Question", "QuestionID": qid} for qid in qids)
        block_elements.append({"Type": "Page Break"})
    single_block: list[dict[str, Any]] = [
        {
            "Type": "Default",
            "Description": "Items",
            "ID": items_id,
            "BlockElements": block_elements,
        },
        trash_block,
    ]
    single_flow: list[dict[str, Any]] = [{"ID": items_id, "Type": "Block", "FlowID": "FL_2"}]
    return single_block, single_flow


def _survey_entry(title: str, *, survey_id: str, rs_id: str) -> dict[str, Any]:
    """SurveyEntry boilerplate. Qualtrics regenerates ownership and
    dates at import time; the importer requires format-valid ids (no
    nulls for owner/creator) and tolerates sentinel dates."""
    return {
        "SurveyID": survey_id,
        "SurveyName": title,
        "SurveyDescription": None,
        "SurveyOwnerID": _OWNER_ID,
        "SurveyBrandID": "infereval",
        "DivisionID": None,
        "SurveyLanguage": "EN",
        "SurveyActiveResponseSet": rs_id,
        "SurveyStatus": "Inactive",
        "SurveyStartDate": "0000-00-00 00:00:00",
        "SurveyExpirationDate": "0000-00-00 00:00:00",
        "SurveyCreationDate": "2026-01-01 00:00:00",
        "CreatorID": _OWNER_ID,
        "LastModified": "2026-01-01 00:00:00",
        "LastAccessed": "0000-00-00 00:00:00",
        "LastActivated": "0000-00-00 00:00:00",
        "Deleted": None,
    }


def _survey_options() -> dict[str, Any]:
    """Minimal import-proven Survey Options payload."""
    return {
        "BackButton": "false",
        "SaveAndContinue": "true",
        "SurveyProtection": "PublicSurvey",
        "BallotBoxStuffingPrevention": "false",
        "NoIndex": "Yes",
        "SecureResponseFiles": "true",
        "SurveyExpiration": "None",
        "SurveyTermination": "DefaultMessage",
        "Header": "",
        "Footer": "",
        "ProgressBarDisplay": "None",
        "PartialData": "+1 week",
        "ValidationMessage": "",
        "PreviousButton": "",
        "NextButton": "",
        "SkinLibrary": "qualtrics",
        "SkinType": "MQ",
        "Skin": "skin1",
        "NewScoring": 1,
        "CustomStyles": "",
    }


def _text_entry_question(
    *,
    survey_id: str,
    qid: str,
    label: str,
    prompt: str,
    data_export_tag: str,
    force_response: bool,
) -> dict[str, Any]:
    """An open-text (essay) question element."""
    return {
        "SurveyID": survey_id,
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
    survey_id: str,
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
        "SurveyID": survey_id,
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


# ---- Structural self-check ------------------------------------------------


def _validate_qsf(qsf: dict[str, Any], *, benchmark_id: str) -> None:
    """Assert the structural contract a live Qualtrics import enforces.

    Checks id grammar, cross-references (flow → blocks, blocks →
    questions), and the question count, then logs an element census so
    a failed import can be diagnosed from the run log alone.
    """
    entry = qsf["SurveyEntry"]
    elements = qsf["SurveyElements"]

    census: dict[str, int] = {}
    for el in elements:
        census[el["Element"]] = census.get(el["Element"], 0) + 1
    for required in ("BL", "FL", "SO", "SCO", "PROJ", "STAT", "QC", "RS"):
        assert census.get(required) == 1, f"expected exactly one {required} element: {census}"

    assert _ID_GRAMMAR["SurveyID"].fullmatch(entry["SurveyID"])
    assert _ID_GRAMMAR["OwnerID"].fullmatch(entry["SurveyOwnerID"])
    assert _ID_GRAMMAR["ResponseSetID"].fullmatch(entry["SurveyActiveResponseSet"])
    for el in elements:
        assert el["SurveyID"] == entry["SurveyID"], "element SurveyID mismatch"

    by_type = {el["Element"]: el for el in elements if el["Element"] != "SQ"}
    blocks = by_type["BL"]["Payload"]
    block_ids = {b["ID"] for b in blocks}
    for bid in block_ids:
        assert _ID_GRAMMAR["BlockID"].fullmatch(bid), bid

    def _block_refs(nodes: list[dict[str, Any]]) -> set[str]:
        refs: set[str] = set()
        for node in nodes:
            assert _ID_GRAMMAR["FlowID"].fullmatch(node["FlowID"]), node
            if "ID" in node:
                refs.add(node["ID"])
            refs |= _block_refs(node.get("Flow", []))
        return refs

    flow_refs = _block_refs(by_type["FL"]["Payload"]["Flow"])
    assert flow_refs <= block_ids, f"flow references unknown blocks: {flow_refs - block_ids}"

    sq_by_qid = {el["PrimaryAttribute"]: el for el in elements if el["Element"] == "SQ"}
    for qid, el in sq_by_qid.items():
        assert _ID_GRAMMAR["QuestionID"].fullmatch(qid), qid
        assert el["Payload"]["QuestionID"] == qid, qid
    referenced_qids = {
        be["QuestionID"]
        for b in blocks
        for be in b["BlockElements"]
        if be.get("Type") == "Question"
    }
    assert referenced_qids == set(sq_by_qid), (
        f"block/question mismatch: {referenced_qids ^ set(sq_by_qid)}"
    )
    assert by_type["QC"]["SecondaryAttribute"] == str(len(sq_by_qid))
    assert by_type["RS"]["PrimaryAttribute"] == entry["SurveyActiveResponseSet"]

    log.info(
        "survey.export.qsf.census benchmark=%s survey_id=%s census=%s flow_count=%s",
        benchmark_id,
        entry["SurveyID"],
        json.dumps(census, sort_keys=True),
        by_type["FL"]["Payload"]["Properties"]["Count"],
    )
