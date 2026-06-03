"""Tests for ``infereval.survey.render`` — the platform-agnostic helpers
shared by all three survey-platform exporters and importers.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from infereval.benchmark import BearerModel, Benchmark, BenchmarkItem
from infereval.survey.render import (
    DEFAULT_EXPERTISE_PROMPT,
    DEFAULT_QUESTION_HEADER,
    DEFAULT_RATIONALE_PROMPT,
    DEFAULT_VERDICT_CHOICES,
    SurveyRespondent,
    render_implication_text,
    sanitize_export_tag,
)
from infereval.types import Verdict

# ---- sanitize_export_tag ---------------------------------------------------


class TestSanitizeExportTag:
    def test_safe_id_passes_through_unchanged(self) -> None:
        tag, hashed = sanitize_export_tag("item_001")
        assert tag == "item_001"
        assert hashed is False

    def test_alnum_only_safe(self) -> None:
        tag, hashed = sanitize_export_tag("pulm123")
        assert tag == "pulm123"
        assert hashed is False

    def test_hyphen_is_NOT_safe(self) -> None:  # noqa: N802 -- explicit policy assertion
        """Hyphens are deliberately excluded so spreadsheet tools don't
        mangle column headers as minus signs in formulas."""
        tag, hashed = sanitize_export_tag("item-001")
        assert hashed is True
        assert tag.startswith("item_")

    def test_slashes_and_spaces_get_hashed(self) -> None:
        tag, hashed = sanitize_export_tag("item/foo bar")
        assert hashed is True
        # Format contract: item_<8 hex chars>.
        assert tag.startswith("item_")
        assert len(tag) == len("item_") + 8

    def test_hash_is_deterministic(self) -> None:
        a, _ = sanitize_export_tag("item/foo bar")
        b, _ = sanitize_export_tag("item/foo bar")
        assert a == b

    def test_distinct_ids_yield_distinct_hashes(self) -> None:
        a, _ = sanitize_export_tag("item/foo bar")
        b, _ = sanitize_export_tag("item/baz qux")
        assert a != b

    def test_boundary_80_char_safe_id(self) -> None:
        """Item ids up to 80 chars of [A-Za-z0-9_] are safe; one
        character longer triggers the hash."""
        eighty = "a" * 80
        tag, hashed = sanitize_export_tag(eighty)
        assert tag == eighty
        assert hashed is False

        eighty_one = "a" * 81
        tag, hashed = sanitize_export_tag(eighty_one)
        assert hashed is True
        assert tag != eighty_one

    def test_empty_id_gets_hashed(self) -> None:
        """An empty string fails the 1-80 char range and gets hashed."""
        tag, hashed = sanitize_export_tag("")
        assert hashed is True


# ---- render_implication_text ----------------------------------------------


def _make_benchmark(
    *,
    bearer_expressions: dict[str, str],
    item_premises: list[str],
    item_conclusions: list[str],
) -> Benchmark:
    """Tiny benchmark builder for render tests."""
    item = BenchmarkItem(
        id="row-0",
        premises=item_premises,
        conclusions=item_conclusions,
        analyst_verdicts=[Verdict.GOOD],
    )
    bearers = {bid: BearerModel(expression=expr) for bid, expr in bearer_expressions.items()}
    return Benchmark(
        id="render-test",
        bearers=bearers,
        analysts=[{"id": "test-analyst"}],
        items=[item],
    )


class TestRenderImplicationText:
    def test_basic_two_premise_one_conclusion(self) -> None:
        bench = _make_benchmark(
            bearer_expressions={
                "p1": "the patient has cough",
                "p2": "the patient has fever",
                "c1": "the patient has pneumonia",
            },
            item_premises=["p1", "p2"],
            item_conclusions=["c1"],
        )
        text = render_implication_text(bench, bench.items[0])
        assert "Premises:" in text
        assert "- the patient has cough" in text
        assert "- the patient has fever" in text
        assert "Conclusion:" in text
        assert "- the patient has pneumonia" in text

    def test_tex_math_is_stripped(self) -> None:
        bench = _make_benchmark(
            bearer_expressions={"p1": r"$pO_2$ is below 60", "c1": r"$ABG$ is abnormal"},
            item_premises=["p1"],
            item_conclusions=["c1"],
        )
        text = render_implication_text(bench, bench.items[0])
        assert "$" not in text
        assert "pO_2 is below 60" in text
        assert "ABG is abnormal" in text

    def test_premise_ordering_matches_benchmark_canonical_order(self) -> None:
        """``BenchmarkItem.premises`` is sorted at validation time
        (alphabetic on bearer id); the renderer reflects whatever order
        the model carries, not the original input order."""
        bench = _make_benchmark(
            bearer_expressions={"a": "A", "b": "B", "c": "C", "z": "Z"},
            item_premises=["b", "a", "c"],
            item_conclusions=["z"],
        )
        item = bench.items[0]
        # Confirm the assumption — premises sorted.
        assert item.premises == ["a", "b", "c"]
        text = render_implication_text(bench, item)
        prem_section = text.split("Premises:")[1].split("Conclusion:")[0]
        assert prem_section.index("- A") < prem_section.index("- B") < prem_section.index("- C")

    def test_multiple_conclusions_render_as_bullets(self) -> None:
        bench = _make_benchmark(
            bearer_expressions={"p1": "premise", "c1": "first conclusion", "c2": "second conclusion"},
            item_premises=["p1"],
            item_conclusions=["c1", "c2"],
        )
        text = render_implication_text(bench, bench.items[0])
        assert "- first conclusion" in text
        assert "- second conclusion" in text

    def test_render_against_pulmonary_edema_fixture(self) -> None:
        """Smoke-test against the bundled real benchmark."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        bench = Benchmark.load(repo_root / "examples" / "pulmonary_edema" / "benchmark.json")
        text = render_implication_text(bench, bench.items[0])
        # Plausible English on a real medical benchmark.
        assert "Premises:" in text
        assert "Conclusion:" in text
        # No raw TeX leaks through.
        assert "$" not in text


