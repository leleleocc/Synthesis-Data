#!/bin/bash
# test.sh — verifier entry point.
# Invoked inside the separate verifier environment with /workspace containing
# the agent's submitted artifact.
#
# Replace the example criterion below with the actual evaluation logic.
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"

# Run Reward Kit criterion evaluation.
# Add or replace criterion modules as needed.
python3 - <<'PY'
import json, sys
from pathlib import Path
from reward_kit import evaluate  # adjust imports to your actual criterion modules

workspace = Path(sys.environ.get("WORKSPACE", "/workspace"))

# TODO: Replace with actual criterion evaluation.
# results = evaluate(workspace, criteria=[...])
# For now, emit an empty programmatic result so the harness can parse scores.
results = {"criteria": [], "score": 0.0}

print(json.dumps(results))
PY
