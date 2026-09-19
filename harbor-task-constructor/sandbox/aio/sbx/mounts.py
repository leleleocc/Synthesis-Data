"""The four mount points, written down once.

Both `sbx app sync` (which declares them on the application) and `sbx task
create` (which narrows them for one instance) generate their requests from this
table, so "what the application allows" and "what an instance asks for" cannot
drift apart.

    in the sandbox   backed by                          narrowed per instance
    /mnt/runtime     TOS <base>/_runtime/<version>      no — the release picks
    /mnt/template    TOS <base>/_templates/<name>       yes
    /mnt/task        TOS <base>/<task-id>               yes
    /home/app        NAS <nas-base>/<task-id>           yes

Two properties are load-bearing and easy to undo by accident:

**The application entry is an allow-list slot, not a backend.** An instance can
only swap the backend of a `local_mount_path` the application already declares;
a path the application never mentions cannot be mounted at instance level at
all. So every row needs an application entry even when the instance always
overrides it.

**Every application-level backend points at a dead prefix.** An instance that
forgets to narrow therefore gets an empty directory rather than every tenant's
data. `/mnt/task` backed by the bare `<base>` would hand any such instance the
whole bucket path — that is the failure this table is shaped to make impossible,
and it is the same reasoning as the read-only flags: put the mistake somewhere
it cannot happen (TODO.md sections 4 and 5).

**A read-only TOS mount requires its prefix to already exist**, so `app sync`
writes a `.keep` object under each prefix it is about to declare. That is also
what lets `_unassigned` be simultaneously declarable and empty.
"""

UNASSIGNED = "_unassigned"

# Prefixes that hold shared, non-task data. A task id may not start with "_", so
# no tenant can ever address one of these by naming a task after it.
RUNTIME_PREFIX = "_runtime"
TEMPLATE_PREFIX = "_templates"


class Mount:
    """One row of the table above.

    `app_suffix` is the dead default declared on the application; `instance` is
    the callable that narrows it for one sandbox, or None when the application's
    value is the real one.
    """

    def __init__(self, local_path, kind, app_suffix, read_only=False, instance=None,
                 purpose=""):
        self.local_path = local_path
        self.kind = kind
        self.app_suffix = app_suffix
        self.read_only = read_only
        self.instance = instance
        self.purpose = purpose


def tos_base(env):
    return (env.get("TOS_BUCKET_PATH") or "/sandbox").rstrip("/")


def nas_base(env):
    return (env.get("NAS_REMOTE_PATH") or "/harbor").rstrip("/")


def runtime_version(env):
    return env.get("RUNTIME_VERSION") or "v1"


def runtime_path(env, version=None):
    return f"{tos_base(env)}/{RUNTIME_PREFIX}/{version or runtime_version(env)}"


def template_path(env, name):
    return f"{tos_base(env)}/{TEMPLATE_PREFIX}/{name}"


def task_path(env, task_id):
    return f"{tos_base(env)}/{task_id}"


def nas_task_path(env, task_id):
    return f"{nas_base(env)}/{task_id}"


TABLE = (
    Mount(
        "/mnt/runtime", "tos",
        lambda env: runtime_path(env),
        read_only=True, instance=None,
        purpose="bootstrap.sh + runner/, shared by every sandbox",
    ),
    Mount(
        "/mnt/template", "tos",
        lambda env: template_path(env, UNASSIGNED),
        read_only=True,
        instance=lambda env, task_id, template: template_path(env, template),
        purpose="the tenant's PROMPT.md, init.sh, verify.sh, roles/",
    ),
    Mount(
        "/mnt/task", "tos",
        lambda env: f"{tos_base(env)}/{UNASSIGNED}",
        read_only=False,
        instance=lambda env, task_id, template: task_path(env, task_id),
        purpose="this task's seed/, archives/, runs/ — the only writable TOS mount",
    ),
    Mount(
        "/home/app", "nas",
        lambda env: f"{nas_base(env)}/{UNASSIGNED}",
        read_only=False,
        instance=lambda env, task_id, template: nas_task_path(env, task_id),
        purpose="the working tree, at /home/app/workspace",
    ),
)


def by_path(local_path):
    for mount in TABLE:
        if mount.local_path == local_path:
            return mount
    raise KeyError(local_path)


RUNTIME_MOUNT = "/mnt/runtime"
TEMPLATE_MOUNT = "/mnt/template"
TASK_MOUNT = "/mnt/task"
NAS_MOUNT = "/home/app"


def app_rows(env, writable_all=False):
    """The application's declaration: one row per mount, dead backends.

    `writable_all` exists for the bring-up ordering: a read-only mount needs its
    prefix to exist, but the prefixes for runtime and templates only get content
    by being mounted and written to. Come up writable, publish the content, then
    sync again without the flag to tighten.
    """
    rows = []
    for mount in TABLE:
        rows.append({
            "local_mount_path": mount.local_path,
            "kind": mount.kind,
            "backend": mount.app_suffix(env),
            "read_only": False if writable_all else mount.read_only,
            "purpose": mount.purpose,
        })
    return rows


def instance_rows(env, task_id, template, writable_all=False):
    """What one sandbox asks for: the same paths, narrowed to this task.

    Rows whose `instance` is None are left out on purpose — the application's
    value is the real one and repeating it here would put the choice of runtime
    version back into every create call, which is exactly what moving it to the
    application was for.

    `writable_all` matches the flag on `app_rows`, and for the same reason: while
    the read-only prefixes are still empty, asking for a read-only mount of one
    is asking for a path that does not exist yet.
    """
    rows = []
    for mount in TABLE:
        if mount.instance is None:
            continue
        rows.append({
            "local_mount_path": mount.local_path,
            "kind": mount.kind,
            "backend": mount.instance(env, task_id, template),
            "read_only": False if writable_all else mount.read_only,
        })
    return rows


def prefixes_needing_keep(env, template=None):
    """TOS prefixes that must contain an object before they can be mounted."""
    wanted = [row["backend"] for row in app_rows(env) if row["kind"] == "tos"]
    if template:
        wanted.append(template_path(env, template))
    return sorted(set(wanted))
