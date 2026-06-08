"""Tests for ``infereval.logging_setup``: JsonFormatter, configure_run_logging, log_event, prompt_hash."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from infereval.logging_setup import (
    JsonFormatter,
    configure_run_logging,
    log_event,
    prompt_hash,
)

# ---- prompt_hash ----------------------------------------------------------


class TestPromptHash:
    def test_stable_for_same_input(self) -> None:
        assert prompt_hash("hello") == prompt_hash("hello")

    def test_changes_on_input_change(self) -> None:
        assert prompt_hash("hello") != prompt_hash("hello!")

    def test_prefixed_with_sha256(self) -> None:
        assert prompt_hash("anything").startswith("sha256:")

    def test_hex_length(self) -> None:
        h = prompt_hash("x")
        assert len(h) == len("sha256:") + 64

    def test_handles_unicode(self) -> None:
        # The paper has TeX-source bearer expressions; round-trip ok
        h = prompt_hash("$a$ is a stop sign and it is nighttime")
        assert h.startswith("sha256:")


# ---- JsonFormatter --------------------------------------------------------


def _format_record(record: logging.LogRecord, formatter: JsonFormatter) -> dict:
    return json.loads(formatter.format(record))


class TestJsonFormatter:
    def test_emits_required_fields(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="infereval.test",
            level=logging.INFO,
            pathname="x.py",
            lineno=1,
            msg="some.event",
            args=(),
            exc_info=None,
        )
        out = _format_record(record, fmt)
        assert "ts" in out
        assert out["level"] == "INFO"
        assert out["logger"] == "infereval.test"
        assert out["event"] == "some.event"

    def test_ts_is_iso_z(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="", lineno=0,
            msg="e", args=(), exc_info=None,
        )
        out = _format_record(record, fmt)
        assert out["ts"].endswith("Z")
        assert "T" in out["ts"]  # ISO 8601 'T' separator
        # millisecond precision: 3 digits after the dot
        assert out["ts"][-5:-1].startswith(".")  # ".dddZ"

    def test_extras_attached(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="", lineno=0,
            msg="e", args=(), exc_info=None,
        )
        record.item_id = "row-2"
        record.sample_index = 1
        out = _format_record(record, fmt)
        assert out["item_id"] == "row-2"
        assert out["sample_index"] == 1

    def test_reserved_attrs_dropped(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="/a.py", lineno=42,
            msg="e", args=(), exc_info=None,
        )
        out = _format_record(record, fmt)
        # stdlib LogRecord noise should not leak
        assert "pathname" not in out
        assert "lineno" not in out
        assert "filename" not in out
        assert "funcName" not in out

    def test_message_with_args_substituted(self) -> None:
        fmt = JsonFormatter()
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="", lineno=0,
            msg="event %s/%d", args=("abc", 7), exc_info=None,
        )
        out = _format_record(record, fmt)
        # Standard logging substitution
        assert out["event"] == "event abc/7"

    def test_exception_info_serialized(self) -> None:
        fmt = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="x", level=logging.ERROR, pathname="", lineno=0,
            msg="error.event", args=(), exc_info=exc_info,
        )
        out = _format_record(record, fmt)
        assert "exc_info" in out
        assert "ValueError" in out["exc_info"]
        assert "boom" in out["exc_info"]


# ---- configure_run_logging ------------------------------------------------


class TestConfigureRunLogging:
    def test_none_path_is_noop(self) -> None:
        with configure_run_logging(None) as handler:
            assert handler is None
            # Logging here should not crash
            logging.getLogger("infereval").info("nothing happens")

    def test_writes_jsonl_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        with configure_run_logging(log_path, run_id="abc-123"):
            log_event(logging.getLogger("infereval"), "test.event", x=1, y="z")

        assert log_path.exists()
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "test.event"
        assert record["x"] == 1
        assert record["y"] == "z"
        assert record["run_id"] == "abc-123"

    def test_handler_removed_on_exit(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        pkg = logging.getLogger("infereval")
        n_before = len(pkg.handlers)
        with configure_run_logging(log_path, run_id="x"):
            assert len(pkg.handlers) == n_before + 1
        assert len(pkg.handlers) == n_before

    def test_logger_level_restored_on_exit(self, tmp_path: Path) -> None:
        pkg = logging.getLogger("infereval")
        original = pkg.level
        try:
            pkg.setLevel(logging.WARNING)
            with configure_run_logging(tmp_path / "x.jsonl", run_id="x"):
                # Inside: level is raised to INFO so events propagate
                assert pkg.level <= logging.INFO
            # On exit: restored to WARNING
            assert pkg.level == logging.WARNING
        finally:
            pkg.setLevel(original)

    def test_extra_context_injected(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        with configure_run_logging(
            log_path,
            run_id="r1",
            extra_context={"benchmark_id": "bench-1", "framework_version": "0.1.0"},
        ):
            log_event(logging.getLogger("infereval"), "x")

        record = json.loads(log_path.read_text().splitlines()[0])
        assert record["run_id"] == "r1"
        assert record["benchmark_id"] == "bench-1"
        assert record["framework_version"] == "0.1.0"

    def test_descendant_loggers_propagate(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        with configure_run_logging(log_path, run_id="r"):
            log_event(logging.getLogger("infereval.endorsement"), "child.event")

        record = json.loads(log_path.read_text().splitlines()[0])
        assert record["event"] == "child.event"
        assert record["logger"] == "infereval.endorsement"
        assert record["run_id"] == "r"

    def test_multiple_events_one_per_line(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        with configure_run_logging(log_path, run_id="r"):
            logger = logging.getLogger("infereval")
            for i in range(5):
                log_event(logger, "tick", i=i)

        lines = log_path.read_text().splitlines()
        assert len(lines) == 5
        for i, line in enumerate(lines):
            record = json.loads(line)
            assert record["event"] == "tick"
            assert record["i"] == i


class TestConcurrentRunIsolation:
    """v0.15.0+: concurrent ``configure_run_logging`` calls in different
    threads must write to separate JSONL files without cross-contamination
    (the v0.14.0 cross-thread logger contamination bug fix).
    """

    def test_concurrent_runs_do_not_cross_contaminate(self, tmp_path: Path) -> None:
        """Two threads each run a configure_run_logging block; each
        thread's events land only in its own log file."""
        import threading

        log_a = tmp_path / "run-a.jsonl"
        log_b = tmp_path / "run-b.jsonl"
        # Use a barrier so both threads have their handler attached
        # *before* either thread logs — this forces the cross-thread
        # broadcast scenario the v0.14.0 bug exhibited.
        barrier = threading.Barrier(2)
        # And another barrier so neither thread tears down its handler
        # before the other has finished logging.
        teardown_barrier = threading.Barrier(2)

        def runner(log_path: Path, run_id: str, n: int) -> None:
            logger = logging.getLogger("infereval")
            with configure_run_logging(log_path, run_id=run_id):
                barrier.wait()
                for i in range(n):
                    log_event(logger, "tick", run=run_id, i=i)
                teardown_barrier.wait()

        ta = threading.Thread(target=runner, args=(log_a, "A", 5))
        tb = threading.Thread(target=runner, args=(log_b, "B", 5))
        ta.start()
        tb.start()
        ta.join()
        tb.join()

        for path, expected_run in [(log_a, "A"), (log_b, "B")]:
            lines = path.read_text().splitlines()
            records = [json.loads(line) for line in lines]
            # Every record in this file must belong to this run — no
            # cross-thread bleed-through.
            assert all(r.get("run_id") == expected_run for r in records), (
                f"{path.name} contaminated with foreign run_id: "
                f"{[r.get('run_id') for r in records]}"
            )
            # And we got every tick we issued (no drops).
            assert len(records) == 5

    def test_thread_pool_executor_isolation(self, tmp_path: Path) -> None:
        """v0.15.0+: real-world orchestrators (e.g. the Phase 2 append
        script) submit evaluate() calls via concurrent.futures.ThreadPoolExecutor.
        TPE does NOT auto-propagate the parent's contextvars — each
        worker thread starts with the contextvar at its default.

        Our fix relies on configure_run_logging being called *inside*
        each worker (which sets the contextvar in that worker's
        context). This test confirms that pattern works under TPE.
        If it breaks, user-orchestrators that fan out evaluate() via
        TPE would see cross-thread bleed-through despite the v0.15.0
        fix — and we'd need to document the requirement or use
        copy_context().run for submissions.
        """
        from concurrent.futures import ThreadPoolExecutor

        runs: list[tuple[Path, str, int]] = [
            (tmp_path / f"run-{i}.jsonl", f"R{i}", 5) for i in range(4)
        ]

        def worker(log_path: Path, run_id: str, n: int) -> None:
            # Pattern: each worker calls configure_run_logging itself.
            # This is what infereval.evaluation.evaluate() does — the
            # contextvar is set in the worker's own context, not the
            # parent's.
            logger = logging.getLogger("infereval")
            with configure_run_logging(log_path, run_id=run_id):
                for i in range(n):
                    log_event(logger, "tick", run=run_id, i=i)

        # Submit all four jobs and let them run truly concurrently.
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(worker, *args) for args in runs]
            for f in futures:
                f.result()  # propagate any exceptions

        # Each file must contain exactly its own run's events.
        for log_path, expected_run, _ in runs:
            records = [
                json.loads(line) for line in log_path.read_text().splitlines()
            ]
            assert all(r.get("run_id") == expected_run for r in records), (
                f"{log_path.name} contaminated with foreign run_id: "
                f"{[r.get('run_id') for r in records]}"
            )
            assert len(records) == 5

    def test_no_run_id_falls_through_unchanged(self, tmp_path: Path) -> None:
        """When no run_id is set anywhere, all handlers receive all
        events (legacy behaviour preserved for tests and direct callers)."""
        log_path = tmp_path / "run.jsonl"
        with configure_run_logging(log_path):  # no run_id
            log_event(logging.getLogger("infereval"), "plain")
        lines = log_path.read_text().splitlines()
        assert len(lines) == 1


# ---- log_event ------------------------------------------------------------


class TestLogEvent:
    def test_no_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="infereval"):
            log_event(logging.getLogger("infereval"), "plain.event")
        records = [r for r in caplog.records if r.getMessage() == "plain.event"]
        assert len(records) == 1

    def test_fields_attached_as_extra(self, tmp_path: Path) -> None:
        log_path = tmp_path / "run.jsonl"
        with configure_run_logging(log_path, run_id="r"):
            log_event(logging.getLogger("infereval"), "evt", a=1, b="two")

        record = json.loads(log_path.read_text().splitlines()[0])
        assert record["a"] == 1
        assert record["b"] == "two"
