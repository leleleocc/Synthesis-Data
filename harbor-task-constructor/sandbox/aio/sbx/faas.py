"""veFaaS: the platform calls, and the two requests that are worth building here.

Two shapes of call live in this file. The thin wrappers at the bottom are one
line each and exist so the command modules never touch `volcenginesdkvefaas`
directly. The two builders — `update_request` and `sandbox_request` — are not
thin, because they are where the mount table becomes an API call, and getting
them wrong is how an instance ends up looking at another task's data.

The AK/SK read here never leave the host. `sandbox_request` deliberately never
sets `role_trn` or `role_chain_trn`: an instance with a role could call this same
API, and the whole reason an unsupervised `--dangerously-skip-permissions` agent
is tolerable inside the sandbox is that it cannot (TODO.md section 3).
"""

import sys

import volcenginesdkcore
import volcenginesdkvefaas
from volcenginesdkcore.rest import ApiException

from . import mounts, settings


def configure(env):
    configuration = volcenginesdkcore.Configuration()
    configuration.region = env.get("VOLC_REGION") or "cn-beijing"
    # Static keys are optional. With ak/sk left empty and no credential_provider
    # set, SignRequestInterceptor attaches DefaultCredentialProvider itself
    # (sign_request_interceptor.py:36), which walks env vars -> OIDC federation
    # -> ~/.volcengine/config.json -> the ECS instance role over IMDS. On a
    # Volcengine ECS with a role bound, .env then holds no secret at all.
    if env.get("VOLC_ACCESSKEY") or env.get("VOLC_SECRETKEY"):
        configuration.ak = settings.need(env, "VOLC_ACCESSKEY")
        configuration.sk = settings.need(env, "VOLC_SECRETKEY")
        if env.get("VOLC_SESSION_TOKEN"):
            configuration.session_token = env["VOLC_SESSION_TOKEN"]
    else:
        print("no VOLC_ACCESSKEY/VOLC_SECRETKEY — falling back to the SDK's default\n"
              "credential chain: env vars, OIDC, CLI config, then ECS instance role.",
              file=sys.stderr)
    volcenginesdkcore.Configuration.set_default(configuration)
    return volcenginesdkvefaas.VEFAASApi()


def call(fn, *args):
    """Run one API call, reporting a rejection as a message rather than a stack.

    Every failure here is the server declining a request, and the body of the
    exception is the only part worth reading — a traceback through the generated
    SDK says nothing about what was wrong with the mount configuration.
    """
    try:
        return fn(*args)
    except ApiException as exc:
        sys.exit(f"{getattr(fn, '__name__', fn)} failed: {exc}")


# --- the application: four mount points, declared once ----------------------

def update_request(env, current=None, writable_all=False):
    """UpdateFunction carrying every row of the mount table.

    UpdateFunction replaces `tos_mount_config` and `nas_storage` wholesale, so
    this builds the complete set from `mounts.TABLE` rather than editing what is
    already there. That is the point: the table is the only description of the
    mounts, and a row that is not in it is a row that does not exist.

    `current` is a GetFunction response, used only to carry the NAS file system
    and mount point forward. Those two identify a filesystem that already exists
    and has data on it — copying them from the live configuration means a sync
    cannot silently repoint the mount at a different filesystem because someone
    mistyped an id into .env. Setting NAS_FILE_SYSTEM_ID / NAS_MOUNT_POINT_ID
    overrides them, which is what a first-time setup needs.
    """
    rows = mounts.app_rows(env, writable_all=writable_all)
    bucket = settings.need(env, "TOS_BUCKET")

    points = []
    for row in rows:
        if row["kind"] != "tos":
            continue
        point = volcenginesdkvefaas.ConvertMountPointForUpdateFunctionInput(
            bucket_name=bucket,
            bucket_path=row["backend"],
            local_mount_path=row["local_mount_path"],
            read_only=row["read_only"],
        )
        if env.get("TOS_ENDPOINT"):
            point.endpoint = env["TOS_ENDPOINT"]
        points.append(point)

    tos_config = volcenginesdkvefaas.TosMountConfigForUpdateFunctionInput(
        enable_tos=True, mount_points=points)
    # auth_mode "default" lets the platform mount with the function's own role,
    # so no access key is written into the application configuration — where it
    # would be readable by anyone who can call GetFunction.
    if env.get("TOS_AUTH_MODE"):
        tos_config.auth_mode = env["TOS_AUTH_MODE"]

    file_system_id, mount_point_id, uid, gid = _nas_identity(env, current)
    nas_configs = []
    for row in rows:
        if row["kind"] != "nas":
            continue
        # No read_only field on this input at all — the platform does not offer
        # a read-only NAS mount, so anything mounted from NAS is writable and the
        # restriction has to live in the runner's own code (TODO.md section 0).
        nas_configs.append(volcenginesdkvefaas.NasConfigForUpdateFunctionInput(
            file_system_id=file_system_id,
            mount_point_id=mount_point_id,
            remote_path=row["backend"],
            local_mount_path=row["local_mount_path"],
            uid=uid,
            gid=gid,
        ))

    return volcenginesdkvefaas.UpdateFunctionRequest(
        id=settings.need(env, "VEFAAS_FUNCTION_ID"),
        tos_mount_config=tos_config,
        nas_storage=volcenginesdkvefaas.NasStorageForUpdateFunctionInput(
            enable_nas=True, nas_configs=nas_configs),
    )


