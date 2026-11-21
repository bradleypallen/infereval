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
5. When ``prolific_completion_code`` is given, the flow opens with an
   Embedded Data node that captures Prolific's ``PROLIFIC_PID`` /
   ``STUDY_ID`` / ``SESSION_ID`` URL parameters, and the survey ends by
   redirecting to Prolific's completion URL with that code (see
   :mod:`infereval.survey.prolific`).
6. When ``consent`` is given, the survey opens with a Consent block
   (information text, one tick box per statement, agree/decline). A
   Branch flow node right after it ends the survey for anyone who
   declines or leaves a statement unticked, before any study item.
7. When the frame declares ``survey_confidence``, a force-response
   confidence question follows each verdict on the same page (and in
   each practice item), DataExportTag ``f"{sanitized_item_id}_confidence"``.
8. When ``quality`` is given, its attention checks are shown among the
   items (in the randomizer, or evenly spaced without randomization) as
   ``check_<id>``, and its repeated items are shown again after all items
   (a second randomizer) as ``repeat_<tag>``. Both look like items: same
   answer labels, confidence and rationale questions.
   With ``assignment`` (an incomplete design), repeats must be core items.
10. When ``assignment`` is given (requires ``randomize_items``), each
   respondent sees every core item and ``rotated_per_respondent`` of the
   others: two Groups, each a randomizer (core items in full; rotated
   items as an evenly presented subset), inside an outer evenly presented
   randomizer that counterbalances which group comes first. Attention
   checks alternate between the two groups, starting with the core: among
   the core items at random, and after the rotated subset.
9. When ``practice`` is given, practice items rendered exactly like the
   benchmark items follow the instructions, outside randomization, each
   on its own page (see :mod:`infereval.survey.session`).

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

from .prolific import PROLIFIC_FIELDS, completion_url
from .render import (
    CONFIDENCE_SUFFIX,
    DEFAULT_EXPERTISE_PROMPT,
    SurveyQuestion,
    rationale_prompt,
    render_survey_question,
    sanitize_export_tag,
)
from .session import (
    CONSENT_STATEMENTS_TAG,
    CONSENT_TAG,
    REPEAT_TAG_PREFIX,
    AssignmentSpec,
    ConsentSpec,
    PracticeSpec,
    QualitySpec,
    is_session_tag,
)

