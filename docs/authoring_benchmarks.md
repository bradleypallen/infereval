# Authoring benchmarks

This guide walks through writing a `benchmark.json` for your own domain. We'll do a small medical-defeasibility example end-to-end, then point you at the validation tools.

If you'd rather build it interactively, the same content is in [`tutorials/02_authoring_a_benchmark.ipynb`](tutorials/02_authoring_a_benchmark.ipynb).

## The skeleton

A benchmark file has five top-level pieces, plus an `id` and optional descriptive metadata:

```json
{
  "schema_version": "1.0",
  "id": "<your-benchmark-id>",
  "title": "...",
  "domain": "...",
  "description": "...",

  "bearers":    {...},        // map from bearer id → expression
  "analysts":   [...],        // who labeled this
  "context_builders": {...},  // how to package premise / conclusion sets
  "items":      [...]         // the implications + analyst verdicts
}
```

A `verification_prompt` override field exists for benchmarks that need a custom system message, user template, parse regex, or stable prompt identifier — for example, to run the paraphrase axis with a defeasibility-explicit prompt. Most benchmarks should leave it alone (the framework default is the locked `default-v1` template). When supplied, each sub-field that you leave out falls back to the framework default:

```json
"verification_prompt": {
  "template": "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
  "system": "You are evaluating defeasible material inference. ...",
  "parse_regex": "\\b(GOOD|BAD|ABSTAIN)\\b",
  "id": "my-defeasible-v1"
}
```

## Step 1: Decide what you're measuring

Before writing JSON, write down (on paper or in a comment):

1. **The domain.** "Medical reasoning about treatment selection." "Contract enforceability." "Default reasoning about animals."
2. **The inferential structure you care about.** Pick one or a few **target inferences** — the inferences whose RSR (range of subjunctive robustness) you want to characterize. For our medical example: `bacterial diagnosis ⟹ antibiotics indicated`.
3. **The defeaters and irrelevant additions** for those target inferences. What are the side-premises that would change the verdict? What are the ones that shouldn't?

These three things tell you what bearers you need.

## Step 2: Carve the bearers

For our medical example, the target inference is `bd ⟹ ab` (`a has a bacterial diagnosis` ⟹ `antibiotics are indicated for a`). The natural side-premises to test:

