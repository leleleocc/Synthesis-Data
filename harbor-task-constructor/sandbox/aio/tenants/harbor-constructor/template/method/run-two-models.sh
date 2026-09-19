#!/usr/bin/env bash
# Run concurrent Harbor arms with life-local sources and compact collected evidence.
set -euo pipefail

task_root="${SOP_TASK_ROOT:-/home/app/workspace/task}"
evidence_root="${SOP_EVIDENCE_ROOT:-/home/app/workspace/evidence}"
parser_path="${SOP_PARSER_PATH:-$(dirname "$0")/parse_scores.py}"
harbor_python="${SOP_HARBOR_PYTHON:-/usr/local/bin/harbor-python}"
attempts=2
attempts_supplied=0
concurrency=1
concurrency_supplied=0
round_number=""
mode="${1:-}"
declare -a arms=()
declare -a child_pids=()
declare -a child_runs=()
declare -a arm_run_dirs=()
credential_dir=""
allocation_lock_dir=""
allocation_lock_owner=""
allocation_lock_token=""
created_evidence_root=0
invocation_launched=0
publication_attempted=0
publication_succeeded=0

usage() {
  echo "usage: $0 {both|target|solver|regrade} [--round N] [--attempts N] [--concurrency N]" >&2
}

print_help() {
  cat <<EOF
Usage: $0 {both|target|solver|regrade} [options]

Modes:
  both                 Run target and solver concurrently in one round.
  target               Run only the target arm.
  solver               Run only the solver arm.
  regrade              Validate the latest real rollout for both arms.

Options:
  --round N            Append the selected arm run(s) to round-NNNN.
  --attempts N         Set Harbor attempts for each selected arm (default: 2).
  --concurrency N      Set Harbor concurrency for each selected arm (default: 2 for fresh runs, 1 for regrade).
  -h, --help           Show this help and exit.

Harbor always receives --max-retries 0; there is no retry option.

Environment required for every run:
  DAYTONA_API_KEY
  HARBOR_JUDGE_BASE_URL
  HARBOR_JUDGE_AUTH_TOKEN

Required bundle for each selected arm:
  Target bundle (required for both or target)
  HARBOR_TARGET_MODEL_NAME
  HARBOR_TARGET_BASE_URL
  HARBOR_TARGET_AUTH_TOKEN

  Solver bundle (required for both or solver)
  HARBOR_SOLVER_MODEL_NAME
  HARBOR_SOLVER_BASE_URL
  HARBOR_SOLVER_AUTH_TOKEN

Optional for each selected arm:
  HARBOR_TARGET_REASONING_EFFORT (both or target)
  HARBOR_SOLVER_REASONING_EFFORT (both or solver)
  Each arm's reasoning effort is optional.

Regrade uses no model bundle and rejects --round and --attempts. It validates
the latest real rollout before allocating or invoking Harbor.

Evidence:
  Without --round, the runner allocates the next numbered round.
  With --round, it appends new run numbers to an existing round; existing
  rollout identities must match the current task before anything is appended.
  Layout: round-NNNN/{target,solver}/run-NNNN/{jobs,harbor.log,exit-code}
  The runner does not write run.json or score.json.
  Full jobs and rollout.lock remain in the current-life runtime root.
  The collected root contains compact jobs, logs, exit codes, and round.json.
  Parser output is display-only; exit status is the Harbor child status
  unless compact publication fails, which also returns nonzero.
EOF
}

write_active_runs_for_test() {
  local run
  [[ -n "${SOP_TEST_ACTIVE_RUNS_PATH:-}" ]] || return 0
  : > "$SOP_TEST_ACTIVE_RUNS_PATH"
  for run in "${child_runs[@]:-}"; do
    [[ -n "$run" ]] && printf '%s\n' "$run" >> "$SOP_TEST_ACTIVE_RUNS_PATH"
  done
  return 0
}