if TYPE_CHECKING:
    from ..benchmark import Benchmark
    from ..prompts import ConfidenceScale, VerificationPrompt
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
    header_mode: str = "per-question",
    prolific_completion_code: str | None = None,
    consent: ConsentSpec | None = None,
    practice: PracticeSpec | None = None,
    prolific_no_consent_code: str | None = None,
    quality: QualitySpec | None = None,
    assignment: AssignmentSpec | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a Qualtrics ``.qsf`` document for ``benchmark``.

    ``coherence_frame`` / ``verification_prompt`` are passed straight
    through to :func:`~infereval.survey.render.render_survey_question`,
    where ALL frame resolution happens (explicit argument, then the
    benchmark's binding, then the library default) — the exporter never
    resolves a frame itself. The resolved frame id, uniform across every
    item in one export (asserted), is recorded on each mapping row so the
    sidecar carries the frame provenance the import guard checks.

    ``header_mode`` controls where the frame's survey header renders:

    - ``"per-question"`` (default, pre-existing behavior): the full
      header repeats above every item question.
    - ``"instructions"``: the full header renders ONCE as a survey-level
      instructions page (a Descriptive Text question shown before the
      expertise question, outside randomization); each item question
      carries only the item body plus the frame's ``survey_stem`` (the
      header's own closing question line — verbatim, so no wording enters
      the elicitation surface that is not already part of the frame).
      Fails loudly when the resolved frame declares no ``survey_stem``.

    ``prolific_completion_code`` (default ``None``: no hand-off, output
    byte-identical to earlier versions) adds the Prolific hand-off: an
    Embedded Data flow node, first in the flow, capturing
    :data:`~infereval.survey.prolific.PROLIFIC_FIELDS` from the study
    link, and an end-of-survey redirect to Prolific's completion URL with
    this code. An invalid code raises ``ValueError`` before anything is
    built.

    ``consent`` adds a Consent block as the survey's first block (after
    the Prolific Embedded Data node, when present) and a Branch node that
    ends the survey for anyone who chooses ``consent.decline`` or leaves
    any statement unticked. That ending overrides the survey-level
    Prolific redirect, so a decliner never receives the completion code:
    with ``prolific_no_consent_code`` it redirects to Prolific with that
    code (set it up in Prolific as a "no consent" code that asks the
    participant to return the study), otherwise it shows Qualtrics's
    default end message. ``prolific_no_consent_code`` requires
    ``consent``.

    ``practice`` adds practice items after the instructions (and the
    expertise question), outside randomization: an optional intro page,
    one item per page, an optional outro page. They are rendered through
    :func:`~infereval.survey.render.render_survey_question` under the
    same question form and frame as the benchmark items (asserted), and
    exported under ``practice_<id>``. They are not in ``mapping``.

    ``quality`` (a :class:`~infereval.survey.session.QualitySpec`) adds
    attention checks and repeated items; see the module docstring. A
    repeated id not in the benchmark, or a check whose ``answer`` is not
    one of the answer labels, raises ``ValueError``. Neither is in
    ``mapping``.

    ``assignment`` (an :class:`~infereval.survey.session.AssignmentSpec`)
    makes the design incomplete: every core item plus a rotated, evenly
    presented subset of the rest (see the module docstring). It needs
    ``randomize_items``; a core id not in the benchmark, too few rotated
    items, or a repeated item that is not core raises ``ValueError``.

    With any of these, a benchmark item whose export tag takes a reserved
    session form (``consent``, ``consent_*``, ``practice_*``, ``check_*``,
    ``repeat_*``) raises ``ValueError``.

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
        - ``confidence_data_export_tag`` (``None`` when the frame
          declares no ``survey_confidence``)
        - ``was_hashed`` (``True`` when the item id triggered the
          sha256-hash fallback)
        - ``question_form`` (the logical question the survey asks)
        - ``frame_id`` (the resolved norm-statement frame the header
          renders; uniform across all rows of one export)
        - ``header_mode`` (where the header rendered: per-question or
          instructions — a presentation-provenance axis)

        The CLI writes this alongside the ``.qsf`` as
        ``<output>.mapping.json`` when any item id was hashed or when
        the export rendered under a non-default frame or header mode.
    """
    if header_mode not in ("per-question", "instructions"):
        raise ValueError(
            f"unknown header_mode {header_mode!r}; expected 'per-question' "
            f"or 'instructions'."
        )
    redirect_url = (
        completion_url(prolific_completion_code)
        if prolific_completion_code is not None
        else None
    )
    if prolific_no_consent_code is not None and consent is None:
        raise ValueError("prolific_no_consent_code requires a consent page (consent=...).")
    no_consent_url = (
        completion_url(prolific_no_consent_code)
        if prolific_no_consent_code is not None
        else None
    )
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
    header_texts: set[str] = set()
    confidence_labels: list[str] | None = None
    rendered: dict[str, tuple[str, SurveyQuestion]] = {}
    for item in benchmark.items:
        tag, was_hashed = sanitize_export_tag(item.id)
        if (
            consent is not None or practice is not None or quality is not None
        ) and is_session_tag(tag):
            raise ValueError(
                f"item {item.id!r} exports under tag {tag!r}, which is reserved "
                f"for the consent/practice/quality-check pages; rename the item."
            )
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
        header_texts.add(sq.header)
        rendered[item.id] = (tag, sq)
        sq_elements.append(
            _mc_question(
                survey_id=survey_id,
                qid=verdict_qid,
                label=f"Verdict on {item.id}",
                prompt=(
                    sq.body_with_stem()
                    if header_mode == "instructions"
                    else sq.full_text()
                ),
                choices=list(sq.choices),
                data_export_tag=tag,
                force_response=True,
            )
        )
        qids = [verdict_qid]

        confidence_tag: str | None = None
        if sq.confidence is not None:
            confidence_labels = list(sq.confidence.labels)
            confidence_qid = f"QID{next_qid}"
            next_qid += 1
            confidence_tag = f"{tag}{CONFIDENCE_SUFFIX}"
            sq_elements.append(
                _confidence_question(
                    survey_id=survey_id, qid=confidence_qid, scale=sq.confidence,
                    label=f"Confidence on {item.id}", data_export_tag=confidence_tag,
                )
            )
            qids.append(confidence_qid)

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
                "confidence_data_export_tag": confidence_tag,
                "was_hashed": was_hashed,
                "question_form": sq.question_form,
                "frame_id": sq.frame_id,
                "header_mode": header_mode,
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
        "survey.export.frame platform=qualtrics benchmark=%s question_form=%s "
        "frame_id=%s header_mode=%s",
        benchmark.id,
        question_form,
        next(iter(resolved_frame_ids), None),
        header_mode,
    )
    check_units: list[tuple[str, list[str]]] = []
    repeat_units: list[tuple[str, list[str]]] = []
    if assignment is not None:
        if not randomize_items:
            raise ValueError("assignment needs randomize_items: the rotation is a randomizer")
        rotated_ids = assignment.rotated([item.id for item in benchmark.items])
        if quality is not None:
            not_core = [i for i in quality.repeats if i not in set(assignment.core)]
            if not_core:
                raise ValueError(
                    f"repeated items must be core items, so every respondent has seen them; "
                    f"not core: {not_core}"
                )
        log.info(
            "survey.export.assignment benchmark=%s core=%d rotated=%d rotated_per_respondent=%d",
            benchmark.id, len(assignment.core), len(rotated_ids),
            assignment.rotated_per_respondent,
        )
    if quality is not None:
        quality.check_items([item.id for item in benchmark.items])

        def _page(
            *, label: str, prompt: str, choices: list[str], tag: str, sq: SurveyQuestion
        ) -> list[str]:
            """An item-like page: verdict, then confidence and rationale as items have."""
            nonlocal next_qid
            qids = [f"QID{next_qid}"]
            next_qid += 1
            sq_elements.append(
                _mc_question(
                    survey_id=survey_id, qid=qids[0], label=label, prompt=prompt,
                    choices=choices, data_export_tag=tag, force_response=True,
                )
            )
            if sq.confidence is not None:
                qids.append(f"QID{next_qid}")
                next_qid += 1
                sq_elements.append(
                    _confidence_question(
                        survey_id=survey_id, qid=qids[-1], scale=sq.confidence,
                        label=f"{label} confidence", data_export_tag=f"{tag}{CONFIDENCE_SUFFIX}",
                    )
                )
            if include_rationales:
                qids.append(f"QID{next_qid}")
                next_qid += 1
                sq_elements.append(
                    _text_entry_question(
                        survey_id=survey_id, qid=qids[-1], label=f"{label} rationale",
                        prompt=rationale_prompt(question_form),
                        data_export_tag=f"{tag}_rationale", force_response=False,
                    )
                )
            return qids

        first_sq = next(iter(rendered.values()))[1]
        for check in quality.attention_checks:
            if check.answer.strip() not in [c.strip() for c in first_sq.choices]:
                raise ValueError(
                    f"attention check {check.id!r}: answer {check.answer!r} is not one "
                    f"of the answer labels {list(first_sq.choices)}"
                )
            check_units.append((
                f"check|{check.id}",
                _page(label=f"Attention check {check.id}", prompt=check.text,
                      choices=list(first_sq.choices), tag=check.tag, sq=first_sq),
            ))
        for item_id in quality.repeats:
            tag, sq = rendered[item_id]
            repeat_units.append((
                f"repeat|{item_id}",
                _page(
                    label=f"Repeat of {item_id}",
                    prompt=sq.body_with_stem() if header_mode == "instructions" else sq.full_text(),
                    choices=list(sq.choices), tag=f"{REPEAT_TAG_PREFIX}{tag}", sq=sq,
                ),
            ))
        log.info(
            "survey.export.quality benchmark=%s attention_checks=%s repeats=%s",
            benchmark.id, ",".join(c.id for c in quality.attention_checks),
            ",".join(quality.repeats),
        )

    n_conf = sum(1 for row in mapping if row["confidence_data_export_tag"] is not None)
    if n_conf:
        log.info(
            "survey.export.confidence benchmark=%s items=%d labels=%s",
            benchmark.id, n_conf, confidence_labels,
        )

    # Intro portion of the survey (always first, outside randomization):
    # under the instructions header mode, the frame's full header renders
    # once as a Descriptive Text page before the expertise question.
    intro_elements: list[dict[str, str]] = [
        {"Type": "Question", "QuestionID": expertise_qid}
    ]
    if header_mode == "instructions":
        if not header_texts:
            raise ValueError(
                "header_mode='instructions' requires at least one item (the "
                "instructions page renders the resolved frame's header)."
            )
        instructions_qid = f"QID{next_qid}"
        next_qid += 1
        sq_elements.insert(
            0,
            _descriptive_text_question(
                survey_id=survey_id,
                qid=instructions_qid,
                text=next(iter(header_texts)),
            ),
        )
        intro_elements = [
            {"Type": "Question", "QuestionID": instructions_qid},
            {"Type": "Page Break"},
            {"Type": "Question", "QuestionID": expertise_qid},
        ]

    if practice is not None:
        practice_pages, next_qid = _practice_questions(
            benchmark,
            practice,
            survey_id=survey_id,
            first_qid=next_qid,
            question_form=question_form,
            coherence_frame=coherence_frame,
            verification_prompt=verification_prompt,
            header_mode=header_mode,
            expected_frame_id=next(iter(resolved_frame_ids), None),
            sq_elements=sq_elements,
        )
        for page in practice_pages:
            intro_elements.append({"Type": "Page Break"})
            intro_elements += [{"Type": "Question", "QuestionID": qid} for qid in page]

    consent_block: dict[str, Any] | None = None
    consent_logic: dict[str, Any] | None = None
    if consent is not None:
        letter_qid, statements_qid, decision_qid = (
            f"QID{next_qid}", f"QID{next_qid + 1}", f"QID{next_qid + 2}"
        )
        next_qid += 3
        sq_elements += [
            _descriptive_text_question(
                survey_id=survey_id,
                qid=letter_qid,
                text=consent.information,
                data_export_tag="consent_information",
                label="Consent information",
            ),
            _mc_question(
                survey_id=survey_id,
                qid=statements_qid,
                label="Consent statements",
                prompt="Please tick each statement you agree with.",
                choices=list(consent.statements),
                data_export_tag=CONSENT_STATEMENTS_TAG,
                force_response=False,
                selector="MAVR",
            ),
            _mc_question(
                survey_id=survey_id,
                qid=decision_qid,
                label="Consent decision",
                prompt=(
                    "Do you agree to take part? If you do not tick every "
                    "statement above, the survey ends here."
                ),
                choices=[consent.agree, consent.decline],
                data_export_tag=CONSENT_TAG,
                force_response=True,
            ),
        ]
        consent_block = {
            "Type": "Standard",
            "Description": "Consent",
            "ID": _qsf_id("BL_", f"infereval|{benchmark.id}|block|consent"),
            "BlockElements": [
                {"Type": "Question", "QuestionID": q}
                for q in (letter_qid, statements_qid, decision_qid)
            ],
        }
        consent_logic = _no_consent_logic(
            decision_qid=decision_qid,
            statements_qid=statements_qid,
            n_statements=len(consent.statements),
        )

    blocks, flow_nodes = _blocks_and_flow(
        benchmark_id=benchmark.id,
        intro_elements=intro_elements,
        item_qids=item_qids,
        randomize_items=randomize_items,
        check_units=check_units,
        repeat_units=repeat_units,
        assignment=assignment,
    )
    # Properties.Count = total flow nodes including Root and nested
    # block nodes under a randomizer.
    def _count_nodes(nodes: list[dict[str, Any]]) -> int:
        return sum(1 + _count_nodes(n.get("Flow", [])) for n in nodes)

    # Nodes added around the item flow take the next free FlowID numbers,
    # so the item flow's own ids never change.
    def _max_flow_n(nodes: list[dict[str, Any]]) -> int:
        return max(
            [int(n["FlowID"].removeprefix("FL_")) for n in nodes]
            + [_max_flow_n(n["Flow"]) for n in nodes if n.get("Flow")]
            + [1]
        )

    if consent_block is not None and consent_logic is not None:
        blocks.insert(0, consent_block)
        n = _max_flow_n(flow_nodes)
        end_node: dict[str, Any] = {
            "Type": "EndSurvey",
            "FlowID": f"FL_{n + 3}",
            "EndingType": "Advanced",
            "Options": (
                {
                    "Advanced": "true",
                    "SurveyTermination": "Redirect",
                    "EOSRedirectURL": no_consent_url,
                }
                if no_consent_url is not None
                else {"Advanced": "true", "SurveyTermination": "DefaultMessage"}
            ),
        }
        flow_nodes[:0] = [
            {"ID": consent_block["ID"], "Type": "Standard", "FlowID": f"FL_{n + 1}"},
            {
                "Type": "Branch",
                "FlowID": f"FL_{n + 2}",
                "Description": "End the survey without consent",
                "BranchLogic": consent_logic,
                "Flow": [end_node],
            },
        ]
        log.info(
            "survey.export.consent benchmark=%s statements=%d decline_ending=%s",
            benchmark.id,
            len(consent.statements) if consent is not None else 0,
            "prolific_redirect" if no_consent_url is not None else "default_message",
        )

    if redirect_url is not None:
        # Embedded Data must be set before any block runs, so it is the
        # flow's first node.
        flow_nodes.insert(
            0,
            _embedded_data_node(f"FL_{_max_flow_n(flow_nodes) + 1}", PROLIFIC_FIELDS),
        )
        log.info(
            "survey.export.prolific benchmark=%s fields=%s redirect_host=app.prolific.com",
            benchmark.id,
            ",".join(PROLIFIC_FIELDS),
        )

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
            _envelope("SO", "Survey Options", _survey_options(redirect_url=redirect_url)),
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
    intro_elements: list[dict[str, str]],
    item_qids: list[tuple[str, list[str]]],
    randomize_items: bool,
    check_units: list[tuple[str, list[str]]] | None = None,
    repeat_units: list[tuple[str, list[str]]] | None = None,
    assignment: AssignmentSpec | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build the BL payload (list of blocks) and the Root flow's nodes.

    ``intro_elements`` are the BlockElements of the survey's non-item
    lead-in (expertise question, plus the instructions page under that
    header mode) — always shown first, outside randomization.

    ``randomize_items=False``: one Default block holding every question
    with explicit page breaks, plus the Trash block; the flow is a
    single Block node — this shape matches the import-proven reference
    files node-for-node.

    ``randomize_items=True``: an Introduction block (``intro_elements``
    only), one Standard block per item (verdict + rationale; block
    boundaries paginate), and a ``BlockRandomizer`` flow node over the
    item blocks with ``SubSet = n`` (present all items, random order).

    ``check_units`` (attention checks) join the items: in the randomizer,
    or evenly spaced among them without randomization. ``repeat_units``
    follow all items: a second randomizer, or in the given order.

    ``assignment`` (randomized only) replaces the single item randomizer
    with an outer randomizer over two Groups, core and rotated; see the
    module docstring.
    """
    check_units = check_units or []
    repeat_units = repeat_units or []
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
                "BlockElements": list(intro_elements),
            }
        ]
        item_nodes: list[dict[str, Any]] = []
        node_of_item: dict[str, dict[str, Any]] = {}
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
            node_of_item[item_id] = item_nodes[-1]
            flow_n += 1
        # Quality-check blocks take FlowIDs after the items', so the item
        # flow is unchanged without them.
        def _unit_block(unit_id: str, qids: list[str]) -> str:
            block_id = _qsf_id("BL_", f"infereval|{benchmark_id}|block|{unit_id}")
            blocks.append(
                {
                    "Type": "Standard",
                    "Description": unit_id.replace("|", " "),
                    "ID": block_id,
                    "BlockElements": [
                        {"Type": "Question", "QuestionID": qid} for qid in qids
                    ],
                }
            )
            return block_id

        check_nodes: list[dict[str, Any]] = []
        for unit_id, qids in check_units:
            check_nodes.append(
                {"ID": _unit_block(unit_id, qids), "Type": "Standard", "FlowID": f"FL_{flow_n}"}
            )
            flow_n += 1
        flow_nodes: list[dict[str, Any]] = [{"ID": intro_id, "Type": "Block", "FlowID": "FL_2"}]
        if assignment is None:
            flow_nodes.append(
                {
                    "Type": "BlockRandomizer",
                    "FlowID": "FL_3",
                    "SubSet": len(item_nodes) + len(check_nodes),
                    "EvenPresentation": False,
                    "Flow": item_nodes + check_nodes,
                }
            )
        else:
            core = set(assignment.core)
            core_nodes = [node_of_item[i] for i, _ in item_qids if i in core]
            rotated_nodes = [node_of_item[i] for i, _ in item_qids if i not in core]
            # Checks alternate between the parts, starting with the core,
            # so each part has its share whichever comes first.
            core_nodes += check_nodes[0::2]
            rotated_checks = check_nodes[1::2]

            def _group(description: str, randomizer: dict[str, Any]) -> dict[str, Any]:
                nonlocal flow_n
                group = {
                    "Type": "Group",
                    "FlowID": f"FL_{flow_n}",
                    "Description": description,
                    "Flow": [randomizer],
                }
                flow_n += 1
                randomizer["FlowID"] = f"FL_{flow_n}"
                flow_n += 1
                return group

            core_group = _group("Core items", {
                "Type": "BlockRandomizer",
                "SubSet": len(core_nodes),
                "EvenPresentation": False,
                "Flow": core_nodes,
            })
            rotated_flow: list[dict[str, Any]] = [{
                "Type": "BlockRandomizer",
                "SubSet": assignment.rotated_per_respondent,
                "EvenPresentation": True,
                "Flow": rotated_nodes,
            }]
            rotated_group = _group("Rotated items", rotated_flow[0])
            if rotated_checks:
                # A subset randomizer cannot guarantee a check is chosen,
                # so the rotated part's checks follow its subset, in
                # their own randomizer.
                rotated_group["Flow"].append({
                    "Type": "BlockRandomizer",
                    "FlowID": f"FL_{flow_n}",
                    "SubSet": len(rotated_checks),
                    "EvenPresentation": False,
                    "Flow": rotated_checks,
                })
                flow_n += 1
            flow_nodes.append(
                {
                    "Type": "BlockRandomizer",
                    "FlowID": "FL_3",
                    "SubSet": 2,
                    "EvenPresentation": True,
                    "Flow": [core_group, rotated_group],
                }
            )
        if repeat_units:
            randomizer_n = flow_n
            repeat_nodes = []
            for unit_id, qids in repeat_units:
                flow_n += 1
                repeat_nodes.append(
                    {"ID": _unit_block(unit_id, qids), "Type": "Standard",
                     "FlowID": f"FL_{flow_n}"}
                )
            flow_nodes.append(
                {
                    "Type": "BlockRandomizer",
                    "FlowID": f"FL_{randomizer_n}",
                    "SubSet": len(repeat_nodes),
                    "EvenPresentation": False,
                    "Flow": repeat_nodes,
                }
            )
        blocks.append(trash_block)
        return blocks, flow_nodes

    items_id = _qsf_id("BL_", f"infereval|{benchmark_id}|block|items")
    block_elements: list[dict[str, str]] = [
        *intro_elements,
        {"Type": "Page Break"},
    ]
    units = [qids for _item_id, qids in item_qids]
    # Attention checks evenly spaced among the items, repeats at the end.
    for k, (_unit_id, qids) in reversed(list(enumerate(check_units))):
        units.insert(round((k + 1) * len(item_qids) / (len(check_units) + 1)), qids)
    units += [qids for _unit_id, qids in repeat_units]
    for qids in units:
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


