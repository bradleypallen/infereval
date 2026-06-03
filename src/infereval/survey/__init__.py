"""Survey export / import for analyst recruitment (v0.9.0).

Generates platform-specific survey artifacts from an :class:`~infereval.benchmark.Benchmark`
(Qualtrics ``.qsf``, Google Forms ``.gs`` Apps Script, or a SurveyMonkey API
payload) and converts platform CSV response exports back into a Benchmark
with one new analyst column per respondent.

Platform support in v0.9.0:

- **Qualtrics** — offline ``.qsf`` file; CSV importer.
- **Google Forms** — offline ``.gs`` Apps Script the recruiter pastes into
  ``script.google.com``; CSV importer. Note that Google Forms cannot
  randomize a subset of questions, so ``randomize_items=True`` is a
  no-op on this platform (emits a logged warning at export time).
- **SurveyMonkey** — live ``POST /v3/surveys`` API call (requires
  ``SURVEYMONKEY_ACCESS_TOKEN`` env var); CSV importer.

The platform-agnostic surface (``render_implication_text``,
``sanitize_export_tag``, ``SurveyRespondent``, shared default constants)
lives in :mod:`infereval.survey.render`. Each platform has a generator
module (``<platform>_qsf``/``<platform>_gas``/``<platform>_api``) and a
CSV-importer module (``<platform>_csv``).

See ``docs/surveys.md`` for the end-to-end workflow.
"""

from __future__ import annotations

from .render import (
    DEFAULT_EXPERTISE_PROMPT,
    DEFAULT_QUESTION_HEADER,
    DEFAULT_RATIONALE_PROMPT,
    DEFAULT_VERDICT_CHOICES,
    SurveyRespondent,
    render_implication_text,
    sanitize_export_tag,
)

__all__ = [
    "DEFAULT_EXPERTISE_PROMPT",
    "DEFAULT_QUESTION_HEADER",
    "DEFAULT_RATIONALE_PROMPT",
    "DEFAULT_VERDICT_CHOICES",
    "SurveyRespondent",
    "render_implication_text",
    "sanitize_export_tag",
]
