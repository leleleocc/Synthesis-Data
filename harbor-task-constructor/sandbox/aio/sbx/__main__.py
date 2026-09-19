"""Dispatch. `sandbox/aio/sbx.sh <group> <command> ...`

    sbx app       show / sync                 the application's mount points
    sbx runtime   publish / show              bootstrap.sh + runner/ on TOS
    sbx template  publish / list / show       one tenant's instructions
    sbx task      create / push / status / logs / get / list / kill
    sbx batch     push / status / reconcile / list   N candidates, one nested task each
    sbx probe     describe / instances / logs / revision / timeout
"""

import argparse
import sys

from . import cmd_app, cmd_batch, cmd_probe, cmd_runtime, cmd_task, cmd_template

GROUPS = (
    ("app", cmd_app, "read and rewrite the application's mount points"),
    ("runtime", cmd_runtime, "publish bootstrap.sh and the runner package"),
    ("template", cmd_template, "publish a tenant's PROMPT.md / init.sh / verify.sh"),
    ("task", cmd_task, "package a tree, start a sandbox, read back what it did"),
    ("batch", cmd_batch, "upload N candidates and reconcile their sandboxes"),
    ("probe", cmd_probe, "read-only platform diagnostics"),
)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="sbx", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    groups = parser.add_subparsers(dest="group")
    for name, module, help_text in GROUPS:
        group = groups.add_parser(name, help=help_text)
        module.add_arguments(group.add_subparsers(dest="command"))
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
