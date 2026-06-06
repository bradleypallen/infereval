#!/usr/bin/env bash
#
# Cross-family rerun of the pulmonary edema benchmark against benchmark v0.2
# (30 items; v0.10.0+). Mirrors the v0.1 capture documented in
# `experiments/results/pulmonology_2026-05-19.md` and archived at
# `experiments/results/pulmonology/archive-29-items-v0.1/`.
#
# Provider + model_id combinations are identical to the v0.1 capture, so the
# new etas are comparable to the archived ones modulo benchmark version.
#
# Requirements
# ------------
# Environment variables:
#   OPENAI_API_KEY       — for gpt-4.1 and gpt-5.5
#   ANTHROPIC_API_KEY    — for claude-opus-4-7
#   OPENROUTER_API_KEY   — for deepseek-v4-pro, gemini-2.5-pro, qwen3-max
#
# A working `infereval` install on the current branch (the package is editable
# in this repo via `pip install -e .`).
#
# Cost
# ----
# Approximately 6 models × 30 items × 3 samples = 540 LLM calls plus overhead.
# At v0.1 capture time the total wall-time across all six runs was ~30 minutes
# (varying by provider). Costs are dominated by Opus 4.7 (largest model) and
# the OpenAI calls. Order-of-magnitude: a few US$ to ~US$20 depending on
# Opus pricing on the day of the run.
#
# Usage
# -----
#   experiments/scripts/rerun_pulmonology_cross_family.sh [--dry-run]
#
# Pass --dry-run to skip the actual provider calls and just print the
# planned invocations.

# NOTE: deliberately not using `set -e` — if one provider fails (auth,
# model-id change, transient 5xx), we still want the remaining providers
# to complete. Failures are surfaced via the trailing per-provider status
# summary.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BENCH="${REPO_ROOT}/examples/pulmonary_edema/benchmark.json"
OUT_DIR="${REPO_ROOT}/experiments/results/pulmonology"
TS="$(/bin/date -u +%Y-%m-%d)"  # used in run_id suffix only

DRY=
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY=echo
  echo "## DRY RUN — planned invocations:" >&2
fi

# Confirm benchmark is the 30-item v0.2 before running anything.
"${REPO_ROOT}/.venv/bin/python" -m infereval.cli.main validate "${BENCH}" >&2
N_ITEMS=$("${REPO_ROOT}/.venv/bin/python" -c "
from pathlib import Path
from infereval.benchmark import Benchmark
print(Benchmark.load(Path('${BENCH}')).n)
")
if [[ "${N_ITEMS}" != "30" ]]; then
  echo "ERROR: expected n=30 in benchmark, got n=${N_ITEMS}. Aborting." >&2
  exit 2
fi

# Shared evaluator flags. n-samples / max-tokens / temperature match the
# v0.1 capture (see archived run.jsonl `params` fields).
COMMON_FLAGS=(
  "--n-samples" "3"
  "--max-tokens" "1024"
  "--temperature" "0.0"
)

# Per-provider status accumulators.
SUCCESSES=()
FAILURES=()

run_one() {
  local label="$1" provider="$2" model_id="$3"
  shift 3
  # `extra` may be empty; ${extra[@]+...} avoids the unbound-variable error
  # under `set -u` when nothing was passed past the first three positionals.
  local extra=("$@")

  local eta="${OUT_DIR}/${label}-eta.json"
  local jsonl="${OUT_DIR}/${label}-run.jsonl"
  local run_id="pulm-${label}-${TS}"

  echo "" >&2
  echo "=== ${label} (${provider}/${model_id}) ===" >&2
  if ${DRY} "${REPO_ROOT}/.venv/bin/python" -m infereval.cli.main evaluate \
      "${BENCH}" \
      --provider "${provider}" \
      --model "${model_id}" \
      "${COMMON_FLAGS[@]}" \
      ${extra[@]+"${extra[@]}"} \
      --run-id "${run_id}" \
      --log "${jsonl}" \
      -o "${eta}"; then
    SUCCESSES+=("${label}")
  else
    FAILURES+=("${label}")
    echo "WARNING: ${label} failed; continuing with remaining providers" >&2
  fi
}

# --- OpenAI ---------------------------------------------------------------

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "WARNING: OPENAI_API_KEY unset; skipping gpt-4.1 and gpt-5.5" >&2
else
  run_one "gpt-4.1"  "openai" "gpt-4.1"
  run_one "gpt-5.5"  "openai" "gpt-5.5"
fi

# --- Anthropic ------------------------------------------------------------

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "WARNING: ANTHROPIC_API_KEY unset; skipping claude-opus-4.7" >&2
else
  run_one "claude-opus-4.7" "anthropic" "claude-opus-4-7"
fi

# --- OpenRouter -----------------------------------------------------------

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "WARNING: OPENROUTER_API_KEY unset; skipping deepseek-v4-pro, gemini-2.5-pro, qwen3-max" >&2
else
  run_one "deepseek-v4-pro" "openrouter" "deepseek/deepseek-v4-pro"
  run_one "gemini-2.5-pro"  "openrouter" "google/gemini-2.5-pro"
  run_one "qwen3-max"       "openrouter" "qwen/qwen3-max"
fi

echo "" >&2
echo "=== summary ===" >&2
echo "successes (${#SUCCESSES[@]}): ${SUCCESSES[*]:-}" >&2
echo "failures  (${#FAILURES[@]}): ${FAILURES[*]:-}" >&2
echo "" >&2
echo "Output in ${OUT_DIR}" >&2
echo "Next: refresh ${REPO_ROOT}/experiments/results/pulmonology_2026-MM-DD.md" >&2
echo "      with cross-family kappa table + interpretation against benchmark v0.2." >&2

# Exit 0 if all attempted runs succeeded; exit 1 if any failed.
if [[ "${#FAILURES[@]}" -gt 0 ]]; then
  exit 1
fi
