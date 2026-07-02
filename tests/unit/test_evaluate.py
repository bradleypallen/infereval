"""Tests for ``infereval.evaluation.evaluate`` (end-to-end orchestration)."""

from __future__ import annotations

from pathlib import Path

from infereval.benchmark import Benchmark, Reference
from infereval.evaluation import (
    EndorsementConfig,
    Evaluation,
    ProviderParams,
    canonical_benchmark_hash,
    evaluate,
)
from infereval.frame import DerivedFrame
from infereval.providers.mock import ScriptedProvider
from infereval.types import Implication, Verdict

REPO_ROOT = Path(__file__).resolve().parents[2]
STOP_SIGN_PATH = REPO_ROOT / "examples" / "stop_sign" / "benchmark.json"


def _stop_sign() -> Benchmark:
    return Benchmark.load(STOP_SIGN_PATH)


# ---- End-to-end happy path -------------------------------------------------


class TestEvaluateStopSign:
    """Matches the analyst row of Example 1: rows 0-2 good, row 3 bad."""

    def test_matches_paper_analyst_row(self) -> None:
        bench = _stop_sign()
        # Schedule the model to match the paper's analyst row for each item.
        # n_samples=3 means three responses per item; reuse the same response.
        # Items: row-0, row-1, row-2 -> good; row-3 -> bad.
        provider = ScriptedProvider(
            responses=(["GOOD"] * 3) * 3 + ["BAD"] * 3
        )
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=3, question_form="support"),
            params=ProviderParams(temperature=0.0, max_tokens=8),
            run_id="test-run-1",
        )
        assert eta.id == "test-run-1"
        assert eta.benchmark_id == "stop-sign-example-1"
        assert eta.n == 4
        verdicts = {it.id: it.model_verdict for it in eta.items}
        assert verdicts == {
            "row-0": Verdict.GOOD,
            "row-1": Verdict.GOOD,
            "row-2": Verdict.GOOD,
            "row-3": Verdict.BAD,
        }

    def test_model_info_records_provider_and_params(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 100, model_id="my-test-v1")
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=2),
            params=ProviderParams(temperature=0.3, max_tokens=12, seed=123),
        )
        assert eta.model.provider == "mock"
        assert eta.model.model_id == "my-test-v1"
        assert eta.model.params.temperature == 0.3
        assert eta.model.params.max_tokens == 12
        assert eta.model.params.seed == 123

    def test_records_timing_and_framework_version(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=2))
        assert eta.started_at is not None
        assert eta.finished_at is not None
        assert eta.finished_at >= eta.started_at
        assert eta.framework_version  # populated from package __version__

    def test_endorsement_config_id_propagated(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=2))
        # Default prompt id is "default-v1"
        assert eta.endorsement_config.verification_prompt_id == "default-v1"
        assert eta.endorsement_config.n_samples == 2


# ---- Per-item samples & majority-vote breakdown ----------------------------


class TestPerItemBreakdown:
    def test_samples_recorded_per_item(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 100)
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=5, question_form="support"),
        )
        for item in eta.items:
            assert len(item.samples) == 5
            for s in item.samples:
                assert s.parse_status == "ok"
                assert s.raw_response == "GOOD"

    def test_majority_vote_attached(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 100)
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=5, question_form="support"),
        )
        for item in eta.items:
            assert item.majority_vote is not None
            assert item.majority_vote.verdict == Verdict.GOOD
            assert item.majority_vote.good == 5

    def test_tie_recorded(self) -> None:
        bench = _stop_sign()
        # Schedule alternating GOOD/BAD to force ties.
        provider = ScriptedProvider(responses=["GOOD", "BAD"] * 100)
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=4, question_form="support"),
        )
        # With n=4 and alternating GOOD/BAD, every item gets 2-2 -> abstain (default)
        for item in eta.items:
            assert item.model_verdict == Verdict.ABSTAIN
            assert item.majority_vote is not None
            assert item.majority_vote.tie_broken


# ---- Benchmark hash --------------------------------------------------------


class TestBenchmarkHash:
    def test_canonical_hash_is_stable(self) -> None:
        h1 = canonical_benchmark_hash(_stop_sign())
        h2 = canonical_benchmark_hash(_stop_sign())
        assert h1 == h2
        assert h1.startswith("sha256:")

    def test_hash_recorded_in_evaluation(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        assert eta.benchmark_hash == canonical_benchmark_hash(bench)

    def test_hash_changes_when_benchmark_changes(self) -> None:
        bench = _stop_sign()
        h1 = canonical_benchmark_hash(bench)
        # Mutate a copy
        data = bench.model_dump(mode="json")
        data["items"][0]["analyst_verdicts"] = ["bad"]  # was "good"
        modified = Benchmark.model_validate(data)
        h2 = canonical_benchmark_hash(modified)
        assert h1 != h2


# ---- JSON round-trip of evaluate result -----------------------------------


class TestEvaluateOutputRoundTrips:
    def test_evaluation_serializes_and_validates(self, tmp_path: Path) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"] * 50)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=2))
        path = tmp_path / "eval.json"
        eta.dump(path)
        # Reload via JSON Schema -> Pydantic
        loaded = Evaluation.load(path)
        assert loaded == eta

    def test_round_trip_preserves_samples(self, tmp_path: Path) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD with a note", "GOOD!", "GOOD."] * 20)
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=3))
        text = eta.dumps()
        eta2 = Evaluation.loads(text)
        for i, item in enumerate(eta.items):
            for j, s in enumerate(item.samples):
                assert eta2.items[i].samples[j].raw_response == s.raw_response


