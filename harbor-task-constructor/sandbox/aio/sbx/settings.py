"""Settings: the operator's .env, and the tenant's task.env.

Two files with deliberately different fates:

  .env       the operator's. Account, application, image, bucket. Read here,
             used here, never leaves the host.
  task.env   the tenant's model token and their own secrets. Read here and
             turned into CreateSandboxRequest.envs — the *file* never enters a
             sandbox, so no credential is ever at rest on TOS, on NAS, or inside
             a checkpoint archive (TODO.md section 8).
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Knobs that vary run to run, and that carry no secret. Letting the process
# environment win for these means a one-off run — a probe run with
# BOOTSTRAP_ARGS=probe, say — needs no edit to .env and, more to the point, no
# second copy of the file that holds the access keys. Credentials, bucket, and
# mount paths are deliberately absent: those describe *which* account and task
# this is, and picking them up from an ambient shell variable is how you create
# an instance against the wrong one.
OVERRIDABLE = (
    "BOOTSTRAP_ARGS",
    "CONSTRUCT_MAX_ITERATIONS",
    "KEEP_ALIVE_SECONDS",
    "LEASE_HEARTBEAT_SECONDS",
    "LEASE_STALE_SECONDS",
    "PROBE_PATHS",
    "RUNTIME_VERSION",
    "SANDBOX_TIMEOUT_MINUTES",
)


def parse_env(path):
    """KEY=VALUE, one per line. Comments and blanks ignored, quotes stripped."""
    env = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_env(path=None):
    path = path or os.environ.get("SANDBOX_AIO_ENV") or os.path.join(HERE, ".env")
    if not os.path.exists(path):
        sys.exit(f"missing {path} — copy sandbox/aio/.env.example to it and fill it in")
    return _apply_overrides(parse_env(path))


def _apply_overrides(env):
    for key in OVERRIDABLE:
        if key in os.environ:
            env[key] = os.environ[key]
            print(f"  override from environment: {key}={env[key]}", file=sys.stderr)
    return env


def load_task_env(task_id, path=None):
    """The tenant's secrets, as a plain dict. Absent is not an error here.

    Looked up per task first so that a host serving a dozen tenants does not
    depend on anyone remembering which file goes with which task; the single
    task.env is the one-tenant shorthand.
    """
    if path:
        candidates = [path]
    elif "/" in task_id:
        batch = task_id.split("/", 1)[0]
        candidates = [
            os.path.join(HERE, "tasks", f"{batch}.env"),
            os.path.join(HERE, "task.env"),
        ]
    else:
        candidates = [
            os.path.join(HERE, "tasks", f"{task_id}.env"),
            os.path.join(HERE, "task.env"),
        ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate, parse_env(candidate)
    if path:
        sys.exit(f"missing {path}")
    return None, {}


def need(env, key):
    val = env.get(key)
    if not val:
        sys.exit(f"{key} is empty in sandbox/aio/.env")
    return val


def redact(value):
    """A credential rendered so it can be printed: length and shape only.

    --dry-run has to show that a key made it into the request without showing
    what it is, because the whole point of task.env is that its values never get
    written down anywhere a second time.
    """
    text = str(value or "")
    if not text:
        return "(empty)"
    return f"<{len(text)} chars, ends {text[-4:]!r}>" if len(text) > 8 else "<set>"
