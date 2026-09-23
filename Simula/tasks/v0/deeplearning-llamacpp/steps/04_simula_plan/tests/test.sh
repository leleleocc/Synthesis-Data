#!/usr/bin/env bash
set -u
source /tests/helpers.sh
verify_state_seal /synthesis/state/01_repo_profile.json \
  /synthesis/state/.integrity/01_repo_profile.sha256
verify_state_seal /synthesis/state/02_repo_gate.json \
  /synthesis/state/.integrity/02_repo_gate.sha256
verify_state_seal /synthesis/state/03_environment.json \
  /synthesis/state/.integrity/03_environment.sha256
require_handoff 04_simula_plan
S=/synthesis/state/04_simula_plan.json
require_json_keys "$S" global slots
python /opt/terminaltraj/scripts/target_spec.py check-simula-plan \
  /synthesis/input/target_spec.json "$S" /synthesis/state/03_environment.json \
  || fail "simula plan is outside target_spec or the sealed environment"
seal_state "$S" /synthesis/state/.integrity/04_simula_plan.sha256
pass "simula plan has exactly max_candidates grounded slots"
