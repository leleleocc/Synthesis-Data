"""Entry point for the in-sandbox runner.

    python3 -m runner            the full lifecycle
    python3 -m runner attach     attach only, for verifying the TOS -> NAS path
    python3 -m runner archive    archive the current workspace and stop
    python3 -m runner probe      preflight + survey, touching nothing on NAS

Lifecycle:

    1  preflight  mounts, capacity, and what is running in this container
    1b survey     probe only: the image, egress, and read-only enforcement
    2  lease      one constructor at a time, or stand down
    3  attach     reuse the NAS tree, or restore the newest verified archive
    4a init       run init.sh once as root; non-zero is a hard fail
    4b iterate    claude -p loop as gem: .done / stall / max_iterations stops it
    5  archive    workspace -> TOS, hashed in flight, sidecar last
    7  report     result.json to this run's directory

The lease is released before the keep-alive sleep, not after: a run that finished
its work and is only holding the container open for inspection must not look like
a live constructor to the next run in.
"""

import json
import os
import subprocess
import sys
import time

from . import archive as archives
from . import config as configuration
from . import status as run_status
from .trace import TraceWriter
from . import workspace as ws
from .lease import Lease, LeaseBusy
from .runlog import RunLog

# uid/gid of the non-root user inside the image. claude --dangerously-skip-permissions
# refuses to run as root, so every subprocess that touches the model must drop here.
_GEM_UID = 1000
_GEM_GID = 1000
_GEM_USER = "gem"
_GEM_HOME = "/home/gem"


def _drop_to_gem():
    """preexec_fn: drop to gem (uid=gid=1000) after fork.

    Only attempted when we are actually root — on a developer machine the tests
    run as a normal user who cannot setuid, so the call is a no-op there.
    """
    if os.getuid() == 0:
        os.setgid(_GEM_GID)
        os.setuid(_GEM_UID)


def _gem_env():
    """The environment to pair with _drop_to_gem.

    setuid changes the uid and nothing else, so a child dropped to gem would
    otherwise inherit root's HOME. Everything the agent's toolchain keeps per
    user — the npm cache, pip's user site, claude's own config — is addressed
    through HOME, so leaving it at /root means a uid-1000 process writing into a
    root-owned directory: permission denied, in three different tools, with three
    different error messages. Set it once here rather than asking every template's
    init.sh to know this.
    """
    if os.getuid() != 0:
        return None
    return dict(os.environ, HOME=_GEM_HOME, USER=_GEM_USER, LOGNAME=_GEM_USER)


def _give_workspace_to_gem(cfg, log):
    """Hand the tree to the user that is about to work in it.

    Everything before this point runs as root — attach extracts the archive,
    init.sh provisions — and the agent that comes after runs as gem, which would
    otherwise find its own workspace read-only. Best effort: the NAS mount may
    map ownership itself, in which case chown is redundant, and on a developer
    machine it is not permitted at all.
    """
    if os.getuid() != 0:
        return
    changed = 0
    for root, dirs, files in os.walk(cfg.workspace):
        for name in dirs + files:
            try:
                os.lchown(os.path.join(root, name), _GEM_UID, _GEM_GID)
                changed += 1
            except OSError:
                pass
    try:
        os.lchown(cfg.workspace, _GEM_UID, _GEM_GID)
    except OSError:
        pass
    log.say(f"  chowned {changed} paths to {_GEM_USER} ({_GEM_UID}:{_GEM_GID})")


def _shell(log, command):
    try:
        out = subprocess.run(command, shell=True, capture_output=True, text=True,
                             timeout=30)
        log.run_output(out.stdout or out.stderr)
    except (OSError, subprocess.SubprocessError) as exc:
        log.say(f"  ({command}: {exc})")


