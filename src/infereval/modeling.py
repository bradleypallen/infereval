"""Factor-effects modeling of model–analyst agreement.

Phase 2.2 of the construct-validity infrastructure (per *Closing the
Construct-Validity Gap in infereval*). Addresses **R7** (multiple items
per condition) and deepens **R12** (per-condition decomposition).

The source document motivates a *generalized linear mixed-effects model*
of M's verdict with declared factors as fixed effects and items/analysts
as random effects. The ideal backend would be ``bambi`` / PyMC, which
gives a proper random-effects decomposition. For the lighter dependency
footprint, this module instead ships a **fixed-effects logistic
regression with item-clustered standard errors** as a proxy for the
per-item random-effect structure.

The trade-off: the variance-component decomposition (item-level and
analyst-level random effects) is sacrificed; the marginal fixed-effects
coefficients and joint Wald tests — which is what the document's
"main effect of side-premise type, p < 0.001" output most directly
needs — are recoverable from the coefficient table.

The CLI / module docstring / CHANGELOG all explicitly call this out as
*not* a full GLMM. A follow-up issue can swap the backend to ``bambi``
for projects that need the full GLMM treatment.

The dependency is :mod:`statsmodels`, available as the optional
``[stats]`` extra: ``pip install 'infereval[stats]'``. Imports are lazy
so the rest of the framework continues to work without it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from .types import Verdict

if TYPE_CHECKING:
    from .benchmark import Benchmark
    from .evaluation import Evaluation


class ModelingError(RuntimeError):
    """Raised when ``infereval.modeling`` cannot fit a model.

    Distinguishable from ``ValueError`` so the CLI layer can render a
    specific user-facing message (e.g. "the benchmark declares no
    factors; modeling has nothing to estimate").
    """


@dataclass(frozen=True)
class FactorEffect:
    """One row of the fitted coefficient table.

    Coefficients are log-odds relative to the alphabetically-first
    level of the same factor (the baseline). Positive coef → higher
    odds of agreement than the baseline level.
    """

    factor: str
    level: str
    coef: float
    std_err: float
    z_value: float
    p_value: float
    conf_int_low: float
    conf_int_high: float


@dataclass(frozen=True)
class ModelFit:
    """Result of fitting the factor-effects logistic regression."""

    n_observations: int
    """Number of (item, sample) rows used in the fit."""
    n_items: int
    """Number of distinct items contributing observations (= number of clusters)."""
    n_factors: int
    n_dropped_abstain: int
    """Sample observations excluded because the verdict was ABSTAIN."""
    deviance: float
    """-2 × log-likelihood of the fitted model."""
    null_deviance: float
    """-2 × log-likelihood of the intercept-only model."""
    pseudo_r2: float | None
    """McFadden's pseudo-R² = 1 - log-lik(full) / log-lik(null)."""
    effects: tuple[FactorEffect, ...]
    """One row per non-baseline level of each declared factor."""
    factor_wald: dict[str, float]
    """Per-factor joint Wald p-value testing 'this factor has no effect'."""
    notes: tuple[str, ...]
    """Methodology notes / caveats surfaced for the CLI report."""


# ---- The public entry point -----------------------------------------------


_DEFAULT_REFERENCE: Literal["consensus"] = "consensus"


def fit_factor_model(
    evaluation: Evaluation,
    benchmark: Benchmark,
    *,
    reference: str = _DEFAULT_REFERENCE,
) -> ModelFit:
    """Logistic regression of agreement on declared factor levels.

    Parameters
    ----------
    evaluation
        The :class:`~infereval.evaluation.Evaluation` to model. Each
        item's per-sample verdicts are unrolled into separate
        observations; samples with ABSTAIN verdicts are dropped.
    benchmark
        The source :class:`~infereval.benchmark.Benchmark`. Must declare
        at least one factor in ``benchmark.factors`` (per Phase 1.1).
    reference
        Which analyst column defines "agreement". ``"consensus"``
        (default) uses the per-item majority of the analyst panel
        (abstain on tie). An ``"analyst:<id>"`` string picks a single
        analyst column.

    Returns
    -------
    ModelFit

    Raises
    ------
    ModelingError
        If the benchmark declares no factors, if no sample observations
        remain after dropping abstains, or if the design matrix is
        rank-deficient (e.g. every item in the same cell).
    """
    if not benchmark.factors:
        raise ModelingError(
            "Benchmark declares no factors. infereval model needs at least "
            "one factor in `benchmark.factors` (Phase 1.1) to fit against. "
            "Re-author the benchmark with factor declarations, or use "
            "`infereval metrics --by-tag` for a tag-based decomposition."
        )

    # Late import so the rest of the package works without statsmodels.
    try:
        import pandas as pd  # type: ignore[import-untyped]
        import statsmodels.api as sm  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ModelingError(
            "infereval.modeling requires the [stats] extra: "
            "pip install 'infereval[stats]'"
        ) from exc

    # 1. Build the long-format observation table.
    rows = _build_observation_rows(evaluation, benchmark, reference=reference)
    n_dropped = sum(1 for r in rows if r["agrees"] is None)
    rows = [r for r in rows if r["agrees"] is not None]
    if not rows:
        raise ModelingError(
            "No substantive observations after dropping abstain samples; "
            "cannot fit a model on an all-abstain dataset."
        )

    df = pd.DataFrame(rows)

    # 2. One-hot encode each factor; the alphabetically-first level is
    # dropped as the baseline (statsmodels default).
    factor_names = sorted(benchmark.factors)
    # Ensure every level is observed as a category so dummies are stable
    # even when the dataset doesn't contain every level.
    for f in factor_names:
        df[f] = pd.Categorical(df[f], categories=benchmark.factors[f], ordered=False)

    design_parts = [pd.Series(1.0, index=df.index, name="Intercept")]
    factor_to_cols: dict[str, list[str]] = {}
    for f in factor_names:
        dummies = pd.get_dummies(df[f], prefix=f, drop_first=True, dtype=float)
        design_parts.append(dummies)
        factor_to_cols[f] = list(dummies.columns)
    design_X = pd.concat(design_parts, axis=1)  # noqa: N806 -- statistical convention
    y = df["agrees"].astype(int).to_numpy()

    if design_X.shape[0] <= design_X.shape[1]:
        raise ModelingError(
            f"Design matrix is rank-deficient: {design_X.shape[0]} observations vs. "
            f"{design_X.shape[1]} parameters. Add items or declare fewer levels."
        )

    # 3. Fit logistic regression with item-clustered SEs.
    model = sm.Logit(y, design_X)
    fit = model.fit(
        method="bfgs",
        disp=False,
        cov_type="cluster",
        cov_kwds={"groups": df["item_id"].to_numpy()},
        maxiter=200,
    )

    # 4. Fit the null model for pseudo-R² and overall LR test.
    null_model = sm.Logit(y, design_X[["Intercept"]])
    null_fit = null_model.fit(method="bfgs", disp=False, maxiter=200)

    deviance = float(-2 * fit.llf)
    null_deviance = float(-2 * null_fit.llf)
    if null_fit.llf == 0:
        pseudo_r2: float | None = None
    else:
        pseudo_r2 = float(1 - fit.llf / null_fit.llf)

    # 5. Per-factor joint Wald tests via the f_test API.
    factor_wald: dict[str, float] = {}
    for f in factor_names:
        cols = factor_to_cols[f]
        if not cols:
            continue
        constraint = " = 0, ".join(f"{c}" for c in cols) + " = 0"
        try:
            wald = fit.wald_test(constraint, scalar=True)
            p = float(wald.pvalue)
        except Exception:  # noqa: BLE001 — Wald can fail when factor is collinear
            p = float("nan")
        factor_wald[f] = p

    # 6. Per-level effects table.
    params = fit.params
    bse = fit.bse
    pvalues = fit.pvalues
    conf = fit.conf_int()
    effects: list[FactorEffect] = []
    for f in factor_names:
        for col in factor_to_cols[f]:
            level = col[len(f) + 1 :]  # strip "factor_" prefix
            ci_low, ci_high = conf.loc[col]
            effects.append(
                FactorEffect(
                    factor=f,
                    level=level,
                    coef=float(params[col]),
                    std_err=float(bse[col]),
                    z_value=float(params[col] / bse[col]) if bse[col] else float("nan"),
                    p_value=float(pvalues[col]),
                    conf_int_low=float(ci_low),
                    conf_int_high=float(ci_high),
                )
            )

    notes = (
        "Fixed-effects logistic regression with item-clustered standard errors.",
        "Approximates the per-item random-effect structure of a proper GLMM.",
        f"Reference for 'agreement': {reference!r}.",
    )

    return ModelFit(
        n_observations=int(design_X.shape[0]),
        n_items=int(df["item_id"].nunique()),
        n_factors=len(factor_names),
        n_dropped_abstain=n_dropped,
        deviance=deviance,
        null_deviance=null_deviance,
        pseudo_r2=pseudo_r2,
        effects=tuple(effects),
        factor_wald=factor_wald,
        notes=notes,
    )


def _build_observation_rows(
    evaluation: Evaluation,
    benchmark: Benchmark,
    *,
    reference: str,
) -> list[dict[str, object]]:
    """One row per (item, sample) pair with factor levels + agreement label."""
    bench_by_id = {it.id: it for it in benchmark.items}

    # Reference column per item: 'consensus' or 'analyst:<id>'.
    if reference == _DEFAULT_REFERENCE:
        ref_col = {it.id: _consensus_of(it.analyst_verdicts) for it in benchmark.items}
    elif reference.startswith("analyst:"):
        target_id = reference.split(":", 1)[1]
        try:
            j = benchmark.analyst_index(target_id)
        except KeyError as exc:
            raise ModelingError(
                f"reference='analyst:{target_id}' but no such analyst on this benchmark"
            ) from exc
        # An item the analyst did not rate reads as abstain (no reference).
        ref_col = {it.id: it.analyst_verdicts[j] or Verdict.ABSTAIN for it in benchmark.items}
    else:
        raise ModelingError(
            f"reference={reference!r} must be 'consensus' or 'analyst:<id>'"
        )

    rows: list[dict[str, object]] = []
    for eta_item in evaluation.items:
        bench_item = bench_by_id.get(eta_item.id)
        if bench_item is None:
            continue
        if not bench_item.factor_levels:
            continue  # item has no factor metadata; skip
        ref_v = ref_col[eta_item.id]
        for sample in eta_item.samples:
            sv = sample.parsed_verdict
            if sv == Verdict.ABSTAIN or ref_v == Verdict.ABSTAIN:
                agrees: int | None = None  # excluded
            else:
                agrees = 1 if sv == ref_v else 0
            row: dict[str, object] = {
                "item_id": eta_item.id,
                "agrees": agrees,
            }
            for f, lvl in bench_item.factor_levels.items():
                row[f] = lvl
            rows.append(row)
    return rows


def _consensus_of(verdicts: list[Verdict | None]) -> Verdict:
    """Majority verdict among analysts; abstain on tie (unrated cells left out)."""
    counts = Counter(v for v in verdicts if v is not None)
    if not counts:
        return Verdict.ABSTAIN
    top = counts.most_common(1)[0][1]
    winners = [v for v, c in counts.items() if c == top]
    if len(winners) > 1:
        return Verdict.ABSTAIN
    return winners[0]


__all__ = [
    "FactorEffect",
    "ModelFit",
    "ModelingError",
    "fit_factor_model",
]

# Acknowledge unused import (np) — kept for downstream callers that may
# extend this module with array-level computations.
_ = np
