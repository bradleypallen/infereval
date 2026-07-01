"""Placeholder firewall (brief §12.6), enforced as a CI gate.

``BenchmarkItem.placeholder`` is the author's provisional dry-run marker, NOT an
analyst verdict. The measurement layer (Definitions 6–10) must never read it;
``analyst_verdicts`` is the sole verdict source for κ. This is a *mechanical*
invariant, not reviewer discipline:

1. ``placeholder`` never enters the evaluation model / η (structural), and
2. no measurement module accesses a ``.placeholder`` attribute (AST-checked, so
   the docstring mention in ``metrics.py`` does not trip the gate), and
3. κ is invariant to placeholder values end-to-end.
"""

from __future__ import annotations

import ast
import inspect

import infereval.metrics as metrics_mod
import infereval.modeling as modeling_mod
import infereval.report as report_mod
import infereval.retest as retest_mod
import infereval.structure as structure_mod
from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, EvaluationItem, evaluate
from infereval.metrics import cohens_kappa, consensus_reference, fleiss_kappa
from infereval.providers.mock import ScriptedProvider

MEASUREMENT_MODULES = [
    metrics_mod,
    report_mod,
    retest_mod,
    modeling_mod,
    structure_mod,
]


def _bench_dict(*, placeholders: list[str]) -> dict:
    """Two-analyst benchmark with per-item placeholders (dry-run markers)."""
    return {
        "id": "firewall-fixture",
        "bearers": {
            "p": {"expression": "premise holds"},
            "q": {"expression": "conclusion holds"},
        },
        "analysts": [{"id": "a1"}, {"id": "a2"}],
        "items": [
            {
                "id": f"i{k}",
                "premises": ["p"],
                "conclusions": ["q"],
                "analyst_verdicts": ["good", "good"],
                "placeholder": ph,
            }
            for k, ph in enumerate(placeholders)
        ],
    }


class TestStructural:
    def test_placeholder_not_in_eta_schema(self) -> None:
        assert "placeholder" not in EvaluationItem.model_fields

    def test_no_placeholder_attribute_access_in_measurement_layer(self) -> None:
        for mod in MEASUREMENT_MODULES:
            tree = ast.parse(inspect.getsource(mod))
            offenders = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr == "placeholder"
            ]
            assert not offenders, (
                f"{mod.__name__} reads a .placeholder attribute — the placeholder "
                f"firewall forbids the measurement layer from touching it"
            )


class TestEndToEnd:
    def test_placeholder_absent_from_eta_output(self) -> None:
        bench = Benchmark.model_validate(
            _bench_dict(placeholders=["good", "bad", "contested"])
        )
        provider = ScriptedProvider(responses=["GOOD"] * 100)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=2))
        assert "placeholder" not in eta.dumps()

    def test_kappa_invariant_to_placeholder(self) -> None:
        provider_responses = ["GOOD", "GOOD", "BAD"] * 20

        def _kappas(placeholders: list[str]) -> tuple[float | None, float | None]:
            bench = Benchmark.model_validate(_bench_dict(placeholders=placeholders))
            eta = evaluate(
                bench,
                ScriptedProvider(responses=list(provider_responses)),
                config=EndorsementConfig(n_samples=1),
            )
            return (
                cohens_kappa(eta, consensus_reference(eta)),
                fleiss_kappa(eta),
            )

        # Same items, same analyst verdicts, only the placeholder markers differ.
        a = _kappas(["good", "bad", "abstain"])
        b = _kappas(["contested", "contested", "contested"])
        assert a == b
