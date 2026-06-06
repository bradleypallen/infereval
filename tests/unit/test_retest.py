"""Tests for the test-retest reliability comparator added in v0.6.0.

Covers:
- :func:`infereval.retest.compute_retest` happy path: identical runs ->
  κ = 1.0, no flips.
- Single-flip detection.
- Stability-verdict ladder rungs.
- :class:`RetestConfigMismatchError` triggers: benchmark_id /
  benchmark_hash / endorsement_config / paraphrase_variant mismatch.
- Per-item :class:`ItemDelta` shape (entropy / margin deltas).
- :func:`retest_result_to_dict` round-trip.
"""

from __future__ import annotations

import pytest

from infereval.evaluation import (
    EndorsementConfig,
    Evaluation,
    EvaluationItem,
    MajorityVote,
    ModelInfo,
    ProviderParams,
)
from infereval.retest import (
    RetestConfigMismatchError,
    compute_retest,
    retest_result_to_dict,
)
from infereval.types import Verdict


def _item(
    item_id: str,
    *,
    analyst_verdicts: list[Verdict],
    model_verdict: Verdict,
    good: int,
    bad: int,
    abstain: int,
) -> EvaluationItem:
    return EvaluationItem(
        id=item_id,
        premises=["x"],
        conclusions=["y"],
        analyst_verdicts=analyst_verdicts,
        model_verdict=model_verdict,
        majority_vote=MajorityVote(
            good=good, bad=bad, abstain=abstain, verdict=model_verdict
        ),
    )


def _eval(
    items: list[EvaluationItem],
    *,
    run_id: str = "r1",
    benchmark_hash: str | None = "abc123",
    config: EndorsementConfig | None = None,
    paraphrase_variant: int = 0,
) -> Evaluation:
    return Evaluation(
        id=run_id,
        benchmark_id="bench",
        benchmark_hash=benchmark_hash,
        model=ModelInfo(provider="mock", model_id="t1", params=ProviderParams()),
        endorsement_config=config or EndorsementConfig(),
        paraphrase_variant=paraphrase_variant,
        items=items,
    )


# ---- Happy path ----------------------------------------------------------


def test_identical_runs_give_kappa_1_no_flips() -> None:
    items = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
        _item("b", analyst_verdicts=[Verdict.BAD], model_verdict=Verdict.BAD,
              good=0, bad=5, abstain=0),
        _item("c", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=4, bad=1, abstain=0),
    ]
    eta_a = _eval(items, run_id="A")
    eta_b = _eval(items, run_id="B")
    result = compute_retest(eta_a, eta_b)
    assert result.n_items == 3
    assert result.n_agreements == 3
    assert result.n_disagreements == 0
    assert result.test_retest_kappa == pytest.approx(1.0)
    assert result.flipped_items == ()
    assert "stable" in result.stability_verdict
    assert result.run_a_id == "A"
    assert result.run_b_id == "B"


def test_single_flip_recorded_and_kappa_below_1() -> None:
    items_a = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
        _item("b", analyst_verdicts=[Verdict.BAD], model_verdict=Verdict.BAD,
              good=0, bad=5, abstain=0),
        _item("c", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=3, bad=2, abstain=0),
    ]
    items_b = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
        _item("b", analyst_verdicts=[Verdict.BAD], model_verdict=Verdict.BAD,
              good=0, bad=5, abstain=0),
        _item("c", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.BAD,
              good=1, bad=4, abstain=0),  # flipped from GOOD
    ]
    eta_a = _eval(items_a, run_id="A")
    eta_b = _eval(items_b, run_id="B")
    result = compute_retest(eta_a, eta_b)
    assert result.n_agreements == 2
    assert result.n_disagreements == 1
    assert len(result.flipped_items) == 1
    assert result.flipped_items[0].item_id == "c"
    assert result.flipped_items[0].verdict_a == "good"
    assert result.flipped_items[0].verdict_b == "bad"
    assert result.test_retest_kappa is not None
    assert result.test_retest_kappa < 1.0


