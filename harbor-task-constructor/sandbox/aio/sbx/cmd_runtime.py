"""`sbx runtime` — publish bootstrap.sh and the runner package to TOS.

The runtime is the one thing every sandbox mounts identically: `/mnt/runtime`,
read-only, shared. It is versioned because it is shared — a fix pushed in place
would change what every running task is about to import, and a task that fails
after such a push gives no way to tell which runtime it actually ran.
"""

import os
import sys

from . import mounts, settings, tos


def add_arguments(sub):
    publish = sub.add_parser("publish", help="upload bootstrap.sh + runner/ to TOS")
    publish.add_argument("--version", help="runtime version directory (default: RUNTIME_VERSION or v1)")
    publish.add_argument("--dry-run", action="store_true")
    publish.set_defaults(func=publish_cmd)

    show = sub.add_parser("show", help="list what is published under a runtime version")
    show.add_argument("--version")
    show.set_defaults(func=show_cmd)


def _files():
    """bootstrap.sh plus every runner module, listed from disk.

    Listed rather than hardcoded so a new module cannot be added locally and
    silently left out — which would fail at import time inside the sandbox,
    where it is most expensive to notice.
    """
    here = settings.HERE
    bootstrap = os.path.join(here, "bootstrap.sh")
    if not os.path.exists(bootstrap):
        sys.exit(f"missing {bootstrap}")
    runner = os.path.join(here, "runner")
    names = sorted(f for f in os.listdir(runner) if f.endswith(".py"))
    if "__main__.py" not in names:
        sys.exit("sandbox/aio/runner/__main__.py is missing")
    return [("bootstrap.sh", bootstrap)] + [
        (f"runner/{n}", os.path.join(runner, n)) for n in names]


def publish_cmd(args):
    env = settings.load_env()
    version = args.version or mounts.runtime_version(env)
    prefix = tos.key_for(mounts.runtime_path(env, version))
    bucket = settings.need(env, "TOS_BUCKET")
    files = _files()

    print(f"publishing runtime {version} to {bucket}:/{prefix}")
    for rel, path in files:
        print(f"  {rel:<28} {os.path.getsize(path):>10,} B")
    if args.dry_run:
        print("\n--dry-run: not sending")
        return

    client = tos.connect(env, socket_timeout=180, connection_time=30, max_retry_count=5)
    print()
    for rel, path in files:
        tos.put(client, bucket, prefix + rel, path, rel)

    print(f"\npublished {len(files)} files.")
    if version != mounts.runtime_version(env):
        print(f"note: the application mounts {mounts.runtime_version(env)}. To switch,\n"
              f"      set RUNTIME_VERSION={version} in .env and run `sbx app sync`.")


def show_cmd(args):
    env = settings.load_env()
    version = args.version or mounts.runtime_version(env)
    prefix = tos.key_for(mounts.runtime_path(env, version))
    bucket = settings.need(env, "TOS_BUCKET")
    client = tos.connect(env)
    objects = tos.listing(client, bucket, prefix)
    print(f"{bucket}:/{prefix}  ({len(objects)} objects)")
    for o in sorted(objects, key=lambda o: o.key):
        print(f"  {o.size:>10,}  {o.last_modified:%Y-%m-%d %H:%M:%S}  {o.key[len(prefix):]}")
