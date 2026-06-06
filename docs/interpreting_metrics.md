# Interpreting metrics

You ran `infereval evaluate`, you ran `infereval metrics`, you got a wall of numbers. What do they mean?

## The four numbers, in order

```
n (items)              : 4
coverage (M)           : 1.0000
coverage (per analyst) : 1.0000
κ_C(η, consensus)      : +1.0000
κ_F(η)                 : +1.0000
κ_F*(β) (inter-analyst, all): undefined
```

### `coverage` — the participation gate

`cov(η) = fraction of items where the model produced a substantive verdict (good or bad, not abstain)`.

This is your **first sanity check**. If it's low, nothing else in the report is fully informative — the kappa metrics are restricted to substantive items, so a 0.3 coverage means you're scoring `M` on 30% of the benchmark.

What low coverage usually means:

| Coverage | Likely cause | What to do |
|---|---|---|
| `0.95–1.00` | Normal | Move on to kappa. |
| `0.70–0.95` | Some items are genuinely hard, or you have a small `--max-tokens` and a verbose model | Inspect the `parse_status` field in `η`: `unparseable` means the model talked but didn't say a verdict word. `budget_clipped` means the provider truncated by `max_tokens` — raise it. `sample_failed` means a provider error after retries. |
| `0.30–0.70` | Likely a verification prompt the model finds genuinely ambiguous, or a content-attribution disagreement (see Haiku-style perceptual default) | Inspect the prompts that produced abstains; try the paraphrase axis (`experiments/paraphrase_axis_triangulation.py`). |
| `0.00–0.30` | Often token-budget or model-misconfigured | Check `parse_status` distribution. If lots of `budget_clipped`, bump `--max-tokens` to 2048+. See [`providers.md`](providers.md) for the reasoning-tokens issue. |

**Per-analyst coverage** (`cov_j(η)`) is the analog for each human analyst — useful when authoring a benchmark to spot analysts who abstain a lot (their column has less inferential signal).

### `κ_C(η, consensus)` — agreement with the analysts

Cohen's kappa against the **analyst consensus** `c_i` (strict-majority vote across analysts; abstain on tie or when most abstain). Restricted to items where both `M` and the consensus are substantive.

Reading scale, with caveats:

| Value | Loose label | What it means |
|---|---|---|
| `+1.00` | perfect | `M` and the consensus agree on every substantive item. |
| `+0.80 to +0.99` | strong | `M` reliably tracks consensus; disagreements are isolated. |
| `+0.40 to +0.80` | moderate | `M` agrees better than chance but with notable exceptions. Decompose by tag to find the pattern. |
| `+0.20 to +0.40` | weak | `M`'s verdicts are correlated with consensus but only modestly. Often this is a content-attribution disagreement, not an inferential one. Try the paraphrase axis (`docs/concepts.md`). |
| `0.00 to +0.20` | none | `M` is at or near chance. |
| `< 0.00` | anti-correlated | `M` is systematically disagreeing. Often this is a prompt-reading issue (the model is treating "GOOD" as something other than what the verification prompt says). |
| `undefined` | n/a | Either the substantive subset is empty (raise coverage) or the chance-expected agreement `p_e = 1` (everyone — including `M` — is in a single class on this subset, so kappa has no signal). |

The standard cautions about Landis–Koch labels apply: these are heuristic, not normative. In small-`n` benchmarks (`n < 20`), kappa is high-variance and the labels above are at best directional.

**Switching the reference**: by default the reference is the consensus, but you can compare `M` against any specific analyst:

```
infereval metrics eta.json --reference analyst:analyst-a
```

This is informative when analysts disagree among themselves: comparing `M` to each analyst separately can show that `M` is closer to one analyst's column than the other. The paper's discussion of carving-relativity (§5) is exactly this kind of phenomenon — disagreement among competent labelers reflects different ways of carving the domain, and `M` may align with one carving more than another.

### `κ_F(η)` — `M` as the `(m+1)`-th annotator

