"""Tests for the coherence-frame API (v0.17.x-series).

Covers :class:`infereval.templates.CoherenceFrame` and the machinery that
binds it: the frame catalog + per-benchmark registry in
:mod:`infereval.templates`, the :attr:`Benchmark.coherence_frame_id` binding
field, resolution precedence through :func:`infereval.evaluation.evaluate`,
provenance stamping (recorded config + run-log events), legacy-eta backfill,
the retest cross-frame refusal, the polarity firewall (frames carry ONLY
system text), and byte-identity of the shipped frame constants against the
2026-07-02 / 2026-07-03 experiment captures they were promoted from.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from infereval import templates as templates_mod
from infereval.benchmark import Benchmark
from infereval.evaluation import (
    EndorsementConfig,
    Evaluation,
    EvaluationItem,
    MajorityVote,
    ModelInfo,
    ProviderParams,
    evaluate,
)
from infereval.providers.mock import ScriptedProvider
from infereval.retest import RetestConfigMismatchError, compute_retest
from infereval.templates import (
    DEFEASIBLE_COHERENCE_FRAME,
    THIN_COHERENCE_FRAME,
    UNDERDET_COHERENCE_FRAME,
    CoherenceFrame,
    DefaultTemplate,
    VerdictRequest,
    coherence_decode,
    coherence_frame_for_id,
    coherence_prompt,
    register_coherence_frame,
    register_coherence_frame_id,
)
from infereval.types import Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
ANCHORED_CAPTURE = (
    REPO_ROOT
    / "experiments"
    / "results"
    / "clinical_pilot"
    / "anchored_coherence_2026-07-02"
    / "AC1-anchoredcoherence-plain.jsonl"
)
UNDERDET_CAPTURE = (
    REPO_ROOT
    / "experiments"
    / "results"
    / "clinical_pilot"
    / "underdet_coherence_2026-07-03"
    / "UD1-underdetcoherence-plain.jsonl"
)

BUILTIN_FRAMES = (
    THIN_COHERENCE_FRAME,
    DEFEASIBLE_COHERENCE_FRAME,
    UNDERDET_COHERENCE_FRAME,
)

CUSTOM_FRAME = CoherenceFrame(
    id="custom-test-frame-v1", system="Custom system text for frame tests."
)


@pytest.fixture
def isolated_frame_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the frame registry + catalog so mutations never leak.

    Same pattern as the ``_REGISTRY`` monkeypatching in
    ``test_templates_clinical.py``: swap in a fresh registry and a *copy* of
    the catalog; monkeypatch restores the originals on teardown.
    """
    monkeypatch.setattr(templates_mod, "_FRAME_REGISTRY", {})
    monkeypatch.setattr(
        templates_mod, "_FRAME_CATALOG", dict(templates_mod._FRAME_CATALOG)
    )


def _bench(**overrides: object) -> Benchmark:
    data: dict[str, object] = {
        "id": "frame-bench",
        "bearers": {b: {"expression": f"expr {b}"} for b in ("p", "c")},
        "analysts": [{"id": "a1"}],
        "items": [
            {
                "id": "it",
                "premises": ["p"],
                "conclusions": ["c"],
                "analyst_verdicts": ["good"],
            }
        ],
    }
    data.update(overrides)
    return Benchmark.model_validate(data)


def _read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---- 1. Catalog ------------------------------------------------------------


class TestCatalog:
    def test_builtin_ids_resolve(self) -> None:
        assert coherence_frame_for_id("thin-v1") is THIN_COHERENCE_FRAME
        assert (
            coherence_frame_for_id("defeasible-coherence-explicit-v1")
            is DEFEASIBLE_COHERENCE_FRAME
        )
        assert (
            coherence_frame_for_id("defeasible-coherence-underdet-v1")
            is UNDERDET_COHERENCE_FRAME
        )

    def test_unknown_id_raises_naming_catalogued_ids(self) -> None:
        with pytest.raises(ValueError, match="unknown coherence_frame_id") as exc_info:
            coherence_frame_for_id("no-such-frame-v0")
        message = str(exc_info.value)
        for frame in BUILTIN_FRAMES:
            assert frame.id in message

    def test_register_coherence_frame_id_makes_custom_resolvable(
        self, isolated_frame_state: None
    ) -> None:
        with pytest.raises(ValueError, match="unknown coherence_frame_id"):
            coherence_frame_for_id(CUSTOM_FRAME.id)
        register_coherence_frame_id(CUSTOM_FRAME)
        assert coherence_frame_for_id(CUSTOM_FRAME.id) is CUSTOM_FRAME