def test_stability_verdict_ladder() -> None:
    """Exercise all three rungs by constructing controlled retests."""
    # Stable: kappa >= 0.8. We'll get kappa = 1.0 from a perfectly-matching pair.
    perfect = [
        _item(f"i{i}", analyst_verdicts=[Verdict.GOOD if i % 2 == 0 else Verdict.BAD],
              model_verdict=Verdict.GOOD if i % 2 == 0 else Verdict.BAD,
              good=5 if i % 2 == 0 else 0, bad=0 if i % 2 == 0 else 5, abstain=0)
        for i in range(10)
    ]
    result_stable = compute_retest(_eval(perfect, run_id="A"), _eval(perfect, run_id="B"))
    assert "stable" in result_stable.stability_verdict
    assert "moderately" not in result_stable.stability_verdict
    assert "unstable" not in result_stable.stability_verdict

    # Substantively unstable: flip enough to drag kappa below 0.6.
    # Start with 10 items, flip 4 of them between runs.
    items_a = [
        _item(f"i{i}", analyst_verdicts=[Verdict.GOOD if i % 2 == 0 else Verdict.BAD],
              model_verdict=Verdict.GOOD if i % 2 == 0 else Verdict.BAD,
              good=5 if i % 2 == 0 else 0, bad=0 if i % 2 == 0 else 5, abstain=0)
        for i in range(10)
    ]
    items_b = []
    for i in range(10):
        analyst = Verdict.GOOD if i % 2 == 0 else Verdict.BAD
        # First 4 items: flip; rest: keep
        model_v = (
            (Verdict.BAD if analyst == Verdict.GOOD else Verdict.GOOD)
            if i < 4
            else analyst
        )
        items_b.append(
            _item(
                f"i{i}",
                analyst_verdicts=[analyst],
                model_verdict=model_v,
                good=5 if model_v == Verdict.GOOD else 0,
                bad=5 if model_v == Verdict.BAD else 0,
                abstain=0,
            )
        )
    result_unstable = compute_retest(
        _eval(items_a, run_id="A"), _eval(items_b, run_id="B")
    )
    # Flip rate is 4/10 = 40%
    assert result_unstable.flip_rate == pytest.approx(0.4)
    # Kappa here is computed over the 10 (verdict_a, verdict_b) pairs:
    # 6 stay-good/stay-bad agreements, 4 flips. Cohen's κ on the verdict
    # columns -> roughly 0.2; landing in "substantively unstable".
    assert result_unstable.test_retest_kappa is not None
    assert result_unstable.test_retest_kappa < 0.6
    assert "unstable" in result_unstable.stability_verdict


# ---- Compatibility check errors -----------------------------------------


def test_benchmark_id_mismatch_raises() -> None:
    eta_a = _eval([_item("a", analyst_verdicts=[Verdict.GOOD],
                         model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)],
                  run_id="A")
    items_b = [_item("a", analyst_verdicts=[Verdict.GOOD],
                     model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)]
    eta_b = Evaluation(
        id="B",
        benchmark_id="OTHER-BENCH",
        benchmark_hash="abc123",
        model=ModelInfo(provider="mock", model_id="t1", params=ProviderParams()),
        items=items_b,
    )
    with pytest.raises(RetestConfigMismatchError, match="benchmark_id"):
        compute_retest(eta_a, eta_b)


def test_benchmark_hash_mismatch_raises() -> None:
    items = [_item("a", analyst_verdicts=[Verdict.GOOD],
                   model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)]
    eta_a = _eval(items, run_id="A", benchmark_hash="aaaaaa")
    eta_b = _eval(items, run_id="B", benchmark_hash="bbbbbb")
    with pytest.raises(RetestConfigMismatchError, match="benchmark_hash"):
        compute_retest(eta_a, eta_b)


def test_endorsement_config_mismatch_raises() -> None:
    items = [_item("a", analyst_verdicts=[Verdict.GOOD],
                   model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)]
    eta_a = _eval(items, run_id="A", config=EndorsementConfig(n_samples=5))
    eta_b = _eval(items, run_id="B", config=EndorsementConfig(n_samples=3))
    with pytest.raises(RetestConfigMismatchError, match="endorsement_config"):
        compute_retest(eta_a, eta_b)


def test_paraphrase_variant_mismatch_raises() -> None:
    items = [_item("a", analyst_verdicts=[Verdict.GOOD],
                   model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)]
    eta_a = _eval(items, run_id="A", paraphrase_variant=0)
    eta_b = _eval(items, run_id="B", paraphrase_variant=1)
    with pytest.raises(RetestConfigMismatchError, match="paraphrase_variant"):
        compute_retest(eta_a, eta_b)


# ---- Per-item deltas + dict serialization -------------------------------


