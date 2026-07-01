"""Tests for ``infereval bearers-import`` and its reusable builder."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from infereval.bearers import parse_bearers_file
from infereval.benchmark import Benchmark
from infereval.cli.bearers_cmd import build_benchmark
from infereval.cli.main import cli

REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT = REPO_ROOT / "examples" / "clinical_pilot"
BEARERS = PILOT / "bearers_v0.5.txt"
ITEMS = PILOT / "benchmark_v0.5.json"


class TestCli:
    def test_import_validates_only_without_out(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["bearers-import", str(BEARERS), str(ITEMS)])
        assert result.exit_code == 0, result.output
        assert "clinical-pilot-cpe-ards-v0.5" in result.output
        assert "items=35" in result.output
        assert "ordinal_families=11" in result.output

    def test_import_writes_native_benchmark(self, tmp_path: Path) -> None:
        out = tmp_path / "benchmark.json"
        runner = CliRunner()
        result = runner.invoke(
            cli, ["bearers-import", str(BEARERS), str(ITEMS), "-o", str(out)]
        )
        assert result.exit_code == 0, result.output
        raw = out.read_text(encoding="utf-8")
        assert "v0.5-extras" not in raw  # the construction_metadata hack is gone
        bench = Benchmark.load(out)
        assert bench.n == 35
        assert len(bench.ordinal_families) == 11
        assert bench.copresence_rules[0].families == ["pf", "rs"]
        c1 = next(it for it in bench.items if it.id == "C1")
        assert c1.monotonicity_step is not None
        assert c1.monotonicity_step.family == "bnp"
        # The v0.5 "contested" placeholder survives natively (no normalization).
        f1 = next(it for it in bench.items if it.id == "F1")
        assert f1.placeholder == "contested"


class TestBuilder:
    def test_synthesizes_pending_analyst_when_absent(self) -> None:
        doc = parse_bearers_file(BEARERS.read_text(encoding="utf-8"))
        items_doc = json.loads(ITEMS.read_text(encoding="utf-8"))
        bench = build_benchmark(doc, items_doc)
        assert bench.m == 1
        assert bench.analysts[0].id == "pending-analyst-panel"
        assert all(v == "abstain" for it in bench.items for v in it.analyst_verdicts)
        # Placeholder markers are preserved and independent of the abstain verdicts.
        assert any(it.placeholder == "good" for it in bench.items)

    def test_respects_meta_supplied_analysts(self) -> None:
        doc = parse_bearers_file('cpe "has CPE"\nad "acute dyspnea"\n')
        items_doc = {
            "_meta": {
                "id": "tiny",
                "targets": ["cpe"],
                "analysts": [{"id": "clin-1"}, {"id": "clin-2"}],
            },
            "items": [
                {
                    "id": "x0",
                    "premises": ["ad"],
                    "target": "cpe",
                    "analyst_verdicts": ["good", "abstain"],
                    "variation": "base",
                    "placeholder": "good",
                }
            ],
        }
        bench = build_benchmark(doc, items_doc)
        assert bench.m == 2
        assert bench.items[0].conclusions == ["cpe"]
        assert bench.items[0].analyst_verdicts == ["good", "abstain"]