cleanup_children() {
  local index pid child_status
  for pid in "${child_pids[@]:-}"; do
    [[ -n "$pid" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  for index in "${!child_pids[@]}"; do
    pid="${child_pids[$index]}"
    [[ -n "$pid" ]] || continue
    if wait "$pid"; then
      child_status=0
    else
      child_status=$?
    fi
    printf '%s\n' "$child_status" > "${child_runs[$index]}/exit-code"
  done
  child_pids=()
  child_runs=()
  write_active_runs_for_test
}

release_allocation_lock() {
  local recorded_owner
  [[ -n "$allocation_lock_token" && -n "$allocation_lock_owner" ]] || return 0
  [[ -f "$allocation_lock_owner" ]] || return 0
  IFS= read -r recorded_owner < "$allocation_lock_owner" || return 0
  [[ "$recorded_owner" == "$allocation_lock_token" ]] || return 0
  rm -f -- "$allocation_lock_owner"
  rmdir -- "$allocation_lock_dir" 2>/dev/null || true
  allocation_lock_dir=""
  allocation_lock_owner=""
  allocation_lock_token=""
}

measuring_marker="/home/app/workspace/.measuring"

raise_measuring() {
  if [[ "$mode" != "regrade" ]]; then
    : > "$measuring_marker"
  fi
}

lower_measuring() {
  rm -f -- "$measuring_marker"
}

cleanup() {
  cleanup_children
  if [[ "$invocation_launched" == 1 && "$publication_attempted" == 0 ]]; then
    publish_current_round || true
  fi
  # A signal may run before the shell records write-round's successful exit.
  # A regrade owns a newly allocated round, so its atomic marker also proves
  # that every run published, including in that narrow interruption window.
  if [[ "$mode" == "regrade" && "$publication_attempted" == 1 && -f "${round_dir:-}/round.json" ]]; then
    publication_succeeded=1
  fi
  release_allocation_lock
  if [[ "$created_evidence_root" == 1 ]]; then
    rmdir -- "$evidence_root" 2>/dev/null || true
  fi
  if [[ -n "$credential_dir" && -d "$credential_dir" ]]; then
    rm -rf "$credential_dir"
  fi
  lower_measuring
}

on_signal() {
  cleanup_children
  exit 143
}

trap cleanup EXIT
trap on_signal INT TERM

case "${1:-}" in
  -h|--help)
    print_help
    exit 0
    ;;
esac

if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi
shift
case "$mode" in
  both) arms=(target solver) ;;
  target|solver) arms=("$mode") ;;
  regrade) arms=(target solver) ;;
  *)
    echo "invalid mode: $mode (expected both, target, solver, or regrade)" >&2
    exit 2
    ;;
esac

is_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --round|--attempts|--concurrency)
      if [[ $# -lt 2 ]]; then
        echo "missing value for $1" >&2
        exit 2
      fi
      case "$1" in
        --round) round_number="$2" ;;
        --attempts) attempts="$2"; attempts_supplied=1 ;;
        --concurrency) concurrency="$2"; concurrency_supplied=1 ;;
      esac
      shift 2
      ;;
    --max-retries)
      echo "--max-retries is fixed at 0 by this runner and cannot be supplied" >&2
      exit 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ "$mode" == "regrade" ]]; then
  if [[ "$attempts_supplied" == 1 ]]; then
    echo "--attempts cannot be supplied for regrade" >&2
    exit 2
  fi
  if [[ -n "$round_number" ]]; then
    echo "--round cannot be supplied for regrade" >&2
    exit 2
  fi
elif [[ "$concurrency_supplied" == 0 ]]; then
  concurrency=2
fi

if ! is_positive_integer "$attempts" || ! is_positive_integer "$concurrency"; then
  echo "--attempts and --concurrency must be positive integers" >&2
  exit 2