def preflight(cfg, log):
    log.phase("1 preflight")
    for label, path, read_only in cfg.mounts:
        if os.path.isdir(path):
            log.ok(f"{label} mount present: {path}"
                   f"{'  (declared read-only)' if read_only else ''}")
        else:
            log.bad(f"{label} mount missing: {path}")

    # Anything else worth looking at in this instance. Comma-separated, so a
    # single create call can ask a question without a new runtime release —
    # which matters while the image's own layout is still being mapped.
    extra = [p for p in (os.environ.get("PROBE_PATHS") or "").split(",") if p.strip()]
    for path in extra:
        path = path.strip()
        log.say(f"  {'present' if os.path.exists(path) else 'MISSING'}  {path}")

    # Who else is in this container. A failing instance is retried on a ~120 s
    # grid and every retry re-runs the startup command inside the *same living*
    # container, so a run needs to be able to see that it is not the first —
    # pid 1's age and the local log count both show it, and neither is visible
    # from outside the instance.
    log.say("")
    log.say(f"  python:   {sys.executable} ({sys.version.split()[0]})")
    try:
        with open("/proc/1/cmdline", "rb") as fh:
            raw = fh.read().replace(b"\x00", b" ").decode(errors="replace")
            log.say(f"  pid 1:    {raw.strip()}")
    except OSError:
        log.say("  pid 1:    (no /proc)")
    _shell(log, "ps -o etime= -p 1 2>/dev/null | sed 's/^/  pid 1 age:/'")
    # Excluding this run's own log, which RunLog has already created by now — the
    # first run in a fresh container must report zero, or the number says nothing.
    mine = os.path.basename(getattr(log, "local_path", "") or "")
    prior = [n for n in _listdir("/tmp/user")
             if n.startswith("bootstrap-") and n != mine]
    log.say(f"  prior runs in this container: {len(prior)}")
    log.say("")
    _shell(log, "df -hT 2>/dev/null || df -h")
    log.say("")
    _shell(log, "free -m 2>/dev/null || true")
    return log.failures == 0


# Questions about the image and the network that only the inside of a sandbox can
# answer, each one paired with the TODO section it settles. They run under `probe`
# only: a construction run has no use for them and they would bury its log.
SURVEY = (
    ("identity", "id; echo; echo \"HOME=$HOME USER=${USER:-?}\""),
    ("home", "ls -la /home 2>&1"),
    # What the image's own entry point does with RUN_HOOK_* and WAIT_FILES. If it
    # already offers an init and a shutdown hook, the injected startup command and
    # TODO section 2's "no exit hook" both stop being settled questions.
    ("run.sh", "cat /opt/gem/run.sh 2>&1 | head -120"),
    ("mounts", "mount | grep -E 'virtiofs|nfs|/mnt|/home' 2>&1"),
    # virtiofs flattens modes to 777 and NFS does not, which is the whole reason
    # only tarballs cross TOS. Worth confirming per image rather than assuming.
    ("claude", "command -v claude || echo 'claude not installed'"),
    ("node", "node --version 2>&1; npm --version 2>&1"),
    ("env", "env | sort | grep -vi -E 'key|token|secret|password'"),
)

# Egress, end to end. NAT is configured, but "configured" and "a TCP connection
# completes" are different claims, and the second is the one `npm i -g
# @anthropic-ai/claude-code` in a tenant's init.sh depends on.
EGRESS = (
    ("npm registry", "https://registry.npmjs.org/"),
    ("anthropic api", "https://api.anthropic.com/"),
)


def survey(cfg, log):
    log.phase("1b survey")
    for label, command in SURVEY:
        log.say(f"  --- {label} ---")
        _shell(log, command)
        log.say("")

    log.say("  --- egress ---")
    for label, url in EGRESS:
        log.say(f"  {label}: {_reach(url)}")

    # Writing to a read-only mount must fail. This is the check that decides
    # whether "the model physically cannot edit the template" is a property or
    # merely a convention (TODO section 4) — so it is reported as a failure when
    # the write succeeds, not merely noted.
    log.say("")
    for label, path, read_only in cfg.mounts:
        if not read_only:
            continue
        probe_file = os.path.join(path, f".write-probe-{cfg.pid}")
        try:
            with open(probe_file, "w") as fh:
                fh.write("x")
        except OSError as exc:
            log.ok(f"{label} is read-only as declared ({type(exc).__name__})")
            continue
        os.remove(probe_file)
        log.bad(f"{label} accepted a write at {probe_file} — read_only is not in "
                "effect, so template protection is a convention, not a property")


