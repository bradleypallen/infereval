"""Anchored-coherence-frame R-cell — does practice selection rescue the bilateral question?

The frame x rendering factorial and the generic-frame completion cell showed that
on the SUPPORT form, an explicit statement of the assessment's norms in the
system prompt (defeasibility, absent-further-information, defeat semantics)
near-fully protects the material reading against practice-stripping renderings,
domain-generally. The COHERENCE form was never tested under such a frame: every
coherence run this cycle (R1/R2/R3/R4/R5-anchor) ran under the library's thin
``_COHERENCE_SYSTEM``, which states the label contract but no material norms —
and collapsed R1 22 -> R3 15 -> R4 7 (good, of 35) as the rendering stripped
practice away.

This run swaps ONLY the system prompt: ``defeasible-coherence-explicit-v1``
mirrors ``defeasible-explicit-v1`` (NOT-strict-consistency framing, defeater
semantics, bird/penguin example transposed to commit/deny), while the question
line, labels, parse regex, and INCOHERENT->good decode stay byte-identical to
the library's coherence path. Cells (one batch, temp 0, seed 7, 6 samples/item):

    R1d  thin coherence / plain      — cross-batch drift anchor (expect ~R1/R1b = 22)
    AC1  anchored coherence / plain
    AC3  anchored coherence / situational   (mirrors R3)
    AC4  anchored coherence / epistemic     (mirrors R4)
    AC2  anchored coherence / domain        (mirrors R2, ClinicalTemplate)

Read-out against the thin-coherence gradient (22/15/7, domain 24): if the AC row
is flat near the analyst row, the practice-selection result is question-form
general and the v0.18.0 coherence default is safe under an anchored frame. If AC
still collapses under generic renderings, the bilateral question is fragile even
with explicit norms — a finding that bears directly on the coherence default.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/anchored_coherence.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --out experiments/results/clinical_pilot/anchored_coherence_2026-07-02
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from infereval.benchmark import Benchmark
from infereval.comparison import compare_runs
from infereval.context import resolve_context_builders, strip_tex_math
from infereval.endorsement import majority_vote
from infereval.evaluation import (
    EndorsementConfig,
    Evaluation,
    EvaluationItem,
    ProviderParams,
    SampleRecord,
    evaluate,
)
from infereval.providers import get_provider
from infereval.providers.base import ProviderSampleError, SampleRequest
from infereval.templates import DefaultTemplate, VerdictRequest, arity_of, coherence_decode
from infereval.templates_clinical import ClinicalTemplate
from infereval.types import Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"
RESULTS_ROOT = REPO_ROOT / "experiments" / "results" / "clinical_pilot"

ANCHORED_COHERENCE_SYSTEM_ID = "defeasible-coherence-explicit-v1"
# Mirrors defeasible-explicit-v1 (support form) clause-for-clause, transposed to
# the bilateral commit/deny question. Question line, labels, and decode are the
# library's, byte-identical — the system prompt is the ONLY manipulated variable
# against the thin-coherence cells.
ANCHORED_COHERENCE_SYSTEM = (
    "You are judging whether a position is coherent in everyday defeasible "
    "reasoning. A position commits to some claims and may deny others.\n\n"
    "This is NOT a question of strict logical consistency. It is a question of "
    "material coherence: granting the commitments as stated, with typical "
    "background conditions and standard kinds, can the whole position be held "
    "together in the ordinary course of things?\n\n"
    "Answer with exactly one of: COHERENT, INCOHERENT, UNCLEAR. No other text.\n\n"
    "COHERENT means the whole position can be held together under default "
    "conditions — including when a commitment defeats what would otherwise "
    "ordinarily follow.\n"
    "INCOHERENT means the position is untenable: it denies something its "
    "commitments would ordinarily settle, or its commitments cannot all hold "
    "together in the ordinary course of things. A strict logical contradiction "
    "is not required.\n"
    "UNCLEAR means the question is ill-formed or you cannot judge.\n\n"
    "For example:\n"
    "  Consider a position that commits to the following: a is a bird; and "
    "denies: a can fly.\n"
    "  Verdict: INCOHERENT  (typical birds fly; absent further information, the "
    "denial clashes with what the commitment ordinarily settles)\n\n"
    "  Consider a position that commits to the following: a is a bird and a is "
    "a penguin; and denies: a can fly.\n"
    "  Verdict: COHERENT  (the second commitment is a defeater; the position "
    "holds together)"
)
COHERENCE_QUESTION = "Is this position coherent? Answer COHERENT, INCOHERENT, or UNCLEAR."
# Byte-identical to templates._COHERENCE_PARSE (INCOHERENT first so the
# alternation never matches the COHERENT substring of it).
_COHERENCE_PATTERN = re.compile(r"\b(INCOHERENT|COHERENT|UNCLEAR)\b", re.IGNORECASE)


def _import_generic_templates():
    sys.path.insert(0, str(Path(__file__).parent))
    from r3_situational import SituationalTemplate
    from r4_epistemic import EpistemicTemplate

    return SituationalTemplate(), EpistemicTemplate()


def _single_succedent(benchmark: Benchmark) -> Benchmark:
    items = [it for it in benchmark.items if len(it.conclusions) == 1]
    return benchmark.model_copy(update={"items": items})


def run_anchored_cell(provider, bench, params, template, n_samples, model_info, label, log_path):
    """Elicit the coherence question under the anchored system; return an Evaluation.

    Same hand-built shape as the R5 normative cells; additionally writes a
    per-sample jsonl log for post-run analysis (raw responses also live in the
    eta's SampleRecords).
    """
    premise_builder, _ = resolve_context_builders(bench.context_builders)
    items: list[EvaluationItem] = []
    with log_path.open("w") as log:
        log.write(json.dumps({
            "event": "cell.started", "label": label, "template_id": template.id,
            "system_id": ANCHORED_COHERENCE_SYSTEM_ID, "system": ANCHORED_COHERENCE_SYSTEM,
            "question": COHERENCE_QUESTION, "n_samples": n_samples,
            "model": model_info.model_id,
        }) + "\n")
        for it in bench.items:
            prem = [strip_tex_math(bench.bearer(b).expression).strip() for b in sorted(it.premises)]
            concl = [strip_tex_math(bench.bearer(b).expression).strip() for b in sorted(it.conclusions)]
            req = VerdictRequest(
                arity=arity_of(sorted(it.conclusions)),
                gamma_ctx=premise_builder(prem),
                delta_ctx=tuple(concl),
            )
            user = f"{template.render(req)}\n{COHERENCE_QUESTION}"
            samples: list[SampleRecord] = []
            for i in range(n_samples):
                try:
                    res = provider.sample(
                        SampleRequest(
                            prompt=user,
                            system=ANCHORED_COHERENCE_SYSTEM,
                            temperature=params.temperature,
                            max_tokens=params.max_tokens,
                            top_p=params.top_p,
                            seed=params.seed,
                            request_id=f"{label}:{it.id}:s{i}",
                        )
                    )
                    verdict, status = coherence_decode(res.text, _COHERENCE_PATTERN, req)
                    samples.append(SampleRecord(sample_index=i, raw_response=res.text,
                                                parsed_verdict=verdict, parse_status=status,
                                                finish_reason=res.finish_reason))
                    log.write(json.dumps({
                        "event": "sample", "label": label, "item": it.id, "sample": i,
                        "user": user, "raw": res.text, "verdict": verdict.value,
                        "status": status,
                    }) + "\n")
                except ProviderSampleError as exc:
                    samples.append(SampleRecord(sample_index=i, raw_response="",
                                                parsed_verdict=Verdict.ABSTAIN,
                                                parse_status="sample_failed",
                                                provider_error=str(exc)))
                    log.write(json.dumps({
                        "event": "sample_failed", "label": label, "item": it.id,
                        "sample": i, "error": str(exc),
                    }) + "\n")
            voting = [s.parsed_verdict for s in samples if s.provider_error is None]
            final, _tb = majority_vote(voting, tie_break="abstain")
            items.append(EvaluationItem(
                id=it.id, premises=sorted(it.premises), conclusions=sorted(it.conclusions),
                analyst_verdicts=list(it.analyst_verdicts), model_verdict=final, samples=samples,
            ))
            log.write(json.dumps({
                "event": "item.finished", "label": label, "item": it.id,
                "verdict": final.value,
            }) + "\n")
    return Evaluation(
        id=f"{model_info.model_id}:{label}", benchmark_id=bench.id, model=model_info,
        endorsement_config=EndorsementConfig(n_samples=n_samples, question_form="coherence"),
        items=items,
    )


def _mix(eta: Evaluation) -> dict:
    c = Counter(it.model_verdict.value for it in eta.items)
    return {"good": c.get("good", 0), "bad": c.get("bad", 0), "abstain": c.get("abstain", 0)}


def _cmp(c) -> dict:
    return {"cross_run_kappa": c.cross_run_kappa, "mean_tv_distance": c.mean_tv_distance,
            "n_both_substantive": c.n_both_substantive,
            "coverage_a": c.coverage_a, "coverage_b": c.coverage_b,
            "insufficient_overlap": c.insufficient_overlap}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", required=True, choices=["anthropic", "openai", "openrouter"])
    p.add_argument("--model", required=True)
    p.add_argument("--key-env", required=True)
    p.add_argument("--n-samples", type=int, default=6)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=16)
    p.add_argument("--results-root", type=Path, default=RESULTS_ROOT,
                   help="root holding the r0r1r2 / r3_situational / r4_epistemic result dirs")
    args = p.parse_args()

    api_key = os.environ.get(args.key_env)
    if not api_key:
        print(f"ERROR: {args.key_env} is not set.", file=sys.stderr)
        return 1

    provider = get_provider(args.provider, args.model, api_key=api_key)
    bench = _single_succedent(Benchmark.load(BENCHMARK))
    params = ProviderParams(temperature=0.0, max_tokens=args.max_tokens, seed=7)
    args.out.mkdir(parents=True, exist_ok=True)
    situational, epistemic = _import_generic_templates()

    # Thin-coherence drift anchor via the standard library path (same-setup
    # re-run of R1/R1b/R1c — the fourth capture of this cell today).
    print("  running R1d-coherence-plain (thin drift anchor) ...", flush=True)
    r1d = evaluate(bench, provider,
                   config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
                   params=params, template=DefaultTemplate(),
                   run_id=f"{args.model}:R1d-coherence-plain",
                   log_path=args.out / "R1d-coherence-plain.jsonl")
    r1d.dump(args.out / "R1d-coherence-plain-eta.json")
    model_info = r1d.model

    anchored = {}
    for label, tmpl in (("AC1-anchoredcoherence-plain", DefaultTemplate()),
                        ("AC3-anchoredcoherence-situational", situational),
                        ("AC4-anchoredcoherence-epistemic", epistemic),
                        ("AC2-anchoredcoherence-domain", ClinicalTemplate())):
        print(f"  running {label} ...", flush=True)
        eta = run_anchored_cell(provider, bench, params, tmpl, args.n_samples,
                                model_info, label, args.out / f"{label}.jsonl")
        eta.dump(args.out / f"{label}-eta.json")
        anchored[label] = eta

    # Thin-coherence reference cells from the earlier same-day captures.
    refs = {
        "R1-thin-plain": Evaluation.load(
            args.results_root / "r0r1r2_2026-07-02" / "R1-coherence-plain-eta.json"),
        "R2-thin-domain": Evaluation.load(
            args.results_root / "r0r1r2_2026-07-02" / "R2-coherence-domain-eta.json"),
        "R1b-thin-plain": Evaluation.load(
            args.results_root / "r3_situational_2026-07-02" / "R1b-coherence-plain-eta.json"),
        "R3-thin-situational": Evaluation.load(
            args.results_root / "r3_situational_2026-07-02" / "R3-coherence-situational-eta.json"),
        "R4-thin-epistemic": Evaluation.load(
            args.results_root / "r4_epistemic_2026-07-02" / "R4-coherence-epistemic-eta.json"),
    }
    ac1 = anchored["AC1-anchoredcoherence-plain"]
    ac3 = anchored["AC3-anchoredcoherence-situational"]
    ac4 = anchored["AC4-anchoredcoherence-epistemic"]
    ac2 = anchored["AC2-anchoredcoherence-domain"]

    comparisons = {
        "R1d_to_R1b_drift_anchor": compare_runs(r1d, refs["R1b-thin-plain"]),
        "AC1_to_R1d_frame_effect_at_plain": compare_runs(ac1, r1d),
        "AC3_to_R3_frame_effect_at_situational": compare_runs(ac3, refs["R3-thin-situational"]),
        "AC4_to_R4_frame_effect_at_epistemic": compare_runs(ac4, refs["R4-thin-epistemic"]),
        "AC2_to_R2_frame_effect_at_domain": compare_runs(ac2, refs["R2-thin-domain"]),
        "AC1_to_AC3_anchored_situational_slope": compare_runs(ac1, ac3),
        "AC1_to_AC4_anchored_epistemic_slope": compare_runs(ac1, ac4),
        "AC1_to_AC2_anchored_domain_slope": compare_runs(ac1, ac2),
    }

    # No analyst reference row: the clinical panel's verdicts are pending (the
    # benchmark carries a single all-abstain placeholder slot), so the read-out
    # is cross-frame/rendering agreement, as in the factorial.
    summary = {
        "model": args.model, "n_samples": args.n_samples,
        "anchored_system_id": ANCHORED_COHERENCE_SYSTEM_ID,
        "anchored_system": ANCHORED_COHERENCE_SYSTEM,
        "cells": {
            "R1d-coherence-plain": {**_mix(r1d), "verdicts": {
                it.id: it.model_verdict.value for it in r1d.items}},
            **{label: {**_mix(eta), "verdicts": {
                it.id: it.model_verdict.value for it in eta.items}}
               for label, eta in anchored.items()},
        },
        "thin_reference_mixes": {k: _mix(v) for k, v in refs.items()},
        "comparisons": {k: _cmp(c) for k, c in comparisons.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== endorsement (good, of 35) ===")
    for label in summary["cells"]:
        c = summary["cells"][label]
        print(f"  {label:40s} good={c['good']} bad={c['bad']} abstain={c['abstain']}")
    print("  [thin reference] plain/situational/epistemic/domain: "
          f"{_mix(refs['R1-thin-plain'])['good']} / "
          f"{_mix(refs['R3-thin-situational'])['good']} / "
          f"{_mix(refs['R4-thin-epistemic'])['good']} / "
          f"{_mix(refs['R2-thin-domain'])['good']}")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
