"""Tests for the clinical pilot template + benchmark-level ``template_id`` binding.

Covers :mod:`infereval.templates_clinical` (the template promoted from the
R0/R1/R2 experiment harness after the 2026-07-02 clinical pilot capture) and
the resolution path that binds it: the template-id catalog in
:mod:`infereval.templates`, the :attr:`Benchmark.template_id` field, and the
two elicitation surfaces (``evaluate`` and the survey renderer) that honor it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from infereval import templates as templates_mod
from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ScriptedProvider
from infereval.survey.render import render_survey_question
from infereval.templates import (
    VerdictRequest,
    resolve_template,
    template_for_id,
)
from infereval.templates_clinical import (
    CLINICAL_PILOT_BENCHMARK_ID,
    ClinicalTemplate,
    register,
)
from infereval.types import Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
CLINICAL_PILOT_PATH = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"


def _req(arity, delta=()):
    return VerdictRequest(
        arity=arity, gamma_ctx="the clinical picture", delta_ctx=tuple(delta)
    )


class TestClinicalTemplate:
    def test_id_is_the_capture_id(self) -> None:
        assert ClinicalTemplate().id == "clinical-coherence-v1"

    def test_renders_each_arity(self) -> None:
        # Wording is frozen to the 2026-07-02 R2 capture — a change here is a
        # new instrument (new id + template_equivalence gate), not an edit.
        t = ClinicalTemplate()
        assert t.render(_req(0)) == (
            "Consider whether a single patient could present with all of the "
            "following at the same moment: the clinical picture."
        )
        assert t.render(_req(1, ["the patient has ARDS"])) == (
            "Consider a patient for whom this clinical picture holds: "
            "the clinical picture. The position under evaluation further "
            "denies that the patient has ARDS."
        )
        assert t.render(_req("many", ["A", "B"])) == (
            "Consider a patient for whom this clinical picture holds: "
            "the clinical picture. The position denies every one of: A; B."
        )

    def test_template_sees_no_bearer_ids(self) -> None:
        # Same invariant as DefaultTemplate: the template renders only
        # content scaffolding and cannot re-smuggle the domain into the
        # verdict layer.
        assert not hasattr(_req(1, ("d",)), "premises")


class TestCatalog:
    def test_clinical_template_is_catalogued(self) -> None:
        assert template_for_id("clinical-coherence-v1").id == "clinical-coherence-v1"

    def test_default_template_is_catalogued(self) -> None:
        assert template_for_id("framework-default-v1").id == "framework-default-v1"

    def test_unknown_id_fails_loudly(self) -> None:
        with pytest.raises(ValueError, match="unknown template_id"):
            template_for_id("no-such-template-v0")

    def test_builtin_loads_lazily_in_fresh_interpreter(self) -> None:
        # The benchmark-declared binding must resolve even when nothing has
        # imported infereval.templates_clinical — the import-order fragility
        # the catalog's lazy built-in load exists to prevent.
        code = (
            "from infereval.templates import template_for_id; "
            "print(template_for_id('clinical-coherence-v1').id)"
        )
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        assert out.stdout.strip() == "clinical-coherence-v1"


class TestResolutionPrecedence:
    def test_benchmark_declared_template_id_resolves(self, monkeypatch) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})
        t = resolve_template("some-benchmark", template_id="clinical-coherence-v1")
        assert isinstance(t, ClinicalTemplate)

    def test_programmatic_registration_overrides_declared_id(self, monkeypatch) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})

        class _Override:
            id = "override-v1"

            def render(self, req: VerdictRequest) -> str:
                return "override"

        templates_mod.register_template("some-benchmark", _Override())
        t = resolve_template("some-benchmark", template_id="clinical-coherence-v1")
        assert t.id == "override-v1"

    def test_no_binding_falls_back_to_default(self, monkeypatch) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})
        assert resolve_template("some-benchmark").id == "framework-default-v1"

    def test_unknown_declared_id_fails_loudly(self, monkeypatch) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})
        with pytest.raises(ValueError, match="unknown template_id"):
            resolve_template("some-benchmark", template_id="typo-v1")

    def test_register_hook_binds_the_pilot_benchmark_id(self, monkeypatch) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})
        registered = register()
        assert resolve_template(CLINICAL_PILOT_BENCHMARK_ID) is registered


class TestClinicalPilotBinding:
    """The shipped clinical pilot benchmark binds the template declaratively."""

    def test_example_benchmark_declares_the_binding(self) -> None:
        bench = Benchmark.load(CLINICAL_PILOT_PATH)
        assert bench.id == CLINICAL_PILOT_BENCHMARK_ID
        assert bench.template_id == "clinical-coherence-v1"

    def test_default_coherence_evaluation_uses_clinical_rendering(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})
        bench = Benchmark.load(CLINICAL_PILOT_PATH)
        bench = bench.model_copy(update={"items": bench.items[:1]})
        log_path = tmp_path / "run.jsonl"
        eta = evaluate(
            bench,
            ScriptedProvider(responses=["INCOHERENT"]),
            config=EndorsementConfig(n_samples=1, question_form="coherence"),
            run_id="clinical-binding-test",
            log_path=log_path,
        )
        assert eta.items[0].model_verdict == Verdict.GOOD
        events = [json.loads(line) for line in log_path.read_text().splitlines()]
        by_kind = {e["event"]: e for e in events}
        # §12.3 provenance: the resolved template id lands in run.started …
        assert by_kind["run.started"]["template_id"] == "clinical-coherence-v1"
        # … and the composed prompt carries the clinical rendering.
        assert (
            "Consider a patient for whom this clinical picture holds:"
            in by_kind["item.started"]["prompt"]
        )

    def test_survey_coherence_body_uses_clinical_rendering(self, monkeypatch) -> None:
        monkeypatch.setattr(templates_mod, "_REGISTRY", {})
        bench = Benchmark.load(CLINICAL_PILOT_PATH)
        q = render_survey_question(bench, bench.items[0], question_form="coherence")
        assert "Consider a patient for whom this clinical picture holds:" in q.body

    def test_benchmark_without_binding_keeps_default_template(self) -> None:
        stop_sign = Benchmark.load(REPO_ROOT / "examples" / "stop_sign" / "benchmark.json")
        assert stop_sign.template_id is None
        resolved = resolve_template(stop_sign.id, template_id=stop_sign.template_id)
        assert resolved.id == "framework-default-v1"