- `sf` — `a has a fever` (irrelevant addition: doesn't change the conclusion)
- `cf` — `a has a cough` (irrelevant addition)
- `vd` — `a has a viral co-infection` (defeater: antibiotics still indicated for the bacterial part, so this is actually irrelevant — but worth testing)
- `pa` — `a is allergic to penicillin` (defeater: changes which antibiotic, but "antibiotics indicated" still holds — also a subtle case)
- `pcr` — `a's bacterial diagnosis was a PCR false positive` (definitive defeater)
- `re` — `a has fully recovered` (definitive defeater)

The carving is a judgment call. There is no "correct" set; you pick what captures the inferential structure your analysis cares about.

Be honest about ambiguity. If `δ(pa) = "a is allergic to penicillin"` could plausibly trigger either "still need antibiotics, just a different class" or "no antibiotics" depending on how the model carves the predicates, the benchmark item using `pa` is going to be hard to interpret — and that's *good*, because it surfaces a real ambiguity in the domain.

## Step 3: Write the bearers section

```json
"bearers": {
  "bd":  {"expression": "a has a bacterial diagnosis"},
  "ab":  {"expression": "antibiotics are indicated for a"},
  "sf":  {"expression": "a has a fever"},
  "cf":  {"expression": "a has a cough"},
  "vd":  {"expression": "a has a viral co-infection"},
  "pcr": {"expression": "a's bacterial diagnosis was a PCR false positive"},
  "re":  {"expression": "a has fully recovered"}
}
```

The bearer id (`bd`, `ab`, ...) is what travels through implications. The `expression` is what the model sees (via `δ`) after TeX-math delimiters are stripped at prompt time.

If you have multiple natural phrasings of the same bearer, list them in `paraphrases`:

```json
"bd": {
  "expression": "a has a bacterial diagnosis",
  "paraphrases": [
    "a's diagnosis indicates a bacterial infection",
    "a has been diagnosed with a bacterial illness"
  ]
}
```

**Paraphrases are runtime-active as of v0.3.1.** `infereval evaluate --paraphrase-variant K` runs against `paraphrases[K-1]` for each bearer that has it (falling back to `expression` for bearers that don't reach that variant). `infereval evaluate --paraphrase-cycle` runs once per variant and writes one `eta-vN.json` per variant. This is what addresses R10 (paraphrase variation under fixed inferential content) — content-vs-form robustness becomes a one-flag operation. See [`construct_validity.md`](construct_validity.md) §2.2 for the full workflow.

## Step 4: Declare the analyst panel

```json
"analysts": [
  {"id": "analyst-a", "display_name": "Analyst A",
   "notes": "Labels reflect the analyst's reading of competent practice in domain D."},
  {"id": "analyst-b", "display_name": "Analyst B"}
]
```

`m = len(analysts)` is the number of analysts. Each item's `analyst_verdicts` list must have exactly `m` entries, in the same order as the `analysts` array.

The number of analysts matters: `κ_F*(β)`, the inter-analyst baseline, is only defined when `m ≥ 2` and the analysts are not unanimous on every item. With `m = 1` (like our stop-sign example) you have a benchmark but no baseline.

**Document analyst competence in `notes`** (R1). The framework records the declaration but cannot vet the credentials — write something a domain reviewer would accept. The pattern is "specific credential or role + tenure/depth + scope of competence relevant to D" rather than just a job title; e.g., for a clinical-reasoning benchmark, "Board-eligible pulmonologist, 12 years bedside experience in differential diagnosis" beats "physician"; for a contract-law benchmark, "Practising commercial-contracts attorney, 8 years drafting and reviewing M&A clauses" beats "lawyer"; for a software-engineering benchmark, "Senior systems engineer, 10 years on production distributed databases" beats "engineer." The pulmonology demo bundled with the framework illustrates the pattern in the clinical-reasoning case.

**Recruiting analysts asynchronously.** When you need to expand the analyst pool — typical in clinical or other distributed-expert domains — `infereval survey {export, import}` turns the benchmark into a Qualtrics, Google Forms, or SurveyMonkey survey, then merges the responses back into the benchmark as new analyst columns. The respondent's free-text expertise blurb lands on `Analyst.expertise_description` (a recruitment-metadata field distinct from `notes`); per-item rationales land in `BenchmarkItem.analyst_rationales`. See [`surveys.md`](surveys.md) for the end-to-end workflow.

### Step 4b: Declare panels (optional, R4)

For the independent reference check (R4), declare analysts as belonging to named panels:

```json
"analysts": [
  {"id": "analyst-a", "panel": "primary", "notes": "..."},
  {"id": "analyst-b", "panel": "primary", "notes": "..."},
  {"id": "analyst-c", "panel": "reviewer", "notes": "..."}
],
"primary_panel": "primary"
```

The validator enforces: if *any* analyst declares a `panel`, *all* must (partial-panel benchmarks are rejected); `primary_panel` must name a panel that at least one analyst belongs to. With ≥ 2 panels declared, `infereval describe` renders per-panel κ_F\* + cross-panel Cohen's κ, and the construct-validity report can mark `cross_panel_check_run: true`. See [`interpreting_metrics.md`](interpreting_metrics.md) for what to read off the per-panel block.

**Declaring panels does not silently change the κ_F\* baseline (v0.7.0+).** Panels are an *additive* convergent-validity device: they give you the per-panel κ_F\* decomposition (`inter_analyst_fleiss_per_panel`) and the cross-panel Cohen's κ (`cross_panel_kappa`) *in addition to* the headline κ_F\*, not in place of it. The headline κ_F\* — the Remark 4 inter-analyst baseline — remains Fleiss' kappa over the full analyst pool whose verdicts the benchmark records (i.e. all of them, across panels). The construct-validity report's section 2 renders both the headline and the primary-panel sub-figure on panelled benchmarks for transparency. Pre-v0.7.0 the headline silently narrowed to the primary panel; [#82](https://github.com/bradleypallen/infereval/issues/82) describes the failure mode that motivated the fix.

## Step 5: Declare context builders (usually leave default)

```json
"context_builders": {
  "premise":    {"kind": "template", "template": "{expressions}", "joiner": " and "},
  "conclusion": {"kind": "template", "template": "{expressions}", "joiner": " or "}
}
```

This is the default and matches Simonelli's dialogue. Skip the field entirely to use it implicitly. Override only if you need richer construction (e.g. "Granting normal background conditions, ..." as a wrapper template), which is rarely the right move — paraphrase the bearers directly instead.

## Step 6: Write the items

Each item declares one `⟨Γ, Δ⟩` implication plus one verdict per analyst:

```json
"items": [
  {
    "id": "base",
    "premises":    ["bd"],
    "conclusions": ["ab"],
    "analyst_verdicts": ["good", "good"],
    "tags": ["base-inference"],
    "rsr_target": {"X": ["bd"], "A": ["ab"]}
  },
  {
    "id": "irrelevant-fever",
    "premises":    ["bd", "sf"],
    "conclusions": ["ab"],
    "analyst_verdicts": ["good", "good"],
    "tags": ["irrelevant-addition", "symptom"],
    "rsr_target": {"X": ["bd"], "A": ["ab"]}
  },
  {
    "id": "defeater-pcr",
    "premises":    ["bd", "pcr"],
    "conclusions": ["ab"],
    "analyst_verdicts": ["bad", "bad"],
    "tags": ["defeater", "false-positive"],
    "rsr_target": {"X": ["bd"], "A": ["ab"]}
  },
  {
    "id": "defeater-recovered",
    "premises":    ["bd", "re"],
    "conclusions": ["ab"],
    "analyst_verdicts": ["bad", "bad"],
    "tags": ["defeater", "recovered"],
    "rsr_target": {"X": ["bd"], "A": ["ab"]}
  },
  {
    "id": "ambiguous-coinfection",
    "premises":    ["bd", "vd"],
    "conclusions": ["ab"],
    "analyst_verdicts": ["good", "good"],
    "tags": ["irrelevant-addition", "coinfection"],
    "rsr_target": {"X": ["bd"], "A": ["ab"]}
  }
]
```

What each field does:

- **`id`**: unique within the benchmark. Used for log lookups and decompositions.
- **`premises` / `conclusions`**: lists of bearer ids. Order doesn't matter (the model treats them as sets); the framework sorts and dedupes them on input.
- **`analyst_verdicts`**: `m`-tuple of `"good" | "bad" | "abstain"`. Order matches the `analysts` array.
- **`tags`**: arbitrary labels for `by-tag` decomposition. `infereval metrics --by-tag <tag>` filters to items carrying that tag. Common conventions: `base-inference`, `irrelevant-addition`, `defeater`, plus domain-specific descriptors.
- **`rsr_target`** (optional): the target inference `⟨X, A⟩` this item helps characterize the RSR of. Items with the same `rsr_target` form a coherent subset for `infereval metrics --by-rsr-target`. Use it whenever you have multiple items probing the same target.
- **`factor_levels`** (optional, v0.3.0): per-factor level assignments for crossed-design benchmarks. See Step 6b.
- **`construction_metadata`** (optional, v0.3.2): per-item provenance. See Step 6c.
- **`references`** (optional, v0.2.2): literature anchoring per item. See Step 7b.

## Step 6b: Declare factors and items' factor levels (optional, R7+R12)

For a *structured* benchmark — one whose items cross declared dimensions — declare the design at the benchmark level:

```json
"factors": {
  "side_premise_type": ["base", "supporter", "defeater", "mixed-evidence"],
  "target_inference": ["T1", "T2", "cross-cutting"]
},
"factor_constraints": {
  "min_items_per_cell": 2
}
```

Then position each item in the design:

```json
{
  "id": "c2",
  "premises": ["bi", "ad", "el"],
  "conclusions": ["cpe"],
  "analyst_verdicts": ["good", "good"],
  "tags": ["supporter", "biomarker"],
  "factor_levels": {
    "side_premise_type": "supporter",
    "target_inference": "T1"
  }
}
```

The validator rejects (a) items with `factor_levels` keys not in `factors`, (b) items with level values not in the declared levels list, and (c) benchmarks where any cell of the crossed design has fewer than `min_items_per_cell` items. The error message lists the underpopulated cells so you can see exactly where to add items.

The payoff is the factor-effects model fit in `infereval model` (v0.4.1): per-factor joint Wald tests + per-level coefficients on the declared design. Without factors, that command refuses to fit with a clear error.

## Step 6c: Record construction provenance (optional, R5+R8+R9)

For benchmarks intended for serious construct-validity work, every item gets a `construction_metadata` block:

```json
"construction_metadata": {
  "authored_by": "analyst-c",
  "authored_on": "2026-04-15",
  "authored_blind_to_models": ["claude-opus-4-7", "gpt-5", "gemini-2.5-pro"],
  "source": "<primary reference work for this item — paper, guideline, textbook, regulation, etc.>"
}
```

All four fields are optional but each addresses a specific construct-validity requirement:

- **`authored_by`** (R5): who authored the item. Used in the `infereval describe` provenance summary.
- **`authored_on`** (R9): ISO date the item was authored. Required for temporal training-data separation arguments.
- **`authored_blind_to_models`** (R8): every model the author had not observed on a draft of this item. The key declaration for *held-out* items — see [`construct_validity.md`](construct_validity.md) §0.5 on why blindness has to be decided up front.
- **`source`**: the primary material the author worked from (distinct from `references`, which records the literature *supporting* the verdict).

The framework validates structure (Pydantic types, `extra="forbid"`) but does not enforce that `authored_on` post-dates any training cutoff — content is the analyst's responsibility, but its *presence* is auditable.

## Step 7: Validate

```
infereval validate path/to/your-benchmark.json
```

The validator runs the full Pydantic checks: every bearer id referenced in `premises` / `conclusions` / `rsr_target` exists in `bearers`; every item has exactly `m` analyst verdicts; analyst and item ids are unique; verdict values are in `{good, bad, abstain}`; etc. The error messages name the offending field and value.

For non-Python downstream consumers, the same checks (modulo cross-field ones) live in the committed JSON Schema — see [`schemas.md`](schemas.md) for the rendered field reference, or the raw [`benchmark.schema.json`](https://github.com/bradleypallen/infereval/blob/main/src/infereval/schemas/benchmark.schema.json) on GitHub.

## Step 7b: Add references (optional but strongly recommended for regulated domains)

For non-trivial benchmarks — anything beyond a teaching example — every item should be traceable to a source. The schema supports a `references` list on three levels:

- **`Benchmark.references`** — corpus-level provenance: the paper / dialogue / regulatory framework the benchmark is derived from.
- **`bearers[<id>].references`** — when the bearer definition itself comes from a specific source (e.g. the threshold `"P/F < 300"` is fixed by the Berlin ARDS definition).
- **`items[i].references`** — the primary use case: the guideline section, paper, or document that justifies the analyst's verdict on that implication.

Each entry is either a plain string (shorthand for `{"citation": "..."}`) or a structured object:

```json
{
  "id": "a2",
  "premises": ["bi", "ad", "pf"],
  "conclusions": ["ards"],
  "analyst_verdicts": ["good"],
  "tags": ["supporter", "criterion"],
  "references": [
    "Ware & Matthay (2005). N Engl J Med 353:2788.",
    {
      "citation": "Ranieri et al. (2012). Acute respiratory distress syndrome: the Berlin Definition. JAMA 307(23), 2526-2533.",
      "doi": "10.1001/jama.2012.5669",
      "section": "Hypoxemia criterion",
      "note": "P/F < 300 is the moderate-severe threshold"
    }
  ]
}
```

Fields on a structured `Reference`: `citation` (required, free-form), `doi`, `url`, `section` (pinpoint locator), `note` (what the reference supports, in the author's words). Unknown fields are rejected by validation, so typos in field names fail loudly. All fields beyond `citation` are optional.

Why bother? Three concrete payoffs:

1. **Auditability.** A reviewer who doesn't trust your analyst's verdict on item `a2` can follow the citation to verify the inference is in the standard literature.
2. **Reproducibility under analyst turnover.** If your domain expert is unavailable later, a new annotator can re-label using the same source material.
3. **Tooling.** Downstream code can render bibliographies, validate DOIs, or filter benchmarks by source.

`references` defaults to `[]` everywhere — adding them is purely additive and doesn't break existing benchmarks.

## Step 8: Describe

```
infereval describe path/to/your-benchmark.json
infereval describe --items path/to/your-benchmark.json
```

Prints the bearer count, item count, analyst panel, per-analyst label distribution, `κ_F*` baseline (when `m ≥ 2` and the analysts are non-unanimous), tag frequencies, and RSR-target groupings. As of v0.3.x the output also includes:

- the **bearer dictionary** (every id with its English expression)
- the **verification prompt** block when an override is set
- a **references summary** with per-level counts
- a **factorial design** section when `factors` is declared, listing total cells / populated cells / floor-meeting cells with underpopulated cells flagged
- a **paraphrase variants** line when any bearer has `paraphrases`
- the **analyst panels** block with per-panel κ_F\* and (for exactly two panels) cross-panel κ_C
- a **construction provenance** summary when any item carries `construction_metadata`
- a **verdict distribution by tag group** cross-tab (T1 / T2 / cross-cutting)

`--items` extends the report with a per-implication block: bearer-id form on the header, resolved English Γ / Δ, the analyst verdict tuple, the tags, the per-item `construction:` line, and the full inline reference block. This is the format you give a domain expert when you want them to audit every item without opening the JSON.

This is your sanity check — does the benchmark look like what you intended?

## Step 9: Smoke-test with the mock provider

Before spending API calls, check the framework wiring with `--replay-from` (if you have a fixture) or with a `ScriptedProvider` via the Python API:

```python
from infereval.benchmark import Benchmark
from infereval.evaluation import EndorsementConfig, evaluate
from infereval.providers.mock import ScriptedProvider

bench = Benchmark.load("path/to/your-benchmark.json")
# 5 items × 5 samples = need 25 responses
provider = ScriptedProvider(responses=["GOOD"] * 15 + ["BAD"] * 10)
eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=5))
print(f"items={eta.n}")
print(f"first item samples: {[s.raw_response for s in eta.items[0].samples]}")
```

Good outcomes here:
- No exceptions during construction or evaluation.
- The shape of `eta` matches what you expect.
- All items got `len(samples) == n_samples`.

## Step 10: Run it for real

```
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY / OPENROUTER_API_KEY
infereval evaluate path/to/your-benchmark.json \
    --provider anthropic --model claude-haiku-4-5-20251001 \
    --output medical-eta.json \
    --n-samples 5 --max-tokens 512 \
    --log medical-run.jsonl
```

Note: the framework default of `--max-tokens 1024` (as of v0.5.2) clears most reasoning-capable models including DeepSeek-style silent-reasoning-token models. Bump to 2048-4096 only for heavy-reasoning variants (`o1-pro`, `o3-pro`, `qwen3-max-thinking`). See [`providers.md`](providers.md) for the per-provider list.

Then:

```
infereval metrics medical-eta.json --benchmark path/to/your-benchmark.json
infereval metrics medical-eta.json --benchmark path/to/your-benchmark.json \
    --by-tag irrelevant-addition --by-tag defeater
```

[`interpreting_metrics.md`](interpreting_metrics.md) walks through what to do with the output.

## Common pitfalls

**Carving too fine or too coarse.** If your bearers are too fine-grained, your items become combinatorial (and your analysts have to label many of them). If too coarse, the inferential structure you wanted to probe gets washed out. Aim for a bearer set that supports 4–20 items per target inference.

**Implicit assumptions in `δ`.** "`a is allergic to penicillin`" embeds the assumption that "antibiotics" generically includes penicillin. If the model disambiguates ("we'd use a non-penicillin antibiotic"), it's reading `ab` differently than your analysts. The fix is to make `δ(ab)` precise about which assumption you're testing.

**Disagreement between analysts you didn't expect.** This is *good information* — it means the domain has genuine ambiguity that the methodology will surface as `κ_F*(β) < 1`. Don't paper over it by forcing unanimous labels. The methodology lets you say "this benchmark has inter-analyst κ_F* = 0.67; the model achieves κ_C = 0.55 against consensus", which is a useful and honest statement.

**Forgetting to set `--max-tokens`.** Symptom: high abstain rate, low coverage. Cause: budget-clipping. Fix: `--max-tokens 256` or higher.

## Where to go next

- Run a real evaluation: [`providers.md`](providers.md).
- Read the output: [`interpreting_metrics.md`](interpreting_metrics.md).
- Use the full construct-validity toolchain (structure / model / sweep / report) to produce a defensible mastery claim: [`construct_validity.md`](construct_validity.md).
- See the conceptual framework that makes all this coherent: [`concepts.md`](concepts.md) and the paper.
