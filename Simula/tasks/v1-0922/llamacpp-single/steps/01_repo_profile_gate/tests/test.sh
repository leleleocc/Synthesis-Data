#!/usr/bin/env bash
set -u
source /tests/helpers.sh

require_file /synthesis/input/target_spec.json
require_handoff 01_repo_profile_gate
S=/synthesis/state/01_repo_profile_gate.json
require_json_keys "$S" \
  checkout languages domains subdomains entrypoints tags \
  evidence license executable deployment_support \
  hard_checks blockers \
  repo_score buildability_score task_potential_score decision
require_json_number_range "$S" repo_score
require_json_number_range "$S" buildability_score
require_json_number_range "$S" task_potential_score

python - "$S" /synthesis/input/target_spec.json <<'PY' || fail "profile gate handoff has forbidden repository fields"
import json
import sys
from pathlib import Path

profile = json.loads(Path(sys.argv[1]).read_text())
spec = json.loads(Path(sys.argv[2]).read_text())
if "source_repo" in profile:
    raise SystemExit("profile.source_repo was removed; checkout.head is the pin")
if "target_alignment" in profile:
    raise SystemExit("profile.target_alignment was removed; use hard_checks.target_alignment")
if "accepted" in profile:
    raise SystemExit("profile.accepted was removed; use decision")
if any(key in profile for key in ("oracle_types", "oracle_type", "task_types", "supported_task_types")):
    raise SystemExit("profile must not contain task or oracle selection fields")
target_source = spec.get("source_repo")
if not isinstance(target_source, dict) or "path" in target_source:
    raise SystemExit("target_spec source_repo must use URL and commit only")
if "path" in target_source:
    raise SystemExit("source_repo.path is forbidden")
checkout = profile.get("checkout")
if not isinstance(checkout, dict) or checkout.get("verified") is not True:
    raise SystemExit("checkout.verified must prove the pinned checkout succeeded")
if checkout.get("head") != target_source.get("commit"):
    raise SystemExit("checkout.head must equal the pinned commit")
license_doc = profile.get("license")
if isinstance(license_doc, dict) and "files" in license_doc:
    raise SystemExit("license.files was removed; use evidence.license_files")
executable = profile.get("executable")
if isinstance(executable, dict) and "entrypoints" in executable:
    raise SystemExit("executable.entrypoints was removed; use entrypoints")
PY

python /opt/terminaltraj/scripts/phase_contract.py validate \
  /synthesis/input/target_spec.json \
  || fail "target_spec.json is invalid"
python /opt/terminaltraj/scripts/phase_contract.py check-repo-profile-gate \
  /synthesis/input/target_spec.json "$S" \
  || fail "repository profile or gate contract failed"

seal_state "$S" /synthesis/state/.integrity/01_repo_profile_gate.sha256
python - "$S" <<'PY' || fail "repository rejected; stopping synthesis"
import json
import sys
from pathlib import Path

raise SystemExit(0 if json.loads(Path(sys.argv[1]).read_text())["decision"] == "accept" else 1)
PY
pass "repository profile and gate are present"
