"""Survey session pages around the benchmark items: consent, practice, quality checks, assignment.

Four optional, study-supplied specifications that the Qualtrics exporter
(:func:`~infereval.survey.qualtrics_qsf.build_qsf`) renders around the
benchmark items. Their wording is the study's (usually approved by an
ethics committee), so it is never hard-coded here: each is loaded from a
JSON file.

**Consent** (:class:`ConsentSpec`) — the survey's first page:

.. code-block:: json

    {
      "information": "How do people judge everyday reasoning? ...",
      "statements": ["I am 18 or older.", "..."],
      "agree": "I agree to take part",
      "decline": "I do not wish to take part"
    }

``agree`` / ``decline`` default to the two strings above. The page shows
the information text, one tick box per statement, and the agree/decline
choice. A participant who declines, or who leaves any statement unticked,
is taken straight to the end of the survey and sees no study item.

**Practice** (:class:`PracticeSpec`) — items rated after the instructions
and before the benchmark items, outside randomization, with no feedback:

.. code-block:: json

    {
      "intro": "First, three practice questions. ...",
      "items": [
        {"id": "kettle", "premises": ["..."], "conclusion": "..."}
      ],
      "outro": "That is the end of the practice. ..."
    }

``intro`` / ``outro`` are optional display-only pages. Practice items are
rendered through the same renderer and frame as the benchmark items, so
they look exactly like the real task; their answers are exported under
``practice_<id>`` and never imported as verdicts.

**Quality checks** (:class:`QualitySpec`) — checks that use only the
respondent's own answers, never agreement with a model:

.. code-block:: json

    {
      "attention_checks": [
        {"id": "ac1", "text": "This is an attention check. Please choose Bad.",
         "answer": "Bad"}
      ],
      "repeats": ["item_017", "item_042"]
    }

Each attention check is a page that looks like an item (same answer
labels, and the confidence question when the frame declares one), shown
among the items in random order and exported as ``check_<id>``; it is
passed when the chosen label equals ``answer``. Each listed item is shown
a second time after all items, in a new random order, exported as
``repeat_<tag>``. Neither is imported as a verdict;
``infereval survey import --quality-checks`` reports them per respondent
(see :mod:`infereval.survey.quality`).

**Assignment** (:class:`AssignmentSpec`) — an incomplete design, in which
each respondent rates every core item and a rotated subset of the rest:

.. code-block:: json

    {
      "core": ["item_001", "item_002"],
      "rotated_per_respondent": 100
    }

Every item not listed in ``core`` is a rotated item. Each respondent sees
all core items and ``rotated_per_respondent`` rotated ones, chosen by the
platform's even presentation so every rotated item is shown about equally
often across respondents. The core and rotated parts are each in random
order, and which part comes first is counterbalanced. Repeated items
(``repeats`` above) must be core items, so every respondent has seen them.
On import, an item a respondent was not shown is recorded as ``None``
(not rated), never as ``abstain``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: DataExportTag of the agree/decline question.
CONSENT_TAG = "consent"
#: DataExportTag of the consent-statements tick boxes.
CONSENT_STATEMENTS_TAG = "consent_statements"
#: DataExportTag prefix of practice answers (``practice_<id>``).
PRACTICE_TAG_PREFIX = "practice_"
#: DataExportTag prefix of attention-check answers (``check_<id>``).
CHECK_TAG_PREFIX = "check_"
#: DataExportTag prefix of repeated items' answers (``repeat_<item tag>``).
REPEAT_TAG_PREFIX = "repeat_"

DEFAULT_AGREE = "I agree to take part"
DEFAULT_DECLINE = "I do not wish to take part"

_PRACTICE_ID = re.compile(r"[A-Za-z0-9_]{1,40}")


def is_session_tag(tag: str) -> bool:
    """True for a DataExportTag owned by the consent, practice or quality-check pages.

    Benchmark item tags may not take these forms (the exporter refuses
    the collision), so the importer can skip them unconditionally.
    Qualtrics may split a multi-answer question into ``<tag>_<n>``
    columns, hence the ``consent_`` prefix match.
    """
    return (
        tag == CONSENT_TAG
        or tag.startswith(CONSENT_TAG + "_")
        or tag.startswith(PRACTICE_TAG_PREFIX)
        or tag.startswith(CHECK_TAG_PREFIX)
        or tag.startswith(REPEAT_TAG_PREFIX)
    )


@dataclass(frozen=True, slots=True)
class ConsentSpec:
    information: str
    statements: tuple[str, ...]
    agree: str = DEFAULT_AGREE
    decline: str = DEFAULT_DECLINE

    def __post_init__(self) -> None:
        if not self.information.strip():
            raise ValueError("consent: 'information' must not be empty")
        if not self.statements or any(not s.strip() for s in self.statements):
            raise ValueError("consent: 'statements' must be a non-empty list of non-empty strings")
        if len(set(self.statements)) != len(self.statements):
            raise ValueError("consent: 'statements' must be distinct")
        if not self.agree.strip() or not self.decline.strip() or self.agree == self.decline:
            raise ValueError("consent: 'agree' and 'decline' must be distinct, non-empty strings")


@dataclass(frozen=True, slots=True)
class PracticeItem:
    id: str
    premises: tuple[str, ...]
    conclusion: str

    def __post_init__(self) -> None:
        if not _PRACTICE_ID.fullmatch(self.id):
            raise ValueError(
                f"practice item id {self.id!r} must be 1-40 letters, digits or underscores"
            )
        if not self.premises or any(not p.strip() for p in self.premises):
            raise ValueError(f"practice item {self.id!r}: 'premises' must be non-empty strings")
        if not self.conclusion.strip():
            raise ValueError(f"practice item {self.id!r}: 'conclusion' must not be empty")

    @property
    def tag(self) -> str:
        return f"{PRACTICE_TAG_PREFIX}{self.id}"


@dataclass(frozen=True, slots=True)
class PracticeSpec:
    items: tuple[PracticeItem, ...]
    intro: str | None = None
    outro: str | None = None

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("practice: 'items' must not be empty")
        ids = [i.id for i in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError(f"practice: item ids must be distinct, got {ids}")


@dataclass(frozen=True, slots=True)
class AttentionCheck:
    id: str
    text: str
    answer: str

    def __post_init__(self) -> None:
        if not _PRACTICE_ID.fullmatch(self.id):
            raise ValueError(
                f"attention check id {self.id!r} must be 1-40 letters, digits or underscores"
            )
        if not self.text.strip():
            raise ValueError(f"attention check {self.id!r}: 'text' must not be empty")
        if not self.answer.strip():
            raise ValueError(f"attention check {self.id!r}: 'answer' must not be empty")

    @property
    def tag(self) -> str:
        return f"{CHECK_TAG_PREFIX}{self.id}"

    def passed(self, chosen: str | None) -> bool:
        return chosen is not None and chosen.strip() == self.answer.strip()


@dataclass(frozen=True, slots=True)
class QualitySpec:
    attention_checks: tuple[AttentionCheck, ...] = ()
    repeats: tuple[str, ...] = ()
    """Benchmark item ids shown a second time, after all items."""

    def __post_init__(self) -> None:
        if not self.attention_checks and not self.repeats:
            raise ValueError("quality checks: give 'attention_checks', 'repeats' or both")
        ids = [c.id for c in self.attention_checks]
        if len(set(ids)) != len(ids):
            raise ValueError(f"quality checks: attention check ids must be distinct, got {ids}")
        if len(set(self.repeats)) != len(self.repeats):
            raise ValueError("quality checks: 'repeats' must be distinct item ids")

    def check_items(self, item_ids: list[str]) -> None:
        """Raise unless every repeated id is one of ``item_ids``."""
        missing = [i for i in self.repeats if i not in set(item_ids)]
        if missing:
            raise ValueError(f"quality checks: repeated ids not in the benchmark: {missing}")


@dataclass(frozen=True)
class AssignmentSpec:
    core: tuple[str, ...]
    """Item ids every respondent rates."""
    rotated_per_respondent: int
    """How many of the other items each respondent rates."""

    def __post_init__(self) -> None:
        if not self.core:
            raise ValueError("assignment: 'core' must list at least one item id")
        if len(set(self.core)) != len(self.core):
            raise ValueError("assignment: 'core' must be distinct item ids")
        if self.rotated_per_respondent < 1:
            raise ValueError("assignment: 'rotated_per_respondent' must be at least 1")

    def rotated(self, item_ids: list[str]) -> list[str]:
        """The rotated item ids, in benchmark order; raises on a bad spec.

        Raises unless every core id is in ``item_ids`` and there are at
        least ``rotated_per_respondent`` other items.
        """
        known = set(item_ids)
        missing = [i for i in self.core if i not in known]
        if missing:
            raise ValueError(f"assignment: core ids not in the benchmark: {missing}")
        core = set(self.core)
        rotated = [i for i in item_ids if i not in core]
        if self.rotated_per_respondent > len(rotated):
            raise ValueError(
                f"assignment: rotated_per_respondent={self.rotated_per_respondent} but only "
                f"{len(rotated)} items are not core"
            )
        return rotated

    def expected_ratings(self, n_respondents: int, item_ids: list[str]) -> float:
        """Ratings per rotated item with ``n_respondents``, under even presentation."""
        return n_respondents * self.rotated_per_respondent / len(self.rotated(item_ids))


def _read_json(path: Path, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{what} file {path}: invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{what} file {path}: expected a JSON object")
    return data


def _check_keys(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}; allowed {sorted(allowed)}")


def load_consent(path: Path) -> ConsentSpec:
    """Load a :class:`ConsentSpec` from a JSON file (see module docs)."""
    data = _read_json(path, "consent")
    _check_keys(data, {"information", "statements", "agree", "decline"}, f"consent file {path}")
    spec = ConsentSpec(
        information=str(data.get("information", "")),
        statements=tuple(str(s) for s in data.get("statements", [])),
        agree=str(data.get("agree", DEFAULT_AGREE)),
        decline=str(data.get("decline", DEFAULT_DECLINE)),
    )
    log.info("survey.consent.load path=%s statements=%d", path, len(spec.statements))
    return spec


def load_practice(path: Path) -> PracticeSpec:
    """Load a :class:`PracticeSpec` from a JSON file (see module docs)."""
    data = _read_json(path, "practice")
    _check_keys(data, {"intro", "items", "outro"}, f"practice file {path}")
    items = []
    for raw in data.get("items", []):
        if not isinstance(raw, dict):
            raise ValueError(f"practice file {path}: each item must be an object")
        _check_keys(raw, {"id", "premises", "conclusion"}, f"practice file {path} item")
        items.append(
            PracticeItem(
                id=str(raw.get("id", "")),
                premises=tuple(str(p) for p in raw.get("premises", [])),
                conclusion=str(raw.get("conclusion", "")),
            )
        )
    spec = PracticeSpec(
        items=tuple(items),
        intro=data.get("intro"),
        outro=data.get("outro"),
    )
    log.info(
        "survey.practice.load path=%s items=%s intro=%s outro=%s",
        path, ",".join(i.id for i in spec.items), spec.intro is not None, spec.outro is not None,
    )
    return spec


def load_quality(path: Path) -> QualitySpec:
    """Load a :class:`QualitySpec` from a JSON file (see module docs)."""
    data = _read_json(path, "quality checks")
    _check_keys(data, {"attention_checks", "repeats"}, f"quality checks file {path}")
    checks = []
    for raw in data.get("attention_checks", []):
        if not isinstance(raw, dict):
            raise ValueError(f"quality checks file {path}: each attention check must be an object")
        _check_keys(raw, {"id", "text", "answer"}, f"quality checks file {path} attention check")
        checks.append(
            AttentionCheck(
                id=str(raw.get("id", "")),
                text=str(raw.get("text", "")),
                answer=str(raw.get("answer", "")),
            )
        )
    spec = QualitySpec(
        attention_checks=tuple(checks),
        repeats=tuple(str(i) for i in data.get("repeats", [])),
    )
    log.info(
        "survey.quality.load path=%s attention_checks=%s repeats=%d",
        path, ",".join(c.id for c in spec.attention_checks), len(spec.repeats),
    )
    return spec


def load_assignment(path: Path) -> AssignmentSpec:
    """Load an :class:`AssignmentSpec` from a JSON file (see module docs)."""
    data = _read_json(path, "assignment")
    _check_keys(data, {"core", "rotated_per_respondent"}, f"assignment file {path}")
    raw_k = data.get("rotated_per_respondent")
    if not isinstance(raw_k, int) or isinstance(raw_k, bool):
        raise ValueError(f"assignment file {path}: 'rotated_per_respondent' must be an integer")
    spec = AssignmentSpec(
        core=tuple(str(i) for i in data.get("core", [])),
        rotated_per_respondent=raw_k,
    )
    log.info(
        "survey.assignment.load path=%s core=%d rotated_per_respondent=%d",
        path, len(spec.core), spec.rotated_per_respondent,
    )
    return spec
