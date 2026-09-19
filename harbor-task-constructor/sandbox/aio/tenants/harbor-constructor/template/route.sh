#!/usr/bin/env bash
# Mechanical router — prints the role name the agent should enter this iteration.
# Usage: route.sh [--check]
#   --check  print the role and exit 0 (for PROMPT.md)
#   (no arg) print the role and exit 0
#
# All decisions come from tree state only. No model judgment here.
set -euo pipefail

task_root="${SOP_TASK_ROOT:-/home/app/workspace/task}"
evidence_root="${SOP_EVIDENCE_ROOT:-/home/app/workspace/evidence}"
parser="${SOP_PARSER_PATH:-/mnt/template/method/parse_scores.py}"

# task_valid needs tomllib, which is 3.11+. The sandbox's system python3 is
# 3.10, so reading task.toml under it raises ModuleNotFoundError — the check
# then fails closed and every life is misrouted to builder. Fall back to
# python3 for host-side tests, where harbor-python does not exist.
harbor_python="${SOP_HARBOR_PYTHON:-/usr/local/bin/harbor-python}"
[[ -x "$harbor_python" ]] || harbor_python=python3

# ── helpers ──────────────────────────────────────────────────────────────────

has_file()  { [[ -f "$1" ]]; }
has_dir()   { [[ -d "$1" ]]; }

# card.json at evidence root signals attribution is done for the latest round
card="${evidence_root}/card.json"
resume="${evidence_root}/resume.md"

# Latest compact round directory (round-NNNN), if any
latest_round() {
  local dir
  dir=$(find "${evidence_root}" -maxdepth 1 -type d -name 'round-[0-9][0-9][0-9][0-9]' \
        2>/dev/null | sort | tail -1)
  echo "${dir:-}"
}

round_dir=$(latest_round)

# Does a round exist with a round.json (publication complete)?
round_published() {
  [[ -n "${round_dir}" ]] && has_file "${round_dir}/round.json"
}

# Is the latest published round still about the tree as it stands now?
#
# measure.md:88 and refine.md:54 both end by deleting card.json, so the state
# "round published + no card.json" is two different situations wearing the same
# face: measure just produced a fresh round (→ attribute it), or refine just
# edited the task and the round now describes a tree that no longer exists
# (→ measure again). card.json cannot tell them apart. The one fact that can is
# whether the round measured the current tree.
#
# Harbor records the digest it measured in every trial's lock.json, and
# parse_scores.py already reads both sides of the comparison, so this reuses it
# rather than restating the hashing rule. Prints: none | current | stale | unknown
round_state() {
  round_published || { echo "none"; return; }
  "$harbor_python" - "${parser}" "${round_dir}" "${task_root}" 2>/dev/null <<'PY' || echo "unknown"
import importlib.util
import sys
from pathlib import Path

parser_path, round_dir, task_root = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("_route_parse_scores", parser_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

digests = module._all_trial_digests(round_dir)
if len(digests) != 1:
    # No trial locks, or locks that disagree: the round makes no single usable
    # statement about which tree it measured.
    print("unknown")
elif next(iter(digests)) == module.harbor_task_digest(task_root):
    print("current")
else:
    print("stale")
PY
}

# Does card.json exist and have closed=true?
card_closed() {
  has_file "${card}" && \
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get('closed') else 1)" \
    "${card}" 2>/dev/null
}

# Does task.toml pass the mechanical validity checklist?
# (flat task schema, separate environment_mode, /workspace artifact, public network)
task_valid() {
  has_file "${task_root}/task.toml" && \
    "$harbor_python" - "${task_root}/task.toml" <<'PY'
import sys
import tomllib
with open(sys.argv[1], "rb") as fh:
    t = tomllib.load(fh)
# The runner accepts the flat schema and explicitly rejects [[steps]].
if t.get("steps"):
    sys.exit(1)
verifier = t.get("verifier") or {}
if verifier.get("environment_mode") != "separate":
    sys.exit(1)
environment = t.get("environment") or {}
if environment.get("network_mode") != "public":
    sys.exit(1)
if (verifier.get("network_mode") not in (None, "public") or
        (verifier.get("environment") or {}).get("network_mode") not in (None, "public")):
    sys.exit(1)
artifacts = t.get("artifacts") or []
if not any(a.get("source") == "/workspace" for a in artifacts):
    sys.exit(1)
sys.exit(0)
PY
}

# ── routing logic (priority order) ───────────────────────────────────────────
#
# 1. builder   — task.toml absent or mechanically invalid
# 2. builder   — no resume.md (first run)
# 3. measure   — no published round yet
# 4. measure   — latest round measured a different tree (refine edited it)
# 5. analyst   — round current, card.json absent   (attribution not started)
# 6. analyst   — card present, not closed          (attribution in progress)
# 7. refine    — card closed                       (hypothesis selected, edit)
#
# The cycle is measure → analyst → refine → measure. Branch 4 is what closes
# it: refine ends by deleting card.json exactly like measure does, so without a
# staleness test the router cannot see that refine has run, falls through to
# branch 5, and sends the next life to re-attribute the round refine just
# invalidated — analyst → refine → analyst forever, with measure unreachable
# and no new measurement ever produced.

route() {
  if ! task_valid; then
    echo "builder"
    return
  fi
  if ! has_file "${resume}"; then
    echo "builder"
    return
  fi

  local round
  round=$(round_state)
  # "unknown" (a round with no readable trial locks) deliberately does not
  # trigger a measurement: a round costs real fresh budget, so only a round
  # proven to describe a different tree is worth spending it on. An unreadable
  # round routes onward to attribution, where a human-visible role can say so.
  if [[ "${round}" == "none" || "${round}" == "stale" ]]; then
    echo "measure"
    return
  fi
  if ! has_file "${card}"; then
    echo "analyst"
    return
  fi
  if ! card_closed; then
    echo "analyst"
    return
  fi
  echo "refine"
}

route
