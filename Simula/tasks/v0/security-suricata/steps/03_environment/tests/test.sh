#!/usr/bin/env bash
set -u
source /tests/helpers.sh
verify_state_seal /synthesis/state/01_repo_profile.json \
  /synthesis/state/.integrity/01_repo_profile.sha256
verify_state_seal /synthesis/state/02_repo_gate.json \
  /synthesis/state/.integrity/02_repo_gate.sha256
require_handoff 03_environment
E=/synthesis/output/environment
S=/synthesis/state/03_environment.json
require_dir "$E"
require_file "$E/Dockerfile"
require_file "$E/setup.sh"
require_file "$E/setup-overlay.sh"
require_file "$E/smoke_test.sh"
require_json_keys "$S" \
  deployment_mode base_image services dependencies \
  network_policy asset_paths workdir data_dir results_dir entrypoints build
python /opt/terminaltraj/scripts/target_spec.py check-environment \
  /synthesis/input/target_spec.json "$S" "$E" \
  || fail "environment contract or build report failed; see the specific check above"
python - "$S" <<'PY' || fail "build status is not passed docker"
import json, sys
from pathlib import Path
doc = json.loads(Path(sys.argv[1]).read_text())
build = doc.get("build") or {}
if build.get("status") != "passed" or build.get("mode") != "docker":
    raise SystemExit(1)
if build.get("buildable") is not True or build.get("smoke_test") is not True:
    raise SystemExit(1)
PY
seal_state "$S" /synthesis/state/.integrity/03_environment.sha256
pass "sealed base environment is present and reported as built"