Fleiss' kappa treats `M` as if it were one more analyst on the panel. Per-item agreement is the pairwise-pair agreement count across all `m+1` annotators, averaged across items, chance-corrected against the pooled marginal distribution.

`κ_F` is different from `κ_C` in two key ways:

1. **Symmetric**. `κ_F` doesn't single out a reference; every annotator contributes equally. This is appropriate when you don't want to privilege analyst consensus over `M`.
2. **Pooled marginals**. The chance-expected agreement is computed from the pooled distribution of all annotators' verdicts. This means `κ_F = κ_C` only by coincidence (typically only when the marginals are symmetric, e.g. under perfect agreement on a balanced item set). At `m = 1`, `κ_F` with `M` as the 2nd annotator is **not** the same number as `κ_C` against that analyst, except in special cases.

Reading `κ_F`: same scale as `κ_C`. What you compare it to is the next metric.

### `κ_F*(β)` — the inter-analyst baseline

This is **the most important reference number** when `m ≥ 2`. It's Fleiss' kappa computed over the analysts alone (no `M`), across the full analyst pool whose verdicts the benchmark records.

The paper's Remark 4 makes the point: `κ_F*(β)` tells you how well the analysts agree with each other before `M` is in the picture. It's the ceiling above which `M` is doing something the analysts don't do. It's also the floor: if `κ_F*(β) = 0.6`, then `M` reaching `κ_F = 0.5` is participating in the practice at a level not far from the analysts' own internal agreement — which is a strong result.

