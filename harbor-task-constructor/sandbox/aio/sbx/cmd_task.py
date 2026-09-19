"""`sbx task` — package a tree, create the sandbox, and read back what it did.

The host cannot mount NAS, so the task's TOS prefix is the whole window onto a
running sandbox: `runs/` is what the runner writes, `archives/` is what it
produces, `seed/` is what we gave it. Everything under `status` / `logs` / `get`
is reading that one prefix.

Two things happen only here. The tenant's `task.env` is read on the host and
becomes `envs` — the file itself never enters the sandbox, so no credential is
ever at rest on TOS, on NAS, or inside an archive. And `metadata` labels the
sandbox server-side, so `list` and `kill` can find a task's instances without
the host keeping its own ledger.
"""

import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from . import faas, mounts, pack, settings, tos

# A trace is many small objects, not a few big ones: TraceWriter cuts a chunk
# every trace_flush_seconds (5s) and the 1 MB size cap never binds, so one run
# is ~1900 objects averaging ~13 KB. At ~1.5 s per TOS round trip that is 45
# minutes serially, on 23 MB of data — latency-bound, not bandwidth-bound.
_TRACE_FETCH_WORKERS = 16


def add_arguments(sub):
    create = sub.add_parser("create", help="package a tree and start one sandbox")
    create.add_argument("task_id")
    create.add_argument("directory", nargs="?",
                        help="the tree to seed the workspace with; omit to reuse "
                             "whatever the task's prefix already holds")
    create.add_argument("--template", default=mounts.UNASSIGNED,
                        help="published template name (default: the empty placeholder)")
    create.add_argument("--bootstrap-args", default=None,
                        help="arguments for the runner: 'probe' runs preflight only")
    create.add_argument("--timeout", type=int, help="sandbox lifetime, minutes")
    create.add_argument("--keep-alive", type=int, help="KEEP_ALIVE_SECONDS")
    create.add_argument("--task-env", help="path to the tenant's env file "
                                           "(default: tasks/<id>.env, then task.env)")
    create.add_argument("--env", action="append", default=[], metavar="K=V",
                        help="extra environment variable for the instance, "
                             "repeatable — for image variables like "
                             "SANDBOX_SHUTDOWN_HOOKS")
    create.add_argument("--writable-all", action="store_true",
                        help="ask for every mount read-write, matching "
                             "`sbx app sync --writable-all`")
    create.add_argument("--dry-run", action="store_true")
    create.set_defaults(func=create_cmd)

    push = sub.add_parser("push", help="package a tree into the task's seed/ prefix")
    push.add_argument("task_id")
    push.add_argument("directory")
    push.set_defaults(func=push_cmd)

    status = sub.add_parser("status", help="read the task's runs/")
    status.add_argument("task_id")
    status.add_argument("--follow", action="store_true")
    status.set_defaults(func=status_cmd)

    logs = sub.add_parser("logs", help="print one run's bootstrap log")
    logs.add_argument("task_id")
    logs.add_argument("--run", help="run id (default: the newest)")
    logs.set_defaults(func=logs_cmd)

    trace = sub.add_parser("trace", help="read a run's Claude output trace")
    trace.add_argument("task_id")
    trace.add_argument("--run", help="run id (default: the newest immutable run)")
    trace.add_argument("--iteration", type=int,
                       help="iteration number (default: all iterations)")
    trace.add_argument("--follow", action="store_true")
    trace.add_argument("--raw", action="store_true",
                       help="emit the stored JSONL bytes without formatting")
    trace.set_defaults(func=trace_cmd)

    get = sub.add_parser("get", help="download one object under the task prefix")
    get.add_argument("task_id")
    get.add_argument("key")
    get.add_argument("destination")
    get.set_defaults(func=get_cmd)

    ls = sub.add_parser("list", help="list live sandboxes")
    ls.add_argument("--metadata", action="append", default=[],
                    help="k=v, repeatable — asks the server to filter")
    ls.add_argument("--status")
    ls.set_defaults(func=list_cmd)

    kill = sub.add_parser("kill", help="stop a task's sandboxes")
    kill.add_argument("task_id", nargs="?")
    kill.add_argument("--sandbox", help="stop one sandbox by id")
    kill.add_argument("--all", action="store_true", help="stop every live sandbox")
    kill.set_defaults(func=kill_cmd)


def _prefix(env, task_id):
    return tos.key_for(mounts.task_path(env, task_id))


