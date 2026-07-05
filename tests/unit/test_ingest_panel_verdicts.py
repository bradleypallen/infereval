"""Tests for ``experiments/scripts/ingest_panel_verdicts.py``.

The script is run via subprocess (``sys.executable``) against a TMP COPY of
the real v0.5 source so the committed ``examples/clinical_pilot/*.json`` are
never touched. Covers: happy path (6 verdicts land in the regenerated
benchmark's analyst_verdicts + analyst_rationales, real analyst declared,
hash changes), unknown-id error, bad-verdict-value error, dry-run writes
nothing, and non-contested-id warning.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from infereval.benchmark import Benchmark
from infereval.evaluation import canonical_benchmark_hash

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "experiments" / "scripts" / "ingest_panel_verdicts.py"
PILOT = REPO_ROOT / "examples" / "clinical_pilot"
REAL_BEARERS = PILOT / "bearers_v0.5.txt"
REAL_V05 = PILOT / "benchmark_v0.5.json"

CONTESTED = ["A0", "A4", "A8", "B7", "B8", "D1"]

_GOOD_VERDICTS = {
    "A0": {"verdict": "bad", "rationale": "Infiltrates + dyspnea alone underdetermine CPE."},
    "A4": {"verdict": "good", "rationale": "Very positive fluid balance favors CPE."},
    "A8": {"verdict": "bad", "rationale": "Diuresed-negative, no effusion: against active CPE."},
    "B7": {"verdict": "bad", "rationale": "Cardiotoxic agent points cardiogenic, not ARDS."},
    "B8": {"verdict": "abstain", "rationale": "Fluid-overload exclusion makes this ill-posed."},
    "D1": {"verdict": "abstain", "rationale": "Risk factors alone underdetermine the inference."},
}


def _write_verdicts(path: Path, verdicts: dict, *, analyst_id: str = "clinical-analyst-1") -> None:
    path.write_text(
        json.dumps(
            {"analyst_id": analyst_id, "date": "2026-07-05", "verdicts": verdicts},
            indent=2,
        ),
        encoding="utf-8",
    )


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Path]:
    """A tmp copy of the v0.5 source + bearers; committed files untouched."""
    v05 = tmp_path / "benchmark_v0.5.json"
    shutil.copyfile(REAL_V05, v05)
    out = tmp_path / "benchmark.json"
    verdicts = tmp_path / "verdicts.json"
    log = tmp_path / "ingest.log.jsonl"
    return {"v05": v05, "out": out, "verdicts": verdicts, "log": log}


def _base_args(ws: dict[str, Path]) -> list[str]:
    return [
        "--verdicts", str(ws["verdicts"]),
        "--bearers", str(REAL_BEARERS),
        "--benchmark-v05", str(ws["v05"]),
        "--out-benchmark", str(ws["out"]),
    ]


class TestHappyPath:
    def test_six_verdicts_land_in_regenerated_benchmark(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        _write_verdicts(ws["verdicts"], _GOOD_VERDICTS)
        result = _run([*_base_args(ws), "--log", str(ws["log"])])
        assert result.returncode == 0, result.stderr

        bench = Benchmark.load(ws["out"])
        # The real analyst is declared exactly once, with the file's id.
        assert bench.m == 1
        assert bench.analysts[0].id == "clinical-analyst-1"

        by_id = {it.id: it for it in bench.items}
        for item_id, payload in _GOOD_VERDICTS.items():
            it = by_id[item_id]
            assert [str(v) for v in it.analyst_verdicts] == [payload["verdict"]]
            assert it.analyst_rationales == [payload["rationale"]]
            # Placeholder is preserved as construction history (firewall).
            assert it.placeholder is not None

        # The 29 unreviewed items are abstain-padded with no rationale.
        reviewed = set(_GOOD_VERDICTS)
        for it in bench.items:
            if it.id not in reviewed:
                assert [str(v) for v in it.analyst_verdicts] == ["abstain"]
                assert it.analyst_rationales is None

    def test_hash_changes(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        old_hash = canonical_benchmark_hash(
            _build_from(REAL_BEARERS, json.loads(ws["v05"].read_text()))
        )
        _write_verdicts(ws["verdicts"], _GOOD_VERDICTS)
        result = _run(_base_args(ws))
        assert result.returncode == 0, result.stderr
        new_hash = canonical_benchmark_hash(Benchmark.load(ws["out"]))
        assert new_hash != old_hash
        # Both hashes are surfaced in the stdout report.
        assert old_hash in result.stdout
        assert new_hash in result.stdout
        # The retest-compat reminder is printed.
        assert "REFUSED" in result.stdout

    def test_v05_source_updated_in_place(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        _write_verdicts(ws["verdicts"], _GOOD_VERDICTS)
        assert _run(_base_args(ws)).returncode == 0
        src = json.loads(ws["v05"].read_text(encoding="utf-8"))
        assert src["_meta"]["analysts"][0]["id"] == "clinical-analyst-1"
        by_id = {it["id"]: it for it in src["items"]}
        assert by_id["A0"]["analyst_verdicts"] == ["bad"]
        assert by_id["A0"]["analyst_rationales"] == [_GOOD_VERDICTS["A0"]["rationale"]]
        # Unreviewed items keep an empty analyst_verdicts in the SOURCE.
        assert by_id["A1"]["analyst_verdicts"] == []
        assert "analyst_rationales" not in by_id["A1"]


class TestValidationErrors:
    def test_unknown_id_errors(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        _write_verdicts(
            ws["verdicts"],
            {"ZZ9": {"verdict": "good", "rationale": "not a real item"}},
        )
        result = _run(_base_args(ws))
        assert result.returncode == 1
        assert "unknown item id" in result.stderr.lower()
        assert not ws["out"].exists()

    def test_bad_verdict_value_errors(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        _write_verdicts(
            ws["verdicts"],
            {"A0": {"verdict": "maybe", "rationale": "not a valid verdict value"}},
        )
        result = _run(_base_args(ws))
        assert result.returncode == 1
        assert "not one of" in result.stderr.lower()
        assert not ws["out"].exists()

    def test_empty_rationale_errors(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        _write_verdicts(ws["verdicts"], {"A0": {"verdict": "good", "rationale": "  "}})
        result = _run(_base_args(ws))
        assert result.returncode == 1
        assert "rationale is empty" in result.stderr.lower()
        assert not ws["out"].exists()


class TestDryRun:
    def test_dry_run_writes_nothing(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        v05_before = ws["v05"].read_bytes()
        _write_verdicts(ws["verdicts"], _GOOD_VERDICTS)
        result = _run([*_base_args(ws), "--dry-run"])
        assert result.returncode == 0, result.stderr
        assert "no files written" in result.stdout.lower()
        # Neither the out benchmark nor the source moved.
        assert not ws["out"].exists()
        assert ws["v05"].read_bytes() == v05_before


class TestNonContestedWarning:
    def test_non_contested_id_warns_but_proceeds(self, workspace: dict[str, Path]) -> None:
        ws = workspace
        # A1 is a real item but NOT in the contested six.
        _write_verdicts(
            ws["verdicts"],
            {"A1": {"verdict": "good", "rationale": "strengthened variant, clearly CPE."}},
        )
        result = _run(_base_args(ws))
        assert result.returncode == 0, result.stderr
        assert "non-contested" in result.stderr.lower()
        bench = Benchmark.load(ws["out"])
        a1 = next(it for it in bench.items if it.id == "A1")
        assert [str(v) for v in a1.analyst_verdicts] == ["good"]


def _build_from(bearers_path: Path, items_doc: dict) -> Benchmark:
    from infereval.bearers import load_bearers_file
    from infereval.cli.bearers_cmd import build_benchmark

    return build_benchmark(load_bearers_file(bearers_path), items_doc)


def test_committed_v05_untouched_by_this_module() -> None:
    """Guard: the real committed v0.5 is only ever read, never written."""
    # The test suite must not have declared analysts on the committed source.
    src = json.loads(REAL_V05.read_text(encoding="utf-8"))
    assert "analysts" not in src["_meta"]
    assert all(it["analyst_verdicts"] == [] for it in src["items"])
