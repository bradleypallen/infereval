# Surveys

`infereval survey {export, import}` is the asynchronous-recruitment surface: it lets you turn a benchmark into a Qualtrics, Google Forms, or SurveyMonkey survey link, send that link to a clinician (or any domain expert), and merge the responses back into the benchmark as a new analyst column — fully validated against the same `Benchmark` schema everything else in the framework consumes.

Three platforms are supported. The shape you get is essentially the same on all three; the only difference is the auth model and a single randomization caveat on Google Forms.

| Platform | Export artifact | Auth needed | Randomization | Import format |
|---|---|---|---|---|
| **Qualtrics** | `.qsf` file (offline, you upload via the Qualtrics UI) | none | full, native | CSV download (Use choice text) |
| **Google Forms** | `.gs` Apps Script file (you paste into script.google.com) | none | **no-op** (whole-form-only API; see below) | CSV from the form's linked Sheet |
| **SurveyMonkey** | live `POST /v3/surveys` API call | `SURVEYMONKEY_ACCESS_TOKEN` env var | full, native | CSV download |

## The shared survey shape

Every export — regardless of platform — produces a survey with:

1. **A free-text expertise question at position 0** (not randomized). The prompt is:

   > Briefly describe your clinical or domain expertise relevant to these inferences — your specialty, years in practice, role, and any board certifications.

   The respondent's answer lands on a new `Analyst.expertise_description` field at import time.

2. **One multiple-choice question per benchmark item**, force-response, with three choices:

   - **Good** — follows from premises
   - **Bad** — does not follow
   - **Abstain** — cannot judge

   The question body is the implication rendered as a premises/conclusion bullet form (TeX-stripped):

   > **Item 7 of 29**
   >
   > Given the following premises, is the conclusion a good diagnostic inference, a bad one, or are you unable to judge?
   >
   > **Premises:**
   > - the patient has acute dyspnea
   > - the patient has bilateral pulmonary infiltrates on imaging
   >
   > **Conclusion:**
   > - the patient has cardiogenic pulmonary edema

3. **An optional free-text rationale** following each MC (default on; disable with `--no-include-rationales`). The prompt is:

   > Optional: briefly explain why you chose that verdict (especially helpful if you abstained or rated bad).

   Rationales land in `BenchmarkItem.analyst_rationales[j]` (existing schema; positionally aligned to `analyst_verdicts`).

4. **Items randomized per respondent** (default on; disable with `--no-randomize-items`). The expertise question stays at position 0 even under randomization. See the Google Forms caveat below.

## Question form (`--question-form`)

A survey must ask the **same** logical question the model is evaluated under, or `κ_C(model vs analyst)` compares two different judgments. Both `infereval survey export` and `infereval survey import` take `--question-form {support,coherence}` (default `support`).

- **`support`** (the default) — the classic single-succedent question: *"Given these premises, is the conclusion a good diagnostic inference, a bad one, or are you unable to judge?"* Choices are Good / Bad / Abstain. Defined only for `|Δ|=1` items.
- **`coherence`** — the bilateral question, rendered through the *same* template the model uses (so the human sees the same content scaffolding), defined for every arity: *"Could this whole position be held at once without conflict, or is it untenable?"* Choices are **Coherent / Incoherent / Unclear**. On import the answer is decoded with the server-side polarity inversion — **Incoherent → good, Coherent → bad, Unclear → abstain** — so imported `analyst_verdicts` sit on the identical good/bad/abstain scale as the model's `E_M`.

**Export and import must use the same `--question-form`.** Whatever `question_form` you evaluate the model under (`EndorsementConfig.question_form`), export the human survey under the same one:

```sh
infereval survey export benchmark.json -o survey.qsf --question-form coherence
# … collect responses …
infereval survey import benchmark.json responses.csv -o benchmark_with_analysts.json --question-form coherence
```

## Survey frames

