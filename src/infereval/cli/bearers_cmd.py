"""``infereval bearers-import`` — build a benchmark from v0.5 sources.

Combines a *bearers file* (:mod:`infereval.bearers` grammar) with an *items
document* (a ``{"_meta": {...}, "items": [...]}`` JSON, the v0.5 shape) into a
validated framework :class:`~infereval.benchmark.Benchmark`, mapping every v0.5
concept onto its native field — no ``construction_metadata.source`` smuggling.

The items document's ``_meta`` supplies the benchmark's presentation and any
domain elicitation config:

- ``id`` / ``title`` / ``domain`` / ``description`` — benchmark identity;
- ``targets`` — declared succedent labels;
- ``verification_prompt`` / ``template_id`` / ``context_builders`` — optional
  elicitation config (framework defaults are used when absent);
- ``analysts`` — optional analyst panel. When absent (a pre-recruitment pilot),
  a single ``pending-analyst-panel`` stopgap is synthesized with all-``abstain``
  verdicts so the benchmark loads; each item's provisional read stays in its
  firewalled ``placeholder`` field. When a real panel *is* declared (e.g. after
  ``experiments/scripts/ingest_panel_verdicts.py`` records collected clinician
  verdicts), items that still carry an empty ``analyst_verdicts`` are padded to
  all-``abstain`` the same way — a neutral "no judgment recorded yet" fill for
  the still-unreviewed items, distinct from an analyst's positive abstain.

Per-item mapping: ``target`` → the single conclusion; ``ladder`` / ``variation``
/ ``target`` / ``placeholder`` → native item fields; ``note`` →
``construction_note``; ``monotonicity`` → ``monotonicity_step``;
``analyst_verdicts`` / ``analyst_rationales`` → the same-named native fields
(rationales pass through verbatim when present). Bearer
``@ordinal`` membership becomes each :class:`BearerModel`'s ``ordinal_family``,
and the file's ``@copresent`` / ``@entails`` / ``~regularity`` become the
benchmark's ``copresence_rules`` / ``entailment_rules`` / ``regularities``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import click

from infereval.bearers import BearersDoc, load_bearers_file
from infereval.benchmark import Benchmark

log = logging.getLogger(__name__)

_PENDING_ANALYST = {
    "id": "pending-analyst-panel",
    "display_name": "Analyst panel (pending recruitment)",
    "notes": (
        "Framework-required stopgap while the analyst panel is being recruited. "
        "All per-item verdicts are 'abstain' and carry no judgment. Each item's "
        "provisional read lives in its 'placeholder' field (dry-run only; "
        "firewalled from the measurement layer, never a κ source). Replace this "
        "entry with the real panel's verdicts once collected and regenerate."
    ),
}


def build_benchmark(doc: BearersDoc, items_doc: dict[str, Any]) -> Benchmark:
    """Map a bearers doc + a v0.5 items document onto a framework Benchmark."""
    meta: dict[str, Any] = items_doc.get("_meta", {})
    items_src: list[dict[str, Any]] = items_doc["items"]

    fam_map = doc.bearer_family_map()
    bearers: dict[str, Any] = {}
    for bid, expr in doc.bearers.items():
        bm: dict[str, Any] = {"expression": expr}
        if bid in fam_map:
            bm["ordinal_family"] = fam_map[bid]
        bearers[bid] = bm

    declared_analysts = meta.get("analysts")
    if declared_analysts is None:
        analysts: list[dict[str, Any]] = [dict(_PENDING_ANALYST)]
    else:
        analysts = list(declared_analysts)
    m = len(analysts)

    items: list[dict[str, Any]] = []
    for src in items_src:
        target = src.get("target")
        conclusions = [target] if target is not None else list(src.get("conclusions", []))
        verdicts = list(src.get("analyst_verdicts") or [])
        # Empty per-item verdicts are padded to all-``abstain`` (one per
        # declared analyst) so the benchmark loads. This is the framework's
        # neutral no-judgment fill: under the *synthesized* pending panel it
        # marks the whole benchmark as unadjudicated; under a *declared*
        # panel it marks the still-unreviewed items (e.g. a partial-ingest
        # where only the contested subset carries real verdicts). Abstain
        # here means "no judgment recorded", NOT the analyst's positive
        # "premises license neither target" claim — the honest per-item
        # record (empty ``analyst_verdicts``) stays in the v0.5 source; the
        # analyst declaration's ``notes`` document the partial-review firewall.
        if not verdicts:
            verdicts = ["abstain"] * m
        item: dict[str, Any] = {
            "id": src["id"],
            "premises": list(src["premises"]),
            "conclusions": conclusions,
            "analyst_verdicts": verdicts,
        }
        # Optional per-analyst rationales (AR-series): pass through verbatim
        # when the v0.5 source supplies them, so an ingested clinician verdict
        # carries its one-sentence reason into BenchmarkItem.analyst_rationales.
        # Length is validated against len(analysts) by Benchmark._check_consistency.
        rationales = src.get("analyst_rationales")
        if rationales is not None:
            item["analyst_rationales"] = list(rationales)
        for key in ("ladder", "variation", "target", "placeholder"):
            if src.get(key) is not None:
                item[key] = src[key]
        if "note" in src:
            item["construction_note"] = src["note"]
        if "monotonicity" in src:
            item["monotonicity_step"] = src["monotonicity"]
        items.append(item)

    benchmark: dict[str, Any] = {
        "id": meta.get("id", "imported-benchmark"),
        "bearers": bearers,
        "analysts": analysts,
        "items": items,
        "ordinal_families": doc.ordinal_families(),
        "copresence_rules": [{"families": list(fams)} for fams in doc.copresence],
        "entailment_rules": [
            {"antecedent": a, "consequent": b} for a, b in doc.entailments
        ],
        "regularities": [{"description": r} for r in doc.regularities],
        "targets": list(meta.get("targets", [])),
    }
    for key in (
        "title",
        "domain",
        "description",
        "verification_prompt",
        "template_id",
        "context_builders",
    ):
        if key in meta:
            benchmark[key] = meta[key]

    return Benchmark.model_validate(benchmark)


@click.command("bearers-import", help="Build a benchmark from a bearers file + items JSON.")
@click.argument(
    "bearers_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.argument(
    "items_path", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
@click.option(
    "--out",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write the benchmark JSON here. Omit to validate only (like --check).",
)
def bearers_import_cmd(bearers_path: Path, items_path: Path, out: Path | None) -> None:
    """Combine BEARERS_PATH and ITEMS_PATH into a validated framework benchmark."""
    log.info("bearers-import.start bearers=%s items=%s", bearers_path, items_path)
    doc = load_bearers_file(bearers_path)
    items_doc = json.loads(items_path.read_text(encoding="utf-8"))
    try:
        bench = build_benchmark(doc, items_doc)
    except Exception as exc:  # noqa: BLE001 — surface any validation/mapping error
        click.echo(f"ERROR: could not build benchmark: {exc}", err=True)
        log.error("bearers-import.failed err=%s", exc)
        sys.exit(1)

    click.echo(
        f"OK: built benchmark id={bench.id!r} "
        f"(bearers={len(bench.bearers)}, items={bench.n}, "
        f"ordinal_families={len(bench.ordinal_families)})"
    )
    if out is not None:
        bench.dump(out)
        click.echo(f"Wrote {out} ({out.stat().st_size} bytes)")
    log.info("bearers-import.ok id=%s wrote=%s", bench.id, out)