fi
if [[ -n "$round_number" ]] && (! is_positive_integer "$round_number" || (( 10#$round_number > 9999 ))); then
  echo "--round must be a number from 1 through 9999" >&2
  exit 2
fi

declare -a missing=()
require_value() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
}

require_value DAYTONA_API_KEY
require_value HARBOR_JUDGE_BASE_URL
require_value HARBOR_JUDGE_AUTH_TOKEN
if [[ "$mode" != "regrade" ]]; then
  for arm in "${arms[@]}"; do
    upper="$(printf '%s' "$arm" | tr '[:lower:]' '[:upper:]')"
    require_value "HARBOR_${upper}_MODEL_NAME"
    require_value "HARBOR_${upper}_BASE_URL"
    require_value "HARBOR_${upper}_AUTH_TOKEN"
  done
fi
if (( ${#missing[@]} )); then
  printf 'missing required environment variables: %s\n' "${missing[*]}" >&2
  exit 2
fi

next_number() {
  local parent="$1" prefix="$2" candidate number largest=0
  shopt -s nullglob
  for candidate in "$parent"/"$prefix"[0-9][0-9][0-9][0-9]; do
    [[ -d "$candidate" ]] || continue
    number="${candidate##*/$prefix}"
    (( 10#$number > largest )) && largest=$((10#$number))
  done
  shopt -u nullglob
  if (( largest >= 9999 )); then
    echo "numbering exhausted for $prefix directories under $parent" >&2
    return 1
  fi
  printf '%04d' "$((largest + 1))"
}

allocation_barrier_for_test() {
  local barrier_dir
  barrier_dir="${SOP_TEST_ALLOCATION_BARRIER_DIR:-}"
  [[ -n "$barrier_dir" ]] || return 0
  : > "$barrier_dir/ready-$$"
  while [[ ! -e "$barrier_dir/release" ]]; do
    sleep 0.01
  done
}

acquire_allocation_lock() {
  allocation_lock_dir="$evidence_root/.allocation.lock"
  allocation_lock_owner="$allocation_lock_dir/owner"
  allocation_lock_token="$$-${RANDOM}-${RANDOM}"
  if mkdir "$allocation_lock_dir" 2>/dev/null; then
    if printf '%s\n' "$allocation_lock_token" > "$allocation_lock_owner"; then
      return 0
    fi
    rmdir -- "$allocation_lock_dir" 2>/dev/null || true
  fi
  allocation_lock_dir=""
  allocation_lock_owner=""
  allocation_lock_token=""
  echo "another two-model invocation is active: $evidence_root/.allocation.lock" >&2
  return 1
}

claim_next_directory() {
  local parent="$1" prefix="$2" number candidate
  number="$(next_number "$parent" "$prefix")" || return 1
  while (( 10#$number <= 9999 )); do
    candidate="$parent/$prefix$number"
    if mkdir "$candidate" 2>/dev/null; then
      printf '%s\n' "$candidate"
      return 0
    fi
    if [[ -e "$candidate" ]]; then
      if (( 10#$number == 9999 )); then
        echo "numbering exhausted for $prefix directories under $parent" >&2
        return 1
      fi
      printf -v number '%04d' "$((10#$number + 1))"
      continue
    fi
    echo "cannot claim $candidate" >&2
    return 1
  done
  echo "numbering exhausted for $prefix directories under $parent" >&2
  return 1
}

host_from_url() {
  "$harbor_python" - "$1" <<'PY'
from urllib.parse import urlparse
import sys

host = urlparse(sys.argv[1]).hostname
if not host:
    raise SystemExit("model base URL has no hostname")
print(host)
PY
}

task_state_json() {
  "$harbor_python" - "$1" <<'PY'
import hashlib
import json
import stat
import sys
from pathlib import Path, PurePosixPath

from harbor.constants import MAIN_SERVICE_NAME
from harbor.environments.definition import has_agent_environment_definition
from harbor.models.task.artifacts import effective_artifact_service, normalize_artifact_entries, source_relative_path
from harbor.models.task.config import NetworkMode, TaskConfig, VerifierEnvironmentMode
from harbor.models.task.verifier_mode import resolve_effective_verifier_env_config
from harbor.publisher.packager import Packager


def fail(message: str) -> None:
    raise SystemExit(f"task is not regrade-ready: {message}")


def overlaps(first: str, second: str) -> bool:
    first_path = PurePosixPath(first.rstrip("/") or "/")
    second_path = PurePosixPath(second.rstrip("/") or "/")
    return first_path == second_path or first_path in second_path.parents or second_path in first_path.parents


root = Path(sys.argv[1]).resolve()
try:
    config = TaskConfig.model_validate_toml((root / "task.toml").read_text(encoding="utf-8"))
except Exception as exc:
    fail(f"cannot read task.toml: {exc}")

if config.steps:
    fail("does not support [[steps]]")
if config.verifier.environment_mode != VerifierEnvironmentMode.SEPARATE:
    fail(
        'requires explicit [verifier].environment_mode = "separate"\n'
        "Next action: make the task regrade-ready, validate nop/oracle, then run "
        "/mnt/template/method/run-two-models.sh both to create a reusable real rollout. "
        "Use regrade only for later verifier-loop changes under tests/ or solution/."
    )
effective_verifier_env = resolve_effective_verifier_env_config(config, None)
if (
    effective_verifier_env is None
    or not has_agent_environment_definition(
        root / "tests", docker_image=effective_verifier_env.docker_image
    )
):
    fail("requires a separate verifier environment definition in tests/")
if config.environment.network_mode != NetworkMode.PUBLIC:
    fail("requires [environment].network_mode = public")
if config.agent.network_mode not in (None, NetworkMode.PUBLIC):
    fail("requires [agent].network_mode to be public when set")
if config.verifier.network_mode not in (None, NetworkMode.PUBLIC):
    fail("requires [verifier].network_mode to be public when set")
if (
    config.verifier.environment is not None
    and config.verifier.environment.network_mode != NetworkMode.PUBLIC
):
    fail("requires [verifier.environment].network_mode to be public when set")

artifacts = normalize_artifact_entries(config.artifacts)
workspace_entries = [
    artifact
    for artifact in artifacts
    if effective_artifact_service(artifact) == MAIN_SERVICE_NAME
    and artifact.source.rstrip("/") == "/workspace"
]
if len(workspace_entries) != 1:
    fail("requires exactly one main-service /workspace artifact")
workspace_artifact = workspace_entries[0]
if workspace_artifact.destination is not None or workspace_artifact.exclude:
    fail("requires a workspace artifact without exclusions or destination")
for artifact in artifacts:
    if artifact is not workspace_artifact and overlaps(artifact.source, "/workspace"):
        fail("rejects another artifact whose source overlaps /workspace")
    host_destination = artifact.destination or source_relative_path(artifact.source).as_posix()
    if artifact is not workspace_artifact and overlaps(host_destination, "workspace"):
        fail("rejects an artifact destination that overlaps workspace")

task_digest, _ = Packager.compute_content_hash(root)
files = {
    path.relative_to(root).as_posix(): path
    for path in Packager.collect_files(root)
    if path.relative_to(root).parts[0] not in {"tests", "solution"}
}
gitignore = root / ".gitignore"
if gitignore.is_file():
    files[".gitignore"] = gitignore
rollout_input = hashlib.sha256()
for relative in sorted(files):
    path = files[relative]
    executable = "1" if stat.S_IMODE(path.stat().st_mode) & 0o111 else "0"
    file_digest = Packager.compute_file_hash(path)
    rollout_input.update(f"{relative}\0{executable}\0{file_digest}\n".encode())

task_name = config.task.name if config.task is not None else root.name
print(json.dumps({
    "task_name": task_name,
    "task_digest": f"sha256:{task_digest}",
    "rollout_input_digest": f"sha256:{rollout_input.hexdigest()}",
}, sort_keys=True))
PY
}

write_rollout_lock() {
  "$harbor_python" - "$1" "$2" "$3" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

round_dir = Path(sys.argv[1])
lock = round_dir / "rollout.lock"
payload = {
    "schema_version": 2,
    "task_digest": sys.argv[2],
    "rollout_input_digest": sys.argv[3],
}
fd, temporary = tempfile.mkstemp(prefix=".rollout.lock.", dir=round_dir)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, lock)
except BaseException:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
    raise
PY
}

rollout_lock_matches() {
  "$harbor_python" - "$1" "$2" "$3" <<'PY'
import json
import sys
from pathlib import Path

try:
    lock = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
expected = {"schema_version", "task_digest", "rollout_input_digest"}
if (
    not isinstance(lock, dict)
    or set(lock) != expected
    or type(lock["schema_version"]) is not int
    or lock["schema_version"] != 2
):
    raise SystemExit(1)
if lock.get("task_digest") != sys.argv[2] or lock.get("rollout_input_digest") != sys.argv[3]:
    raise SystemExit(1)
PY
}

regrade_sources_json() {
  "$harbor_python" - "$1" "$2" "$3" "${4:-strict}" <<'PY'
import json
import re
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"regrade source is unusable: {message}")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read {path}: {exc}")


def numbered_children(parent: Path, prefix: str) -> list[Path]:
    expression = re.compile(rf"^{re.escape(prefix)}[0-9]{{4}}$")
    if not parent.is_dir():
        return []
    return [item for item in parent.iterdir() if item.is_dir() and expression.fullmatch(item.name)]


def workspace_entry(manifest):
    if not isinstance(manifest, list):
        return None
    for entry in manifest:
        if (
            isinstance(entry, dict)
            and entry.get("source") == "/workspace"
            and entry.get("destination") == "artifacts/workspace"
            and entry.get("type") == "directory"
            and "service" in entry
            and entry["service"] is None
        ):
            return entry
    return None


def replayable_job(job: Path, task_name: str | None, marker_digest: str) -> bool:
    trials = sorted(path for path in job.rglob("task__*") if path.is_dir())
    found = False
    for trial in trials:
        try:
            result = json.loads((trial / "result.json").read_text(encoding="utf-8"))
            lock = json.loads((trial / "lock.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(result, dict) or not isinstance(lock, dict):
            continue
        same_name = task_name is None or result.get("task_name") == task_name
        digest = lock.get("task", {}).get("digest") if isinstance(lock.get("task"), dict) else None
        try:
            manifest = json.loads((trial / "artifacts" / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = None
        entry = workspace_entry(manifest)
        if same_name and entry is not None and digest != marker_digest:
            fail(f"workspace-bearing trial digest does not match rollout marker: {trial}")
        if not same_name or digest != marker_digest or entry is None:
            continue
        status = entry.get("status")
        if status not in {"ok", "empty"}:
            continue
        if status == "ok" and not (trial / "artifacts" / "workspace").is_dir():
            continue
        found = True
    return found


def source_job(round_dir: Path, arm: str, task_name: str | None, marker_digest: str) -> Path:
    runs = numbered_children(round_dir / arm, "run-")
    if not runs:
        fail(f"missing {arm} run under {round_dir}")
    run = max(runs, key=lambda item: item.name)
    return run_source_job(run, arm, task_name, marker_digest)


def run_source_job(run: Path, arm: str, task_name: str | None, marker_digest: str) -> Path:
    exit_code_path = run / "exit-code"
    try:
        exit_code = exit_code_path.read_text(encoding="utf-8").strip()
    except OSError:
        fail(f"missing exit-code for {arm} run: {run}")
    if not exit_code.isdecimal():
        fail(f"exit-code is not numeric for {arm} run: {run}")
    jobs_dir = run / "jobs"
    jobs = [item for item in jobs_dir.iterdir() if item.is_dir()] if jobs_dir.is_dir() else []
    if len(jobs) != 1:
        fail(f"expected exactly one immediate job for {arm} run {run}, found {len(jobs)}")
    job = jobs[0]
    config = read_json(job / "config.json")
    result = read_json(job / "result.json")
    if not isinstance(config, dict) or not isinstance(result, dict):
        fail(f"job metadata is malformed: {job}")
    if not replayable_job(job, task_name, marker_digest):
        fail(f"no replayable trial for {arm} job: {job}")
    return job.resolve()


def require_published_job(job: Path) -> None:
    if (job.parent.parent / "exit-code").read_text().strip() != "0":
        fail("real round has a failed arm")
    collected_job = collected_root / job.relative_to(evidence_root.resolve())
    for name in ("config.json", "result.json"):
        if read_json(collected_job / name) != read_json(job / name):
            fail("published job metadata differs from runtime source")


def retained_source_job(round_dir: Path, arm: str, task_name: str | None, marker_digest: str) -> Path:
    # Remember a pair that actually completed together. Combining arbitrary
    # historical successes could promote a round that was never complete.
    checkpoint = round_dir / ".complete-runs.json"
    if not checkpoint.exists():
        # Existing runtime rounds without a checkpoint must still have valid
        # latest runs before they can become a retained complete source.
        return source_job(round_dir, arm, task_name, marker_digest)
    runs = read_json(checkpoint)
    if (
        not isinstance(runs, dict)
        or set(runs) != {"target", "solver"}
        or any(not isinstance(run, str) or not re.fullmatch(r"run-[0-9]{4}", run) for run in runs.values())
    ):
        fail(f"invalid completed-run checkpoint: {checkpoint}")
    return run_source_job(round_dir / arm / runs[arm], arm, task_name, marker_digest)


evidence_root = Path(sys.argv[1])
task_name = sys.argv[2]
rollout_input_digest = sys.argv[3]
selection = sys.argv[4]
collected_root = evidence_root
rounds = [round_dir for round_dir in numbered_children(evidence_root, "round-") if (round_dir / "rollout.lock").is_file()]
if not rounds and selection == "strict":
    fail(
        "no current-life rollout source exists; run run-two-models.sh both first\n"
        "Next action: run /mnt/template/method/run-two-models.sh both to create a reusable "
        "real rollout. Use regrade only for later verifier-loop changes under tests/ or solution/."
    )
for round_dir in sorted(rounds, key=lambda item: item.name, reverse=True):
    try:
        marker = read_json(round_dir / "rollout.lock")
        expected = {"schema_version", "task_digest", "rollout_input_digest"}
        if (
            not isinstance(marker, dict)
            or set(marker) != expected
            or type(marker.get("schema_version")) is not int
            or marker["schema_version"] != 2
            or not isinstance(marker.get("task_digest"), str)
            or not isinstance(marker.get("rollout_input_digest"), str)
        ):
            fail(f"invalid rollout.lock: {round_dir / 'rollout.lock'}")
        if selection == "strict" and marker["rollout_input_digest"] != rollout_input_digest:
            fail("current rollout input identity does not match latest rollout")
        # A replacement must be usable for the current task. An older source
        # may belong to the task identity from before the current edits.
        source_task_name = (
            task_name
            if selection == "strict" or marker["rollout_input_digest"] == rollout_input_digest
            else None
        )
        select_job = retained_source_job if selection == "retained" else source_job
        target = select_job(round_dir, "target", source_task_name, marker["task_digest"])
        solver = select_job(round_dir, "solver", source_task_name, marker["task_digest"])
        if selection != "strict":
            # Retention preserves a published, successful real source even
            # when the next real measurement changes the rollout inputs.
            metadata = read_json(collected_root / round_dir.name / "round.json")
            if metadata != {"schema_version": 1, "kind": "real"}:
                fail("real round has not published")
            for job in (target, solver):
                require_published_job(job)
        print(json.dumps({"source_round": str(round_dir.resolve()), "target": str(target), "solver": str(solver)}, sort_keys=True))
        break
    except (SystemExit, OSError):
        if selection == "strict":
            raise
else:
    print("{}")
PY
}

json_source_round() {
  "$harbor_python" -c 'import json,sys; print(json.loads(sys.argv[1]).get("source_round", ""))' "$1"
}

remember_complete_source() {
  "$harbor_python" - "$1" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

source = json.loads(sys.argv[1])
round_dir = Path(source["source_round"])
runs = {arm: Path(source[arm]).parent.parent.name for arm in ("target", "solver")}
descriptor, temporary = tempfile.mkstemp(prefix=".complete-runs.", dir=round_dir)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(runs, output)
        output.write("\n")
    os.replace(temporary, round_dir / ".complete-runs.json")
finally:
    Path(temporary).unlink(missing_ok=True)
PY
}

publish_current_round() {
  local source_round_name="" source_round_arg=""
  publication_attempted=1
  if [[ "$mode" == "regrade" ]]; then
    source_round_name="${source_round##*/}"
    source_round_arg="$source_round_name"
  fi
  "$harbor_python" - "$round_dir" "$round_kind" "$source_round_arg" <<'PY' || return 1
import json
import os
import sys
import tempfile
from pathlib import Path

round_dir = Path(sys.argv[1])
kind = sys.argv[2]
source_round_name = sys.argv[3]

payload = {"schema_version": 1, "kind": kind}
if source_round_name:
    payload["source_round"] = source_round_name

fd, tmp = tempfile.mkstemp(prefix=".round.", dir=round_dir)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
        fh.write("\n")
    os.replace(tmp, round_dir / "round.json")
except BaseException:
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    raise
PY
  publication_succeeded=1
}

# One owner spans source preflight, allocation, children, publication,
# retention, and display. Child Harbor processes still execute concurrently.
if [[ ! -d "$evidence_root" ]]; then
  mkdir -p "$evidence_root"
  created_evidence_root=1
fi
acquire_allocation_lock || exit 1

declare -a arm_models=()
declare -a arm_base_urls=()
declare -a arm_efforts=()
declare -a arm_hosts=()
if [[ "$mode" != "regrade" ]]; then
  for arm in "${arms[@]}"; do
    upper="$(printf '%s' "$arm" | tr '[:lower:]' '[:upper:]')"
    model_name="HARBOR_${upper}_MODEL_NAME"
    base_url_name="HARBOR_${upper}_BASE_URL"
    effort_name="HARBOR_${upper}_REASONING_EFFORT"
    arm_models+=("${!model_name}")
    arm_base_urls+=("${!base_url_name}")
    arm_efforts+=("${!effort_name:-}")
    arm_hosts+=("$(host_from_url "${!base_url_name}")")
  done
fi

task_state="$(task_state_json "$task_root")"
task_name="$("$harbor_python" - "$task_state" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["task_name"])
PY
)"
task_digest="$("$harbor_python" - "$task_state" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["task_digest"])
PY
)"
rollout_input_digest="$("$harbor_python" - "$task_state" <<'PY'
import json
import sys
print(json.loads(sys.argv[1])["rollout_input_digest"])
PY
)"

declare -a regrade_sources=()
source_round=""
round_kind="real"
if [[ "$mode" == "regrade" ]]; then
  round_kind="regrade"
  regrade_source_json="$(regrade_sources_json "$evidence_root" "$task_name" "$rollout_input_digest")"
  source_round="$(json_source_round "$regrade_source_json")"
  while IFS= read -r source_job; do
    regrade_sources+=("$source_job")
  done < <("$harbor_python" - "$regrade_source_json" <<'PY'
import json
import sys

sources = json.loads(sys.argv[1])
for arm in ("target", "solver"):
    print(sources[arm])
PY
)
fi

previous_source_json="$(regrade_sources_json "$evidence_root" "$task_name" "$rollout_input_digest" retained)"
previous_source_round="$(json_source_round "$previous_source_json")"
if [[ -n "$previous_source_round" ]]; then
  remember_complete_source "$previous_source_json"
fi

if [[ "$mode" != "regrade" ]]; then
  credential_dir="$(mktemp -d "${TMPDIR:-/tmp}/sop-two-models.XXXXXX")"
  chmod 700 "$credential_dir"
fi

declare -a claimed_arm_runs=()
declare -a created_arm_roots=()
claimed_round_dir=""

rollback_empty_claims() {
  local item
  for item in "${claimed_arm_runs[@]:-}"; do
    rmdir "$item/jobs" 2>/dev/null || true
    rmdir "$item" 2>/dev/null || true
  done
  for item in "${created_arm_roots[@]:-}"; do
    rmdir "$item" 2>/dev/null || true
  done
  if [[ -n "$claimed_round_dir" ]]; then
    rmdir "$claimed_round_dir" 2>/dev/null || true
  fi
}

if [[ -n "$round_number" ]]; then
  printf -v formatted_round '%04d' "$((10#$round_number))"
  round_dir="$evidence_root/round-$formatted_round"
  if [[ ! -d "$round_dir" ]]; then
    echo "requested round does not exist: $round_dir" >&2
    exit 2
  fi
fi

allocation_barrier_for_test

if [[ -n "$round_number" ]]; then
  if ! rollout_lock_matches "$round_dir/rollout.lock" "$task_digest" "$rollout_input_digest"; then
    echo "rollout identity does not match the current task" >&2
    exit 1
  fi
  : > "$round_dir/.active"
else
  round_dir="$(claim_next_directory "$evidence_root" "round-")"
  claimed_round_dir="$round_dir"
  : > "$round_dir/.active"
fi

for arm in "${arms[@]}"; do
  arm_root="$round_dir/$arm"
  if ! next_number "$arm_root" "run-" >/dev/null; then
    rollback_empty_claims
    exit 1
  fi
done

for arm in "${arms[@]}"; do
  arm_root="$round_dir/$arm"
  if mkdir "$arm_root" 2>/dev/null; then
    created_arm_roots+=("$arm_root")
  elif [[ ! -d "$arm_root" ]]; then
    echo "cannot create arm directory: $arm_root" >&2
    rollback_empty_claims
    exit 1
  fi
  if arm_run_dir="$(claim_next_directory "$arm_root" "run-")"; then
    claimed_arm_runs+=("$arm_run_dir")
    arm_run_dirs+=("$arm_run_dir")
    mkdir -p "$arm_run_dir/jobs"
  else
    rollback_empty_claims
    exit 1
  fi
done

if [[ -z "$round_number" && "$mode" != "regrade" ]]; then
  if ! write_rollout_lock "$round_dir" "$task_digest" "$rollout_input_digest"; then
    rollback_empty_claims
    exit 1
  fi
fi
claimed_round_dir=""

# Harbor receives model credentials only through its selected private
# --env-file. Regrades retain only the exact Daytona configuration needed by
# the supported runtime; neither mode inherits arbitrary parent variables.
scrub_child_environment() {
  local environment_name
  while IFS= read -r environment_name; do
    case "$environment_name" in
      PATH|HOME|USER|LOGNAME|SHELL|TMPDIR|TMP|TEMP|TZ) ;;
      LANG|LANGUAGE|LC_ALL|LC_CTYPE|LC_COLLATE|LC_MESSAGES|LC_MONETARY|LC_NUMERIC|LC_TIME|LC_PAPER|LC_NAME|LC_ADDRESS|LC_TELEPHONE|LC_MEASUREMENT|LC_IDENTIFICATION) ;;
      TERM|COLORTERM|NO_COLOR|FORCE_COLOR) ;;
      SSL_CERT_FILE|SSL_CERT_DIR|REQUESTS_CA_BUNDLE|CURL_CA_BUNDLE) ;;
      HTTP_PROXY|HTTPS_PROXY|ALL_PROXY|NO_PROXY|http_proxy|https_proxy|all_proxy|no_proxy) ;;
      XDG_CONFIG_HOME|XDG_CACHE_HOME|XDG_DATA_HOME|XDG_STATE_HOME|XDG_RUNTIME_DIR) ;;
      DOCKER_HOST|DOCKER_CONTEXT|DOCKER_CONFIG|DOCKER_TLS_VERIFY|DOCKER_CERT_PATH|DOCKER_DEFAULT_PLATFORM|DOCKER_BUILDKIT|BUILDKIT_HOST) ;;
      PYTHONUTF8|PYTHONIOENCODING|PYTHONUNBUFFERED) ;;
      HARBOR_JUDGE_BASE_URL|HARBOR_JUDGE_AUTH_TOKEN) ;;
      FAKE_CAPTURE|FAKE_META|FAKE_SIGNAL_LOG|FAKE_HARBOR_BARRIER_DIR|FAKE_HARBOR_SLEEP|FAKE_HARBOR_SLEEP_TARGET|FAKE_HARBOR_SLEEP_SOLVER|FAKE_HARBOR_SLEEP_REGRADE_TARGET|FAKE_HARBOR_SLEEP_REGRADE_SOLVER|FAKE_HARBOR_FAIL_REGRADE_ARM|FAKE_HARBOR_FAIL_MODEL) ;;
      DAYTONA_API_KEY|DAYTONA_JWT_TOKEN|DAYTONA_ORGANIZATION_ID|DAYTONA_API_URL|DAYTONA_SERVER_URL|DAYTONA_TARGET|DAYTONA_USE_DEPRECATED_POLLING|DAYTONA_OTEL_ENABLED|DAYTONA_EXPERIMENTAL_OTEL_ENABLED|DAYTONA_HAPPY_EYEBALLS_DELAY)
        if [[ "$mode" != "regrade" ]]; then
          unset "$environment_name"
        fi
        ;;
      *)
        if ! unset "$environment_name"; then
          echo "cannot remove parent environment variable: $environment_name" >&2
          return 1
        fi
        ;;
    esac
  done < <(compgen -e)
}

