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
require_handoff 07_verifier_review
S=/synthesis/state/07_verifier_review.json
require_json_keys "$S" reviews approved_candidate_ids
python /opt/terminaltraj/scripts/target_spec.py check-verifier-review \
  /synthesis/state/06_verifier.json "$S" /synthesis/output/candidates \
  || fail "verifier review records do not satisfy the phase 07 contract"
python - "$S" <<'PY' || fail "verifier-review edits reference missing paths"
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for item in d.get("reviews") or []:
    cid = item.get("candidate_id")
    for edit in item.get("edits") or []:
        path = Path(str(edit.get("path") or ""))
        if not path.is_file():
            raise SystemExit(f"missing edit path for {cid}: {path}")
PY
seal_state "$S" /synthesis/state/.integrity/07_verifier_review.sha256
pass "all surviving candidates passed verifier review"
