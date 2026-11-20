"""Attention checks and repeated items: export, import and the quality report."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.prompts import ConfidenceScale, resolve_verification_prompt
from infereval.survey.quality import quality_report
from infereval.survey.qualtrics_csv import parse_qualtrics_csv
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.session import (
    AttentionCheck,
    QualitySpec,
    is_session_tag,
    load_quality,
)

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

VERDICTS = ["Good", "Bad", "Can't tell"]
LABELS = ["1 Not at all", "2 Slightly", "3 Fairly", "4 Very"]


def _bench_dict() -> dict[str, Any]:
    data = json.loads(PULM_PATH.read_text())
    data["verification_prompt"] = {
        "id": "test-v1",
        "template": "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
        "survey_header": "Instructions.\n\nDoes it follow?",
        "survey_stem": "Does it follow?",
        "survey_choices": VERDICTS,
        "survey_confidence": {"prompt": "How confident?", "labels": LABELS},
    }
    return data


def _bench() -> Benchmark:
    return Benchmark.model_validate(_bench_dict())


def _spec(bench: Benchmark) -> QualitySpec:
    return QualitySpec(
        attention_checks=(
            AttentionCheck("ac1", "Attention check: please choose Bad.", "Bad"),
            AttentionCheck("ac2", "Attention check: please choose Good.", "Good"),
        ),
        repeats=(bench.items[1].id, bench.items[3].id),
    )


def _questions(qsf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        el["Payload"]["DataExportTag"]: el["Payload"]
        for el in qsf["SurveyElements"]
        if el["Element"] == "SQ"
    }


def _blocks(qsf: dict[str, Any]) -> list[dict[str, Any]]:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == "BL")["Payload"]


def _flow(qsf: dict[str, Any]) -> list[dict[str, Any]]:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == "FL")["Payload"]["Flow"]


def _block_with(qsf: dict[str, Any], qid: str) -> dict[str, Any]:
    return next(
        b for b in _blocks(qsf)
        if any(be.get("QuestionID") == qid for be in b.get("BlockElements", []))
    )


def _flow_ids(nodes: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for n in nodes:
        out.append(n["FlowID"])
        out += _flow_ids(n.get("Flow", []))
    return out


class TestSpec:
    def test_load(self, tmp_path: Path) -> None:
        p = tmp_path / "q.json"
        p.write_text(json.dumps({
            "attention_checks": [{"id": "ac1", "text": "Choose Bad.", "answer": "Bad"}],
            "repeats": ["a", "b"],
        }))
        spec = load_quality(p)
        assert spec.attention_checks[0].tag == "check_ac1"
        assert spec.repeats == ("a", "b")

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {"repeats": ["a", "a"]},
            {"attention_checks": [{"id": "x", "text": "t", "answer": "Bad"}] * 2},
            {"attention_checks": [{"id": "bad id", "text": "t", "answer": "Bad"}]},
            {"attention_checks": [{"id": "x", "text": "", "answer": "Bad"}]},
            {"repeats": ["a"], "extra": 1},
        ],
    )
    def test_invalid_rejected(self, tmp_path: Path, data: dict[str, Any]) -> None:
        p = tmp_path / "q.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ValueError):
            load_quality(p)

    def test_reserved_prefixes(self) -> None:
        assert is_session_tag("check_ac1") and is_session_tag("repeat_item_1")


class TestExport:
    def test_checks_randomized_with_items_repeats_after(self) -> None:
        bench = _bench()
        spec = _spec(bench)
        qsf, mapping = build_qsf(bench, header_mode="instructions", quality=spec)
        qs = _questions(qsf)
        flow = _flow(qsf)
        main, repeats = [n for n in flow if n["Type"] == "BlockRandomizer"]
        block_of = {b["ID"]: b for b in _blocks(qsf)}

        def tags(node: dict[str, Any]) -> set[str]:
            q_by_id = {q["QuestionID"]: t for t, q in qs.items()}
            return {
                q_by_id[be["QuestionID"]]
                for n in node["Flow"]
                for be in block_of[n["ID"]]["BlockElements"]
                if "QuestionID" in be
            }

        assert main["SubSet"] == len(bench.items) + 2
        assert {"check_ac1", "check_ac2"} <= tags(main)
        assert repeats["SubSet"] == 2
        assert flow.index(repeats) == flow.index(main) + 1
        rep = {t for t in tags(repeats) if not t.endswith(("_confidence", "_rationale"))}
        assert rep == {f"repeat_{mapping[1]['verdict_data_export_tag']}",
                       f"repeat_{mapping[3]['verdict_data_export_tag']}"}
        assert len(set(_flow_ids(flow))) == len(_flow_ids(flow))
        # Not in the mapping: it stays one row per benchmark item.
        assert [m["item_id"] for m in mapping] == [i.id for i in bench.items]

    def test_pages_look_like_items(self) -> None:
        bench = _bench()
        qsf, mapping = build_qsf(bench, header_mode="instructions", quality=_spec(bench))
        qs = _questions(qsf)
        tag = mapping[1]["verdict_data_export_tag"]
        assert qs[f"repeat_{tag}"]["QuestionText"] == qs[tag]["QuestionText"]
        assert qs[f"repeat_{tag}"]["Choices"] == qs[tag]["Choices"]
        assert qs["check_ac1"]["QuestionText"] == "Attention check: please choose Bad."
        assert qs["check_ac1"]["Choices"] == qs[tag]["Choices"]
        for unit in ("check_ac1", f"repeat_{tag}"):
            ids = [be.get("QuestionID")
                   for be in _block_with(qsf, qs[unit]["QuestionID"])["BlockElements"]]
            assert ids == [qs[unit]["QuestionID"], qs[f"{unit}_confidence"]["QuestionID"],
                           qs[f"{unit}_rationale"]["QuestionID"]]

    def test_without_randomization(self) -> None:
        bench = _bench()
        qsf, mapping = build_qsf(
            bench, header_mode="instructions", quality=_spec(bench), randomize_items=False,
            include_rationales=False,
        )
        qs = _questions(qsf)
        q_by_id = {q["QuestionID"]: t for t, q in qs.items()}
        block = _block_with(qsf, qs[mapping[0]["verdict_data_export_tag"]]["QuestionID"])
        order = [q_by_id[be["QuestionID"]] for be in block["BlockElements"]
                 if "QuestionID" in be and not q_by_id[be["QuestionID"]].endswith("_confidence")]
        verdict_order = [t for t in order if t not in ("expertise", "instructions")]
        n = len(bench.items)
        positions = [verdict_order.index("check_ac1"), verdict_order.index("check_ac2")]
        assert 0 < positions[0] < positions[1] < n + 1
        assert verdict_order[-2:] == [f"repeat_{mapping[1]['verdict_data_export_tag']}",
                                      f"repeat_{mapping[3]['verdict_data_export_tag']}"]

    def test_unchanged_without_spec(self) -> None:
        bench = _bench()
        assert build_qsf(bench, quality=None) == build_qsf(bench)

    def test_bad_answer_and_unknown_repeat_rejected(self) -> None:
        bench = _bench()
        with pytest.raises(ValueError, match="not one of the answer labels"):
            build_qsf(bench, quality=QualitySpec(
                attention_checks=(AttentionCheck("ac1", "Choose Maybe.", "Maybe"),)))
        with pytest.raises(ValueError, match="not in the benchmark"):
            build_qsf(bench, quality=QualitySpec(repeats=("no_such_item",)))

    def test_reserved_item_tag_refused(self) -> None:
        data = _bench_dict()
        data["items"][0]["id"] = "check_x"
        with pytest.raises(ValueError, match="reserved"):
            build_qsf(Benchmark.model_validate(data), quality=QualitySpec(repeats=("check_x",)))


def _csv(tmp_path: Path, bench: Benchmark, respondents: list[dict[str, Any]]) -> Path:
    """Qualtrics rows; each respondent dict gives verdict/confidence per item index,
    repeat answers, check answers and duration."""
    _, mapping = build_qsf(bench, header_mode="instructions", include_rationales=False)
    tags = [m["verdict_data_export_tag"] for m in mapping]
    header = ["ResponseId", "Finished", "Duration (in seconds)", "expertise"]
    for t in tags:
        header += [t, f"{t}_confidence"]
    header += ["check_ac1", "check_ac1_confidence", "check_ac2", "check_ac2_confidence"]
    for i in (1, 3):
        header += [f"repeat_{tags[i]}", f"repeat_{tags[i]}_confidence"]
    rows = []
    for n, r in enumerate(respondents):
        cells = [f"R_{n}", "True", str(r["duration"]), ""]
        for i in range(len(tags)):
            cells += [VERDICTS[i % 3], LABELS[i % 4]]
        cells += [r["ac1"], LABELS[0], r["ac2"], LABELS[0]]
        for i in (1, 3):
            cells += [r["repeat"].get(i, VERDICTS[i % 3]), LABELS[3]]
        rows.append(cells)
    path = tmp_path / "responses.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerows([header, header, ["{}"] * len(header), *rows])
    return path


RESPONDENTS = [
    {"duration": 1800, "ac1": "Bad", "ac2": "Good", "repeat": {}},
    {"duration": 300, "ac1": "Good", "ac2": "Good", "repeat": {1: "Good"}},
]


class TestImport:
    def test_parsed_apart_from_verdicts(self, tmp_path: Path) -> None:
        bench = _bench()
        resp = parse_qualtrics_csv(
            _csv(tmp_path, bench, RESPONDENTS), choices=tuple(VERDICTS),
            confidence=ConfidenceScale("How confident?", tuple(LABELS)),
        )
        r0 = resp[0]
        assert r0.duration_seconds == 1800.0
        assert r0.check_answers == {"ac1": "Bad", "ac2": "Good"}
        assert len(r0.verdicts) == len(bench.items)
        assert not any(is_session_tag(t) for t in r0.verdicts)

    def test_report(self, tmp_path: Path) -> None:
        bench = _bench()
        scale = resolve_verification_prompt(bench.verification_prompt).survey_confidence
        resp = parse_qualtrics_csv(
            _csv(tmp_path, bench, RESPONDENTS), choices=tuple(VERDICTS), confidence=scale
        )
        report = quality_report(bench, resp, _spec(bench))
        a, b = report["respondents"]
        assert (a["attention_passed"], a["attention_total"]) == (2, 2)
        assert (b["attention_passed"], b["attention_total"]) == (1, 2)
        assert b["attention"]["ac1"] == {"answer": "Good", "expected": "Bad", "passed": False}
        assert (a["repeats_same"], a["repeats_answered"]) == (2, 2)
        # Item 1's first verdict is Bad (VERDICTS[1]); its repeat is Good.
        rep1 = b["repeats"][bench.items[1].id]
        assert rep1 == {"first": "bad", "second": "good", "first_confidence": 2,
                        "second_confidence": 4, "same": False}
        assert (b["repeats_same"], b["repeats_answered"]) == (1, 2)
        assert report["summary"] == {
            "respondents": 2,
            "attention_checks": ["ac1", "ac2"],
            "repeats": [bench.items[1].id, bench.items[3].id],
            "failed_any_attention_check": 1,
            "repeat_agreement": 0.75,
            "median_duration_seconds": 1050.0,
        }

    def test_cli_report_and_exclusion(self, tmp_path: Path) -> None:
        bench = _bench()
        bench_path, spec_path = tmp_path / "bench.json", tmp_path / "quality.json"
        bench_path.write_text(bench.model_dump_json())
        spec = _spec(bench)
        spec_path.write_text(json.dumps({
            "attention_checks": [
                {"id": c.id, "text": c.text, "answer": c.answer} for c in spec.attention_checks
            ],
            "repeats": list(spec.repeats),
        }))
        out = tmp_path / "merged.json"
        result = CliRunner().invoke(cli, [
            "survey", "import", str(bench_path), "-r", str(_csv(tmp_path, bench, RESPONDENTS)),
            "-o", str(out), "--quality-checks", str(spec_path), "--exclude-respondent", "R_1",
        ])
        assert result.exit_code == 0, result.output
        assert "1 failed an attention check; repeat agreement 0.75" in result.output
        report = json.loads((tmp_path / "merged.quality.json").read_text())
        assert [r["response_id"] for r in report["respondents"]] == ["R_0", "R_1"]
        merged = Benchmark.load(out)
        assert [a.id for a in merged.analysts][-1] == "clinician-R_0"
        assert len(merged.analysts) == len(bench.analysts) + 1

    def test_cli_unknown_exclusion_exits_2(self, tmp_path: Path) -> None:
        bench = _bench()
        bench_path = tmp_path / "bench.json"
        bench_path.write_text(bench.model_dump_json())
        result = CliRunner().invoke(cli, [
            "survey", "import", str(bench_path), "-r", str(_csv(tmp_path, bench, RESPONDENTS)),
            "-o", str(tmp_path / "m.json"), "--exclude-respondent", "R_9",
        ])
        assert result.exit_code == 2
        assert "R_9" in result.output

    def test_cli_export(self, tmp_path: Path) -> None:
        bench = _bench()
        bench_path, spec_path, out = tmp_path / "b.json", tmp_path / "q.json", tmp_path / "s.qsf"
        bench_path.write_text(bench.model_dump_json())
        spec_path.write_text(json.dumps({
            "attention_checks": [{"id": "ac1", "text": "Choose Bad.", "answer": "Bad"}],
            "repeats": [bench.items[0].id],
        }))
        result = CliRunner().invoke(cli, [
            "survey", "export", str(bench_path), "-o", str(out), "--header-mode", "instructions",
            "--quality-checks", str(spec_path),
        ])
        assert result.exit_code == 0, result.output
        assert "Quality checks: 1 attention checks among the items, 1 items repeated" in (
            result.output
        )
        assert {"check_ac1", f"repeat_{bench.items[0].id}"} <= set(
            _questions(json.loads(out.read_text()))
        )
