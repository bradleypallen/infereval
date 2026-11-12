"""``infereval describe <benchmark.json>`` -- print a benchmark summary.

Useful as the first step in working with a new benchmark: how many bearers,
items, analysts, and what the inter-analyst Fleiss baseline
:math:`\\kappa_F^*(\\beta)` looks like before any model is evaluated.
"""

from __future__ import annotations

import logging
import textwrap
from collections import Counter
from pathlib import Path

import click

from infereval.benchmark import Benchmark, BenchmarkItem
from infereval.metrics import inter_analyst_fleiss
from infereval.types import Verdict

log = logging.getLogger(__name__)


# Width target for wrapped prose. Standard 80-col minus a 2-col left margin.
_WRAP = 78

# All top-level header lines (id / title / domain / description / schema) use
# a fixed 13-char column for the label so values line up vertically.
_HEADER_COL = 13


def _format_kappa(value: float | None) -> str:
    if value is None:
        return "undefined"
    return f"{value:+.4f}"


def _verdict_counts(verdicts: list[Verdict]) -> str:
    """Render a verdict tuple as ``g=3 b=1 a=0`` for compact tabular output."""
    counts = Counter(verdicts)
    return (
        f"g={counts.get(Verdict.GOOD, 0)} "
        f"b={counts.get(Verdict.BAD, 0)} "
        f"a={counts.get(Verdict.ABSTAIN, 0)}"
    )


