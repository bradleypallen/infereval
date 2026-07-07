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


# ---- Randomization (BlockRandomizer flow) ---------------------------------


def _flow(qsf: dict) -> dict:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == "FL")["Payload"]


def _blocks(qsf: dict) -> list[dict]:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == "BL")["Payload"]


class TestRandomization:
    def test_randomize_on_uses_block_randomizer_over_item_units(self) -> None:
        """Randomization is over item blocks (verdict + rationale travel
        together), never over individual questions."""
        bench = _pulm()
        qsf, _ = build_qsf(bench, randomize_items=True, include_rationales=True)
        flow = _flow(qsf)
        randomizer = next(n for n in flow["Flow"] if n.get("Type") == "BlockRandomizer")
        assert randomizer["SubSet"] == bench.n  # all items shown, random order
        assert len(randomizer["Flow"]) == bench.n
        # Each randomized block holds exactly one item's verdict + rationale.
        randomized_ids = {n["ID"] for n in randomizer["Flow"]}
        item_blocks = [b for b in _blocks(qsf) if b["ID"] in randomized_ids]
        assert len(item_blocks) == bench.n
        for block in item_blocks:
            qids = [be["QuestionID"] for be in block["BlockElements"]]
            assert len(qids) == 2  # verdict + its rationale, inseparable
        # Expertise block is the flow's first node, outside the randomizer.
        first = flow["Flow"][0]
        assert first["Type"] == "Block"
        intro = next(b for b in _blocks(qsf) if b["ID"] == first["ID"])
        assert [be["QuestionID"] for be in intro["BlockElements"]] == ["QID1"]

    def test_randomize_off_single_block_flow(self) -> None:
        qsf, _ = build_qsf(_stop_sign(), randomize_items=False)
        flow = _flow(qsf)
        assert [n["Type"] for n in flow["Flow"]] == ["Block"]
        assert flow["Properties"]["Count"] == 2  # Root + one block node
        # All questions live in the one Default block, page-broken.
        default = next(b for b in _blocks(qsf) if b["Type"] == "Default")
        assert {"Type": "Page Break"} in default["BlockElements"]


# ---- Instructions header mode (DESIGN §6.1) --------------------------------


class TestInstructionsHeaderMode:
    """header_mode='instructions': the frame's full header renders once as
    a Descriptive Text page; each item question carries only the item body
    plus the frame's closing question line (survey_stem)."""

    def _build(self, **kwargs):
        from infereval.templates import DEFEASIBLE_COHERENCE_FRAME

        return build_qsf(
            _pulm(),
            question_form="coherence",
            coherence_frame=DEFEASIBLE_COHERENCE_FRAME,
            header_mode="instructions",
            **kwargs,
        )

    def test_header_renders_once_as_descriptive_text(self) -> None:
        from infereval.templates import DEFEASIBLE_COHERENCE_FRAME

        qsf, _ = self._build()
        dbs = [
            el
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ" and el["Payload"]["QuestionType"] == "DB"
        ]
        assert len(dbs) == 1
        assert dbs[0]["Payload"]["QuestionText"] == DEFEASIBLE_COHERENCE_FRAME.survey_header

    def test_instructions_page_precedes_expertise_outside_randomization(self) -> None:
        qsf, _ = self._build(randomize_items=True)
        flow = _flow(qsf)
        first = flow["Flow"][0]
        assert first["Type"] == "Block"
        intro = next(b for b in _blocks(qsf) if b["ID"] == first["ID"])
        kinds = [(e.get("Type"), e.get("QuestionID")) for e in intro["BlockElements"]]
        instructions_qid = kinds[0][1]
        qsf_sq = {
            el["PrimaryAttribute"]: el["Payload"]
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ"
        }
        assert qsf_sq[instructions_qid]["QuestionType"] == "DB"
        assert kinds[1] == ("Page Break", None)
        assert qsf_sq[kinds[2][1]]["DataExportTag"] == "expertise"

    def test_item_questions_carry_body_plus_stem_not_header(self) -> None:
        from infereval.templates import DEFEASIBLE_COHERENCE_FRAME

        qsf, _ = self._build()
        header = DEFEASIBLE_COHERENCE_FRAME.survey_header
        stem = DEFEASIBLE_COHERENCE_FRAME.survey_stem
        mcs = [
            el["Payload"]
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ" and el["Payload"]["QuestionType"] == "MC"
        ]
        assert len(mcs) == _pulm().n
        for p in mcs:
            assert header not in p["QuestionText"]
            assert p["QuestionText"].endswith(stem)

    def test_mapping_records_header_mode(self) -> None:
        _qsf, mapping = self._build()
        assert all(row["header_mode"] == "instructions" for row in mapping)
        _qsf2, mapping2 = build_qsf(_pulm())
        assert all(row["header_mode"] == "per-question" for row in mapping2)

    def test_default_mode_has_no_descriptive_text_element(self) -> None:
        qsf, _ = build_qsf(_pulm())
        assert not any(
            el.get("Element") == "SQ" and el["Payload"]["QuestionType"] == "DB"
            for el in qsf["SurveyElements"]
        )

    def test_stemless_frame_fails_loudly(self) -> None:
        from infereval.templates import CoherenceFrame

        stemless = CoherenceFrame(
            id="stemless-test-v1",
            system="sys",
            survey_header="A header without a declared stem?",
        )
        import pytest

        with pytest.raises(ValueError, match="survey_stem"):
            build_qsf(
                _pulm(),
                question_form="coherence",
                coherence_frame=stemless,
                header_mode="instructions",
            )

    def test_unknown_header_mode_rejected(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="header_mode"):
            build_qsf(_pulm(), header_mode="banner")

    def test_norand_single_block_starts_with_instructions(self) -> None:
        qsf, _ = self._build(randomize_items=False)
        default = next(b for b in _blocks(qsf) if b["Type"] == "Default")
        first = default["BlockElements"][0]
        qsf_sq = {
            el["PrimaryAttribute"]: el["Payload"]
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ"
        }
        assert qsf_sq[first["QuestionID"]]["QuestionType"] == "DB"

    def test_support_form_instructions_mode(self) -> None:
        """The default-v1 support header is a single question line and
        serves as its own stem."""
        from infereval.survey.render import DEFAULT_QUESTION_HEADER

        qsf, mapping = build_qsf(
            _pulm(), question_form="support", header_mode="instructions"
        )
        dbs = [
            el["Payload"]
            for el in qsf["SurveyElements"]
            if el.get("Element") == "SQ" and el["Payload"]["QuestionType"] == "DB"
        ]
        assert len(dbs) == 1
        assert dbs[0]["QuestionText"] == DEFAULT_QUESTION_HEADER
        assert all(row["header_mode"] == "instructions" for row in mapping)


