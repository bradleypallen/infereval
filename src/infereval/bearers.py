"""Loader for v0.5 bearers files.

A *bearers file* is the human-authored source of a benchmark's vocabulary: one
``id "expression"`` line per content-bearer, plus a header of annotation
comments declaring the structure over those bearers. The annotation grammar
(all carried on ``#``-comment lines so the file also reads as a plain
``id "statement"`` block once comments are stripped):

- ``@ordinal FAM = [t0, t1, ...]  @target T`` — an ordered, mutually-exclusive
  family ``FAM`` whose members are the listed bearer ids, lowest tier first. The
  optional ``@target T`` names the differential the family bears on.
- ``@mutex FAM = [a, b, ...]`` — an unordered mutually-exclusive family (same
  shape as ``@ordinal`` minus the ordering commitment).
- ``@entails a -> b`` — bearer-level entailment: ``a`` present entails ``b``.
- ``@copresent A & B`` — a saturation / well-formedness rule: families ``A`` and
  ``B`` must co-occur in an item. NOT an exclusion of any tier combination.
- ``~regularity: <description>`` — a tested-but-not-enforced defeasible
  regularity; earns no membership in the derived frame.

The parser is deliberately dependency-light (stdlib + dataclasses only): it
returns a :class:`BearersDoc` of plain data, which the CLI / benchmark loader
maps onto the Pydantic models in :mod:`infereval.benchmark`. This keeps the
grammar independently testable and avoids an import cycle.

**Bearer-versioning contract (additive-only within a minor version).** A bearer
id is a stable handle: within a benchmark's minor version, bearer definitions
are *additive only* — you may add bearers, never silently redefine an existing
id's ``expression``, because historical η reference bearers by id and a
redefinition would make old captures un-rescorable. If a bearer's meaning must
change, mint a NEW id and retire the old one. Reusing an id with a *different*
expression inside a single file is a hard error (:class:`BearersParseError`);
across versions it is the author's discipline, documented here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "BearersDoc",
    "BearersParseError",
    "OrdinalDecl",
    "load_bearers_file",
    "parse_bearers_file",
]


class BearersParseError(ValueError):
    """Raised when a bearers file is malformed or internally inconsistent."""


@dataclass(frozen=True)
class OrdinalDecl:
    """A declared family of bearers.

    ``ordered`` distinguishes ``@ordinal`` (True — the tier order is meaningful,
    e.g. for monotonicity ladders) from ``@mutex`` (False — mutually exclusive
    but unordered). ``target`` is the optional ``@target`` differential.
    """

    family: str
    tiers: tuple[str, ...]
    ordered: bool = True
    target: str | None = None


@dataclass(frozen=True)
class BearersDoc:
    """Parsed contents of a bearers file."""

    bearers: dict[str, str] = field(default_factory=dict)
    """Bearer id → canonical natural-language expression."""
    families: tuple[OrdinalDecl, ...] = ()
    """Declared ordinal / mutex families, in declaration order."""
    copresence: tuple[tuple[str, ...], ...] = ()
    """Each entry is a set of family names that must co-occur (``@copresent``)."""
    entailments: tuple[tuple[str, str], ...] = ()
    """Each entry is an ``(antecedent, consequent)`` bearer-id pair (``@entails``)."""
    regularities: tuple[str, ...] = ()
    """Free-text ``~regularity`` descriptions (tested, not enforced)."""

    def ordinal_families(self) -> dict[str, list[str]]:
        """Family name → ordered tier list, for :attr:`Benchmark.ordinal_families`."""
        return {d.family: list(d.tiers) for d in self.families}

    def bearer_family_map(self) -> dict[str, str]:
        """Bearer id → the family it is a tier of (only for family members)."""
        out: dict[str, str] = {}
        for d in self.families:
            for tier in d.tiers:
                out[tier] = d.family
        return out


# Annotation grammar (matched against the text after the leading ``#`` is stripped).
_ORDINAL_RE = re.compile(r"@(ordinal|mutex)\s+(\w+)\s*=\s*\[([^\]]*)\]")
_TARGET_RE = re.compile(r"@target\s+(\w+)")
_ENTAILS_RE = re.compile(r"@entails\s+(\w+)\s*->\s*(\w+)")
_COPRESENT_RE = re.compile(r"@copresent\s+(.+)")
_REGULARITY_RE = re.compile(r"~regularity\s*:\s*(.+)")
_BEARER_RE = re.compile(r'^(\S+)\s+"(.*)"\s*$')


def parse_bearers_file(text: str) -> BearersDoc:
    """Parse the contents of a bearers file into a :class:`BearersDoc`.

    Raises :class:`BearersParseError` on a malformed bearer line, a duplicate
    bearer id with a conflicting expression, or a structural inconsistency
    (an ordinal tier, entailment endpoint, or copresent family that is not a
    defined bearer / declared family).
    """
    bearers: dict[str, str] = {}
    families: list[OrdinalDecl] = []
    copresence: list[tuple[str, ...]] = []
    entailments: list[tuple[str, str]] = []
    regularities: list[str] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            _parse_annotation(
                line.lstrip("#").strip(),
                families=families,
                copresence=copresence,
                entailments=entailments,
                regularities=regularities,
                lineno=lineno,
            )
            continue
        # A bearer definition line.
        m = _BEARER_RE.match(line)
        if m is None:
            raise BearersParseError(
                f"line {lineno}: malformed bearer line (expected 'id \"expression\"'): "
                f"{raw!r}"
            )
        bid, expr = m.group(1), m.group(2)
        if bid in bearers and bearers[bid] != expr:
            raise BearersParseError(
                f"line {lineno}: bearer id {bid!r} redefined with a different "
                f"expression (was {bearers[bid]!r}). Bearer ids are additive-only; "
                f"mint a new id instead of redefining."
            )
        bearers[bid] = expr

    doc = BearersDoc(
        bearers=bearers,
        families=tuple(families),
        copresence=tuple(copresence),
        entailments=tuple(entailments),
        regularities=tuple(regularities),
    )
    _validate(doc)
    return doc


def _parse_annotation(
    body: str,
    *,
    families: list[OrdinalDecl],
    copresence: list[tuple[str, ...]],
    entailments: list[tuple[str, str]],
    regularities: list[str],
    lineno: int,
) -> None:
    """Extract a single annotation from a comment line's body, if present.

    An annotation is recognised only when its marker is the *first* token of the
    comment body (``.match`` is anchored at the start), so prose that merely
    mentions ``@copresent`` / ``@ordinal`` mid-sentence is not misread as a
    declaration.
    """
    m = _ORDINAL_RE.match(body)
    if m is not None:
        kind, family, inner = m.group(1), m.group(2), m.group(3)
        tiers = tuple(t.strip() for t in inner.split(",") if t.strip())
        if not tiers:
            raise BearersParseError(
                f"line {lineno}: @{kind} {family!r} declares no tiers"
            )
        tmatch = _TARGET_RE.search(body[m.end() :])
        families.append(
            OrdinalDecl(
                family=family,
                tiers=tiers,
                ordered=(kind == "ordinal"),
                target=tmatch.group(1) if tmatch else None,
            )
        )
        return
    m = _ENTAILS_RE.match(body)
    if m is not None:
        entailments.append((m.group(1), m.group(2)))
        return
    m = _COPRESENT_RE.match(body)
    if m is not None:
        # Split on '&'; take the first whitespace-delimited token of each part so
        # trailing prose after the family names is ignored.
        fams = tuple(
            part.split()[0] for part in m.group(1).split("&") if part.split()
        )
        if len(fams) < 2:
            raise BearersParseError(
                f"line {lineno}: @copresent needs at least two families, got {fams}"
            )
        copresence.append(fams)
        return
    m = _REGULARITY_RE.match(body)
    if m is not None:
        regularities.append(m.group(1).strip())
        return
    # Otherwise it is an ordinary prose comment; ignore.


def _validate(doc: BearersDoc) -> None:
    """Check that every declared reference resolves to a defined bearer / family."""
    bearer_ids = set(doc.bearers)
    family_names = {d.family for d in doc.families}

    for decl in doc.families:
        missing = [t for t in decl.tiers if t not in bearer_ids]
        if missing:
            raise BearersParseError(
                f"@{'ordinal' if decl.ordered else 'mutex'} {decl.family!r} lists "
                f"undefined bearer ids: {missing}"
            )
    for ante, cons in doc.entailments:
        undefined = [b for b in (ante, cons) if b not in bearer_ids]
        if undefined:
            raise BearersParseError(
                f"@entails {ante} -> {cons} references undefined bearer ids: {undefined}"
            )
    for fams in doc.copresence:
        undefined_fams = [f for f in fams if f not in family_names]
        if undefined_fams:
            raise BearersParseError(
                f"@copresent {' & '.join(fams)} references undeclared families: "
                f"{undefined_fams}"
            )


def load_bearers_file(path: str | Path) -> BearersDoc:
    """Read and parse a bearers file from disk."""
    return parse_bearers_file(Path(path).read_text(encoding="utf-8"))
