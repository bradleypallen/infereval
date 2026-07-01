"""Benchmark :math:`\\beta` model and JSON I/O.

A benchmark is, per Definition 4 of the paper, a finite set
:math:`\\{(I_1, V_1), \\ldots, (I_n, V_n)\\}` where each :math:`I_i` is an
implication and each :math:`V_i = (v_{i,1}, \\ldots, v_{i,m})` is a tuple of
analyst verdicts. This module defines the Pydantic-validated JSON shape and
provides :meth:`Benchmark.load` / :meth:`Benchmark.dump` for disk I/O.

The runtime conversion to :class:`infereval.types.Implication` lives on
:meth:`BenchmarkItem.to_implication`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from .types import Bearer as _RuntimeBearer
from .types import Implication, PlaceholderVerdict, VariationType, Verdict

SCHEMA_VERSION: Literal["1.0"] = "1.0"


class Reference(BaseModel):
    """A traceable provenance entry for a benchmark, bearer, or item.

    The motivating use case is regulated-domain benchmarks (medical, legal,
    financial) where every non-trivial implication needs a citation to a
    guideline, statute, or peer-reviewed source. Recording these as
    structured objects lets downstream tooling render bibliographies,
    validate DOIs, and connect items to the documents that justify them.

    Only :attr:`citation` is required. The other fields populate when the
    relevant identifier is known and remain ``None`` otherwise.

    Authoring shorthand: a plain string in any ``references`` list is
    auto-promoted to a :class:`Reference` with the string as
    :attr:`citation` and everything else ``None``. See
    :func:`_promote_reference_shorthand`.
    """

    model_config = ConfigDict(extra="forbid")

    citation: str
    doi: str | None = None
    url: str | None = None
    section: str | None = None
    """Pinpoint location within the cited work, e.g. ``"Section 5.2"`` or
    ``"Hypoxemia criterion"``."""
    note: str | None = None
    """What specifically this reference supports, in the author's words."""


def _promote_reference_shorthand(v: object) -> object:
    """Normalize a ``references`` list-entry: strings become ``Reference(citation=s)``.

    Used as a ``mode="before"`` validator on every ``references`` field to
    let authors write ``["Some citation", {"citation": "...", "doi": "..."}]``
    interchangeably.
    """
    if isinstance(v, list):
        out: list[object] = []
        for entry in v:
            if isinstance(entry, str):
                out.append({"citation": entry})
            else:
                out.append(entry)
        return out
    return v


class BearerModel(BaseModel):
    """JSON shape for a :class:`infereval.types.Bearer`."""

    model_config = ConfigDict(extra="forbid")

    expression: str
    paraphrases: tuple[str, ...] = ()
    references: list[Reference] = Field(default_factory=list)
    """Provenance for the bearer's definition, e.g. the guideline section
    that defines the threshold ``"P/F < 300"`` is measured against."""
    ordinal_family: str | None = None
    """Name of the ordinal family this bearer is a tier of, when it is one
    (e.g. ``"bnp"`` for ``bnp_lo``). Must name a family declared in
    :attr:`Benchmark.ordinal_families`. ``None`` (default) for non-tier
    bearers. Additive (v0.17.0): pre-existing benchmarks validate unchanged."""

    @field_validator("references", mode="before")
    @classmethod
    def _promote_refs(cls, v: object) -> object:
        return _promote_reference_shorthand(v)

    def to_runtime(self, bearer_id: str) -> _RuntimeBearer:
        return _RuntimeBearer(
            id=bearer_id, expression=self.expression, paraphrases=self.paraphrases
        )


class AnalystModel(BaseModel):
    """A human analyst :math:`a_j` whose verdicts appear in :math:`V_i`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str | None = None
    notes: str | None = None
    expertise_description: str | None = None
    """Free-text description of the analyst's relevant expertise — the
    domain background, specialty, years of practice, role, board
    certifications. Captured at recruitment time via
    ``infereval survey``: the survey's first block asks each respondent
    for this prose, which lands here when the response CSV is imported.
    Distinct from :attr:`notes` (general analyst-side annotations) —
    this field is specifically recruitment metadata about *why* this
    analyst's judgement counts for the benchmark's domain. ``None``
    (the default) means no expertise was declared (e.g. analysts
    seeded by the benchmark author rather than recruited via a
    survey).

    Added in v0.9.0 with the ``infereval survey`` recruitment workflow.
    Additive: pre-v0.9.0 benchmarks validate unchanged."""

    panel: str | None = None
    """Optional panel identifier. Analysts sharing the same panel string
    are members of the same panel for cross-panel agreement analysis
    (R4: independent reference check). ``None`` (default) means the
    benchmark is flat — every analyst is treated equivalently. Adding
    a panel string to ANY analyst requires ALL analysts to declare one
    (no partial-panel benchmarks)."""


class TemplateContextBuilder(BaseModel):
    """A context builder specified by an inline template string.

    The template is a format string with a single ``{expressions}`` placeholder.
    Bearer expressions are joined by ``joiner`` to fill it.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["template"] = "template"
    template: str = "{expressions}"
    joiner: str = " and "


