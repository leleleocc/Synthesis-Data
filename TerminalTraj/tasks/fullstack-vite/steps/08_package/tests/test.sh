#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in \
  01_repo_profile \
  02_repo_gate \
  03_environment \
  04_task_design \
  05_task_review \
  06_verifier; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
# 07 is optional in the assembly model; seal it only when present.
if [ -f /synthesis/state/07_verifier_review.json ]; then
  verify_state_seal /synthesis/state/07_verifier_review.json \
    /synthesis/state/.integrity/07_verifier_review.sha256
  APPROVED_STATE=/synthesis/state/07_verifier_review.json
else
  APPROVED_STATE=/synthesis/state/05_task_review.json
fi
P=/synthesis/output/generated_task
require_dir "$P"
require_file "$P/manifest.json"
python /opt/terminaltraj/scripts/target_spec.py check-package \
  /synthesis/input/target_spec.json \
  /synthesis/state/03_environment.json \
  /synthesis/state/04_task_design.json \
  /synthesis/state/06_verifier.json \
  "$APPROVED_STATE" \
  /synthesis/output/environment \
  /synthesis/output/candidates \
  "$P" \
  || fail "generated task packages do not satisfy the assemble-only contract"
pass "all surviving candidates assembled as Harbor tasks"