def _practice_questions(
    benchmark: Benchmark,
    practice: PracticeSpec,
    *,
    survey_id: str,
    first_qid: int,
    question_form: str,
    coherence_frame: CoherenceFrame | None,
    verification_prompt: VerificationPrompt | None,
    header_mode: str,
    expected_frame_id: str | None,
    sq_elements: list[dict[str, Any]],
) -> tuple[list[list[str]], int]:
    """Append the practice pages' questions to ``sq_elements``.

    Practice items become a throwaway benchmark that shares the real
    benchmark's id and frame bindings, so
    :func:`~infereval.survey.render.render_survey_question` renders them
    through exactly the same path (body format, header, stem, choices).
    Returns the QIDs page by page and the next free QID number.
    """
    from ..benchmark import Benchmark as _Benchmark

    bearers: dict[str, dict[str, str]] = {}
    items: list[dict[str, Any]] = []
    for p in practice.items:
        prem_ids = [f"{p.id}__p{i}" for i in range(len(p.premises))]
        concl_id = f"{p.id}__c"
        bearers.update({b: {"expression": t} for b, t in zip(prem_ids, p.premises, strict=True)})
        bearers[concl_id] = {"expression": p.conclusion}
        items.append(
            {
                "id": p.id,
                "premises": prem_ids,
                "conclusions": [concl_id],
                "analyst_verdicts": ["abstain"],
            }
        )
    base = benchmark.model_dump(
        mode="json",
        include={
            "schema_version", "id", "title", "context_builders",
            "verification_prompt", "template_id", "coherence_frame_id",
        },
        exclude_none=True,
    )
    shadow = _Benchmark.model_validate(
        {**base, "bearers": bearers, "items": items, "analysts": [{"id": "practice"}]}
    )

    qid_n = first_qid
    pages: list[list[str]] = []

    def _next() -> str:
        nonlocal qid_n
        qid = f"QID{qid_n}"
        qid_n += 1
        return qid

    if practice.intro:
        qid = _next()
        sq_elements.append(
            _descriptive_text_question(
                survey_id=survey_id, qid=qid, text=practice.intro,
                data_export_tag="practice_intro", label="Practice introduction",
            )
        )
        pages.append([qid])
    for p, item in zip(practice.items, shadow.items, strict=True):
        sq = render_survey_question(
            shadow,
            item,
            question_form=question_form,
            coherence_frame=coherence_frame,
            verification_prompt=verification_prompt,
        )
        if expected_frame_id is not None and sq.frame_id != expected_frame_id:
            raise ValueError(
                f"practice item {p.id!r} rendered under frame {sq.frame_id!r}, "
                f"but the benchmark items use {expected_frame_id!r}."
            )
        qid = _next()
        sq_elements.append(
            _mc_question(
                survey_id=survey_id,
                qid=qid,
                label=f"Practice {p.id}",
                prompt=sq.body_with_stem() if header_mode == "instructions" else sq.full_text(),
                choices=list(sq.choices),
                data_export_tag=p.tag,
                force_response=True,
            )
        )
        page = [qid]
        if sq.confidence is not None:
            cqid = _next()
            sq_elements.append(
                _confidence_question(
                    survey_id=survey_id, qid=cqid, scale=sq.confidence,
                    label=f"Practice {p.id} confidence",
                    data_export_tag=f"{p.tag}{CONFIDENCE_SUFFIX}",
                )
            )
            page.append(cqid)
        pages.append(page)
    if practice.outro:
        qid = _next()
        sq_elements.append(
            _descriptive_text_question(
                survey_id=survey_id, qid=qid, text=practice.outro,
                data_export_tag="practice_outro", label="Practice end",
            )
        )
        pages.append([qid])
    log.info(
        "survey.export.practice benchmark=%s items=%s frame_id=%s",
        benchmark.id, ",".join(p.id for p in practice.items), expected_frame_id,
    )
    return pages, qid_n