def _check_task_id(task_id):
    # `_runtime` / `_templates` share the bucket path with tasks. A leading
    # '_' on either segment would mount shared data as a read-write prefix.
    # At most one '/' — that is the batch/candidate split; more would make
    # delimiter listing of a batch see nested prefixes as members.
    if task_id.startswith("_") or task_id.startswith("/") or task_id.endswith("/"):
        sys.exit(f"invalid task id {task_id!r}: no leading '_' or empty segment")
    if task_id.count("/") > 1:
        sys.exit(f"invalid task id {task_id!r}: at most one '/'")
    if "/" in task_id:
        batch, candidate = task_id.split("/")
        if not batch or not candidate or batch.startswith("_") or candidate.startswith("_"):
            sys.exit(f"invalid task id {task_id!r}: empty segment or leading '_'")


def _extra_env(pairs):
    """--env K=V, parsed. Values may contain '=' and may be empty."""
    out = {}
    for item in pairs:
        if "=" not in item:
            sys.exit(f"--env expects K=V, got {item!r}")
        key, value = item.split("=", 1)
        out[key.strip()] = value
    return out


# --- packaging and upload ---------------------------------------------------

def _push(env, client, task_id, directory):
    bucket = settings.need(env, "TOS_BUCKET")
    prefix = _prefix(env, task_id)
    with tempfile.TemporaryDirectory(prefix="sbx-pack-") as staging:
        print(f"packing {directory} ...")
        archive, digest = pack.pack(directory, staging, task_id)
        name = os.path.basename(archive)
        print(f"  {name}  {os.path.getsize(archive):,} B  sha256 {digest[:16]}…")

        ckpt = tos.checkpoint_dir(staging)
        os.makedirs(ckpt, exist_ok=True)
        tos.live_checkpoint(client, bucket, prefix + "seed/", ckpt)

        print(f"\npushing to {bucket}:/{prefix}seed/")
        tos.put(client, bucket, f"{prefix}seed/{name}", archive, "seed archive", ckpt)
        tos.put(client, bucket, f"{prefix}seed/{name}.manifest.json",
                archive + ".manifest.json", "manifest")
        # Last, and only now: an archive without its sidecar is treated as
        # absent, which is what stops a sandbox that starts mid-upload from
        # attaching half a tree.
        tos.put(client, bucket, f"{prefix}seed/{name}.sha256",
                archive + ".sha256", "sidecar (last)")
    return name


def push_cmd(args):
    _check_task_id(args.task_id)
    env = settings.load_env()
    client = tos.connect(env, socket_timeout=180, connection_time=30, max_retry_count=5)
    name = _push(env, client, args.task_id, args.directory)
    print(f"\nseeded {args.task_id} with {name}")


# --- create -----------------------------------------------------------------

def create_cmd(args):
    _check_task_id(args.task_id)
    env = settings.load_env()
    if args.timeout:
        env["SANDBOX_TIMEOUT_MINUTES"] = str(args.timeout)
    if args.keep_alive:
        env["KEEP_ALIVE_SECONDS"] = str(args.keep_alive)
    bootstrap_args = args.bootstrap_args or env.get("BOOTSTRAP_ARGS") or None

    path, task_env = settings.load_task_env(args.task_id, args.task_env)
    if path:
        print(f"task env: {path}")
        for key, value in sorted(task_env.items()):
            print(f"  {key:<24} {settings.redact(value)}")
    else:
        print("task env: none found — the sandbox gets no model credential.\n"
              "  copy sandbox/aio/task.env.example to sandbox/aio/task.env to add one.")

    request = faas.sandbox_request(env, args.task_id, args.template,
                                   task_env=task_env, bootstrap_args=bootstrap_args,
                                   writable_all=args.writable_all,
                                   extra_env=_extra_env(args.env))
    print("\nmounts:")
    for row in mounts.instance_rows(env, args.task_id, args.template,
                                    writable_all=args.writable_all):
        ro = "ro" if row["read_only"] else "rw"
        print(f"  {row['local_mount_path']:<16} {row['kind']:<4} {ro}  {row['backend']}")
    print(f"  {mounts.RUNTIME_MOUNT:<16} tos  ro  "
          f"{mounts.runtime_path(env)}   (from the application, not overridden)")
    print(f"\nmetadata: {request.metadata}")
    print(f"timeout:  {request.timeout} {request.timeout_unit}   "
          f"cpu={request.cpu_milli}m mem={request.memory_mb}MB")
    print("envs:")
    for e in request.envs:
        shown = settings.redact(e.value) if e.key in task_env else repr(e.value)
        print(f"  {e.key:<24} {shown}")

    if args.dry_run:
        print("\n--dry-run: not sending")
        return

    client = tos.connect(env, socket_timeout=180, connection_time=30, max_retry_count=5)
    if args.directory:
        print()
        _push(env, client, args.task_id, args.directory)

    api = faas.configure(env)

    # Guard: refuse to create a second sandbox for a task that already has one live.
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    _guard_resp = faas.list_sandboxes(api, function_id, metadata={"task": args.task_id})
    live = _guard_resp.sandboxes or []
    if live:
        ids = ", ".join(s.id for s in live)
        print(f"\nerror: task '{args.task_id}' already has live sandbox(es): {ids}")
        print("  use 'sbx task kill' first if you want to restart.")
        raise SystemExit(1)

    response = faas.create_sandbox(api, request)
    print(f"\nSandboxId: {response.sandbox_id}   assign={response.assign_status}")
    if response.assign_missed_reason:
        print(f"  assign_missed_reason: {response.assign_missed_reason}")
    print(f"\nWatch it:\n  sbx task status {args.task_id} --follow")


