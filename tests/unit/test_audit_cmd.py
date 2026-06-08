"""Tests for ``infereval audit`` (v0.15.0+).

Covers both the v0.15.0 ``provider_error`` known-failure path and the
legacy heuristic (parsed_verdict=ABSTAIN + empty raw_response /
zero wall_time_ms) for pre-v0.15.0 etas.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from infereval.cli.audit_cmd import audit_cmd


def _minimal_eta_dict(items_samples: list[list[dict]]) -> dict:
    """Build a minimal Evaluation JSON suitable for audit_cmd.

    ``items_samples[i][j]`` is the dict-form ``SampleRecord`` to use for
    item i, sample j. The function fills in mandatory benchmark / model
    plumbing so the Evaluation validates.
    """
    items = []
    for i, samples in enumerate(items_samples):
        items.append(
            {
                "id": f"item-{i}",
                "premises": ["a"],
                "conclusions": ["b"],
                # 3 analyst verdicts so the consensus_reference works.
                "analyst_verdicts": ["good", "good", "good"],
                "model_verdict": "good",
                "samples": samples,
            }
        )
    return {
        "id": "test-eta",
        "benchmark_id": "test-bench",
        "benchmark_hash": "sha256:0" * 4,
        "model": {
            "provider": "mock",
            "model_id": "mock-v1",
            "params": {
                "temperature": 1.0,
                "max_tokens": 1024,
                "top_p": None,
                "seed": None,
                "stop": [],
            },
        },
        "endorsement_config": {
            "n_samples": 3,
            "tie_break": "abstain",
            "verification_prompt_id": "default",
        },
        "items": items,
        "framework_version": "0.15.0",
        "started_at": "2026-06-07T00:00:00Z",
        "finished_at": "2026-06-07T00:01:00Z",
    }


def _good_sample(index: int) -> dict:
    return {
        "sample_index": index,
        "raw_response": "GOOD",
        "parsed_verdict": "good",
        "parse_status": "ok",
        "wall_time_ms": 100.0,
    }


def _silent_failure_sample(index: int) -> dict:
    """v0.14.0-era silent failure: ABSTAIN + empty body + 0 wall_time."""
    return {
        "sample_index": index,
        "raw_response": "",
        "parsed_verdict": "abstain",
        "parse_status": "ok",
        "wall_time_ms": 0.0,
    }


def _known_failure_sample(index: int) -> dict:
    """v0.15.0+ known failure: provider_error set."""
    return {
        "sample_index": index,
        "raw_response": "",
        "parsed_verdict": "abstain",
        "parse_status": "sample_failed",
        "wall_time_ms": None,
        "provider_error": "EmptyResponseError(...)",
    }


def _real_abstain_sample(index: int) -> dict:
    """Genuine model abstention: ABSTAIN with non-empty body + real wall_time."""
    return {
        "sample_index": index,
        "raw_response": "I cannot determine — abstain.",
        "parsed_verdict": "abstain",
        "parse_status": "ok",
        "wall_time_ms": 250.0,
    }


def _write(tmp_path: Path, eta: dict) -> Path:
    p = tmp_path / "eta.json"
    p.write_text(json.dumps(eta))
    return p


class TestAuditCmd:
    def test_clean_eta_reports_zero_failures(self, tmp_path: Path) -> None:
        eta = _minimal_eta_dict(
            [[_good_sample(0), _good_sample(1), _good_sample(2)] for _ in range(3)]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p)])
        assert result.exit_code == 0, result.output
        assert "known provider errors    : 0" in result.output
        assert "suspected silent failures: 0" in result.output

    def test_silent_failure_detected_by_heuristic(self, tmp_path: Path) -> None:
        eta = _minimal_eta_dict(
            [
                [_good_sample(0), _good_sample(1), _silent_failure_sample(2)],
                [_good_sample(0), _good_sample(1), _good_sample(2)],
            ]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p)])
        assert result.exit_code == 0, result.output
        assert "suspected silent failures: 1" in result.output

    def test_known_provider_error_counted(self, tmp_path: Path) -> None:
        eta = _minimal_eta_dict(
            [[_good_sample(0), _good_sample(1), _known_failure_sample(2)]]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p)])
        assert result.exit_code == 0, result.output
        assert "known provider errors    : 1" in result.output
        # And the heuristic should NOT double-count the same sample.
        assert "suspected silent failures: 0" in result.output

    def test_real_abstain_not_flagged(self, tmp_path: Path) -> None:
        """Genuine model abstention (non-empty body + real wall_time) must
        not be flagged as a silent failure."""
        eta = _minimal_eta_dict(
            [[_good_sample(0), _real_abstain_sample(1), _good_sample(2)]]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p)])
        assert result.exit_code == 0, result.output
        assert "suspected silent failures: 0" in result.output

    def test_json_output_round_trips(self, tmp_path: Path) -> None:
        eta = _minimal_eta_dict(
            [[_good_sample(0), _good_sample(1), _silent_failure_sample(2)]]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p), "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["n_suspected_silent_failures"] == 1
        assert report["n_known_provider_errors"] == 0
        assert report["per_item_failures"][0]["id"] == "item-0"
        # Both published and recomputed metric blocks present.
        assert "coverage" in report["published"]
        assert "coverage" in report["recomputed_failures_excluded"]

    def test_verbose_includes_per_item(self, tmp_path: Path) -> None:
        eta = _minimal_eta_dict(
            [
                [_good_sample(0), _good_sample(1), _silent_failure_sample(2)],
                [_good_sample(0), _good_sample(1), _good_sample(2)],
            ]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p), "--verbose"])
        assert result.exit_code == 0, result.output
        assert "Per-item failure breakdown" in result.output
        assert "item-0" in result.output
        # item-1 has no flagged samples and should not appear.
        assert "item-1" not in result.output

    def test_recomputed_coverage_drops_failed_samples(
        self, tmp_path: Path
    ) -> None:
        """When an item's only ABSTAIN is a silent failure and the other
        samples are GOOD, the recomputed vote becomes GOOD — coverage
        should reflect that."""
        # 3 items: each had 2 GOOD + 1 silent-failure ABSTAIN.
        # Published model_verdict was "good" in our fixture, but if
        # captured under the bug it would have been the failed-ABSTAIN
        # majority. Recomputed reliability path rebuilds majority
        # excluding failed samples.
        eta = _minimal_eta_dict(
            [
                [_good_sample(0), _good_sample(1), _silent_failure_sample(2)],
                [_good_sample(0), _good_sample(1), _silent_failure_sample(2)],
                [_good_sample(0), _good_sample(1), _silent_failure_sample(2)],
            ]
        )
        p = _write(tmp_path, eta)
        result = CliRunner().invoke(audit_cmd, [str(p), "--json"])
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        # All three items recover a substantive GOOD verdict.
        assert report["recomputed_failures_excluded"]["coverage"] == 1.0