def _nas_identity(env, current):
    existing = None
    nas = getattr(current, "nas_storage", None)
    for config in (getattr(nas, "nas_configs", None) or []):
        existing = config
        break

    file_system_id = env.get("NAS_FILE_SYSTEM_ID") or getattr(existing, "file_system_id", None)
    mount_point_id = env.get("NAS_MOUNT_POINT_ID") or getattr(existing, "mount_point_id", None)
    if not file_system_id or not mount_point_id:
        sys.exit("cannot tell which NAS filesystem to mount: the application declares "
                 "none and\nNAS_FILE_SYSTEM_ID / NAS_MOUNT_POINT_ID are unset in "
                 "sandbox/aio/.env")
    uid = int(env.get("NAS_UID") or getattr(existing, "uid", None) or 1000)
    gid = int(env.get("NAS_GID") or getattr(existing, "gid", None) or 1000)
    return file_system_id, mount_point_id, uid, gid


# --- one sandbox: the same paths, narrowed to one task ----------------------

def sandbox_request(env, task_id, template, task_env=None, bootstrap_args=None,
                    writable_all=False, extra_env=None):
    """CreateSandbox for one task.

    Every mount here is an override of a slot the application already declares
    (`mounts.instance_rows`). `/mnt/runtime` is absent on purpose: the runtime
    version is a property of the release, and repeating it per instance would put
    that choice back into every create call.
    """
    bucket = settings.need(env, "TOS_BUCKET")
    rows = mounts.instance_rows(env, task_id, template, writable_all=writable_all)

    tos_points, nas_points = [], []
    for row in rows:
        if row["kind"] == "tos":
            point = volcenginesdkvefaas.TosMountPointForCreateSandboxInput(
                bucket_name=bucket,
                bucket_path=row["backend"],
                local_mount_path=row["local_mount_path"],
                read_only=row["read_only"],
                # Ask for the mount to exist before the container starts. The
                # startup command still waits for it: the field's semantics are
                # not documented in the SDK, so the waiter stays as the thing
                # actually relied on.
                pre_mount=True,
            )
            if env.get("TOS_ENDPOINT"):
                point.endpoint = env["TOS_ENDPOINT"]
            tos_points.append(point)
        else:
            nas_points.append(volcenginesdkvefaas.NasMountPointForCreateSandboxInput(
                remote_path=row["backend"],
                local_mount_path=row["local_mount_path"],
            ))

    image = _image(env)

    # What the host *asked* to be read-only, so the runner can check the request
    # was honoured instead of assuming a fixed answer. Empty during the writable
    # bring-up round, which is exactly when a fixed assumption would be wrong.
    read_only = "" if writable_all else ",".join(
        m.local_path for m in mounts.TABLE if m.read_only)

    pairs = [
        ("SANDBOX_TASK_ID", task_id),
        ("RUNTIME_MOUNT_PATH", mounts.RUNTIME_MOUNT),
        ("TEMPLATE_MOUNT_PATH", mounts.TEMPLATE_MOUNT),
        ("TASK_MOUNT_PATH", mounts.TASK_MOUNT),
        ("NAS_MOUNT_PATH", mounts.NAS_MOUNT),
        ("READONLY_MOUNTS", read_only),
        ("KEEP_ALIVE_SECONDS", env.get("KEEP_ALIVE_SECONDS") or "3600"),
        # The lease's liveness thresholds. The default stale window is 90 s
        # against a ~120 s retry interval for a *failing* instance, whose every
        # retry re-runs this startup command against the same NAS directory — so
        # a genuinely dead holder is reclaimed before the next run arrives rather
        # than blocking it.
        ("LEASE_HEARTBEAT_SECONDS", env.get("LEASE_HEARTBEAT_SECONDS") or "15"),
        ("LEASE_STALE_SECONDS", env.get("LEASE_STALE_SECONDS") or "30"),
        # How many times the agent is re-run before the loop gives up. The
        # budget, not the goal: a template is expected to stop itself by writing
        # .done, and this is only what bounds the cost when it does not.
        ("CONSTRUCT_MAX_ITERATIONS", env.get("CONSTRUCT_MAX_ITERATIONS") or "10"),
        ("PROBE_PATHS", env.get("PROBE_PATHS") or ""),
        # Trigger bootstrap.sh through the image's post-ready hook so its output
        # goes to the main process stdout that the platform collects. The hook
        # fires after the mounts are up, which is why the command no longer has
        # to poll for the script to appear.
        #
        # bootstrap.sh forwards "$@" to `python3 -m runner`, whose argv[1] picks
        # probe / attach / archive over the default run — so the args have to
        # ride along here or --bootstrap-args reaches nothing but the metadata
        # label. Whether the image shell-splits this value is unverified; the
        # no-argument form is what production runs on.
        ("RUN_HOOK_POST_READY",
         f"{mounts.RUNTIME_MOUNT}/bootstrap.sh"
         + ((" " + bootstrap_args) if bootstrap_args else "")),
    ]
    # Anything the caller passed with --env, which is how a variable the image
    # itself reads — SANDBOX_SHUTDOWN_HOOKS, WAIT_FILES, RUN_HOOK_INIT — gets
    # set for one run without a new .env key for every question worth asking.
    # Before task_env, so a tenant's own file still has the last word.
    for key, value in (extra_env or {}).items():
        pairs.append((key, value))
    # The tenant's secrets, last so a task.env can override any default above,
    # and injected as values rather than as a file: task.env itself never enters
    # the sandbox, so no credential is ever at rest on TOS, on NAS, or inside a
    # checkpoint archive — which matters because archives pack the whole tree.
    for key, value in (task_env or {}).items():
        if value:
            pairs.append((key, value))

    envs = [volcenginesdkvefaas.EnvForCreateSandboxInput(key=k, value=v)
            for k, v in pairs]

    request = volcenginesdkvefaas.CreateSandboxRequest(
        function_id=settings.need(env, "VEFAAS_FUNCTION_ID"),
        timeout=int(env.get("SANDBOX_TIMEOUT_MINUTES") or 1440),
        timeout_unit=env.get("SANDBOX_TIMEOUT_UNIT") or "minute",
        cpu_milli=int(env.get("SANDBOX_CPU_MILLI") or 4000),
        memory_mb=int(env.get("SANDBOX_MEMORY_MB") or 8192),
        instance_tos_mount_config=(
            volcenginesdkvefaas.InstanceTosMountConfigForCreateSandboxInput(
                enable=True, tos_mount_points=tos_points)),
        instance_nas_mount_config=(
            volcenginesdkvefaas.InstanceNasMountConfigForCreateSandboxInput(
                enable=True, nas_mount_points=nas_points)),
        instance_image_info=image,
        envs=envs,
        # Server-side labels, so `sbx task list` can answer "what is running and
        # for whom" without the host keeping its own ledger — the one piece of
        # state that would otherwise have to survive on the operator's laptop.
        metadata=_metadata(task_id, template, env, bootstrap_args),
    )
    return request


