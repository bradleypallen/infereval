"""Tests for the native v0.5 schema fields added in v0.17.0.

Covers ordinal families, monotonicity-step annotations, ladder / variation /
target / placeholder / construction-note item metadata, and the copresence /
entailment / regularity declaration models — plus the consistency validations
that keep them referentially sound. All fields are additive: pre-v0.17.0
benchmarks validate unchanged (see :class:`TestBackCompat`).
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from infereval.benchmark import (
    Benchmark,
    CopresenceRule,
    EntailmentRule,
    MonotonicityStep,
    Regularity,
)


def _v05_dict() -> dict:
    """A minimal benchmark exercising every v0.17.0 native field."""
    return {
        "id": "v05-fixture",
        "targets": ["cpe", "ards"],
        "ordinal_families": {
            "bnp": ["bnp_lo", "bnp_grey", "bnp_hi"],
            "pf": ["pf_mild", "pf_severe"],
            "rs": ["rs_hfnc", "rs_niv"],
        },
        "copresence_rules": [{"families": ["pf", "rs"]}],
        "entailment_rules": [{"antecedent": "septic_shock", "consequent": "sep"}],
        "regularities": [
            {"description": "rs up => pf up", "test_item_ids": ["C1"]},
        ],
        "bearers": {
            "ad": {"expression": "the patient has acute dyspnea"},
            "bnp_lo": {"expression": "BNP < 100", "ordinal_family": "bnp"},
            "bnp_grey": {"expression": "BNP 100-500", "ordinal_family": "bnp"},
            "bnp_hi": {"expression": "BNP > 500", "ordinal_family": "bnp"},
            "pf_mild": {"expression": "P/F 200-300", "ordinal_family": "pf"},
            "pf_severe": {"expression": "P/F < 100", "ordinal_family": "pf"},
            "rs_hfnc": {"expression": "on high-flow nasal cannula", "ordinal_family": "rs"},
            "rs_niv": {"expression": "on non-invasive ventilation", "ordinal_family": "rs"},
            "septic_shock": {"expression": "in septic shock"},
            "sep": {"expression": "has sepsis"},
            "cpe": {"expression": "has cardiogenic pulmonary edema"},
            "ards": {"expression": "has ARDS"},
        },
        "analysts": [{"id": "a1"}],
        "items": [
            {
                "id": "A0",
                "premises": ["ad"],
                "conclusions": ["cpe"],
                "analyst_verdicts": ["abstain"],
                "ladder": "A",
                "variation": "base",
                "target": "cpe",
                "placeholder": "abstain",
            },
            {
                "id": "A6",
                "premises": ["ad", "pf_mild"],
                "conclusions": ["cpe"],
                "analyst_verdicts": ["good"],
                "ladder": "A",
                "variation": "contested",
                "target": "cpe",
                "placeholder": "contested",
                "construction_note": "preserved EF does not exclude CPE (HFpEF)",
            },
            {
                "id": "C1",
                "premises": ["ad", "bnp_lo"],
                "conclusions": ["cpe"],
                "analyst_verdicts": ["abstain"],
                "ladder": "C",
                "variation": "monotonicity_step",
                "target": "cpe",
                "placeholder": "bad",
                "monotonicity_step": {
                    "family": "bnp",
                    "tier": "bnp_lo",
                    "tier_index": 0,
                    "expected": "non_decreasing",
                },
            },
        ],
    }


class TestNativeFieldsValid:
    def test_loads_and_exposes_fields(self) -> None:
        b = Benchmark.model_validate(_v05_dict())
        assert b.targets == ["cpe", "ards"]
        assert b.ordinal_families["bnp"] == ["bnp_lo", "bnp_grey", "bnp_hi"]
        assert b.bearers["bnp_lo"].ordinal_family == "bnp"
        a0, a6, c1 = b.items
        assert a0.ladder == "A" and a0.variation == "base" and a0.target == "cpe"
        assert a6.placeholder == "contested"  # superset of Verdict, preserved
        assert "HFpEF" in (a6.construction_note or "")
        assert c1.monotonicity_step is not None
        assert c1.monotonicity_step.tier_index == 0
        assert c1.monotonicity_step.expected == "non_decreasing"

    def test_declaration_models_roundtrip(self) -> None:
        b = Benchmark.model_validate(_v05_dict())
        assert b.copresence_rules == [CopresenceRule(families=["pf", "rs"])]
        assert b.entailment_rules == [
            EntailmentRule(antecedent="septic_shock", consequent="sep")
        ]
        assert b.regularities == [
            Regularity(description="rs up => pf up", test_item_ids=["C1"])
        ]

    def test_json_roundtrip_preserves_native_fields(self) -> None:
        b = Benchmark.model_validate(_v05_dict())
        b2 = Benchmark.loads(b.dumps())
        assert b2.ordinal_families == b.ordinal_families
        assert b2.items[2].monotonicity_step == b.items[2].monotonicity_step
        assert b2.items[1].placeholder == "contested"

    def test_cross_family_fixed_tier(self) -> None:
        d = _v05_dict()
        d["items"][2]["monotonicity_step"] = {
            "family": "pf",
            "tier": "pf_severe",
            "tier_index": 1,
            "expected": "non_decreasing",
            "fixed": "bnp_hi",
        }
        b = Benchmark.model_validate(d)
        assert b.items[2].monotonicity_step is not None
        assert b.items[2].monotonicity_step.fixed == "bnp_hi"


class TestNativeFieldsValidation:
    @pytest.mark.parametrize(
        ("mutate", "match"),
        [
            (
                lambda d: d["ordinal_families"].__setitem__("bnp", ["bnp_lo", "ghost"]),
                "unknown bearer ids",
            ),
            (
                lambda d: d["items"][2]["monotonicity_step"].__setitem__(
                    "tier_index", 2
                ),
                "tier_index",
            ),
            (
                lambda d: d["items"][2]["monotonicity_step"].__setitem__(
                    "family", "nope"
                ),
                "not a declared ordinal family",
            ),
            (
                lambda d: d["items"][2]["monotonicity_step"].__setitem__(
                    "tier", "bnp_grey"
                ),
                "tier_index",
            ),
            (lambda d: d["items"][0].__setitem__("target", "xxx"), "declared benchmark target"),
            (
                lambda d: d["bearers"]["ad"].__setitem__("ordinal_family", "ghostfam"),
                "no such family is declared",
            ),
            (
                lambda d: d["copresence_rules"].append({"families": ["pf", "nope"]}),
                "unknown families",
            ),
            (
                lambda d: d["entailment_rules"].append(
                    {"antecedent": "ghost", "consequent": "sep"}
                ),
                "unknown bearer ids",
            ),
            (
                lambda d: d["regularities"].append(
                    {"description": "x", "test_item_ids": ["ZZ"]}
                ),
                "unknown item ids",
            ),
        ],
    )
    def test_rejects_inconsistent(self, mutate, match: str) -> None:
        d = _v05_dict()
        mutate(d)
        with pytest.raises(ValidationError, match=match):
            Benchmark.model_validate(d)

    def test_copresence_requires_two_families(self) -> None:
        # A well-formed MonotonicityStep constructs fine (baseline sanity)...
        MonotonicityStep(family="bnp", tier="bnp_lo", tier_index=0)
        # ...but a copresence rule needs at least two families.
        with pytest.raises(ValidationError):
            CopresenceRule(families=["pf"])


class TestBackCompat:
    """Pre-v0.17.0 benchmarks validate unchanged; new fields default empty."""

    def test_existing_benchmarks_have_empty_native_fields(self) -> None:
        for path in (
            "examples/pulmonary_edema/benchmark.json",
            "examples/stop_sign/benchmark.json",
        ):
            b = Benchmark.load(path)
            assert b.ordinal_families == {}
            assert b.copresence_rules == []
            assert b.entailment_rules == []
            assert b.regularities == []
            assert b.targets == []
            assert all(it.monotonicity_step is None for it in b.items)
            assert all(it.placeholder is None for it in b.items)

    def test_bare_item_defaults(self) -> None:
        d = copy.deepcopy(_v05_dict())
        for it in d["items"]:
            for k in ("ladder", "variation", "target", "placeholder"):
                it.pop(k, None)
            it.pop("monotonicity_step", None)
            it.pop("construction_note", None)
        b = Benchmark.model_validate(d)
        assert all(it.variation is None for it in b.items)
