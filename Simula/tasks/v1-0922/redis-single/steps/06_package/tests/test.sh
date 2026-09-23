#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in 01_repo_profile_gate 02_environment 03_simula_plan 04_task_design 05_verifier; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
P=/synthesis/output/generated_task
require_dir "$P"
require_file "$P/manifest.json"
python /opt/terminaltraj/scripts/phase_contract.py check-package \
  /synthesis/state/02_environment.json \
  /synthesis/state/04_task_design.json \
  /synthesis/state/05_verifier.json \
  /synthesis/output/environment \
  /synthesis/output/candidates \
  "$P" --allow-environment-repairs \
  || fail "generated task packages do not satisfy the assembly contract"
require_harbor_packages "$P"
pass "all valid candidates assembled as Harbor tasks"
