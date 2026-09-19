#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_root="$(cd -- "$script_dir/.." && pwd -P)"

usage() {
  cat <<'EOF'
Usage:
  scripts/run-production.sh MODE --env-file PATH [options]

Modes:
  check       Validate launcher inputs and the local task path; print JobConfig but does not expand nested task values or allocate remote/model work.
  install     Build the Daytona environment and install the outer agent only.
  run         Run one real task-construction attempt.

Options:
  --env-file PATH   Trusted shell env file based on .env.example (required).
  --jobs-dir PATH   Harbor job output directory (default: ./jobs).
  --job-name NAME   Job name (default for install/run: mode plus UTC timestamp).
  --yes             Required for install and run; confirms remote/costful work.
  -h, --help        Show this help.
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 2
}

if [[ $# -eq 0 ]]; then
  usage >&2
  exit 2
fi

case "$1" in
  -h|--help)
    usage
    exit 0
    ;;
  check|install|run)
    mode="$1"
    shift
    ;;
  *)
    die "unknown mode '$1' (expected check, install, or run)"
    ;;
esac

env_file=""
jobs_dir="$repo_root/jobs"
job_name=""
confirmed=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file|--jobs-dir|--job-name)
      [[ $# -ge 2 ]] || die "missing value for $1"
      case "$1" in
        --env-file) env_file="$2" ;;
        --jobs-dir) jobs_dir="$2" ;;
        --job-name) job_name="$2" ;;
      esac
      shift 2
      ;;
    --yes)
      confirmed=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option '$1'"
      ;;
  esac
done

[[ -n "$env_file" ]] || die "--env-file is required"
[[ -f "$env_file" ]] || die "env file not found: $env_file"
[[ -r "$env_file" ]] || die "env file is not readable: $env_file"

if [[ "$mode" != "check" && "$confirmed" != true ]]; then
  die "$mode requires --yes because it allocates remote resources"
fi

# The env file is deliberately sourced: it is operator-owned configuration, not
# untrusted input. This also makes its values available to task.toml interpolation.
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

required=(
  DAYTONA_API_KEY
  ANTHROPIC_BASE_URL
  ANTHROPIC_AUTH_TOKEN
  HARBOR_CONSTRUCTOR_MODEL
  HARBOR_TARGET_MODEL_NAME
  HARBOR_TARGET_BASE_URL
  HARBOR_TARGET_AUTH_TOKEN
  HARBOR_SOLVER_MODEL_NAME
  HARBOR_SOLVER_BASE_URL
  HARBOR_SOLVER_AUTH_TOKEN
  HARBOR_JUDGE_BASE_URL
  HARBOR_JUDGE_AUTH_TOKEN
)
missing=()
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || missing+=("$name")
done
if (( ${#missing[@]} > 0 )); then
  die "missing required env values: ${missing[*]}"
fi

command -v harbor >/dev/null 2>&1 || die "harbor is not installed or not on PATH"

command=(
  harbor run
  --path "$repo_root/template"
  --env daytona
  --env-file "$env_file"
  --agent claude-code
  --model "$HARBOR_CONSTRUCTOR_MODEL"
)
if [[ -n "${HARBOR_CONSTRUCTOR_REASONING_EFFORT:-}" ]]; then
  command+=(--agent-kwarg "reasoning_effort=$HARBOR_CONSTRUCTOR_REASONING_EFFORT")
fi
command+=(
  --n-attempts 1
  --n-concurrent 1
  --max-retries 0
  --jobs-dir "$jobs_dir"
)

if [[ -n "$job_name" ]]; then
  command+=(--job-name "$job_name")
elif [[ "$mode" != "check" ]]; then
  command+=(--job-name "harbor-task-constructor-$mode-$(date -u +%Y%m%d-%H%M%S)")
fi

case "$mode" in
  check) command+=(--print-config) ;;
  install) command+=(--install-only --yes) ;;
  run) command+=(--yes) ;;
esac

exec "${command[@]}"
