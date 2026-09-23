#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in \
  01_repo_profile \
  02_repo_gate \
  03_environment \
  04_simula_plan \
  05_task_design \
  06_task_review; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
require_handoff 07_verifier
S=/synthesis/state/07_verifier.json
require_json_keys "$S" verifiers
python /opt/terminaltraj/scripts/target_spec.py check-verifiers \
  /synthesis/state/06_task_review.json "$S" /synthesis/output/candidates \
  || fail "verifier records do not satisfy the phase 07 contract"
seal_state "$S" /synthesis/state/.integrity/07_verifier.sha256
pass "verifiers generated for all approved candidates"