# ---- Canonical import structure -------------------------------------------


class TestCanonicalImportStructure:
    """The structural contract a live Qualtrics import enforces — the
    original exporter emitted only BL + SQ elements with free-form ids
    and was rejected by the importer ("Something went wrong and the
    project wasn't created")."""

    def test_required_element_census(self) -> None:
        qsf, _ = build_qsf(_pulm())
        census: dict[str, int] = {}
        for el in qsf["SurveyElements"]:
            census[el["Element"]] = census.get(el["Element"], 0) + 1
        for required in ("BL", "FL", "SO", "SCO", "PROJ", "STAT", "QC", "RS"):
            assert census.get(required) == 1, (required, census)

    def test_id_grammar(self) -> None:
        import re

        qsf, _ = build_qsf(_pulm())
        entry = qsf["SurveyEntry"]
        assert re.fullmatch(r"SV_[a-zA-Z0-9]{15}", entry["SurveyID"])
        assert re.fullmatch(r"UR_[a-zA-Z0-9]{15}", entry["SurveyOwnerID"])
        assert re.fullmatch(r"RS_[a-zA-Z0-9]{15}", entry["SurveyActiveResponseSet"])
        for block in _blocks(qsf):
            assert re.fullmatch(r"BL_[a-zA-Z0-9]{15}", block["ID"])

    def test_flow_references_existing_blocks(self) -> None:
        qsf, _ = build_qsf(_pulm(), randomize_items=True)
        block_ids = {b["ID"] for b in _blocks(qsf)}

        def refs(nodes: list[dict]) -> set[str]:
            out: set[str] = set()
            for n in nodes:
                if "ID" in n:
                    out.add(n["ID"])
                out |= refs(n.get("Flow", []))
            return out

        assert refs(_flow(qsf)["Flow"]) <= block_ids

    def test_question_count_element_matches_sq_census(self) -> None:
        bench = _pulm()
        qsf, _ = build_qsf(bench, include_rationales=True)
        qc = next(el for el in qsf["SurveyElements"] if el["Element"] == "QC")
        assert qc["SecondaryAttribute"] == str(1 + 2 * bench.n)

    def test_trash_block_present(self) -> None:
        qsf, _ = build_qsf(_stop_sign())
        assert any(b["Type"] == "Trash" for b in _blocks(qsf))

    def test_deterministic_output(self) -> None:
        """Same benchmark → byte-identical artifact (golden-test property)."""
        import json

        a, _ = build_qsf(_pulm())
        b, _ = build_qsf(_pulm())
        assert json.dumps(a) == json.dumps(b)

    def test_distinct_benchmarks_get_distinct_survey_ids(self) -> None:
        a, _ = build_qsf(_pulm())
        b, _ = build_qsf(_stop_sign())
        assert a["SurveyEntry"]["SurveyID"] != b["SurveyEntry"]["SurveyID"]


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