# --- reading the task prefix ------------------------------------------------

def _run_ids(client, bucket, prefix):
    """Run directory names under `<task>/runs/`, via delimiter listing.

    Walks no jsonl. Run ids start with a UTC stamp, so sorted()[-1] is newest.
    """
    return tos.prefixes(client, bucket, prefix + "runs/")


def _get_json(client, bucket, key):
    try:
        raw = client.get_object(bucket, key).read()
    except Exception:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        return None


def status_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    prefix = _prefix(env, args.task_id)
    client = tos.connect(env)
    seen = set()
    while True:
        done = _report(client, bucket, prefix, seen)
        if done or not args.follow:
            return
        time.sleep(10)


def _report(client, bucket, prefix, seen):
    # One GET, not a walk of runs/. Absent is fine — older runs never wrote it.
    current = _get_json(client, bucket, prefix + "status.json")
    if current and "status.json" not in seen:
        seen.add("status.json")
        markers = current.get("markers") or {}
        print(f"status.json  phase={current.get('phase')}  "
              f"iter={current.get('iteration')}/{current.get('max_iterations')}  "
              f"lives={current.get('lives')}  sandboxes={current.get('sandboxes')}  "
              f"done={current.get('done')}  verified={current.get('verified')}  "
              f"measuring={markers.get('measuring')}  blocked={markers.get('blocked')}")

    # One directory per run, so every run that started is visible — including the
    # ones that stood down because another run held the lease. A run that leaves
    # nothing behind is indistinguishable from one that never started.
    results = []
    for run_id in sorted(_run_ids(client, bucket, prefix)):
        if run_id in seen:
            continue
        body = _get_json(client, bucket, f"{prefix}runs/{run_id}/result.json")
        if body is None:
            continue
        seen.add(run_id)
        results.append(body)
        line = (f"\n{body.get('run_id') or run_id}\n"
                f"  verdict: {body.get('verdict')}  failures: {body.get('failures')}"
                f"  lease: {body.get('lease')}")
        if body.get("verdict") == "stood-down":
            holder = body.get("holder") or {}
            line += f"\n  stood down for {holder.get('run_id')}"
        else:
            line += (f"\n  attach: {body.get('attach')}"
                     f"  files: {body.get('restored_files')}"
                     f"  archived: {body.get('archived')}"
                     f"  done: {body.get('done')}")
        print(line)
    return bool(results)


def logs_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    prefix = _prefix(env, args.task_id)
    client = tos.connect(env)

    run_id = args.run
    if not run_id:
        runs = _run_ids(client, bucket, prefix)
        if not runs:
            sys.exit(f"no runs under {bucket}:/{prefix}runs/")
        run_id = sorted(runs)[-1]
        print(f"# {run_id}\n", file=sys.stderr)
    print(client.get_object(bucket, f"{prefix}runs/{run_id}/bootstrap.log").read().decode())


_TRACE_OUTPUT = re.compile(r"(?:^|/)runs/([^/]+)/iterations/(\d{4})/(output-[^/]+\.jsonl)$")
_TRACE_STATUS = re.compile(r"(?:^|/)runs/([^/]+)/iterations/(\d{4})/status\.json$")


