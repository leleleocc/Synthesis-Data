"""One runner invocation's configuration, read from the environment.

Four mounts, and the task-scoped two are scoped by CreateSandbox rather than by
anything written here — so nothing below either repeats the task id: /mnt/task
*is* this task's TOS prefix and /home/app is its NAS directory. SANDBOX_TASK_ID
is a label for the log, not part of any path.

    runtime   /mnt/runtime    read-only, shared: this code came from there
    template  /mnt/template   read-only, per tenant: PROMPT.md, init.sh, roles/
    task      /mnt/task       read-write, per task: seed/, archives/, runs/
    nas       /home/app       read-write, per task: the working tree
"""

import os
import re
import socket
import time
from dataclasses import dataclass


def _safe_host():
    """A hostname fit to be one segment of a TOS key.

    run_id names a directory under runs/, so the hostname ends up in an object
    key. Container hostnames are assigned by the platform, not chosen here, and a
    '/' in one would silently nest the run somewhere else. Keep it to characters
    that mean the same thing on a mount and in a key.
    """
    raw = socket.gethostname() or ""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "-", raw).strip("-.")
    return cleaned or "unknown"


def _int(env, key, default):
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _flag(env, key, default=False):
    raw = env.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    task_id: str
    task: str
    nas: str
    runtime: str
    template: str
    read_only_paths: tuple
    keep_alive_seconds: int
    lease_heartbeat_seconds: int
    lease_stale_seconds: int
    # Construction loop
    max_iterations: int
    agent_bin: str
    host: str
    pid: int
    stamp: str
    trace_flush_seconds: int = 5
    trace_chunk_bytes: int = 1048576

    @property
    def run_id(self):
        # Host and pid, not just the stamp. A second-resolution stamp alone
        # collided: on 2026-09-10 two runs at 06:49:44 computed the same name and
        # one log was overwritten and lost. That is structural rather than bad
        # luck, because instance pids are near-identical — all six runs in the
        # live series were pid 13 — so two instances started on one task within a
        # second of each other agree on stamp and pid together, and the hostname
        # is the only thing left that tells them apart. A failing instance being
        # retried adds a second way in: its retries share one container.
        return f"{self.stamp}-{self.host}-{self.pid}"

    @property
    def workspace(self):
        return os.path.join(self.nas, "workspace")

    @property
    def attached_marker(self):
        return os.path.join(self.workspace, ".attached")

    @property
    def done_marker(self):
        return os.path.join(self.workspace, ".done")

    @property
    def measuring_marker(self):
        return os.path.join(self.workspace, ".measuring")

    @property
    def blocked_marker(self):
        return os.path.join(self.workspace, ".blocked")

    @property
    def status_path(self):
        return os.path.join(self.task, "status.json")

    @property
    def lease_dir(self):
        return os.path.join(self.nas, ".lease")

    @property
    def archives_dir(self):
        return os.path.join(self.task, "archives")

    @property
    def seed_dir(self):
        """Where the packed task lands, kept apart from archives/ on purpose.

        Both hold /app-shaped tarballs, so if the seed sat in archives/ it would
        be selected by the same newest-first rule as a run's own output. Pushing
        a corrected seed after a run would then outrank every archive and silently
        restore the pristine tree over the construction. Seed is an input and is
        only consulted when there is no archive at all.
        """
        return os.path.join(self.task, "seed")

    @property
    def run_dir(self):
        return os.path.join(self.task, "runs", self.run_id)

    @property
    def prompt_file(self):
        return os.path.join(self.template, "PROMPT.md")

    @property
    def init_script(self):
        return os.path.join(self.template, "init.sh")

    @property
    def verify_script(self):
        return os.path.join(self.template, "verify.sh")

    @property
    def mounts(self):
        """The four mounts, in the order preflight should report them.

        A tuple rather than four attribute reads at the call site, so adding a
        mount to the scaffold means adding it here and nowhere else. The
        read-only flag is what the host *asked for*, not what this process can
        infer — during bring-up the read-only mounts are deliberately writable,
        and a runner that assumed otherwise would report a failure every run.
        """
        return tuple(
            (label, path, path in self.read_only_paths)
            for label, path in (("RUNTIME", self.runtime), ("TEMPLATE", self.template),
                                ("TASK", self.task), ("NAS", self.nas))
        )


def _paths(env, key):
    return tuple(p.strip() for p in (env.get(key) or "").split(",") if p.strip())


def from_env(env=None):
    env = os.environ if env is None else env
    return Config(
        task_id=env.get("SANDBOX_TASK_ID", ""),
        task=env.get("TASK_MOUNT_PATH") or "/mnt/task",
        nas=env.get("NAS_MOUNT_PATH") or "/home/app",
        runtime=env.get("RUNTIME_MOUNT_PATH") or "/mnt/runtime",
        template=env.get("TEMPLATE_MOUNT_PATH") or "/mnt/template",
        read_only_paths=_paths(env, "READONLY_MOUNTS"),
        keep_alive_seconds=_int(env, "KEEP_ALIVE_SECONDS", 3600),
        lease_heartbeat_seconds=_int(env, "LEASE_HEARTBEAT_SECONDS", 15),
        lease_stale_seconds=_int(env, "LEASE_STALE_SECONDS", 90),
        max_iterations=_int(env, "CONSTRUCT_MAX_ITERATIONS", 10),
        # The agent CLI the loop drives. A name rather than a whole command line:
        # the flags are the runner's business, not a tenant's, and letting a
        # template supply the argv would let it drop --dangerously-skip-permissions
        # or point --add-dir somewhere else. Overridden in tests with a stub, so
        # the loop's stop conditions can be exercised without the network.
        agent_bin=env.get("CONSTRUCT_AGENT_BIN") or "claude",
        host=_safe_host(),
        pid=os.getpid(),
        stamp=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
        trace_flush_seconds=_int(env, "TRACE_FLUSH_SECONDS", 5),
        trace_chunk_bytes=_int(env, "TRACE_CHUNK_BYTES", 1048576),
    )
