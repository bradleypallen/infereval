"""Provenance-tuple tests (generalization brief §12.3, acceptance h)."""

from __future__ import annotations

import json
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ScriptedProvider


def _bench() -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "prov",
            "bearers": {b: {"expression": b} for b in ("p", "c")},
            "analysts": [{"id": "a1"}],
            "items": [
                {
                    "id": "it",
                    "premises": ["p"],
                    "conclusions": ["c"],
                    "analyst_verdicts": ["good"],
                }
            ],
        }
    )


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestPersistedProvenance:
    def test_question_form_persists_in_eta(self) -> None:
        eta = evaluate(
            _bench(),
            ScriptedProvider(responses=["INCOHERENT"] * 5),
            config=EndorsementConfig(n_samples=2, question_form="coherence"),
        )
        assert eta.endorsement_config.question_form == "coherence"
        # Round-trips through JSON.
        assert '"question_form": "coherence"' in eta.dumps()

    def test_default_is_support(self) -> None:
        eta = evaluate(_bench(), ScriptedProvider(responses=["GOOD"] * 5))
        assert eta.endorsement_config.question_form == "support"


class TestRunLogProvenance:
    def test_run_log_records_full_tuple(self, tmp_path: Path) -> None:
        log = tmp_path / "run.jsonl"
        evaluate(
            _bench(),
            ScriptedProvider(responses=["GOOD"] * 5),
            config=EndorsementConfig(n_samples=2),
            log_path=log,
            run_id="prov-run",
        )
        events = _read_events(log)
        started = next(e for e in events if e.get("event") == "item.started")
        # Full composed prompt + system + question_form + template/prompt id.
        assert "prompt" in started and "Premises:" in started["prompt"]
        assert started["question_form"] == "support"
        assert "verification_prompt_id" in started
        # Per-sample: raw completion + parsed verdict.
        sample = next(e for e in events if e.get("event") == "sample.completed")
        assert "raw_response" in sample
        assert sample["parsed_verdict"] == "good"


class TestPromptDeterminism:
    def test_same_config_yields_same_prompt(self, tmp_path: Path) -> None:
        # Acceptance (h): same (item, question_form, sampler, snapshot) → same prompt.
        prompts = []
        for run in ("a", "b"):
            log = tmp_path / f"{run}.jsonl"
            evaluate(
                _bench(),
                ScriptedProvider(responses=["GOOD"] * 5),
                config=EndorsementConfig(n_samples=1),
                log_path=log,
                run_id=run,
            )
            started = next(
                e for e in _read_events(log) if e.get("event") == "item.started"
            )
            prompts.append(started["prompt"])
        assert prompts[0] == prompts[1]