class PluginContextBuilder(BaseModel):
    """A context builder specified by a dotted import path.

    The plugin must resolve to a callable ``(Sequence[str]) -> str`` taking
    bearer expressions and returning the natural-language context.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["plugin"] = "plugin"
    plugin: str  # e.g. "my_pkg.builders:premise_default"


ContextBuilder = Annotated[
    TemplateContextBuilder | PluginContextBuilder,
    Field(discriminator="kind"),
]


class ContextBuilders(BaseModel):
    """Pair of context builders for :math:`\\mathrm{ctx}_\\Gamma` and :math:`\\mathrm{ctx}_\\Delta`."""

    model_config = ConfigDict(extra="forbid")

    premise: ContextBuilder = Field(
        default_factory=lambda: TemplateContextBuilder(joiner=" and ")
    )
    conclusion: ContextBuilder = Field(
        default_factory=lambda: TemplateContextBuilder(joiner=" or ")
    )


class VerificationPromptOverride(BaseModel):
    """Optional benchmark-level override of the framework's default verification prompt.

    All four fields are optional in practice (``template`` is required by
    the schema since it is the minimal thing an override needs to
    contribute). When a field is ``None`` the framework default is used:

    - :attr:`system` ``None`` → :data:`infereval.prompts.DEFAULT_SYSTEM_PROMPT`.
    - :attr:`parse_regex` ``None`` → :data:`infereval.prompts.DEFAULT_PARSE_REGEX`.
    - :attr:`id` ``None`` → the caller-supplied ``override_id`` parameter to
      :func:`infereval.prompts.resolve_verification_prompt`.

    Adding the ``system`` field makes the paraphrase-axis experiment
    fully JSON-drivable (no Python required to vary the verification prompt).
    """

    model_config = ConfigDict(extra="forbid")

    template: str
    system: str | None = None
    parse_regex: str | None = None
    id: str | None = None


class RSRTarget(BaseModel):
    """Target inference :math:`\\langle X, A \\rangle` for an RSR-targeted item.

    See the paper's Remark on "RSR-targeted benchmarks".
    """

    model_config = ConfigDict(extra="forbid")

    X: list[str]
    A: list[str]

    @field_validator("X", "A", mode="before")
    @classmethod
    def _dedup_and_sort(cls, v: object) -> object:
        if isinstance(v, list):
            return sorted({str(x) for x in v})
        return v


class ConstructionMetadata(BaseModel):
    """Per-item construction provenance for benchmark audit.

    Records who authored an item, when, against what training-cutoff
    posture, and from what source materials. Phase 1.3 of the
    construct-validity infrastructure series, providing the data model
    for requirements R5 (documented construction), R8 (held-out items),
    and R9 (training-data separation).

    Content is the analyst's responsibility — the framework validates
    structure (Pydantic types, ``extra="forbid"``) but does not enforce
    that, e.g., ``authored_on`` actually post-dates a model's training
    cutoff. The point is to make the *presence* of these declarations
    auditable.
    """

    model_config = ConfigDict(extra="forbid")

    authored_by: str | None = None
    """Identifier for the author of the item, e.g. ``"physician-c"``."""
    authored_on: date | None = None
    """ISO date the item was authored."""
    authored_blind_to_models: list[str] = Field(default_factory=list)
    """Model identifiers the author had not observed at construction
    time. Critical for R8 (held-out items): if the author had seen
    M's draft-version output on the item, M's agreement on the final
    item does not constitute independent evidence."""
    source: str | None = None
    """Free-form source citation for the primary material the author
    worked from (e.g. ``"Sanford Guide to Antimicrobial Therapy 2025"``).
    Distinct from :attr:`BenchmarkItem.references`, which carries the
    framework-level :class:`Reference` objects supporting the verdict;
    ``source`` is intended for the *primary material*, not the literature
    that justifies the analyst's call."""


