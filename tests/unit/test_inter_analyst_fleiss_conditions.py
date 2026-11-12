"""When the inter-analyst baseline κ_F* is (and is not) defined.

Pins the conditions stated in docs/formal_specification.md (Remark 2):
undefined with fewer than two analysts, with no all-substantive item, or
when every analyst rating falls in one class (P̄_e = 1). Analysts who agree
on every item while the items include both classes give κ_F* = 1.0.
"""

from __future__ import annotations

from infereval.benchmark import Benchmark
from infereval.metrics import inter_analyst_fleiss


def _bench(rows: list[list[str]]) -> Benchmark:
    m = len(rows[0])
    return Benchmark.model_validate({
        "id": "kfstar",
        "bearers": {"p": {"expression": "p"}, "q": {"expression": "q"}},
        "analysts": [{"id": f"a{j}"} for j in range(m)],
        "items": [
            {"id": f"i{k}", "premises": ["p"], "conclusions": ["q"], "analyst_verdicts": row}
            for k, row in enumerate(rows)
        ],
    })


def test_unanimous_on_every_item_with_both_classes_is_perfect_agreement() -> None:
    assert inter_analyst_fleiss(_bench([["good", "good"], ["bad", "bad"], ["good", "good"]])) == 1.0


def test_all_ratings_in_one_class_is_undefined() -> None:
    assert inter_analyst_fleiss(_bench([["good", "good"], ["good", "good"]])) is None


def test_single_analyst_is_undefined() -> None:
    assert inter_analyst_fleiss(_bench([["good"], ["bad"]])) is None


def test_no_all_substantive_item_is_undefined() -> None:
    assert inter_analyst_fleiss(_bench([["good", "abstain"], ["abstain", "bad"]])) is None
