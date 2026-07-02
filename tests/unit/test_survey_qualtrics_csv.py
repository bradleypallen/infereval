"""Tests for ``infereval.survey.qualtrics_csv`` —
``parse_qualtrics_csv`` and the shared ``merge_respondents`` merger.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infereval.benchmark import BearerModel, Benchmark, BenchmarkItem
from infereval.survey.qualtrics_csv import (
    IncompleteRespondentError,
    merge_respondents,
    parse_qualtrics_csv,
)
from infereval.survey.render import SurveyRespondent
from infereval.types import Verdict

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "qualtrics"
    / "responses_known_good.csv"
)


# ---- parse_qualtrics_csv --------------------------------------------------


class TestParseQualtricsCsv:
    def test_parses_three_respondents(self) -> None:
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        assert len(respondents) == 3
        ids = [r.response_id for r in respondents]
        assert ids == ["R_alpha", "R_beta", "R_gamma"]

    def test_expertise_extracted(self) -> None:
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        assert respondents[0].expertise == "Pulmonologist, 12 years, board certified"
        assert respondents[1].expertise == "Critical care, 8 years"
        assert respondents[2].expertise == "Pulmonology fellow"

    def test_finished_flag(self) -> None:
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        assert all(r.finished for r in respondents)

    def test_verdicts_mapped_to_enum(self) -> None:
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        r_alpha = respondents[0]
        # item_001 -> Good, item_002 -> Bad, item_003 -> Good,
        # item_004 -> Abstain, item_005 -> Good.
        assert r_alpha.verdicts == {
            "item_001": Verdict.GOOD,
            "item_002": Verdict.BAD,
            "item_003": Verdict.GOOD,
            "item_004": Verdict.ABSTAIN,
            "item_005": Verdict.GOOD,
        }

    def test_rationales_separated_by_suffix(self) -> None:
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        # R_alpha gave rationales on items 1, 2, 4; blank elsewhere.
        assert respondents[0].rationales["item_001"] == "classic presentation"
        assert respondents[0].rationales["item_002"] == "missing key finding"
        assert respondents[0].rationales["item_003"] is None
        assert respondents[0].rationales["item_004"] == "need more imaging"

    def test_missing_verdict_means_absent_dict_entry(self) -> None:
        """R_gamma's item_005 cell is blank — the parser leaves that
        tag out of the verdicts dict (rather than inserting Abstain).
        The merger's require_complete check picks this up."""
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        r_gamma = respondents[2]
        assert "item_005" not in r_gamma.verdicts

    def test_malformed_verdict_raises_with_location(self, tmp_path: Path) -> None:
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text(
            "ResponseId,Finished,expertise,item_001\n"
            "label_row,label_row,label_row,label_row\n"
            "metadata,metadata,metadata,metadata\n"
            "R_bad,True,test,Maybe — uncertain\n"
        )
        with pytest.raises(ValueError, match="row 4 column 'item_001'"):
            parse_qualtrics_csv(bad_csv)


# ---- merge_respondents ----------------------------------------------------


