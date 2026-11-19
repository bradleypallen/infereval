"""Consent page and practice items in the Qualtrics export, and their import skip."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.survey.prolific import completion_url
from infereval.survey.qualtrics_csv import parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.render import render_survey_question
from infereval.survey.session import (
    ConsentSpec,
    PracticeItem,
    PracticeSpec,
    is_session_tag,
    load_consent,
    load_practice,
)

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"
FIXTURE = ROOT / "tests" / "fixtures" / "qualtrics" / "responses_known_good.csv"

CONSENT = ConsentSpec(
    information="About this study.",
    statements=("I am 18 or older.", "I take part voluntarily."),
)
PRACTICE = PracticeSpec(
    intro="Three practice questions.",
    items=(
        PracticeItem("kettle", ("Sam boils a kettle",), "The water is hot"),
        PracticeItem("basil", ("Priya waters the basil", "The basil is artificial"),
                     "The basil will grow"),
    ),
    outro="End of practice.",
)


def _pulm() -> Benchmark:
    return Benchmark.load(PULM_PATH)


def _element(qsf: dict[str, Any], kind: str) -> Any:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == kind)["Payload"]


def _questions(qsf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        el["Payload"]["DataExportTag"]: el["Payload"]
        for el in qsf["SurveyElements"]
        if el["Element"] == "SQ"
    }


def _flow_ids(nodes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        out.append(n["FlowID"])
        out += _flow_ids(n.get("Flow", []))
    return out


def _block_of(qsf: dict[str, Any], qid: str) -> dict[str, Any]:
    return next(
        b for b in _element(qsf, "BL")
        if any(be.get("QuestionID") == qid for be in b["BlockElements"])
    )


class TestSpecs:
    def test_session_tags(self) -> None:
        assert all(is_session_tag(t) for t in
                   ["consent", "consent_statements", "consent_statements_2", "practice_x"])
        assert not any(is_session_tag(t) for t in ["c1", "consents", "expertise", "practicex"])

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"information": " ", "statements": ("a",)},
            {"information": "x", "statements": ()},
            {"information": "x", "statements": ("a", "a")},
            {"information": "x", "statements": ("a",), "agree": "same", "decline": "same"},
        ],
    )
    def test_consent_rejects_bad_specs(self, kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValueError, match="consent"):
            ConsentSpec(**kwargs)

    def test_practice_rejects_bad_specs(self) -> None:
        with pytest.raises(ValueError, match="practice item"):
            PracticeItem("bad id", ("p",), "c")
        with pytest.raises(ValueError, match="premises"):
            PracticeItem("x", (), "c")
        with pytest.raises(ValueError, match="distinct"):
            PracticeSpec(items=(PracticeItem("x", ("p",), "c"),) * 2)

    def test_loaders_round_trip_and_reject_unknown_keys(self, tmp_path: Path) -> None:
        c = tmp_path / "consent.json"
        c.write_text(json.dumps({"information": "i", "statements": ["s1", "s2"]}))
        assert load_consent(c) == ConsentSpec("i", ("s1", "s2"))
        p = tmp_path / "practice.json"
        p.write_text(json.dumps(
            {"items": [{"id": "k", "premises": ["a"], "conclusion": "b"}]}
        ))
        assert load_practice(p) == PracticeSpec(items=(PracticeItem("k", ("a",), "b"),))
        c.write_text(json.dumps({"information": "i", "statements": ["s"], "extra": 1}))
        with pytest.raises(ValueError, match="unknown keys"):
            load_consent(c)


class TestConsent:
    @pytest.mark.parametrize("randomize", [True, False])
    def test_consent_block_first_then_branch_to_end(self, randomize: bool) -> None:
        qsf, _ = build_qsf(_pulm(), randomize_items=randomize, consent=CONSENT)
        qs = _questions(qsf)
        flow = _element(qsf, "FL")["Flow"]
        consent_block = _block_of(qsf, qs["consent"]["QuestionID"])
        assert flow[0]["ID"] == consent_block["ID"]
        assert [be["QuestionID"] for be in consent_block["BlockElements"]] == [
            qs["consent_information"]["QuestionID"],
            qs["consent_statements"]["QuestionID"],
            qs["consent"]["QuestionID"],
        ]
        branch = flow[1]
        assert branch["Type"] == "Branch"
        assert [n["Type"] for n in branch["Flow"]] == ["EndSurvey"]
        # The decliners' ending overrides any survey-level redirect.
        assert branch["Flow"][0]["Options"]["SurveyTermination"] == "DefaultMessage"

    def test_questions_render_spec(self) -> None:
        qs = _questions(build_qsf(_pulm(), consent=CONSENT)[0])
        assert qs["consent_information"]["QuestionType"] == "DB"
        assert qs["consent_information"]["QuestionText"] == CONSENT.information
        st = qs["consent_statements"]
        assert st["Selector"] == "MAVR"
        assert [c["Display"] for c in st["Choices"].values()] == list(CONSENT.statements)
        dec = qs["consent"]
        assert dec["Selector"] == "SAVR"
        assert dec["Validation"]["Settings"]["ForceResponse"] == "ON"
        assert [c["Display"] for c in dec["Choices"].values()] == [CONSENT.agree, CONSENT.decline]

    def test_branch_ends_on_decline_or_any_unticked_statement(self) -> None:
        qsf, _ = build_qsf(_pulm(), consent=CONSENT)
        qs = _questions(qsf)
        dec, st = qs["consent"]["QuestionID"], qs["consent_statements"]["QuestionID"]
        cond = _element(qsf, "FL")["Flow"][1]["BranchLogic"]["0"]
        exprs = [cond[k] for k in sorted((k for k in cond if k != "Type"), key=int)]
        assert [(e["ChoiceLocator"], e["Operator"]) for e in exprs] == [
            (f"q://{dec}/SelectableChoice/2", "Selected"),
            (f"q://{st}/SelectableChoice/1", "NotSelected"),
            (f"q://{st}/SelectableChoice/2", "NotSelected"),
        ]
        assert "Conjuction" not in exprs[0]
        assert all(e["Conjuction"] == "Or" for e in exprs[1:])

    def test_prolific_no_consent_code_redirects_decliners(self) -> None:
        qsf, _ = build_qsf(
            _pulm(), consent=CONSENT,
            prolific_completion_code="DONE1234", prolific_no_consent_code="NOCONS12",
        )
        flow = _element(qsf, "FL")["Flow"]
        assert flow[0]["Type"] == "EmbeddedData"  # Prolific ids captured before consent
        end = flow[2]["Flow"][0]
        assert end["Options"]["SurveyTermination"] == "Redirect"
        assert end["Options"]["EOSRedirectURL"] == completion_url("NOCONS12")
        assert _element(qsf, "SO")["EOSRedirectURL"] == completion_url("DONE1234")

    def test_no_consent_code_requires_consent(self) -> None:
        with pytest.raises(ValueError, match="requires a consent page"):
            build_qsf(_pulm(), prolific_no_consent_code="NOCONS12")

    @pytest.mark.parametrize("randomize", [True, False])
    def test_flow_ids_unique_and_item_flow_unchanged(self, randomize: bool) -> None:
        base, _ = build_qsf(_pulm(), randomize_items=randomize)
        qsf, _ = build_qsf(
            _pulm(), randomize_items=randomize, consent=CONSENT, practice=PRACTICE,
            prolific_completion_code="DONE1234",
        )
        flow, base_flow = _element(qsf, "FL"), _element(base, "FL")
        ids = ["FL_1", *_flow_ids(flow["Flow"])]
        assert len(ids) == len(set(ids))
        assert flow["Properties"]["Count"] == len(ids)
        # ED + consent block + branch + end node come first; the item flow keeps its ids.
        assert _flow_ids(flow["Flow"])[4:] == _flow_ids(base_flow["Flow"])

    def test_reserved_item_tag_refused(self) -> None:
        bench = _pulm()
        data = bench.model_dump(mode="json")
        data["items"][0]["id"] = "practice_c1"
        clash = Benchmark.model_validate(data)
        with pytest.raises(ValueError, match="reserved"):
            build_qsf(clash, practice=PRACTICE)
        build_qsf(clash)  # without session pages the tag is allowed, as before


class TestPractice:
    @pytest.mark.parametrize("header_mode", ["per-question", "instructions"])
    def test_rendered_like_items_and_placed_after_intro(self, header_mode: str) -> None:
        bench = _pulm()
        if header_mode == "instructions" and (
            render_survey_question(bench, bench.items[0]).stem is None
        ):
            pytest.skip("default frame has no survey_stem")
        qsf, mapping = build_qsf(bench, practice=PRACTICE, header_mode=header_mode)
        qs = _questions(qsf)
        item_q = qs[mapping[0]["verdict_data_export_tag"]]
        kettle = qs["practice_kettle"]
        assert kettle["Choices"] == item_q["Choices"]
        assert kettle["Validation"]["Settings"]["ForceResponse"] == "ON"
        # Same header/stem surface; only the premises/conclusion body differs.
        sep = "Premises:"
        assert kettle["QuestionText"].split(sep)[0] == item_q["QuestionText"].split(sep)[0]
        assert "- Sam boils a kettle" in kettle["QuestionText"]
        assert "- Priya waters the basil\n- The basil is artificial" in (
            qs["practice_basil"]["QuestionText"]
        )
        assert [m["item_id"] for m in mapping] == [i.id for i in bench.items]

        intro = _block_of(qsf, qs["expertise"]["QuestionID"])
        order = [be.get("QuestionID") for be in intro["BlockElements"]]
        want = [qs[t]["QuestionID"] for t in
                ("expertise", "practice_intro", "practice_kettle", "practice_basil",
                 "practice_outro")]
        assert [q for q in order if q in want] == want
        # Each practice page is separated by a page break.
        for qid in want[1:]:
            assert intro["BlockElements"][order.index(qid) - 1] == {"Type": "Page Break"}

    def test_practice_outside_randomizer(self) -> None:
        qsf, _ = build_qsf(_pulm(), practice=PRACTICE, randomize_items=True)
        rand = next(n for n in _element(qsf, "FL")["Flow"] if n["Type"] == "BlockRandomizer")
        randomized = {n["ID"] for n in rand["Flow"]}
        qs = _questions(qsf)
        assert _block_of(qsf, qs["practice_kettle"]["QuestionID"])["ID"] not in randomized


class TestImport:
    def _write(self, tmp_path: Path, decline_row: bool) -> Path:
        rows = list(csv.reader(FIXTURE.open(encoding="utf-8")))
        extra = ["consent", "consent_statements", "practice_kettle"]
        rows[0] += extra
        rows[1] += extra
        rows[2] += [json.dumps({"ImportId": k}) for k in extra]
        for row in rows[3:]:
            row += ["I agree to take part", "I am 18 or older.,I take part voluntarily.",
                    "Good — follows"]
        if decline_row:
            blank = ["" for _ in rows[0]]
            blank[rows[0].index("ResponseId")] = "R_declined"
            blank[rows[0].index("consent")] = "I do not wish to take part"
            rows.append(blank)
        path = tmp_path / "with_session.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)
        return path

    def test_session_columns_not_parsed_as_verdicts(self, tmp_path: Path) -> None:
        got = parse_qualtrics_csv(self._write(tmp_path, decline_row=False))
        plain = parse_qualtrics_csv(FIXTURE)
        assert [r.verdicts for r in got] == [r.verdicts for r in plain]

    def test_decliners_are_dropped(self, tmp_path: Path) -> None:
        got = parse_qualtrics_csv(self._write(tmp_path, decline_row=True))
        assert "R_declined" not in {r.response_id for r in got}
        assert len(got) == len(parse_qualtrics_csv(FIXTURE))


class TestCli:
    def test_export_with_consent_and_practice(self, tmp_path: Path) -> None:
        c, p, out = tmp_path / "c.json", tmp_path / "p.json", tmp_path / "s.qsf"
        c.write_text(json.dumps({"information": "i", "statements": ["s1"]}))
        p.write_text(json.dumps({"items": [{"id": "k", "premises": ["a"], "conclusion": "b"}]}))
        result = CliRunner().invoke(cli, [
            "survey", "export", str(PULM_PATH), "-o", str(out),
            "--consent", str(c), "--practice", str(p),
            "--prolific-completion-code", "DONE1234", "--prolific-no-consent-code", "NOCONS12",
        ])
        assert result.exit_code == 0, result.output
        qs = _questions(json.loads(out.read_text()))
        assert {"consent", "consent_statements", "practice_k"} <= set(qs)
        assert "Consent: first page, 1 statements" in result.output

    def test_bad_spec_exits_2(self, tmp_path: Path) -> None:
        c, out = tmp_path / "c.json", tmp_path / "s.qsf"
        c.write_text(json.dumps({"information": "", "statements": ["s1"]}))
        result = CliRunner().invoke(
            cli, ["survey", "export", str(PULM_PATH), "-o", str(out), "--consent", str(c)]
        )
        assert result.exit_code == 2
        assert not out.exists()

    def test_no_consent_code_needs_consent(self, tmp_path: Path) -> None:
        result = CliRunner().invoke(cli, [
            "survey", "export", str(PULM_PATH), "-o", str(tmp_path / "s.qsf"),
            "--prolific-no-consent-code", "NOCONS12",
        ])
        assert result.exit_code != 0
        assert "requires --consent" in result.output

    def test_refused_for_other_platforms(self, tmp_path: Path) -> None:
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"items": [{"id": "k", "premises": ["a"], "conclusion": "b"}]}))
        result = CliRunner().invoke(cli, [
            "survey", "export", str(PULM_PATH), "-o", str(tmp_path / "f.gs"),
            "--platform", "google_forms", "--practice", str(p),
        ])
        assert result.exit_code != 0
        assert "qualtrics only" in result.output
