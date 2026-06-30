#!/usr/bin/env bash
# AUMC pilot dry-run gate: 6-model cross-family panel, single capture per cell.
# Pre-clinician — outputs land in /tmp (NOT committed) and feed the
# decision about which contested items deserve clinician time.
#
# Same 6-model panel as the existing pulmonology cross-family benchmark,
# so this dry-run is comparable across the two clinical benchmarks.

set -uo pipefail

REPO=/Users/bradleyallen/Documents/GitHub/infereval
BENCH="${REPO}/examples/AUMC_pilot/benchmark.json"
OUT_DIR=/tmp/aumc-dryrun
mkdir -p "${OUT_DIR}"

# (provider, model_id, label) triples
CELLS=(
  "anthropic,claude-opus-4-7,claude-opus-4.7"
  "openai,gpt-4.1,gpt-4.1"
  "openai,gpt-5.5,gpt-5.5"
  "openrouter,deepseek/deepseek-v4-pro,deepseek-v4-pro"
  "openrouter,google/gemini-2.5-pro,gemini-2.5-pro"
  "openrouter,qwen/qwen3-max,qwen3-max"
)

CLI="${REPO}/.venv/bin/infereval"

run_one() {
  local triple=$1
  IFS=, read -r provider model_id label <<<"$triple"
  local eta="${OUT_DIR}/${label}-eta.json"
  local log="${OUT_DIR}/${label}-run.jsonl"
  echo "[${label}] starting (provider=${provider} model_id=${model_id})"
  local start=$SECONDS
  if "${CLI}" evaluate "${BENCH}" \
      --provider "${provider}" --model "${model_id}" \
      --temperature 0.0 --max-tokens 2048 \
      -o "${eta}" --log "${log}" \
      >"${OUT_DIR}/${label}.stdout" 2>"${OUT_DIR}/${label}.stderr"; then
    local elapsed=$((SECONDS - start))
    echo "[${label}] ok in ${elapsed}s"
  else
    local rc=$?
    local elapsed=$((SECONDS - start))
    echo "[${label}] FAILED rc=${rc} in ${elapsed}s — see ${OUT_DIR}/${label}.stderr"
  fi
}

# Fan-out in parallel (max 6 concurrent — same as v0.10.0 pulm capture pattern)
echo "=== AUMC pilot dry-run gate started at $(date) ==="
for triple in "${CELLS[@]}"; do
  run_one "$triple" &
done
wait
echo "=== AUMC pilot dry-run gate finished at $(date) ==="