# ---- 2. Byte-identity of the default path ----------------------------------


class TestDefaultPathByteIdentity:
    def test_no_frame_composes_the_pre_frame_prompt(self) -> None:
        # Frame-less coherence_prompt must be byte-identical to the library
        # before frames existed: the thin system text and the same user text
        # (template scaffold + the fixed question line).
        template = DefaultTemplate()
        req = VerdictRequest(
            arity=1, gamma_ctx="expr p", delta_ctx=("expr c",)
        )
        rendered = coherence_prompt(req, template)
        assert rendered.system == templates_mod._COHERENCE_SYSTEM
        assert rendered.system == THIN_COHERENCE_FRAME.system
        expected_user = (
            f"{template.render(req)}\n"
            "Is this position coherent? Answer COHERENT, INCOHERENT, or UNCLEAR."
        )
        assert rendered.user == expected_user

    def test_answer_contract_is_unchanged(self) -> None:
        req = VerdictRequest(arity=0, gamma_ctx="expr p", delta_ctx=())
        rendered = coherence_prompt(req, DefaultTemplate())
        assert rendered.labels == ("INCOHERENT", "COHERENT", "UNCLEAR")
        assert rendered.parse_regex == r"\b(INCOHERENT|COHERENT|UNCLEAR)\b"


# ---- 3. Resolution precedence through evaluate() ----------------------------


class TestResolutionPrecedence:
    def _evaluate(
        self,
        bench: Benchmark,
        *,
        config: EndorsementConfig | None = None,
        coherence_frame: CoherenceFrame | None = None,
        log_path: Path | None = None,
        run_id: str = "frame-precedence-test",
    ) -> Evaluation:
        return evaluate(
            bench,
            ScriptedProvider(responses=["INCOHERENT"]),
            config=config
            or EndorsementConfig(n_samples=1, question_form="coherence"),
            coherence_frame=coherence_frame,
            run_id=run_id,
            log_path=log_path,
        )

    def test_default_resolves_to_thin(self, isolated_frame_state: None) -> None:
        eta = self._evaluate(_bench())
        assert eta.endorsement_config.coherence_frame_id == "thin-v1"

    def test_benchmark_binding_is_honored(
        self, isolated_frame_state: None, tmp_path: Path
    ) -> None:
        bench = _bench(coherence_frame_id="defeasible-coherence-explicit-v1")
        log_path = tmp_path / "run.jsonl"
        eta = self._evaluate(bench, log_path=log_path)
        assert (
            eta.endorsement_config.coherence_frame_id
            == "defeasible-coherence-explicit-v1"
        )
        # §12.3 provenance in the run log: the resolved frame id lands in
        # run.started, and item.started carries the composed prompt id.
        by_kind = {e["event"]: e for e in _read_events(log_path)}
        assert (
            by_kind["run.started"]["coherence_frame_id"]
            == "defeasible-coherence-explicit-v1"
        )
        assert by_kind["item.started"]["verification_prompt_id"] == (
            "framework-default-v1:coherence:defeasible-coherence-explicit-v1"
        )
        assert by_kind["item.started"]["system"] == DEFEASIBLE_COHERENCE_FRAME.system

    def test_programmatic_registration_overrides_benchmark_binding(
        self, isolated_frame_state: None
    ) -> None:
        bench = _bench(coherence_frame_id="defeasible-coherence-explicit-v1")
        register_coherence_frame(bench.id, UNDERDET_COHERENCE_FRAME)
        eta = self._evaluate(bench)
        assert (
            eta.endorsement_config.coherence_frame_id
            == "defeasible-coherence-underdet-v1"
        )

    def test_non_default_config_value_overrides_registry(
        self, isolated_frame_state: None
    ) -> None:
        bench = _bench()
        register_coherence_frame(bench.id, DEFEASIBLE_COHERENCE_FRAME)
        eta = self._evaluate(
            bench,
            config=EndorsementConfig(
                n_samples=1, coherence_frame_id="defeasible-coherence-underdet-v1"
            ),
        )
        assert (
            eta.endorsement_config.coherence_frame_id
            == "defeasible-coherence-underdet-v1"
        )

    def test_explicit_argument_overrides_everything(
        self, isolated_frame_state: None
    ) -> None:
        # Registry binding + benchmark binding + non-default config all point
        # elsewhere; the explicit coherence_frame argument still wins (this is
        # also the documented way to force the thin frame over a binding).
        bench = _bench(coherence_frame_id="defeasible-coherence-explicit-v1")
        register_coherence_frame(bench.id, DEFEASIBLE_COHERENCE_FRAME)
        eta = self._evaluate(
            bench,
            config=EndorsementConfig(
                n_samples=1, coherence_frame_id="defeasible-coherence-underdet-v1"
            ),
            coherence_frame=THIN_COHERENCE_FRAME,
        )
        assert eta.endorsement_config.coherence_frame_id == "thin-v1"

    def test_unknown_benchmark_binding_fails_before_any_provider_call(
        self, isolated_frame_state: None
    ) -> None:
        bench = _bench(coherence_frame_id="no-such-frame-v0")
        provider = ScriptedProvider(responses=["INCOHERENT"])
        with pytest.raises(ValueError, match="unknown coherence_frame_id"):
            evaluate(
                bench,
                provider,
                config=EndorsementConfig(n_samples=1),
                run_id="frame-unknown-binding-test",
            )
        # ScriptedProvider counts sample() calls in _index: zero calls made.
        assert provider._index == 0


