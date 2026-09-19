#!/bin/sh
# verify.sh — programmatic delivery gate.
# Called by the runner after .done is written. Exit 0 = verified.
# Checks the four delivery conditions without running any model.
set -eu

task_root="${SOP_TASK_ROOT:-/home/app/workspace/task}"
evidence_root="${SOP_EVIDENCE_ROOT:-/home/app/workspace/evidence}"
parser="${SOP_PARSER_PATH:-/mnt/template/method/parse_scores.py}"

# parse_scores.py imports harbor.publisher.packager, so it needs the venv
# interpreter — the sandbox's plain python3 is 3.10 and cannot import it.
# Fall back to python3 for host-side tests, where harbor-python does not exist.
harbor_python="${SOP_HARBOR_PYTHON:-/usr/local/bin/harbor-python}"
[ -x "${harbor_python}" ] || harbor_python=python3

fail() {
  echo "VERIFY FAIL: $1" >&2
  exit 1
}

# 1. task.toml exists
[ -f "${task_root}/task.toml" ] || fail "task.toml missing"

# 2. resume.md exists
[ -f "${evidence_root}/resume.md" ] || fail "resume.md missing"

# 3. Find the latest compact round and check it has round.json
latest_round=$(find "${evidence_root}" -maxdepth 1 -type d -name 'round-[0-9][0-9][0-9][0-9]' \
               2>/dev/null | sort | tail -1)
[ -n "${latest_round}" ] || fail "no compact round found under ${evidence_root}"
[ -f "${latest_round}/round.json" ] || fail "latest round has no round.json: ${latest_round}"

# 4. Score gates: target_mean < 0.7 and R > 0.2, round matches final task.
#
# These come from parse_scores.py, NOT from round.json. round.json holds only
# {schema_version, kind} (run-two-models.sh:727), and run-two-models.sh:669
# requires exact equality with that two-key form to retain a published real
# source for regrade — so the gate fields cannot simply be added to it. Reading
# them from round.json made this step unsatisfiable by any role, and made it
# report a digest mismatch when the digest in fact matched.
#
# The round directory is passed positionally rather than via --last so the gate
# is evaluated on exactly the round step 3 validated.
report_json=$(mktemp) || fail "cannot create temp file"
trap 'rm -f "${report_json}"' EXIT

"${harbor_python}" "${parser}" "${latest_round}" --final-task "${task_root}" --json \
  > "${report_json}" || fail "parse_scores.py could not read ${latest_round}"

"${harbor_python}" - "${report_json}" "${latest_round}" <<'PY'
import json, sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text())
round_name = Path(sys.argv[2]).name

if report.get("task_matches_final") is not True:
    print("VERIFY FAIL: round task digest does not match final task", file=sys.stderr)
    sys.exit(1)

if not report.get("score_gates", {}).get("all"):
    target_mean = (report.get("arms") or {}).get("target", {}).get("mean")
    print(
        f"VERIFY FAIL: score gates not met "
        f"(target_mean={target_mean}, R={report.get('R')}, "
        f"R_state={report.get('R_state')})",
        file=sys.stderr,
    )
    sys.exit(1)

# R is None when target_mean is 0 and solver_mean is positive — an infinite
# ratio, which clears the gate. Only format it when it is a number.
R = report.get("R")
R_text = f"{R:.3f}" if isinstance(R, (int, float)) else report.get("R_state", "unknown")
print(
    f"verified: target_mean={report['arms']['target']['mean']:.3f} "
    f"R={R_text} round={round_name}"
)
PY
