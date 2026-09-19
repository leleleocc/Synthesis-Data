"""`sbx app` — read and rewrite the application's mount points.

The application is the allow-list: an instance can only swap the backend of a
`local_mount_path` declared here, so `sync` is what decides which mounts are
available to any task at all. It rewrites all four from `mounts.TABLE` rather
than editing what is there, because a mount that has fallen out of the table is
a mount that should no longer exist.
"""

import time

from . import faas, mounts, settings, tos


def add_arguments(sub):
    show = sub.add_parser("show", help="read the current application configuration")
    show.set_defaults(func=show_cmd)

    sync = sub.add_parser("sync", help="write the mount table to the application")
    sync.add_argument("--dry-run", action="store_true",
                      help="print the four mount points without sending anything")
    sync.add_argument("--writable-all", action="store_true",
                      help="declare every mount read-write, for the round where the "
                           "read-only prefixes have no content yet")
    sync.add_argument("--no-release", action="store_true",
                      help="update the draft without releasing it")
    sync.set_defaults(func=sync_cmd)


def show_cmd(args):
    env = settings.load_env()
    api = faas.configure(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")

    fn = faas.get_function(api, function_id)
    print(f"function {fn.id}  ({fn.name})")
    print(f"  last_update_time: {fn.last_update_time}")
    print(f"  command:          {fn.command}")
    print(f"  port:             {fn.port}   request_timeout: {fn.request_timeout}")
    print()
    _print_mounts(fn)

    status = faas.release_status(api, function_id)
    print(f"\nrelease: stable={status.stable_revision_number} "
          f"status={status.status} traffic={status.current_traffic_weight}")
    if status.status_message:
        print(f"  {status.status_message}")

    revisions = faas.list_revisions(api, function_id)
    print(f"revisions: total={revisions.total}")


def _print_mounts(fn):
    tos_config = fn.tos_mount_config
    points = (tos_config.mount_points if tos_config else None) or []
    print(f"  TOS (enable={getattr(tos_config, 'enable_tos', None)}):")
    for p in points:
        ro = "ro" if p.read_only else "rw"
        print(f"    {p.local_mount_path:<16} {ro}  {p.bucket_name}:{p.bucket_path}")
    if not points:
        print("    (none)")

    nas = fn.nas_storage
    configs = (nas.nas_configs if nas else None) or []
    print(f"  NAS (enable={getattr(nas, 'enable_nas', None)}):")
    for c in configs:
        print(f"    {c.local_mount_path:<16} rw  {c.file_system_id}:{c.remote_path}"
              f"  uid={c.uid} gid={c.gid}  {c.mount_point_id}")
    if not configs:
        print("    (none)")


def sync_cmd(args):
    env = settings.load_env()
    rows = mounts.app_rows(env, writable_all=args.writable_all)
    api = faas.configure(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    # Read before writing: the NAS filesystem and mount point are carried forward
    # from what is live rather than retyped, and the dry-run below then prints the
    # request that would actually be sent.
    current = faas.get_function(api, function_id)

    print("mount table to declare:")
    for row in rows:
        ro = "ro" if row["read_only"] else "rw"
        print(f"  {row['local_mount_path']:<16} {row['kind']:<4} {ro}  {row['backend']}")
        print(f"  {'':<16} {'':<4}      {row['purpose']}")
    if args.writable_all:
        print("\n  --writable-all: every mount read-write this round. Run `sbx app sync`\n"
              "  without it once the runtime and templates are published, to tighten.")

    print("\ncurrently declared:")
    _print_mounts(current)

    keeps = mounts.prefixes_needing_keep(env)
    print(f"\nprefixes that must exist first: {len(keeps)}")
    for prefix in keeps:
        print(f"  {prefix}")

    request = faas.update_request(env, current, writable_all=args.writable_all)

    if args.dry_run:
        print("\nUpdateFunction request:")
        print(request)
        print("\n--dry-run: not sending")
        return

    # A TOS mount whose backend prefix holds no object is rejected at
    # configuration time, and the `_unassigned` backends are empty by design —
    # so is `_runtime/v1` until the first publish. One zero-byte marker satisfies
    # the check without giving the prefix any content.
    bucket = settings.need(env, "TOS_BUCKET")
    client = tos.connect(env)
    print()
    for prefix in keeps:
        key = tos.key_for(prefix)
        created = tos.touch_keep(client, bucket, key)
        print(f"  {'wrote' if created else 'present'}  {key}.keep")

    before = faas.release_status(api, function_id)
    print(f"\ncurrent stable revision: {before.stable_revision_number} "
          "(roll back to this if the new one misbehaves)")

    faas.update_function(api, request)
    print("UpdateFunction ok — the draft now carries the table above")

    if args.no_release:
        print("--no-release: the draft is not live. `sbx app sync` again to publish.")
        return

    # Revision 0 is the draft; releasing it is what mints a new numbered revision
    # and points traffic at it. Nothing an instance sees changes until this runs.
    faas.release(api, function_id, 0, description="sbx app sync")
    print("Release requested — polling …")
    _await_release(api, function_id, before.stable_revision_number)


def _await_release(api, function_id, previous, timeout=300):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        status = faas.release_status(api, function_id)
        line = f"  {status.status}  stable={status.stable_revision_number}"
        if line != last:
            print(line)
            last = line
        if status.status in ("done", "succeeded") and \
                status.stable_revision_number != previous:
            print(f"released revision {status.stable_revision_number}")
            return
        if status.status in ("failed", "aborted"):
            print(f"release {status.status}: {status.status_message}")
            print(f"  error_code: {status.error_code}")
            if status.failed_instance_logs:
                print(status.failed_instance_logs)
            return
        time.sleep(5)
    print(f"still not settled after {timeout}s — check `sbx app show`")