class FactorConstraints(BaseModel):
    """Constraints the benchmark validator should enforce on the factorial design.

    Currently supports ``min_items_per_cell``: every cell of the *fully
    crossed* design (cartesian product of all declared factor levels)
    must contain at least this many items, where a cell is defined by
    the per-factor level assignments in :attr:`BenchmarkItem.factor_levels`.

    Per *Closing the Construct-Validity Gap in infereval* (Phase 1.1)
    addressing requirement R7 (multiple items per condition) and
    supporting R12 (per-condition decomposition).
    """

    model_config = ConfigDict(extra="forbid")

    min_items_per_cell: int | None = None
    """If set, every cell of the crossed design must have at least this
    many items. Set to ``None`` to skip the cell-count validation
    entirely (the per-key / per-value type checks on ``factor_levels``
    still run)."""


class MonotonicityStep(BaseModel):
    """Ordinal-family annotation for a ``monotonicity_step`` item (v0.5 schema).

    Declares where the item sits on an ordinal ladder: the :attr:`family` walked,
    the :attr:`tier` it occupies, that tier's 0-based :attr:`tier_index` in the
    family's declared order, and the :attr:`expected` monotonicity direction of
    endorsement as the tier rises. On a cross-family ladder, :attr:`fixed` names
    the bearer id held constant in the other family. Consumed by the
    monotonicity scorer (v0.17.1); never by the shape-blind measurement layer.
    """

    model_config = ConfigDict(extra="forbid")

    family: str
    tier: str
    tier_index: int
    expected: Literal["non_decreasing", "non_increasing"] = "non_decreasing"
    fixed: str | None = None


class CopresenceRule(BaseModel):
    """``@copresent`` saturation / well-formedness rule over ordinal families.

    Declares that a set of :attr:`families` must co-occur: an item carrying a
    tier from any listed family must carry a tier from every listed family. This
    is a *well-formedness* rule on item construction, NOT an exclusion of any
    tier combination. With :attr:`exhaustivity` off (the default) the constraint
    compiler emits only an admissibility rule and **no** sequents; turning it on
    additionally makes exhaustivity itself testable (brief §2/§7).
    """

    model_config = ConfigDict(extra="forbid")

    families: list[str] = Field(min_length=2)
    exhaustivity: bool = False


class EntailmentRule(BaseModel):
    """``@entails`` bearer-level entailment: ``antecedent`` present entails ``consequent``."""

    model_config = ConfigDict(extra="forbid")

    antecedent: str
    consequent: str


class Regularity(BaseModel):
    """``~regularity``: a tested-but-not-enforced defeasible regularity.

    Documents a domain regularity that is *tested* (typically as a cross-family
    ladder) rather than *enforced* — it earns no membership in the derived
    implication frame. :attr:`test_item_ids` optionally names the items probing
    it.
    """

    model_config = ConfigDict(extra="forbid")

    description: str
    test_item_ids: list[str] = Field(default_factory=list)


