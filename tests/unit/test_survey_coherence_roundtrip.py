"""Coherence-form export→import roundtrip through the platform modules.

Complements ``test_survey_question_form.py`` (which covers the shared core in
``render.py``) by checking that ``question_form="coherence"`` actually threads
through a platform exporter and a platform importer:

- Exporting under ``question_form="coherence"`` yields a question carrying the
  coherence header + the ``Incoherent`` choice (not the support surface).
- Parsing a coherence CSV cell ``"Incoherent — …"`` via the importer (with
  ``question_form="coherence"``) decodes to :class:`Verdict.GOOD` — the
  polarity inversion firewall.

Since the survey frame axis, also the frame threading (the norm-statement
analogue of the question_form threading):

- Every export records the resolved ``frame_id`` (uniform across items) in
  the mapping sidecar rows.
- An anchored frame's ``survey_header`` lands verbatim in the platform
  artifact while the choice labels stay library-owned (the survey side of
  the polarity firewall).
- The shared merger refuses to compose responses across frames.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from infereval.benchmark import Benchmark
from infereval.survey.google_forms_gas import build_gas_script
from infereval.survey.qualtrics_csv import (
    FrameMismatchError,
    merge_respondents,
    parse_qualtrics_csv,
)
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import (
    COHERENCE_QUESTION_HEADER,
    SurveyRespondent,
    sanitize_export_tag,
)
from infereval.survey.surveymonkey_api import build_surveymonkey_payload
from infereval.templates import DEFEASIBLE_COHERENCE_FRAME
from infereval.types import Verdict


def _bench() -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "coherence-roundtrip",
            "bearers": {
                "p": {"expression": "the patient has acute dyspnea"},
                "q": {"expression": "the patient has cardiogenic pulmonary edema"},
            },
            "analysts": [{"id": "a1"}],
            "items": [
                {
                    "id": "one",
                    "premises": ["p"],
                    "conclusions": ["q"],
                    "analyst_verdicts": ["good"],
                },
            ],
        }
    )


def test_export_coherence_uses_coherence_header_and_choices() -> None:
    qsf, _mapping = build_qsf(_bench(), question_form="coherence")
    mc_payloads = [
        el["Payload"]
        for el in qsf["SurveyElements"]
        if el.get("Element") == "SQ" and el["Payload"].get("QuestionType") == "MC"
    ]
    assert len(mc_payloads) == 1
    payload = mc_payloads[0]
    # Header comes from the coherence surface, not the support one.
    assert COHERENCE_QUESTION_HEADER in payload["QuestionText"]
    # The Incoherent choice is present (support surface would say "Good").
    displays = [c["Display"] for c in payload["Choices"].values()]
    assert any(d.startswith("Incoherent") for d in displays)
    assert not any(d.startswith("Good") for d in displays)


def test_import_coherence_cell_decodes_incoherent_to_good(tmp_path: Path) -> None:
    tag, _ = sanitize_export_tag("one")
    csv_path = tmp_path / "responses.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        # Qualtrics 3-header-row shape: column names, then two metadata rows.
        writer.writerow(["ResponseId", "StartDate", "Finished", "expertise", tag])
        writer.writerow(["Response ID", "Start Date", "Finished", "expertise", "Verdict"])
        writer.writerow(["{...}", "{...}", "{...}", "{...}", "{...}"])
        writer.writerow(
            ["R_1", "2026-01-01 00:00:00", "True", "pulmonologist", "Incoherent — untenable"]
        )

    respondents = parse_qualtrics_csv(csv_path, question_form="coherence")
    assert len(respondents) == 1
    # Incoherent → good under the coherence inversion.
    assert respondents[0].verdicts[tag] == Verdict.GOOD


# ---- Frame threading (survey frame axis) ----------------------------------


class TestExportRecordsFrameId:
    def test_default_coherence_records_thin_frame(self) -> None:
        _qsf, mapping = build_qsf(_bench(), question_form="coherence")
        assert [row["frame_id"] for row in mapping] == ["thin-v1"]
        assert [row["question_form"] for row in mapping] == ["coherence"]

    def test_default_support_records_default_frame(self) -> None:
        _qsf, mapping = build_qsf(_bench(), question_form="support")
        assert [row["frame_id"] for row in mapping] == ["default-v1"]
        assert [row["question_form"] for row in mapping] == ["support"]

    def test_explicit_frame_recorded_uniformly_across_platforms(self) -> None:
        for build in (build_qsf, build_gas_script, build_surveymonkey_payload):
            _artifact, mapping = build(
                _bench(),
                question_form="coherence",
                coherence_frame=DEFEASIBLE_COHERENCE_FRAME,
            )
            recorded = {row["frame_id"] for row in mapping}
            assert recorded == {"defeasible-coherence-explicit-v1"}, build.__name__


class TestAnchoredFrameRendersInArtifact:
    def test_qsf_question_text_carries_anchored_header(self) -> None:
        """Spot-check one platform: the anchored survey_header lands verbatim
        in the artifact's rendered question, while the choice labels stay
        library-owned (the survey side of the polarity firewall)."""
        assert DEFEASIBLE_COHERENCE_FRAME.survey_header is not None
        qsf, _mapping = build_qsf(
            _bench(),
            question_form="coherence",
            coherence_frame=DEFEASIBLE_COHERENCE_FRAME,
        )
        mc_payloads = [
            el["Payload"]
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ" and el["Payload"].get("QuestionType") == "MC"
        ]
        assert len(mc_payloads) == 1
        payload = mc_payloads[0]
        assert DEFEASIBLE_COHERENCE_FRAME.survey_header in payload["QuestionText"]
        assert COHERENCE_QUESTION_HEADER not in payload["QuestionText"]
        # Choice labels are NOT frame-configurable: same three at every frame.
        displays = [c["Display"] for c in payload["Choices"].values()]
        assert sorted(d.split()[0] for d in displays) == [
            "Coherent", "Incoherent", "Unclear",
        ]


class TestMergeFrameGuard:
    def _respondent(self) -> SurveyRespondent:
        return SurveyRespondent(
            response_id="R_1",
            started_at=None,
            finished=True,
            expertise=None,
            verdicts={"one": Verdict.GOOD},
        )

    def _mapping(self, frame_id: str) -> list[dict[str, object]]:
        return [
            {
                "item_id": "one",
                "verdict_data_export_tag": "one",
                "frame_id": frame_id,
            }
        ]

    def test_declared_vs_recorded_mismatch_refused(self) -> None:
        with pytest.raises(FrameMismatchError) as exc_info:
            merge_respondents(
                _bench(),
                [self._respondent()],
                mapping=self._mapping("thin-v1"),
                frame_id="defeasible-coherence-explicit-v1",
            )
        # The error names both ids.
        message = str(exc_info.value)
        assert "thin-v1" in message
        assert "defeasible-coherence-explicit-v1" in message

    def test_conflicting_recorded_frames_refused(self) -> None:
        mapping = self._mapping("thin-v1") + [
            {
                "item_id": "two",
                "verdict_data_export_tag": "two",
                "frame_id": "defeasible-coherence-explicit-v1",
            }
        ]
        with pytest.raises(FrameMismatchError) as exc_info:
            merge_respondents(_bench(), [self._respondent()], mapping=mapping)
        message = str(exc_info.value)
        assert "thin-v1" in message
        assert "defeasible-coherence-explicit-v1" in message

    def test_matching_declaration_merges(self) -> None:
        merged = merge_respondents(
            _bench(),
            [self._respondent()],
            mapping=self._mapping("thin-v1"),
            frame_id="thin-v1",
        )
        assert len(merged.analysts) == 2

    def test_legacy_sidecar_without_frame_passes(self) -> None:
        """Pre-frame sidecars record no frame_id — nothing to conflict with."""
        legacy = [{"item_id": "one", "verdict_data_export_tag": "one"}]
        merged = merge_respondents(
            _bench(),
            [self._respondent()],
            mapping=legacy,
            frame_id="defeasible-coherence-explicit-v1",
        )
        assert len(merged.analysts) == 2

    def test_no_declaration_with_recorded_frame_passes(self) -> None:
        merged = merge_respondents(
            _bench(),
            [self._respondent()],
            mapping=self._mapping("defeasible-coherence-explicit-v1"),
        )
        assert len(merged.analysts) == 2