def _metadata(task_id, template, env, bootstrap_args):
    meta = {
        "task": task_id,
        "template": template,
        "runtime": mounts.runtime_version(env),
        "role": bootstrap_args or "run",
    }
    if "/" in task_id:
        meta["batch"] = task_id.split("/", 1)[0]
    return meta


def _image(env):
    # The startup command only has to start the application. The platform gates
    # readiness on it listening on its port, so a command that runs a script
    # instead never opens one and cold start fails with
    # function_cold_start_timeout. bootstrap.sh is triggered by
    # RUN_HOOK_POST_READY instead (see above), which fires once the mounts are
    # up and therefore does not have to race them.
    app_command = env.get("SANDBOX_APP_COMMAND") or "/opt/gem/run.sh"
    command = env.get("SANDBOX_IMAGE_COMMAND") or f"exec {app_command}"
    image = volcenginesdkvefaas.InstanceImageInfoForCreateSandboxInput(command=command)
    if env.get("SANDBOX_IMAGE"):
        image.image = env["SANDBOX_IMAGE"]
    if env.get("SANDBOX_IMAGE_ID"):
        image.id = env["SANDBOX_IMAGE_ID"]
    if env.get("SANDBOX_IMAGE_PORT"):
        image.port = int(env["SANDBOX_IMAGE_PORT"])
    if not image.image and not image.id:
        print("warning: neither SANDBOX_IMAGE nor SANDBOX_IMAGE_ID is set, so the\n"
              "         request carries only a command. If the platform rejects that,\n"
              "         the application's own startup command runs and bootstrap.sh\n"
              "         is never invoked.\n", file=sys.stderr)
    return image


