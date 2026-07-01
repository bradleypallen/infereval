"""Tests for the constraint compiler (:mod:`infereval.compiler`).

Covers brief §2 acceptance criteria (b) — exact pairwise exclusivity for any
family and zero forbidden-cell sequents for any ``@copresent`` — and (c) —
generator saturation rejects a Γ carrying one co-present family's tier without
the other's.
"""

from __future__ import annotations

from itertools import combinations

from infereval.bearers import load_bearers_file
from infereval.compiler import (
    AdmissibilityRule,
    CopresenceSpec,
    compile_constraints,
    is_saturated,
)
from infereval.types import Implication


class TestExclusivity:
    def test_pairwise_exclusivity_count_and_shape(self) -> None:
        families = {"fam": ["t0", "t1", "t2", "t3"]}  # C(4,2) = 6 pairs
        result = compile_constraints(families)
        assert len(result.exclusivity_sequents) == 6
        # Every emitted sequent is ⟨{t_i, t_j}, ∅⟩.
        for seq in result.exclusivity_sequents:
            assert len(seq.premises) == 2
            assert seq.conclusions == frozenset()
        # Exactly the distinct tier pairs, nothing else.
        emitted = {seq.premises for seq in result.exclusivity_sequents}
        expected = {frozenset(pair) for pair in combinations(["t0", "t1", "t2", "t3"], 2)}
        assert emitted == expected

    def test_ordinal_and_mutex_treated_identically(self) -> None:
        # The compiler does not distinguish ordering; both are within-family
        # exclusive. Two 2-tier families → 1 + 1 = 2 exclusivity sequents.
        result = compile_constraints({"ord": ["a", "b"], "mut": ["x", "y"]})
        assert len(result.exclusivity_sequents) == 2

    def test_singleton_family_emits_nothing(self) -> None:
        result = compile_constraints({"fam": ["only"]})
        assert result.exclusivity_sequents == ()


class TestCopresence:
    def test_copresence_off_emits_admissibility_only(self) -> None:
        # Acceptance (b): @copresent yields zero cell-exclusion sequents by default.
        result = compile_constraints(
            {"pf": ["pf_a", "pf_b"], "rs": ["rs_a", "rs_b"]},
            copresence=[CopresenceSpec(families=("pf", "rs"))],
        )
        assert result.admissibility == (AdmissibilityRule(families=("pf", "rs")),)
        assert result.exhaustivity_sequents == ()
        # The only sequents are the within-family exclusivity ones (1 per family).
        assert len(result.sequents) == 2
        assert all(s.conclusions == frozenset() for s in result.sequents)

    def test_copresence_exhaustivity_on_emits_multisuccedent(self) -> None:
        result = compile_constraints(
            {"pf": ["pf_a", "pf_b"], "rs": ["rs_a", "rs_b"]},
            copresence=[CopresenceSpec(families=("pf", "rs"), exhaustivity=True)],
        )
        # For each pf tier: ⟨{pf_i}, {all rs tiers}⟩; symmetric for rs.
        assert len(result.exhaustivity_sequents) == 4
        pf_seq = next(
            s for s in result.exhaustivity_sequents if s.premises == frozenset({"pf_a"})
        )
        assert pf_seq.conclusions == frozenset({"rs_a", "rs_b"})


class TestSaturation:
    def test_saturation_rejects_partial_copresence(self) -> None:
        # Acceptance (c): a Γ with a pf tier but no rs tier is rejected.
        rule = AdmissibilityRule(families=("pf", "rs"))
        family_tiers = {"pf": ["pf_a", "pf_b"], "rs": ["rs_a", "rs_b"]}
        assert is_saturated(["pf_a"], rule, family_tiers) is False
        assert is_saturated(["rs_a"], rule, family_tiers) is False

    def test_saturation_accepts_both_or_neither(self) -> None:
        rule = AdmissibilityRule(families=("pf", "rs"))
        family_tiers = {"pf": ["pf_a", "pf_b"], "rs": ["rs_a", "rs_b"]}
        assert is_saturated(["pf_a", "rs_b"], rule, family_tiers) is True
        assert is_saturated(["something_else"], rule, family_tiers) is True  # neither


class TestEntailment:
    def test_entailment_sequents_opt_in(self) -> None:
        off = compile_constraints({}, entailments=[("a", "b")])
        assert off.entailment_sequents == ()
        on = compile_constraints(
            {}, entailments=[("a", "b")], emit_entailment_sequents=True
        )
        assert on.entailment_sequents == (Implication.of(["a"], ["b"]),)


class TestRealFixture:
    def test_v05_families_yield_pairwise_and_no_copresence_cells(self) -> None:
        doc = load_bearers_file("examples/AUMC_pilot/bearers_v0.5.txt")
        copresence = [CopresenceSpec(families=f) for f in doc.copresence]
        result = compile_constraints(
            doc.ordinal_families(), copresence=copresence
        )
        # Σ C(k,2) over the 11 families: 10+6+10+6+3+6+1+3+1+1+1 = 48.
        assert len(result.exclusivity_sequents) == 48
        # @copresent pf & rs → an admissibility rule and ZERO cell-exclusion sequents.
        assert result.admissibility == (AdmissibilityRule(families=("pf", "rs")),)
        assert result.exhaustivity_sequents == ()
