#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in 01_repo_profile_gate 02_environment 03_simula_plan 04_task_design; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
require_handoff 05_verifier
S=/synthesis/state/05_verifier.json
require_json_keys "$S" verifiers
python /opt/terminaltraj/scripts/phase_contract.py check-verifiers \
  /synthesis/state/04_task_design.json "$S" /synthesis/output/candidates \
  || fail "verifier, task.toml, or tests contract failed"
seal_state "$S" /synthesis/state/.integrity/05_verifier.sha256
pass "verifiers and task manifests are valid for every candidate"