class BenchmarkItem(BaseModel):
    """A single benchmark item: an implication paired with analyst verdicts."""

    model_config = ConfigDict(extra="forbid")

    id: str
    premises: list[str]
    conclusions: list[str]
    analyst_verdicts: list[Verdict]
    analyst_rationales: list[str] | None = Field(
        default=None,
        description=(
            "Optional per-analyst, per-item rationales: the "
            "natural-language reason each analyst gave for their "
            "verdict on this item. Positionally aligned to "
            "analyst_verdicts — index j is analyst j's rationale, "
            "matching the benchmark's analysts declaration order. "
            "null (or absent) means 'this benchmark carries no "
            "rationale discipline.' A present-but-empty entry ('') "
            "means 'this analyst gave a verdict but recorded no "
            "reason on this item' — semantically distinct from null. "
            "When present, the length must equal len(benchmark.analysts)."
        ),
    )
    """Optional per-analyst, per-item rationales: the natural-language
    reason each analyst gave for their verdict on this item.
    Positionally aligned to :attr:`analyst_verdicts` — index ``j`` is
    analyst ``j``'s rationale, matching :attr:`Benchmark.analysts`
    declaration order. ``None`` (or absent) means "this benchmark
    carries no rationale discipline." A present-but-empty entry
    (``""``) means "this analyst gave a verdict but recorded no reason
    on this item" — semantically distinct from ``None``. When present,
    the length must equal ``len(benchmark.analysts)`` (enforced in
    :meth:`Benchmark._check_consistency`). The framework validates
    structure and length only; content is the analyst's responsibility.
    Added in v0.5.4 (AR1–AR12)."""
    tags: list[str] = Field(default_factory=list)
    rsr_target: RSRTarget | None = None
    references: list[Reference] = Field(default_factory=list)
    """Provenance for this implication: the guideline section, paper, or
    regulatory document that justifies the analyst's verdict. Empty by
    default; populating these turns the benchmark into an auditable
    artifact that a domain expert can cross-check against source material."""
    factor_levels: dict[str, str] = Field(default_factory=dict)
    """Per-factor level assignments for this item, naming its position
    in the benchmark's crossed design. Keys must be factor names
    declared in :attr:`Benchmark.factors`; values must be levels from
    the corresponding levels list. Empty by default — items without
    factor_levels appear in no cell and are ignored by the
    ``min_items_per_cell`` check."""
    construction_metadata: ConstructionMetadata | None = None
    """Per-item provenance for construct-validity audit: who authored
    the item, when, which models the author was blind to at
    construction time, and what source material they worked from.
    ``None`` by default; populate selectively for items where the
    provenance matters. Phase 1.3 of the construct-validity
    infrastructure (R5, R8, R9)."""
    ladder: str | None = None
    """Ladder identifier (v0.5 schema) grouping items into a directed
    variation / monotonicity sequence, e.g. ``"A"`` … ``"G"``. Descriptive
    metadata; the shape-blind measurement layer never branches on it.
    Additive (v0.17.0)."""
    variation: VariationType | None = None
    """The item's role in its ladder: base / strengthen / contested / defeat /
    abstain_anchor / monotonicity_step. Drives reporting stratification
    (v0.17.1); the κ layer (Definitions 6–10) ignores it. Additive (v0.17.0)."""
    target: str | None = None
    """Differential / succedent label for the item (v0.5 schema), e.g.
    ``"cpe"`` or ``"ards"``. In the single-succedent fragment it coincides with
    the sole conclusion; kept explicit for per-target reporting. Must name a
    declared :attr:`Benchmark.targets` entry when both are set. Additive."""
    placeholder: PlaceholderVerdict | None = None
    """Author-provided provisional verdict for pre-recruitment model dry-runs
    ONLY. **Not** an analyst verdict: the measurement layer is mechanically
    firewalled from reading it (the placeholder firewall). ``"contested"`` marks
    an item the author expects the analyst panel to split on. Additive."""
    construction_note: str | None = None
    """Author's prose justifying the item's design (e.g. why an item is
    contested). Distinct from :attr:`references` (citations) and
    :attr:`analyst_rationales` (per-analyst verdict reasons). Additive."""
    monotonicity_step: MonotonicityStep | None = None
    """Ordinal-ladder annotation, present iff :attr:`variation` is
    ``"monotonicity_step"``. Consumed by the monotonicity scorer (v0.17.1)."""

    @field_validator("premises", "conclusions", mode="before")
    @classmethod
    def _dedup_and_sort_bearer_ids(cls, v: object) -> object:
        if isinstance(v, list):
            return sorted({str(x) for x in v})
        return v

    @field_validator("references", mode="before")
    @classmethod
    def _promote_refs(cls, v: object) -> object:
        return _promote_reference_shorthand(v)

    @field_serializer("premises", "conclusions")
    def _serialize_sorted(self, value: list[str]) -> list[str]:
        return sorted(value)

    def to_implication(self) -> Implication:
        """Return the runtime :class:`Implication` view of this item."""
        return Implication(
            premises=frozenset(self.premises),
            conclusions=frozenset(self.conclusions),
            id=self.id,
        )


