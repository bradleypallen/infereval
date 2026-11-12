# Concepts

A pedagogical walk through what `infereval` does. The [Formal specification](formal_specification.md) states the definitions precisely, the [Glossary](glossary.md) collects the notation, and [Interpreting metrics](interpreting_metrics.md) goes deeper on what the numbers mean.

## The question

Given a large language model `M` and a domain (everyday physical objects, medical reasoning, contract law, classical logic — anything that admits expert labeling of inferential examples), we want to ask: **how well does `M` agree with expert practice when judging inferences in that domain?**

Not "how often does `M` get the right answer to factual questions" (that's standard factuality benchmarking, which `infereval` is not). Not "is `M` sapient" (philosophy). What we want is a measurable proxy for how well `M` participates in the same inferential practice as a labeling expert: when expert analysts say "yes, that's a good inference under default conditions" or "no, the premises don't support that conclusion", how often does `M` say the same thing?

The methodology gives you that proxy. It also gives you concrete instruments for asking why `M` disagrees when it does.

## A note on terminology

Two terms that *look* like they might mean the same thing but don't:

- **Item** (`BenchmarkItem`, `EvaluationItem`) — one *row* of the benchmark: an implication `⟨Γ, Δ⟩` paired with analyst verdicts. If your benchmark has 4 items, the analyst labeled 4 implications. This is the unit a supervised-ML reader would intuitively call a "sample" or "example"; `infereval` consistently calls it an **item**.

- **Sample** (`SampleRequest`, `SampleResult`, `SampleRecord`, the `n_samples` parameter) — one *completion drawn from the model*. The methodology samples `M`'s response to a verification prompt `n_samples` times per item (default `n_samples = 5`), parses each completion's verdict token, and majority-votes to compute `E_M`. This is the LLM-literature usage of "sample" — repeated draws from `M`'s output distribution for noise reduction, not rows of a dataset.

So a run with 4 items at `n_samples = 5` issues 20 sample calls total to the provider; the resulting `Evaluation` contains 4 `EvaluationItem`s, each of which contains a list of 5 `SampleRecord`s. Items and samples never collide once you have the vocabulary.

## The pieces, in order

### Bearers (`B`)

A **bearer** is a propositional content-bearer — informally, "a thing the model could affirm or deny", individuated by an English statement. Stop signs example:

| id | English |
|---|---|
| `sa` | a is a stop sign |
| `ra` | a is red |
| `n` | it is nighttime |
| `nr` | a is not made with reflective material |
| `ba` | a has been painted blue |

`B = {sa, ra, n, nr, ba}` is the **bearer set** for this benchmark. Bearers are the atoms the methodology reasons over.

The analyst picks the bearer set. There is no canonical "correct" set for a domain; you choose the granularity that captures the inferential structure you want to evaluate. This is the **carving** of the domain. The methodology is honest that carvings matter: different carvings give different evaluations.

### The expression function `δ` and contexts `ctx_Γ` / `ctx_Δ`

Bearers are abstract. To present them to an LLM, you need to translate them into natural language. Two layers:

- **δ : B → L** maps each bearer to its English sentence. This is `δ(sa) = "a is a stop sign"` above.
- **ctx_Γ** packages a *set* of premises into a single natural-language clause. The default is conjunction: `ctx_Γ({sa, n}) = "a is a stop sign and it is nighttime"`.
- **ctx_Δ** packages a *set* of conclusions. The default is disjunction: `ctx_Δ({ra}) = "a is red"`.

Both `ctx_Γ` and `ctx_Δ` are configurable per benchmark (template or Python-plugin). The defaults match the simplest choices Simonelli's dialogue uses.

### The endorsement function `E_M`

For each candidate inference `⟨Γ, Δ⟩` (a premise set `Γ` ⊆ B and a conclusion set `Δ` ⊆ B), the framework constructs a **verification prompt**:

```
[system] You are evaluating whether an inference from premises to a
[system] conclusion is good, bad, or whether you should abstain.
[system] Answer with exactly one of: GOOD, BAD, ABSTAIN. No other text.
[system] GOOD means the conclusion follows from the premises in everyday reasoning.
[system] BAD means the premises do not support the conclusion.
[system] ABSTAIN means the question is ill-formed or you cannot judge.

[user]   Premises: a is a stop sign and it is nighttime
[user]   Conclusion: a is red
[user]   Verdict:
```

`M` is sampled `n_samples` times at the configured temperature. Each response is parsed for the first `GOOD`/`BAD`/`ABSTAIN` token (case-insensitive). Unparseable responses become `abstain`. The `n_samples` per-sample verdicts are aggregated by **majority vote** with a configurable tie-break (default `abstain` — conservative).

The result is `E_M(⟨Γ, Δ⟩) ∈ {good, bad, abstain}`. That's the endorsement function — the methodology's link between the abstract inferential structure and the concrete model.

### The derived frame ⟨B, I_M⟩

Once you have `E_M`, the derived **implication frame** for `M` is the pair `⟨B, I_M⟩`, where `I_M` is the set of implications the model "lets through":

```
⟨Γ, Δ⟩ ∈ I_M  iff  Γ ∩ Δ ≠ ∅   (Containment, "clause i")
              or   E_M(⟨Γ, Δ⟩) = good  ("clause ii")

⟨∅, ∅⟩ ∉ I_M  (excluded by stipulation)
```

Two things to notice:

- **Containment is built in.** Any implication where the premise set and conclusion set share a bearer is in `I_M` for free, regardless of what `M` says. This makes `⟨B, I_M⟩` a well-formed implication frame in the Hlobil–Brandom sense from the start.
- **The frame is lazy.** The full `I_M ⊆ ℘(B) × ℘(B)` is exponential in `|B|` and the framework never materializes it. The `DerivedFrame` class lets you query membership for any particular `⟨Γ, Δ⟩` via the iff above.

`⟨B, I_M⟩` is the formal object the methodology builds. It's the analyst's window into `M`'s inferential behavior, in a form the Hlobil–Brandom machinery can act on.

### The benchmark `β`

A **benchmark** is the analyst's labeled dataset:

```
β = { (I_1, V_1), (I_2, V_2), ..., (I_n, V_n) }
```

Each `I_i = ⟨Γ_i, Δ_i⟩` is an implication. Each `V_i = (v_{i,1}, …, v_{i,m})` is a tuple of verdicts from `m` analysts (humans labeling the dataset). Each `v_{i,j} ∈ {good, bad, abstain}`.

In code, a benchmark is a JSON file (Draft 2020-12 schema enforced) carrying the bearer dictionary, the analyst panel, the items (each with its verdict tuple), and optional context-builder overrides. See [`authoring_benchmarks.md`](authoring_benchmarks.md).

### The evaluation `η`

An **evaluation** is what you get from running `M` against `β`:

```
η = { (I_1, V_1, E_M(I_1)), ..., (I_n, V_n, E_M(I_n)) }
```

Same items, same analyst verdicts, plus `M`'s verdict on each. Plus, in the framework's representation, the full per-sample audit trail (raw responses, prompts, token usage, timestamps), the model identity and decoding parameters, and a SHA-256 hash of the canonicalized benchmark JSON for tamper detection.

Evaluations are JSON files; the schema for one is parallel to the benchmark schema. They are immutable artifacts of a particular `(β, M, parameters)` triple — fully reproducible from the JSONL audit log alone.

### The metrics

From `η`, three load-bearing metrics:

**Coverage** `cov(η) = |{ i : E_M(I_i) ≠ abstain }| / n`. The rate at which `M` takes a substantive position. Per-analyst coverage `cov_j(η)` is the analog for analyst `j`.

**Cohen's kappa** `κ_C(η, r)`. Agreement between `M` and a reference verdict function `r`, corrected for chance, restricted to items where both are substantive. The reference is most commonly the **analyst consensus** `c_i` (majority of analysts; abstain on tie), but can also be any single analyst's column.

**Fleiss' kappa** `κ_F(η)`. Agreement across all annotators when `M` is treated as the `(m+1)`th annotator. Same chance correction. **Inter-analyst Fleiss** `κ_F*(β)` is the analog over analyst verdicts alone — the **baseline** `M`'s `κ_F` should be compared against: the analysts' agreement with one another before `M` is in the picture.

Decompositions: each metric can be computed over a subset of items filtered by **tag** or by **RSR target**. The `by-tag` filter is invaluable for localizing disagreement (see [`interpreting_metrics.md`](interpreting_metrics.md)).

Each metric returns `None` (with a logged warning) rather than raising when undefined — the substantive subset is empty, `m < 2` for `κ_F*`, all annotators degenerate to one class, etc. These edge cases are deliberate: an undefined statistic is reported as undefined, not as zero.

## How it all hangs together

```
              ┌─────────────────────────────────────────┐
              │ analyst chooses domain, bearers,        │
              │ items, writes verdicts, declares        │
              │ panels / factors / construction meta    │
              ├─────────────────────────────────────────┤
              │ ↓                                       │
              │ β  (benchmark.json)                     │
              │ ↓                                       │
              │ infereval evaluate                      │
              │   - for each item:                      │
              │     build prompt via δ + ctx_Γ + ctx_Δ  │
              │     sample M n times                    │
              │     parse + majority-vote → E_M         │
              │   - aggregate items into η              │
              │ ↓                                       │
              │ η  (evaluation.json) + run.jsonl        │
              │ ↓                                       │
              │ ┌─────────┬──────────┬─────────┬──────┐ │
              │ │ metrics │ structure│  model  │sweep │ │
              │ └────┬────┴────┬─────┴────┬────┴──┬───┘ │
              │      ↓         ↓          ↓       ↓    │
              │   κ_C / κ_F   RSR + cov. factor   κ_C  │
              │   κ_F* by    coherence  effects  range │
              │   panel      checks     (Wald)  stab.  │
              │      └────────┴──────────┴───────┘     │
              │                  ↓                     │
              │             infereval report           │
              │             (claims + auto-collected   │
              │              negative findings)        │
              └─────────────────────────────────────────┘

              ┌─────────────────────────────────────────┐
              │ Independently:                          │
              │ DerivedFrame.from_endorsements(η)       │
              │   ↓                                     │
              │ ⟨B, I_M⟩ — the implication frame the    │
              │   Hlobil–Brandom machinery acts on:     │
              │   RSR, implication roles, content       │
              │   inclusion, classical-core extensions  │
              │   (the formal apparatus).              │
              └─────────────────────────────────────────┘
```

The four analytical commands (`metrics`, `structure`, `model`, `sweep`) all consume the evaluation JSON; their outputs are the inputs to `report`, which combines them with the analyst's claim declarations into a structured Markdown report with a deterministic mastery verdict. The construct-validity workflow document ([`construct_validity.md`](construct_validity.md)) walks all of this end-to-end.

## What the methodology buys you (and what it doesn't)

It buys you:

- A **reproducible, audit-logged** procedure for asking "does `M` agree with the analysts' inferential practice?" against a specific labeled dataset.
- **Decomposability**: by-tag and by-rsr-target decompositions localize disagreement to specific item subsets. You can see which kinds of inference `M` handles well and which it doesn't.
- **Carving-relativity-aware comparisons across models**: holding `β` constant, comparing `κ_C` across models tells you how each model agrees (or disagrees) with the same labeled practice. Holding the model constant and varying `δ` (the **paraphrase axis**) tells you how much of the agreement depends on the surface form. See `experiments/paraphrase_axis_triangulation.py` for a worked example.
- A **frame** in a precise inferentialist sense (`⟨B, I_M⟩`) on which the Hlobil–Brandom apparatus (RSR, implicational roles, content inclusion, classical-core extensions via NMMS) directly applies.

It does not buy you:

- **Model truth**. The methodology is carving-relative; "what `M` really thinks" is not a frame-independent fact, and the framework is honest about this.
- **A leaderboard**. Comparing models across different benchmarks is incoherent; comparing models on the same benchmark is the unit of comparison the methodology supports.
- **Settlement of in-principle questions**. Whether LLMs can ever be sapient is not a question this framework answers; any such claim would have to take a carving-indexed form, relative to the analyst-supplied carving.

## Next steps

- Author your own benchmark: [`authoring_benchmarks.md`](authoring_benchmarks.md).
- Run an existing one and read the numbers: [`interpreting_metrics.md`](interpreting_metrics.md).
- Run it against real LLMs: [`providers.md`](providers.md).
- Produce defensible evidence for an inferential-mastery claim: [`construct_validity.md`](construct_validity.md) — end-to-end practitioner's guide covering the framework's nine analytical capabilities plus the research-program responsibilities outside the tool's scope.
- See what was shipped to make that workflow possible: [`construct_validity.md`](construct_validity.md) — requirement-by-requirement implementation record.
- The README's 60-second quickstart pulls the basic measurement loop together, against the bundled stop-sign benchmark, with no API key required.
