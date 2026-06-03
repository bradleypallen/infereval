"""Tests for ``infereval.survey.surveymonkey_csv.parse_surveymonkey_csv``."""

from __future__ import annotations

from pathlib import Path

import pytest

from infereval.benchmark import BearerModel, Benchmark, BenchmarkItem
from infereval.survey.qualtrics_csv import merge_respondents
from infereval.survey.surveymonkey_csv import parse_surveymonkey_csv
from infereval.types import Verdict

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "surveymonkey"
    / "responses_known_good.csv"
)


class TestParseSurveymonkeyCsv:
    def test_parses_two_respondents(self) -> None:
        respondents = parse_surveymonkey_csv(FIXTURE)
        assert len(respondents) == 2

    def test_uses_respondent_id_column(self) -> None:
        respondents = parse_surveymonkey_csv(FIXTURE)
        ids = [r.response_id for r in respondents]
        assert ids == ["SM_resp_alpha", "SM_resp_beta"]

    def test_expertise_extracted(self) -> None:
        respondents = parse_surveymonkey_csv(FIXTURE)
        assert respondents[0].expertise == "Pulmonologist, 12 years"
        assert respondents[1].expertise == "Critical care, 8 years"

    def test_verdicts_via_item_tag_regex(self) -> None:
        respondents = parse_surveymonkey_csv(FIXTURE)
        assert respondents[0].verdicts == {
            "item_001": Verdict.GOOD,
            "item_002": Verdict.BAD,
            "item_003": Verdict.GOOD,
            "item_004": Verdict.ABSTAIN,
            "item_005": Verdict.GOOD,
        }

    def test_rationales_separated_by_suffix(self) -> None:
        respondents = parse_surveymonkey_csv(FIXTURE)
        assert respondents[0].rationales["item_001"] == "classic presentation"
        assert respondents[0].rationales["item_002"] == "missing finding"
        assert respondents[0].rationales["item_003"] is None
        assert respondents[0].rationales["item_004"] == "need imaging"


# ---- Merger integration --------------------------------------------------


def _five_item_benchmark() -> Benchmark:
    return Benchmark(
        id="merge-test",
        bearers={
            "p": BearerModel(expression="premise"),
            "c": BearerModel(expression="conclusion"),
        },
        analysts=[{"id": "seed"}],
        items=[
            BenchmarkItem(
                id=f"item_00{i+1}",
                premises=["p"],
                conclusions=["c"],
                analyst_verdicts=[Verdict.GOOD],
            )
            for i in range(5)
        ],
    )


class TestMergerIntegration:
    def test_merges_two_respondents(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_surveymonkey_csv(FIXTURE)
        merged = merge_respondents(bench, respondents)
        assert len(merged.analysts) == 3
        ids = [a.id for a in merged.analysts[1:]]
        assert ids == ["clinician-SM_resp_alpha", "clinician-SM_resp_beta"]


# ---- Optional second-header tolerance ------------------------------------


def test_skips_response_second_header_row(tmp_path: Path) -> None:
    """SurveyMonkey sometimes writes a second header row labelled
    'Response' under each MC column; the parser skips it."""
    csv_with_extra = tmp_path / "with_response_header.csv"
    csv_with_extra.write_text(
        'Respondent ID,Expertise,"Item 1 [item:item_001]"\n'
        'Response,Open-ended response,Response\n'
        'SM_1,test,Good — follows from premises\n'
    )
    respondents = parse_surveymonkey_csv(csv_with_extra)
    assert len(respondents) == 1
    assert respondents[0].response_id == "SM_1"


def test_malformed_verdict_in_surveymonkey_csv_raises(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        'Respondent ID,Expertise,"Item 1 [item:item_001]"\n'
        'SM_1,test,Maybe — uncertain\n'
    )
    with pytest.raises(ValueError, match="row 2"):
        parse_surveymonkey_csv(bad_csv)