class Benchmark(BaseModel):
    """A benchmark :math:`\\beta` over a bearer set, analyst panel, and items.

    See the paper, Definition 4.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    id: str
    title: str | None = None
    domain: str | None = None
    description: str | None = None
    bearers: dict[str, BearerModel]
    analysts: list[AnalystModel] = Field(min_length=1)
    context_builders: ContextBuilders = Field(default_factory=ContextBuilders)
    verification_prompt: VerificationPromptOverride | None = None
    items: list[BenchmarkItem]
    factors: dict[str, list[str]] = Field(default_factory=dict)
    """Declared design factors and their levels for a crossed-design
    benchmark, e.g. ``{"side_premise_type": ["none", "irrelevant",
    "perceptual_defeater", "genuine_defeater"], "target_inference":
    ["color", "shape", "function"]}``. Items position themselves in the
    design via :attr:`BenchmarkItem.factor_levels`. Empty by default —
    omit to declare a flat (unstructured) benchmark. Phase 1.1 of the
    construct-validity infrastructure (R7, supports R12)."""
    factor_constraints: FactorConstraints | None = None
    """Optional constraints the benchmark validator enforces on the
    factorial design. Currently supports ``min_items_per_cell``. See
    :class:`FactorConstraints`."""
    factor_kinds: dict[str, Literal["substantive", "experimentally_controlled"]] = Field(
        default_factory=dict
    )
    """Optional per-factor valence tag used by ``infereval report`` to
    label null-effect findings. ``"substantive"`` factors are the
    things the analyst wants the model's behavior to differ across
    (a null Wald test on a substantive factor *weakens* the mastery
    claim — the model failed to differentiate where it should).
    ``"experimentally_controlled"`` factors are things the analyst
    *wants* not to matter (paraphrase variants, prompt seeds; a null
    Wald test on a controlled factor *strengthens* the claim —
    content-not-form behavior). Keys must be names declared in
    :attr:`factors`; factors omitted from this map get no valence
    label and the report describes the null-effect finding
    neutrally. Phase 4 of the construct-validity infrastructure
    (added in v0.5.3 in response to external review)."""
    primary_panel: str | None = None
    """Optional name of the primary analyst panel. Determines which
    panel ``κ_F*(β)`` reports against by default and which column feeds
    the cross-panel agreement calculation. When unset, defaults to the
    panel name of the first analyst declaring one (alphabetical order
    if multiple). Validation requires that at least one analyst belongs
    to the named panel when set. Phase 1.4 of the construct-validity
    infrastructure (R4)."""
    references: list[Reference] = Field(default_factory=list)
    """Corpus-level provenance: the paper, dialogue, or regulatory framework
    the benchmark is derived from. The stop-sign benchmark would cite
    Simonelli (2026); a contract-law benchmark would cite the relevant
    Restatement / UCC sections; a clinical benchmark would cite the
    governing guidelines."""
    ordinal_families: dict[str, list[str]] = Field(default_factory=dict)
    """Declared ordinal families: family name → ordered list of member bearer
    ids, lowest tier first (e.g. ``{"bnp": ["bnp_lo", "bnp_grey", "bnp_mod",
    "bnp_hi", "bnp_vhi"]}``). Distinct from :attr:`factors` (crossed-design
    dimensions on items): an ordinal family is a *tier ordering on bearers*,
    consumed by the constraint compiler (pairwise-exclusivity sequents) and the
    monotonicity scorer. Empty by default (v0.17.0, additive)."""
    copresence_rules: list[CopresenceRule] = Field(default_factory=list)
    """``@copresent`` saturation rules over ordinal families. See
    :class:`CopresenceRule`. Empty by default (v0.17.0, additive)."""
    entailment_rules: list[EntailmentRule] = Field(default_factory=list)
    """``@entails`` bearer-level entailment rules. See :class:`EntailmentRule`.
    Empty by default (v0.17.0, additive)."""
    regularities: list[Regularity] = Field(default_factory=list)
    """``~regularity`` tested-but-not-enforced regularities. See
    :class:`Regularity`. Empty by default (v0.17.0, additive)."""
    targets: list[str] = Field(default_factory=list)
    """Declared succedent / differential labels for the domain (e.g. ``["cpe",
    "ards"]``). Items name their target via :attr:`BenchmarkItem.target`. Empty
    by default (v0.17.0, additive)."""

    @field_validator("references", mode="before")
    @classmethod
    def _promote_refs(cls, v: object) -> object:
        return _promote_reference_shorthand(v)

    @model_validator(mode="after")
    def _check_consistency(self) -> Benchmark:
        # Analyst ids unique
        analyst_ids = [a.id for a in self.analysts]
        if len(analyst_ids) != len(set(analyst_ids)):
            raise ValueError("Analyst ids must be unique")

        # Panel sanity (Issue #36, Phase 1.4):
        # - If any analyst declares a panel, every analyst must declare one
        #   (no partial-panel benchmarks).
        # - If primary_panel is set, at least one analyst must belong to it.
        panel_count = sum(1 for a in self.analysts if a.panel is not None)
        if 0 < panel_count < len(self.analysts):
            no_panel = [a.id for a in self.analysts if a.panel is None]
            raise ValueError(
                f"Partial-panel benchmark: {panel_count}/{len(self.analysts)} "
                f"analysts declare a 'panel' but {sorted(no_panel)} do not. "
                f"Either all analysts must declare a panel or none must."
            )
        if self.primary_panel is not None:
            declared_panels = {a.panel for a in self.analysts if a.panel is not None}
            if self.primary_panel not in declared_panels:
                raise ValueError(
                    f"primary_panel={self.primary_panel!r} but no analyst belongs "
                    f"to that panel (declared panels: {sorted(declared_panels)})"
                )

        # Bearer ids consistent: every premise / conclusion / rsr_target id must
        # appear in self.bearers
        bearer_keys = set(self.bearers)

        # Ordinal families (v0.17.0): every tier must be a declared bearer id.
        family_names = set(self.ordinal_families)
        for fam, tiers in self.ordinal_families.items():
            unknown_tiers = set(tiers) - bearer_keys
            if unknown_tiers:
                raise ValueError(
                    f"Ordinal family {fam!r} references unknown bearer ids: "
                    f"{sorted(unknown_tiers)}"
                )

        # Bearer ordinal_family annotations must name a declared family.
        for bid, bm in self.bearers.items():
            if bm.ordinal_family is not None and bm.ordinal_family not in family_names:
                raise ValueError(
                    f"Bearer {bid!r} declares ordinal_family={bm.ordinal_family!r} but "
                    f"no such family is declared (families: {sorted(family_names)})"
                )

        # Copresence rules must reference declared families.
        for rule in self.copresence_rules:
            unknown_fam = set(rule.families) - family_names
            if unknown_fam:
                raise ValueError(
                    f"copresence_rule references unknown families {sorted(unknown_fam)} "
                    f"(declared families: {sorted(family_names)})"
                )

        # Entailment rules must reference declared bearer ids.
        for erule in self.entailment_rules:
            unknown_bearers = {erule.antecedent, erule.consequent} - bearer_keys
            if unknown_bearers:
                raise ValueError(
                    f"entailment_rule references unknown bearer ids: "
                    f"{sorted(unknown_bearers)}"
                )

        item_ids: set[str] = set()
        for item in self.items:
            if item.id in item_ids:
                raise ValueError(f"Duplicate item id: {item.id!r}")
            item_ids.add(item.id)

            unknown_premise = set(item.premises) - bearer_keys
            unknown_concl = set(item.conclusions) - bearer_keys
            if unknown_premise or unknown_concl:
                raise ValueError(
                    f"Item {item.id!r} references unknown bearer ids: "
                    f"premises={sorted(unknown_premise)}, conclusions={sorted(unknown_concl)}"
                )
            if item.rsr_target is not None:
                unknown_rsr = (
                    set(item.rsr_target.X) | set(item.rsr_target.A)
                ) - bearer_keys
                if unknown_rsr:
                    raise ValueError(
                        f"Item {item.id!r} rsr_target references unknown bearer ids: "
                        f"{sorted(unknown_rsr)}"
                    )

            # v0.5 target label must name a declared benchmark target when both
            # are set (v0.17.0).
            if (
                item.target is not None
                and self.targets
                and item.target not in self.targets
            ):
                raise ValueError(
                    f"Item {item.id!r} declares target={item.target!r} but that is not "
                    f"a declared benchmark target (declared: {sorted(self.targets)})"
                )

            # monotonicity_step consistency against the declared ordinal family.
            ms = item.monotonicity_step
            if ms is not None:
                if ms.family not in self.ordinal_families:
                    raise ValueError(
                        f"Item {item.id!r} monotonicity_step names family {ms.family!r} "
                        f"which is not a declared ordinal family "
                        f"(families: {sorted(family_names)})"
                    )
                tiers = self.ordinal_families[ms.family]
                if ms.tier not in tiers:
                    raise ValueError(
                        f"Item {item.id!r} monotonicity_step tier {ms.tier!r} is not in "
                        f"family {ms.family!r} (tiers: {tiers})"
                    )
                if ms.tier_index != tiers.index(ms.tier):
                    raise ValueError(
                        f"Item {item.id!r} monotonicity_step tier_index={ms.tier_index} "
                        f"but {ms.tier!r} is at index {tiers.index(ms.tier)} in family "
                        f"{ms.family!r}"
                    )
                if ms.fixed is not None and ms.fixed not in bearer_keys:
                    raise ValueError(
                        f"Item {item.id!r} monotonicity_step fixed={ms.fixed!r} is not a "
                        f"declared bearer id"
                    )

            # Analyst-verdict tuple length must equal m
            if len(item.analyst_verdicts) != len(self.analysts):
                raise ValueError(
                    f"Item {item.id!r} has {len(item.analyst_verdicts)} analyst verdicts "
                    f"but the benchmark declares {len(self.analysts)} analysts"
                )

            # Analyst-rationale tuple length must equal m when supplied (AR5).
            # When None (absent), no constraint applies (AR3).
            if (
                item.analyst_rationales is not None
                and len(item.analyst_rationales) != len(self.analysts)
            ):
                raise ValueError(
                    f"Item {item.id!r} has {len(item.analyst_rationales)} analyst "
                    f"rationales but the benchmark declares {len(self.analysts)} "
                    f"analysts"
                )

            # Factor-level keys/values must be declared in self.factors
            for fkey, fval in item.factor_levels.items():
                if fkey not in self.factors:
                    raise ValueError(
                        f"Item {item.id!r} declares factor_levels[{fkey!r}] but "
                        f"that factor is not declared at the benchmark level "
                        f"(declared factors: {sorted(self.factors)})"
                    )
                if fval not in self.factors[fkey]:
                    raise ValueError(
                        f"Item {item.id!r} declares factor_levels[{fkey!r}]={fval!r} "
                        f"but {fval!r} is not a declared level for {fkey!r} "
                        f"(declared levels: {self.factors[fkey]})"
                    )

        # Regularity test_item_ids must reference declared items (v0.17.0).
        for reg in self.regularities:
            unknown_items = set(reg.test_item_ids) - item_ids
            if unknown_items:
                raise ValueError(
                    f"Regularity {reg.description!r} references unknown item ids: "
                    f"{sorted(unknown_items)}"
                )

        # factor_kinds keys must reference declared factors. (Values are
        # constrained to {"substantive", "experimentally_controlled"} by
        # the Literal typing at the field declaration.)
        for fkey in self.factor_kinds:
            if fkey not in self.factors:
                raise ValueError(
                    f"factor_kinds references unknown factor {fkey!r} "
                    f"(declared factors: {sorted(self.factors)})"
                )

        # min_items_per_cell — every cell of the fully crossed design must
        # contain ≥ k items (an item is in a cell iff its factor_levels
        # match the cell on every factor).
        if (
            self.factor_constraints is not None
            and self.factor_constraints.min_items_per_cell is not None
            and self.factors
        ):
            k = self.factor_constraints.min_items_per_cell
            counts = self.cells()
            underpopulated = sorted(
                [(cell, n) for cell, n in counts.items() if n < k],
                key=lambda kv: (kv[1], kv[0]),
            )
            if underpopulated:
                shown = ", ".join(
                    f"{dict(zip(sorted(self.factors), cell, strict=True))}={n}"
                    for cell, n in underpopulated[:5]
                )
                more = (
                    f" and {len(underpopulated) - 5} more"
                    if len(underpopulated) > 5
                    else ""
                )
                raise ValueError(
                    f"min_items_per_cell={k} not met: "
                    f"{len(underpopulated)}/{len(counts)} cells are underpopulated "
                    f"({shown}{more})"
                )

        return self

    def cells(self) -> dict[tuple[str, ...], int]:
        """Count items per cell of the fully crossed design.

        Returns a mapping from cell-tuple to item count, where the
        cell-tuple is the per-factor level value in the order given by
        ``sorted(self.factors)``. Every cell of the cartesian product is
        present in the result (count 0 if no item lands there); items
        whose ``factor_levels`` don't name every declared factor are
        excluded entirely (they belong to no cell).
        """
        from itertools import product as _product

        if not self.factors:
            return {}
        factor_names = sorted(self.factors)
        # Initialise every cell to zero so under-populated cells appear.
        cells: dict[tuple[str, ...], int] = {
            tuple(combo): 0
            for combo in _product(*(self.factors[f] for f in factor_names))
        }
        for item in self.items:
            if not all(f in item.factor_levels for f in factor_names):
                continue
            key = tuple(item.factor_levels[f] for f in factor_names)
            cells[key] = cells.get(key, 0) + 1
        return cells

    def is_fully_crossed_at_k(self, k: int) -> bool:
        """True iff every cell of the crossed design contains at least ``k`` items.

        Returns ``False`` when no factors are declared (an unstructured
        benchmark trivially fails any factorial coverage check).
        """
        if not self.factors:
            return False
        return all(n >= k for n in self.cells().values())

    @property
    def n_paraphrase_variants(self) -> int:
        """Number of paraphrase variants this benchmark admits at evaluation time.

        Returns ``1 + max(len(b.paraphrases) for b in bearers)``, or just
        ``1`` if no bearer carries any paraphrase. Variant ``0`` always
        uses the canonical :attr:`BearerModel.expression`; variant
        ``k >= 1`` uses ``bearer.paraphrases[k-1]`` when available and
        falls back to the canonical otherwise (per
        :func:`infereval.endorsement._expressions_for`).

        Phase 1.2 of the construct-validity infrastructure (R10).
        """
        if not self.bearers:
            return 1
        return 1 + max(len(b.paraphrases) for b in self.bearers.values())

    @property
    def m(self) -> int:
        """Number of analysts :math:`m`."""
        return len(self.analysts)

    @property
    def n(self) -> int:
        """Number of items :math:`n`."""
        return len(self.items)

    def bearer(self, bearer_id: str) -> _RuntimeBearer:
        """Runtime :class:`Bearer` for ``bearer_id``."""
        return self.bearers[bearer_id].to_runtime(bearer_id)

    def runtime_bearers(self) -> dict[str, _RuntimeBearer]:
        """All bearers as runtime :class:`Bearer` instances, keyed by id."""
        return {bid: bm.to_runtime(bid) for bid, bm in self.bearers.items()}

    def analyst_index(self, analyst_id: str) -> int:
        """0-based index of analyst ``analyst_id`` within :attr:`analysts`."""
        for j, a in enumerate(self.analysts):
            if a.id == analyst_id:
                return j
        raise KeyError(f"No analyst with id {analyst_id!r}")

    def panel_names(self) -> list[str]:
        """Sorted unique panel names across :attr:`analysts`.

        Returns ``[]`` for an unpanelled (flat) benchmark. Phase 1.4 of
        the construct-validity infrastructure (R4).
        """
        return sorted({a.panel for a in self.analysts if a.panel is not None})

    def analysts_in_panel(self, name: str) -> list[AnalystModel]:
        """Every analyst whose :attr:`AnalystModel.panel` equals ``name``."""
        return [a for a in self.analysts if a.panel == name]

    def analyst_indices_in_panel(self, name: str) -> list[int]:
        """0-based indices into the verdict tuple for analysts in ``name``.

        Returned in the same order analysts appear in :attr:`analysts`,
        which is also the order verdicts appear in each item's
        :attr:`BenchmarkItem.analyst_verdicts` list.
        """
        return [j for j, a in enumerate(self.analysts) if a.panel == name]

    def resolved_primary_panel(self) -> str | None:
        """The primary panel name to use for analyses.

        Returns :attr:`primary_panel` if set; otherwise the
        alphabetically-first declared panel name; otherwise ``None`` for
        unpanelled benchmarks.
        """
        if self.primary_panel is not None:
            return self.primary_panel
        names = self.panel_names()
        return names[0] if names else None

    @classmethod
    def load(cls, path: str | Path) -> Benchmark:
        """Load a benchmark from JSON on disk and validate."""
        with Path(path).open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    @classmethod
    def loads(cls, text: str) -> Benchmark:
        """Load a benchmark from a JSON string and validate."""
        return cls.model_validate_json(text)

    def dump(self, path: str | Path, *, indent: int = 2) -> None:
        """Write the benchmark to ``path`` as canonical-ish JSON."""
        with Path(path).open("w", encoding="utf-8") as f:
            f.write(self.dumps(indent=indent))
            f.write("\n")

    def dumps(self, *, indent: int = 2) -> str:
        """Return the benchmark as a JSON string."""
        return self.model_dump_json(indent=indent, exclude_none=True)
