"""Ingest the clinical pilot panel's contested-item verdicts into the benchmark.

RUNBOOK — the ten-minute flow (run from the repo root)
======================================================

When the clinician reviewer returns verdicts for the six contested items,
turning them into a measurable benchmark is a five-step, ~ten-minute job:

1. **Fill the template.** Copy the template and enter, for each of the six
   contested items (A0, A4, A8, B7, B8, D1), the clinician's verdict
   (``good`` / ``bad`` / ``abstain``) plus a one-sentence rationale::

       cp examples/clinical_pilot/panel_verdicts_TEMPLATE.json \\
          examples/clinical_pilot/panel_verdicts.json
       # edit panel_verdicts.json: set "analyst_id", "date", and each
       # item's "verdict" + "rationale".

2. **Dry-run the ingest** to eyeball the diff (writes nothing)::

       python experiments/scripts/ingest_panel_verdicts.py \\
           --verdicts examples/clinical_pilot/panel_verdicts.json --dry-run

3. **Ingest for real.** This updates the v0.5 source in place (recording
   each verdict as the item's ``analyst_verdicts`` + ``analyst_rationales``
   and declaring the real analyst on ``_meta.analysts``) and regenerates the
   canonical ``benchmark.json`` via the native loader — the same path as
   ``examples/clinical_pilot/convert.py``::

       python experiments/scripts/ingest_panel_verdicts.py \\
           --verdicts examples/clinical_pilot/panel_verdicts.json

   It prints: items updated, old-vs-new canonical benchmark hash, and a
   reminder that any pre-ingestion η artifacts are now hash-incompatible.

4. **Re-run the model panel capture.** Because the benchmark hash changed,
   the pre-ingestion dry-run η files (``…/dryrun_2026-06-30/*``) will be
   *refused* by ``infereval retest``'s setup-conformance check (by design —
   they were captured against a different benchmark). Re-capture the panel
   against the freshly-regenerated benchmark, e.g. with the existing
   dry-run harness::

       bash experiments/results/clinical_pilot/dryrun_2026-06-30/run.sh
       # (or your current 6-model panel capture script)

5. **Report / metrics are now meaningful.** With real analyst verdicts on
   the six contested items, κ_C (model-vs-clinician) and the ladder
   monotonicity stratification stop being all-abstain placeholders::

       infereval describe --items examples/clinical_pilot/benchmark.json
       infereval report <the re-captured η> examples/clinical_pilot/benchmark.json
       infereval monotonicity <the re-captured η> examples/clinical_pilot/benchmark.json

WHAT THIS SCRIPT DOES
=====================

Input is a *verdicts file* (see ``panel_verdicts_TEMPLATE.json``)::

    {"analyst_id": "clinical-analyst-1", "date": "2026-07-05",
     "verdicts": {"A0": {"verdict": "bad", "rationale": "…"}, …}}

For each verdicted item the script sets, on the v0.5 source item,
``analyst_verdicts = [verdict]`` and ``analyst_rationales = [rationale]``,
and declares the real analyst (id taken from the verdicts file) on
``_meta.analysts`` — the single place the panel is declared. The native
loader (:func:`infereval.cli.bearers_cmd.build_benchmark`) then maps those
straight onto ``BenchmarkItem.analyst_verdicts`` / ``.analyst_rationales``
and the benchmark's ``analysts`` panel. The other 29 unanimous items keep an
empty ``analyst_verdicts`` in the source (no verdict collected yet); the
loader pads them to a single neutral ``abstain`` in the derived benchmark so
it validates — a "no judgment recorded" fill, documented in the analyst's
``notes``, NOT a positive clinician abstain.

Placeholder-firewall decision
------------------------------
The protocol says a verdict "replaces the placeholder", but we do **not**
delete the ``placeholder`` field. Downstream never reads it as a label (the
measurement layer is mechanically firewalled from it; see the placeholder
firewall in ``metrics.py`` / ``tests/unit/test_placeholder_firewall.py``),
so the safe, auditable move is to *keep* ``placeholder`` as construction
history and let the real ``analyst_verdicts`` be the label that flows to κ.
"Replaces" is therefore realized as "is superseded by", not "erased".

Validation
----------
- every verdict item id must exist in the benchmark (else ERROR + exit 1);
- each verdict value must be one of good/bad/abstain (else ERROR + exit 1);
- each rationale must be non-empty (else ERROR + exit 1);
- ``analyst_id`` must be non-empty (else ERROR + exit 1);
- a verdict on an item OUTSIDE the six-item contested set is a loud WARN
  (the script still proceeds — the contested set is a convention, not a lock).

``--dry-run`` prints the planned per-item diff + the hash delta and writes
nothing. Structured JSONL logging (``--log``) records every decision for
post-run analysis, per repo convention.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

from infereval.bearers import load_bearers_file  # noqa: E402
from infereval.cli.bearers_cmd import build_benchmark  # noqa: E402
from infereval.evaluation import canonical_benchmark_hash  # noqa: E402
from infereval.logging_setup import configure_run_logging, log_event  # noqa: E402

log = logging.getLogger("infereval.ingest_panel_verdicts")

PILOT_DIR = REPO_ROOT / "examples" / "clinical_pilot"
DEFAULT_BEARERS = PILOT_DIR / "bearers_v0.5.txt"
DEFAULT_BENCHMARK_V05 = PILOT_DIR / "benchmark_v0.5.json"
DEFAULT_OUT_BENCHMARK = PILOT_DIR / "benchmark.json"

VALID_VERDICTS = {"good", "bad", "abstain"}

#: The six items the model panel split on (contested_items_2026-06-30.md).
#: Verdicts on any other id are allowed but warned about.
CONTESTED_ITEM_IDS = frozenset({"A0", "A4", "A8", "B7", "B8", "D1"})


class IngestError(Exception):
    """A fatal validation error that should abort the ingest with exit 1."""


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _analyst_declaration(analyst_id: str, date: str, n_reviewed: int) -> dict[str, Any]:
    """The single real-analyst entry written to ``_meta.analysts``.

    Depersonalized by construction: the id comes from the verdicts file
    (the neutral ``clinical-analyst-1``); the display name and notes name
    no institution or individual.
    """
    date_clause = f" on {date}" if date else ""
    return {
        "id": analyst_id,
        "display_name": "Clinical pilot reviewer",
        "notes": (
            f"Clinical reviewer for the CPE-vs-ARDS pilot. Verdicts recorded"
            f"{date_clause} for {n_reviewed} contested item(s) where the model "
            "panel split; the remaining items are unreviewed and appear as a "
            "neutral 'abstain' in the derived benchmark ('no judgment recorded "
            "yet', NOT a 'premises license neither target' claim). The honest "
            "per-item record (empty analyst_verdicts) is kept in the v0.5 source."
        ),
    }


def validate_verdicts(
    verdicts_doc: dict[str, Any],
    benchmark_item_ids: set[str],
) -> tuple[str, str, dict[str, dict[str, str]]]:
    """Validate the verdicts file against the benchmark; return the parts.

    Returns ``(analyst_id, date, verdicts)``. Raises :class:`IngestError`
    on any fatal problem (unknown id, bad verdict value, empty rationale,
    empty analyst id). Verdicts on non-contested items only WARN.
    """
    analyst_id = str(verdicts_doc.get("analyst_id", "")).strip()
    if not analyst_id:
        raise IngestError("verdicts file is missing a non-empty 'analyst_id'.")

    date = str(verdicts_doc.get("date", "")).strip()

    raw_verdicts = verdicts_doc.get("verdicts")
    if not isinstance(raw_verdicts, dict) or not raw_verdicts:
        raise IngestError("verdicts file has no 'verdicts' object with any items.")

    cleaned: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for item_id, payload in raw_verdicts.items():
        if not isinstance(payload, dict):
            errors.append(f"{item_id}: entry is not an object with verdict/rationale.")
            continue
        verdict = str(payload.get("verdict", "")).strip()
        rationale = str(payload.get("rationale", "")).strip()

        if item_id not in benchmark_item_ids:
            errors.append(
                f"{item_id}: unknown item id (not present in the benchmark)."
            )
            continue
        if verdict not in VALID_VERDICTS:
            errors.append(
                f"{item_id}: verdict {verdict!r} is not one of "
                f"{sorted(VALID_VERDICTS)}."
            )
            continue
        if not rationale:
            errors.append(f"{item_id}: rationale is empty.")
            continue

        if item_id not in CONTESTED_ITEM_IDS:
            msg = (
                f"verdict supplied for NON-CONTESTED item {item_id!r} "
                f"(contested set = {sorted(CONTESTED_ITEM_IDS)}); proceeding, "
                "but double-check this was intentional."
            )
            log.warning("ingest.warn.non_contested item_id=%s", item_id)
            print(f"WARNING: {msg}", file=sys.stderr)

        cleaned[item_id] = {"verdict": verdict, "rationale": rationale}

    if errors:
        raise IngestError(
            "verdicts file failed validation:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
    if not cleaned:
        raise IngestError("no valid verdicts to ingest after validation.")

    return analyst_id, date, cleaned


def apply_verdicts(
    items_doc: dict[str, Any],
    analyst_id: str,
    date: str,
    verdicts: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], list[str]]:
    """Return a new items_doc with verdicts applied; also the updated ids.

    Does not mutate the input. Declares the real analyst on ``_meta.analysts``
    and records each verdict as ``analyst_verdicts`` + ``analyst_rationales``
    on its item. ``placeholder`` is deliberately left in place (see the
    module docstring's placeholder-firewall decision).
    """
    updated = copy.deepcopy(items_doc)
    updated.setdefault("_meta", {})["analysts"] = [
        _analyst_declaration(analyst_id, date, len(verdicts))
    ]

    updated_ids: list[str] = []
    by_id = {it["id"]: it for it in updated["items"]}
    for item_id, payload in verdicts.items():
        item = by_id[item_id]
        item["analyst_verdicts"] = [payload["verdict"]]
        item["analyst_rationales"] = [payload["rationale"]]
        updated_ids.append(item_id)

    return updated, sorted(updated_ids)


def _hash_from_items_doc(bearers_path: Path, items_doc: dict[str, Any]) -> str:
    doc = load_bearers_file(bearers_path)
    bench = build_benchmark(doc, items_doc)
    return canonical_benchmark_hash(bench)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Ingest clinician panel verdicts into the clinical-pilot benchmark."
    )
    p.add_argument(
        "--verdicts",
        type=Path,
        required=True,
        help="Filled-in verdicts JSON (see panel_verdicts_TEMPLATE.json).",
    )
    p.add_argument(
        "--bearers",
        type=Path,
        default=DEFAULT_BEARERS,
        help=f"Bearers file for the native loader (default: {DEFAULT_BEARERS.name}).",
    )
    p.add_argument(
        "--benchmark-v05",
        type=Path,
        default=DEFAULT_BENCHMARK_V05,
        help=f"v0.5 source items JSON, updated in place (default: {DEFAULT_BENCHMARK_V05.name}).",
    )
    p.add_argument(
        "--out-benchmark",
        type=Path,
        default=DEFAULT_OUT_BENCHMARK,
        help=f"Regenerated canonical benchmark (default: {DEFAULT_OUT_BENCHMARK.name}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned diff + hash delta; write nothing.",
    )
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Optional JSONL structured-log path for post-run analysis.",
    )
    args = p.parse_args(argv)

    with configure_run_logging(
        args.log,
        run_id="ingest-panel-verdicts",
        extra_context={"verdicts_file": str(args.verdicts)},
    ):
        return _run(args)


def _run(args: argparse.Namespace) -> int:
    log_event(
        log,
        "ingest.start",
        verdicts=str(args.verdicts),
        benchmark_v05=str(args.benchmark_v05),
        out_benchmark=str(args.out_benchmark),
        dry_run=bool(args.dry_run),
    )

    try:
        verdicts_doc = _load_json(args.verdicts)
        items_doc = _load_json(args.benchmark_v05)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read input: {exc}", file=sys.stderr)
        log.error("ingest.read_failed err=%s", exc)
        return 1

    benchmark_item_ids = {it["id"] for it in items_doc.get("items", [])}

    try:
        analyst_id, date, verdicts = validate_verdicts(verdicts_doc, benchmark_item_ids)
    except IngestError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        log.error("ingest.validation_failed err=%s", exc)
        return 1

    # Old hash: build from the UNMODIFIED source (== what the committed
    # benchmark.json and every pre-ingestion η were captured against).
    try:
        old_hash = _hash_from_items_doc(args.bearers, items_doc)
    except Exception as exc:  # noqa: BLE001 — surface any loader/mapping error
        print(f"ERROR: could not build the pre-ingestion benchmark: {exc}", file=sys.stderr)
        log.error("ingest.old_build_failed err=%s", exc)
        return 1

    updated_doc, updated_ids = apply_verdicts(items_doc, analyst_id, date, verdicts)

    try:
        doc = load_bearers_file(args.bearers)
        new_bench = build_benchmark(doc, updated_doc)
    except Exception as exc:  # noqa: BLE001 — surface any validation error
        print(f"ERROR: could not build the post-ingestion benchmark: {exc}", file=sys.stderr)
        log.error("ingest.new_build_failed err=%s", exc)
        return 1
    new_hash = canonical_benchmark_hash(new_bench)

    # ---- Report ----------------------------------------------------------
    print(f"Analyst declared: {analyst_id!r} (date: {date or 'unspecified'})")
    print(f"Items updated ({len(updated_ids)}):")
    for item_id in updated_ids:
        payload = verdicts[item_id]
        note = "" if item_id in CONTESTED_ITEM_IDS else "  [NON-CONTESTED]"
        print(
            f"  {item_id}: analyst_verdicts [] -> [{payload['verdict']!r}]"
            f"  rationale: {payload['rationale']!r}{note}"
        )
        log_event(
            log,
            "ingest.item_updated",
            item_id=item_id,
            verdict=payload["verdict"],
            contested=item_id in CONTESTED_ITEM_IDS,
        )
    print(f"Old canonical benchmark hash: {old_hash}")
    print(f"New canonical benchmark hash: {new_hash}")
    print(
        "Hash changed."
        if old_hash != new_hash
        else "Hash UNCHANGED (no effective change — check the verdicts file)."
    )
    print(
        "REMINDER: pre-ingestion η artifacts (e.g. the dry-run panel captures) "
        "carry the OLD benchmark hash and will be REFUSED by `infereval retest`'s "
        "setup-conformance check (by design). Re-run the 6-model panel capture "
        "against the regenerated benchmark before computing κ_C / retest."
    )

    log_event(
        log,
        "ingest.hashes",
        old_hash=old_hash,
        new_hash=new_hash,
        hash_changed=old_hash != new_hash,
        n_updated=len(updated_ids),
    )

    if args.dry_run:
        print("\n--dry-run: no files written.")
        log_event(log, "ingest.dry_run_complete")
        return 0

    # ---- Write -----------------------------------------------------------
    # Update the v0.5 source in place (durable record: convert.py reproduces
    # benchmark.json from it), then regenerate the canonical benchmark via the
    # native path — byte-for-byte the same as convert.py / bearers-import.
    args.benchmark_v05.write_text(
        json.dumps(updated_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote v0.5 source: {args.benchmark_v05}")
    new_bench.dump(args.out_benchmark)
    print(f"Wrote benchmark:   {args.out_benchmark} ({args.out_benchmark.stat().st_size} bytes)")
    log_event(
        log,
        "ingest.wrote",
        benchmark_v05=str(args.benchmark_v05),
        out_benchmark=str(args.out_benchmark),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
