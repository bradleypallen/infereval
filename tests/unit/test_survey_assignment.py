"""--assignment: an incomplete design with core items for everyone and a rotated subset."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.metrics import (
    _panel_consensus_verdict,
    consensus_verdict,
    coverage_analyst,
    inter_analyst_fleiss,
)
from infereval.survey.qualtrics_csv import (
    IncompleteRespondentError,
    merge_respondents,
    parse_qualtrics_csv,
)
from infereval.survey.qualtrics_qsf import build_qsf
from infereval.survey.session import (
    AssignmentSpec,
    AttentionCheck,
    QualitySpec,
    load_assignment,
)
from infereval.types import Verdict

ROOT = Path(__file__).resolve().parents[2]
PULM_PATH = ROOT / "examples" / "pulmonary_edema" / "benchmark.json"

VERDICTS = ["Good", "Bad", "Can't tell"]
CORE = ("c1", "c2", "c3", "c4", "c5", "c6")
K = 8  # rotated items per respondent, of the 24 non-core


def _bench() -> Benchmark:
    data = json.loads(PULM_PATH.read_text())
    data["verification_prompt"] = {
        "id": "test-v1",
        "template": "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
        "survey_header": "Instructions.\n\nDoes it follow?",
        "survey_stem": "Does it follow?",
        "survey_choices": VERDICTS,
    }
    return Benchmark.model_validate(data)


SPEC = AssignmentSpec(core=CORE, rotated_per_respondent=K)
QUALITY = QualitySpec(
    attention_checks=(
        AttentionCheck("ac1", "Please choose Bad.", "Bad"),
        AttentionCheck("ac2", "Please choose Good.", "Good"),
        AttentionCheck("ac3", "Please choose Can't tell.", "Can't tell"),
    ),
    repeats=("c2", "c5"),
)


def _flow(qsf: dict[str, Any]) -> list[dict[str, Any]]:
    return next(el for el in qsf["SurveyElements"] if el["Element"] == "FL")["Payload"]["Flow"]


def _block_names(qsf: dict[str, Any]) -> dict[str, str]:
    blocks = next(el for el in qsf["SurveyElements"] if el["Element"] == "BL")["Payload"]
    blocks = blocks if isinstance(blocks, list) else list(blocks.values())
    return {b["ID"]: b["Description"] for b in blocks}


def _flow_ids(nodes: list[dict[str, Any]]) -> list[str]:
    out = []
    for n in nodes:
        out.append(n["FlowID"])
        out += _flow_ids(n.get("Flow", []))
    return out


class TestSpec:
    @pytest.mark.parametrize(
        ("core", "k", "match"),
        [((), 3, "at least one"), (("c1", "c1"), 3, "distinct"), (("c1",), 0, "at least 1")],
    )
    def test_invalid_spec(self, core: tuple[str, ...], k: int, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            AssignmentSpec(core=core, rotated_per_respondent=k)

    def test_rotated_checks_benchmark(self) -> None:
        ids = [i.id for i in _bench().items]
        assert SPEC.rotated(ids) == [i for i in ids if i not in CORE]
        assert SPEC.expected_ratings(30, ids) == pytest.approx(30 * K / 24)
        with pytest.raises(ValueError, match="not in the benchmark"):
            AssignmentSpec(core=("nope",), rotated_per_respondent=1).rotated(ids)
        with pytest.raises(ValueError, match="only 24 items are not core"):
            AssignmentSpec(core=CORE, rotated_per_respondent=25).rotated(ids)

    def test_load(self, tmp_path: Path) -> None:
        path = tmp_path / "a.json"
        path.write_text(json.dumps({"core": list(CORE), "rotated_per_respondent": K}))
        assert load_assignment(path) == SPEC
        path.write_text(json.dumps({"core": list(CORE), "rotated_per_respondent": "8"}))
        with pytest.raises(ValueError, match="must be an integer"):
            load_assignment(path)
        path.write_text(json.dumps({"core": list(CORE), "k": 8}))
        with pytest.raises(ValueError, match="unknown keys"):
            load_assignment(path)


class TestExport:
    def test_flow_counterbalances_core_and_rotated(self) -> None:
        qsf, _ = build_qsf(
            _bench(), header_mode="instructions", quality=QUALITY, assignment=SPEC
        )
        names = _block_names(qsf)
        flow = _flow(qsf)
        outer = next(n for n in flow if n["Type"] == "BlockRandomizer")
        assert outer["FlowID"] == "FL_3"
        assert (outer["SubSet"], outer["EvenPresentation"]) == (2, True)
        core_group, rotated_group = outer["Flow"]
        assert [g["Type"] for g in outer["Flow"]] == ["Group", "Group"]

        (core_rand,) = core_group["Flow"]
        core_units = [names[n["ID"]] for n in core_rand["Flow"]]
        assert core_units == [f"Item {i}" for i in CORE] + ["check ac1", "check ac3"]
        assert (core_rand["SubSet"], core_rand["EvenPresentation"]) == (len(core_units), False)

        rotated_rand, rotated_checks = rotated_group["Flow"]
        assert (rotated_rand["SubSet"], rotated_rand["EvenPresentation"]) == (K, True)
        assert [names[n["ID"]] for n in rotated_rand["Flow"]] == [
            f"Item {i.id}" for i in _bench().items if i.id not in CORE
        ]
        assert [names[n["ID"]] for n in rotated_checks["Flow"]] == ["check ac2"]

        # Repeats still follow everything, in their own randomizer.
        repeats = flow[flow.index(outer) + 1]
        assert [names[n["ID"]] for n in repeats["Flow"]] == ["repeat c2", "repeat c5"]
        ids = _flow_ids(flow)
        assert len(ids) == len(set(ids))

    def test_item_flow_ids_unchanged_without_assignment(self) -> None:
        plain, _ = build_qsf(_bench(), header_mode="instructions", quality=QUALITY)
        rand = next(n for n in _flow(plain) if n["Type"] == "BlockRandomizer")
        assert rand["FlowID"] == "FL_3"
        assert rand["SubSet"] == len(rand["Flow"]) == 30 + 3
        assert rand["Flow"][0]["FlowID"] == "FL_4"

    def test_refusals(self) -> None:
        with pytest.raises(ValueError, match="needs randomize_items"):
            build_qsf(_bench(), randomize_items=False, assignment=SPEC)
        with pytest.raises(ValueError, match="must be core items.*c9"):
            build_qsf(_bench(), assignment=SPEC, quality=QualitySpec(repeats=("c9",)))
        with pytest.raises(ValueError, match="not in the benchmark"):
            build_qsf(_bench(), assignment=AssignmentSpec(("zz",), 1))


def _csv(tmp_path: Path, shown: list[list[str]], *, display_order: bool = False) -> Path:
    """One finished Qualtrics row per respondent, answering only the ``shown`` item ids."""
    bench = _bench()
    header = ["ResponseId", "Finished", "expertise"] + [i.id for i in bench.items]
    if display_order:
        header.append("FL_3_DO")
    rows = []
    for n, ids in enumerate(shown):
        cells = [f"R_{n}", "True", ""]
        cells += [VERDICTS[k % 3] if item.id in ids else "" for k, item in enumerate(bench.items)]
        if display_order:
            cells.append("FL_9|FL_8")
        rows.append(cells)
    path = tmp_path / "responses.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows([header, header, ["{}"] * len(header), *rows])
    return path


def _rotated(start: int, k: int = K) -> list[str]:
    rotated = SPEC.rotated([i.id for i in _bench().items])
    return [rotated[(start + j) % len(rotated)] for j in range(k)]


class TestImport:
    def test_unshown_items_not_rated(self, tmp_path: Path) -> None:
        bench = _bench()
        shown = [list(CORE) + _rotated(0), list(CORE) + _rotated(8), list(CORE) + _rotated(16)]
        path = _csv(tmp_path, shown, display_order=True)
        respondents = parse_qualtrics_csv(path, choices=tuple(VERDICTS))
        merged = merge_respondents(bench, respondents, assignment=SPEC)
        assert len(merged.analysts) == 1 + 3
        for item in merged.items:
            new = item.analyst_verdicts[1:]
            if item.id in CORE:
                assert None not in new
            else:
                # Each rotated item was shown to exactly one of the three.
                assert sum(v is not None for v in new) == 1
        # Without --assignment the same blanks read as abstain (unchanged).
        old = merge_respondents(bench, respondents, require_complete=False)
        assert None not in [v for it in old.items for v in it.analyst_verdicts]
        # The merged file round-trips through JSON.
        again = Benchmark.model_validate_json(merged.model_dump_json())
        assert again.items[-1].analyst_verdicts == merged.items[-1].analyst_verdicts

    def test_complete_means_core_plus_k_rotated(self, tmp_path: Path) -> None:
        bench = _bench()
        too_few = _csv(tmp_path, [list(CORE) + _rotated(0, K - 1)])
        with pytest.raises(IncompleteRespondentError, match=f"rated {K - 1} rotated.*expected {K}"):
            merge_respondents(bench, parse_qualtrics_csv(too_few, choices=tuple(VERDICTS)),
                              assignment=SPEC)
        no_core = _csv(tmp_path, [list(CORE[1:]) + _rotated(0)])
        with pytest.raises(IncompleteRespondentError, match="missing verdicts on 1 item"):
            merge_respondents(bench, parse_qualtrics_csv(no_core, choices=tuple(VERDICTS)),
                              assignment=SPEC)
        partial = merge_respondents(
            bench, parse_qualtrics_csv(no_core, choices=tuple(VERDICTS)),
            assignment=SPEC, require_complete=False,
        )
        assert partial.items[0].analyst_verdicts[-1] is None


class TestMetricsWithUnrated:
    def test_consensus_ignores_unrated(self) -> None:
        g, b, a = Verdict.GOOD, Verdict.BAD, Verdict.ABSTAIN
        assert consensus_verdict([g, None, None, b, g]) == g
        assert consensus_verdict([None, None]) == a
        assert _panel_consensus_verdict([None, None, b], [0, 1, 2]) == b
        assert _panel_consensus_verdict([None, None], [0, 1]) == a

    def test_coverage_and_fleiss_over_rated(self, tmp_path: Path) -> None:
        bench = _bench()
        shown = [list(CORE) + _rotated(0), list(CORE) + _rotated(8)]
        merged = merge_respondents(
            bench, parse_qualtrics_csv(_csv(tmp_path, shown), choices=tuple(VERDICTS)),
            assignment=SPEC,
        )
        from infereval.evaluation import Evaluation, EvaluationItem

        eta = Evaluation.model_construct(
            items=[
                EvaluationItem.model_construct(
                    id=it.id, analyst_verdicts=it.analyst_verdicts, model_verdict=Verdict.GOOD
                )
                for it in merged.items
            ]
        )
        # Analyst 1 rated 6 + 8 items; a third of each answer cycle is Can't tell.
        rated = [it.analyst_verdicts[1] for it in merged.items if it.analyst_verdicts[1]]
        assert len(rated) == len(CORE) + K
        expected = sum(v != Verdict.ABSTAIN for v in rated) / len(rated)
        assert coverage_analyst(eta, 1) == pytest.approx(expected)
        # Fleiss over the new analysts covers only the items both rated (the core).
        both = [
            it for it in merged.items
            if all(v in (Verdict.GOOD, Verdict.BAD) for v in it.analyst_verdicts[1:])
        ]
        assert both and all(it.id in CORE for it in both)
        assert inter_analyst_fleiss(merged, analyst_indices=[1, 2]) is not None


class TestCli:
    def test_round_trip(self, tmp_path: Path) -> None:
        bench_path = tmp_path / "bench.json"
        bench_path.write_text(_bench().model_dump_json())
        spec_path = tmp_path / "assignment.json"
        spec_path.write_text(json.dumps({"core": list(CORE), "rotated_per_respondent": K}))
        runner = CliRunner()
        result = runner.invoke(cli, [
            "survey", "export", str(bench_path), "-o", str(tmp_path / "s.qsf"),
            "--header-mode", "instructions", "--assignment", str(spec_path),
        ])
        assert result.exit_code == 0, result.output
        assert "Assignment: 6 core items for everyone, plus 8 of the other 24" in result.output

        path = _csv(tmp_path, [list(CORE) + _rotated(0), list(CORE) + _rotated(4)])
        out = tmp_path / "merged.json"
        result = runner.invoke(cli, [
            "survey", "import", str(bench_path), "-r", str(path), "-o", str(out),
            "--assignment", str(spec_path),
        ])
        assert result.exit_code == 0, result.output
        assert "new ratings per rotated item min 0, max 2" in result.output
        merged = Benchmark.load(out)
        assert merged.items[0].analyst_verdicts[1:] != [None, None]

    def test_other_platform_refused(self, tmp_path: Path) -> None:
        bench_path = tmp_path / "bench.json"
        bench_path.write_text(_bench().model_dump_json())
        spec_path = tmp_path / "assignment.json"
        spec_path.write_text(json.dumps({"core": list(CORE), "rotated_per_respondent": K}))
        result = CliRunner().invoke(cli, [
            "survey", "export", str(bench_path), "-o", str(tmp_path / "f.gs"),
            "--platform", "google_forms", "--assignment", str(spec_path),
        ])
        assert result.exit_code == 2
        assert "--assignment is implemented for --platform qualtrics only" in result.output