if [[ "$mode" != "regrade" ]]; then
  for arm in "${arms[@]}"; do
    upper="$(printf '%s' "$arm" | tr '[:lower:]' '[:upper:]')"
    base_url_name="HARBOR_${upper}_BASE_URL"
    token_name="HARBOR_${upper}_AUTH_TOKEN"
    arm_env_file="$credential_dir/$arm.env"
    umask 077
    {
      printf 'DAYTONA_API_KEY=%s\n' "$DAYTONA_API_KEY"
      printf 'ANTHROPIC_BASE_URL=%s\n' "${!base_url_name}"
      printf 'ANTHROPIC_AUTH_TOKEN=%s\n' "${!token_name}"
    } > "$arm_env_file"
    chmod 600 "$arm_env_file"
  done
fi

launch_arm() {
  local arm="$1" index="$2" model effort host arm_run_dir
  arm_run_dir="${arm_run_dirs[$index]}"
  local -a command=()
  if [[ "$mode" == "regrade" ]]; then
    command=(
      harbor job regrade "${regrade_sources[$index]}"
      --task-path "$task_root"
      --env daytona
      --n-concurrent "$concurrency"
      --jobs-dir "$arm_run_dir/jobs"
    )
  else
    model="${arm_models[$index]}"
    effort="${arm_efforts[$index]}"
    host="${arm_hosts[$index]}"
    command=(
      harbor run
      --path "$task_root"
      --env daytona
      --env-file "$credential_dir/$arm.env"
      --n-concurrent "$concurrency"
      --n-attempts "$attempts"
      --max-retries 0
      --yes
      --agent claude-code
      --model "$model"
    )
    if [[ -n "$effort" ]]; then
      command+=(--agent-kwarg "reasoning_effort=$effort")
    fi
    command+=(--allow-agent-host "$host" --jobs-dir "$arm_run_dir/jobs")
  fi
  (
    scrub_child_environment
    exec "${command[@]}"
  ) > "$arm_run_dir/harbor.log" 2>&1 &
  child_pids+=("$!")
  child_runs+=("$arm_run_dir")
}

