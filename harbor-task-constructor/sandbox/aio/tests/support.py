"""Shared fixtures for the runner tests.

Everything here runs against a temporary directory standing in for the two
mounts, which is the point of the module: the whole lifecycle — lease contention,
archive integrity, the cleanup policy — is exercised on a laptop without
launching a sandbox.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runner.config import Config  # noqa: E402


class CaptureLog:
    """A RunLog with the same surface, collecting lines instead of publishing."""

    def __init__(self):
        self.lines = []
        self.failures = 0

    def say(self, message=""):
        self.lines.append(message)

    def phase(self, title):
        self.say(f"=== {title} ===")

    def ok(self, message):
        self.say(f"  ok   {message}")

    def bad(self, message):
        self.say(f"  FAIL {message}")
        self.failures += 1

    def run_output(self, text):
        self.say(str(text))

    def publish(self):
        pass

    def close(self):
        pass

    @property
    def text(self):
        return "\n".join(self.lines)


def make_config(root, **overrides):
    task = os.path.join(root, "task")
    nas = os.path.join(root, "nas")
    runtime = os.path.join(root, "runtime")
    template = os.path.join(root, "template")
    for path in (task, nas, runtime, template):
        os.makedirs(path, exist_ok=True)
    fields = dict(
        task_id="task-under-test",
        task=task,
        nas=nas,
        runtime=runtime,
        template=template,
        read_only_paths=(),
        keep_alive_seconds=0,
        lease_heartbeat_seconds=1,
        lease_stale_seconds=5,
        max_iterations=10,
        # The agent that does nothing and succeeds. Tests that care what the
        # loop does with the agent's output pass their own via fake_agent();
        # the rest must not reach the network, and would if this defaulted to
        # the real `claude`.
        agent_bin="/usr/bin/true",
        host="host-a",
        pid=os.getpid(),
        stamp="20260101T000000Z",
    )
    fields.update(overrides)
    return Config(**fields)


def make_workspace(cfg, files=("build/a.txt", "build/bin/run.sh", "method/m.py",
                               "instruction.md")):
    """A workspace shaped like a packed Harbor task, already attached."""
    for rel in files:
        path = os.path.join(cfg.workspace, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(f"contents of {rel}\n")
    # Only when the caller kept the default shape. The exec bit is what the
    # round-trip tests assert survives, but callers passing their own file list
    # are testing something else and should not have to include it.
    runner = os.path.join(cfg.workspace, "build/bin/run.sh")
    if os.path.exists(runner):
        os.chmod(runner, 0o755)
    open(cfg.attached_marker, "w").close()
    return cfg.workspace


def declare_done(cfg):
    """Write the .done marker that signals construction is complete."""
    open(cfg.done_marker, "w").close()


def fake_agent(root, body):
    """An executable standing in for `claude -p`, running `body` in the workspace.

    The runner invokes the agent with its own argv and the prompt on stdin, and
    judges it only by what appears in the workspace — so a shell script is a
    complete substitute, and the loop's three stop conditions (.done, stall,
    max_iterations) can each be provoked on demand.
    """
    path = os.path.join(root, "fake-agent")
    with open(path, "w") as fh:
        fh.write("#!/bin/sh\n" + body)
    os.chmod(path, 0o755)
    return path


def seed_tree(cfg, stamp="20250101T000000Z", marker="from-the-seed"):
    """Put one verified archive in seed/ and leave NAS empty.

    The marker file is what tells a test which tree it got back: the seed and a
    run's own archive are the same shape, so only the contents distinguish them.
    """
    from runner import archive as archives

    made = make_workspace(cfg, files=("build/a.txt", marker))
    archives.create(made, cfg.seed_dir, stamp, CaptureLog())
    import shutil
    shutil.rmtree(cfg.workspace)
    return marker
