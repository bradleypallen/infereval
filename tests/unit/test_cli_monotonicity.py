"""Tests for ``infereval monotonicity`` CLI + the markdown renderer."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from infereval.benchmark import Benchmark
from infereval.cli.main import cli
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.monotonicity import render_markdown, score_all_ladders
from infereval.providers.mock import ScriptedProvider

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "examples" / "clinical_pilot"
DRYRUN = ROOT / "experiments" / "results" / "clinical_pilot" / "dryrun_2026-06-30"
GPT55_ETA = DRYRUN / "gpt-5.5-eta.json"
BENCH = PILOT / "benchmark.json"


class TestCli:
    def test_scores_dryrun_ladders(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["monotonicity", str(GPT55_ETA), str(BENCH)])
        assert result.exit_code == 0, result.output
        assert "3 monotone, 0 violated" in result.output
        assert "| C | bnp |" in result.output
        assert "Variation breakdown" in result.output

    def test_no_variation_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli, ["monotonicity", str(GPT55_ETA), str(BENCH), "--no-variation"]
        )
        assert result.exit_code == 0
        assert "Variation breakdown" not in result.output


def _violation_benchmark() -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "viol",
            "targets": ["tgt"],
            "ordinal_families": {"fam": ["t0", "t1"]},
            "bearers": {
                "base": {"expression": "base"},
                "t0": {"expression": "t0", "ordinal_family": "fam"},
                "t1": {"expression": "t1", "ordinal_family": "fam"},
                "tgt": {"expression": "tgt"},
            },
            "analysts": [{"id": "a1"}],
            "items": [
                {
                    "id": f"L{i}",
                    "premises": ["base", f"t{i}"],
                    "conclusions": ["tgt"],
                    "analyst_verdicts": ["abstain"],
                    "ladder": "L",
                    "variation": "monotonicity_step",
                    "monotonicity_step": {
                        "family": "fam",
                        "tier": f"t{i}",
                        "tier_index": i,
                        "expected": "non_decreasing",
                    },
                }
                for i in range(2)
            ],
        }
    )


class TestViolationExit:
    def test_violation_exits_nonzero(self, tmp_path: Path) -> None:
        bench = _violation_benchmark()
        # good then bad → strict inversion under non_decreasing.
        eta = evaluate(
            bench,
            ScriptedProvider(responses=["GOOD", "BAD"]),
            config=EndorsementConfig(n_samples=1),
        )
        eta_path = tmp_path / "eta.json"
        bench_path = tmp_path / "bench.json"
        eta.dump(eta_path)
        bench.dump(bench_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["monotonicity", str(eta_path), str(bench_path)])
        assert result.exit_code == 1
        assert "1 violated" in result.output
        assert "Violations" in result.output


class TestRenderMarkdown:
    def test_empty_results(self) -> None:
        assert "No monotonicity ladders" in render_markdown([])

    def test_renders_sequence_glyphs(self) -> None:
        bench = Benchmark.load(BENCH)
        from infereval.evaluation import Evaluation

        eta = Evaluation.load(GPT55_ETA)
        md = render_markdown(score_all_ladders(eta, bench))
        assert "`BGGGG`" in md  # ladder C bad→good sequence
        assert "monotone" in md
