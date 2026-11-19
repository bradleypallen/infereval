"""Prolific hand-off for survey exports.

Prolific sends each participant to the survey with three URL query
parameters and expects them back on Prolific when they finish:

- the survey captures ``PROLIFIC_PID``, ``STUDY_ID`` and ``SESSION_ID``
  from the study link (configure the link in Prolific as
  ``...?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}``);
- at the end of the survey the participant is redirected to Prolific's
  completion URL carrying the study's completion code.

The exporter (``qualtrics_qsf.build_qsf``) writes both halves into the
``.qsf``; the CSV importer skips the captured columns so they are never
parsed as verdicts and never copied into the benchmark. Prolific ids are
pseudonymous personal data: they stay in the platform export, which is
where approval and payment are reconciled.
"""

from __future__ import annotations

import re

#: URL parameters Prolific appends to the study link, in Prolific's order.
PROLIFIC_FIELDS: tuple[str, ...] = ("PROLIFIC_PID", "STUDY_ID", "SESSION_ID")

#: Prolific's completion endpoint; ``{code}`` is the study's completion code.
PROLIFIC_COMPLETION_URL = "https://app.prolific.com/submissions/complete?cc={code}"

_COMPLETION_CODE = re.compile(r"[A-Za-z0-9]{4,32}")


def completion_url(code: str) -> str:
    """Return the redirect URL for ``code``, after validating it.

    Prolific completion codes are short alphanumeric strings (the study
    page shows them, e.g. ``C1A2B3C4``). Anything else — spaces, a pasted
    URL, an empty string — is rejected so a typo cannot silently send
    every participant to a broken completion link.
    """
    if not _COMPLETION_CODE.fullmatch(code):
        raise ValueError(
            f"invalid Prolific completion code {code!r}: expected 4-32 "
            f"letters or digits, as shown on the Prolific study page."
        )
    return PROLIFIC_COMPLETION_URL.format(code=code)