def _no_consent_logic(
    *, decision_qid: str, statements_qid: str, n_statements: int
) -> dict[str, Any]:
    """BranchLogic: decline chosen, OR any consent statement unticked."""

    def _expr(qid: str, choice: int, operator: str, description: str) -> dict[str, Any]:
        locator = f"q://{qid}/SelectableChoice/{choice}"
        return {
            "LogicType": "Question",
            "QuestionID": qid,
            "QuestionIsInLoop": "no",
            "ChoiceLocator": locator,
            "Operator": operator,
            "QuestionIDFromLocator": qid,
            "LeftOperand": locator,
            "Type": "Expression",
            "Description": description,
        }

    exprs = [_expr(decision_qid, 2, "Selected", "Consent decision: decline is selected")]
    exprs += [
        _expr(statements_qid, k, "NotSelected", f"Consent statement {k} is not selected")
        for k in range(1, n_statements + 1)
    ]
    condition: dict[str, Any] = {"Type": "If"}
    for i, e in enumerate(exprs):
        if i:
            e = {**e, "Conjuction": "Or"}  # Qualtrics's own spelling
        condition[str(i)] = e
    return {"0": condition, "Type": "BooleanExpression"}


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


def _embedded_data_node(flow_id: str, fields: tuple[str, ...]) -> dict[str, Any]:
    """An Embedded Data flow node whose fields are filled from the URL.

    ``Type: "Recipient"`` is Qualtrics's "set from panel or URL" source:
    a field with that type and no value takes the same-named query
    parameter of the survey link, which is how Prolific ids arrive.
    """
    return {
        "Type": "EmbeddedData",
        "FlowID": flow_id,
        "EmbeddedData": [
            {
                "Description": field,
                "Type": "Recipient",
                "Field": field,
                "VariableType": "String",
                "DataVisibility": [],
                "AnalyzeText": False,
            }
            for field in fields
        ],
    }


