#!/usr/bin/env bash
set -u

mkdir -p /logs/verifier

fail() {
    printf '%s\n' "${1:-verification failed}" >&2
    printf '0\n' > /logs/verifier/reward.txt
    exit 1
}

pass() {
    printf '%s\n' "${1:-ok}"
    printf '1\n' > /logs/verifier/reward.txt
    exit 0
}

require_file() {
    [ -f "$1" ] || fail "missing file: $1"
}

require_dir() {
    [ -d "$1" ] || fail "missing directory: $1"
}

require_json_keys() {
    require_file "$1"
    python /opt/terminaltraj/scripts/validate_json.py "$@" \
        || fail "invalid JSON contract: $1"
}

seal_state() {
    python /opt/terminaltraj/scripts/state_integrity.py seal "$1" "$2" \
        || fail "could not seal state: $1"
}

verify_state_seal() {
    python /opt/terminaltraj/scripts/state_integrity.py verify "$1" "$2" \
        || fail "state was modified after its handoff: $1"
}

# Require the phase state JSON (and companions) to exist before other checks.
# Phase keys match phase_contract.PHASE_HANDOFFS for the seven-phase pipeline.
require_handoff() {
    python /opt/terminaltraj/scripts/phase_contract.py require-handoff "$1" \
        || fail "missing or incomplete handoff for phase $1"
}

# Harbor library shape check. Do not wrap this in phase_contract.py.
require_harbor_packages() {
    local root="${1:-/synthesis/output/generated_task}"
    python -c "import harbor" 2>/dev/null \
        || fail "factory image is missing Harbor"
    python - "$root" <<'PY' || fail "Harbor TaskPaths/TaskConfig validation failed"
import json
import sys
from pathlib import Path

from harbor.models.task.config import TaskConfig
from harbor.models.task.paths import TaskPaths

try:
    from harbor.models.task.task import Task
except ImportError:
    Task = None

root = Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
errors = []
for item in manifest.get("generated_tasks") or []:
    if not isinstance(item, dict) or not item.get("path"):
        continue
    task_dir = root / str(item["path"])
    paths = TaskPaths(task_dir)
    is_valid = getattr(paths, "is_valid", None)
    if callable(is_valid):
        ok = bool(is_valid())
    elif Task is not None and hasattr(Task, "is_valid_dir"):
        ok = bool(Task.is_valid_dir(task_dir))
    else:
        errors.append(f"{task_dir}: TaskPaths.is_valid unavailable")
        continue
    if not ok:
        errors.append(f"{task_dir}: TaskPaths.is_valid() returned false")
    TaskConfig.model_validate_toml(Path(paths.config_path).read_text(encoding="utf-8"))
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
PY
}

require_json_bool_true() {
    python - "$1" "$2" <<'PY' || fail "expected true: $1.$2"
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get(sys.argv[2]) is not True:
    raise SystemExit(1)
PY
}

require_json_number_range() {
    python - "$1" "$2" <<'PY' || fail "expected [0, 1] number: $1.$2"
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
number = value.get(sys.argv[2])
if not isinstance(number, (int, float)) or not 0 <= number <= 1:
    raise SystemExit(1)
PY
}

require_json_min_number() {
    python - "$1" "$2" "$3" <<'PY' || fail "expected $1.$2 >= $3"
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
number = value.get(sys.argv[2])
minimum = float(sys.argv[3])
if not isinstance(number, (int, float)) or number < minimum:
    raise SystemExit(1)
PY
}