# --- thin wrappers ----------------------------------------------------------

def get_function(api, function_id):
    return call(api.get_function,
                volcenginesdkvefaas.GetFunctionRequest(id=function_id))


def update_function(api, request):
    return call(api.update_function, request)


def release(api, function_id, revision_number, description=""):
    return call(api.release, volcenginesdkvefaas.ReleaseRequest(
        function_id=function_id, revision_number=revision_number,
        description=description, target_traffic_weight=100))


def release_status(api, function_id):
    return call(api.get_release_status,
                volcenginesdkvefaas.GetReleaseStatusRequest(function_id=function_id))


def list_revisions(api, function_id, page_size=20):
    return call(api.list_revisions, volcenginesdkvefaas.ListRevisionsRequest(
        function_id=function_id, page_size=page_size))


def get_revision(api, function_id, revision_number):
    return call(api.get_revision, volcenginesdkvefaas.GetRevisionRequest(
        function_id=function_id, revision_number=revision_number))


def create_sandbox(api, request):
    return call(api.create_sandbox, request)


def describe_sandbox(api, function_id, sandbox_id):
    return call(api.describe_sandbox, volcenginesdkvefaas.DescribeSandboxRequest(
        function_id=function_id, sandbox_id=sandbox_id))


def list_sandboxes(api, function_id, metadata=None, status=None, page_size=50):
    request = volcenginesdkvefaas.ListSandboxesRequest(
        function_id=function_id, page_size=page_size)
    if metadata:
        request.metadata = metadata
    if status:
        request.status = status
    return call(api.list_sandboxes, request)


def kill_sandbox(api, function_id, sandbox_id):
    return call(api.kill_sandbox, volcenginesdkvefaas.KillSandboxRequest(
        function_id=function_id, sandbox_id=sandbox_id))


def set_timeout(api, function_id, sandbox_id, timeout, unit="minute"):
    return call(api.set_sandbox_timeout,
                volcenginesdkvefaas.SetSandboxTimeoutRequest(
                    function_id=function_id, sandbox_id=sandbox_id,
                    timeout=timeout, timeout_unit=unit))


def instance_logs(api, function_id, name, limit=200):
    return call(api.get_function_instance_logs,
                volcenginesdkvefaas.GetFunctionInstanceLogsRequest(
                    function_id=function_id, name=name, limit=limit))


def list_instances(api, function_id):
    return call(api.list_function_instances,
                volcenginesdkvefaas.ListFunctionInstancesRequest(
                    function_id=function_id))
