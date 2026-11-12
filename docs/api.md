# API reference

Auto-generated from the docstrings in `src/infereval/`. The docstrings are
maintained as a first-class artifact and use the notation in the
[Glossary](glossary.md), so
`help(infereval.metrics.cohens_kappa)` is reliable; this page just renders
the same content as a navigable site.

If you're looking for symbolic notation rather than callables, see the
[Glossary](glossary.md).

## Core data types

::: infereval.types.Verdict
    options:
      show_root_heading: true

::: infereval.types.Bearer
    options:
      show_root_heading: true

::: infereval.types.Implication
    options:
      show_root_heading: true

::: infereval.frame.DerivedFrame
    options:
      show_root_heading: true

## Benchmark

::: infereval.benchmark.Benchmark
    options:
      show_root_heading: true
      members:
        - load
        - dump
        - n
        - m
        - cells
        - has_factorial_design
        - panel_names
        - resolved_primary_panel

::: infereval.benchmark.BenchmarkItem
    options:
      show_root_heading: true

::: infereval.benchmark.BearerModel
    options:
      show_root_heading: true

::: infereval.benchmark.AnalystModel
    options:
      show_root_heading: true

::: infereval.benchmark.RSRTarget
    options:
      show_root_heading: true

::: infereval.benchmark.ConstructionMetadata
    options:
      show_root_heading: true

::: infereval.benchmark.FactorConstraints
    options:
      show_root_heading: true

::: infereval.benchmark.ContextBuilders
    options:
      show_root_heading: true

::: infereval.benchmark.TemplateContextBuilder
    options:
      show_root_heading: true

::: infereval.benchmark.PluginContextBuilder
    options:
      show_root_heading: true

::: infereval.benchmark.VerificationPromptOverride
    options:
      show_root_heading: true

::: infereval.benchmark.Reference
    options:
      show_root_heading: true

## Evaluation

::: infereval.evaluation.evaluate
    options:
      show_root_heading: true

::: infereval.evaluation.Evaluation
    options:
      show_root_heading: true

::: infereval.evaluation.EvaluationItem
    options:
      show_root_heading: true

::: infereval.evaluation.EndorsementConfig
    options:
      show_root_heading: true

::: infereval.evaluation.ProviderParams
    options:
      show_root_heading: true

::: infereval.evaluation.SampleRecord
    options:
      show_root_heading: true

::: infereval.evaluation.MajorityVote
    options:
      show_root_heading: true

::: infereval.evaluation.canonical_benchmark_hash
    options:
      show_root_heading: true

## Metrics

::: infereval.metrics.coverage
    options:
      show_root_heading: true

::: infereval.metrics.consensus_verdict
    options:
      show_root_heading: true

::: infereval.metrics.consensus_reference
    options:
      show_root_heading: true

::: infereval.metrics.cohens_kappa
    options:
      show_root_heading: true

::: infereval.metrics.fleiss_kappa
    options:
      show_root_heading: true

::: infereval.metrics.inter_analyst_fleiss
    options:
      show_root_heading: true

::: infereval.metrics.inter_analyst_fleiss_per_panel
    options:
      show_root_heading: true

::: infereval.metrics.cross_panel_kappa
    options:
      show_root_heading: true

::: infereval.metrics.MetricsReport
    options:
      show_root_heading: true

## Structural checks (R13)

::: infereval.structure.run_all_checks
    options:
      show_root_heading: true

::: infereval.structure.containment_closure_check
    options:
      show_root_heading: true

::: infereval.structure.rsr_role_consistency_check
    options:
      show_root_heading: true

::: infereval.structure.base_case_stability_check
    options:
      show_root_heading: true

::: infereval.structure.StructuralReport
    options:
      show_root_heading: true

::: infereval.structure.StructuralCheck
    options:
      show_root_heading: true

::: infereval.structure.StructuralAnomaly
    options:
      show_root_heading: true

## Factor-effects model (R7 / R12)

::: infereval.modeling.fit_factor_model
    options:
      show_root_heading: true

::: infereval.modeling.ModelFit
    options:
      show_root_heading: true

::: infereval.modeling.FactorEffect
    options:
      show_root_heading: true

## Sensitivity sweeps (R11)

::: infereval.sweep.run_sweep
    options:
      show_root_heading: true

::: infereval.sweep.SweepResult
    options:
      show_root_heading: true

::: infereval.sweep.SweepRow
    options:
      show_root_heading: true

## Construct-validity report (R16–R21)

::: infereval.report.ConstructValidityClaims
    options:
      show_root_heading: true

::: infereval.report.MasterySenseClaim
    options:
      show_root_heading: true

::: infereval.report.ScopeClaim
    options:
      show_root_heading: true

::: infereval.report.ConstitutionClaim
    options:
      show_root_heading: true

::: infereval.report.CarvingClaim
    options:
      show_root_heading: true

::: infereval.report.CompetingExplanationChecks
    options:
      show_root_heading: true

::: infereval.report.ReportVerdict
    options:
      show_root_heading: true

::: infereval.report.compute_verdict
    options:
      show_root_heading: true

::: infereval.report.render_markdown
    options:
      show_root_heading: true

::: infereval.report.NegativeFinding
    options:
      show_root_heading: true

::: infereval.report.collect_negative_findings
    options:
      show_root_heading: true

## Providers

::: infereval.providers.get_provider
    options:
      show_root_heading: true

::: infereval.providers.base.Provider
    options:
      show_root_heading: true

::: infereval.providers.base.BaseProvider
    options:
      show_root_heading: true

::: infereval.providers.base.SampleRequest
    options:
      show_root_heading: true

::: infereval.providers.base.SampleResult
    options:
      show_root_heading: true

::: infereval.providers.base.RetryPolicy
    options:
      show_root_heading: true

::: infereval.providers.mock.ScriptedProvider
    options:
      show_root_heading: true

::: infereval.providers.mock.ReplayProvider
    options:
      show_root_heading: true

## Prompts

::: infereval.prompts.VerificationPrompt
    options:
      show_root_heading: true

::: infereval.prompts.resolve_verification_prompt
    options:
      show_root_heading: true

## Endorsement

::: infereval.endorsement.endorse
    options:
      show_root_heading: true

::: infereval.endorsement.EndorsementRecord
    options:
      show_root_heading: true

::: infereval.endorsement.parse_verdict
    options:
      show_root_heading: true

::: infereval.endorsement.majority_vote
    options:
      show_root_heading: true

## Context builders

::: infereval.context.resolve_context_builder
    options:
      show_root_heading: true

::: infereval.context.resolve_context_builders
    options:
      show_root_heading: true

::: infereval.context.make_template_builder
    options:
      show_root_heading: true

::: infereval.context.strip_tex_math
    options:
      show_root_heading: true
