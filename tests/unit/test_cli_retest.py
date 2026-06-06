"""Tests for ``infereval retest`` CLI in MANUAL mode (two pre-existing
eta files). v0.11.0 adds auto-mode tests in test_cli_retest_auto.py."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from infereval.cli.main import cli
from infereval.types import Verdict

from ..conftest import build_evaluation


def _dump_eta(eta, path: Path) -> None:
    eta.dump(path)


class TestManualMode:
    def test_happy_path_two_etas(self, tmp_path: Path) -> None:
        eta_a = build_evaluation(
            rows=[([Verdict.GOOD], Verdict.GOOD)] * 4,
            run_id="run-a",
        )
        eta_b = build_evaluation(
            rows=[([Verdict.GOOD], Verdict.GOOD)] * 4,
            run_id="run-b",
        )
        a_path = tmp_path / "a.json"
        b_path = tmp_path / "b.json"
        _dump_eta(eta_a, a_path)
        _dump_eta(eta_b, b_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["retest", str(a_path), str(b_path)])
        assert result.exit_code == 0, result.output
        assert "test-retest reliability" in result.output
        assert "items:       4" in result.output
        # Perfect agreement on identical etas — κ undefined (p_e=1) but the
        # 100% agreement line is present.
        assert "100.0%" in result.output

    def test_happy_path_with_output_file(self, tmp_path: Path) -> None:
        eta_a = build_evaluation(rows=[([Verdict.GOOD], Verdict.GOOD)] * 3, run_id="a")
        eta_b = build_evaluation(rows=[([Verdict.GOOD], Verdict.GOOD)] * 3, run_id="b")
        a_path = tmp_path / "a.json"
        b_path = tmp_path / "b.json"
        out_path = tmp_path / "retest.json"
        _dump_eta(eta_a, a_path)
        _dump_eta(eta_b, b_path)

        runner = CliRunner()
        result = runner.invoke(
            cli, ["retest", str(a_path), str(b_path), "-o", str(out_path)]
        )
        assert result.exit_code == 0, result.output
        assert out_path.is_file()
        loaded = json.loads(out_path.read_text())
        assert loaded["benchmark_id"] == "test-bench"
        assert loaded["n_items"] == 3

    def test_mismatched_benchmark_id_exits_1(self, tmp_path: Path) -> None:
        eta_a = build_evaluation(
            rows=[([Verdict.GOOD], Verdict.GOOD)],
            run_id="a", benchmark_id="bench-X",
        )
        eta_b = build_evaluation(
            rows=[([Verdict.GOOD], Verdict.GOOD)],
            run_id="b", benchmark_id="bench-Y",
        )
        a_path = tmp_path / "a.json"
        b_path = tmp_path / "b.json"
        _dump_eta(eta_a, a_path)
        _dump_eta(eta_b, b_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["retest", str(a_path), str(b_path)])
        assert result.exit_code == 1
        assert "incompatible runs" in result.output

    def test_malformed_eta_exits_2(self, tmp_path: Path) -> None:
        a_path = tmp_path / "bad.json"
        a_path.write_text("{not valid json")
        b_path = tmp_path / "b.json"
        eta_b = build_evaluation(rows=[([Verdict.GOOD], Verdict.GOOD)], run_id="b")
        _dump_eta(eta_b, b_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["retest", str(a_path), str(b_path)])
        assert result.exit_code == 2
        assert "could not load evaluation" in result.output

    def test_missing_eta_paths_errors(self) -> None:
        """Without --auto AND without eta paths, the command errors."""
        runner = CliRunner()
        result = runner.invoke(cli, ["retest"])
        assert result.exit_code != 0
        assert "Manual mode requires two positional eta paths" in result.output