# ---- 4. Provenance ----------------------------------------------------------


class TestProvenance:
    def test_dumped_eta_records_the_resolved_id(
        self, isolated_frame_state: None
    ) -> None:
        bench = _bench(coherence_frame_id="defeasible-coherence-explicit-v1")
        eta = evaluate(
            bench,
            ScriptedProvider(responses=["INCOHERENT"]),
            config=EndorsementConfig(n_samples=1),
            run_id="frame-provenance-test",
        )
        data = json.loads(eta.dumps())
        assert (
            data["endorsement_config"]["coherence_frame_id"]
            == "defeasible-coherence-explicit-v1"
        )

    def test_support_form_still_stamps_thin(self, isolated_frame_state: None) -> None:
        # The support path ignores frames, but the stamped config field stays
        # concrete and uniform: "thin-v1" (harmless — never elicited under it).
        eta = evaluate(
            _bench(),
            ScriptedProvider(responses=["GOOD"]),
            config=EndorsementConfig(n_samples=1, question_form="support"),
            run_id="frame-support-stamp-test",
        )
        assert eta.endorsement_config.coherence_frame_id == "thin-v1"
        assert '"coherence_frame_id": "thin-v1"' in eta.dumps()


# ---- 5. Legacy backfill ------------------------------------------------------


class TestLegacyBackfill:
    def test_legacy_eta_backfills_thin(self, isolated_frame_state: None) -> None:
        # A pre-frame η has no coherence_frame_id; every evaluate()-produced
        # coherence η before frames existed used the thin system, so load-time
        # backfill must say "thin-v1".
        eta = evaluate(
            _bench(),
            ScriptedProvider(responses=["INCOHERENT"]),
            config=EndorsementConfig(n_samples=1),
            run_id="frame-legacy-backfill-test",
        )
        data = json.loads(eta.dumps())
        del data["endorsement_config"]["coherence_frame_id"]  # simulate legacy η
        legacy = Evaluation.model_validate(data)
        assert legacy.endorsement_config.coherence_frame_id == "thin-v1"

    def test_backfilled_eta_round_trips(self, isolated_frame_state: None) -> None:
        eta = evaluate(
            _bench(),
            ScriptedProvider(responses=["INCOHERENT"]),
            config=EndorsementConfig(n_samples=1),
            run_id="frame-roundtrip-test",
        )
        data = json.loads(eta.dumps())
        del data["endorsement_config"]["coherence_frame_id"]
        legacy = Evaluation.model_validate(data)
        reloaded = Evaluation.loads(legacy.dumps())
        assert reloaded == legacy
        assert reloaded.endorsement_config.coherence_frame_id == "thin-v1"


# ---- 6. Retest refusal -------------------------------------------------------


def _retest_item(item_id: str) -> EvaluationItem:
    return EvaluationItem(
        id=item_id,
        premises=["x"],
        conclusions=["y"],
        analyst_verdicts=[Verdict.GOOD],
        model_verdict=Verdict.GOOD,
        majority_vote=MajorityVote(good=1, bad=0, abstain=0, verdict=Verdict.GOOD),
    )


def _retest_eval(run_id: str, frame_id: str) -> Evaluation:
    return Evaluation(
        id=run_id,
        benchmark_id="bench",
        benchmark_hash="abc123",
        model=ModelInfo(provider="mock", model_id="t1", params=ProviderParams()),
        endorsement_config=EndorsementConfig(coherence_frame_id=frame_id),
        items=[_retest_item("a"), _retest_item("b")],
    )