> **What changed in v0.7.0 ([#82](https://github.com/bradleypallen/infereval/issues/82)).** On panelled benchmarks (those declaring `analysts[*].panel` + `primary_panel`), the pre-v0.7.0 default silently restricted κ_F\*(β) to the primary panel — which inflated the headline number when the primary panel was internally unanimous, even if the second panel disagreed on several items. The methodology says otherwise: the Remark 4 baseline is over the full analyst pool you've recruited, and panels are an *additive* convergent-validity device (per-panel decomposition + cross-panel Cohen's κ) rather than a way to narrow the baseline. From v0.7.0, `inter_analyst_fleiss(bench)` returns the all-analyst figure by default; the construct-validity report's section 2 renders both the headline (all analysts) and the primary-panel sub-figure on panelled benchmarks. The primary-panel value remains reachable via `inter_analyst_fleiss_per_panel(bench)[bench.resolved_primary_panel()]` or by passing `analyst_indices=bench.analyst_indices_in_panel(primary_name)`.

| Comparison | What it tells you |
|---|---|
| `κ_F(η) ≈ κ_F*(β)` | `M`'s inclusion doesn't lower inter-annotator agreement — it participates at human-analyst-level coherence. |
| `κ_F(η) > κ_F*(β)` | `M` is *more* consistent with the analyst consensus than the analysts are with each other. Plausible if `M` is just tracking the median, but worth investigating. |
| `κ_F(η) << κ_F*(β)` | `M` is systematically disagreeing with the analyst community. Decompose by tag. |
| `κ_F*(β) = undefined` | Either `m < 2` (no inter-analyst comparison possible) or the analysts are unanimous on every item (no signal). Single-analyst benchmarks are perfectly fine — you just lose this comparison. |

If your benchmark has `m = 1`, expect `κ_F*` to always be undefined and rely on `κ_C` for headline numbers.

### Per-panel and cross-panel: independent-reference checks (v0.3.0+)

If your benchmark declares **reference panels** (per-analyst `panel` plus a benchmark-level `primary_panel`, see [`authoring_benchmarks.md`](authoring_benchmarks.md) Step 4b), `infereval describe` and `infereval report` surface two extra metrics:

```
κ_F*(β) per panel:
  primary (n_analysts=3) : +0.6824
  check   (n_analysts=2) : +0.7100

κ_C cross-panel (primary vs check) : +0.5800
```

| Metric | What it is | Why it matters |
|---|---|---|
| `inter_analyst_fleiss_per_panel` | `κ_F*` computed within each declared panel | Tells you how internally coherent each panel is on its own. A primary panel with `κ_F* = 0.10` and a check panel with `κ_F* = 0.70` means the primary panel is the one to inspect for analyst-disagreement. |
| `cross_panel_kappa` | Cohen's `κ_C` between the two panels' per-item consensuses (default `primary` vs the first declared check panel; override with `--check`) | The construct-validity convergence check (R4 in `construct_validity.md`). A high cross-panel `κ_C` plus a high `κ_C(η, primary-consensus)` is the convergent half of a multi-trait/multi-method argument. A model that agrees with `primary` but disagrees with `check` is a warning sign that the `primary` consensus is panel-specific rather than carving-specific. |

The same `undefined` rules apply as for the corresponding base metrics (empty substantive intersection, `p_e = 1`, single-analyst panel).

### R22 — test-retest reliability (`κ_test-retest`)

Test-retest reliability is the **co-equal §2 reliability metric** alongside agreement (`κ_C`, `κ_F`, `κ_F*`). The agreement metrics tell you how well one capture of `M`'s endorsement column matches the analyst column; `κ_test-retest` tells you whether *that capture is repeatable*. A high `κ_C` whose underlying η you couldn't reproduce twenty minutes later is reporting a sample from an unknown distribution, not a model-level signal.

- **Definition.** Two captures of the same evaluation under the same parameters: `η_a` (baseline) and `η_b` (retest). `κ_test-retest = Cohen's κ` computed over the *consensus column* of each capture, item-by-item. With `n_samples ≥ 3` and majority-vote consensus, sample-internal noise is already smoothed out; the residual disagreement is the cross-capture noise.
- **Within-model analog of `κ_F*(β)`.** Just as `κ_F*` is the analyst-internal baseline above which `M`'s participation is a real signal, `κ_test-retest` is the *model-internal* baseline against which a single-capture `κ_C` should be read. Without it you don't know whether a `κ_C` of `+0.5` reflects the model's actual practice or one moment in a noisy stream.
- **Verdict thresholds.** The framework labels the stability verdict (`stable` / `moderately stable` / `substantively unstable` / `undefined`) using a κ threshold and a verdict-flip-rate threshold; see `infereval.retest`.
- **Audit cap (R22 enforcement).** At scope ≥ `domain_D_as_sampled`, if `competing_explanations.test_retest_run = True` but the supplied retest result is substantively unstable or has undefined κ, the construct-validity verdict caps at `partially_defensible`. The headline `κ_C` cannot be interpreted as signal under a reliability that didn't hold up. A second leg also fires at this scope: the analyst must declare an `IdentityCriterion` under which the across-update comparison is principled.
- **Multi-interval (v0.12.0+).** `infereval retest --auto --interval-s S1 --interval-s S2 ...` captures the baseline once and N timed follow-ups, producing a `MultiIntervalRetestResult` whose `pairs` field carries N retest results, each anchored on the same baseline (cumulative-drift-since-baseline reading). The construct-validity report's worst-case rule applies: if any captured interval is substantively unstable or undefined, the audit cap fires. The methodological commitment: the mastery claim has to hold at *every* time scale the analyst captured, not just the back-to-back floor.

When `κ_test-retest` is **not measured** (no `--retest` artifact supplied), the report explicitly says so under §2 Reliability — a missing R22 capture is itself a construct-validity signal, not a silent zero.

## Decompositions: when the overall number isn't enough

A single `κ_C = 0.40` could mean many different things:

- `M` is uniformly mediocre across all items;
- `M` is perfect on some items and chance on others;
- `M` is perfect on "easy" items (base inferences) and consistently wrong on "hard" ones (defeaters);
- `M` is fine on items with a particular tag and broken on others.

The first three are inferentially different and the fourth is a smoking gun for content-attribution issues. **Decomposition is how you tell which it is.**

### By tag

```
infereval metrics eta.json --benchmark bench.json \
    --by-tag base-inference \
    --by-tag irrelevant-addition \
    --by-tag defeater
```

Produces a separate `n / coverage / κ_C / κ_F / κ_F*` block per tag. **This is the single most useful tool the framework gives you for diagnosis.** A pattern like:

```
By tag: base-inference        κ_C = +1.0000
By tag: irrelevant-addition   κ_C = -1.0000
By tag: defeater              κ_C = +1.0000
```

tells you a precise story: `M` handles base inferences and defeaters but is systematically wrong on irrelevant additions. This is exactly the cross-model finding from `experiments/paraphrase_axis_triangulation.py`: Claude Haiku 4.5 vs. the paper's analyst row.

Choose tag conventions when authoring the benchmark with this decomposition in mind. `["base-inference"]`, `["irrelevant-addition"]`, `["defeater"]` are the obvious ones for RSR-style work; add domain-specific tags too (`["nighttime"]`, `["coinfection"]`).

### By RSR target

```
infereval metrics eta.json --benchmark bench.json \
    --by-rsr-target '{"X": ["bd"], "A": ["ab"]}'
```

Filter to items probing one specific target inference. Useful when a benchmark covers multiple target inferences (multiple `rsr_target` groupings) and you want the per-target story.

## Beyond `metrics`: structure, factor effects, sensitivity (v0.4.0+)

`infereval metrics` answers "how well does `M` agree with the analysts on this benchmark, this run". Three other CLI commands answer adjacent construct-validity questions; their outputs are also consumed by `infereval report`.

### `infereval structure benchmark.json` — content-validity gate

Three deterministic checks on the benchmark itself (no model, no evaluation needed):

| Check | What it verifies | A failure means |
|---|---|---|
| **Containment** | Every declared bearer appears in at least one item's `Γ` or `Δ` | An orphaned bearer — likely a carving slip; either delete it or add an item that exercises it. |
| **RSR role consistency** | For each `rsr_target` group, the role hierarchy (base → addition → defeater) is logically consistent | Misordered roles within a target — the RSR analysis won't be interpretable. |
| **Base-case stability** | Every `rsr_target` group contains at least one base-inference item (the `Γ` from which additions are built) | No anchor for the RSR sweep — additions and defeaters have nothing to attach to. |

Read it as a gate: if `structure` returns non-zero, the benchmark fails content validity (R3) and metrics from it should be reported with that caveat. `report` echoes the `structure` verdict in §3 of its output.

### `infereval model eta.json --benchmark β.json` — factor effects (v0.4.1)

Logistic regression of per-sample agreement (1 if `M` matches the reference, 0 otherwise) on the declared `benchmark.factors` levels, with item-clustered standard errors. Requires `infereval[stats]`.

The output has two parts:

1. **Per-factor joint Wald tests** (`factor_wald`) — one p-value per declared factor, testing the null "this factor has no effect on agreement". A small p-value (e.g. `< 0.05`) means agreement varies systematically across the factor's levels — that factor is doing inferential work. A large p-value means the factor is not differentiating the model's behavior at this sample size.
2. **Per-level coefficients** (`effects`) — log-odds of agreement at this level relative to the alphabetically-first level of the same factor (the baseline). Positive coef → higher agreement than baseline; negative → lower. The `p_value` is the per-level Wald test; the `conf_int_low`/`high` is the 95% CI on the log-odds.

`pseudo_r2` (McFadden) gives a rough sense of overall fit; values above ~0.2 indicate the declared factors meaningfully predict per-sample agreement. This is the GLMM-proxy specified in R10 of the construct-validity programme.

### `infereval sweep` — sensitivity analysis (v0.4.2)

Re-runs `metrics` across a swept parameter (e.g. `--vary tie_break --values abstain,good,bad`) and reports a **stability verdict** based on the range of `κ_C` across the sweep:

| `κ_C` range | Verdict | Reading |
|---|---|---|
| `< 0.05` | `stable across the sweep range` | Choice of parameter doesn't materially affect agreement. Safe to publish at any of the swept values. |
| `0.05 ≤ r < 0.10` | `moderately sensitive` | Some dependence on the parameter; report the specific value used and acknowledge the range. |
| `≥ 0.10` | `varies substantively` | Headline numbers are not robust to the parameter. Consider tighter parameter choices or a wider analyst panel before publishing a mastery claim. |

The point is **not** to pick the best parameter post-hoc — that's p-hacking. The point is to show that the parameter you committed to (`infereval evaluate ...`) wasn't load-bearing. `report` consumes the sweep summary and downgrades the construct-validity verdict by one tier if the sweep is anything other than stable (R11).

### `infereval report` — the construct-validity envelope (v0.5.0)

Consumes the claims file plus the outputs of the four analytical commands above and emits a single Markdown report with a deterministic verdict over five tiers (`Strongly substantiated` / `Substantiated` / `Partially substantiated` / `Limited` / `Insufficient`). The verdict is a function of the claims declared (R-numbers) plus the structural and inferential evidence; it is not a free-text summary.

Two interactions to be aware of:

- **Suppression asymmetry**: if `negative_findings_suppressed: true` is set in the claims file, the verdict downgrades one tier. This makes silence about negative findings explicitly costly in the headline number.
- **Sweep instability penalty**: any sweep verdict other than "stable" triggers a one-tier downgrade with a logged rationale.

The full mapping from claims and evidence to verdict tier is documented in [`construct_validity.md`](construct_validity.md); the practitioner's walk-through is in [`construct_validity.md`](construct_validity.md).

## Edge cases the framework reports rather than hides

The metrics functions return `None` (with a logged warning) rather than raise. These cases are not bugs:

- **`κ_C` undefined when substantive subset is empty.** All items have `M` abstain, or the reference abstain, or both. No items to compare.
- **`κ_C` undefined when `p_e = 1`.** On the substantive subset, every item is the same class (all `good` or all `bad`) for both `M` and the reference. Chance and observed are both 1.0; their difference is 0/0. This often appears on small tag subsets where the analysts unanimously labeled one way and `M` matched.
- **`κ_F` undefined when no items have all-substantive annotations.** Same idea as `κ_C` empty `S`, applied across the full annotator set.
- **`κ_F*` undefined when `m < 2`.** Single-analyst benchmarks have no inter-analyst comparison.
- **`κ_F*` undefined when analysts are unanimous.** `m ≥ 2` analysts agreeing perfectly on every item gives `P̄_e = 1` and chance and observed are both 1.0. No signal.

Each of these returns `null` in the JSON output and `"undefined"` in the text / markdown output, with the reason logged at WARNING. They are diagnostic, not failures — they tell you something concrete about the structure of your benchmark or the model's behavior.

## A worked reading: the live Haiku result from the M9 demo

We ran Claude Haiku 4.5 against the stop-sign benchmark with the original `δ(ra) = "a is red"` and got:

```
n (items)              : 4
coverage (M)           : 1.0000
κ_C(η, consensus)      : +0.2000
κ_F(η)                 : +0.0000
κ_F*(β) (inter-analyst, all): undefined        // m = 1

By tag: base-inference
  n (substantive)      : 1
  M verdicts           : good 1 / bad 0 / abstain 0
  reference verdicts   : good 1 / bad 0 / abstain 0
  κ_C undefined  [under-powered: n < 10]    (p_e = 1 on a one-item subset)
  κ_F  undefined  [under-powered: n < 10]

By tag: irrelevant-addition
  n (substantive)      : 2
  M verdicts           : good 0 / bad 2 / abstain 0
  reference verdicts   : good 2 / bad 0 / abstain 0
  κ_F = -1.0000  [under-powered: n < 10]

By tag: defeater
  n (substantive)      : 1
  M verdicts           : good 0 / bad 1 / abstain 0
  reference verdicts   : good 0 / bad 1 / abstain 0
  κ_C undefined  [under-powered: n < 10]    (p_e = 1 on a one-item subset)
  κ_F undefined  [under-powered: n < 10]
```

Step-by-step reading:

1. **Coverage is 1.00.** No abstains; the model committed on every item. Good baseline.
2. **Overall κ_C = +0.20.** Above chance but well below agreement. Something is going wrong.
3. **By-tag decomposition isolates the disagreement to one tag.** On `irrelevant-addition`, `M` returns `bad` on both items and the analyst returns `good` on both items. The class counts (`good 0 / bad 2` vs `good 2 / bad 0`) make the direction unambiguous: M and the analyst disagree on every item of that tag. The magnitude `κ_F = -1.0000` is *under-powered* — on n = 2 the formula is forced by single-class-each marginals, not measured — so we read the *direction* as a diagnostic lead, not the magnitude as a measurement. The under-powered annotation in the rendered output stops us from over-reading.
4. **Hypothesis** (from the direction): `M` reads `is red` as a *perceptual* claim (nighttime defeats visibility), not an intrinsic claim. Both readings are coherent; they just denote different things. Those two items are exactly the ones where `Γ = {sa, n}` and `Γ = {sa, n, nr}` — the nighttime / non-reflective additions.

Following up on the hypothesis is what `experiments/paraphrase_axis_triangulation.py` does: hold the analyst row constant, vary `δ(ra)`, see whether the disagreement comes from the bearer carving. (It does. The intrinsic phrasing `a has the standard color of stop signs` flipped row-1 to `good` and raised `κ_C` to `+0.50`.) The paraphrase-axis result is what converts the diagnostic lead (the *direction* of the n=2 disagreement) into a confirmed content-attributional reading.

This is the methodology working at correct precision: the headline (`+0.20`) gives the summary; the decomposition (the `irrelevant-addition` cell, with its class counts and under-powered annotation) localizes the disagreement and explicitly warns against reading the magnitude as a measurement; the paraphrase-axis follow-up confirms the cause. Each step is a concrete output of the framework, and the under-powered guard makes the chain self-correcting against over-reading small-subset κ values.

## When the numbers are surprising

If the kappa numbers don't match your prior intuition for the model, the order of diagnostic steps is:

1. **Coverage low?** Token-budget or prompt-ambiguity issue. Fix `--max-tokens`; inspect a few `unparseable` samples in `η`.
2. **Decompose by tag.** Is the disagreement concentrated in one tag? That's almost always content-attributional.
3. **Check the cell's `n (substantive)` and class counts before treating a decomposed `κ` as a finding.** A `κ` of ±1.0 on `n < 10` is a *forced* value, not a measurement — the formula is locked by single-class-each marginals on a tiny subset. The CLI marks these with `[under-powered: n < 10]` and the construct-validity report surfaces them as section 4b negative findings. Use the *direction* of the disagreement as a diagnostic lead; do not use the magnitude.
4. **Inspect the actual prompts.** `infereval evaluate --dry-run` prints what the model is seeing. Verify the framing is what you intended.
5. **Probe with reasoning enabled.** Outside the framework, ask the model the same question with room to explain. Often the model's reasoning makes its content-attribution explicit (Claude's verbatim "we cannot infer that the sign *displays* its standard color — only that it *possesses* that color as a property" is the canonical example).
6. **Vary `δ`.** If the disagreement is content-attributional, swapping the bearer phrasing for the analyst's reading should recover agreement. Run a second benchmark with the variant; see `experiments/paraphrase_axis_triangulation.py` for the pattern.

## Where to go next

- [`concepts.md`](concepts.md) for the methodology's terms.
- [`authoring_benchmarks.md`](authoring_benchmarks.md) if your interpretation suggests you need a richer benchmark — especially the panel/factor/construction-metadata fields that feed the new analytical commands.
- [`construct_validity.md`](construct_validity.md) for the end-to-end practitioner's guide: how to chain `structure` → `metrics` → `model` → `sweep` → `report` into reproducible evidence for an inferential-mastery claim.
- [`construct_validity.md`](construct_validity.md) for which construct-validity requirements (R1–R21) each metric speaks to.
- [`providers.md`](providers.md) for per-provider quirks (specifically, what to set `--max-tokens` to).
- `experiments/paraphrase_axis_triangulation.py` for a worked example of the diagnostic chain above.
