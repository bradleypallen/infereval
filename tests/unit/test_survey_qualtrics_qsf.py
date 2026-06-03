"""Tests for ``infereval.survey.qualtrics_qsf.build_qsf``."""

from __future__ import annotations

from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import DEFAULT_VERDICT_CHOICES, sanitize_export_tag

STOP_SIGN_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "stop_sign" / "benchmark.json"
)
PULM_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "pulmonary_edema" / "benchmark.json"
)


def _stop_sign() -> Benchmark:
    return Benchmark.load(STOP_SIGN_PATH)


def _pulm() -> Benchmark:
    return Benchmark.load(PULM_PATH)


# ---- Structural shape -----------------------------------------------------


class TestQsfStructure:
    def test_has_survey_entry_and_elements(self) -> None:
        qsf, _mapping = build_qsf(_stop_sign())
        assert "SurveyEntry" in qsf
        assert "SurveyElements" in qsf
        # SurveyEntry boilerplate.
        assert qsf["SurveyEntry"]["SurveyLanguage"] == "EN"
        assert isinstance(qsf["SurveyElements"], list)

    def test_default_title_uses_benchmark_id(self) -> None:
        bench = _stop_sign()
        qsf, _ = build_qsf(bench)
        assert bench.id in qsf["SurveyEntry"]["SurveyName"]

    def test_explicit_title_overrides_default(self) -> None:
        qsf, _ = build_qsf(_stop_sign(), title="Custom title")
        assert qsf["SurveyEntry"]["SurveyName"] == "Custom title"

    def test_each_mc_question_has_three_choices_force_response(self) -> None:
        qsf, _ = build_qsf(_pulm())
        mc_payloads = [
            el["Payload"]
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ" and el["Payload"].get("QuestionType") == "MC"
        ]
        assert len(mc_payloads) == _pulm().n  # one MC per item
        for p in mc_payloads:
            assert p["Selector"] == "SAVR"
            assert p["Validation"]["Settings"]["ForceResponse"] == "ON"
            assert len(p["Choices"]) == 3
            displays = [c["Display"] for c in p["Choices"].values()]
            assert displays == list(DEFAULT_VERDICT_CHOICES)


# ---- Item-count expectations ---------------------------------------------


class TestItemCounts:
    def test_with_rationales_question_count(self) -> None:
        """For an n-item benchmark with rationales on: 1 expertise + 2n
        question elements (verdict + rationale per item)."""
        bench = _pulm()
        qsf, _ = build_qsf(bench, include_rationales=True)
        sqs = [el for el in qsf["SurveyElements"] if el.get("Element") == "SQ"]
        assert len(sqs) == 1 + 2 * bench.n

    def test_without_rationales_question_count(self) -> None:
        bench = _pulm()
        qsf, _ = build_qsf(bench, include_rationales=False)
        sqs = [el for el in qsf["SurveyElements"] if el.get("Element") == "SQ"]
        assert len(sqs) == 1 + bench.n


# ---- Sanitization + mapping sidecar --------------------------------------


class TestMappingSidecar:
    def test_mapping_has_one_row_per_item(self) -> None:
        bench = _pulm()
        _qsf, mapping = build_qsf(bench)
        assert len(mapping) == bench.n
        for row, item in zip(mapping, bench.items, strict=True):
            assert row["item_id"] == item.id

    def test_safe_ids_pass_through_unhashed(self) -> None:
        """Pulmonology uses simple ids like 'c1' — pass through unchanged."""
        _qsf, mapping = build_qsf(_pulm())
        for row in mapping:
            assert row["was_hashed"] is False
            assert row["verdict_data_export_tag"] == row["item_id"]

    def test_hyphenated_ids_get_hashed(self) -> None:
        """Stop-sign uses ids like 'row-0' (hyphens are not safe per the
        sanitize policy — see docstring on ``sanitize_export_tag``).
        These must be hashed and recorded as such."""
        _qsf, mapping = build_qsf(_stop_sign())
        for row in mapping:
            assert row["was_hashed"] is True
            assert row["verdict_data_export_tag"].startswith("item_")

    def test_rationale_tag_suffix(self) -> None:
        _qsf, mapping = build_qsf(_stop_sign(), include_rationales=True)
        for row in mapping:
            assert row["rationale_data_export_tag"] == f"{row['verdict_data_export_tag']}_rationale"

    def test_no_rationale_tag_when_disabled(self) -> None:
        _qsf, mapping = build_qsf(_stop_sign(), include_rationales=False)
        for row in mapping:
            assert row["rationale_data_export_tag"] is None


# ---- Randomization payload ----------------------------------------------


class TestRandomization:
    def test_randomize_on_emits_randomization_payload(self) -> None:
        qsf, _ = build_qsf(_pulm(), randomize_items=True, include_rationales=True)
        block_el = next(el for el in qsf["SurveyElements"] if el["Element"] == "BL")
        block = block_el["Payload"][0]
        assert "Options" in block
        rand = block["Options"]["Randomization"]
        # All item question QIDs are in RandomizeAll (verdicts + rationales).
        bench = _pulm()
        assert len(rand["RandomizeAll"]) == 2 * bench.n
        # Expertise QID1 is NOT in the randomization list.
        assert "QID1" not in rand["RandomizeAll"]

    def test_randomize_off_omits_payload(self) -> None:
        qsf, _ = build_qsf(_stop_sign(), randomize_items=False)
        block_el = next(el for el in qsf["SurveyElements"] if el["Element"] == "BL")
        block = block_el["Payload"][0]
        # No randomization options means no shuffle.
        assert "Options" not in block or "Randomization" not in block.get("Options", {})


# ---- Expertise question ------------------------------------------------


def test_first_sq_element_is_expertise_text_entry() -> None:
    qsf, _ = build_qsf(_stop_sign())
    sqs = [el for el in qsf["SurveyElements"] if el.get("Element") == "SQ"]
    assert sqs[0]["Payload"]["QuestionType"] == "TE"
    assert sqs[0]["Payload"]["DataExportTag"] == "expertise"
    # Expertise is NOT force-response (recruiter may want anonymous responses).
    assert sqs[0]["Payload"]["Validation"]["Settings"]["ForceResponse"] == "OFF"


def test_custom_expertise_prompt() -> None:
    qsf, _ = build_qsf(_stop_sign(), expertise_prompt="What's your specialty?")
    sqs = [el for el in qsf["SurveyElements"] if el.get("Element") == "SQ"]
    assert sqs[0]["Payload"]["QuestionText"] == "What's your specialty?"


# ---- Hashed-id round trip (via a synthetic benchmark with unsafe ids) ----


def test_unsafe_item_id_gets_hashed_in_mapping() -> None:
    """When item ids contain forbidden characters, the DataExportTag is
    hashed and the mapping sidecar records it."""
    from infereval.benchmark import BearerModel, BenchmarkItem
    from infereval.types import Verdict

    bench = Benchmark(
        id="hash-test",
        bearers={"p": BearerModel(expression="p"), "c": BearerModel(expression="c")},
        analysts=[{"id": "a"}],
        items=[
            BenchmarkItem(
                id="item/with slash",  # unsafe — must be hashed
                premises=["p"],
                conclusions=["c"],
                analyst_verdicts=[Verdict.GOOD],
            )
        ],
    )
    _qsf, mapping = build_qsf(bench)
    expected_tag, expected_hashed = sanitize_export_tag("item/with slash")
    assert mapping[0]["was_hashed"] is True
    assert expected_hashed is True
    assert mapping[0]["verdict_data_export_tag"] == expected_tag