wait_for_children() {
  local pid status=0 child_status
  while [[ -n "${child_pids[0]:-}" ]]; do
    pid="${child_pids[0]}"
    if wait "$pid"; then
      child_status=0
    else
      child_status=$?
    fi
    printf '%s\n' "$child_status" > "${child_runs[0]}/exit-code"
    if (( child_status != 0 )); then
      status="$child_status"
    fi
    child_pids=("${child_pids[@]:1}")
    child_runs=("${child_runs[@]:1}")
    write_active_runs_for_test
  done
  return "$status"
}

raise_measuring
invocation_launched=1
for index in "${!arms[@]}"; do
  launch_arm "${arms[$index]}" "$index"
done
if wait_for_children; then
  harbor_status=0
else
  harbor_status=$?
fi

if ! publish_current_round; then
  exit 1
fi
rm -f -- "$round_dir/.active"
if (( harbor_status == 0 )) && [[ "$mode" != "regrade" ]]; then
  complete_source_json="$(regrade_sources_json "$evidence_root" "$task_name" "$rollout_input_digest" complete)"
  complete_source_round="$(json_source_round "$complete_source_json")"
  if [[ "${complete_source_round##*/}" == "${round_dir##*/}" ]]; then
    remember_complete_source "$complete_source_json"
  fi
fi
"$harbor_python" "$parser_path" "$round_dir" --final-task "$task_root" || true
exit "$harbor_status"
