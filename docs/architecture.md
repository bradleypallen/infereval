# Architecture

A single dataflow diagram for the whole framework, plus a brief tour of
each component. The narrative version is in [Concepts](concepts.md);
this page is for readers who want to see the wiring at a glance.

## Dataflow

```mermaid
flowchart TB
    subgraph ANALYST["Analyst inputs"]
        A1["bearers B<br/>expression δ : B → L<br/>context builders ctx_Γ, ctx_Δ"]
        A2["items I_i = ⟨Γ_i, Δ_i⟩<br/>analyst verdicts V_i<br/>tags · rsr_target · factor_levels<br/>construction_metadata · analyst_rationales"]
    end

    A1 --> BENCH["benchmark.json (β)"]
    A2 --> BENCH

    BENCH -->|infereval validate| VAL["schema check"]
    BENCH -->|infereval describe| DESC["bearer dictionary, panel<br/>summary, tag freq, κ_F*(β),<br/>factor cells, provenance,<br/>verdict-by-tag-group cross-tab"]

    BENCH --> EVAL["infereval evaluate"]
    M["LLM under evaluation M"] -.->|"endorsement E_M (good/bad/abstain),<br/>majority-vote over n_samples"| EVAL
    EVAL --> ETA["evaluation.json (η)<br/>η = {(I_i, V_i, E_M(I_i))}"]
    EVAL --> LOG["run.jsonl<br/>per-sample audit log"]

    ETA --> METRICS["infereval metrics"]
    ETA --> STRUCT["infereval structure"]
    ETA --> MODEL["infereval model"]
    ETA --> SWEEP["infereval sweep"]

    METRICS --> MET_OUT["cov · κ_C · κ_F · κ_F*<br/>by-tag · by-rsr-target<br/>per-panel · cross-panel"]
    STRUCT --> STR_OUT["Containment<br/>RSR role consistency<br/>base-case stability"]
    MODEL --> MOD_OUT["per-factor Wald<br/>per-level coefficients<br/>pseudo-R²"]
    SWEEP --> SWP_OUT["κ_C range across<br/>swept parameter<br/>stability verdict"]

    CLAIMS["claims.json<br/>mastery_sense · scope · constitution<br/>carving · competing_explanations"] --> REPORT
    MET_OUT --> REPORT
    STR_OUT --> REPORT
    MOD_OUT --> REPORT
    SWP_OUT --> REPORT
    REPORT["infereval report"] --> RENDER["construct-validity report (Markdown)<br/>5-tier deterministic verdict"]
```

## Layer-by-layer tour

### Layer 1 — analyst inputs

Everything the framework consumes is **analyst-supplied**:

- **Bearers `B`**, an expression function `δ : B → L`, and context-construction
  functions `ctx_Γ`, `ctx_Δ`. Together they determine how implications get
  presented to the model. See the paper's Definition 1.
- **Items**, each a single-bearer-succedent implication `⟨Γ_i, {ψ_i}⟩`
  paired with a verdict tuple `V_i = (v_{i,1}, …, v_{i,m})` from the
  analyst panel. Optional richer metadata — tags, `rsr_target`,
  `factor_levels`, `construction_metadata`, `analyst_rationales` — feeds
  the construct-validity layer.

### Layer 2 — the benchmark `β`

`benchmark.json` packages the analyst inputs as a Pydantic-validated
artifact. Two entry points without ever calling a model:

- **`infereval validate`** — schema + cross-field validation. Pure check.
- **`infereval describe`** — comprehensive inspector: bearer dictionary,
  per-analyst verdict distribution, `κ_F*(β)` baseline (when defined),
  tag frequency, factorial-design coverage, paraphrase-variant count,
  per-panel summaries, construction-provenance roll-up, and the
  verdict-by-tag-group cross-tab. Run it first on any new benchmark.

### Layer 3 — evaluate `M` on `β`

