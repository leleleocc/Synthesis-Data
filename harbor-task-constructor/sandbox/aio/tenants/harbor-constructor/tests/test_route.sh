#!/usr/bin/env bash
# Tests for route.sh — exercises all 7 routing branches.
# Usage: bash tests/test_route.sh
# Exits 0 if all pass, nonzero otherwise.
set -euo pipefail

TEMPLATE_DIR="$(cd "$(dirname "$0")/.." && pwd)/template"
ROUTE="${TEMPLATE_DIR}/route.sh"

pass=0
fail=0

# Empty means "no parser": route.sh then falls back to its /mnt/template path,
# which does not exist on the host, so round_state reports "unknown". Tests that
# care about staleness point this at a stub instead.
parser_env=""

check() {
  local name="$1" expected="$2"
  local got
  got=$(SOP_TASK_ROOT="${task}" SOP_EVIDENCE_ROOT="${evidence}" \
        SOP_PARSER_PATH="${parser_env}" \
        bash "${ROUTE}" 2>/dev/null)
  if [[ "${got}" == "${expected}" ]]; then
    echo "  PASS  ${name}"
    (( pass++ )) || true
  else
    echo "  FAIL  ${name}: expected '${expected}', got '${got}'"
    (( fail++ )) || true
  fi
}

# Set up scratch area
tmp=$(mktemp -d)
cleanup() { rm -rf "${tmp}"; }
trap cleanup EXIT

task="${tmp}/task"
evidence="${tmp}/evidence"

# helper: write a valid task.toml
write_valid_toml() {
  mkdir -p "${task}"
  cat > "${task}/task.toml" <<'TOML'
[verifier]
environment_mode = "separate"
[environment]
network_mode = "public"
[[artifacts]]
source = "/workspace"
TOML
}

# helper: write a round.json into the latest round dir
write_round() {
  local round_dir="${evidence}/round-0001"
  mkdir -p "${round_dir}"
  echo '{}' > "${round_dir}/round.json"
}

# helper: write card.json
write_card() {
  local closed="${1:-false}"
  cat > "${evidence}/card.json" <<JSON
{"closed": ${closed}}
JSON
}

# ── test 1: no task.toml → builder ───────────────────────────────────────────
rm -rf "${task}" "${evidence}"
mkdir -p "${task}" "${evidence}"
check "no task.toml → builder" "builder"

# ── test 2: invalid task.toml → builder ──────────────────────────────────────
mkdir -p "${task}"
echo '[steps]' > "${task}/task.toml"   # missing required fields
check "invalid task.toml → builder" "builder"

# ── test 3: valid toml, no resume.md → builder ───────────────────────────────
rm -rf "${task}" "${evidence}"
mkdir -p "${evidence}"
write_valid_toml
check "valid toml, no resume.md → builder" "builder"

# ── test 4: valid toml + resume.md, no round → measure ───────────────────────
touch "${evidence}/resume.md"
check "no round yet → measure" "measure"

# ── test 5: round published, no card.json → analyst ──────────────────────────
write_round
check "round published, no card → analyst" "analyst"

# ── test 6: card.json present, closed=false → analyst ────────────────────────
write_card false
check "card not closed → analyst" "analyst"

# ── test 7: card.json present, closed=true → refine ──────────────────────────
write_card true
check "card closed → refine" "refine"

# ── staleness (branch 4) ─────────────────────────────────────────────────────
#
# The real comparison needs harbor (Packager.compute_content_hash), which is not
# on the host. A stub parser supplies the two functions route.sh calls, so these
# test the router's own logic rather than harbor's hashing.
stub="${tmp}/stub_parse_scores.py"
cat > "${stub}" <<'PY'
"""Stand-in for parse_scores.py: the digest of a tree is the bytes of DIGEST."""
from pathlib import Path


def _all_trial_digests(round_dir):
    return {p.read_text().strip() for p in Path(round_dir).rglob("task__*/DIGEST")}


def harbor_task_digest(task_root):
    return (Path(task_root) / "DIGEST").read_text().strip()
PY
parser_env="${stub}"

# A round whose trials recorded the same tree the task now has.
mkdir -p "${evidence}/round-0001/job/task__abc"
echo "sha256:aaa" > "${task}/DIGEST"
echo "sha256:aaa" > "${evidence}/round-0001/job/task__abc/DIGEST"

rm -f "${evidence}/card.json"
check "round current, no card → analyst" "analyst"

write_card true
check "round current, card closed → refine" "refine"

# refine edits the tree: the round now describes something that no longer
# exists, so the next life must measure rather than re-attribute it — even
# though card.json is absent exactly as it is after measure.
echo "sha256:bbb" > "${task}/DIGEST"
rm -f "${evidence}/card.json"
check "round stale, no card → measure" "measure"

# Staleness outranks a closed card: there is nothing worth refining against a
# round that measured a different tree.
write_card true
check "round stale, card closed → measure" "measure"

# A round with no trial locks says nothing about which tree it measured.
# Unknown must not spend fresh budget on a guess.
rm -rf "${evidence}/round-0001/job/task__abc"
rm -f "${evidence}/card.json"
check "round unknown, no card → analyst" "analyst"

echo ""
echo "Results: ${pass} passed, ${fail} failed"
[[ "${fail}" -eq 0 ]]