# ---- SurveyRespondent dataclass ------------------------------------------


class TestSurveyRespondent:
    def test_frozen(self) -> None:
        r = SurveyRespondent(
            response_id="R1",
            started_at=datetime(2026, 6, 3, 10, 30, 0),
            finished=True,
            expertise="pulmonologist, 12 years",
        )
        with pytest.raises((AttributeError, TypeError)):
            r.expertise = "something else"  # type: ignore[misc]

    def test_default_factories(self) -> None:
        r = SurveyRespondent(
            response_id="R1",
            started_at=None,
            finished=True,
            expertise=None,
        )
        # Default factories for verdicts and rationales yield empty dicts.
        assert r.verdicts == {}
        assert r.rationales == {}

    def test_equality_on_value(self) -> None:
        kwargs: dict = dict(
            response_id="R1",
            started_at=None,
            finished=True,
            expertise="pulmonologist",
            verdicts={"item_001": Verdict.GOOD},
            rationales={"item_001": None},
        )
        a = SurveyRespondent(**kwargs)
        b = SurveyRespondent(**kwargs)
        assert a == b


# ---- Default constants surface -------------------------------------------


def test_default_constants_have_expected_shapes() -> None:
    """Locked at v0.9.0; regression-guard against accidental rewording."""
    assert "premises" in DEFAULT_QUESTION_HEADER.lower()
    assert "conclusion" in DEFAULT_QUESTION_HEADER.lower()
    assert len(DEFAULT_VERDICT_CHOICES) == 3
    # First-word parsing contract — the importer maps "Good"/"Bad"/"Abstain"
    # back to the Verdict enum.
    first_words = [c.split()[0] for c in DEFAULT_VERDICT_CHOICES]
    assert first_words == ["Good", "Bad", "Abstain"]
    assert "expertise" in DEFAULT_EXPERTISE_PROMPT.lower()
    assert "rationale" in DEFAULT_RATIONALE_PROMPT.lower() or "explain" in DEFAULT_RATIONALE_PROMPT.lower()