def _reach(url, timeout=10):
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return f"reachable (HTTP {response.status})"
    except urllib.error.HTTPError as exc:
        # A status code is still proof the connection completed; 4xx from a bare
        # GET to an API root is the expected answer, not a failure to reach it.
        return f"reachable (HTTP {exc.code})"
    except Exception as exc:
        return f"UNREACHABLE ({type(exc).__name__}: {exc})"


def _listdir(path):
    try:
        return os.listdir(path)
    except OSError:
        return []


def init_phase(cfg, log):
    """Phase 4a: run init.sh once, before the iteration loop.

    init.sh is optional — if the template has no init.sh, this is a no-op.
    Any non-zero exit is a hard fail: the loop never starts.

    Unlike the agent, this runs as root. init.sh provisions the container, and
    provisioning is a root job: `npm install -g` writes to a root-owned global
    prefix and exits 243 for a uid-1000 caller, which is exactly how the first
    real sandbox run died. The alternative — a per-user npm prefix — only moves
    the tools somewhere the next phase's PATH does not look. Running it as root
    and handing the workspace to gem afterwards keeps each phase doing the thing
    it is actually for.

    Its output is captured into the run log rather than left on stdout. This is
    the one phase whose failure stops everything, and the run log is the only
    window the host has onto a sandbox — a hard fail that reports an exit status
    and nothing else costs a whole sandbox launch to diagnose.
    """
    log.phase("4a init")
    if not os.path.isfile(cfg.init_script):
        log.say("  no init.sh in template — skipping")
        return True

    log.say(f"  $ bash {cfg.init_script}")
    started = time.time()
    result = subprocess.run(
        ["bash", cfg.init_script],
        cwd=cfg.workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    log.run_output(result.stdout)
    elapsed = time.time() - started
    if result.returncode == 0:
        log.ok(f"init.sh exited 0 after {elapsed:.0f}s")
        return True
    log.bad(f"init.sh exited {result.returncode} after {elapsed:.0f}s — hard fail")
    return False


# Three consecutive identical fingerprints = stall.
_STALL_THRESHOLD = 3


def iterate(cfg, log):
    """Phase 4b: claude -p loop.

    Runs until:
      • .done appears in the workspace          (success)
      • fingerprint unchanged for _STALL_THRESHOLD consecutive iterations
      • cfg.max_iterations reached

    Each iteration runs:
        claude -p < PROMPT.md --add-dir $TEMPLATE_MOUNT_PATH

    as gem (uid=gid=1000), cwd=workspace.  Output goes to the process stdout/
    stderr which the platform collects; we do not capture it here so it streams
    in real time.
    """
    log.phase("4b iterate")

    if not os.path.isfile(cfg.prompt_file):
        log.bad(f"PROMPT.md not found at {cfg.prompt_file} — cannot iterate")
        return False

    prev_fp = None
    stall_count = 0

    for i in range(1, cfg.max_iterations + 1):
        # .done check before running: a reused workspace from a prior run may
        # already be done; also checked inside the loop so we stop immediately
        # when the model creates it.
        if os.path.exists(cfg.done_marker):
            log.ok(f".done present before iteration {i} — construction complete")
            return True

        log.say(f"  iteration {i}/{cfg.max_iterations}")
        run_status.write(cfg, phase="4b", iteration=i, bump_lives=True)
        started = time.time()
        writer = TraceWriter(cfg, i)
        completed = False
        process = None
        try:
            with open(cfg.prompt_file) as prompt_fh:
                process = subprocess.Popen(
                    [cfg.agent_bin, "-p",
                     "--output-format", "stream-json",
                     "--verbose",
                     "--add-dir", cfg.template,
                     "--dangerously-skip-permissions"],
                    stdin=prompt_fh,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,   # captured separately for diagnostics
                    cwd=cfg.workspace,
                    preexec_fn=_drop_to_gem,
                    env=_gem_env(),
                )

                for line in iter(process.stdout.readline, b""):
                    writer.write_event(line)
                    print(line.decode(errors="replace"), end="", flush=True)

                process.stdout.close()
                stderr = process.stderr.read()
                process.stderr.close()
                rc = process.wait()

            elapsed = time.time() - started
            writer.finish(exit_code=rc, elapsed_seconds=elapsed)
            completed = True
        finally:
            # Preserve a durable incomplete status if the runner is interrupted
            # or the agent cannot produce a result for this iteration.
            if not completed and process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            writer.close(incomplete=not completed)

        # Claude Code exit code meanings (non-zero are noted but do not stop
        # the loop — a transient error or an incomplete task both get another
        # iteration to recover or finish).
        _RC = {
            0:   "ok",
            1:   "generic error",
            2:   "usage error",
            3:   "cancelled by user",
            130: "interrupted (SIGINT)",
        }
        rc_label = _RC.get(rc, f"exit {rc}")
        if rc != 0:
            log.say(f"  iteration {i} {rc_label} after {elapsed:.0f}s (continuing)")
            # Print the last few lines of stderr so the reason is visible in
            # the bootstrap log without needing to attach to the instance.
            stderr_tail = (stderr or b"").decode(errors="replace").strip()
            if stderr_tail:
                for line in stderr_tail.splitlines()[-10:]:
                    log.say(f"    stderr: {line}")
        else:
            log.say(f"  iteration {i} ok after {elapsed:.0f}s")

        if os.path.exists(cfg.done_marker):
            log.ok(f".done created in iteration {i} — construction complete")
            return True

        # Stall detection. Like reaching max_iterations, a stall is a statement
        # about the construction, not about the runner — it is reported through
        # `done: false` in result.json, not as a runner failure, so a task whose
        # model gave up does not read as a broken scaffold.
        fp = ws.fingerprint(cfg.workspace)
        if fp == prev_fp:
            stall_count += 1
            log.say(f"  fingerprint unchanged ({stall_count}/{_STALL_THRESHOLD}): "
                    f"{fp[0]} files, mtime={fp[1]:.0f}")
            if stall_count >= _STALL_THRESHOLD:
                log.say(f"  stall detected after {i} iterations — stopping loop")
                return False
        else:
            stall_count = 0
            prev_fp = fp

    log.say(f"  reached max_iterations={cfg.max_iterations} without .done — loop ended")
    return False


def verify_phase(cfg, log):
    """Phase 4c: run verify.sh after .done, record the outcome.

    verify.sh is optional. When absent, the result is recorded as 'claimed':
    the agent declared itself done but no programmatic gate confirmed it.

    Unlike init.sh, a non-zero exit here is not a hard fail of the scaffold —
    it is an outcome of the construction (done=True but verified=False). The
    runner still archives and reports normally; verdict stays 'pass' because
    the scaffold itself did not break.

    Runs as root (same process, no uid change). verify.sh is the tenant's
    gate, not the agent's tool, so it has no reason to need gem's uid. If a
    tenant's verify.sh needs a lower privilege it can drop itself.
    """
    log.phase("4c verify")
    if not os.path.isfile(cfg.verify_script):
        log.say("  no verify.sh in template — recording 'claimed'")
        return "claimed"

    log.say(f"  $ bash {cfg.verify_script}")
    started = time.time()
    result = subprocess.run(
        ["bash", cfg.verify_script],
        cwd=cfg.workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    log.run_output(result.stdout)
    elapsed = time.time() - started
    if result.returncode == 0:
        log.ok(f"verify.sh exited 0 after {elapsed:.0f}s — verified")
        return "verified"
    log.say(f"  verify.sh exited {result.returncode} after {elapsed:.0f}s — not verified")
    return "failed"


def report(cfg, log, **fields):
    log.phase("7 report")
    verdict = "pass" if log.failures == 0 else "fail"
    fields.setdefault("verdict", verdict)
    body = dict(
        run_id=cfg.run_id, stamp=cfg.stamp, host=cfg.host, pid=cfg.pid,
        task_id=cfg.task_id, failures=log.failures, **fields)
    log.say(f"  verdict: {body['verdict']} ({log.failures} failures)")
    if fields.get("lease") != "denied":
        run_status.write(cfg, phase="7", verified=fields.get("verified"),
                         create=False)
    try:
        os.makedirs(cfg.run_dir, exist_ok=True)
        with open(os.path.join(cfg.run_dir, "result.json"), "w") as fh:
            json.dump(body, fh, indent=2)
    except OSError as exc:
        log.say(f"  (could not write result.json: {exc})")
    return body


def stand_down(cfg, log, busy):
    """Record that this run deliberately did nothing, and why.

    A run that stands down still writes a result. A silent exit is
    indistinguishable from a crash, and these runs are only observable through
    what they leave in TOS.
    """
    log.say("")
    log.say(f"  {busy}")
    log.say("  standing down — the workspace belongs to a live run")
    report(cfg, log, verdict="stood-down", lease="denied", holder=busy.holder,
           attach=None, archived=None)
    log.close()


def lifecycle(cfg, log):
    if not preflight(cfg, log):
        log.say("")
        log.say("preflight failed — stopping before touching anything")
        report(cfg, log, lease=None, attach=None, archived=None)
        return

    log.phase("2 lease")
    lease = Lease(cfg, log)
    try:
        lease.acquire()
    except LeaseBusy as busy:
        stand_down(cfg, log, busy)
        return
    log.ok(f"lease held by this run ({cfg.run_id})")
    run_status.write(cfg, phase="2", bump_sandboxes=True)

    archived, mode = None, None
    try:
        log.phase("3 attach")
        try:
            mode = ws.attach(cfg, log)
        except ws.AttachRefused as exc:
            log.bad(str(exc))
            report(cfg, log, lease="held", attach=None, archived=None)
            return

        # Phase 4a: init — hard fail if init.sh exits non-zero.
        if not init_phase(cfg, log):
            report(cfg, log, lease="held", attach=mode, archived=None,
                   verdict="fail")
            return

        # Phase 4b: iterate — claude -p loop.
        _give_workspace_to_gem(cfg, log)
        done = iterate(cfg, log)

        # Phase 4c: verify — run verify.sh if .done was written.
        verified = None
        if done:
            verified = verify_phase(cfg, log)

        log.phase("5 archive")
        if done:
            log.say("  .done present — archiving workspace")
        else:
            log.say("  loop ended without .done — archiving current state")
        path, digest = archives.create(cfg.workspace, cfg.archives_dir,
                                       cfg.run_id, log)
        archived = os.path.basename(path) if digest else None

    finally:
        # Before the keep-alive sleep, always.
        lease.release()
        log.say("")
        log.say("  lease released")

    report(cfg, log, lease="held", attach=mode, archived=archived,
           done=os.path.exists(cfg.done_marker),
           verified=verified,
           restored_files=archives.count_files(cfg.workspace)
           if os.path.isdir(cfg.workspace) else 0)


def main(argv):
    command = (argv[1] if len(argv) > 1 else "run").lstrip("-")
    cfg = configuration.from_env()
    log = RunLog(cfg)
    log.say(f"runner {cfg.run_id}")
    log.say(f"task={cfg.task_id}")
    for label, path, read_only in cfg.mounts:
        log.say(f"  {label.lower():<9} {path}{'  (ro)' if read_only else ''}")

    try:
        if command == "probe":
            preflight(cfg, log)
            survey(cfg, log)
            report(cfg, log, lease=None, attach=None, archived=None)
        elif command == "attach":
            preflight(cfg, log)
            log.phase("attach")
            ws.attach(cfg, log)
        elif command == "archive":
            log.phase("archive")
            archives.create(cfg.workspace, cfg.archives_dir, cfg.run_id, log)
        else:
            lifecycle(cfg, log)
    except ws.AttachRefused as exc:
        log.bad(str(exc))
    finally:
        log.close()

    if command == "run" and cfg.keep_alive_seconds > 0:
        print(f"done — staying alive {cfg.keep_alive_seconds}s for inspection",
              flush=True)
        time.sleep(cfg.keep_alive_seconds)
    return 1 if log.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
