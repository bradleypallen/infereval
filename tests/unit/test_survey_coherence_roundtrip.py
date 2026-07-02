"""Coherence-form export→import roundtrip through the platform modules.

Complements ``test_survey_question_form.py`` (which covers the shared core in
``render.py``) by checking that ``question_form="coherence"`` actually threads
through a platform exporter and a platform importer:

- Exporting under ``question_form="coherence"`` yields a question carrying the
  coherence header + the ``Incoherent`` choice (not the support surface).
- Parsing a coherence CSV cell ``"Incoherent — …"`` via the importer (with
  ``question_form="coherence"``) decodes to :class:`Verdict.GOOD` — the
  polarity inversion firewall.
"""

from __future__ import annotations

import csv
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.survey.qualtrics_csv import parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import (
    COHERENCE_QUESTION_HEADER,
    sanitize_export_tag,
)
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
