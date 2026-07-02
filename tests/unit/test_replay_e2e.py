"""End-to-end ReplayProvider tests + committed-fixture drift check.

The drift check regenerates ``stop_sign_replay.jsonl`` in a tmp path and
asserts byte-equality with the committed fixture. Failure means the
verification prompt template, context builders, or bearer expressions
have shifted -- regenerate with::

    python -m tests.fixtures.build_stop_sign_replay
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ReplayProvider
from infereval.types import Verdict

from ..fixtures.build_stop_sign_replay import (
    FIXTURE_PATH,
    RESPONSES_BY_ITEM_ID,
    build_records,
    serialize,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_BENCHMARK = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


# ---- Drift check (committed fixture vs generator output) ----------------


class TestFixtureDrift:
    def test_committed_fixture_matches_generator(self) -> None:
        expected = serialize(build_records())
        actual = FIXTURE_PATH.read_text(encoding="utf-8")
        assert actual == expected, (
            "Committed stop_sign_replay.jsonl is out of sync with the "
            "generator. Regenerate with: "
            "`python -m tests.fixtures.build_stop_sign_replay`."
        )

    def test_committed_fixture_has_expected_record_count(self) -> None:
        n_expected = sum(len(v) for v in RESPONSES_BY_ITEM_ID.values())
        n_actual = sum(
            1 for line in FIXTURE_PATH.read_text().splitlines() if line.strip()
        )
        assert n_actual == n_expected


# ---- Evaluate against the committed replay fixture ---------------------


class TestEvaluateWithReplay:
    @pytest.fixture
    def benchmark(self) -> Benchmark:
        return Benchmark.load(STOP_SIGN_BENCHMARK)

    @pytest.fixture
    def replay(self) -> ReplayProvider:
        return ReplayProvider(FIXTURE_PATH)

    def test_full_pipeline_produces_paper_analyst_row(
        self, benchmark: Benchmark, replay: ReplayProvider
    ) -> None:
        eta = evaluate(
            benchmark,
            replay,
            config=EndorsementConfig(n_samples=5, question_form="support"),
            run_id="replay-run-1",
        )
        verdicts = {it.id: it.model_verdict for it in eta.items}
        assert verdicts == {
            "row-0": Verdict.GOOD,
            "row-1": Verdict.GOOD,
            "row-2": Verdict.GOOD,
            "row-3": Verdict.BAD,
        }

    def test_majority_vote_breakdown_deterministic(
        self, benchmark: Benchmark, replay: ReplayProvider
    ) -> None:
        eta = evaluate(
            benchmark,
            replay,
            config=EndorsementConfig(n_samples=5, question_form="support"),
        )
        # All 5 responses for each row parse to the same verdict; verify counts.
        for item in eta.items:
            assert item.majority_vote is not None
            mv = item.majority_vote
            if item.id in ("row-0", "row-1", "row-2"):
                assert mv.good == 5
                assert mv.bad == 0
                assert mv.abstain == 0
                assert mv.verdict == Verdict.GOOD
                assert not mv.tie_broken
            else:  # row-3
                assert mv.good == 0
                assert mv.bad == 5
                assert mv.abstain == 0
                assert mv.verdict == Verdict.BAD
                assert not mv.tie_broken

    def test_raw_responses_preserved_from_fixture(
        self, benchmark: Benchmark, replay: ReplayProvider
    ) -> None:
        eta = evaluate(
            benchmark,
            replay,
            config=EndorsementConfig(n_samples=5, question_form="support"),
        )
        # Index items by id for predictable lookup
        by_id = {it.id: it for it in eta.items}
        # Sample texts in order should match the canned responses table
        for item_id, expected_texts in RESPONSES_BY_ITEM_ID.items():
            samples = by_id[item_id].samples
            assert [s.raw_response for s in samples] == expected_texts

    def test_recorded_provider_and_model_propagated(
        self, benchmark: Benchmark, replay: ReplayProvider
    ) -> None:
        eta = evaluate(
            benchmark,
            replay,
            config=EndorsementConfig(n_samples=1, question_form="support"),
        )
        # The Evaluation's ModelInfo records the provider's identity at
        # construction time -- ReplayProvider self-reports as "replay" /
        # the recorded model id.
        assert eta.model.provider == "replay"
        assert eta.model.model_id == "claude-haiku-4-5-20251001"
        # Each sample's individual provider/model fields come from the
        # recorded fixture (so a downstream consumer can see what was
        # originally recorded).
        for item in eta.items:
            for sample in item.samples:
                # We have these inside the underlying SampleResult, but
                # SampleRecord (the Pydantic JSON shape) doesn't expose them
                # directly -- it preserves the parsed verdict and raw text.
                # The provider/model identity lives on Evaluation.model.
                assert sample.raw_response

    def test_repeated_runs_are_byte_identical_on_deterministic_fields(
        self, benchmark: Benchmark, replay: ReplayProvider
    ) -> None:
        """Two runs with the same ``run_id`` should produce identical output
        on every field except wall-clock timestamps.

        Sample ``request_id``s embed the run id (``<run>:<item>:sample-N``),
        so pinning ``run_id`` is what makes the comparison meaningful;
        without it, the auto-generated uuid would cascade into every sample.
        """

        def _normalize(text: str) -> dict:
            data = json.loads(text)
            data.pop("started_at", None)
            data.pop("finished_at", None)
            return data

        eta1 = evaluate(
            benchmark, replay,
            config=EndorsementConfig(n_samples=5),
            run_id="run-fixed",
        )
        replay.reset()  # cursors back to the top
        eta2 = evaluate(
            benchmark, replay,
            config=EndorsementConfig(n_samples=5),
            run_id="run-fixed",
        )
        assert _normalize(eta1.dumps()) == _normalize(eta2.dumps())


# ---- CLI --replay-from path ---------------------------------------------


class TestCliReplayFrom:
    def test_writes_evaluation_without_provider_or_model(self, tmp_path: Path) -> None:
        out = tmp_path / "eta.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "evaluate", str(STOP_SIGN_BENCHMARK),
                "--replay-from", str(FIXTURE_PATH),
                "--output", str(out),
                "--n-samples", "5",
                "--question-form", "support",
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

        with out.open("r", encoding="utf-8") as f:
            eta = json.load(f)
        verdicts = {it["id"]: it["model_verdict"] for it in eta["items"]}
        assert verdicts == {
            "row-0": "good",
            "row-1": "good",
            "row-2": "good",
            "row-3": "bad",
        }

    def test_replay_with_log_writes_jsonl(self, tmp_path: Path) -> None:
        out = tmp_path / "eta.json"
        log_path = tmp_path / "run.jsonl"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "evaluate", str(STOP_SIGN_BENCHMARK),
                "--replay-from", str(FIXTURE_PATH),
                "--output", str(out),
                "--n-samples", "5",
                "--question-form", "support",
                "--log", str(log_path),
            ],
        )
        assert result.exit_code == 0, result.output
        assert log_path.exists()
        # Each line is a JSON event
        events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert any(e["event"] == "run.started" for e in events)
        assert any(e["event"] == "sample.completed" for e in events)

    def test_replay_with_missing_fixture(self, tmp_path: Path) -> None:
        out = tmp_path / "eta.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "evaluate", str(STOP_SIGN_BENCHMARK),
                "--replay-from", str(tmp_path / "missing.jsonl"),
                "--output", str(out),
            ],
        )
        # click rejects nonexistent paths via path_type's `exists=True`
        assert result.exit_code != 0