**`infereval evaluate`** drives the model `M` through every item,
sampling `n_samples` verdicts via a verification prompt and computing
`E_M` by majority vote (tie-break configurable; default `abstain`).
Outputs:

- **`η`** (`evaluation.json`) — the evaluation artifact: the benchmark's
  items plus `M`'s verdicts, with a tamper-evident `benchmark_hash` for
  integrity.
- **`run.jsonl`** — per-sample audit log: prompt hash, raw response,
  parsed verdict, usage, timing, finish reason, reasoning tokens. One
  event per provider call.

### Layer 4 — the four analytical commands

All four take `η` (and usually `β`) and emit JSON. They're designed to
compose: each addresses a distinct construct-validity axis, and the
report (layer 5) consumes all four together.

| Command | Question it answers | Output |
|---|---|---|
| `infereval metrics` | How well does `M` agree with the analysts? | `cov`, `κ_C`, `κ_F`, `κ_F*` + by-tag / by-rsr-target / per-panel / cross-panel decompositions |
| `infereval structure` | Does the derived frame ⟨B, I_M⟩ exhibit the structural properties the inferentialist framework treats as constitutive of mastery? | Containment check, RSR role consistency, base-case stability, per-item anomaly list |
| `infereval model` | Which declared `factors` actually differentiate `M`'s behaviour? | Logistic regression of per-sample agreement with item-clustered SEs; per-factor joint Wald + per-level coefficients |
| `infereval sweep` | Are the headline metrics robust to the framework parameters chosen? | Re-runs `metrics` across a swept parameter; reports a deterministic stability verdict on the `κ_C` range |

### Layer 5 — the construct-validity report

**`infereval report`** combines a `claims.json` file (the analyst's
explicit declarations about mastery sense, scope, constitution, carving,
and which competing-explanation checks were run) with the four analytical
artifacts above. It emits a Markdown report ending in a deterministic
five-tier verdict (`Strongly substantiated` → `Insufficient`) computed by
[`compute_verdict()`](api.md). The verdict consults the artifacts, not
just the self-report booleans — structural anomalies and `m<2` panels cap
the verdict at `partially_defensible` per the v0.5.3 audit-cap rules.

## What this diagram doesn't show

- **The Hlobil–Brandom layer** — `Definition 3` of the paper specifies
  `⟨B, I_M⟩` as the derived frame; the framework guarantees Containment
  by construction (clause i). RSR, ≈, implicational roles, conceptual
  content all live on top of `⟨B, I_M⟩` and aren't separately materialised
  in code (`DerivedFrame.contains()` is the lazy gateway).
- **Replay / mock providers** — `ReplayProvider` and `ScriptedProvider`
  occupy the `M` slot in the diagram for deterministic CI / quickstart;
  the structure is identical, only the provider differs.
- **The paraphrase axis** — `infereval evaluate --paraphrase-variant K`
  or `--paraphrase-cycle` re-runs the same benchmark with `δ` substituted
  per variant. Drops into the diagram at layer 3, producing per-variant
  `η` files that feed independent metrics / structure / model / sweep
  runs.

## Multi-succedent generalization (v0.17.x)

The v0.17.x series generalized the item to `⟨Γ, Δ⟩` at any arity and factored
elicitation into a `question_form` (support / coherence) composed with a
per-domain **template registry** (`templates.py`): one prompt,
`prompt = question_form.frame(template.render(req))`, with the measurement layer
(Definitions 6–10) untouched. It also added native v0.5-schema support
(`bearers.py`, `compiler.py`), monotonicity scoring (`monotonicity.py`),
cross-run comparison + validity guards (`comparison.py`, `guards.py`), and
question-form-aware surveys. The
[instrument validation walkthrough](instrument_validation.md) is the
reviewer-facing dossier tying all of this to the construct-validity argument;
the [reviewer checklist](reviewer_checklist.md) turns it into a referee's
yes/no list.