# ---- Frame round-trip via Evaluation.endorsements() -----------------------


class TestFrameFromEvaluation:
    def test_derived_frame_matches_paper(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(
            responses=(["GOOD"] * 3) * 3 + ["BAD"] * 3
        )
        eta = evaluate(
            bench,
            provider,
            config=EndorsementConfig(n_samples=3, question_form="support"),
        )
        bearers = bench.runtime_bearers()
        frame = DerivedFrame.from_endorsements(bearers, eta.endorsements())

        # Rows 0-2 in (via clause ii); row 3 out
        assert frame.contains(Implication.of(["sa"], ["ra"]))
        assert frame.contains(Implication.of(["sa", "n"], ["ra"]))
        assert frame.contains(Implication.of(["sa", "n", "nr"], ["ra"]))
        assert not frame.contains(Implication.of(["sa", "ba"], ["ra"]))


# ---- References propagation (Issue #22) -----------------------------------


class TestReferencesPropagation:
    """Benchmark-side ``references`` survive ``evaluate()`` into the Evaluation."""

    def _bench_with_refs(self):
        bench = _stop_sign()
        # Construct Reference instances directly so we don't trip the
        # serializer warnings that fire when model_copy bypasses validators.
        bench = bench.model_copy(update={
            "references": [
                Reference(citation="Simonelli (2026). The Stop Sign Dialogue."),
                Reference(citation="Allen (2026). Note on Simonelli.", doi="10.0/test"),
            ]
        })
        first_item_with_refs = bench.items[0].model_copy(update={
            "references": [
                Reference(citation="Hlobil & Brandom (2025)", section="Definition 3"),
                Reference(citation="Plain string ref"),
            ]
        })
        new_items = [first_item_with_refs] + list(bench.items[1:])
        return bench.model_copy(update={"items": new_items})

    def test_corpus_references_propagated_to_evaluation(self) -> None:
        bench = self._bench_with_refs()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        assert len(eta.references) == 2
        assert eta.references[0].citation == "Simonelli (2026). The Stop Sign Dialogue."
        assert eta.references[1].doi == "10.0/test"

    def test_item_references_propagated_to_evaluation_items(self) -> None:
        bench = self._bench_with_refs()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        # The stop-sign benchmark file orders items differently from how
        # they appear in source; find the one whose id matches whatever
        # _bench_with_refs() decorated. We added refs to bench.items[0]
        # before calling evaluate(); _bench_id of that item:
        annotated_id = self._bench_with_refs().items[0].id
        annotated = next(it for it in eta.items if it.id == annotated_id)
        assert len(annotated.references) == 2
        assert annotated.references[0].section == "Definition 3"
        assert annotated.references[1].citation == "Plain string ref"
        for it in eta.items:
            if it.id != annotated_id:
                assert it.references == []
        for it in eta.items[1:]:
            assert it.references == []

    def test_references_survive_dump_load_round_trip(self, tmp_path: Path) -> None:
        bench = self._bench_with_refs()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        path = tmp_path / "eta.json"
        eta.dump(path)
        reloaded = Evaluation.load(path)
        assert len(reloaded.references) == 2
        annotated_id = self._bench_with_refs().items[0].id
        annotated = next(it for it in reloaded.items if it.id == annotated_id)
        assert annotated.references[0].section == "Definition 3"
        assert annotated.references[1].citation == "Plain string ref"

    def test_empty_benchmark_references_yield_empty_evaluation_references(self) -> None:
        # Backwards-compat regression: an unannotated benchmark produces
        # an evaluation with all-empty references at both levels.
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        assert eta.references == []
        assert all(it.references == [] for it in eta.items)

    def test_evaluation_string_shorthand_promoted(self) -> None:
        # Round-trip stability when an evaluation JSON is hand-edited with
        # string-shorthand references (parallel to BenchmarkItem behavior).
        eta_json = {
            "id": "test-run",
            "benchmark_id": "test",
            "model": {"provider": "mock", "model_id": "scripted-mock-v1"},
            "items": [],
            "references": ["A string", {"citation": "Structured"}],
        }
        eta = Evaluation.model_validate(eta_json)
        assert len(eta.references) == 2
        assert eta.references[0].citation == "A string"
        assert eta.references[0].doi is None
        assert eta.references[1].citation == "Structured"


# ---- Paraphrase variants (Issue #32, Phase 1.2) ---------------------------


class TestParaphraseVariantInEvaluation:
    """``Evaluation.paraphrase_variant`` records which variant was used."""

    def test_default_variant_is_zero(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1))
        assert eta.paraphrase_variant == 0

    def test_variant_recorded_when_supplied(self) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1), variant=3)
        assert eta.paraphrase_variant == 3

    def test_variant_survives_dump_load(self, tmp_path: Path) -> None:
        bench = _stop_sign()
        provider = ScriptedProvider(responses=["GOOD"])
        eta = evaluate(bench, provider, config=EndorsementConfig(n_samples=1), variant=2)
        path = tmp_path / "eta.json"
        eta.dump(path)
        reloaded = Evaluation.load(path)
        assert reloaded.paraphrase_variant == 2

    def test_evaluation_loads_pre_032_evaluation_with_default_variant(self) -> None:
        # An evaluation JSON predating Issue #32 has no paraphrase_variant
        # field; the model should default it to 0.
        eta_json = {
            "id": "pre-0.3.1",
            "benchmark_id": "test",
            "model": {"provider": "mock", "model_id": "scripted-mock-v1"},
            "items": [],
        }
        eta = Evaluation.model_validate(eta_json)
        assert eta.paraphrase_variant == 0
