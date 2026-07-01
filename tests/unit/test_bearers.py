"""Tests for the v0.5 bearers-file loader (:mod:`infereval.bearers`)."""

from __future__ import annotations

import pytest

from infereval.bearers import (
    BearersParseError,
    load_bearers_file,
    parse_bearers_file,
)

_SAMPLE = '''\
# header prose that mentions @copresent and @ordinal mid-sentence, e.g.
# "the @ordinal rs declaration stands" — must NOT be read as a declaration.
# @ordinal bnp = [bnp_lo, bnp_hi]   @target cpe
# @mutex   side = [left, right]
# @entails septic_shock -> sep
# @copresent pf & rs
#   (this indented continuation is prose and is ignored)
# ~regularity: rs up => pf up (defeasible)

bnp_lo "BNP under 100"
bnp_hi "BNP over 500"
left "left-sided"
right "right-sided"
pf_x "a P/F tier"
rs_x "a support tier"
septic_shock "in septic shock"
sep "has sepsis"
'''


def _sample_with_pf_rs_families() -> str:
    # Add pf and rs as declared families so @copresent pf & rs validates.
    return _SAMPLE.replace(
        "# @mutex   side = [left, right]",
        "# @mutex   side = [left, right]\n# @ordinal pf = [pf_x]\n# @ordinal rs = [rs_x]",
    )


class TestParse:
    def test_bearers_and_families(self) -> None:
        doc = parse_bearers_file(_sample_with_pf_rs_families())
        assert doc.bearers["bnp_lo"] == "BNP under 100"
        assert len(doc.bearers) == 8
        fam = {d.family: d for d in doc.families}
        assert fam["bnp"].tiers == ("bnp_lo", "bnp_hi")
        assert fam["bnp"].ordered is True
        assert fam["bnp"].target == "cpe"
        assert fam["side"].ordered is False  # @mutex
        assert fam["side"].target is None

    def test_entails_copresent_regularity(self) -> None:
        doc = parse_bearers_file(_sample_with_pf_rs_families())
        assert doc.entailments == (("septic_shock", "sep"),)
        assert doc.copresence == (("pf", "rs"),)
        assert doc.regularities == ("rs up => pf up (defeasible)",)

    def test_helper_maps(self) -> None:
        doc = parse_bearers_file(_sample_with_pf_rs_families())
        assert doc.ordinal_families()["bnp"] == ["bnp_lo", "bnp_hi"]
        assert doc.bearer_family_map()["bnp_lo"] == "bnp"
        assert doc.bearer_family_map()["left"] == "side"

    def test_prose_mention_not_parsed_as_annotation(self) -> None:
        # The header lines mention @copresent / @ordinal mid-sentence. If those
        # were misread as declarations the parse would raise or produce junk.
        doc = parse_bearers_file(_sample_with_pf_rs_families())
        assert len(doc.copresence) == 1  # only the real "@copresent pf & rs"


class TestErrors:
    def test_malformed_bearer_line(self) -> None:
        with pytest.raises(BearersParseError, match="malformed bearer line"):
            parse_bearers_file('bnp_lo BNP under 100 with no quotes\n')

    def test_duplicate_id_conflicting_expression(self) -> None:
        text = 'x "one"\nx "two"\n'
        with pytest.raises(BearersParseError, match="additive-only"):
            parse_bearers_file(text)

    def test_duplicate_id_same_expression_ok(self) -> None:
        doc = parse_bearers_file('x "one"\nx "one"\n')
        assert doc.bearers == {"x": "one"}

    def test_ordinal_tier_undefined_bearer(self) -> None:
        text = '# @ordinal fam = [a, ghost]\na "a"\n'
        with pytest.raises(BearersParseError, match="undefined bearer ids"):
            parse_bearers_file(text)

    def test_entails_undefined_bearer(self) -> None:
        text = '# @entails a -> ghost\na "a"\n'
        with pytest.raises(BearersParseError, match="undefined bearer ids"):
            parse_bearers_file(text)

    def test_copresent_undeclared_family(self) -> None:
        text = '# @ordinal pf = [pf_x]\n# @copresent pf & rs\npf_x "x"\n'
        with pytest.raises(BearersParseError, match="undeclared families"):
            parse_bearers_file(text)

    def test_copresent_single_family_rejected(self) -> None:
        text = '# @copresent pf\n'
        with pytest.raises(BearersParseError, match="at least two families"):
            parse_bearers_file(text)


class TestRealFile:
    def test_v05_bearers_file(self) -> None:
        doc = load_bearers_file("examples/AUMC_pilot/bearers_v0.5.txt")
        assert len(doc.bearers) == 47
        assert len(doc.families) == 11
        assert doc.copresence == (("pf", "rs"),)
        assert doc.entailments == (("septic_shock", "sep"),)
        assert doc.bearers["cpe"].startswith("the patient has cardiogenic")
        # The mid-sentence @copresent / @ordinal mentions in the CHANGELOG header
        # must not have produced spurious declarations.
        assert len(doc.copresence) == 1