def test_item_deltas_record_entropy_and_margin_per_run() -> None:
    # Run A: confident agree (5/0/0). Run B: thin agree (3/2/0).
    items_a = [_item("a", analyst_verdicts=[Verdict.GOOD],
                     model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)]
    items_b = [_item("a", analyst_verdicts=[Verdict.GOOD],
                     model_verdict=Verdict.GOOD, good=3, bad=2, abstain=0)]
    result = compute_retest(_eval(items_a, run_id="A"), _eval(items_b, run_id="B"))
    assert len(result.item_deltas) == 1
    delta = result.item_deltas[0]
    assert delta.item_id == "a"
    assert delta.verdict_a == "good" and delta.verdict_b == "good"  # not flipped
    assert delta.margin_a == 1.0
    assert delta.margin_b == pytest.approx(0.2)
    assert delta.margin_delta == pytest.approx(0.8)
    assert delta.entropy_b > delta.entropy_a  # thin distribution is higher entropy
    assert delta.entropy_delta > 0


def test_dict_serialization_round_trip() -> None:
    items = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
    ]
    result = compute_retest(_eval(items, run_id="A"), _eval(items, run_id="B"))
    d = retest_result_to_dict(result)
    assert d["schema_version"] == "1.0"
    assert d["benchmark_id"] == "bench"
    assert d["n_items"] == 1
    assert d["test_retest_kappa"] is None  # single item, all-GOOD -> p_e = 1
    assert d["agreement_rate"] == 1.0
    assert d["flipped_items"] == []
    assert len(d["item_deltas"]) == 1
    assert "stability_verdict" in d
    assert "framework_version" in d


# ---- Item-id intersection ------------------------------------------------


