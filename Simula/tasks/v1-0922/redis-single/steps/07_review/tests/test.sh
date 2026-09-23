#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in 01_repo_profile_gate 02_environment 03_simula_plan 04_task_design 05_verifier; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
require_handoff 07_review
S=/synthesis/state/07_review.json
require_json_keys "$S" reviews release_candidate_ids
for doc in "/opt/terminaltraj/docs/static-checks.md" \
           "/opt/terminaltraj/docs/task-implementation.toml" \
           "/opt/terminaltraj/docs/difficulty.md" \
           "/opt/terminaltraj/docs/taxonomy.md"; do
  [ -f "$doc" ] || fail "missing quality doc $doc"
done
require_harbor_packages /synthesis/output/generated_task
python /opt/terminaltraj/scripts/phase_contract.py check-verifier-review \
  /synthesis/state/05_verifier.json "$S" /synthesis/output/generated_task \
  || fail "packaged verifier review failed"
if [ -e /synthesis/output/generated_task/release_manifest.json ]; then
  fail "release_manifest.json was removed; join release_candidate_ids with manifest.json"
fi
seal_state "$S" /synthesis/state/.integrity/07_review.sha256
pass "packaged verifiers reviewed for too-loose and too-strict behavior"
