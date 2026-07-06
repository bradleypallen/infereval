"""SurveyMonkey API exporter.

SurveyMonkey doesn't have an offline survey-definition format the UI
can import. The only programmatic path is the
``POST /v3/surveys`` REST API, which requires a per-account access
token (developer.surveymonkey.com → My Apps → Settings → Access Token).

Two surfaces:

- :func:`build_surveymonkey_payload` — pure function that returns the
  JSON body for the API call plus the mapping sidecar. No I/O. Most of
  the test surface targets this.
- :func:`publish_to_surveymonkey` — the only function that touches the
  network. Uses stdlib ``urllib.request`` (no new deps); reads the
  token from the ``SURVEYMONKEY_ACCESS_TOKEN`` env var if not passed.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from .render import (
    DEFAULT_EXPERTISE_PROMPT,
    rationale_prompt,
    render_survey_question,
    sanitize_export_tag,
)

if TYPE_CHECKING:
    from ..benchmark import Benchmark
    from ..prompts import VerificationPrompt
    from ..templates import CoherenceFrame

log = logging.getLogger(__name__)

#: Default API base URL. SurveyMonkey runs the same API on a single
#: global host; EU customers may use ``https://eu-api.surveymonkey.com/v3``
#: instead, configurable via the ``base_url`` param.
DEFAULT_SURVEYMONKEY_BASE_URL: str = "https://api.surveymonkey.com/v3"


class SurveyMonkeyAuthError(RuntimeError):
    """Raised when ``SURVEYMONKEY_ACCESS_TOKEN`` is unset or the API
    rejects the supplied token."""


class SurveyMonkeyApiError(RuntimeError):
    """Raised when the API returns a non-2xx status that isn't an
    auth failure."""


def build_surveymonkey_payload(
    benchmark: Benchmark,
    *,
    title: str | None = None,
    randomize_items: bool = True,
    include_rationales: bool = True,
    expertise_prompt: str = DEFAULT_EXPERTISE_PROMPT,
    question_form: str = "support",
    coherence_frame: CoherenceFrame | None = None,
    verification_prompt: VerificationPrompt | None = None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Build the JSON body for ``POST /v3/surveys`` and the mapping
    sidecar.

    ``coherence_frame`` / ``verification_prompt`` are passed straight
    through to :func:`~infereval.survey.render.render_survey_question`,
    where ALL frame resolution happens. The resolved frame id (uniform
    across items in one export — asserted) is recorded on each mapping
    row.

    Returns
    -------
    payload
        Body of the ``POST /v3/surveys`` request. Shape follows the
        SurveyMonkey API v3 reference (pages → questions tree). Each
        item question carries ``presentation_options.randomize_questions``
        when randomization is requested.
    mapping
        Per-item mapping records — same shape as the Qualtrics /
        Google Forms mappings: ``item_id``,
        ``verdict_data_export_tag``, ``rationale_data_export_tag``,
        ``was_hashed``, ``question_form``, ``frame_id``. SurveyMonkey
        CSV column headers are literal
        question titles, so the CSV importer parses ``[item:<tag>]``
        out of the title in the same way as Google Forms.
    """
    effective_title = title if title is not None else f"Analyst recruitment for {benchmark.id}"

    # v0.9.2: each item now lives on its OWN page so the SurveyMonkey
    # ``page.description`` can carry the full premises/conclusion
    # prompt — keeping the question titles short means the CSV column
    # headers downstream are scannable. Pre-v0.9.2, all items shared
    # one ``Items`` page and the prompt was baked into the question
    # title (which became a 200-char column header in the export CSV).
    pages: list[dict[str, object]] = [
        {
            "title": "Welcome",
            "position": 1,
            "questions": [
                {
                    "headings": [{"heading": expertise_prompt}],
                    "position": 1,
                    "family": "open_ended",
                    "subtype": "essay",
                    "required": {"text": "This question requires an answer.", "type": "all"},
                }
            ],
        }
    ]

    mapping: list[dict[str, object]] = []
    resolved_frame_ids: set[str | None] = set()

    for i, item in enumerate(benchmark.items, start=1):
        tag, was_hashed = sanitize_export_tag(item.id)
        sq = render_survey_question(
            benchmark,
            item,
            question_form=question_form,
            coherence_frame=coherence_frame,
            verification_prompt=verification_prompt,
        )
        resolved_frame_ids.add(sq.frame_id)
        page_description = sq.full_text()
        verdict_title = f"Item {i} verdict"
        questions: list[dict[str, object]] = [
            {
                "headings": [{"heading": verdict_title}],
                "position": 1,
                "family": "single_choice",
                "subtype": "vertical",
                "answers": {
                    "choices": [
                        {"text": c, "position": j + 1}
                        for j, c in enumerate(sq.choices)
                    ],
                },
                "required": {"text": "Please select one.", "type": "one"},
            }
        ]
        rationale_tag: str | None = None
        if include_rationales:
            rationale_tag = f"{tag}_rationale"
            questions.append({
                "headings": [
                    {"heading": f"Item {i} rationale (optional)"},
                    {"heading": rationale_prompt(question_form)},
                ],
                "position": 2,
                "family": "open_ended",
                "subtype": "essay",
            })

        item_page: dict[str, object] = {
            "title": f"Item {i} of {benchmark.n}",
            "description": page_description,
            "position": i + 1,  # Welcome was position 1
            "questions": questions,
        }
        pages.append(item_page)

        mapping.append({
            "item_id": item.id,
            "verdict_data_export_tag": tag,
            "rationale_data_export_tag": rationale_tag,
            "was_hashed": was_hashed,
            "question_form": sq.question_form,
            "frame_id": sq.frame_id,
        })

    # One export = one frame (see qualtrics_qsf.build_qsf).
    assert len(resolved_frame_ids) <= 1, (
        f"survey export resolved multiple frame ids in one export: "
        f"{sorted(str(f) for f in resolved_frame_ids)}"
    )
    log.info(
        "survey.export.frame platform=surveymonkey benchmark=%s question_form=%s frame_id=%s",
        benchmark.id,
        question_form,
        next(iter(resolved_frame_ids), None),
    )

    payload: dict[str, object] = {
        "title": effective_title,
        "nickname": f"infereval-{benchmark.id}",
        "language": "en",
        "category": "research_efforts",
        "pages": pages,
    }

    # Randomization: with one-page-per-item, randomization happens at
    # the SURVEY level via ``page_randomization``. We keep page 1
    # (Welcome / expertise) fixed and randomize pages 2..N+1.
    if randomize_items:
        payload["page_randomization"] = {
            "type": "all",
            "pages_to_randomize": [p["position"] for p in pages[1:]],
        }

    return payload, mapping


