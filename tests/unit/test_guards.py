"""Tests for validity guards (:mod:`infereval.guards`, brief §8, §12.7)."""

from __future__ import annotations

from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.guards import (
    distribution_agreement,
    shuffle_invariance,
    template_equivalence,
)
from infereval.providers.mock import ScriptedProvider


def _bench() -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "guard",
            "bearers": {b: {"expression": b} for b in ("p", "c0", "c1", "c2")},
            "analysts": [{"id": "a1"}],
            "items": [
                {
                    "id": f"i{k}",
                    "premises": ["p"],
                    "conclusions": [f"c{k}"],
                    "analyst_verdicts": ["good"],
                }
                for k in range(3)
            ],
        }
    )


def _run(responses: list[str], *, n_samples: int = 3):
    return evaluate(
        _bench(),
        ScriptedProvider(responses=responses),
        config=EndorsementConfig(n_samples=n_samples),
    )


class TestAgreementGate:
    def test_identical_runs_pass_below_threshold(self) -> None:
        a = _run(["GOOD"] * 9)
        b = _run(["GOOD"] * 9)
        res = distribution_agreement(a, b, n_floor=3)
        assert res.passed
        assert res.max_tv == 0.0

    def test_divergent_template_fails(self) -> None:
        # i1 flips good→bad between the two runs → TV = 1.0 > 0.10.
        a = _run(["GOOD", "GOOD", "GOOD", "GOOD", "GOOD", "GOOD", "GOOD", "GOOD", "GOOD"])
        b = _run(["GOOD", "GOOD", "GOOD", "BAD", "BAD", "BAD", "GOOD", "GOOD", "GOOD"])
        res = distribution_agreement(a, b, n_floor=3)
        assert not res.passed
        assert res.offenders[0][0] == "i1"
        assert res.offenders[0][1] == 1.0

    def test_under_powered_fails_even_when_identical(self) -> None:
        # Default n_floor=30 but only 3 samples/item → under-powered.
        a = _run(["GOOD"] * 9)
        b = _run(["GOOD"] * 9)
        res = distribution_agreement(a, b)  # default n_floor=30
        assert not res.passed
        assert set(res.under_powered) == {"i0", "i1", "i2"}

    def test_summary_string(self) -> None:
        a = _run(["GOOD"] * 9)
        b = _run(["GOOD"] * 9)
        assert "PASS" in distribution_agreement(a, b, n_floor=3).summary()


class TestWrappers:
    def test_template_equivalence(self) -> None:
        a = _run(["GOOD"] * 9)
        b = _run(["GOOD"] * 9)
        assert template_equivalence(a, b, n_floor=3).passed

    def test_shuffle_invariance(self) -> None:
        a = _run(["GOOD"] * 9)
        b = _run(["GOOD"] * 9)
        assert shuffle_invariance(a, b, n_floor=3).passed
