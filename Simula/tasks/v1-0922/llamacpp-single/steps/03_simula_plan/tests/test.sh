#!/usr/bin/env bash
set -u
source /tests/helpers.sh
verify_state_seal /synthesis/state/01_repo_profile_gate.json \
  /synthesis/state/.integrity/01_repo_profile_gate.sha256
verify_state_seal /synthesis/state/02_environment.json \
  /synthesis/state/.integrity/02_environment.sha256
require_handoff 03_simula_plan
S=/synthesis/state/03_simula_plan.json
require_json_keys "$S" difficulty global slots
python /opt/terminaltraj/scripts/phase_contract.py check-simula-plan \
  /synthesis/input/target_spec.json "$S" /synthesis/state/02_environment.json \
  || fail "simula plan is outside target_spec or environment contract"
seal_state "$S" /synthesis/state/.integrity/03_simula_plan.sha256
pass "simula plan has grounded, diverse slots"
