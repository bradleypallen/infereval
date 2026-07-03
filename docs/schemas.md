# JSON schemas

`infereval` ships two **Draft 2020-12** JSON schemas — one for benchmarks
and one for evaluations. They are committed under
[`src/infereval/schemas/`](https://github.com/bradleypallen/infereval/tree/main/src/infereval/schemas)
and **generated from the Pydantic models** — a drift test keeps them in
sync with the source. Versioned independently from the framework via
`schema_version: "1.0"`; **stability from 1.0 onward is promised**
regardless of framework version. The 0.3.x–0.5.x construct-validity
series added optional fields only, so every pre-0.3.0 benchmark continues
to validate against the current schema.

This page is the reference companion to [Authoring benchmarks](authoring_benchmarks.md).
For runtime behavior, see the [API reference](api.md).

## Files

- [`benchmark.schema.json`](https://github.com/bradleypallen/infereval/blob/main/src/infereval/schemas/benchmark.schema.json)
- [`evaluation.schema.json`](https://github.com/bradleypallen/infereval/blob/main/src/infereval/schemas/evaluation.schema.json)

Validate any benchmark against the committed schema:

```bash
infereval validate examples/stop_sign/benchmark.json
```

or in Python:

```python
import json, jsonschema
from importlib.resources import files
schema = json.loads(files("infereval.schemas").joinpath("benchmark.schema.json").read_text())
jsonschema.Draft202012Validator(schema).validate(your_benchmark_dict)
```

---

## `benchmark.schema.json`

A benchmark is the analyst-supplied artifact that drives evaluation:
bearers, an analyst panel, and items. See the
[Authoring guide](authoring_benchmarks.md) for the practitioner walk-through.

### Top-level fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `schema_version` | `"1.0"` (Literal) | ✓ | Independent of framework version. Promised stable from 1.0. |
| `id` | `str` | ✓ | Stable identifier for the benchmark. |
| `title` | `str \| null` | optional | Human-readable title. |
| `domain` | `str \| null` | optional | Domain of discourse (e.g. `"clinical reasoning"`). |
| `description` | `str \| null` | optional | One-line description. |
| `bearers` | `dict[str, BearerModel]` | ✓ | The bearer set `B` keyed by id. |
| `analysts` | `list[AnalystModel]` (min 1) | ✓ | The analyst panel `{a_1, …, a_m}`. |
| `context_builders` | `ContextBuilders` | optional | `ctx_Γ` / `ctx_Δ`; defaults to "and"-conjunction / "or"-disjunction templates. |
| `verification_prompt` | `VerificationPromptOverride \| null` | optional | Benchmark-level override of the framework's default verification prompt (`support` question form only). |
| `template_id` | `str \| null` | optional | Id of a catalogued template the `coherence` question form renders items through (model prompt + survey paths), e.g. `"clinical-coherence-v1"`. Unknown ids fail loudly at resolution time. |
| `items` | `list[BenchmarkItem]` | ✓ | The implications + analyst-verdict tuples. |
| `factors` | `dict[str, list[str]]` | optional, default `{}` | Declared design factors and their levels (v0.3.0+). |
| `factor_constraints` | `FactorConstraints \| null` | optional | Validator constraints on the factorial design — currently `min_items_per_cell`. |
| `factor_kinds` | `dict[str, "substantive" \| "experimentally_controlled"]` | optional, default `{}` | Per-factor valence label (v0.5.3+). Used by the report's negative-findings renderer. |
| `primary_panel` | `str \| null` | optional | The panel name `κ_F*` defaults to (when panels are declared). |
| `references` | `list[Reference]` | optional, default `[]` | Corpus-level provenance citations. |

### `BearerModel`

| Field | Type | Meaning |
|---|---|---|
| `expression` | `str` | The natural-language statement `δ(φ)` for the bearer. |
| `paraphrases` | `tuple[str, ...]` | Optional meaning-preserving paraphrases. Activated at runtime via `--paraphrase-variant K` / `--paraphrase-cycle` (v0.3.1+). |
| `references` | `list[Reference]` | Per-bearer citations. |

### `AnalystModel`

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Stable identifier. |
| `display_name` | `str \| null` | Optional display label. |
| `notes` | `str \| null` | Free-form competence note (R1). |
| `panel` | `str \| null` | Optional panel id for cross-panel agreement (v0.3.3+). All-or-none across analysts. |

### `BenchmarkItem`

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Stable identifier. |
| `premises` | `list[str]` | Bearer ids in `Γ_i`. |
| `conclusions` | `list[str]` | Bearer ids in `Δ_i` (single-bearer in the paper's instantiation; multi-bearer permitted by infereval). |
| `analyst_verdicts` | `list[Verdict]` (length `m`) | `V_i = (v_{i,1}, …, v_{i,m})`. |
| `analyst_rationales` | `list[str] \| null` | Optional per-analyst, per-item rationale text positionally aligned to `analyst_verdicts` (v0.5.4+). `null` ≠ list with empty strings (semantically distinct). |
| `tags` | `list[str]` | Decomposition labels for `infereval metrics --by-tag`. Common: `base-inference`, `irrelevant-addition`, `supporter`, `defeater`. |
| `rsr_target` | `RSRTarget \| null` | Target inference `⟨X, A⟩` this item helps characterise. |
| `references` | `list[Reference]` | Per-item citations. |
| `factor_levels` | `dict[str, str]` | Position of the item in the crossed design. Keys / values must match `factors`. |
| `construction_metadata` | `ConstructionMetadata \| null` | Authoring provenance (v0.3.2+). |

### `RSRTarget`

| Field | Type | Meaning |
|---|---|---|
| `X` | `list[str]` | Bearer ids in the target's premise set. |
| `A` | `list[str]` | Bearer ids in the target's conclusion set. |

### `ConstructionMetadata`

| Field | Type | Meaning |
|---|---|---|
| `authored_by` | `str \| null` | Item author (R5). |
| `authored_on` | `date \| null` | ISO date authored (R9). |
| `authored_blind_to_models` | `list[str]` | Models the author had **not** observed at draft time (R8). Required field for the held-out argument. |
| `source` | `str \| null` | Primary material the author worked from. |

### `ContextBuilders`

| Field | Type | Meaning |
|---|---|---|
| `premise` | `TemplateContextBuilder \| PluginContextBuilder` | `ctx_Γ`. Default: template with `joiner=" and "`. |
| `conclusion` | `TemplateContextBuilder \| PluginContextBuilder` | `ctx_Δ`. Default: template with `joiner=" or "`. |

### `TemplateContextBuilder` / `PluginContextBuilder`

Two discriminated-union variants on `kind`:

- `kind: "template"` — `template: str` (default `"{expressions}"`) + `joiner: str`. Inline template form.
- `kind: "plugin"` — `plugin: str` (dotted import path). Escape hatch for full Python control.

### `VerificationPromptOverride`

| Field | Type | Meaning |
|---|---|---|
| `template` | `str` | The user template (required). `{premise_context}` / `{conclusion_context}` placeholders. |
| `system` | `str \| null` | Optional system message override (v0.2.2+); uses `DEFAULT_SYSTEM_PROMPT` otherwise. |
| `parse_regex` | `str \| null` | Optional override of the verdict-parsing regex. |
| `id` | `str \| null` | Optional id for the override. |

### `Reference`

| Field | Type | Meaning |
|---|---|---|
| `citation` | `str` | Required citation string. (A bare string in a `references` list is auto-promoted to `{"citation": str}`.) |
| `doi` | `str \| null` | DOI when known. |
| `url` | `str \| null` | URL when known. |
| `section` | `str \| null` | Pinpoint location (e.g. `"Section 5.2"`). |
| `note` | `str \| null` | What this reference supports. |

### `FactorConstraints`

| Field | Type | Meaning |
|---|---|---|
| `min_items_per_cell` | `int \| null` | If set, every cell of the fully crossed design must contain at least this many items. Validator rejects below the floor with a list of underpopulated cells. |

### `Verdict`

Enum: `"good"` / `"bad"` / `"abstain"`.

### Cross-field validation summary

The schema covers types and value enums; cross-field rules are enforced by
the Pydantic model validator and may reject schema-passing inputs:

- `len(item.analyst_verdicts) == len(analysts)` for every item.
- `len(item.analyst_rationales) == len(analysts)` when the field is present.
- `item.factor_levels` keys ⊆ `factors` keys; values ⊆ declared levels.
- `factor_constraints.min_items_per_cell` ≤ items per cell of the fully crossed design.
- `primary_panel` ∈ declared `analyst.panel` values when set.
- `analyst.panel` is all-or-none: if any analyst declares a panel, all must.
- `factor_kinds` keys ⊆ `factors` keys.

Run `infereval validate` to surface these.

---

## `evaluation.schema.json`

An evaluation is what `infereval evaluate` writes after running a model
against a benchmark.

### Top-level fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `schema_version` | `"1.0"` (Literal) | ✓ | Schema version. |
| `framework_version` | `str` | ✓ | The framework version that produced this evaluation. |
| `id` | `str` | ✓ | Stable identifier (UUID4 unless overridden). |
| `benchmark_id` | `str` | ✓ | The source benchmark's id. |
| `benchmark_hash` | `str \| null` | optional | `sha256:` prefix + canonical-JSON SHA-256 of the benchmark. Tamper-evidence. |
| `model` | `ModelInfo` | ✓ | Provider, model id, decoding params. |
| `endorsement_config` | `EndorsementConfig` | ✓ | `n_samples`, `tie_break`, prompt ids. |
| `items` | `list[EvaluationItem]` | ✓ | Items + analyst verdicts + `M`'s verdict + samples. |
| `references` | `list[Reference]` | optional | Corpus-level provenance carried from the benchmark. |
| `paraphrase_variant` | `int \| null` | optional | Which paraphrase variant produced this `η` (0 = canonical). |
| `started_at` | `datetime \| null` | optional | UTC start. |
| `finished_at` | `datetime \| null` | optional | UTC end. |

### `EvaluationItem`

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Matches the benchmark item id. |
| `premises` / `conclusions` | `list[str]` | Bearer ids. |
| `analyst_verdicts` | `list[Verdict]` | Carried from the benchmark. |
| `analyst_rationales` | `list[str] \| null` | Carried from the benchmark (v0.5.4+). |
| `model_verdict` | `Verdict` | `E_M(I_i)`. |
| `samples` | `list[SampleRecord]` | One record per provider call (raw response, parsed verdict, usage, timing, finish reason). |
| `majority_vote` | `MajorityVote \| null` | Tally + tie-break flag. |
| `tags` | `list[str]` | Decomposition labels (propagated). |
| `references` | `list[Reference]` | Per-item citations (propagated). |

### `ModelInfo` / `EndorsementConfig` / `SampleRecord` / `MajorityVote`

See the [API reference](api.md) for full field listings — these mirror the
Pydantic models exactly.

---

## Updating schemas

The schemas are **generated**, not hand-edited. After any change to the
Pydantic models in `benchmark.py` or `evaluation.py`:

```bash
python -c "from infereval.schemas import emit_static_schemas; emit_static_schemas()"
```

A drift test in the suite keeps the committed JSON in sync with the
Pydantic source; CI fails on a hand-edit. Version bumps to
`__version__` also flow into `evaluation.schema.json`'s
`framework_version.default` via the same regeneration step.
