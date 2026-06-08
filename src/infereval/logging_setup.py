"""Structured JSONL logging for evaluation runs.

Why stdlib `logging` (not `structlog`):

- Zero new dependencies; researchers can ``pip install infereval`` and
  immediately ``jq`` or ``pandas.read_json("...", lines=True)`` the log.
- Library users already know the stdlib API. Library callers can attach
  their own handlers without infereval forcing a particular framework.

The trade-off is that stdlib's API is positional ``logger.info(msg, *args)``
rather than ``logger.info("event", **kv)``. We compensate with the small
:func:`log_event` helper that takes an event name and arbitrary keyword
fields, attaches them as ``extra=``, and lets :class:`JsonFormatter`
serialize everything (standard fields + any extras) to one JSON object
per line.

Reproducibility primitives:

- A per-run :class:`_RunContextFilter` injects ``run_id`` and any caller-
  supplied context (e.g. ``benchmark_id``) into every record, so the log
  is fully reconstructible without per-call boilerplate.
- A :func:`prompt_hash` helper computes a stable SHA-256 of any prompt
  string, recorded alongside the raw response so the prompt-to-response
  binding is auditable.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# v0.15.0: per-evaluate run_id scoped via contextvars so concurrent
# ``evaluate()`` calls in different threads/tasks don't cross-contaminate
# each other's JSONL log files. Set by :func:`configure_run_logging` for
# the duration of the context-manager body; read by the run-scoping
# filter attached to each FileHandler so a handler only emits records
# whose calling context's ``run_id`` matches the handler's own.
#
# Note: ``ContextVar`` is per-thread AND per-asyncio-task, but
# ``ThreadPoolExecutor`` does *not* automatically propagate context to
# worker threads. Code that fans out evaluate() work across a
# ThreadPoolExecutor needs to either submit via
# ``ctx.run(...)`` or call ``configure_run_logging`` inside each worker.
# In practice evaluate() itself is sequential (one item at a time); the
# fan-out lives in user orchestrators that call evaluate() per thread —
# each thread sets up its own logging via ``configure_run_logging``, so
# the contextvar is correctly populated in each thread of execution.
_current_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "infereval_run_id", default=None
)


def current_run_id() -> str | None:
    """Return the currently-active evaluation run_id, or ``None``.

    v0.15.0+: exposed for diagnostics; downstream code generally doesn't
    need to call this directly because :func:`configure_run_logging`
    plumbs the run_id transparently.
    """
    return _current_run_id.get()

# Builtin LogRecord attributes -- we don't want to serialize the formatter
# plumbing into structured logs.
_RESERVED_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)


def _iso_z(epoch_seconds: float) -> str:
    """Format a Unix timestamp as ISO 8601 with ms precision and ``Z`` suffix."""
    return (
        datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def prompt_hash(prompt: str) -> str:
    """Stable SHA-256 of a prompt string, prefixed ``sha256:``."""
    return f"sha256:{hashlib.sha256(prompt.encode('utf-8')).hexdigest()}"


class JsonFormatter(logging.Formatter):
    """Emit each :class:`~logging.LogRecord` as one JSON object per line.

    The log message (``record.getMessage()``) becomes the ``event`` field.
    Any ``extra={…}`` kwargs become top-level fields. Reserved stdlib
    attributes are dropped. Exceptions are formatted into ``exc_info``.

    The output is suitable for ``jq -c`` and ``pandas.read_json(lines=True)``.
    """

    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": _iso_z(record.created),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            if key in out:
                continue
            out[key] = value
        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


class _RunContextFilter(logging.Filter):
    """Inject persistent context (run_id, benchmark_id, …) into every record.

    v0.15.0: also enforces run scoping. If a non-``None`` ``run_id`` was
    provided to :func:`configure_run_logging`, this filter is paired with
    a specific FileHandler and:

    1. Reads the current contextvar ``run_id`` (set per-thread by
       :func:`configure_run_logging`).
    2. If the contextvar is set and doesn't match this handler's run_id,
       the record is dropped — preventing concurrent ``evaluate()``
       calls in different threads from cross-contaminating each other's
       JSONL log files (the v0.14.0 silent cross-thread bug).
    3. If the contextvar isn't set (legacy callers using the module
       logger outside a configured run), the record is allowed through
       and stamped with this handler's static context.
    """

    def __init__(
        self,
        context: dict[str, Any],
        *,
        handler_run_id: str | None = None,
    ) -> None:
        super().__init__()
        self.context = context
        self._handler_run_id = handler_run_id

    def filter(self, record: logging.LogRecord) -> bool:
        # v0.15.0: per-evaluate run scoping. Only enforce when this
        # filter is bound to a specific run; legacy module-logger use
        # (handler_run_id=None) is unaffected.
        if self._handler_run_id is not None:
            current = _current_run_id.get()
            if current is not None and current != self._handler_run_id:
                return False
        for key, value in self.context.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


@contextmanager
def configure_run_logging(
    log_path: Path | str | None,
    *,
    run_id: str | None = None,
    level: int = logging.INFO,
    extra_context: dict[str, Any] | None = None,
    logger_name: str = "infereval",
) -> Iterator[logging.FileHandler | None]:
    """Attach a JSONL :class:`~logging.FileHandler` to the package logger.

    Use as a context manager around an evaluation run. The handler is
    removed and closed on exit; the package logger's prior level is
    restored.

    Parameters
    ----------
    log_path
        Destination JSONL file. If ``None``, the context manager is a
        no-op (yields ``None``) so callers don't need to branch.
    run_id
        Stable run identifier propagated into every record via the
        context filter.
    level
        Minimum level the handler accepts. Default ``INFO``.
    extra_context
        Additional persistent fields (e.g. ``{"benchmark_id": "..."}``)
        added to every record alongside ``run_id``.
    logger_name
        Logger to attach to. Defaults to ``"infereval"`` so descendants
        (e.g. ``infereval.endorsement``) propagate through.

    Yields
    ------
    FileHandler or None
        The attached handler, or ``None`` if ``log_path`` was ``None``.
    """
    if log_path is None:
        yield None
        return

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(path, mode="a", encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())

    context: dict[str, Any] = dict(extra_context or {})
    if run_id is not None:
        context["run_id"] = run_id
    # v0.15.0: always attach a filter when a run_id is supplied so the
    # handler is run-scoped (drops cross-thread events from other runs).
    # When no run_id is given the filter is informational-only and lets
    # everything through (legacy single-call behaviour).
    if context or run_id is not None:
        handler.addFilter(_RunContextFilter(context, handler_run_id=run_id))

    pkg_logger = logging.getLogger(logger_name)
    pkg_logger.addHandler(handler)

    # stdlib logging gates twice: first the logger, then the handler.
    # Raise the logger floor only if it's stricter than the handler's level.
    saved_level = pkg_logger.level
    if saved_level == logging.NOTSET or saved_level > level:
        pkg_logger.setLevel(level)

    # v0.15.0: set the contextvar so the run-scoped filter on this
    # handler — and on any other concurrent handler — can detect which
    # run the event "belongs to". The token is reset on exit so nested
    # / sequential evaluate() calls restore the outer context cleanly.
    token = _current_run_id.set(run_id) if run_id is not None else None

    try:
        yield handler
    finally:
        handler.flush()
        pkg_logger.removeHandler(handler)
        pkg_logger.setLevel(saved_level)
        handler.close()
        if token is not None:
            _current_run_id.reset(token)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    """Emit ``event`` as the log message with ``fields`` attached for the formatter.

    Convention: ``event`` is a dotted name like ``"sample.completed"`` or
    ``"run.started"``; fields are JSON-serializable scalars / containers.
    """
    if fields:
        logger.info(event, extra=fields)
    else:
        logger.info(event)


__all__ = [
    "JsonFormatter",
    "configure_run_logging",
    "current_run_id",
    "log_event",
    "prompt_hash",
]