def test_item_id_intersection_runs_over_common_items_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When one run is missing items present in the other, the comparison
    runs over the intersection with a logged warning."""
    items_a = [
        _item(f"i{i}", analyst_verdicts=[Verdict.GOOD],
              model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)
        for i in range(3)
    ]
    items_b = [
        _item("i0", analyst_verdicts=[Verdict.GOOD],
              model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0),
        _item("i1", analyst_verdicts=[Verdict.GOOD],
              model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0),
        # i2 missing; new item i3 instead
        _item("i3", analyst_verdicts=[Verdict.GOOD],
              model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0),
    ]
    caplog.clear()
    import logging
    caplog.set_level(logging.WARNING, logger="infereval.retest")
    result = compute_retest(_eval(items_a, run_id="A"), _eval(items_b, run_id="B"))
    assert result.n_items == 2  # i0, i1 common
    assert "only-in-A" in caplog.text


# ---- v0.6.1: IdentityCriterion threading + Stage-2 framing changes -------


def _valid_criterion():
    from infereval.report import IdentityCriterion

    return IdentityCriterion(
        same_provider_model_id=True,
        cross_update_identity_asserted=True,
        same_scaffolding=True,
        unverifiable_caveats="OpenAI snapshot fingerprint stable across runs.",
        rationale="Two runs minutes apart on the same provider snapshot.",
    )


def test_v0_6_1_compute_retest_without_criterion_backward_compatible() -> None:
    """Pre-v0.6.1 call style still works; identity_criterion is None."""
    items = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
    ]
    result = compute_retest(_eval(items, run_id="A"), _eval(items, run_id="B"))
    assert result.identity_criterion is None
    # stability_verdict has no "under the declared identity criterion" clause.
    assert "under the declared identity criterion" not in result.stability_verdict


def test_v0_6_1_compute_retest_with_criterion_threads_it_through() -> None:
    items = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
        _item("b", analyst_verdicts=[Verdict.BAD], model_verdict=Verdict.BAD,
              good=0, bad=5, abstain=0),
    ]
    crit = _valid_criterion()
    result = compute_retest(
        _eval(items, run_id="A"),
        _eval(items, run_id="B"),
        identity_criterion=crit,
    )
    assert result.identity_criterion is crit
    # stability_verdict now carries the criterion clause.
    assert "under the declared identity criterion" in result.stability_verdict


def test_v0_6_1_retest_result_to_dict_serializes_criterion() -> None:
    items = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
        _item("b", analyst_verdicts=[Verdict.BAD], model_verdict=Verdict.BAD,
              good=0, bad=5, abstain=0),
    ]
    crit = _valid_criterion()
    result = compute_retest(
        _eval(items, run_id="A"),
        _eval(items, run_id="B"),
        identity_criterion=crit,
    )
    payload = retest_result_to_dict(result)
    assert "identity_criterion" in payload
    embedded = payload["identity_criterion"]
    assert isinstance(embedded, dict)
    assert embedded["same_provider_model_id"] is True
    assert embedded["rationale"].startswith("Two runs minutes apart")


def test_v0_6_1_retest_result_to_dict_omits_criterion_when_absent() -> None:
    """Pre-v0.6.1 retest results round-trip without the new key."""
    items = [
        _item("a", analyst_verdicts=[Verdict.GOOD], model_verdict=Verdict.GOOD,
              good=5, bad=0, abstain=0),
    ]
    result = compute_retest(_eval(items, run_id="A"), _eval(items, run_id="B"))
    payload = retest_result_to_dict(result)
    assert "identity_criterion" not in payload


def test_v0_6_1_relabel_error_message_names_setup_conformance() -> None:
    """Stage-2 relabel: RetestConfigMismatchError messages now use the
    setup-conformance / individuation-criterion vocabulary."""
    items_a = [_item("a", analyst_verdicts=[Verdict.GOOD],
                     model_verdict=Verdict.GOOD, good=5, bad=0, abstain=0)]
    eta_a = _eval(items_a, run_id="A", benchmark_hash="aaaaaa")
    eta_b = _eval(items_a, run_id="B", benchmark_hash="bbbbbb")
    with pytest.raises(RetestConfigMismatchError) as exc_info:
        compute_retest(eta_a, eta_b)
    msg = str(exc_info.value)
    assert "setup-conformance" in msg
    assert "individuation criterion" in msg


# ---- v0.14.0: compute_interval_s helper ----------------------------------


def test_compute_interval_s_basic_delta() -> None:
    """Standard case: later capture's started_at is N seconds after baseline's."""
    from datetime import datetime, timezone

    from infereval.retest import compute_interval_s

    baseline = _eval([], run_id="b")
    later = _eval([], run_id="l")
    # Force timestamps via Pydantic model_copy (Evaluation is frozen-ish
    # but model_copy returns a new instance).
    baseline = baseline.model_copy(update={
        "started_at": datetime(2026, 6, 6, 12, 0, 0, tzinfo=timezone.utc),
    })
    later = later.model_copy(update={
        "started_at": datetime(2026, 6, 6, 12, 10, 0, tzinfo=timezone.utc),
    })
    assert compute_interval_s(baseline, later) == 600


def test_compute_interval_s_returns_zero_when_started_at_missing() -> None:
    """Defensive: either eta missing started_at → return 0 (degenerate metadata)."""
    from infereval.retest import compute_interval_s

    baseline = _eval([], run_id="b").model_copy(update={"started_at": None})
    later = _eval([], run_id="l")
    assert compute_interval_s(baseline, later) == 0
    # Also covers the reverse case.
    baseline = _eval([], run_id="b")
    later = _eval([], run_id="l").model_copy(update={"started_at": None})
    assert compute_interval_s(baseline, later) == 0


def test_compute_interval_s_clamps_negative_delta_to_zero() -> None:
    """If later.started_at < baseline.started_at (clock skew or flipped
    argument order), clamp to 0 rather than raising. Same effect as the
    within-session-floor reading for `--interval-s 0`."""
    from datetime import datetime, timezone

    from infereval.retest import compute_interval_s

    baseline = _eval([], run_id="b").model_copy(update={
        "started_at": datetime(2026, 6, 6, 13, 0, 0, tzinfo=timezone.utc),
    })
    later = _eval([], run_id="l").model_copy(update={
        "started_at": datetime(2026, 6, 6, 12, 0, 0, tzinfo=timezone.utc),
    })
    assert compute_interval_s(baseline, later) == 0


# ---- v0.12.0: MultiIntervalRetestResult ----------------------------------


class TestMultiIntervalRetestResult:
    """v0.12.0: anchored-on-baseline N-pair retest wrapper."""

    @staticmethod
    def _three_item_eval(run_id: str) -> Evaluation:
        items = [
            _item(f"item-{i}", analyst_verdicts=[Verdict.GOOD],
                  model_verdict=Verdict.GOOD, good=3, bad=0, abstain=0)
            for i in range(3)
        ]
        return _eval(items, run_id=run_id)

    def test_pairs_carry_per_interval_metadata(self) -> None:
        from infereval.retest import IntervalPair, MultiIntervalRetestResult
        baseline = self._three_item_eval("baseline")
        later1 = self._three_item_eval("later-1")
        later2 = self._three_item_eval("later-2")

        pair1 = IntervalPair(
            interval_s=0,
            run_id=later1.id,
            retest=compute_retest(baseline, later1),
        )
        pair2 = IntervalPair(
            interval_s=86400,
            run_id=later2.id,
            retest=compute_retest(baseline, later2),
        )

        result = MultiIntervalRetestResult(
            schema_version="1.0",
            framework_version="0.12.0",
            benchmark_id="bench",
            benchmark_hash="abc123",
            baseline_run_id=baseline.id,
            pairs=(pair1, pair2),
        )

        assert result.baseline_run_id == "baseline"
        assert len(result.pairs) == 2
        assert result.pairs[0].interval_s == 0
        assert result.pairs[1].interval_s == 86400
        # Each embedded retest is the baseline-vs-later comparison.
        assert result.pairs[0].retest.run_a_id == baseline.id
        assert result.pairs[0].retest.run_b_id == later1.id
        assert result.pairs[1].retest.run_a_id == baseline.id
        assert result.pairs[1].retest.run_b_id == later2.id

    def test_frozen_dataclass_contract(self) -> None:
        """Mirrors RetestResult's frozen=True invariant."""
        from infereval.retest import MultiIntervalRetestResult

        result = MultiIntervalRetestResult(
            schema_version="1.0", framework_version="0.12.0",
            benchmark_id="b", benchmark_hash="h",
            baseline_run_id="bl", pairs=(),
        )
        with pytest.raises((AttributeError, TypeError)):
            result.baseline_run_id = "different"  # type: ignore[misc]

    def test_dict_serialization_round_trip(self) -> None:
        from infereval.retest import (
            IntervalPair,
            MultiIntervalRetestResult,
            multi_interval_retest_result_to_dict,
        )
        baseline = self._three_item_eval("baseline")
        later = self._three_item_eval("later-1")

        result = MultiIntervalRetestResult(
            schema_version="1.0", framework_version="0.12.0",
            benchmark_id="bench", benchmark_hash="abc123",
            baseline_run_id=baseline.id,
            pairs=(IntervalPair(
                interval_s=0, run_id=later.id,
                retest=compute_retest(baseline, later),
            ),),
        )
        d = multi_interval_retest_result_to_dict(result)
        assert d["schema_version"] == "1.0"
        assert d["benchmark_id"] == "bench"
        assert d["baseline_run_id"] == "baseline"
        assert len(d["pairs"]) == 1
        p = d["pairs"][0]
        assert p["interval_s"] == 0
        assert p["run_id"] == later.id
        # Embedded retest dict carries the standard RetestResult shape.
        assert p["retest"]["benchmark_id"] == "bench"
        assert "test_retest_kappa" in p["retest"]
        # Multi-interval default has no identity_criterion.
        assert "identity_criterion" not in d

    def test_empty_pairs_is_legal_but_pointless(self) -> None:
        """The dataclass admits an empty pairs tuple — caller's
        responsibility to not construct one in practice. This regression-
        guards that no validator silently rejects the shape."""
        from infereval.retest import MultiIntervalRetestResult
        result = MultiIntervalRetestResult(
            schema_version="1.0", framework_version="0.12.0",
            benchmark_id="b", benchmark_hash=None,
            baseline_run_id="bl", pairs=(),
        )
        assert result.pairs == ()

    def test_identity_criterion_threading(self) -> None:
        """When supplied at construction time, identity_criterion is
        carried in serialization (mirrors RetestResult's pattern)."""
        from infereval.report import IdentityCriterion
        from infereval.retest import (
            MultiIntervalRetestResult,
            multi_interval_retest_result_to_dict,
        )

        crit = IdentityCriterion(
            same_benchmark_hash=True,
            same_endorsement_config=True,
            same_paraphrase_variant=True,
            same_provider_model_id=True,
            cross_update_identity_asserted=False,
            same_scaffolding=True,
            unverifiable_caveats="back-to-back captures same process",
            rationale="multi-interval same-process anchor",
        )
        result = MultiIntervalRetestResult(
            schema_version="1.0", framework_version="0.12.0",
            benchmark_id="b", benchmark_hash="h",
            baseline_run_id="bl", pairs=(),
            identity_criterion=crit,
        )
        d = multi_interval_retest_result_to_dict(result)
        assert "identity_criterion" in d
        assert d["identity_criterion"]["rationale"] == (
            "multi-interval same-process anchor"
        )

    def test_exposed_in_module_all(self) -> None:
        """Stage-1 contract: the new symbols are in infereval.retest.__all__."""
        import infereval.retest as r
        assert "IntervalPair" in r.__all__
        assert "MultiIntervalRetestResult" in r.__all__
        assert "multi_interval_retest_result_to_dict" in r.__all__
