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
    def test_two_pages_expertise_then_items(self) -> None:
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench)
        assert len(payload["pages"]) == 2
        assert payload["pages"][0]["title"] == "Welcome"
        assert payload["pages"][1]["title"] == "Items"

    def test_expertise_is_open_ended_essay(self) -> None:
        payload, _ = build_surveymonkey_payload(_pulm())
        q = payload["pages"][0]["questions"][0]
        assert q["family"] == "open_ended"
        assert q["subtype"] == "essay"

    def test_one_question_per_item_without_rationales(self) -> None:
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench, include_rationales=False)
        item_qs = payload["pages"][1]["questions"]
        assert len(item_qs) == bench.n
        for q in item_qs:
            assert q["family"] == "single_choice"
            assert len(q["answers"]["choices"]) == 3

    def test_two_questions_per_item_with_rationales(self) -> None:
        bench = _pulm()
        payload, _ = build_surveymonkey_payload(bench, include_rationales=True)
        item_qs = payload["pages"][1]["questions"]
        assert len(item_qs) == 2 * bench.n

    def test_randomize_on_emits_presentation_options(self) -> None:
        payload, _ = build_surveymonkey_payload(_pulm(), randomize_items=True)
        items_page = payload["pages"][1]
        assert items_page["presentation_options"] == {"randomize_questions": "all"}

    def test_randomize_off_omits_presentation_options(self) -> None:
        payload, _ = build_surveymonkey_payload(_pulm(), randomize_items=False)
        items_page = payload["pages"][1]
        assert "presentation_options" not in items_page

    def test_each_mc_question_carries_item_tag_in_title(self) -> None:
        bench = _pulm()
        payload, mapping = build_surveymonkey_payload(bench)
        item_qs = payload["pages"][1]["questions"]
        for q in item_qs:
            heading = q["headings"][0]["heading"]
            # Either an [item:<tag>] or [item:<tag>_rationale] is present.
            assert "[item:" in heading

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
