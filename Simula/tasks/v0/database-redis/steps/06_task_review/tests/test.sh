#!/usr/bin/env bash
set -u
source /tests/helpers.sh
for state in \
  01_repo_profile \
  02_repo_gate \
  03_environment \
  04_simula_plan \
  05_task_design; do
  verify_state_seal "/synthesis/state/$state.json" \
    "/synthesis/state/.integrity/$state.sha256"
done
require_handoff 06_task_review
S=/synthesis/state/06_task_review.json
require_json_keys "$S" reviews approved_candidate_ids
python /opt/terminaltraj/scripts/target_spec.py check-review \
  /synthesis/input/target_spec.json \
  /synthesis/state/05_task_design.json "$S" \
  /synthesis/output/candidates \
  || fail "candidate reviews are incomplete or inconsistent"
for id in $(python -c 'import json; print("\n".join(json.load(open("/synthesis/state/06_task_review.json"))["approved_candidate_ids"]))'); do
  path="/synthesis/output/candidates/$id/instruction.md"
  require_file "$path"
  [ -s "$path" ] || fail "empty candidate instruction: $id"
  require_file "/synthesis/output/candidates/$id/task.toml"
done
# Minimal-fix reviews may edit instruction.md / task.toml / overlay; require listed paths exist.
python - "$S" <<'PY' || fail "review edits reference missing paths"
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
seal_state "$S" /synthesis/state/.integrity/06_task_review.sha256
pass "all approved candidate tasks passed review"