def _trace_objects(objects, run_id=None, iteration=None):
    """Return immutable output/status objects grouped by selected run."""
    grouped = {}
    for obj in objects:
        match = _TRACE_OUTPUT.search(obj.key)
        if match:
            run, number, _name = match.groups()
            if run_id and run != run_id:
                continue
            if iteration is not None and int(number) != iteration:
                continue
            grouped.setdefault((run, int(number)), {"output": [], "status": None})["output"].append(obj)
            continue
        match = _TRACE_STATUS.search(obj.key)
        if match:
            run, number = match.groups()
            if run_id and run != run_id:
                continue
            if iteration is not None and int(number) != iteration:
                continue
            grouped.setdefault((run, int(number)), {"output": [], "status": None})["status"] = obj
    return grouped


def _event_text(event):
    text = event.get("text")
    message = event.get("message")
    if text is None and isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            text = " ".join(
                str(item.get("text", item.get("content", "")))
                for item in content
                if isinstance(item, dict) and item.get("type") in ("text", "tool_result", "tool_use")
            )
    if text is None:
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                text = " ".join(str(item.get("text", item)) if isinstance(item, dict) else str(item)
                                for item in content)
            elif content is not None:
                text = content
        if text is None:
            text = event.get("content", event.get("error", ""))
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False, sort_keys=True)
    return str(text or "").replace("\n", " ")


def _format_event(event, iteration):
    event_type = event.get("type", "event")
    timestamp = event.get("timestamp") or event.get("created_at") or event.get("time") or "-"
    tool = event.get("name") or event.get("tool_name") or event.get("tool")
    if not tool and isinstance(event.get("message"), dict):
        blocks = event["message"].get("content") or []
        tool = next((block.get("name") for block in blocks
                     if isinstance(block, dict) and block.get("type") == "tool_use"), None)
    label = event_type
    if tool:
        label += f" {tool}"
    text = _event_text(event)
    if len(text) > 160:
        text = text[:157] + "..."
    return f"{timestamp}  iteration {iteration}  {label}: {text}".rstrip()


def _trace_fetch(client, bucket, objects):
    """Yield (obj, body) for each object, downloaded concurrently, in input order.

    `ThreadPoolExecutor.map` submits everything up front but hands results back
    in the order given, so the caller still prints a trace in sequence while the
    round trips overlap. Objects are ~13 KB each; holding a run's worth in
    flight is a few tens of MB.
    """
    def body(obj):
        data = client.get_object(bucket, obj.key).read()
        return data.encode() if isinstance(data, str) else data

    if not objects:
        return
    with ThreadPoolExecutor(max_workers=_TRACE_FETCH_WORKERS) as pool:
        yield from zip(objects, pool.map(body, objects))


def _trace_done(client, bucket, groups):
    """Read selected statuses and report whether follow mode can stop."""
    complete = False
    incomplete = False
    for group in groups.values():
        status_obj = group["status"]
        if not status_obj:
            continue
        try:
            body = client.get_object(bucket, status_obj.key).read()
            if isinstance(body, str):
                body = body.encode()
            status = json.loads(body)
        except (ValueError, TypeError):
            continue
        if status.get("complete") is True:
            complete = True
        else:
            incomplete = True
    return complete, incomplete


def _trace_result_exists(client, bucket, prefix, run_id):
    return _get_json(client, bucket, f"{prefix}runs/{run_id}/result.json") is not None


def _trace_listing_prefix(prefix, run_id, iteration):
    """Narrowest prefix that still contains the requested jsonl.

    A full `runs/` walk is 10k jsonl objects on a long task. One run is
    hundreds; one iteration is tens.
    """
    base = prefix + "runs/" + run_id + "/iterations/"
    if iteration is not None:
        return base + f"{iteration:04d}/"
    return base


def trace_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    prefix = _prefix(env, args.task_id)
    client = tos.connect(env)
    seen = set()
    selected_run = args.run
    printed_any = False
    announced_run = False

    while True:
        if not selected_run:
            runs = _run_ids(client, bucket, prefix)
            if runs:
                selected_run = sorted(runs)[-1]
        if not selected_run:
            objects = []
        else:
            objects = tos.listing(
                client, bucket,
                _trace_listing_prefix(prefix, selected_run, args.iteration))
        groups = _trace_objects(objects, selected_run, args.iteration)
        output_objects = [obj for group in groups.values() for obj in group["output"]]
        output_objects.sort(key=lambda obj: obj.key)

        if selected_run and not args.raw and output_objects and not announced_run:
            print(f"# run {selected_run}")
            announced_run = True

        pending = [obj for obj in output_objects if obj.key not in seen]
        seen.update(obj.key for obj in pending)
        if pending:
            printed_any = True

        for obj, data in _trace_fetch(client, bucket, pending):
            if args.raw:
                sys.stdout.write(data.decode("utf-8", errors="replace"))
                sys.stdout.flush()
                continue
            iteration = int(_TRACE_OUTPUT.search(obj.key).group(2))
            for line in data.splitlines():
                try:
                    event = json.loads(line)
                except (ValueError, TypeError):
                    print(f"-  iteration {iteration}: {line.decode(errors='replace')}")
                    continue
                print(_format_event(event, iteration))

        complete, incomplete = _trace_done(client, bucket, groups)
        terminal = bool(selected_run and _trace_result_exists(
            client, bucket, prefix, selected_run))
        if not args.follow:
            if not printed_any:
                sys.exit("no trace objects under selected task/run")
            if not args.raw and incomplete and not complete:
                print("status: incomplete")
            return
        if complete or terminal:
            return
        time.sleep(5)


