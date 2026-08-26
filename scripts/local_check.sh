#!/usr/bin/env bash
# Run the harness pre-flight against a local model, once one is available.
#
# The pre-flight's layer 1 needs no model at all and is what gates a paid run.
# This adds layer 2: proof that a REAL model, not a deterministic oracle,
# returns schema-valid output the grader can score and refuses a question it
# cannot answer. It costs electricity and nothing else.
#
# It does not predict the paid run. A small local model has a different
# accuracy profile, so any separation between arms seen here is not a result
# and must never be reported as one.
set -euo pipefail

MODEL="${MODEL:-qwen2.5:3b}"
BASE="${BASE:-http://localhost:11434}"

command -v ollama >/dev/null 2>&1 || { echo "ollama is not installed"; exit 1; }
curl -sf "$BASE/api/tags" >/dev/null 2>&1 || {
  echo "no server answering at $BASE -- start it with: ollama serve"; exit 1; }
ollama list | awk 'NR>1{print $1}' | grep -qx "$MODEL" || {
  echo "model $MODEL not present -- pull it with: ollama pull $MODEL"; exit 1; }

cd "$(dirname "$0")/.."
exec python3 scripts/preflight.py --local "$BASE" --model "$MODEL"
