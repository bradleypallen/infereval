# Archived: 29-item pulmonology cross-family runs (benchmark v0.1)

These six model evaluations were captured against the v0.1 of the
pulmonary edema differential benchmark — the 29-item version, before
the v0.10.0 release added `x3` (ARDS + sepsis → elevated BNP) and
bumped the benchmark id to `pulmonary-edema-differential-v0.2`.

Captured 2026-05-19 against the following framework versions:

- claude-opus-4.7: framework v0.2.1 (after issue #16 fix)
- gpt-5.5: framework v0.2.3 (after issue #20 fix)
- gpt-4.1, gemini-2.5-pro, deepseek-v4-pro, qwen3-max: framework v0.2.0+

## Why these are archived rather than regenerated

The v0.1 → v0.2 benchmark transition adds one cross-cutting marker-inference
item (`x3`) and changes the `benchmark_hash` accordingly. The cross-family
analysis at `experiments/results/pulmonology_2026-05-19.md` was authored
against v0.1; these archived artifacts preserve the dataset that analysis
references. They remain valid evidence about the framework's behavior at
that snapshot — useful for longitudinal comparison once the v0.2 reruns
land.

## What replaces these

Fresh evaluations against the 30-item benchmark v0.2 live in the
parent directory (`experiments/results/pulmonology/`). See
`experiments/scripts/rerun_pulmonology_cross_family.sh` for the rerun
script and `experiments/results/pulmonology_2026-MM-DD.md` for the
refreshed analysis (date TBD).

## Loading these archived artifacts

The eta.json files are tied to benchmark id
`pulmonary-edema-differential-v0.1`. To re-analyze them, you'll need to
git-checkout a pre-v0.10.0 tag (e.g. `git checkout v0.9.2 -- examples/pulmonary_edema/benchmark.json`)
into a scratch directory, then point `--benchmark` at the v0.1 file:

```sh
infereval structure path/to/archive-29-items-v0.1/gemini-2.5-pro-eta.json \
    --benchmark path/to/v0.1/benchmark.json
```

Or simply checkout a v0.9.x tag of the repo, which carries the v0.1
benchmark inline.