def _wrap_field(label: str, value: str, *, width: int = _WRAP) -> str:
    """Format a ``label:<pad><value>`` so the wrap continuation aligns under the value.

    The label is padded to :data:`_HEADER_COL` so the top-level header
    block stays column-aligned vertically. Subsequent wrap lines indent
    under the value column.
    """
    header = f"{label + ':':<{_HEADER_COL}}"
    return textwrap.fill(
        f"{header}{value}",
        width=width,
        subsequent_indent=" " * _HEADER_COL,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _truncate(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _render_verification_prompt(bench: Benchmark) -> None:
    """Print the benchmark's verification-prompt override, when present."""
    vp = bench.verification_prompt
    if vp is None:
        return
    click.echo("verification prompt:")
    if vp.id:
        click.echo(f"  id:          {vp.id}")
    # Show the template's first line at most; collapse internal newlines.
    flat_template = vp.template.replace("\n", " | ").strip()
    click.echo(f"  template:    {_truncate(flat_template, limit=200)}")
    if vp.system:
        flat_system = vp.system.replace("\n", " ").strip()
        # Wrap so the body indents under the value, not under the label.
        click.echo(
            textwrap.fill(
                f"  system:      {_truncate(flat_system, limit=400)}",
                width=_WRAP,
                subsequent_indent="               ",
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    if vp.parse_regex:
        click.echo(f"  parse_regex: {vp.parse_regex}")
    click.echo("")


def _render_bearers(bench: Benchmark) -> None:
    """List bearers as ``id: expression`` aligned on the longest id."""
    if not bench.bearers:
        return
    click.echo(f"bearers ({len(bench.bearers)}):")
    width = max(len(bid) for bid in bench.bearers)
    for bid in sorted(bench.bearers):
        expr = bench.bearers[bid].expression
        # Wrap long expressions under the value column for readability.
        line_label = f"  {bid.ljust(width)}  "
        click.echo(
            textwrap.fill(
                f"{line_label}{expr}",
                width=_WRAP,
                subsequent_indent=" " * len(line_label),
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    click.echo("")


def _render_references_summary(bench: Benchmark) -> None:
    """Print a summary of provenance: count at each level + first few citations."""
    n_corpus = len(bench.references)
    bearer_refs = sum(len(b.references) for b in bench.bearers.values())
    bearer_annotated = sum(1 for b in bench.bearers.values() if b.references)
    item_refs = sum(len(it.references) for it in bench.items)
    item_annotated = sum(1 for it in bench.items if it.references)

    if not (n_corpus or bearer_refs or item_refs):
        return  # Nothing to show.

    click.echo("references:")
    click.echo(f"  benchmark-level: {n_corpus}")
    click.echo(
        f"  bearer-level:    {bearer_refs} "
        f"(across {bearer_annotated}/{len(bench.bearers)} bearers)"
    )
    if item_refs:
        mean = item_refs / max(item_annotated, 1)
        click.echo(
            f"  item-level:      {item_refs} references across "
            f"{item_annotated}/{bench.n} items; mean {mean:.2f}/annotated-item"
        )
    else:
        click.echo("  item-level:      0")

    if bench.references:
        click.echo("  first corpus refs:")
        for ref in bench.references[:3]:
            citation = _truncate(ref.citation, limit=_WRAP - 6)
            click.echo(f"    - {citation}")
        if n_corpus > 3:
            click.echo(f"    ... and {n_corpus - 3} more")
    click.echo("")


def _render_panels(bench: Benchmark) -> None:
    """Print analyst-panel summary + per-panel κ_F* + cross-panel κ_C.

    Surfaces R4 (independent reference check) infrastructure. Omitted
    when no analyst declares a panel. Phase 1.4 of the construct-validity
    infrastructure.
    """
    names = bench.panel_names()
    if not names:
        return

    from infereval.metrics import cross_panel_kappa, inter_analyst_fleiss_per_panel

    primary = bench.resolved_primary_panel()
    per_panel = inter_analyst_fleiss_per_panel(bench)

    click.echo(f"analyst panels: {len(names)} (primary = {primary})")
    name_w = max(len(n) for n in names)
    for n in names:
        analysts = bench.analysts_in_panel(n)
        m = len(analysts)
        ids = ", ".join(a.id for a in analysts)
        kappa = per_panel.get(n)
        kappa_str = _format_kappa(kappa) if kappa is not None else (
            "undefined (n<2)" if m < 2 else "undefined (unanimous)"
        )
        click.echo(
            f"  {n.ljust(name_w)}  {ids}  (n={m})  κ_F* = {kappa_str}"
        )

    # Cross-panel κ_C when exactly two panels are declared.
    if len(names) == 2 and primary is not None:
        check = next(n for n in names if n != primary)
        cp = cross_panel_kappa(bench, primary=primary, check=check)
        if cp is not None:
            click.echo(
                f"  cross-panel κ_C({primary} vs {check}): {_format_kappa(cp)}"
            )
        else:
            click.echo(
                f"  cross-panel κ_C({primary} vs {check}): undefined "
                "(no substantive intersection or degenerate marginal)"
            )
    click.echo("")


def _render_construction_provenance(bench: Benchmark) -> None:
    """Print a summary of per-item construction provenance.

    Surfaces who authored items, when, against which models they were
    blind, and from what source materials. Omitted when no item carries
    construction_metadata. Phase 1.3 of the construct-validity
    infrastructure (R5, R8, R9).
    """
    annotated = [it for it in bench.items if it.construction_metadata is not None]
    if not annotated:
        return

    click.echo("construction provenance:")
    click.echo(f"  items with metadata: {len(annotated)} / {len(bench.items)}")

    # Authors
    author_counts: Counter[str] = Counter()
    for it in annotated:
        cm = it.construction_metadata
        assert cm is not None
        if cm.authored_by:
            author_counts[cm.authored_by] += 1
    if author_counts:
        top = ", ".join(f"{a}: {n}" for a, n in author_counts.most_common(5))
        more = (
            f", and {len(author_counts) - 5} more"
            if len(author_counts) > 5
            else ""
        )
        click.echo(f"  authors:             {len(author_counts)} unique ({top}{more})")

    # Date range
    dates = [
        it.construction_metadata.authored_on
        for it in annotated
        if it.construction_metadata is not None
        and it.construction_metadata.authored_on is not None
    ]
    if dates:
        if min(dates) == max(dates):
            click.echo(f"  authored_on:         {min(dates).isoformat()}")
        else:
            click.echo(
                f"  authored_on range:   "
                f"{min(dates).isoformat()} to {max(dates).isoformat()}"
            )

    # Blinded-to models — union across items
    blinded_models: Counter[str] = Counter()
    for it in annotated:
        cm = it.construction_metadata
        assert cm is not None
        for m in cm.authored_blind_to_models:
            blinded_models[m] += 1
    if blinded_models:
        top = ", ".join(m for m, _ in blinded_models.most_common(3))
        more = (
            f", and {len(blinded_models) - 3} more"
            if len(blinded_models) > 3
            else ""
        )
        click.echo(f"  blinded-to models:   {len(blinded_models)} unique ({top}{more})")

    # Source citations (count of distinct)
    sources = {
        it.construction_metadata.source
        for it in annotated
        if it.construction_metadata is not None and it.construction_metadata.source
    }
    if sources:
        click.echo(f"  source citations:    {len(sources)} distinct")
    click.echo("")


def _render_paraphrase_variants(bench: Benchmark) -> None:
    """Print a single line summarising paraphrase coverage across bearers.

    Omitted when no bearer carries any paraphrase. Phase 1.2 of the
    construct-validity infrastructure (R10).
    """
    bearers_with = [bid for bid, b in bench.bearers.items() if b.paraphrases]
    if not bearers_with:
        return
    max_paras = max(len(bench.bearers[bid].paraphrases) for bid in bearers_with)
    n_variants = 1 + max_paras
    click.echo(
        f"paraphrase variants: {n_variants} "
        f"({len(bearers_with)}/{len(bench.bearers)} bearers carry paraphrases; "
        f"max {max_paras} each)"
    )
    click.echo("")


def _render_factorial_design(bench: Benchmark) -> None:
    """Print the declared factorial design and its cell coverage.

    Per Issue #30 (Phase 1.1 of the construct-validity infrastructure).
    Surfaces what ``infereval describe`` previously left invisible: which
    design factors are declared, their levels, how the items distribute
    across the crossed-design cells, and whether the declared
    ``min_items_per_cell`` floor is met. Skipped when no factors are
    declared.
    """
    if not bench.factors:
        return

    factor_names = sorted(bench.factors)
    cells = bench.cells()
    total_cells = len(cells)
    populated = sum(1 for n in cells.values() if n > 0)

    click.echo(f"factorial design ({len(factor_names)} factor{'s' if len(factor_names) != 1 else ''}):")

    # Each factor: name, level count, level list (truncated if long).
    name_w = max(len(f) for f in factor_names)
    for f in factor_names:
        levels = bench.factors[f]
        lst = "[" + ", ".join(levels) + "]"
        # Truncate the level-list display for readability.
        if len(lst) > 60:
            lst = "[" + ", ".join(levels[:4]) + f", … ({len(levels) - 4} more)]"
        click.echo(f"  {f.ljust(name_w)}  {len(levels)} levels: {lst}")

    # Crossed-cell summary line.
    dims = " × ".join(str(len(bench.factors[f])) for f in factor_names)
    click.echo(f"  total cells:        {dims} = {total_cells}")
    click.echo(f"  populated cells:    {populated} / {total_cells}")

    # min_items_per_cell, if declared — show whether the floor is met and,
    # if not, list a few of the underpopulated cells.
    if bench.factor_constraints is not None and bench.factor_constraints.min_items_per_cell is not None:
        k = bench.factor_constraints.min_items_per_cell
        meeting = sum(1 for n in cells.values() if n >= k)
        click.echo(f"  min items per cell: {k} (declared)")
        click.echo(f"  cells meeting min:  {meeting} / {total_cells}")
        underpopulated = [(cell, n) for cell, n in cells.items() if n < k]
        if underpopulated:
            click.echo("  underpopulated cells:")
            shown = sorted(underpopulated, key=lambda kv: (kv[1], kv[0]))[:5]
            for cell, n in shown:
                desc = ", ".join(
                    f"{f}={lvl}" for f, lvl in zip(factor_names, cell, strict=True)
                )
                click.echo(f"    ({desc}): {n} item{'s' if n != 1 else ''}")
            if len(underpopulated) > 5:
                click.echo(f"    ... and {len(underpopulated) - 5} more")
    click.echo("")


def _render_group_cross_tab(bench: Benchmark) -> None:
    """For each tag group, show the primary-analyst verdict distribution.

    "Group" is computed by scanning each item's ``tags`` for the **first**
    target-inference identifier (``T1``, ``T2``, …) or the literal tag
    ``cross-cutting``. Items lacking such a tag are pooled under
    ``(other)``. Items with no tags at all are pooled under
    ``(untagged)``.

    Surfaces label skew per category that the flat tag-frequency list
    cannot show; e.g. "T1: 12 items, 8 good / 4 bad" vs. "T2: 10 items,
    7 good / 3 bad" answers "are the supporters and defeaters balanced
    inside each target?" at a glance.

    Skipped entirely if no item has a recognised category tag.
    """
    if bench.m == 0 or not bench.items:
        return

    def _category_of(item: BenchmarkItem) -> str:
        if not item.tags:
            return "(untagged)"
        for t in item.tags:
            # T1, T2, … target-inference identifiers (uppercase T followed by digits).
            if len(t) >= 2 and t[0] == "T" and t[1:].isdigit():
                return str(t)
            if t == "cross-cutting":
                return str(t)
        return "(other)"

    primary = 0
    groups: dict[str, Counter[Verdict]] = {}
    for item in bench.items:
        cat = _category_of(item)
        counts = groups.setdefault(cat, Counter())
        counts[item.analyst_verdicts[primary]] += 1

    # Skip the section entirely if every item ended up in (other) or
    # (untagged) — there's no informative cross-tab to print.
    informative = {g for g in groups if not g.startswith("(")}
    if not informative:
        return

    # Sort: target-inference groups (T1, T2, …) first by index, then
    # cross-cutting, then fallback buckets.
    def _sort_key(g: str) -> tuple[int, str]:
        if g.startswith("T") and g[1:].isdigit():
            return (0, g.zfill(4))
        if g == "cross-cutting":
            return (1, g)
        return (2, g)

    ordered = sorted(groups.items(), key=lambda kv: _sort_key(kv[0]))

    name = bench.analysts[primary].id
    click.echo(f"verdict distribution by tag group (analyst [{primary}] {name}):")
    name_width = max(len(g) for g, _ in ordered)
    for cat, counts in ordered:
        g = counts.get(Verdict.GOOD, 0)
        b = counts.get(Verdict.BAD, 0)
        a = counts.get(Verdict.ABSTAIN, 0)
        n = g + b + a
        click.echo(
            f"  {cat.ljust(name_width)}  "
            f"good={g:<3} bad={b:<3} abstain={a:<3} n={n}"
        )
    click.echo("")


def _render_items(bench: Benchmark) -> None:
    """Print every item in an expert-readable form (Issue #28).

    For each implication: bearer-id form on the header line (compact,
    matches the formal notation), resolved English expressions
    for premises and conclusions, analyst verdict(s), tag annotation,
    and the full reference block — citation + DOI + URL + section + note
    for every reference attached to the item.

    Items are grouped by target tag (``T1`` / ``T2`` / ``cross-cutting``)
    when those tags are present, otherwise rendered as a single flat
    block.
    """
    if not bench.items:
        return

    def _category_of(item: BenchmarkItem) -> str:
        if not item.tags:
            return "(other)"
        for t in item.tags:
            if len(t) >= 2 and t[0] == "T" and t[1:].isdigit():
                return str(t)
            if t == "cross-cutting":
                return str(t)
        return "(other)"

    # Group by category if there's at least one target/cross-cutting tag.
    groups: dict[str, list[BenchmarkItem]] = {}
    for item in bench.items:
        groups.setdefault(_category_of(item), []).append(item)
    has_target_groups = any(g != "(other)" for g in groups)

    def _sort_key(g: str) -> tuple[int, str]:
        if g.startswith("T") and g[1:].isdigit():
            return (0, g.zfill(4))
        if g == "cross-cutting":
            return (1, g)
        return (2, g)

    def _item_sort(item: BenchmarkItem) -> tuple[str, int, str]:
        # Sort within group by leading-letter then numeric suffix so
        # c1 < c2 < c10 < c11 (string sort would give c1, c10, c11, c2).
        prefix = item.id[:1]
        rest = item.id[1:]
        return (prefix, int(rest) if rest.isdigit() else 0, item.id)

    click.echo(f"items ({bench.n}):")
    click.echo("")

    def _render_one(item: BenchmarkItem, indent: str = "    ") -> None:
        pre_ids = "{" + ", ".join(sorted(item.premises)) + "}"
        con_ids = "{" + ", ".join(sorted(item.conclusions)) + "}"

        # Verdict(s). For single-analyst, render as ``→ good``; for
        # multi-analyst, render as ``→ good, bad, good`` so the per-
        # analyst tuple is visible to the reader.
        if bench.m == 1:
            verdict_str = f"→  {item.analyst_verdicts[0]}"
        else:
            verdict_str = "→  " + ", ".join(item.analyst_verdicts)
        tag_annot = f"   [{', '.join(item.tags)}]" if item.tags else ""

        # AR11: divergence-with-rationales flag. When the analyst column
        # disagrees AND rationales are present on this item, this is a
        # noise-vs-signal triage target — the rationale text is what
        # disambiguates a genuine carving disagreement from a labelling
        # slip. Flag it on the header line so a reader scanning the
        # benchmark sees it without diving into the body.
        verdicts_diverge = len(set(item.analyst_verdicts)) > 1
        rationales_present = item.analyst_rationales is not None
        divergence_flag = (
            "  ⚠ disagreement+rationales"
            if verdicts_diverge and rationales_present
            else ""
        )

        click.echo(
            f"{indent}{item.id}  {pre_ids} ⊢? {con_ids}  {verdict_str}"
            f"{tag_annot}{divergence_flag}"
        )

        # Γ premises in English. Wrap each long expression under the
        # value column for readability on narrow terminals.
        body_indent = indent + "    "
        gamma_label = body_indent + "Γ: "
        gamma_cont = body_indent + "   "
        if item.premises:
            premises_sorted = sorted(item.premises)
            for i, pid in enumerate(premises_sorted):
                expr = bench.bearers[pid].expression
                lead = gamma_label if i == 0 else gamma_cont
                click.echo(
                    textwrap.fill(
                        f"{lead}{expr}",
                        width=_WRAP,
                        subsequent_indent=gamma_cont,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )

        delta_label = body_indent + "Δ: "
        delta_cont = body_indent + "   "
        if item.conclusions:
            for i, cid in enumerate(sorted(item.conclusions)):
                expr = bench.bearers[cid].expression
                lead = delta_label if i == 0 else delta_cont
                click.echo(
                    textwrap.fill(
                        f"{lead}{expr}",
                        width=_WRAP,
                        subsequent_indent=delta_cont,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )

        # Per-analyst rationales (AR11), if present. The field-is-None
        # case skips this block entirely (no rationale discipline).
        # When the field is a list, render one line per analyst with
        # their id and their rationale text; an empty-string entry
        # renders as "(no reason recorded)" so the bare-verdict-with-
        # no-reason case is visually distinct from the absent-field
        # case (which renders nothing at all).
        if item.analyst_rationales is not None:
            click.echo(f"{body_indent}rationales:")
            rationale_indent = body_indent + "  "
            for j, analyst in enumerate(bench.analysts):
                text = item.analyst_rationales[j].strip()
                rendered = text if text else "(no reason recorded)"
                lead = f"{rationale_indent}{analyst.id}: "
                cont = " " * len(lead)
                click.echo(
                    textwrap.fill(
                        f"{lead}{rendered}",
                        width=_WRAP,
                        subsequent_indent=cont,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )

        # Construction provenance (Issue #34), if present.
        if item.construction_metadata is not None:
            cm = item.construction_metadata
            parts: list[str] = []
            if cm.authored_by and cm.authored_on:
                parts.append(f"{cm.authored_by} on {cm.authored_on.isoformat()}")
            elif cm.authored_by:
                parts.append(cm.authored_by)
            elif cm.authored_on:
                parts.append(cm.authored_on.isoformat())
            if cm.authored_blind_to_models:
                parts.append("blind to " + ", ".join(cm.authored_blind_to_models))
            if cm.source:
                parts.append(f"source: {cm.source}")
            if parts:
                label = f"{body_indent}construction: "
                cont = " " * len(label)
                click.echo(
                    textwrap.fill(
                        label + "; ".join(parts),
                        width=_WRAP,
                        subsequent_indent=cont,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )

        # References, if any.
        if item.references:
            click.echo(f"{body_indent}references ({len(item.references)}):")
            for idx, ref in enumerate(item.references, start=1):
                num = f"{body_indent}  {idx}. "
                cont = " " * len(num)
                click.echo(
                    textwrap.fill(
                        f"{num}{ref.citation}",
                        width=_WRAP,
                        subsequent_indent=cont,
                        break_long_words=False,
                        break_on_hyphens=False,
                    )
                )
                if ref.doi:
                    click.echo(f"{cont}doi: {ref.doi}")
                if ref.url:
                    click.echo(f"{cont}url: {ref.url}")
                if ref.section:
                    click.echo(f"{cont}section: {ref.section}")
                if ref.note:
                    note_lead = f"{cont}note: "
                    note_cont = cont + "      "
                    click.echo(
                        textwrap.fill(
                            f"{note_lead}{ref.note}",
                            width=_WRAP,
                            subsequent_indent=note_cont,
                            break_long_words=False,
                            break_on_hyphens=False,
                        )
                    )

    if has_target_groups:
        for cat in sorted(groups, key=_sort_key):
            items = sorted(groups[cat], key=_item_sort)
            click.echo(f"  {cat} ({len(items)} items):")
            click.echo("")
            for item in items:
                _render_one(item)
                click.echo("")
    else:
        for item in sorted(bench.items, key=_item_sort):
            _render_one(item, indent="  ")
            click.echo("")


@click.command("describe", help="Print a summary of a benchmark JSON file.")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--items",
    "show_items",
    is_flag=True,
    default=False,
    help=(
        "Also print every implication in expert-readable form: bearer-id "
        "form, resolved English expressions for Γ and Δ, analyst verdict(s), "
        "tags, and the full inline reference block. Verbose; intended for "
        "domain-expert review."
    ),
)
def describe_cmd(path: Path, show_items: bool = False) -> None:
    """Print a benchmark summary (id, |B|, |β|, m, label distribution, κ_F*)."""
    log.info("describe.start path=%s", path)
    bench = Benchmark.load(path)

    click.echo(_wrap_field("id", bench.id))
    if bench.title:
        click.echo(_wrap_field("title", bench.title))
    if bench.domain:
        click.echo(_wrap_field("domain", bench.domain))
    if bench.description:
        click.echo(_wrap_field("description", bench.description))
    click.echo(_wrap_field("schema", bench.schema_version))
    click.echo("")
    click.echo(f"|B| (bearers):  {len(bench.bearers)}")
    click.echo(f"n (items):      {bench.n}")
    click.echo(f"m (analysts):   {bench.m}")
    click.echo("")

    # Per-analyst label distribution.
    click.echo("Per-analyst label distribution:")
    for j, analyst in enumerate(bench.analysts):
        verdicts = [item.analyst_verdicts[j] for item in bench.items]
        name = analyst.display_name or analyst.id
        click.echo(f"  [{j}] {analyst.id} ({name}): {_verdict_counts(verdicts)}")
    click.echo("")

    # Inter-analyst Fleiss baseline. Skip the call when m < 2 so the
    # metrics module's WARNING doesn't bleed into CLI output. v0.7.0
    # (#82): the value is the all-analyst κ_F* even on panelled
    # benchmarks; per-panel breakdown is rendered separately by
    # _render_analyst_panels_section above.
    if bench.m < 2:
        click.echo("κ_F*(β) (all analysts): undefined")
        click.echo("  (undefined: requires m ≥ 2 analysts)")
    else:
        kappa_star = inter_analyst_fleiss(bench)
        click.echo(f"κ_F*(β) (all analysts): {_format_kappa(kappa_star)}")
        if kappa_star is None:
            click.echo("  (undefined: analysts are unanimous or all-non-substantive)")
    click.echo("")

    # New sections (Issue #25): verification prompt, bearers, references, cross-tab.
    _render_verification_prompt(bench)
    _render_bearers(bench)
    _render_references_summary(bench)
    _render_factorial_design(bench)
    _render_paraphrase_variants(bench)
    _render_panels(bench)
    _render_construction_provenance(bench)
    _render_group_cross_tab(bench)

    # Tag frequencies, if any.
    tag_counts: Counter[str] = Counter()
    for item in bench.items:
        tag_counts.update(item.tags)
    if tag_counts:
        click.echo("Tags:")
        for tag, count in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            click.echo(f"  {tag}: {count}")
        click.echo("")

    # RSR-targeted items, if any.
    rsr_targets = [item for item in bench.items if item.rsr_target is not None]
    if rsr_targets:
        click.echo(f"RSR-targeted items: {len(rsr_targets)} / {bench.n}")
        # Group by target
        by_target: dict[tuple[tuple[str, ...], tuple[str, ...]], int] = {}
        for item in rsr_targets:
            assert item.rsr_target is not None
            key = (
                tuple(sorted(item.rsr_target.X)),
                tuple(sorted(item.rsr_target.A)),
            )
            by_target[key] = by_target.get(key, 0) + 1
        for (X, A), count in sorted(by_target.items(), key=lambda kv: (-kv[1], kv[0])):
            click.echo(f"  ⟨{{{','.join(X)}}}, {{{','.join(A)}}}⟩: {count}")
        click.echo("")

    # Item listing (Issue #28): expert-readable per-implication rendering.
    if show_items:
        _render_items(bench)

    log.info("describe.ok path=%s", path)
