"""Tests for ``infereval survey export`` CLI."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from infereval.cli.main import cli

PULM_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "pulmonary_edema" / "benchmark.json"
)


class TestQualtricsExport:
    def test_writes_qsf_file(self, tmp_path: Path) -> None:
        out = tmp_path / "recruit.qsf"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        assert out.is_file()
        loaded = json.loads(out.read_text())
        assert "SurveyEntry" in loaded
        assert "SurveyElements" in loaded

    def test_no_mapping_sidecar_when_ids_are_safe(self, tmp_path: Path) -> None:
        out = tmp_path / "recruit.qsf"
        runner = CliRunner()
        runner.invoke(cli, ["survey", "export", str(PULM_PATH), "-o", str(out)])
        sidecar = out.with_suffix(".qsf.mapping.json")
        # Pulmonology item ids ("c1"..) are all safe — no sidecar.
        assert not sidecar.exists()

    def test_no_randomize_omits_payload(self, tmp_path: Path) -> None:
        out = tmp_path / "no_random.qsf"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out), "--no-randomize-items"],
        )
        assert result.exit_code == 0, result.output
        loaded = json.loads(out.read_text())
        block = next(el for el in loaded["SurveyElements"] if el["Element"] == "BL")["Payload"][0]
        # No Options block means no randomization payload.
        assert "Options" not in block or "Randomization" not in block.get("Options", {})


class TestCoherenceFrameOption:
    def test_unknown_frame_id_exits_2_before_writing(self, tmp_path: Path) -> None:
        out = tmp_path / "recruit.qsf"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "export", str(PULM_PATH),
                "-o", str(out),
                "--question-form", "coherence",
                "--coherence-frame", "no-such-frame-v0",
            ],
        )
        assert result.exit_code == 2
        assert "unknown coherence_frame_id" in result.output
        # Catalog validation is pre-work: nothing was written.
        assert not out.exists()

    def test_anchored_frame_writes_sidecar_with_frame_id(self, tmp_path: Path) -> None:
        """A non-default frame forces the Qualtrics sidecar so the frame
        provenance survives on disk for the import-side merge guard."""
        out = tmp_path / "recruit.qsf"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "export", str(PULM_PATH),
                "-o", str(out),
                "--question-form", "coherence",
                "--coherence-frame", "defeasible-coherence-explicit-v1",
            ],
        )
        assert result.exit_code == 0, result.output
        sidecar = out.with_suffix(".qsf.mapping.json")
        assert sidecar.is_file()
        mapping = json.loads(sidecar.read_text())
        assert {row["frame_id"] for row in mapping} == {
            "defeasible-coherence-explicit-v1"
        }
        assert {row["question_form"] for row in mapping} == {"coherence"}
        # The anchored header made it into the artifact itself.
        assert "ordinary course of things" in out.read_text()

    def test_default_coherence_export_writes_no_sidecar(self, tmp_path: Path) -> None:
        """No frame flag + thin resolution: the pre-frame behavior — safe item
        ids, no sidecar — is preserved byte-for-byte."""
        out = tmp_path / "recruit.qsf"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "export", str(PULM_PATH),
                "-o", str(out),
                "--question-form", "coherence",
            ],
        )
        assert result.exit_code == 0, result.output
        assert not out.with_suffix(".qsf.mapping.json").exists()


class TestGoogleFormsExport:
    def test_writes_gas_file_and_warns_on_randomize(self, tmp_path: Path) -> None:
        out = tmp_path / "recruit.gs"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out), "--platform", "google_forms"],
        )
        assert result.exit_code == 0, result.output
        assert out.is_file()
        content = out.read_text()
        assert "function createForm()" in content
        assert "FormApp.create(" in content
        # Limitation warning rendered on stderr.
        assert "Google Forms cannot randomize a subset" in result.output

    def test_no_randomize_no_warning(self, tmp_path: Path) -> None:
        out = tmp_path / "no_random.gs"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "survey", "export", str(PULM_PATH),
                "-o", str(out),
                "--platform", "google_forms",
                "--no-randomize-items",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "cannot randomize" not in result.output


class TestSurveyMonkeyExport:
    def test_missing_token_fails_fast(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SURVEYMONKEY_ACCESS_TOKEN", raising=False)
        out = tmp_path / "sm.json"
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["survey", "export", str(PULM_PATH), "-o", str(out), "--platform", "surveymonkey"],
        )
        assert result.exit_code == 2
        assert "SURVEYMONKEY_ACCESS_TOKEN" in result.output

    def test_writes_api_response_on_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SURVEYMONKEY_ACCESS_TOKEN", "test_token")
        out = tmp_path / "sm.json"
        fake_response = b'{"id": "12345", "href": "https://api.surveymonkey.com/v3/surveys/12345"}'

        def fake_urlopen(req, timeout=None):
            return io.BytesIO(fake_response)

        runner = CliRunner()
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = runner.invoke(
                cli,
                ["survey", "export", str(PULM_PATH), "-o", str(out), "--platform", "surveymonkey"],
            )
        assert result.exit_code == 0, result.output
        # Response written to the file the user specified.
        loaded = json.loads(out.read_text())
        assert loaded["id"] == "12345"
        # Friendly URLs echoed to stdout.
        assert "12345" in result.output
