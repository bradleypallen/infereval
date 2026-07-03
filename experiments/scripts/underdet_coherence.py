"""Underdetermination-clause R-cell — can the coherence form's abstain channel function?

The anchored-coherence cell (2026-07-02) rescued the bilateral question's
rendering-robustness but produced 0 UNCLEAR in 840 samples: the frame's UNCLEAR
gloss ("ill-formed or you cannot judge") licenses no *underdetermined* verdict,
so abstain-designed items were forced substantive. This cell tests the flagged
design change: ``defeasible-coherence-underdet-v1`` is byte-identical to
``defeasible-coherence-explicit-v1`` except (a) the UNCLEAR gloss adds an
explicit underdetermination clause (commitments bear on the denial but neither
settle nor defeat it; competent reasoners could disagree) and (b) a third
exemplar (unusually-heavy bird -> UNCLEAR) parallel to the existing two.
Question line, labels, parse regex, and decode remain the library's.

Cells (one batch, temp 0, seed 7, 6 samples/item):

    AC1b  explicit-v1 / plain      — cross-batch drift anchor (expect ~AC1 = 24/11/0)
    UD1   underdet-v1 / plain
    UD3   underdet-v1 / situational
    UD4   underdet-v1 / epistemic   (the hedging stress cell)
    UD2   underdet-v1 / domain      (ClinicalTemplate)

Read-outs against the 2026-07-02 anchored row (24/23/23/25 good, 0 abstain):
(1) do UNCLEAR verdicts appear at all; (2) do abstains land on the
contested/abstain-designed items (reported here stratified by the public
``variation`` typology; construction-expectation discussion belongs to the
analysis, per the placeholder firewall); (3) does the rendering-flatness
survive, or does the new clause open an R4-style hedging floodgate under the
epistemic rendering; (4) do the consensus-bad core and the restored goods stay
put — i.e. does UNCLEAR take territory only from the genuinely contested
middle?

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/underdet_coherence.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --out experiments/results/clinical_pilot/underdet_coherence_2026-07-03
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
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
)
from infereval.providers import get_provider
from infereval.providers.base import ProviderSampleError, SampleRequest
from infereval.templates import DefaultTemplate, VerdictRequest, arity_of, coherence_decode
from infereval.templates_clinical import ClinicalTemplate
from infereval.types import Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"
RESULTS_ROOT = REPO_ROOT / "experiments" / "results" / "clinical_pilot"

sys.path.insert(0, str(Path(__file__).parent))
from anchored_coherence import (  # noqa: E402
    _COHERENCE_PATTERN,
    ANCHORED_COHERENCE_SYSTEM,
    ANCHORED_COHERENCE_SYSTEM_ID,
    COHERENCE_QUESTION,
    _import_generic_templates,
    _single_succedent,
)

UNDERDET_SYSTEM_ID = "defeasible-coherence-underdet-v1"
# Byte-identical to defeasible-coherence-explicit-v1 EXCEPT: the UNCLEAR gloss
# gains the underdetermination clause, and a third exemplar is appended. The
# smoke test asserts the shared prefix so the manipulation stays surgical.
UNDERDET_SYSTEM = (
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
    "UNCLEAR means the question is ill-formed or you cannot judge — or the "
    "matter is genuinely underdetermined: the commitments bear on what the "
    "position denies but neither ordinarily settle it nor defeat it, so "
    "competent reasoners could disagree about whether the position holds "
    "together.\n\n"
    "For example:\n"
    "  Consider a position that commits to the following: a is a bird; and "
    "denies: a can fly.\n"
    "  Verdict: INCOHERENT  (typical birds fly; absent further information, the "
    "denial clashes with what the commitment ordinarily settles)\n\n"
    "  Consider a position that commits to the following: a is a bird and a is "
    "a penguin; and denies: a can fly.\n"
    "  Verdict: COHERENT  (the second commitment is a defeater; the position "
    "holds together)\n\n"
    "  Consider a position that commits to the following: a is a bird and a is "
    "unusually heavy for its kind; and denies: a can fly.\n"
    "  Verdict: UNCLEAR  (the commitments pull in different directions without "
    "settling the matter; competent reasoners could disagree)"
)


def run_coherence_cell(provider, bench, params, template, n_samples, model_info,
                       label, system_id, system_text, log_path):
    """Elicit the coherence question under the given system; return an Evaluation."""
    premise_builder, _ = resolve_context_builders(bench.context_builders)
    items: list[EvaluationItem] = []
    with log_path.open("w") as log:
        log.write(json.dumps({
            "event": "cell.started", "label": label, "template_id": template.id,
            "system_id": system_id, "system": system_text,
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
                            system=system_text,
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


def _by_variation(eta: Evaluation, bench: Benchmark) -> dict:
    """Verdict counts stratified by the public variation typology."""
    variation = {it.id: (it.variation or "-") for it in bench.items}
    strata: dict[str, Counter] = defaultdict(Counter)
    for it in eta.items:
        strata[variation[it.id]][it.model_verdict.value] += 1
    return {k: dict(v) for k, v in sorted(strata.items())}


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
    p.add_argument("--anchored-dir", type=Path,
                   default=RESULTS_ROOT / "anchored_coherence_2026-07-02",
                   help="dir with the 2026-07-02 AC1/AC3/AC4/AC2 etas")
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

    from infereval.evaluation import ModelInfo
    model_info = ModelInfo(provider=args.provider, model_id=args.model, params=params)

    cells: dict[str, Evaluation] = {}
    plan = [
        # Cross-batch drift anchor: yesterday's AC1 cell, identical machinery.
        ("AC1b-anchoredcoherence-plain-anchorrun", DefaultTemplate(),
         ANCHORED_COHERENCE_SYSTEM_ID, ANCHORED_COHERENCE_SYSTEM),
        ("UD1-underdetcoherence-plain", DefaultTemplate(), UNDERDET_SYSTEM_ID, UNDERDET_SYSTEM),
        ("UD3-underdetcoherence-situational", situational, UNDERDET_SYSTEM_ID, UNDERDET_SYSTEM),
        ("UD4-underdetcoherence-epistemic", epistemic, UNDERDET_SYSTEM_ID, UNDERDET_SYSTEM),
        ("UD2-underdetcoherence-domain", ClinicalTemplate(), UNDERDET_SYSTEM_ID, UNDERDET_SYSTEM),
    ]
    for label, tmpl, sys_id, sys_text in plan:
        print(f"  running {label} ...", flush=True)
        eta = run_coherence_cell(provider, bench, params, tmpl, args.n_samples,
                                 model_info, label, sys_id, sys_text,
                                 args.out / f"{label}.jsonl")
        eta.dump(args.out / f"{label}-eta.json")
        cells[label] = eta

    # Yesterday's anchored (explicit-v1) reference etas.
    ac_refs = {
        "AC1": Evaluation.load(args.anchored_dir / "AC1-anchoredcoherence-plain-eta.json"),
        "AC3": Evaluation.load(args.anchored_dir / "AC3-anchoredcoherence-situational-eta.json"),
        "AC4": Evaluation.load(args.anchored_dir / "AC4-anchoredcoherence-epistemic-eta.json"),
        "AC2": Evaluation.load(args.anchored_dir / "AC2-anchoredcoherence-domain-eta.json"),
    }
    ac1b = cells["AC1b-anchoredcoherence-plain-anchorrun"]
    ud1 = cells["UD1-underdetcoherence-plain"]
    ud3 = cells["UD3-underdetcoherence-situational"]
    ud4 = cells["UD4-underdetcoherence-epistemic"]
    ud2 = cells["UD2-underdetcoherence-domain"]

    comparisons = {
        "AC1b_to_AC1_drift_anchor": compare_runs(ac1b, ac_refs["AC1"]),
        "UD1_to_AC1b_gloss_effect_at_plain": compare_runs(ud1, ac1b),
        "UD3_to_AC3_gloss_effect_at_situational": compare_runs(ud3, ac_refs["AC3"]),
        "UD4_to_AC4_gloss_effect_at_epistemic": compare_runs(ud4, ac_refs["AC4"]),
        "UD2_to_AC2_gloss_effect_at_domain": compare_runs(ud2, ac_refs["AC2"]),
        "UD1_to_UD3_slope": compare_runs(ud1, ud3),
        "UD1_to_UD4_slope": compare_runs(ud1, ud4),
        "UD1_to_UD2_slope": compare_runs(ud1, ud2),
    }

    summary = {
        "model": args.model, "n_samples": args.n_samples,
        "underdet_system_id": UNDERDET_SYSTEM_ID,
        "underdet_system": UNDERDET_SYSTEM,
        "anchor_system_id": ANCHORED_COHERENCE_SYSTEM_ID,
        "cells": {label: {**_mix(eta),
                          "by_variation": _by_variation(eta, bench),
                          "abstain_items": sorted(i.id for i in eta.items
                                                  if i.model_verdict == Verdict.ABSTAIN),
                          "verdicts": {i.id: i.model_verdict.value for i in eta.items}}
                  for label, eta in cells.items()},
        "anchored_reference_mixes": {k: _mix(v) for k, v in ac_refs.items()},
        "comparisons": {k: _cmp(c) for k, c in comparisons.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    print("\n=== verdict mixes (of 35) ===")
    for label in summary["cells"]:
        c = summary["cells"][label]
        print(f"  {label:44s} good={c['good']} bad={c['bad']} abstain={c['abstain']}"
              f"  abstains={c['abstain_items']}")
    print("  [anchored explicit-v1 reference] plain/sit/epi/domain good: "
          f"{_mix(ac_refs['AC1'])['good']} / {_mix(ac_refs['AC3'])['good']} / "
          f"{_mix(ac_refs['AC4'])['good']} / {_mix(ac_refs['AC2'])['good']} (0 abstain)")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
