"""End-to-end logging test: run `evaluate` with --log and parse the JSONL output."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ScriptedProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---- Python API ------------------------------------------------------------


class TestLogPathOnEvaluate:
    def test_writes_expected_event_sequence(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 9 + ["BAD"] * 3)
        evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=3),
            run_id="run-A",
            log_path=log_path,
        )
        events = _load_jsonl(log_path)
        kinds = [e["event"] for e in events]
        # We expect run.started ... run.finished, with item.started / sample.* / item.completed inside
        assert kinds[0] == "run.started"
        assert kinds[-1] == "run.finished"
        # 4 items × (1 item.started + 3 sample.completed + 1 item.completed) = 20 inner events
        assert kinds.count("item.started") == 4
        assert kinds.count("item.completed") == 4
        assert kinds.count("sample.completed") == 12  # 4 items × 3 samples

    def test_every_record_has_run_id_and_benchmark_id(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=2),
            run_id="run-B",
            log_path=log_path,
        )
        for ev in _load_jsonl(log_path):
            assert ev["run_id"] == "run-B"
            assert ev["benchmark_id"] == "stop-sign-example-1"
            assert ev["framework_version"]  # populated

    def test_sample_completed_carries_full_audit_record(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=2, question_form="support"),
            log_path=log_path,
        )
        sample_events = [
            e for e in _load_jsonl(log_path) if e["event"] == "sample.completed"
        ]
        assert sample_events  # not empty
        e = sample_events[0]
        # Required audit fields per the M7 plan
        for key in (
            "item_id", "sample_index", "provider", "model_id",
            "request_id", "prompt_hash", "raw_response",
            "parsed_verdict", "parse_status", "wall_time_ms",
        ):
            assert key in e, f"sample.completed missing {key!r}: {e.keys()}"
        assert e["parsed_verdict"] == "good"
        assert e["parse_status"] == "ok"
        assert e["prompt_hash"].startswith("sha256:")

    def test_item_completed_carries_vote_breakdown(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=3),
            log_path=log_path,
        )
        item_completed = [
            e for e in _load_jsonl(log_path) if e["event"] == "item.completed"
        ]
        assert len(item_completed) == 4
        for e in item_completed:
            assert "item_id" in e and "verdict" in e
            assert "good" in e and "bad" in e and "abstain" in e
            assert "tie_broken" in e

    def test_run_started_records_benchmark_hash(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=1),
            log_path=log_path,
        )
        events = _load_jsonl(log_path)
        run_started = next(e for e in events if e["event"] == "run.started")
        assert run_started["benchmark_hash"].startswith("sha256:")
        assert run_started["n_items"] == 4
        assert run_started["provider"] == "mock"

    def test_no_log_when_log_path_none(self, tmp_path: Path) -> None:
        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        # Should not create any files in tmp_path
        evaluate(
            bench, provider,
            config=EndorsementConfig(n_samples=1),
            log_path=None,
        )
        assert list(tmp_path.iterdir()) == []


# ---- CLI integration ------------------------------------------------------


class TestCliLogFlag:
    def test_cli_writes_log_when_log_flag_set(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        log_path = tmp_path / "run.jsonl"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                    "--log", str(log_path),
                ],
            )
        assert result.exit_code == 0, result.output
        assert "log ->" in result.output
        assert log_path.exists()
        events = _load_jsonl(log_path)
        assert any(e["event"] == "run.started" for e in events)
        assert any(e["event"] == "run.finished" for e in events)

    def test_cli_no_log_when_flag_omitted(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "log ->" not in result.output

    def test_log_directory_created(self, tmp_path: Path) -> None:
        out_path = tmp_path / "eta.json"
        log_path = tmp_path / "nested" / "subdir" / "run.jsonl"
        provider = ScriptedProvider(responses=["GOOD"] * 10)
        with patch(
            "infereval.cli.evaluate_cmd.get_provider", return_value=provider
        ):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    "evaluate", str(STOP_SIGN_PATH),
                    "--provider", "openai", "--model", "gpt-4o-mini",
                    "--output", str(out_path),
                    "--n-samples", "1",
                    "--log", str(log_path),
                ],
            )
        assert result.exit_code == 0
        assert log_path.exists()
