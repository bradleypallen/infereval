#!/usr/bin/env bash
#
# Stop-sign R22 retest captures against the 4-item paper-aligned benchmark.
# Uses `infereval retest --auto` (v0.11.0) to capture per-model test-retest
# evidence that the historical stop-sign cross-family sweep
# (experiments/results/stop_sign_2026-05-18.md) lacked.
#
# Three representative models, one per family:
#   - Claude Opus 4.7      (anthropic)
#   - GPT-4.1              (openai, the v0.5 anchor)
#   - Gemini 2.5 Pro       (openrouter / google)
#
# Output (per model, e.g. opus47):
#   experiments/results/stop_sign/retest/opus47/eta-a.json
#   experiments/results/stop_sign/retest/opus47/eta-a.run.jsonl
#   experiments/results/stop_sign/retest/opus47/eta-b.json
#   experiments/results/stop_sign/retest/opus47/eta-b.run.jsonl
#   experiments/results/stop_sign/retest/opus47-retest.json
#
# Requirements (sourced from the repo's local .env):
#   OPENAI_API_KEY, ANTHROPIC_API_KEY, OPENROUTER_API_KEY
#
# Cost estimate: 3 models × 4 items × 3 samples × 2 captures = 72 LLM calls.
# Under US$1 at current pricing.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BENCH="${REPO_ROOT}/examples/stop_sign/benchmark.json"
OUT_DIR="${REPO_ROOT}/experiments/results/stop_sign/retest"

DRY=
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY=echo
  echo "## DRY RUN — planned invocations:" >&2
fi

# Confirm benchmark before running anything.
"${REPO_ROOT}/.venv/bin/python" -m infereval.cli.main validate "${BENCH}" >&2

mkdir -p "${OUT_DIR}"

SUCCESSES=()
FAILURES=()

run_one() {
  local label="$1" provider="$2" model_id="$3"
  chflags -R nohidden "${REPO_ROOT}/.venv" 2>/dev/null

  local etas_dir="${OUT_DIR}/${label}"
  local retest_out="${OUT_DIR}/${label}-retest.json"

  echo "" >&2
  echo "=== ${label} (${provider}/${model_id}) ===" >&2
  if ${DRY} "${REPO_ROOT}/.venv/bin/python" -m infereval.cli.main retest --auto \
      --benchmark "${BENCH}" \
      --provider "${provider}" \
      --model "${model_id}" \
      --n-samples 3 --temperature 0.0 --max-tokens 1024 \
      --save-etas "${etas_dir}" \
      -o "${retest_out}"; then
    SUCCESSES+=("${label}")
  else
    FAILURES+=("${label}")
    echo "WARNING: ${label} failed; continuing with remaining models" >&2
  fi
}

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "WARNING: ANTHROPIC_API_KEY unset; skipping claude-opus-4.7" >&2
else
  run_one "opus47" "anthropic" "claude-opus-4-7"
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "WARNING: OPENAI_API_KEY unset; skipping gpt-4.1" >&2
else
  run_one "gpt41" "openai" "gpt-4.1"
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "WARNING: OPENROUTER_API_KEY unset; skipping gemini-2.5-pro" >&2
else
  run_one "gemini25pro" "openrouter" "google/gemini-2.5-pro"
fi

echo "" >&2
echo "=== summary ===" >&2
echo "successes (${#SUCCESSES[@]}): ${SUCCESSES[*]:-}" >&2
echo "failures  (${#FAILURES[@]}): ${FAILURES[*]:-}" >&2
echo "" >&2
echo "Output in ${OUT_DIR}" >&2
echo "Next: refresh ${REPO_ROOT}/experiments/results/stop_sign_2026-06-06.md" >&2
echo "      with R22 retest table + R12 under-powered decomposition rendering." >&2

if [[ "${#FAILURES[@]}" -gt 0 ]]; then
  exit 1
fi
