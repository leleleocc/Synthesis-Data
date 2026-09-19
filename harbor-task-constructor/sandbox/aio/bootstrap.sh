#!/usr/bin/env bash
# Shim. Everything real is in runner/, alongside this file on the runtime mount.
#
# This is what InstanceImageInfo.Command points at, and it stays this short on
# purpose: it runs before anything is known to work, so its only jobs are to wait
# for the mount, find an interpreter, and hand over.
#
#   bash bootstrap.sh [run|attach|archive|probe]
#
# Env (set by `sbx task create`): SANDBOX_TASK_ID, RUNTIME_MOUNT_PATH,
# TEMPLATE_MOUNT_PATH, TASK_MOUNT_PATH, NAS_MOUNT_PATH, KEEP_ALIVE_SECONDS,
# CONSTRUCT_MAX_ITERATIONS, LEASE_HEARTBEAT_SECONDS, LEASE_STALE_SECONDS,
# PROBE_PATHS — plus whatever the tenant's task.env carries, which is how
# ANTHROPIC_AUTH_TOKEN and ANTHROPIC_MODEL reach the agent.
#
# Two mounts matter here and they are not the same one. RUNTIME is read-only and
# shared by every sandbox — this file and the runner package come from there.
# TASK is this task's own read-write prefix, and is where the log below has to go,
# because a diagnostic written to the shared runtime would be either unwritable or
# overwritten by the next task.

set -uo pipefail

RUNTIME="${RUNTIME_MOUNT_PATH:-/mnt/runtime}"
TASK="${TASK_MOUNT_PATH:-/mnt/task}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$TASK/runs/$STAMP-$(hostname 2>/dev/null || echo unknown)-$$"

# The mount is already up if the injected waiter found this file, but the package
# is what actually gets imported, so wait on that instead of assuming.
for _ in $(seq 1 30); do
  [ -f "$RUNTIME/runner/__main__.py" ] && break
  sleep 2
done

PY="$(command -v python3 || command -v python || true)"

if [ -z "$PY" ] || [ ! -f "$RUNTIME/runner/__main__.py" ]; then
  # Say so where it can be seen. A startup path that fails silently is
  # indistinguishable from one that never ran, and the only window onto this
  # instance is what it leaves in TOS.
  mkdir -p "$RUN_DIR" 2>/dev/null
  {
    echo "runner did not start"
    echo "  stamp:        $STAMP"
    echo "  host:         $(hostname 2>/dev/null)"
    echo "  python:       ${PY:-NOT FOUND}"
    echo "  runner pkg:   $([ -f "$RUNTIME/runner/__main__.py" ] && echo present || echo MISSING)"
    echo "  runtime:      $RUNTIME"
    echo "  task:         $TASK"
    echo "  PATH:         $PATH"
    echo ""
    echo "runtime contents:"
    ls -la "$RUNTIME" 2>&1
    echo ""
    echo "task contents:"
    ls -la "$TASK" 2>&1
  } | tee "$RUN_DIR/bootstrap.log" 2>/dev/null
  sleep "${KEEP_ALIVE_SECONDS:-3600}"
  exit 1
fi

# Do not write __pycache__ into the runtime mount: every import would become a
# write to object storage, and that mount is shared with every other sandbox —
# which is also why it is read-only once the scaffold is settled.
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$RUNTIME${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m runner "$@"