def get_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    prefix = _prefix(env, args.task_id)
    client = tos.connect(env)
    client.get_object_to_file(bucket, prefix + args.key, args.destination)
    print(f"{prefix}{args.key} -> {args.destination}")


# --- live sandboxes ---------------------------------------------------------

def _sandboxes(api, env, metadata=None, status=None):
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    response = faas.list_sandboxes(api, function_id, metadata=metadata, status=status)
    return response.sandboxes or []


def list_cmd(args):
    env = settings.load_env()
    api = faas.configure(env)
    metadata = dict(pair.split("=", 1) for pair in args.metadata) or None
    sandboxes = _sandboxes(api, env, metadata=metadata, status=args.status)
    if not sandboxes:
        print("no sandboxes")
        return
    for s in sandboxes:
        print(f"  {s.id}  {getattr(s, 'status', '?'):<10} {_format_labels(s)}")
    if metadata:
        # Whether the server honours the metadata filter is unverified, so the
        # count is printed as a check the reader can make rather than an
        # assurance: a filter that is silently ignored looks exactly like a
        # filter that matched everything.
        print(f"\n{len(sandboxes)} returned for metadata={metadata} — if that is every\n"
              "sandbox you have, the server ignored the filter.")


def _labels(sandbox):
    """The metadata dict, whichever shape this response uses.

    ListSandboxes returns a plain `metadata` dict; DescribeSandbox returns a
    `metadata_list` of meta_key/meta_value objects. Same labels either way, so
    normalise here rather than at each call site.
    """
    if getattr(sandbox, "metadata", None):
        return dict(sandbox.metadata)
    return {m.meta_key: m.meta_value
            for m in (getattr(sandbox, "metadata_list", None) or [])
            if getattr(m, "meta_key", None)}


def _format_labels(sandbox):
    labels = _labels(sandbox)
    return " ".join(f"{k}={v}" for k, v in sorted(labels.items())) or "(no metadata)"


def kill_cmd(args):
    env = settings.load_env()
    api = faas.configure(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")

    if args.sandbox:
        targets = [args.sandbox]
    elif args.all:
        targets = [s.id for s in _sandboxes(api, env)]
    elif args.task_id:
        # Ask the server to filter, then filter again here on what came back.
        # If the server ignores `metadata` this still kills only the right task's
        # sandboxes; if it honours it, the second pass costs nothing.
        wanted = {"task": args.task_id}
        candidates = _sandboxes(api, env, metadata=wanted)
        targets = [s.id for s in candidates
                   if _labels(s).get("task") == args.task_id]
        if candidates and not targets:
            print(f"{len(candidates)} sandboxes came back but none is labelled "
                  f"task={args.task_id} — refusing to kill them.\n"
                  "Use --sandbox <id> if you meant a specific one.")
    else:
        sys.exit("give a task id, --sandbox <id>, or --all")

    if not targets:
        print("nothing to kill")
        return
    for sandbox_id in targets:
        faas.kill_sandbox(api, function_id, sandbox_id)
        print(f"  killed {sandbox_id}")

    # Wait for the platform to actually reclaim the instances before returning,
    # so a `kill` followed immediately by `create` never races the lease heartbeat.
    print("  waiting for sandbox(es) to clear …", end="", flush=True)
    for _ in range(24):  # up to ~120s
        time.sleep(5)
        remaining = faas.list_sandboxes(api, function_id,
                                        metadata={"task": args.task_id} if args.task_id else None)
        live = [s for s in (remaining.sandboxes or []) if s.id in targets]
        if not live:
            print(" gone")
            return
        print(".", end="", flush=True)
    print(" timed out (sandbox may still be shutting down)")
