"""Derived implication frame :math:`\\langle B, I_M \\rangle`.

Definition 3 of the paper (Allen 2026):

.. math::
   \\langle \\Gamma, \\Delta \\rangle \\in I_M \\iff
       \\Gamma \\cap \\Delta \\neq \\emptyset \\;\\;\\text{(i)}
       \\;\\;\\text{or}\\;\\;
       E_M(\\langle \\Gamma, \\Delta \\rangle) = \\text{good} \\;\\;\\text{(ii)}

with :math:`\\langle \\emptyset, \\emptyset \\rangle \\notin I_M` by stipulation.

The frame is *lazy*: it stores the queried endorsements only, and answers
membership questions via the iff above. The full :math:`I_M` over
:math:`\\wp(B) \\times \\wp(B)` is unbounded and never materialized.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .types import Bearer, Implication, Verdict


@dataclass(frozen=True)
class DerivedFrame:
    """The implication frame :math:`\\langle B, I_M \\rangle` derived from a model :math:`M`.

    Construct via :meth:`from_endorsements`; do not instantiate directly unless
    you have already validated that all implication bearer-ids reference
    elements of ``bearers``.

    Attributes
    ----------
    bearers
        Read-only mapping ``id -> Bearer`` representing :math:`B`.
    endorsements
        Read-only mapping from each *queried* :class:`Implication` to the
        verdict :math:`E_M` returned. Implications not in this mapping are
        treated as un-queried; :meth:`contains` returns ``False`` for them
        unless clause (i) applies.
    """

    bearers: Mapping[str, Bearer]
    endorsements: Mapping[Implication, Verdict]

    @classmethod
    def from_endorsements(
        cls,
        bearers: Mapping[str, Bearer],
        endorsements: Mapping[Implication, Verdict],
    ) -> DerivedFrame:
        """Build a frame from a bearer set and a mapping of queried endorsements.

        Raises
        ------
        ValueError
            If any implication references a bearer id not present in ``bearers``.
        """
        bearer_ids = set(bearers)
        for imp in endorsements:
            unknown = (imp.premises | imp.conclusions) - bearer_ids
            if unknown:
                raise ValueError(
                    f"Implication {imp!r} references unknown bearer ids: {sorted(unknown)}"
                )
        return cls(
            bearers=MappingProxyType(dict(bearers)),
            endorsements=MappingProxyType(dict(endorsements)),
        )

    def contains(self, implication: Implication) -> bool:
        """Membership in :math:`I_M` per Definition 3.

        ``<empty, empty>`` is excluded by stipulation. Otherwise the iff of
        clauses (i) and (ii) decides. For implications not in
        :attr:`endorsements`, clause (ii) is treated as false (we have no
        evidence of endorsement).
        """
        if implication.is_empty_empty:
            return False
        if implication.intersects():
            return True  # clause (i)
        return self.endorsements.get(implication) == Verdict.GOOD  # clause (ii)

    def __contains__(self, implication: Implication) -> bool:
        return self.contains(implication)

    def satisfies_containment(self) -> bool:
        """Containment is satisfied by construction (clause (i) of Definition 3).

        This always returns ``True``; the method is provided as an explicit
        witness of the invariant the paper makes a remark of ("Containment by
        construction"). Tests assert it to guard against future refactors that
        might break the invariant.
        """
        return True

    def queried_implications(self) -> frozenset[Implication]:
        """The implications for which an :math:`E_M` verdict has been recorded."""
        return frozenset(self.endorsements)


def derive_closure(frame: DerivedFrame) -> DerivedFrame:
    """Multisuccedent cut / RSR-closure over a frame's verdicts — NOT IMPLEMENTED.

    Deferred by design (generalization brief §9). EM-elicit-and-score does not
    need cut: membership is decided per-implication by :meth:`DerivedFrame.contains`.
    A closure becomes load-bearing only if infereval later *composes* verdicts
    (e.g. chaining ``rs ⊢ {pf tiers}`` with pf-keyed targets), which is exactly
    where classical vs. substructural readings of the disjunctive succedent
    diverge. This function is the single seam where such a closure would attach;
    implement it here rather than hand-rolling verdict composition elsewhere.
    """
    raise NotImplementedError(
        "Multisuccedent cut / RSR-closure is deferred (generalization brief §9); "
        "see derive_closure.__doc__ for the intended seam."
    )
