"""Constraint compiler: family declarations → sequents + admissibility rules.

Turns a benchmark's vocabulary metadata (ordinal / mutex families, co-presence
rules, entailments) into

- **sequents** to add to the benchmark — the pairwise *exclusivity* sequents
  ``⟨{x_i, x_j}, ∅⟩`` ("holding both tiers at once is incoherent") for each
  family, plus, opt-in, *exhaustivity* sequents and *entailment* sequents; and
- **admissibility rules** the item generator must honour — the ``@copresent``
  saturation constraints ("an item carrying an A-tier must carry a B-tier and
  vice versa").

Domain-agnostic by construction: it operates on declarations and knows nothing
about the domain the families describe. The exclusivity emission is identical
for ``@ordinal`` and ``@mutex`` families (both are within-family exclusive); the
ordering of an ``@ordinal`` family matters only later, to the monotonicity
scorer, via each item's ``monotonicity_step`` — not here.

Note on arity: exclusivity sequents have an empty succedent (``Δ = ∅``) and
exhaustivity sequents have ``|Δ| ≥ 2``. This module only *computes* them as data;
*evaluating* a non-singleton-succedent sequent through the endorsement core is a
later-release concern (the multi-succedent template). Emission here is unaffected.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations

from .types import Implication

__all__ = [
    "AdmissibilityRule",
    "CompileResult",
    "CopresenceSpec",
    "compile_constraints",
    "is_saturated",
]


@dataclass(frozen=True)
class CopresenceSpec:
    """A co-presence declaration over two or more families.

    ``exhaustivity`` off (default): the compiler emits only an admissibility
    rule and no sequents. On: it additionally emits exhaustivity sequents making
    "committing a tier while denying every co-present family's tier" incoherent
    (brief §2/§7) — use only when a domain wants exhaustivity itself testable and
    the reporting stratification is respected.
    """

    families: tuple[str, ...]
    exhaustivity: bool = False


@dataclass(frozen=True)
class AdmissibilityRule:
    """A generator constraint: the listed families must co-occur in Γ (or none do).

    Checked against a candidate Γ with :func:`is_saturated`, which needs the
    family→tiers mapping (kept external so this rule stays a simple, hashable
    value).
    """

    families: tuple[str, ...]


@dataclass(frozen=True)
class CompileResult:
    """The compiler's output: sequents to add and admissibility rules to honour."""

    sequents: tuple[Implication, ...] = ()
    admissibility: tuple[AdmissibilityRule, ...] = ()
    exclusivity_sequents: tuple[Implication, ...] = field(default=(), repr=False)
    exhaustivity_sequents: tuple[Implication, ...] = field(default=(), repr=False)
    entailment_sequents: tuple[Implication, ...] = field(default=(), repr=False)


def compile_constraints(
    families: Mapping[str, Sequence[str]],
    copresence: Sequence[CopresenceSpec] = (),
    entailments: Sequence[tuple[str, str]] = (),
    *,
    emit_entailment_sequents: bool = False,
) -> CompileResult:
    """Compile family declarations into sequents + admissibility rules.

    Parameters
    ----------
    families
        Family name → its tiers (bearer ids). Both ordinal and mutex families
        are passed here; exclusivity emission treats them identically.
    copresence
        Co-presence declarations. Each yields one admissibility rule; with
        ``exhaustivity`` set it also yields exhaustivity sequents.
    entailments
        ``(antecedent, consequent)`` bearer-id pairs.
    emit_entailment_sequents
        When True, emit ``⟨{a}, {b}⟩`` for each entailment (opt-in — entailments
        are often left as vocabulary metadata rather than elicited items).
    """
    exclusivity: list[Implication] = []
    for fam in sorted(families):
        tiers = sorted(set(families[fam]))
        for a, b in combinations(tiers, 2):
            # Order-independent: sort the pair so the emitted sequent is canonical.
            exclusivity.append(Implication.of([a, b], []))

    admissibility: list[AdmissibilityRule] = []
    exhaustivity: list[Implication] = []
    for spec in copresence:
        admissibility.append(AdmissibilityRule(families=tuple(spec.families)))
        if spec.exhaustivity:
            for fam in spec.families:
                others = [f for f in spec.families if f != fam]
                other_tiers = sorted(
                    {t for f in others for t in families.get(f, ())}
                )
                for tier in sorted(set(families.get(fam, ()))):
                    exhaustivity.append(Implication.of([tier], other_tiers))

    entailment: list[Implication] = []
    if emit_entailment_sequents:
        for ante, cons in entailments:
            entailment.append(Implication.of([ante], [cons]))

    all_sequents = tuple(exclusivity) + tuple(exhaustivity) + tuple(entailment)
    return CompileResult(
        sequents=all_sequents,
        admissibility=tuple(admissibility),
        exclusivity_sequents=tuple(exclusivity),
        exhaustivity_sequents=tuple(exhaustivity),
        entailment_sequents=tuple(entailment),
    )


def is_saturated(
    gamma: Iterable[str],
    rule: AdmissibilityRule,
    family_tiers: Mapping[str, Iterable[str]],
) -> bool:
    """Whether Γ satisfies a co-presence rule: every listed family present, or none.

    A Γ that carries a tier from one co-present family but not the other(s)
    violates saturation and would be rejected (or auto-completed) by the item
    generator.
    """
    g = set(gamma)
    present = sum(
        1 for fam in rule.families if g & set(family_tiers.get(fam, ()))
    )
    return present == 0 or present == len(rule.families)
