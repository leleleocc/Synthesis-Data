"""`sbx template` — publish one tenant's instructions to TOS.

A template is what makes this scaffold general: the runner is fixed, and
everything task-specific — the prompt, the setup, the check — arrives as files
under `/mnt/template`. A template holds no credentials and no data; it is read
by the agent, so anything in it is content the agent may act on.

    PROMPT.md    piped to the constructor on stdin
    init.sh      run once before construction, for whatever the tree needs
    verify.sh    run to decide whether the work is done
    roles/*.md   read by the agent by path, which is why /mnt/template has to be
                 reachable from its cwd tree (--add-dir)
"""

import os
import sys

from . import mounts, settings, tos

# Not required — a template may legitimately be prompt-only — but named here so
# `publish` can say which of them is missing rather than leaving that to the
# first sandbox that tries to use it.
EXPECTED = ("PROMPT.md", "init.sh", "verify.sh")


def add_arguments(sub):
    publish = sub.add_parser("publish", help="upload a template directory to TOS")
    publish.add_argument("directory")
    publish.add_argument("--name", help="template name (default: the directory's name)")
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=publish_cmd)

    ls = sub.add_parser("list", help="list published templates")
    ls.set_defaults(func=list_cmd)

    show = sub.add_parser("show", help="list one template's files")
    show.add_argument("name")
    show.set_defaults(func=show_cmd)


def publish_cmd(args):
    env = settings.load_env()
    directory = args.directory.rstrip("/")
    if not os.path.isdir(directory):
        sys.exit(f"no such directory: {directory}")
    name = args.name or os.path.basename(os.path.abspath(directory))
    if name.startswith("_"):
        sys.exit(f"template names may not start with '_' — {mounts.UNASSIGNED} and the "
                 "other reserved prefixes do")

    prefix = tos.key_for(mounts.template_path(env, name))
    bucket = settings.need(env, "TOS_BUCKET")

    print(f"template {name} from {directory}")
    for expected in EXPECTED:
        mark = "ok " if os.path.exists(os.path.join(directory, expected)) else "-- "
        print(f"  {mark} {expected}")
    print(f"  -> {bucket}:/{prefix}")

    if args.dry_run:
        print("\n--dry-run: not sending")
        return

    client = tos.connect(env, socket_timeout=180, connection_time=30, max_retry_count=5)
    print()
    sent = tos.put_tree(client, bucket, prefix, directory, label=name)
    print(f"\npublished {sent} files. Use it with:\n"
          f"  sbx task create <task-id> <dir> --template {name}")


def list_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    root = tos.key_for(f"{mounts.tos_base(env)}/{mounts.TEMPLATE_PREFIX}")
    client = tos.connect(env)
    names = {}
    for o in tos.listing(client, bucket, root):
        rest = o.key[len(root):]
        if "/" not in rest:
            continue
        head = rest.split("/", 1)[0]
        names.setdefault(head, 0)
        if not o.key.endswith("/.keep"):
            names[head] += 1
    if not names:
        print(f"no templates under {bucket}:/{root}")
        return
    for name in sorted(names):
        note = "  (empty — the placeholder that keeps the prefix mountable)" \
            if not names[name] else ""
        print(f"  {name:<24} {names[name]:>3} files{note}")


def show_cmd(args):
    env = settings.load_env()
    bucket = settings.need(env, "TOS_BUCKET")
    prefix = tos.key_for(mounts.template_path(env, args.name))
    client = tos.connect(env)
    objects = tos.listing(client, bucket, prefix)
    print(f"{bucket}:/{prefix}  ({len(objects)} objects)")
    for o in sorted(objects, key=lambda o: o.key):
        print(f"  {o.size:>10,}  {o.last_modified:%Y-%m-%d %H:%M:%S}  {o.key[len(prefix):]}")
