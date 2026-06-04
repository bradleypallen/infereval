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
    DEFAULT_QUESTION_HEADER,
    DEFAULT_RATIONALE_PROMPT,
    DEFAULT_VERDICT_CHOICES,
    render_implication_text,
    sanitize_export_tag,
)

if TYPE_CHECKING:
    from ..benchmark import Benchmark

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
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Build the JSON body for ``POST /v3/surveys`` and the mapping
    sidecar.

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
        ``was_hashed``. SurveyMonkey CSV column headers are literal
        question titles, so the CSV importer parses ``[item:<tag>]``
        out of the title in the same way as Google Forms.
    """
    effective_title = title if title is not None else f"Analyst recruitment for {benchmark.id}"

    questions_page1: list[dict[str, object]] = [
        {
            "headings": [{"heading": expertise_prompt}],
            "position": 1,
            "family": "open_ended",
            "subtype": "essay",
            "required": {"text": "This question requires an answer.", "type": "all"},
        }
    ]

    item_questions: list[dict[str, object]] = []
    mapping: list[dict[str, object]] = []
    position = 1

    for i, item in enumerate(benchmark.items, start=1):
        tag, was_hashed = sanitize_export_tag(item.id)
        # Verdict-question title uses ``Item N of M`` as the parse
        # anchor the CSV importer keys on; respondents see only the
        # progress indicator + the rendered prompt.
        verdict_title = (
            f"Item {i} of {benchmark.n}\n\n"
            + DEFAULT_QUESTION_HEADER
            + "\n\n"
            + render_implication_text(benchmark, item)
        )
        item_questions.append({
            "headings": [{"heading": verdict_title}],
            "position": position,
            "family": "single_choice",
            "subtype": "vertical",
            "answers": {
                "choices": [{"text": c, "position": j + 1} for j, c in enumerate(DEFAULT_VERDICT_CHOICES)],
            },
            "required": {"text": "Please select one.", "type": "one"},
        })
        position += 1
        rationale_tag: str | None = None
        if include_rationales:
            rationale_tag = f"{tag}_rationale"
            # Rationale title carries the ``Item N rationale`` anchor.
            rationale_title = (
                f"Item {i} rationale (optional) — "
                + DEFAULT_RATIONALE_PROMPT
            )
            item_questions.append({
                "headings": [{"heading": rationale_title}],
                "position": position,
                "family": "open_ended",
                "subtype": "essay",
            })
            position += 1

        mapping.append({
            "item_id": item.id,
            "verdict_data_export_tag": tag,
            "rationale_data_export_tag": rationale_tag,
            "was_hashed": was_hashed,
        })

    items_page: dict[str, object] = {
        "title": "Items",
        "position": 2,
        "questions": item_questions,
    }
    if randomize_items:
        items_page["presentation_options"] = {"randomize_questions": "all"}

    payload: dict[str, object] = {
        "title": effective_title,
        "nickname": f"infereval-{benchmark.id}",
        "language": "en",
        "category": "research_efforts",
        "pages": [
            {
                "title": "Welcome",
                "position": 1,
                "questions": questions_page1,
            },
            items_page,
        ],
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
