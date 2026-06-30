"""Convert clinical_pilot v0.5 sources into a framework-compatible benchmark.json.

The clinical_pilot benchmark uses a richer schema than the current framework
``Benchmark`` Pydantic model supports (ordinal families, monotonicity ladders,
variation typology, single-target items, external bearers file with @ordinal /
@copresent / @entails annotations). This converter is a v0.16.x stopgap that
maps the v0.5 sources onto the current schema so ``infereval evaluate`` can
fire the pre-clinician dry-run gate today, before the framework's v0.17.x
work catches up.

What survives the conversion:
    - ``tags`` carries human-readable shortcuts:
        ``ladder:A``, ``variation:strengthen``, ``target:cpe``, etc.
    - ``construction_metadata.source`` carries a JSON-encoded blob with
      the v0.5 extras the framework's data model doesn't represent yet:
        - ladder, variation, placeholder, monotonicity, note, source_target
      Downstream tooling that understands the v0.5 schema can parse this
      string back into a dict; everything else just sees a string.
    - ``factor_levels`` carries the ordinal-family tier assignments per
      item (e.g. ``{"bnp": "bnp_vhi"}``).

What's lossy:
    - Bearers file annotations (@ordinal, @copresent, @entails) become
      benchmark-level ``factors`` + ``factor_kinds`` (ordinal_families) and
      free-text notes in the description (copresent + entailment rules).
      The framework currently has no first-class @copresent / @entails
      enforcement, so these are informational until v0.17.x adds them.
    - F1's placeholder ("contested") collapses to "abstain" in the
      construction_metadata.placeholder field — recorded as
      ``placeholder_normalized=True`` with the original preserved at
      ``placeholder_v05``.

Analyst panel handling:
    The v0.5 spec is explicit that ``placeholder`` is not an analyst label;
    actual analyst verdicts will be collected from clinicians later. The
    framework requires m >= 1 analysts, so the converter inserts a single
    placeholder analyst whose per-item verdicts are all ``abstain`` and
    whose ``notes`` say "pending clinician panel". This is enough to make
    the benchmark loadable for the dry-run gate; analyst-comparison metrics
    against this placeholder are not meaningful and should be ignored until
    real clinician verdicts land.

Usage:
    python examples/clinical_pilot/convert.py
        # writes examples/clinical_pilot/benchmark.json

    python examples/clinical_pilot/convert.py --check
        # parse + validate without writing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
BEARERS_V05 = HERE / "bearers_v0.5.txt"
BENCHMARK_V05 = HERE / "benchmark_v0.5.json"
OUTPUT = HERE / "benchmark.json"

# v0.5 placeholders that aren't in the framework's Verdict enum.
# "contested" is the methodology's "panel will likely split" marker; closest
# Verdict-enum match is "abstain" (framework's "can't tell" answer).
PLACEHOLDER_NORMALIZE = {"contested": "abstain"}


def parse_bearers_file(path: Path) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    """Parse bearers_v0.5.txt.

    Returns ``(bearers, ordinal_families, annotations_summary)`` where
    ``bearers`` maps id → expression, ``ordinal_families`` maps family-name →
    ordered list of tier ids (from @ordinal annotations), and
    ``annotations_summary`` is a list of free-text @copresent / @entails
    lines to thread into the benchmark description.
    """
    bearers: dict[str, str] = {}
    ordinal_families: dict[str, list[str]] = {}
    annotation_summary: list[str] = []
    # Match @ordinal lines in comments:
    #   # @ordinal bnp = [bnp_lo, bnp_grey, ...]  @target cpe
    ordinal_re = re.compile(
        r"@ordinal\s+(\w+)\s*=\s*\[([^\]]+)\]"
    )
    bearer_re = re.compile(r'^(\S+)\s+"(.+)"\s*$')

    for raw in path.read_text().splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            # Comment line — extract annotations
            m = ordinal_re.search(line)
            if m:
                family = m.group(1)
                tiers = [t.strip() for t in m.group(2).split(",") if t.strip()]
                ordinal_families[family] = tiers
                continue
            # Other annotation markers we surface in the description
            for marker in ("@copresent", "@entails"):
                if marker in line:
                    annotation_summary.append(line.lstrip("# ").strip())
                    break
            continue
        # Bearer line: id "expression"
        m = bearer_re.match(line)
        if m:
            bid, expression = m.group(1), m.group(2)
            bearers[bid] = expression
    return bearers, ordinal_families, annotation_summary


def build_benchmark(
    bearers: dict[str, str],
    ordinal_families: dict[str, list[str]],
    annotation_summary: list[str],
    v05: dict,
) -> dict:
    """Build the framework-compatible benchmark JSON."""
    # Cross-check: every bearer id used in any item premise / target must
    # be present in the bearers dict.
    used_ids: set[str] = set()
    for item in v05["items"]:
        used_ids.update(item["premises"])
        used_ids.add(item["target"])
    missing = sorted(used_ids - set(bearers))
    if missing:
        raise SystemExit(
            f"ERROR: items reference {len(missing)} bearer id(s) not defined "
            f"in bearers_v0.5.txt: {missing}"
        )

    items: list[dict] = []
    placeholder_normalize_count = 0
    for src in v05["items"]:
        # v0.5 extras the framework's BenchmarkItem doesn't model natively
        # — JSON-encoded into ConstructionMetadata.source. Strict schema
        # there forbids arbitrary keys, but the free-text source field
        # round-trips cleanly.
        v05_extras: dict = {
            "source_target": src["target"],
            "ladder": src["ladder"],
            "variation": src["variation"],
            "placeholder_v05": src["placeholder"],
        }
        if "note" in src:
            v05_extras["note"] = src["note"]
        if "monotonicity" in src:
            v05_extras["monotonicity"] = src["monotonicity"]

        # Normalize the placeholder for downstream readers; record if
        # normalized so the round-trip is lossless.
        pl = src["placeholder"]
        if pl in PLACEHOLDER_NORMALIZE:
            v05_extras["placeholder"] = PLACEHOLDER_NORMALIZE[pl]
            v05_extras["placeholder_normalized"] = True
            placeholder_normalize_count += 1
        else:
            v05_extras["placeholder"] = pl

        # Derive factor_levels: which ordinal-family tier (if any) each item
        # carries. An item can carry at most one tier per family (mutex
        # invariant from v0.5).
        factor_levels: dict[str, str] = {}
        for family, tiers in ordinal_families.items():
            for tier in tiers:
                if tier in src["premises"]:
                    factor_levels[family] = tier
                    break

        items.append({
            "id": src["id"],
            "premises": list(src["premises"]),
            "conclusions": [src["target"]],
            "analyst_verdicts": ["abstain"],  # see module docstring
            "tags": [
                f"ladder:{src['ladder']}",
                f"variation:{src['variation']}",
                f"target:{src['target']}",
            ],
            "factor_levels": factor_levels,
            "construction_metadata": {
                "source": "v0.5-extras:" + json.dumps(v05_extras, sort_keys=True),
            },
        })

    # Top-level description folds in the @copresent and @entails annotations
    # the framework can't enforce natively yet, plus the methodology lineage.
    description_lines = [
        "clinical pilot benchmark for the cardiogenic pulmonary edema (CPE) vs. "
        "acute respiratory distress syndrome (ARDS) differential. Designed in "
        "collaboration with the clinical collaborator.",
        "",
        "Methodology lineage: Hlobil-Brandom implication frame, single-succedent "
        "instantiation (|delta|=1), per Allen Definitions 4-5.",
        "",
        f"Items organized into ladders (A/B/C/D/F/G) with explicit variation "
        f"typology (base / strengthen / contested / defeat / abstain_anchor / "
        f"monotonicity_step). See item_ladders_v0.5_oxygenation.md for the "
        f"ladder design and the clinician's round-2 corrections to the v0.4 encoding.",
        "",
        "PLACEHOLDER ANALYST PANEL: this benchmark is a pre-clinician pilot. "
        "The single analyst entry below is a framework-required stopgap; all "
        "per-item analyst_verdicts are 'abstain' and DO NOT REPRESENT CLINICAL "
        "JUDGMENT. The v0.5 dry-run placeholder values are preserved in each "
        "item's construction_metadata.placeholder. Real clinician verdicts "
        "will be collected from the pilot panel and the benchmark regenerated. "
        "Until then, model-vs-analyst metrics against this placeholder panel "
        "are not meaningful.",
    ]
    if annotation_summary:
        description_lines.extend([
            "",
            "v0.5 bearer-file annotations (informational; not enforced by the "
            "current framework — pending v0.17.x):",
        ])
        for ann in annotation_summary:
            description_lines.append(f"  - {ann}")

    # Reuse the existing pulmonary_edema verification prompt verbatim; same
    # clinical-defeasibility domain so the same prompt is appropriate.
    verification_prompt = {
        "id": "defeasible-clinical-v1",
        "system": (
            "You are evaluating defeasible material inference in clinical "
            "reasoning. An inference from premises to a conclusion is GOOD "
            "when, granting the premises and absent further information, a "
            "competent clinician would endorse the conclusion as defeasibly "
            "supported. It is BAD when the premises do not support the "
            "conclusion, either because they are unrelated or because they "
            "defeat it. It is ABSTAIN when the question is ill-formed or "
            "you cannot judge. Defeasible support does not require deductive "
            "entailment: an inference is GOOD if it would be endorsed by "
            "default in everyday clinical reasoning, even if it could be "
            "defeated by additional information not present in the premises. "
            "For example, 'bird flies' is GOOD by default even though "
            "'penguin flies' is BAD; the bird-flies inference is defeasible. "
            "Answer with exactly one of: GOOD, BAD, ABSTAIN. No other text."
        ),
        "template": "Premises: {premise_context}\nConclusion: {conclusion_context}\nVerdict:",
        "parse_regex": r"\b(GOOD|BAD|ABSTAIN)\b",
    }

    benchmark = {
        "schema_version": "1.0",
        "id": "clinical-pilot-cpe-ards-v0.5",
        "title": "clinical pilot — CPE vs. ARDS differential (v0.5)",
        "domain": "Clinical pulmonary medicine — defeasible diagnostic reasoning",
        "description": "\n".join(description_lines),
        "bearers": {
            bid: {"expression": expr, "paraphrases": [], "references": []}
            for bid, expr in bearers.items()
        },
        "analysts": [
            {
                "id": "clinician-panel-placeholder",
                "display_name": "clinician panel (pending recruitment)",
                "notes": (
                    "Framework-required placeholder while the clinician panel is "
                    "being recruited. All per-item verdicts are 'abstain'. The "
                    "v0.5 dry-run placeholder values (which encode the design "
                    "team's provisional reading, NOT a clinical judgment) are "
                    "preserved in each item's construction_metadata.placeholder "
                    "field. Replace this analyst entry with the real clinician "
                    "panel verdicts once collected; regenerate benchmark.json "
                    "from benchmark_v0.5.json via examples/clinical_pilot/convert.py."
                ),
            }
        ],
        "context_builders": {
            "premise": {
                "kind": "template",
                "template": "{expressions}",
                "joiner": " and ",
            },
            "conclusion": {
                "kind": "template",
                "template": "{expressions}",
                "joiner": " or ",
            },
        },
        "verification_prompt": verification_prompt,
        "factors": dict(ordinal_families),
        "factor_kinds": {family: "substantive" for family in ordinal_families},
        "items": items,
    }
    benchmark["_conversion_stats"] = {
        "n_items": len(items),
        "n_bearers": len(bearers),
        "n_ordinal_families": len(ordinal_families),
        "n_placeholder_normalized": placeholder_normalize_count,
    }
    return benchmark


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="Parse + validate; don't write")
    p.add_argument(
        "--out",
        type=Path,
        default=OUTPUT,
        help=f"Output path (default: {OUTPUT.relative_to(HERE.parent.parent)})",
    )
    args = p.parse_args()

    print(f"Reading bearers from {BEARERS_V05.relative_to(HERE.parent.parent)} ...")
    bearers, ordinal_families, annotations = parse_bearers_file(BEARERS_V05)
    print(f"  {len(bearers)} bearer ids")
    print(f"  {len(ordinal_families)} ordinal families")
    print(f"  {len(annotations)} @copresent / @entails annotations")

    print(f"Reading benchmark from {BENCHMARK_V05.relative_to(HERE.parent.parent)} ...")
    v05 = json.loads(BENCHMARK_V05.read_text())
    print(f"  {len(v05['items'])} items")

    print("Building framework-compatible benchmark...")
    bench = build_benchmark(bearers, ordinal_families, annotations, v05)
    stats = bench.pop("_conversion_stats")
    print(f"  → {stats['n_items']} items, {stats['n_bearers']} bearers")
    print(f"  → {stats['n_ordinal_families']} ordinal families as factors")
    if stats["n_placeholder_normalized"]:
        print(
            f"  → {stats['n_placeholder_normalized']} placeholder(s) normalized "
            f"(v0.5 → Verdict enum); originals preserved in "
            f"construction_metadata.placeholder_v05"
        )

    # Round-trip through Pydantic to catch validation errors before writing.
    try:
        from infereval.benchmark import Benchmark
        Benchmark.model_validate(bench)
    except ImportError:
        print("WARN: infereval not importable; skipped Pydantic round-trip")
    except Exception as exc:
        print(f"ERROR: framework rejected the converted benchmark:\n  {exc}",
              file=sys.stderr)
        return 1

    if args.check:
        print("Check passed; no file written.")
        return 0

    args.out.write_text(json.dumps(bench, indent=2) + "\n")
    print(f"Wrote {args.out.relative_to(HERE.parent.parent)}  ({args.out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
