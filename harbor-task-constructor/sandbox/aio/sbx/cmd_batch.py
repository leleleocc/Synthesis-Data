"""Batch: N candidate trees, one nested task-id each, one reconciler."""

import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

from . import cmd_task, faas, mounts, settings, tos

_CANDIDATE = re.compile(r"^[A-Za-z0-9._-]+$")
_RESERVED = {"seed", "archives", "runs"}
_SHARED_PREFIXES = {
    mounts.RUNTIME_PREFIX, mounts.TEMPLATE_PREFIX, mounts.UNASSIGNED,
}


def add_arguments(sub):
    push = sub.add_parser("push", help="upload every candidate subdirectory as a nested task")
    push.add_argument("directory")
    push.add_argument("--name", help="batch name (default: the directory's basename)")
    push.add_argument("--template", required=True)
    push.add_argument("--dry-run", action="store_true")
    push.set_defaults(func=push_cmd)

    status = sub.add_parser("status", help="one row per candidate")
    status.add_argument("batch")
    status.set_defaults(func=status_cmd)

    rec = sub.add_parser("reconcile", help="open the next sandbox for idle/queued candidates")
    rec.add_argument("batch")
    rec.add_argument("--max-sandboxes", type=int, default=60)
    rec.add_argument("--max-measuring", type=int, default=24)
    rec.add_argument("--max-sandboxes-per-line", type=int, default=10)
    rec.add_argument("--dry-run", action="store_true")
    rec.set_defaults(func=reconcile_cmd)

    ls = sub.add_parser("list", help="list batches (meta only, not per-candidate state)")
    ls.set_defaults(func=list_cmd)


def _batch_name(args):
    return args.name or os.path.basename(os.path.abspath(args.directory).rstrip("/"))


def _candidates(directory):
    names = []
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        if not os.path.isdir(path):
            continue
        if name.startswith(".") or name.startswith("_"):
            continue
        if name in _RESERVED:
            continue
        if not _CANDIDATE.match(name):
            sys.exit(f"invalid candidate name {name!r}")
        names.append(name)
    return names