def _survey_options(*, redirect_url: str | None = None) -> dict[str, Any]:
    """Minimal import-proven Survey Options payload.

    With ``redirect_url`` the survey ends by sending the respondent to
    that URL (Qualtrics's "Redirect to a URL" end-of-survey option)
    instead of the default thank-you message.
    """
    options = {
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
    if redirect_url is not None:
        options["SurveyTermination"] = "Redirect"
        options["EOSRedirectURL"] = redirect_url
    return options


def _descriptive_text_question(
    *,
    survey_id: str,
    qid: str,
    text: str,
    data_export_tag: str = "instructions",
    label: str = "Instructions",
) -> dict[str, Any]:
    """A Descriptive Text (DB) element — display-only, collects no data.

    Used by the instructions header mode to show the frame's full survey
    header once, on its own page, before the expertise question, and for
    the consent information and practice intro/outro pages.
    """
    return {
        "SurveyID": survey_id,
        "Element": "SQ",
        "PrimaryAttribute": qid,
        "SecondaryAttribute": label,
        "TertiaryAttribute": None,
        "Payload": {
            "QuestionText": text,
            "DataExportTag": data_export_tag,
            "QuestionID": qid,
            "QuestionType": "DB",
            "Selector": "TB",
            "DataVisibility": {"Private": False, "Hidden": False},
            "Configuration": {"QuestionDescriptionOption": "UseText"},
            "QuestionDescription": label,
            "Validation": {"Settings": {"Type": "None"}},
            "Language": [],
        },
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


def _confidence_question(
    *, survey_id: str, qid: str, scale: ConfidenceScale, label: str, data_export_tag: str
) -> dict[str, Any]:
    """The force-response confidence rating asked after a verdict."""
    return _mc_question(
        survey_id=survey_id, qid=qid, label=label, prompt=scale.prompt,
        choices=list(scale.labels), data_export_tag=data_export_tag, force_response=True,
    )


def _mc_question(
    *,
    survey_id: str,
    qid: str,
    label: str,
    prompt: str,
    choices: list[str],
    data_export_tag: str,
    force_response: bool,
    selector: str = "SAVR",
) -> dict[str, Any]:
    """A multiple-choice question element: single answer (``SAVR``) or
    multiple answer (``MAVR``), vertical."""
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
            "Selector": selector,
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
