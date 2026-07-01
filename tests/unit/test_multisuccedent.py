"""Arity generalization at the data-model + frame level (v0.17.2 Stage 1).

The item is generalized to ``⟨Γ, Δ⟩`` with ``|Δ| ∈ {0, 1, ≥2}``. This module
confirms the data model already admits every arity and that Definition-3
Containment (``frame.py``) is correct for all of them without a logic change —
the empty-succedent (incompatibility) item gets NO free Containment inclusion,
and ``⟨∅, ∅⟩`` stays excluded by stipulation. Verdict elicitation / rendering
for non-singleton succedents is wired in later stages (the template registry);
here we only exercise structure and membership.
"""

from __future__ import annotations

import pytest

from infereval.benchmark import Benchmark
from infereval.frame import DerivedFrame, derive_closure
from infereval.types import Implication, Verdict


def _bench(conclusions: list[str]) -> Benchmark:
    return Benchmark.model_validate(
        {
            "id": "arity",
            "bearers": {b: {"expression": b} for b in ("a", "b", "c", "d")},
            "analysts": [{"id": "a1"}],
            "items": [
                {
                    "id": "it",
                    "premises": ["a"],
                    "conclusions": conclusions,
                    "analyst_verdicts": ["good"],
                }
            ],
        }
    )


class TestDataModelAdmitsArities:
    def test_empty_succedent_validates(self) -> None:
        b = _bench([])  # ⟨{a}, ∅⟩ — incompatibility
        assert b.items[0].to_implication().conclusions == frozenset()

    def test_disjunctive_succedent_validates(self) -> None:
        b = _bench(["c", "d"])  # ⟨{a}, {c, d}⟩ — |Δ| = 2
        assert b.items[0].to_implication().conclusions == frozenset({"c", "d"})

    def test_single_succedent_unchanged(self) -> None:
        b = _bench(["c"])
        assert b.items[0].to_implication().conclusions == frozenset({"c"})


class TestContainmentAllArities:
    def test_empty_succedent_gets_no_free_containment(self) -> None:
        # Γ ∩ ∅ = ∅, so an empty-succedent item is not in I_M by clause (i);
        # with no endorsement recorded it is not in I_M at all.
        frame = DerivedFrame.from_endorsements({b: _bearer(b) for b in "ab"}, {})
        assert not frame.contains(Implication.of(["a"], []))

    def test_empty_succedent_included_only_when_endorsed(self) -> None:
        imp = Implication.of(["a"], [])
        frame = DerivedFrame.from_endorsements(
            {b: _bearer(b) for b in "ab"}, {imp: Verdict.GOOD}
        )
        assert frame.contains(imp)  # clause (ii)

    def test_disjunctive_containment_by_overlap(self) -> None:
        # Γ ∩ Δ ≠ ∅ when a premise also appears among the disjuncts.
        frame = DerivedFrame.from_endorsements({b: _bearer(b) for b in "abc"}, {})
        assert frame.contains(Implication.of(["a", "b"], ["b", "c"]))  # b overlaps
        assert not frame.contains(Implication.of(["a"], ["b", "c"]))  # no overlap, unendorsed

    def test_empty_empty_still_excluded(self) -> None:
        frame = DerivedFrame.from_endorsements({}, {})
        assert not frame.contains(Implication.of([], []))

    def test_containment_invariant_holds(self) -> None:
        frame = DerivedFrame.from_endorsements({}, {})
        assert frame.satisfies_containment() is True


class TestCutSeam:
    def test_derive_closure_is_deferred(self) -> None:
        frame = DerivedFrame.from_endorsements({}, {})
        with pytest.raises(NotImplementedError, match="deferred"):
            derive_closure(frame)


def _bearer(bid: str):
    from infereval.types import Bearer

    return Bearer(id=bid, expression=bid)