def _write_batch_json(env, client, batch, template):
    bucket = settings.need(env, "TOS_BUCKET")
    # key_for is a prefix helper (always trailing '/'); batch.json is the object.
    key = tos.key_for(f"{mounts.tos_base(env)}/{batch}") + "batch.json"
    body = {
        "template": template,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(body, fh, indent=2)
        fh.write("\n")
        path = fh.name
    try:
        tos.put(client, bucket, key, path, "batch.json")
    finally:
        os.unlink(path)


def push_cmd(args):
    batch = _batch_name(args)
    cmd_task._check_task_id(f"{batch}/x")
    names = _candidates(args.directory)
    if not names:
        sys.exit(f"no candidates under {args.directory}")
    env = settings.load_env()
    client = tos.connect(env, socket_timeout=180, connection_time=30, max_retry_count=5)
    for name in names:
        task_id = f"{batch}/{name}"
        cmd_task._check_task_id(task_id)
        directory = os.path.join(args.directory, name)
        print(f"\n=== {task_id} ===")
        if args.dry_run:
            print(f"  (dry-run) would push {directory}")
            continue
        cmd_task._push(env, client, task_id, directory)
    if not args.dry_run:
        _write_batch_json(env, client, batch, args.template)
    print(f"\n{len(names)} candidates. Reconcile with:\n  sbx batch reconcile {batch}")


_PER_LINE_CAP = 10
_STATE_ORDER = (
    "working", "measuring", "blocked", "verified", "stopped", "idle", "queued",
)


def classify(status, live, per_line_cap):
    """status: dict or None (None = no status.json). live: bool. per_line_cap: int."""
    if status is None:
        return "queued"
    markers = status.get("markers") or {}
    done = bool(status.get("done"))
    if done and status.get("verified") == "verified":
        return "verified"
    if markers.get("blocked"):
        return "blocked"
    sandboxes = int(status.get("sandboxes") or 0)
    if sandboxes >= per_line_cap and not done:
        return "stopped"
    if live and markers.get("measuring"):
        return "measuring"
    if live:
        return "working"
    return "idle"


def _get_json(client, bucket, key):
    try:
        raw = client.get_object(bucket, key).read()
    except Exception:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _is_live(sandbox):
    """Ready and Failed count as live. Failed still holds the lease.

    classify never sees veFaaS states — this is the caller's translation.
    Unknown / missing status counts as live; only obviously dead names are gone.
    """
    status = getattr(sandbox, "status", None) or "Ready"
    return status not in {"Dead", "Deleted", "Killed"}


def _ago(stamp):
    if not stamp:
        return "—"
    try:
        dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 0:
        seconds = 0
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _iter_cell(status):
    if not status or status.get("phase") != "4b":
        return "—"
    iteration = status.get("iteration")
    max_iterations = status.get("max_iterations")
    if iteration is None or max_iterations is None:
        return "—"
    return f"{iteration}/{max_iterations}"


def _live_tasks(sandboxes):
    live = set()
    for sandbox in sandboxes:
        if not _is_live(sandbox):
            continue
        task = cmd_task._labels(sandbox).get("task")
        if task:
            live.add(task)
    return live


def status_cmd(args):
    env = settings.load_env()
    batch = args.batch
    bucket = settings.need(env, "TOS_BUCKET")
    client = tos.connect(env)
    parent = tos.key_for(f"{mounts.tos_base(env)}/{batch}")
    members = tos.prefixes(client, bucket, parent)

    api = faas.configure(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    response = faas.list_sandboxes(api, function_id, metadata={"batch": batch})
    live_by_task = _live_tasks(response.sandboxes or [])

    rows = []
    counts = {state: 0 for state in _STATE_ORDER}
    for name in members:
        status = _get_json(client, bucket, parent + f"{name}/status.json")
        state = classify(status, live=(f"{batch}/{name}" in live_by_task),
                         per_line_cap=_PER_LINE_CAP)
        counts[state] = counts.get(state, 0) + 1
        rows.append((name, state, status))

    print(f"{'candidate':<18} {'state':<11} {'sbx':<4} {'lives':<6} "
          f"{'iter':<6} {'updated':<8} note")
    for name, state, status in rows:
        sbx = 0 if status is None else int(status.get("sandboxes") or 0)
        lives = 0 if status is None else int(status.get("lives") or 0)
        updated = "—" if status is None else _ago(status.get("updated_at"))
        print(f"{name:<18} {state:<11} {sbx:<4} {lives:<6} "
              f"{_iter_cell(status):<6} {updated:<8}")

    parts = [f"{counts[s]} {s}" for s in _STATE_ORDER if counts.get(s)]
    print(f"{'':18} {len(rows)} candidates: " + " · ".join(parts))


def _next_to_open(rows):
    queued = sorted(r["name"] for r in rows if r["state"] == "queued")
    idle = sorted(r["name"] for r in rows if r["state"] == "idle")
    return queued + idle


def _admitted(global_live, max_sandboxes, measuring, max_measuring):
    return global_live < max_sandboxes and measuring < max_measuring


def _open_one(env, api, task_id, template):
    cmd_task._check_task_id(task_id)
    _, task_env = settings.load_task_env(task_id)
    request = faas.sandbox_request(env, task_id, template, task_env=task_env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    existing = faas.list_sandboxes(api, function_id, metadata={"task": task_id})
    if existing.sandboxes:
        print(f"  skip {task_id}: already live")
        return
    faas.create_sandbox(api, request)


def reconcile_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    client = tos.connect(env)
    batch = args.batch
    parent = tos.key_for(f"{mounts.tos_base(env)}/{batch}")
    members = tos.prefixes(client, bucket, parent)
    spec = _get_json(client, bucket, parent + "batch.json")
    if not spec or not spec.get("template"):
        sys.exit(f"no batch.json under {batch}; run sbx batch push first")
    template = spec["template"]

    api = faas.configure(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    global_sbx = faas.list_sandboxes(api, function_id)
    batch_sbx = faas.list_sandboxes(api, function_id, metadata={"batch": batch})
    live_global = [s for s in (global_sbx.sandboxes or []) if _is_live(s)]
    live_batch = [s for s in (batch_sbx.sandboxes or []) if _is_live(s)]
    live_tasks = {cmd_task._labels(s).get("task") for s in live_batch}

    rows = []
    measuring = 0
    for name in members:
        task_id = f"{batch}/{name}"
        st = _get_json(client, bucket, parent + f"{name}/status.json")
        state = classify(st, live=(task_id in live_tasks),
                         per_line_cap=args.max_sandboxes_per_line)
        if state == "measuring":
            measuring += 1
        rows.append({"name": name, "task_id": task_id, "state": state, "status": st})

    opened = 0
    global_live = len(live_global)
    for name in _next_to_open(rows):
        if not _admitted(global_live, args.max_sandboxes, measuring, args.max_measuring):
            print(f"  skip {batch}/{name}: at a gate "
                  f"(sandboxes={global_live}/{args.max_sandboxes} "
                  f"measuring={measuring}/{args.max_measuring})")
            break
        task_id = f"{batch}/{name}"
        print(f"  open {task_id}")
        if args.dry_run:
            global_live += 1
            opened += 1
            continue
        try:
            _open_one(env, api, task_id, template)
        except Exception as exc:
            print(f"  error creating {task_id}: {exc}")
            continue
        global_live += 1
        opened += 1
    print(f"\nopened {opened}")


def list_cmd(args):
    """One row per batch: name, template, candidate count, live sandboxes.

    Does not GET per-candidate status.json. A prefix is a batch iff it has
    batch.json; shared _runtime/_templates/_unassigned and flat task ids
    (no batch.json) are skipped.
    """
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    client = tos.connect(env)
    root = tos.key_for(mounts.tos_base(env))
    names = [n for n in tos.prefixes(client, bucket, root)
             if n not in _SHARED_PREFIXES]

    api = faas.configure(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    response = faas.list_sandboxes(api, function_id)
    live_by_batch = {}
    for sandbox in (response.sandboxes or []):
        if not _is_live(sandbox):
            continue
        batch = cmd_task._labels(sandbox).get("batch")
        if batch:
            live_by_batch[batch] = live_by_batch.get(batch, 0) + 1

    rows = []
    for name in names:
        parent = tos.key_for(f"{mounts.tos_base(env)}/{name}")
        spec = _get_json(client, bucket, parent + "batch.json")
        if not spec:
            continue
        members = tos.prefixes(client, bucket, parent)
        rows.append((name, spec.get("template") or "—", len(members),
                     live_by_batch.get(name, 0)))

    if not rows:
        print("no batches (no batch.json under the TOS base)")
        return

    print(f"{'batch':<24} {'template':<24} {'n':>4} {'live':>4}")
    for name, template, n, live in rows:
        print(f"{name:<24} {template:<24} {n:>4} {live:>4}")
    print(f"{'':24} {len(rows)} batches  "
          f"{sum(r[2] for r in rows)} candidates  "
          f"{sum(r[3] for r in rows)} live")
