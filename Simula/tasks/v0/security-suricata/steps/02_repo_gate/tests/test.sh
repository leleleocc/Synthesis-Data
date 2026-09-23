#!/usr/bin/env bash
set -u
source /tests/helpers.sh
verify_state_seal /synthesis/state/01_repo_profile.json \
  /synthesis/state/.integrity/01_repo_profile.sha256
require_handoff 02_repo_gate
S=/synthesis/state/02_repo_gate.json
require_json_keys "$S" \
  accepted hard_checks blockers \
  repo_score buildability_score task_potential_score decision
require_json_number_range "$S" repo_score
require_json_number_range "$S" buildability_score
require_json_number_range "$S" task_potential_score
python /opt/terminaltraj/scripts/target_spec.py check-repo-gate \
  /synthesis/input/target_spec.json "$S" \
  || fail "repo gate hard_checks or score threshold failed"
require_json_bool_true "$S" accepted
python - "$S" <<'PY' || fail "score decision is not accept"
import json, sys
from pathlib import Path
if json.loads(Path(sys.argv[1]).read_text())["decision"] != "accept":
    raise SystemExit(1)
PY
seal_state "$S" /synthesis/state/.integrity/02_repo_gate.sha256
pass "repository passed the combined filter and score gate"
