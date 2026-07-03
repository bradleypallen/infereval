"""R5: the normative-frame cell — does the bilateral CONCEPT drift, or just the word "coherent"?

R3/R4 showed the coherence question drifting from a material to a logical
reading under generic renderings, with the "coherent / without conflict" lexicon
implicated as a consistency-attractor. This cell isolates concept from lexeme:
keep the bilateral commit/deny structure and the three renderings, but replace
the coherence frame (system prompt + question line + labels) with a **normative**
one — Restall/Brandom "out of bounds" / entitlement vocabulary, zero consistency
lexicon:

    system: "... judging whether a position is out of bounds by the standards of
             competent reasoning ... Answer OUT-OF-BOUNDS, PERMISSIBLE, or UNCLEAR ..."
    decode: OUT-OF-BOUNDS -> good  (may not deny psi given Gamma; the inference holds)
            PERMISSIBLE   -> bad   (may hold the position; the inference fails)
            UNCLEAR       -> abstain

This is the SAME polarity as coherence's INCOHERENT->good (an out-of-bounds
position is an incoherent one), so a divergence between the two frames is about
the framing lexicon, not the mapping.

Four cells, one pinned session:

    R1c  coherence / plain     — same-batch drift anchor for the coherence frame
    N1   normative / plain      — mirrors R1b
    N3   normative / situational — mirrors R3
    N4   normative / epistemic   — mirrors R4

Read-out: if the normative curve N1->N3->N4 is FLAT where the coherence curve
R1b->R3->R4 collapsed, the lability was the word; the bilateral concept, normatively
framed, is robust. If N also collapses, the bilateral concept itself is labile.

Renderings are imported from the R0/R1/R2 and R3/R4 scripts so the scaffolding is
byte-identical; only the frame differs. The normative cells are elicited directly
(the coherence question form is fixed in the library); their eta files record
endorsement_config.question_form="coherence" as a family marker — the run_id and
this script identify them as the normative-lexicon variant.

Usage::

    set -a; source /path/to/.env; set +a
    python experiments/scripts/r5_normative.py \
        --provider openai --model gpt-4.1 --key-env OPENAI_API_KEY \
        --n-samples 6 --r3dir experiments/results/clinical_pilot/r3_situational_2026-07-02 \
        --out experiments/results/clinical_pilot/r5_normative_2026-07-02
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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
from infereval.templates import DefaultTemplate, VerdictRequest, arity_of
from infereval.types import ParseStatus, Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = REPO_ROOT / "examples" / "clinical_pilot" / "benchmark.json"

# The normative bilateral frame — deontic / entitlement vocabulary, no
# "coherent / consistent / conflict" anywhere.
NORMATIVE_SYSTEM = (
    "You are judging whether a position is out of bounds by the standards of "
    "competent reasoning in the relevant field. A position takes on some "
    "commitments and rejects some claims. Answer with exactly one of: "
    "OUT-OF-BOUNDS, PERMISSIBLE, UNCLEAR. No other text.\n\n"
    "PERMISSIBLE means a competent reasoner is entitled to take up this whole "
    "position — to hold the commitments while rejecting what it rejects.\n"
    "OUT-OF-BOUNDS means a competent reasoner is not so entitled: taking on "
    "those commitments rules out rejecting what is rejected.\n"
    "UNCLEAR means the question is ill-formed or you cannot judge."
)
NORMATIVE_QUESTION = (
    "May a competent reasoner take up this position, or is it out of bounds? "
    "Answer OUT-OF-BOUNDS, PERMISSIBLE, or UNCLEAR."
)
_OUT = re.compile(r"out[\s_-]?of[\s_-]?bounds|forbidden|impermissible", re.IGNORECASE)
_PERM = re.compile(r"permissible|permitted|allowed|in[\s_-]?bounds", re.IGNORECASE)
_UNCLEAR = re.compile(r"unclear", re.IGNORECASE)


def _normative_decode(text: str) -> tuple[Verdict, ParseStatus]:
    # Order matters: "impermissible" must be caught by _OUT before _PERM's
    # "permissible" substring; _OUT is checked first.
    if _OUT.search(text):
        return Verdict.GOOD, "ok"
    if _PERM.search(text):
        return Verdict.BAD, "ok"
    if _UNCLEAR.search(text):
        return Verdict.ABSTAIN, "ok"
    return Verdict.ABSTAIN, "unparseable"


def _import_generic_templates():
    sys.path.insert(0, str(Path(__file__).parent))
    from r3_situational import SituationalTemplate
    from r4_epistemic import EpistemicTemplate

    return SituationalTemplate(), EpistemicTemplate()


def _single_succedent(benchmark: Benchmark) -> Benchmark:
    items = [it for it in benchmark.items if len(it.conclusions) == 1]
    return benchmark.model_copy(update={"items": items})


def run_normative_cell(provider, bench, params, template, n_samples, model_info, label):
    """Elicit the normative bilateral question directly, return an Evaluation."""
    premise_builder, _ = resolve_context_builders(bench.context_builders)
    items: list[EvaluationItem] = []
    for it in bench.items:
        prem = [strip_tex_math(bench.bearer(b).expression).strip() for b in sorted(it.premises)]
        concl = [strip_tex_math(bench.bearer(b).expression).strip() for b in sorted(it.conclusions)]
        req = VerdictRequest(
            arity=arity_of(sorted(it.conclusions)),
            gamma_ctx=premise_builder(prem),
            delta_ctx=tuple(concl),
        )
        user = f"{template.render(req)}\n{NORMATIVE_QUESTION}"
        samples: list[SampleRecord] = []
        verdicts: list[Verdict] = []
        for i in range(n_samples):
            try:
                res = provider.sample(
                    SampleRequest(
                        prompt=user,
                        system=NORMATIVE_SYSTEM,
                        temperature=params.temperature,
                        max_tokens=params.max_tokens,
                        top_p=params.top_p,
                        seed=params.seed,
                        request_id=f"{label}:{it.id}:s{i}",
                    )
                )
                verdict, status = _normative_decode(res.text)
                samples.append(SampleRecord(sample_index=i, raw_response=res.text,
                                            parsed_verdict=verdict, parse_status=status,
                                            finish_reason=res.finish_reason))
                verdicts.append(verdict)
            except ProviderSampleError as exc:
                samples.append(SampleRecord(sample_index=i, raw_response="",
                                            parsed_verdict=Verdict.ABSTAIN,
                                            parse_status="sample_failed", provider_error=str(exc)))
        voting = [s.parsed_verdict for s in samples if s.provider_error is None]
        final, _tb = majority_vote(voting, tie_break="abstain")
        items.append(EvaluationItem(
            id=it.id, premises=sorted(it.premises), conclusions=sorted(it.conclusions),
            analyst_verdicts=list(it.analyst_verdicts), model_verdict=final, samples=samples,
        ))
    return Evaluation(
        id=f"{model_info.model_id}:{label}", benchmark_id=bench.id, model=model_info,
        endorsement_config=EndorsementConfig(n_samples=n_samples, question_form="coherence"),
        items=items,
    )


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
    p.add_argument("--r3dir", type=Path, required=True, help="dir with R1b/R3/R4 etas")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-tokens", type=int, default=16)
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

    # Same-batch coherence-plain drift anchor via the standard path.
    print("  running R1c-coherence-plain (drift anchor) ...", flush=True)
    r1c = evaluate(bench, provider,
                   config=EndorsementConfig(n_samples=args.n_samples, question_form="coherence"),
                   params=params, template=DefaultTemplate(),
                   run_id=f"{args.model}:R1c-coherence-plain",
                   log_path=args.out / "R1c-coherence-plain.jsonl")
    r1c.dump(args.out / "R1c-coherence-plain-eta.json")
    model_info = r1c.model

    normative = {}
    for label, tmpl in (("N1-normative-plain", DefaultTemplate()),
                        ("N3-normative-situational", situational),
                        ("N4-normative-epistemic", epistemic)):
        print(f"  running {label} ...", flush=True)
        eta = run_normative_cell(provider, bench, params, tmpl, args.n_samples, model_info, label)
        eta.dump(args.out / f"{label}-eta.json")
        normative[label] = eta

    r1b = Evaluation.load(args.r3dir / "R1b-coherence-plain-eta.json")
    r3 = Evaluation.load(args.r3dir / "R3-coherence-situational-eta.json")
    r4 = Evaluation.load(args.r3dir / "R4-coherence-epistemic-eta.json")
    n1, n3, n4 = normative["N1-normative-plain"], normative["N3-normative-situational"], normative["N4-normative-epistemic"]

    comparisons = {
        "R1c_to_R1b_drift_anchor": compare_runs(r1c, r1b),
        "N1_to_R1c_frame_effect_at_plain": compare_runs(n1, r1c),
        "N1_to_N3_normative_situational_slope": compare_runs(n1, n3),
        "N1_to_N4_normative_epistemic_slope": compare_runs(n1, n4),
        "N3_to_R3_frame_effect_at_situational": compare_runs(n3, r3),
        "N4_to_R4_frame_effect_at_epistemic": compare_runs(n4, r4),
    }
    summary = {
        "model": args.model, "n_samples": args.n_samples,
        "coherence_curve_reference": {"R1b_good": 22, "R3_good": 15, "R4_good": 7},
        "comparisons": {k: _cmp(c) for k, c in comparisons.items()},
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary["comparisons"], indent=2))
    print(f"Wrote etas + summary to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
