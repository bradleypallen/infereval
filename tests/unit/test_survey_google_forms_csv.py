"""Tests for ``infereval.survey.google_forms_csv.parse_google_forms_csv``
+ the merger integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from infereval.benchmark import BearerModel, Benchmark, BenchmarkItem
from infereval.survey.google_forms_csv import parse_google_forms_csv
from infereval.survey.qualtrics_csv import merge_respondents
from infereval.types import Verdict

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "google_forms"
    / "responses_known_good.csv"
)


class TestParseGoogleFormsCsv:
    def test_parses_two_respondents(self) -> None:
        respondents = parse_google_forms_csv(FIXTURE)
        assert len(respondents) == 2

    def test_response_ids_synthesized(self) -> None:
        """Google Forms doesn't surface a ResponseId; we synthesize
        ``row<n>``."""
        respondents = parse_google_forms_csv(FIXTURE)
        assert respondents[0].response_id == "row2"
        assert respondents[1].response_id == "row3"

    def test_expertise_extracted_from_first_non_stock_column(self) -> None:
        respondents = parse_google_forms_csv(FIXTURE)
        assert respondents[0].expertise == "Pulmonologist, 12 years"
        assert respondents[1].expertise == "Critical care, 8 years"

    def test_verdicts_mapped_via_item_tag_regex(self) -> None:
        """Each column header with ``[item:<tag>]`` (no ``_rationale``
        suffix) parses into the verdicts dict, keyed by the tag."""
        respondents = parse_google_forms_csv(FIXTURE)
        r0 = respondents[0]
        assert r0.verdicts == {
            "item_001": Verdict.GOOD,
            "item_002": Verdict.BAD,
            "item_003": Verdict.GOOD,
            "item_004": Verdict.ABSTAIN,
            "item_005": Verdict.GOOD,
        }

    def test_rationales_separated_by_suffix(self) -> None:
        respondents = parse_google_forms_csv(FIXTURE)
        assert respondents[0].rationales["item_001"] == "classic presentation"
        assert respondents[0].rationales["item_002"] == "missing key finding"
        assert respondents[0].rationales["item_003"] is None
        assert respondents[0].rationales["item_004"] == "need more imaging"

    def test_finished_always_true(self) -> None:
        """Google Forms only stores completed submissions."""
        respondents = parse_google_forms_csv(FIXTURE)
        assert all(r.finished for r in respondents)


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
    def test_merges_two_respondents_into_benchmark(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_google_forms_csv(FIXTURE)
        merged = merge_respondents(bench, respondents)
        assert len(merged.analysts) == 3  # seed + 2 from CSV

    def test_merged_analyst_ids_use_synthesized_response_id(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_google_forms_csv(FIXTURE)
        merged = merge_respondents(bench, respondents)
        assert merged.analysts[1].id == "clinician-row2"
        assert merged.analysts[2].id == "clinician-row3"


# ---- Defensive: malformed verdict ----------------------------------------


def test_malformed_verdict_in_google_forms_csv_raises(tmp_path: Path) -> None:
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "Timestamp,expertise,Item 1 [item:item_001]\n"
        "6/1/2026 10:00:00,test,Maybe — uncertain\n"
    )
    with pytest.raises(ValueError, match="row 2"):
        parse_google_forms_csv(bad_csv)
