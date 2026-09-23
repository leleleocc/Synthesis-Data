#!/usr/bin/env bash
set -u
source /tests/helpers.sh

verify_state_seal /synthesis/state/01_repo_profile_gate.json \
  /synthesis/state/.integrity/01_repo_profile_gate.sha256
require_handoff 02_environment
E=/synthesis/output/environment
S=/synthesis/state/02_environment.json
require_dir "$E"
require_json_keys "$S" deployment_mode source_repo services dependencies asset_paths network paths entrypoints build
if [ ! -f "$E/Dockerfile" ] && [ ! -f "$E/docker-compose.yaml" ] && [ ! -f "$E/docker-compose.yml" ]; then
  fail "environment needs Dockerfile or docker-compose.yaml/yaml"
fi
python /opt/terminaltraj/scripts/phase_contract.py check-environment \
  /synthesis/input/target_spec.json "$S" "$E" \
  || fail "shared environment contract failed"
python - "$S" <<'PY' || fail "environment did not pass a docker build and smoke test"
import json
import sys
from pathlib import Path

build = json.loads(Path(sys.argv[1]).read_text())['build']
if build.get('status') != 'passed' or build.get('mode') != 'docker':
    raise SystemExit(1)
if build.get('buildable') is not True or build.get('smoke_test') is not True:
    raise SystemExit(1)
PY
seal_state "$S" /synthesis/state/.integrity/02_environment.sha256
pass "shared environment is present and sealed"
