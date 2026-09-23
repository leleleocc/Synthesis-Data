#!/usr/bin/env bash
set -u
source /tests/helpers.sh

require_file /synthesis/input/target_spec.json
require_dir /synthesis/input/repository
require_handoff 01_repo_profile
require_json_keys /synthesis/state/01_repo_profile.json \
  source_repo languages domains subdomains entrypoints tags
python /opt/terminaltraj/scripts/target_spec.py validate \
  /synthesis/input/target_spec.json \
  || fail "target_spec.json is invalid"
python /opt/terminaltraj/scripts/target_spec.py check-profile \
  /synthesis/input/target_spec.json \
  /synthesis/state/01_repo_profile.json \
  || fail "repo profile is not aligned with target_spec"
seal_state /synthesis/state/01_repo_profile.json \
  /synthesis/state/.integrity/01_repo_profile.sha256
pass "repository profile is present"
