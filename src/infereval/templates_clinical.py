"""Clinical-idiom domain template for the clinical pilot benchmark (brief §5, §8).

Promoted from the R0/R1/R2 experiment harness
(``experiments/scripts/r0r1r2_clinical.py``) after the 2026-07-02 clinical
pilot capture: under the patient-framed rendering the coherence question
recovered 4 of 5 question-form verdict flips and lifted coverage to 1.00
relative to the plain framework template (see
``experiments/results/clinical_pilot/r0r1r2_2026-07-02/analysis.md``,
Finding 2).

The rendered wording is byte-identical to the harness template used in that
capture and the template id is unchanged (``clinical-coherence-v1``), so etas
recorded against either copy carry the same provenance. Any change to the
wording is a new instrument: mint a new id and gate it through
:func:`infereval.guards.template_equivalence` (brief §8) rather than editing
in place.

The clinical pilot benchmark binds this template declaratively via its
``template_id`` field (:attr:`infereval.benchmark.Benchmark.template_id`);
:func:`register` is the programmatic hook for binding it to a benchmark id
that doesn't declare the field.
"""

from __future__ import annotations

from dataclasses import dataclass

from .templates import VerdictRequest, register_template, register_template_id

__all__ = ["CLINICAL_PILOT_BENCHMARK_ID", "ClinicalTemplate", "register"]

#: The benchmark id the clinical pilot ships under (``examples/clinical_pilot``).
CLINICAL_PILOT_BENCHMARK_ID = "clinical-pilot-cpe-ards-v0.5"


@dataclass(frozen=True)
class ClinicalTemplate:
    """A clinical-idiom rendering of the bilateral position.

    Renders only content scaffolding — it never sees bearer ids — so it cannot
    re-smuggle the domain into the verdict layer. The coherence question form
    frames it with "Is this position coherent?".
    """

    id: str = "clinical-coherence-v1"

    def render(self, req: VerdictRequest) -> str:
        gamma = req.gamma_ctx
        if req.arity == 0:
            return (
                "Consider whether a single patient could present with all of the "
                f"following at the same moment: {gamma}."
            )
        if req.arity == 1:
            return (
                "Consider a patient for whom this clinical picture holds: "
                f"{gamma}. The position under evaluation further denies that "
                f"{req.delta_ctx[0]}."
            )
        joined = "; ".join(req.delta_ctx)
        return (
            "Consider a patient for whom this clinical picture holds: "
            f"{gamma}. The position denies every one of: {joined}."
        )


def register(benchmark_id: str = CLINICAL_PILOT_BENCHMARK_ID) -> ClinicalTemplate:
    """Programmatically bind the clinical template to ``benchmark_id``.

    The clinical pilot benchmark declares the binding itself (its
    ``template_id`` field), so calling this is only needed to attach the
    template to a benchmark that doesn't — e.g. a derived benchmark whose id
    differs. The returned instance is the one registered.
    """
    template = ClinicalTemplate()
    register_template(benchmark_id, template)
    return template


# Catalog on import so a benchmark-declared ``template_id:
# "clinical-coherence-v1"`` resolves (templates.template_for_id loads this
# module lazily on first lookup).
register_template_id(ClinicalTemplate())
