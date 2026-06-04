"""Tests for ``infereval.survey.surveymonkey_api``."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from infereval.benchmark import Benchmark
from infereval.survey.surveymonkey_api import (
    SurveyMonkeyApiError,
    SurveyMonkeyAuthError,
    build_surveymonkey_payload,
    publish_to_surveymonkey,
)

PULM_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "pulmonary_edema" / "benchmark.json"
)


def _pulm() -> Benchmark:
    return Benchmark.load(PULM_PATH)


# ---- build_surveymonkey_payload (pure, no network) ----------------------


class TestPayloadShape:
    def test_one_welcome_page_then_one_page_per_item(self) -> None:
        """v0.9.2: each item lives on its own page (Welcome + n items
        pages) so the page description can carry the full prompt and
        the question titles stay short."""
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench)
        assert len(payload["pages"]) == 1 + bench.n
        assert payload["pages"][0]["title"] == "Welcome"
        # Item pages titled by progress indicator.
        for i in range(1, bench.n + 1):
            assert payload["pages"][i]["title"] == f"Item {i} of {bench.n}"

    def test_item_pages_carry_prompt_in_description(self) -> None:
        """The full premises/conclusion prose lives in the page
        ``description`` so it renders separately from the question
        title (which becomes the CSV column header)."""
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench)
        for i in range(1, bench.n + 1):
            desc = payload["pages"][i]["description"]
            assert "Premises:" in desc
            assert "Conclusion:" in desc

    def test_expertise_is_open_ended_essay(self) -> None:
        payload, _ = build_surveymonkey_payload(_pulm())
        q = payload["pages"][0]["questions"][0]
        assert q["family"] == "open_ended"
        assert q["subtype"] == "essay"

    def test_one_question_per_item_without_rationales(self) -> None:
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench, include_rationales=False)
        # Each item page has exactly one MC.
        for i in range(1, bench.n + 1):
            qs = payload["pages"][i]["questions"]
            assert len(qs) == 1
            assert qs[0]["family"] == "single_choice"
            assert len(qs[0]["answers"]["choices"]) == 3

    def test_two_questions_per_item_with_rationales(self) -> None:
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench, include_rationales=True)
        for i in range(1, bench.n + 1):
            qs = payload["pages"][i]["questions"]
            assert len(qs) == 2

    def test_randomize_on_emits_page_randomization(self) -> None:
        """v0.9.2: with one-page-per-item, randomization is set at the
        survey level via ``page_randomization`` (skips page 1, the
        Welcome page)."""
        payload, _ = build_surveymonkey_payload(_pulm(), randomize_items=True)
        assert "page_randomization" in payload
        rand = payload["page_randomization"]
        assert rand["type"] == "all"
        # Pages 2..N+1 randomized; page 1 (Welcome) stays put.
        bench = _pulm()
        assert rand["pages_to_randomize"] == list(range(2, bench.n + 2))

    def test_randomize_off_omits_page_randomization(self) -> None:
        payload, _ = build_surveymonkey_payload(_pulm(), randomize_items=False)
        assert "page_randomization" not in payload

    def test_visible_titles_do_NOT_leak_item_tag_machine_markers(self) -> None:  # noqa: N802 -- assertion shape
        """v0.9.1+: ``[item:<tag>]`` markers must NOT appear in
        respondent-visible titles. (v0.9.2 extends: titles also don't
        carry the full prompt anymore.)"""
        bench = _pulm()
        payload, _mapping = build_surveymonkey_payload(bench)
        for page in payload["pages"]:
            for q in page["questions"]:
                heading = q["headings"][0]["heading"]
                assert "[item:" not in heading

    def test_visible_titles_use_short_item_n_anchors(self) -> None:
        """v0.9.2: titles are short. ``Item N verdict`` / ``Item N
        rationale (optional)`` — keeps CSV column headers scannable."""
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench, include_rationales=True)
        for i in range(1, bench.n + 1):
            verdict_heading = payload["pages"][i]["questions"][0]["headings"][0]["heading"]
            assert verdict_heading == f"Item {i} verdict"
            rationale_heading = payload["pages"][i]["questions"][1]["headings"][0]["heading"]
            assert rationale_heading == f"Item {i} rationale (optional)"

    def test_mapping_aligns_with_benchmark(self) -> None:
        bench = _pulm()
        _payload, mapping = build_surveymonkey_payload(bench)
        assert [row["item_id"] for row in mapping] == [it.id for it in bench.items]


# ---- publish_to_surveymonkey (mocked network) ---------------------------


class TestPublishAuthHandling:
    def test_missing_token_raises_authn_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SURVEYMONKEY_ACCESS_TOKEN", raising=False)
        with pytest.raises(SurveyMonkeyAuthError, match="SURVEYMONKEY_ACCESS_TOKEN"):
            publish_to_surveymonkey({})

    def test_explicit_token_param_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SURVEYMONKEY_ACCESS_TOKEN", raising=False)
        captured: dict[str, object] = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            return io.BytesIO(b'{"id": "12345", "href": "https://api.surveymonkey.com/v3/surveys/12345"}')

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = publish_to_surveymonkey({"title": "X"}, access_token="testtoken123")
        # Verify the token landed in the Authorization header (urllib
        # title-cases the key).
        auth_header = next(v for k, v in captured["headers"].items() if k.lower() == "authorization")
        assert auth_header == "bearer testtoken123"
        assert result["id"] == "12345"

    def test_env_token_picked_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SURVEYMONKEY_ACCESS_TOKEN", "env_token_xyz")

        def fake_urlopen(req, timeout=None):
            assert next(v for k, v in req.header_items() if k.lower() == "authorization") == "bearer env_token_xyz"
            return io.BytesIO(b'{"id": "env-survey"}')

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = publish_to_surveymonkey({"title": "X"})
        assert result["id"] == "env-survey"


class TestPublishApiErrors:
    def test_401_raises_auth_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SURVEYMONKEY_ACCESS_TOKEN", "bad")
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 401, "Unauthorized", {},
                io.BytesIO(b'{"error":{"message":"bad token"}}'),
            )

        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            pytest.raises(SurveyMonkeyAuthError, match="HTTP 401"),
        ):
            publish_to_surveymonkey({"title": "X"})

    def test_500_raises_api_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SURVEYMONKEY_ACCESS_TOKEN", "ok")
        import urllib.error

        def fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 500, "Internal Server Error", {},
                io.BytesIO(b'{"error":{"message":"server fault"}}'),
            )

        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            pytest.raises(SurveyMonkeyApiError, match="HTTP 500"),
        ):
            publish_to_surveymonkey({"title": "X"})


class TestPublishBaseUrl:
    def test_custom_base_url_eu_datacenter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SURVEYMONKEY_ACCESS_TOKEN", "ok")
        captured: dict[str, str] = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            return io.BytesIO(b'{"id": "1"}')

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            publish_to_surveymonkey(
                {"title": "X"},
                base_url="https://eu-api.surveymonkey.com/v3",
            )
        assert captured["url"] == "https://eu-api.surveymonkey.com/v3/surveys"

    def test_payload_serialized_as_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SURVEYMONKEY_ACCESS_TOKEN", "ok")
        captured: dict[str, object] = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return io.BytesIO(b'{"id": "1"}')

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            publish_to_surveymonkey({"title": "Pulm survey", "language": "en"})
        assert captured["body"] == {"title": "Pulm survey", "language": "en"}
