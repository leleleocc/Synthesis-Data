"""The in-sandbox runner for the AIO Sandbox path.

Standard library only, on purpose. This package is exec'd on the startup path,
before anything has had a chance to install packages, so a dependency here would
be a network round trip standing between the instance and its first line of log.

Layout it owns. The task-scoped mounts are already narrowed to one task by
CreateSandbox, so no path below either repeats the task id:

    /mnt/runtime/runner/                this package, read-only and shared
    /mnt/template/                      the tenant's prompt and scripts, read-only
    /mnt/task/archives/<stamp>.tar.gz   ready archives + .sha256 + .manifest.json
    /mnt/task/seed/                     the starting tree, used only until the
                                        first archive exists
    /mnt/task/runs/<run-id>/            one directory per run, append-only
    /home/app/workspace/                the tree
    /home/app/.lease/                   owner + heartbeat
"""
