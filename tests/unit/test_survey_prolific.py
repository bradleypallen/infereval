"""Prolific hand-off: Embedded Data capture, completion redirect, import skip."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.survey.prolific import PROLIFIC_FIELDS, completion_url
from infereval.survey.qualtrics_csv import parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"
FIXTURE = ROOT / "tests" / "fixtures" / "qualtrics" / "responses_known_good.csv"
CODE = "C1A2B3C4"


def _pulm() -> Benchmark:
    return Benchmark.load(PULM_PATH)


def _element(qsf: dict, kind: str) -> dict:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == kind)["Payload"]


def _flow_ids(nodes: list[dict]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        out.append(n["FlowID"])
        out += _flow_ids(n.get("Flow", []))
    return out


class TestCompletionUrl:
    def test_builds_prolific_url(self) -> None:
        assert completion_url(CODE) == (
            "https://app.prolific.com/submissions/complete?cc=C1A2B3C4"
        )

    @pytest.mark.parametrize("bad", ["", "abc", "C1A2 B3C4", "https://x.y/?cc=1", "x" * 33])
    def test_rejects_malformed_codes(self, bad: str) -> None:
        with pytest.raises(ValueError, match="completion code"):
            completion_url(bad)


class TestQsfHandoff:
    @pytest.mark.parametrize("randomize", [True, False])
    def test_embedded_data_node_is_first_and_captures_prolific_fields(
        self, randomize: bool
    ) -> None:
        qsf, _ = build_qsf(_pulm(), randomize_items=randomize, prolific_completion_code=CODE)
        flow = _element(qsf, "FL")
        first = flow["Flow"][0]
        assert first["Type"] == "EmbeddedData"
        assert [f["Field"] for f in first["EmbeddedData"]] == list(PROLIFIC_FIELDS)
        assert all(f["Type"] == "Recipient" for f in first["EmbeddedData"])

    @pytest.mark.parametrize("randomize", [True, False])
    def test_flow_ids_unique_and_count_includes_new_node(self, randomize: bool) -> None:
        base, _ = build_qsf(_pulm(), randomize_items=randomize)
        qsf, _ = build_qsf(_pulm(), randomize_items=randomize, prolific_completion_code=CODE)
        flow, base_flow = _element(qsf, "FL"), _element(base, "FL")
        ids = ["FL_1", *_flow_ids(flow["Flow"])]
        assert len(ids) == len(set(ids))
        assert flow["Properties"]["Count"] == base_flow["Properties"]["Count"] + 1
        # Existing nodes keep their ids; only the new node is added.
        assert _flow_ids(flow["Flow"])[1:] == _flow_ids(base_flow["Flow"])

    def test_survey_ends_with_redirect_to_prolific(self) -> None:
        qsf, _ = build_qsf(_pulm(), prolific_completion_code=CODE)
        options = _element(qsf, "SO")
        assert options["SurveyTermination"] == "Redirect"
        assert options["EOSRedirectURL"] == completion_url(CODE)

    def test_default_export_unchanged(self) -> None:
        """No code: no Embedded Data, default termination, same bytes as before."""
        qsf, _ = build_qsf(_pulm())
        assert all(n["Type"] != "EmbeddedData" for n in _element(qsf, "FL")["Flow"])
        assert _element(qsf, "SO")["SurveyTermination"] == "DefaultMessage"
        assert "EOSRedirectURL" not in _element(qsf, "SO")
        assert json.dumps(qsf) == json.dumps(build_qsf(_pulm())[0])

    def test_invalid_code_raises(self) -> None:
        with pytest.raises(ValueError, match="completion code"):
            build_qsf(_pulm(), prolific_completion_code="not a code")


class TestImportSkipsProlificColumns:
    def test_prolific_columns_not_parsed_as_verdicts(self, tmp_path: Path) -> None:
        rows = list(csv.reader(FIXTURE.open(encoding="utf-8")))
        extra = {"PROLIFIC_PID": "5f1a2b3c4d5e6f7a8b9c0d1e", "STUDY_ID": "S1", "SESSION_ID": "X9"}
        rows[0] += list(extra)
        rows[1] += list(extra)
        rows[2] += [json.dumps({"ImportId": k}) for k in extra]
        for row in rows[3:]:
            row += list(extra.values())
        path = tmp_path / "with_prolific.csv"
        with path.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)

        with_ids = parse_qualtrics_csv(path)
        plain = parse_qualtrics_csv(FIXTURE)
        assert [r.verdicts for r in with_ids] == [r.verdicts for r in plain]
        for r in with_ids:
            assert not set(r.verdicts) & set(PROLIFIC_FIELDS)
            assert r.response_id.startswith("R_")  # analyst id stays the ResponseId


class TestCli:
    def test_export_with_code_writes_handoff(self, tmp_path: Path) -> None:
        out = tmp_path / "recruit.qsf"
        result = CliRunner().invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out),
             "--prolific-completion-code", CODE],
        )
        assert result.exit_code == 0, result.output
        qsf = json.loads(out.read_text())
        assert _element(qsf, "FL")["Flow"][0]["Type"] == "EmbeddedData"
        assert "PROLIFIC_PID={{%PROLIFIC_PID%}}" in result.output

    def test_bad_code_exits_2_without_writing(self, tmp_path: Path) -> None:
        out = tmp_path / "recruit.qsf"
        result = CliRunner().invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out),
             "--prolific-completion-code", "bad code"],
        )
        assert result.exit_code == 2
        assert "completion code" in result.output
        assert not out.exists()

    def test_refused_for_other_platforms(self, tmp_path: Path) -> None:
        out = tmp_path / "form.gs"
        result = CliRunner().invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out),
             "--platform", "google_forms", "--prolific-completion-code", CODE],
        )
        assert result.exit_code != 0
        assert "qualtrics only" in result.output
        assert not out.exists()