def _five_item_benchmark() -> Benchmark:
    """Synthetic 5-item benchmark whose item ids match the CSV fixture's
    column DataExportTags (``item_001`` … ``item_005``)."""
    return Benchmark(
        id="merge-test",
        bearers={
            "p": BearerModel(expression="premise"),
            "c": BearerModel(expression="conclusion"),
        },
        analysts=[{"id": "seed-analyst"}],
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


class TestMergeRespondents:
    def test_adds_one_analyst_per_respondent(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        # R_gamma is incomplete; restrict to the two complete ones to
        # exercise the happy path.
        complete = [r for r in respondents if r.response_id != "R_gamma"]
        merged = merge_respondents(bench, complete)
        assert len(merged.analysts) == 1 + 2  # seed + 2 new
        new_ids = [a.id for a in merged.analysts[1:]]
        assert new_ids == ["clinician-R_alpha", "clinician-R_beta"]

    def test_expertise_landed_on_new_analysts(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")[:2]
        merged = merge_respondents(bench, respondents)
        assert merged.analysts[1].expertise_description == "Pulmonologist, 12 years, board certified"
        assert merged.analysts[2].expertise_description == "Critical care, 8 years"

    def test_verdicts_positionally_appended(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")[:2]
        merged = merge_respondents(bench, respondents)
        # item_001: [seed_GOOD, R_alpha_GOOD, R_beta_GOOD].
        assert merged.items[0].analyst_verdicts == [Verdict.GOOD, Verdict.GOOD, Verdict.GOOD]
        # item_002: [seed_GOOD, R_alpha_BAD, R_beta_GOOD].
        assert merged.items[1].analyst_verdicts == [Verdict.GOOD, Verdict.BAD, Verdict.GOOD]
        # item_004: [seed_GOOD, R_alpha_ABSTAIN, R_beta_GOOD].
        assert merged.items[3].analyst_verdicts == [Verdict.GOOD, Verdict.ABSTAIN, Verdict.GOOD]

    def test_rationales_expanded_from_None_when_first_arrives(self) -> None:  # noqa: N802 -- literal None
        """Pre-merge ``analyst_rationales=None`` (no rationale discipline).
        First respondent with any rationale → expand to populated list;
        prior analysts get empty-string sentinel per the model's
        documented semantics."""
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")[:2]
        merged = merge_respondents(bench, respondents)
        # item_001: R_alpha said "classic presentation"; seed analyst
        # gets empty string; R_beta gets empty string (no rationale).
        assert merged.items[0].analyst_rationales == ["", "classic presentation", ""]

    def test_require_complete_rejects_incomplete_respondent(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        with pytest.raises(IncompleteRespondentError, match="R_gamma.*missing"):
            merge_respondents(bench, respondents, require_complete=True)

    def test_allow_partial_inserts_abstain_for_missing(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")
        merged = merge_respondents(bench, respondents, require_complete=False)
        # R_gamma is the 3rd new analyst — index 3 in the merged list
        # (seed + alpha + beta + gamma).
        assert len(merged.analysts) == 4
        # item_005: R_gamma missing → defaulted to ABSTAIN.
        assert merged.items[4].analyst_verdicts[-1] == Verdict.ABSTAIN

    def test_custom_analyst_id_prefix(self) -> None:
        bench = _five_item_benchmark()
        respondents = parse_qualtrics_csv(FIXTURE, question_form="support")[:1]
        merged = merge_respondents(bench, respondents, analyst_id_prefix="expert-")
        assert merged.analysts[-1].id == "expert-R_alpha"

    def test_explicit_mapping_takes_precedence_over_id_derivation(self) -> None:
        """When the recruiter passes a sidecar mapping, the merger
        honors it even if the item.id sanitizes to a different tag."""
        bench = _five_item_benchmark()
        # Force one item to look up via an explicit (different) tag.
        mapping = [
            {"item_id": "item_001", "verdict_data_export_tag": "custom_tag_001"},
            {"item_id": "item_002", "verdict_data_export_tag": "item_002"},
            {"item_id": "item_003", "verdict_data_export_tag": "item_003"},
            {"item_id": "item_004", "verdict_data_export_tag": "item_004"},
            {"item_id": "item_005", "verdict_data_export_tag": "item_005"},
        ]
        # Use a custom respondent whose verdicts include the custom tag.
        custom = [SurveyRespondent(
            response_id="R_custom",
            started_at=None,
            finished=True,
            expertise="test",
            verdicts={
                "custom_tag_001": Verdict.BAD,
                "item_002": Verdict.GOOD,
                "item_003": Verdict.GOOD,
                "item_004": Verdict.GOOD,
                "item_005": Verdict.GOOD,
            },
            rationales={},
        )]
        merged = merge_respondents(bench, custom, mapping=mapping)
        # item_001's new analyst verdict is BAD because the mapping
        # said look up under custom_tag_001.
        assert merged.items[0].analyst_verdicts[-1] == Verdict.BAD
