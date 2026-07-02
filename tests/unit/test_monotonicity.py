"""Tests for the monotonicity scorer (:mod:`infereval.monotonicity`, brief §12.2)."""

from __future__ import annotations

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.monotonicity import score_all_ladders, score_ladder
from infereval.providers.mock import ScriptedProvider


def _ladder_benchmark(*, expected: str = "non_decreasing") -> Benchmark:
    """A 3-tier bnp ladder (t0<t1<t2) targeting one conclusion."""
    return Benchmark.model_validate(
        {
            "id": "mono-fixture",
            "targets": ["tgt"],
            "ordinal_families": {"bnp": ["t0", "t1", "t2"]},
            "bearers": {
                "base": {"expression": "base premise"},
                "t0": {"expression": "tier 0", "ordinal_family": "bnp"},
                "t1": {"expression": "tier 1", "ordinal_family": "bnp"},
                "t2": {"expression": "tier 2", "ordinal_family": "bnp"},
                "tgt": {"expression": "the target"},
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
                    "target": "tgt",
                    "monotonicity_step": {
                        "family": "bnp",
                        "tier": f"t{i}",
                        "tier_index": i,
                        "expected": expected,
                    },
                }
                for i in range(3)
            ],
        }
    )


def _score(verdict_texts: list[str], *, expected: str = "non_decreasing"):
    bench = _ladder_benchmark(expected=expected)
    # n_samples=1 → one scripted response per item, in item order t0, t1, t2.
    eta = evaluate(
        bench,
        ScriptedProvider(responses=verdict_texts),
        config=EndorsementConfig(n_samples=1, question_form="support"),
    )
    result = score_ladder(eta, bench, "L")
    assert result is not None
    return result


class TestScoring:
    def test_bad_then_good_is_monotone(self) -> None:
        r = _score(["BAD", "GOOD", "GOOD"])
        assert r.status == "monotone"
        assert r.is_monotone
        assert r.violations == ()
        assert [s.verdict.value for s in r.steps] == ["bad", "good", "good"]

    def test_good_then_bad_is_a_violation(self) -> None:
        r = _score(["GOOD", "BAD", "GOOD"])
        assert r.status == "violated"
        assert not r.is_monotone
        # The strict inversion is the adjacent good→bad pair (L0 → L1).
        assert r.violations == (("L0", "L1"),)

    def test_flat_all_good_is_monotone(self) -> None:
        r = _score(["GOOD", "GOOD", "GOOD"])
        assert r.status == "monotone"
        assert r.n_gaps == 0


class TestAbstainGaps:
    def test_abstain_is_skipped_not_a_violation(self) -> None:
        # good, gap, good — the gap neither satisfies nor violates.
        r = _score(["GOOD", "ABSTAIN", "GOOD"])
        assert r.status == "monotone"
        assert r.n_gaps == 1
        assert [s.item_id for s in r.substantive] == ["L0", "L2"]

    def test_inversion_across_a_gap_is_still_caught(self) -> None:
        # good, gap, bad — abstain skipped, but good→bad across it still inverts.
        r = _score(["GOOD", "ABSTAIN", "BAD"])
        assert r.status == "violated"
        assert r.n_gaps == 1
        assert r.violations == (("L0", "L2"),)

    def test_all_abstain_is_insufficient_not_a_pass(self) -> None:
        r = _score(["ABSTAIN", "ABSTAIN", "ABSTAIN"])
        assert r.status == "insufficient"
        assert not r.is_monotone or r.status != "monotone"  # never counts as monotone
        assert r.substantive == ()
        assert r.n_gaps == 3

    def test_single_substantive_step_is_insufficient(self) -> None:
        r = _score(["ABSTAIN", "GOOD", "ABSTAIN"])
        assert r.status == "insufficient"


class TestDirection:
    def test_non_increasing_flips_the_violation(self) -> None:
        # good→bad is fine under non_increasing; bad→good violates.
        ok = _score(["GOOD", "BAD", "BAD"], expected="non_increasing")
        assert ok.status == "monotone"
        bad = _score(["BAD", "GOOD", "GOOD"], expected="non_increasing")
        assert bad.status == "violated"


class TestRealFixture:
    def test_dryrun_ladders_all_monotone(self) -> None:
        from pathlib import Path

        from infereval.evaluation import Evaluation

        root = Path(__file__).resolve().parents[2]
        bench = Benchmark.load(root / "examples" / "clinical_pilot" / "benchmark.json")
        eta = Evaluation.load(
            root
            / "experiments"
            / "results"
            / "clinical_pilot"
            / "dryrun_2026-06-30"
            / "gpt-5.5-eta.json"
        )
        results = score_all_ladders(eta, bench)
        assert {r.ladder for r in results} == {"C", "F", "G"}
        assert all(r.status == "monotone" for r in results)
        # Ladder C carries the informative bad→good transition (bnp_lo defeater).
        ladder_c = next(r for r in results if r.ladder == "C")
        assert ladder_c.steps[0].verdict.value == "bad"