The question form fixes *which* logical question the survey asks; the **frame** fixes *under which stated norms* it is asked. On the model side the frame is the system prompt (a [`CoherenceFrame`](api.md#infereval.templates) under `coherence`, a `VerificationPrompt` under `support`); on the survey side, the frame's human-facing surface is its **`survey_header`** — the instruction text rendered above each item's body, stating the same assessment norms in respondent voice.

The header is the *only* thing a frame controls on a survey. Choice labels (Good / Bad / Abstain, Coherent / Incoherent / Unclear) and the importer's decode — including the coherence polarity inversion — stay library-controlled at every frame, exactly as the question line, labels, and parse regex do on the model side. This is the survey side of the polarity firewall: no frame can silently invert verdicts on either elicitation surface.

### Resolution order

`render_survey_question` resolves the frame by mirroring the model path:

- **`coherence`** — an explicit `coherence_frame=` argument, then a programmatic `register_coherence_frame(benchmark_id, …)` binding, then the benchmark's declared `coherence_frame_id`, then the thin default (`thin-v1`). All three built-in frames (`thin-v1`, `defeasible-coherence-explicit-v1`, `defeasible-coherence-underdet-v1`) ship authored headers.
- **`support`** — an explicit `verification_prompt=` argument, then the benchmark's `verification_prompt` binding, then the default prompt (`default-v1`).

The resolved frame's id is recorded on the rendered question as `SurveyQuestion.frame_id`, so exports can carry it as provenance and imports can refuse mixed-frame compositions.

### Fail-loud, with one documented fallback

A resolved frame that declares **no** `survey_header` raises `ValueError` rather than silently eliciting humans under different wording than the frame the evaluation records — declaring the human-facing wording is part of the frame's identity. This applies to any coherence frame without a header and to any *explicitly passed* verification prompt without one.

The single deliberate exception: a **benchmark-bound** support prompt without a header (a `verification_prompt` override in the benchmark JSON, which has no `survey_header` field) falls back to the locked v0.9.0 default header. This preserves every pre-frame support survey byte-for-byte — support surveys have always shown the default wording regardless of the benchmark's verification-prompt binding. The fallback is honest and loud: `frame_id` records `"default-v1"` (what was actually shown, not the benchmark's binding), and a `survey.frame.fallback` warning is logged naming the benchmark and the bound prompt id, so the model/survey frame misalignment is visible in the run logs instead of hidden.

### Frames and `κ_C`

The rule above — *"a survey must ask the **same** logical question the model is evaluated under, or `κ_C(model vs analyst)` compares two different judgments"* — extends to the frame axis: model and human elicitation must share the question form **and** the frame. The frame-anchoring captures showed the stated norms are the variable that decides how the coherence question behaves, so a model evaluated under an anchored frame but compared against humans surveyed under the thin header (or vice versa) is a cross-instrument comparison, not an agreement measurement. Whatever frame the model is evaluated under (`coherence_frame_id` / `verification_prompt`), export the human survey under the same one, and check `frame_id` at import time.

## Qualtrics

### Export

```sh
infereval survey export examples/pulmonary_edema/benchmark.json \
    -o recruit.qsf
# Default --platform qualtrics
```

This writes a `.qsf` file. To publish:

1. Log in to Qualtrics → **Projects → Create new project → From a file → Import Qualtrics Survey Format**.
2. Select the `.qsf`.
3. Distribute via **Anonymous Link** (or whatever distribution channel you prefer).

### Import

After collecting responses, export the CSV from Qualtrics:

1. **Data & Analysis → Export → CSV → Use choice text** (this is important — numeric export breaks the importer).
2. Keep the default "Include the first three header rows" setting.

Then:

```sh
infereval survey import examples/pulmonary_edema/benchmark.json \
    -r qualtrics-responses.csv \
    -o examples/pulmonary_edema/benchmark-with-clinicians.json
```

The output is a new benchmark with one new analyst column per respondent. Default require-complete mode rejects any respondent who didn't finish or whose verdicts don't cover all items; pass `--allow-partial` to merge partials (missing verdicts become `ABSTAIN`).

## Google Forms

### Export

```sh
infereval survey export examples/pulmonary_edema/benchmark.json \
    -o recruit.gs \
    --platform google_forms
```

This writes a `.gs` Apps Script file. To publish:

1. Open <https://script.google.com> → **New Project**.
2. Paste the `.gs` contents into `Code.gs`, replacing the placeholder.
3. Click **Run → createForm** and authorize when prompted (one-time Google consent for your own account).
4. Read the form's published URL from the execution log (View → Logs).

> **Randomization caveat.** Google Forms' `FormApp.setShuffleQuestions` is *whole-form* — it would shuffle the expertise question too, which we want to keep first. There's no per-section randomization API. So `--randomize-items` is a no-op on this platform: the questions emit in canonical order, and a warning appears at export time. If item-order randomization is critical to your study, use Qualtrics or SurveyMonkey instead.

### Import

After collecting responses:

1. In the form's responses tab, click **View in Sheets** to open the linked Google Sheet.
2. **File → Download → CSV**.

Then:

```sh
infereval survey import examples/pulmonary_edema/benchmark.json \
    -r google-forms-responses.csv \
    -o examples/pulmonary_edema/benchmark-with-clinicians.json \
    --platform google_forms
```

## SurveyMonkey

SurveyMonkey doesn't have an offline survey-definition format the UI can import; the only programmatic path is the v3 REST API. This means **`infereval survey export --platform surveymonkey` makes a live API call** and requires an access token.

### Getting an access token

1. Sign in at <https://developer.surveymonkey.com>.
2. **My Apps → Create app** (or use an existing app).
3. **Settings → Access Token** — copy the bearer token.
4. Export it:

   ```sh
   export SURVEYMONKEY_ACCESS_TOKEN='<paste>'
   ```

   Or pass it inline via `--surveymonkey-token`.

### Export

```sh
infereval survey export examples/pulmonary_edema/benchmark.json \
    -o surveymonkey-response.json \
    --platform surveymonkey
```

The output file contains the full `POST /v3/surveys` response (survey id, edit URL, share URL). The CLI also echoes the URLs to stdout. Open the edit URL in your browser, click **Collect responses**, and distribute via the SurveyMonkey distribution UI.

EU customers can override the API base URL:

```sh
infereval survey export … \
    --platform surveymonkey \
    --surveymonkey-base-url https://eu-api.surveymonkey.com/v3
```

### Import

Export the CSV from SurveyMonkey: **Analyze Results → Export → Original View, CSV format, Use choice text**. Then:

```sh
infereval survey import examples/pulmonary_edema/benchmark.json \
    -r surveymonkey-responses.csv \
    -o examples/pulmonary_edema/benchmark-with-clinicians.json \
    --platform surveymonkey
```

## Multi-respondent batching

The default behaviour on `infereval survey import` is **all respondents at once** — one CSV with N rows becomes one output benchmark with `m_old + N` analyst columns. The merger:

- Synthesizes each new analyst's id as `f"clinician-{response_id}"` (override the prefix via `--analyst-id-prefix`).
- Threads each respondent's expertise prose into `Analyst.expertise_description`.
- Appends verdicts to `BenchmarkItem.analyst_verdicts` in stable order (one append per respondent, positional with the new analyst order).
- Expands `BenchmarkItem.analyst_rationales` from `None` to a populated `list[str]` when any respondent provided a rationale — pre-existing analysts get the empty-string `""` sentinel (the existing model semantics for "this analyst gave a verdict but recorded no reason").

To filter to a single respondent (useful for piloting), pass `--respondent <ResponseId>`.

## The `mapping.json` sidecar

When any benchmark item id contains characters outside `[A-Za-z0-9_]` (hyphens, slashes, spaces, …), the exporter hashes the id into a `sha8` prefix and writes a sidecar `mapping.json` next to the exported artifact. The importer auto-discovers this sidecar; you only need to pass `--mapping` explicitly if you've moved it.

For benchmarks with clean ids (the common case: `c1`, `pulm_001`, …), no sidecar is written and `--mapping` is unnecessary.

## Schema impact

Only one additive field is added in v0.9.0: `AnalystModel.expertise_description: str | None = None`. Pre-v0.9.0 benchmarks validate unchanged. The shared rationale field (`BenchmarkItem.analyst_rationales: list[str] | None`) was already in the schema — the merger just populates it when respondents write rationales.

## Downstream pipeline interop

The merged benchmark is a regular `Benchmark` JSON file. After import, run any of:

- `infereval describe …` — see the new analyst column count.
- `infereval metrics …` against an evaluation — `κ_F*` recomputes over the expanded analyst pool.
- `infereval report …` — section 2 reflects the new `κ_F*` and the report's analyst tally counts the recruited clinicians.

Nothing downstream changes; only the benchmark's `m` is larger.
