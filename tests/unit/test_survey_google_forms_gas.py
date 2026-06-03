"""Tests for ``infereval.survey.google_forms_gas.build_gas_script``."""

from __future__ import annotations

import logging
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.survey.google_forms_gas import build_gas_script
from infereval.survey.render import DEFAULT_VERDICT_CHOICES

PULM_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "pulmonary_edema" / "benchmark.json"
)


def _pulm() -> Benchmark:
    return Benchmark.load(PULM_PATH)


class TestGasStructure:
    def test_emits_createForm_entry_point(self) -> None:  # noqa: N802 -- entry-point literal
        gs, _ = build_gas_script(_pulm())
        assert "function createForm() {" in gs
        assert "FormApp.create(" in gs

    def test_emits_logger_log_of_published_url(self) -> None:
        gs, _ = build_gas_script(_pulm())
        # The user reads the published URL from the Apps Script execution log.
        assert "form.getPublishedUrl()" in gs
        assert "Logger.log(" in gs

    def test_expertise_question_first(self) -> None:
        gs, _ = build_gas_script(_pulm())
        # Expertise is rendered as an addParagraphTextItem before any
        # addMultipleChoiceItem.
        expertise_pos = gs.index(".addParagraphTextItem()")
        mc_pos = gs.index(".addMultipleChoiceItem()")
        assert expertise_pos < mc_pos

    def test_one_mc_per_item(self) -> None:
        bench = _pulm()
        gs, _ = build_gas_script(bench, include_rationales=False)
        assert gs.count("addMultipleChoiceItem()") == bench.n

    def test_two_TE_per_rationale_item_plus_one_expertise(self) -> None:  # noqa: N802 -- literal
        bench = _pulm()
        gs, _ = build_gas_script(bench, include_rationales=True)
        # 1 expertise + n rationale.
        assert gs.count("addParagraphTextItem()") == 1 + bench.n

    def test_choices_are_default_verdict_strings(self) -> None:
        gs, _ = build_gas_script(_pulm())
        for choice in DEFAULT_VERDICT_CHOICES:
            # JSON encoding escapes em-dash to —; assert on the
            # word-only prefix instead.
            assert choice.split()[0] in gs


class TestRandomizationWarning:
    def test_randomize_on_emits_warning_log_and_comment(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="infereval.survey.google_forms_gas"):
            gs, _ = build_gas_script(_pulm(), randomize_items=True)
        # Logged warning at INFO/WARNING level.
        assert any("randomize_items_ignored" in r.message for r in caplog.records)
        # Comment in the generated source explains the limitation.
        assert "NOTE: --randomize-items was requested" in gs
        assert "FormApp.setShuffleQuestions" in gs

    def test_randomize_off_no_warning(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="infereval.survey.google_forms_gas"):
            gs, _ = build_gas_script(_pulm(), randomize_items=False)
        assert not any("randomize_items_ignored" in r.message for r in caplog.records)
        # No comment block warning about the limitation either.
        assert "NOTE: --randomize-items was requested" not in gs


class TestMapping:
    def test_mapping_includes_item_tag_in_question_title(self) -> None:
        bench = _pulm()
        gs, mapping = build_gas_script(bench, include_rationales=True)
        for row in mapping:
            # The [item:<tag>] prefix is the importer's mapping key.
            assert f"[item:{row['verdict_data_export_tag']}]" in gs

    def test_safe_ids_pass_through_unhashed(self) -> None:
        bench = _pulm()
        _gs, mapping = build_gas_script(bench)
        for row in mapping:
            assert row["was_hashed"] is False