def publish_to_surveymonkey(
    payload: dict[str, object],
    *,
    access_token: str | None = None,
    base_url: str = DEFAULT_SURVEYMONKEY_BASE_URL,
) -> dict[str, object]:
    """POST the payload to ``{base_url}/surveys``.

    Returns the parsed JSON response (with ``id``, ``href``, etc.).
    Reads the token from ``SURVEYMONKEY_ACCESS_TOKEN`` when
    ``access_token`` is not supplied.

    Raises
    ------
    SurveyMonkeyAuthError
        Token unset or rejected by the API (401/403).
    SurveyMonkeyApiError
        Any other non-2xx status; message includes the response body.
    """
    token = access_token or os.environ.get("SURVEYMONKEY_ACCESS_TOKEN")
    if not token:
        raise SurveyMonkeyAuthError(
            "SURVEYMONKEY_ACCESS_TOKEN is unset and no --surveymonkey-token "
            "was provided. Generate an access token at "
            "https://developer.surveymonkey.com/api/v3/#authentication "
            "and export it as SURVEYMONKEY_ACCESS_TOKEN."
        )

    url = f"{base_url.rstrip('/')}/surveys"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
        },
    )
    log.info(
        "surveymonkey.api.publish_start url=%s payload_bytes=%d",
        url, len(data),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 -- URL is controlled
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise SurveyMonkeyAuthError(
                f"SurveyMonkey API rejected the token (HTTP {exc.code}): {body}"
            ) from exc
        raise SurveyMonkeyApiError(
            f"SurveyMonkey API returned HTTP {exc.code}: {body}"
        ) from exc

    survey_id = parsed.get("id") if isinstance(parsed, dict) else None
    log.info("surveymonkey.api.publish_done survey_id=%s", survey_id)
    return parsed
