"""`sbx probe` — read the platform back.

Every command here is read-only except `timeout`. They are grouped apart from
`task` and `app` because they are diagnostic: nothing in the normal path calls
them. They were written to turn the guesses in TODO section 0 into printed
facts, and that job is done — what keeps them is that a sandbox which fails
before `bootstrap.sh` runs leaves nothing in TOS, and then `probe describe` and
`probe logs` are the only account of it there is.
"""

import sys

from . import faas, mounts, settings


def add_arguments(sub):
    describe = sub.add_parser("describe", help="everything the platform says about one sandbox")
    describe.add_argument("sandbox_id")
    describe.set_defaults(func=describe_cmd)

    instances = sub.add_parser("instances", help="list function instances")
    instances.set_defaults(func=instances_cmd)

    logs = sub.add_parser("logs", help="GetFunctionInstanceLogs for one instance")
    logs.add_argument("name", help="instance name from `sbx probe instances`")
    logs.add_argument("--limit", type=int, default=200)
    logs.set_defaults(func=logs_cmd)

    revision = sub.add_parser("revision", help="one revision's mount configuration")
    revision.add_argument("number", type=int, nargs="?",
                          help="revision number (default: the stable one)")
    revision.set_defaults(func=revision_cmd)

    timeout = sub.add_parser("timeout", help="SetSandboxTimeout, then re-read expire_at")
    timeout.add_argument("sandbox_id")
    timeout.add_argument("minutes", type=int)
    timeout.set_defaults(func=timeout_cmd)


def _api(env):
    return faas.configure(env)


def describe_cmd(args):
    env = settings.load_env()
    api = _api(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    s = faas.describe_sandbox(api, function_id, args.sandbox_id)

    print(f"sandbox {s.id}")
    print(f"  status:          {s.status}   assign={s.assign_status} pending={s.pending}")
    print(f"  created_at:      {s.created_at}   expire_at: {s.expire_at}")
    # Which revision an instance actually runs decides whether `sbx app sync`
    # has to be released before it takes effect, or whether the draft is enough.
    print(f"  revision_number: {s.revision_number}")
    print(f"  role_trn:        {s.role_trn or '(none — the credential boundary holds)'}")
    if s.error_code or s.error_message:
        print(f"  error:           {s.error_code} {s.error_message}")

    print("\n  metadata_list:")
    items = s.metadata_list or []
    for m in items:
        print(f"    {m.meta_key}={m.meta_value}")
    if not items:
        print("    (empty — the server dropped the metadata we sent)")

    print("\n  TOS mounts:")
    _print_tos(s.instance_tos_mount_config)
    print("\n  NAS mounts:")
    _print_nas(s.instance_nas_mount_config)

    print("\n  This is the answer to 'overlay or wholesale replacement': if only the\n"
          "  paths the create request narrowed appear above, the instance config\n"
          "  replaced the application's; if /mnt/runtime is here too, it overlays.")


def _print_tos(config):
    points = (config.tos_mount_points if config else None) or []
    if config is not None and getattr(config, "mode", None):
        print(f"    mode={config.mode}  enable={config.enable}")
    for p in points:
        ro = "ro" if p.read_only else "rw"
        print(f"    {p.local_mount_path:<16} {ro}  {p.bucket_name}:{p.bucket_path}"
              f"  pre_mount={p.pre_mount}")
    if not points:
        print("    (none)")


def _print_nas(config):
    points = (config.nas_mount_points if config else None) or []
    for p in points:
        print(f"    {p.local_mount_path:<16} rw  {p.remote_path}")
    if not points:
        print("    (none)")


def instances_cmd(args):
    env = settings.load_env()
    api = _api(env)
    response = faas.list_instances(api, settings.need(env, "VEFAAS_FUNCTION_ID"))
    print(f"total: {response.total}")
    for item in response.items or []:
        print(f"  {item.instance_name}  {item.instance_status:<10} "
              f"rev={item.revision_number}  created={item.creation_time}  "
              f"expire={item.expire_at}")
    if not response.items:
        print("  (none — a sandbox is not necessarily a function instance)")


def logs_cmd(args):
    env = settings.load_env()
    api = _api(env)
    response = faas.instance_logs(api, settings.need(env, "VEFAAS_FUNCTION_ID"),
                                  args.name, limit=args.limit)
    if not response.logs:
        print("(empty — so this is not the channel the startup command's stdout "
              "goes to)", file=sys.stderr)
        return
    print(response.logs)


def revision_cmd(args):
    env = settings.load_env()
    api = _api(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    number = args.number
    if number is None:
        number = faas.release_status(api, function_id).stable_revision_number
        print(f"# stable revision {number}\n")
    r = faas.get_revision(api, function_id, number)
    print(f"revision {r.revision_number}  created={r.revision_creation_time}")
    print(f"  description: {r.revision_description}")
    print("\n  TOS:")
    points = (r.tos_mount_config.mount_points if r.tos_mount_config else None) or []
    for p in points:
        ro = "ro" if p.read_only else "rw"
        print(f"    {p.local_mount_path:<16} {ro}  {p.bucket_name}:{p.bucket_path}")
    print("  NAS:")
    configs = (r.nas_storage.nas_configs if r.nas_storage else None) or []
    for c in configs:
        print(f"    {c.local_mount_path:<16} rw  {c.file_system_id}:{c.remote_path}"
              f"  uid={c.uid} gid={c.gid}")

    expected = {row["local_mount_path"] for row in mounts.app_rows(env)}
    got = {p.local_mount_path for p in points} | {c.local_mount_path for c in configs}
    missing = expected - got
    if missing:
        print(f"\n  missing from this revision: {sorted(missing)}\n"
              "  an instance cannot mount a path the application does not declare.")


def timeout_cmd(args):
    env = settings.load_env()
    api = _api(env)
    function_id = settings.need(env, "VEFAAS_FUNCTION_ID")
    before = faas.describe_sandbox(api, function_id, args.sandbox_id)
    print(f"expire_at before: {before.expire_at}")
    faas.set_timeout(api, function_id, args.sandbox_id, args.minutes)
    after = faas.describe_sandbox(api, function_id, args.sandbox_id)
    print(f"expire_at after:  {after.expire_at}")
    if before.expire_at == after.expire_at:
        print("unchanged — SetSandboxTimeout does not apply to a running sandbox.")