class TestRetestRefusal:
    def test_cross_frame_runs_are_refused(self) -> None:
        # A frame change is an instrument change: retest variability must not
        # be conflated with frame-change effects.
        eta_a = _retest_eval("run-a", "thin-v1")
        eta_b = _retest_eval("run-b", "defeasible-coherence-explicit-v1")
        with pytest.raises(RetestConfigMismatchError, match="endorsement_config"):
            compute_retest(eta_a, eta_b)

    def test_identical_frames_pass(self) -> None:
        eta_a = _retest_eval("run-a", "defeasible-coherence-explicit-v1")
        eta_b = _retest_eval("run-b", "defeasible-coherence-explicit-v1")
        result = compute_retest(eta_a, eta_b)
        assert result.n_items == 2
        assert result.n_disagreements == 0


# ---- 7. Polarity firewall ----------------------------------------------------


class TestPolarityFirewall:
    def test_frame_has_no_decode_or_labels_surface(self) -> None:
        # Structural check: a frame carries ONLY norm-statement surfaces —
        # the model system text, its human-facing survey header, and the
        # header's own closing question line (survey_stem). The answer
        # contract (question line, labels, parse regex, decode inversion,
        # survey choice labels) is library-owned, so no frame can silently
        # invert verdicts on either elicitation surface.
        assert {f.name for f in dataclasses.fields(CoherenceFrame)} == {
            "id",
            "system",
            "survey_header",
            "survey_stem",
        }

    @pytest.mark.parametrize("frame", BUILTIN_FRAMES, ids=lambda f: f.id)
    def test_survey_stem_is_verbatim_tail_of_header(
        self, frame: CoherenceFrame
    ) -> None:
        # The stem is the header's own closing question line, verbatim: the
        # instructions header mode (header once + stem per item) introduces
        # no wording that is not already part of the frame's reviewed
        # surface.
        assert frame.survey_header is not None
        assert frame.survey_stem is not None
        assert frame.survey_header.endswith(frame.survey_stem)
        assert frame.survey_stem.strip().endswith("?")

    @pytest.mark.parametrize("frame", BUILTIN_FRAMES, ids=lambda f: f.id)
    def test_decode_is_identical_under_every_frame(
        self, frame: CoherenceFrame
    ) -> None:
        req = VerdictRequest(arity=1, gamma_ctx="expr p", delta_ctx=("expr c",))
        rendered = coherence_prompt(req, DefaultTemplate(), frame)
        # The answer contract never varies by frame …
        assert rendered.labels == ("INCOHERENT", "COHERENT", "UNCLEAR")
        assert rendered.parse_regex == r"\b(INCOHERENT|COHERENT|UNCLEAR)\b"
        # … and neither does the decode: INCOHERENT → good, COHERENT → bad,
        # UNCLEAR → abstain, regardless of which frame produced the prompt.
        pattern = re.compile(rendered.parse_regex, re.IGNORECASE)
        assert coherence_decode("INCOHERENT", pattern, req) == (Verdict.GOOD, "ok")
        assert coherence_decode("COHERENT", pattern, req) == (Verdict.BAD, "ok")
        assert coherence_decode("UNCLEAR", pattern, req) == (Verdict.ABSTAIN, "ok")


# ---- 8. Captured-record byte-identity ----------------------------------------


class TestCapturedRecordByteIdentity:
    """The shipped frame constants are byte-identical to the experiment
    captures they were promoted from (same discipline as the clinical
    template's frozen-wording tests)."""

    @pytest.mark.skipif(
        not ANCHORED_CAPTURE.exists(),
        reason="anchored-coherence 2026-07-02 capture not present",
    )
    def test_anchored_capture_system_matches_shipped_frame(self) -> None:
        with ANCHORED_CAPTURE.open("r", encoding="utf-8") as f:
            first = json.loads(f.readline())
        assert first["event"] == "cell.started"
        assert first["system_id"] == DEFEASIBLE_COHERENCE_FRAME.id
        assert first["system"] == DEFEASIBLE_COHERENCE_FRAME.system

    @pytest.mark.skipif(
        not UNDERDET_CAPTURE.exists(),
        reason="underdetermination-clause 2026-07-03 capture not present",
    )
    def test_underdet_capture_system_matches_shipped_frame(self) -> None:
        with UNDERDET_CAPTURE.open("r", encoding="utf-8") as f:
            first = json.loads(f.readline())
        assert first["event"] == "cell.started"
        assert first["system_id"] == UNDERDET_COHERENCE_FRAME.id
        assert first["system"] == UNDERDET_COHERENCE_FRAME.system
