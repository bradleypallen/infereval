"""Tests for v0.8.0 decomposition-under-powered integration (closes #84).

Covers:
- ``NegativeFinding.source`` Literal extended with
  ``"decomposition_under_powered"``.
- ``collect_negative_findings(decomposition_cells=...)`` emits one
  finding per under-powered cell and skips healthy cells.
- ``render_markdown`` threads ``decomposition_cells`` into section 4b
  under the new "Decomposition under-powered (R12)" group label.
- The new collector keeps existing callers (no ``decomposition_cells``
  arg) intact — backward compatible.
"""

from __future__ import annotations

from pathlib import Path

from infereval.report import (
    ConstructValidityClaims,
    NegativeFinding,
    collect_negative_findings,
    render_markdown,
)

STOP_SIGN_PATH = (
    Path(__file__).parent.parent.parent / "examples" / "stop_sign" / "benchmark.json"
)


def _under_powered_cell(title: str, n: int = 2, kappa_f: float = -1.0) -> dict[str, object]:
    return {
        "title": title,
        "n_substantive": n,
        "cohens_kappa": None,
        "fleiss_kappa": kappa_f,
        "is_under_powered": True,
    }


def _healthy_cell(title: str, n: int = 50) -> dict[str, object]:
    return {
        "title": title,
        "n_substantive": n,
        "cohens_kappa": 0.7,
        "fleiss_kappa": 0.7,
        "is_under_powered": False,
    }


# ---- collect_negative_findings ------------------------------------------


class TestCollector:
    def test_under_powered_cell_emits_one_finding(self) -> None:
        findings = collect_negative_findings(
            decomposition_cells=[_under_powered_cell("By tag: irrelevant-addition")]
        )
        assert len(findings) == 1
        assert findings[0].source == "decomposition_under_powered"
        assert "irrelevant-addition" in findings[0].summary
        assert "n_substantive = 2" in findings[0].summary
        # Threshold value must be mentioned for the reader.
        assert "(< 10)" in findings[0].summary

    def test_healthy_cell_does_not_emit_finding(self) -> None:
        findings = collect_negative_findings(
            decomposition_cells=[_healthy_cell("By tag: base-inference")]
        )
        # The new collector only fires on is_under_powered=True cells.
        assert [f for f in findings if f.source == "decomposition_under_powered"] == []

    def test_mixed_cells_emit_only_under_powered(self) -> None:
        findings = collect_negative_findings(
            decomposition_cells=[
                _under_powered_cell("By tag: irrelevant-addition", n=2),
                _healthy_cell("By tag: base-inference", n=50),
                _under_powered_cell("By tag: defeater", n=1, kappa_f=1.0),
            ]
        )
        dec = [f for f in findings if f.source == "decomposition_under_powered"]
        assert len(dec) == 2
        titles = [f.summary for f in dec]
        assert any("irrelevant-addition" in t for t in titles)
        assert any("defeater" in t for t in titles)
        assert not any("base-inference" in t for t in titles)

    def test_kappa_undefined_handled(self) -> None:
        """When both κ values are None, the finding still emits but the
        kappa-string falls back to a degenerate stanza."""
        findings = collect_negative_findings(
            decomposition_cells=[
                {
                    "title": "By tag: empty",
                    "n_substantive": 0,
                    "cohens_kappa": None,
                    "fleiss_kappa": None,
                    "is_under_powered": True,
                }
            ]
        )
        assert len(findings) == 1
        assert "κ_C undefined" in findings[0].summary
        assert "κ_F undefined" in findings[0].summary

    def test_no_decomposition_cells_argument_is_backward_compatible(self) -> None:
        """Pre-v0.8.0 callers omit the argument — no new findings, no
        crash."""
        findings = collect_negative_findings(
            structure_report=None,
            sweep_summary=None,
            model_fit=None,
            retest_result=None,
        )
        # No phase-2 inputs => no findings.
        assert findings == []


# ---- NegativeFinding.source Literal --------------------------------------


def test_negative_finding_accepts_new_source() -> None:
    """The Literal must include the new source string; constructing one
    with it must succeed."""
    nf = NegativeFinding(
        source="decomposition_under_powered",
        summary="dummy",
    )
    assert nf.source == "decomposition_under_powered"


# ---- render_markdown section 4b grouping ---------------------------------


class TestRenderingSection4b:
    def test_under_powered_cells_appear_under_R12_group_label(self) -> None:  # noqa: N802 -- literal
        """Section 4b groups findings by source; the new label is
        "Decomposition under-powered (R12)"."""
        from infereval.benchmark import Benchmark
        from infereval.endorsement import EndorsementConfig
        from infereval.evaluation import evaluate
        from infereval.providers.mock import ScriptedProvider

        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 8)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        claims = ConstructValidityClaims.stub()
        md = render_markdown(
            evaluation=eta,
            benchmark=bench,
            claims=claims,
            decomposition_cells=[
                _under_powered_cell("By tag: irrelevant-addition", n=2),
            ],
        )
        assert "## 4b. Negative findings" in md
        assert "### Decomposition under-powered (R12) (1 flagged)" in md
        # The cell summary must appear in the rendered body.
        assert "irrelevant-addition" in md
        assert "n_substantive = 2" in md

    def test_no_decomposition_cells_keeps_old_4b_behavior(self) -> None:
        """Omitting decomposition_cells must NOT introduce a new
        section — backward compat for the pre-v0.8.0 caller surface."""
        from infereval.benchmark import Benchmark
        from infereval.endorsement import EndorsementConfig
        from infereval.evaluation import evaluate
        from infereval.providers.mock import ScriptedProvider

        bench = Benchmark.load(STOP_SIGN_PATH)
        provider = ScriptedProvider(responses=["GOOD"] * 8)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        claims = ConstructValidityClaims.stub()
        md = render_markdown(
            evaluation=eta,
            benchmark=bench,
            claims=claims,
        )
        assert "Decomposition under-powered" not in md
