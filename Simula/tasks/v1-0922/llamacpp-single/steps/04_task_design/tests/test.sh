#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in 01_repo_profile_gate 02_environment 03_simula_plan; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
require_handoff 04_task_design
S=/synthesis/state/04_task_design.json
require_json_keys "$S" candidates
python /opt/terminaltraj/scripts/phase_contract.py check-design \
  "$S" /synthesis/output/candidates \
  || fail "task design is outside the slot or environment contract"
seal_state "$S" /synthesis/state/.integrity/04_task_design.sha256
pass "candidate instructions and environment copies are valid"
