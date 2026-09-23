#!/usr/bin/env bash
set -u
source /tests/helpers.sh
verify_state_seal /synthesis/state/01_repo_profile.json \
  /synthesis/state/.integrity/01_repo_profile.sha256
verify_state_seal /synthesis/state/02_repo_gate.json \
  /synthesis/state/.integrity/02_repo_gate.sha256
verify_state_seal /synthesis/state/03_environment.json \
  /synthesis/state/.integrity/03_environment.sha256
verify_state_seal /synthesis/state/04_simula_plan.json \
  /synthesis/state/.integrity/04_simula_plan.sha256
require_handoff 05_task_design
S=/synthesis/state/05_task_design.json
require_json_keys "$S" candidates
python /opt/terminaltraj/scripts/target_spec.py check-design \
  /synthesis/input/target_spec.json "$S" /synthesis/output/candidates \
  || fail "task design is outside target_spec or missing instruction.md/task.toml/overlay"
seal_state "$S" /synthesis/state/.integrity/05_task_design.sha256
pass "candidate instruction.md, task.toml, and overlay environment/ are present"
