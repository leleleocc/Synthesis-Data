"""TOS: uploads that can be resumed, and the read-back window onto a task.

The host cannot mount NAS, so a task's TOS prefix is the only thing about a
running sandbox it can see. Everything here is either putting bytes there or
reading them back.
"""

import glob
import hashlib
import json
import os
import sys
import threading
import time

import tos

from . import settings

# The API floor: "invalid part size, the size must be [5242880, 5368709120]".
PART_SIZE = 5 << 20
# Concurrency, not part size, is the lever here. The host is far from
# ap-southeast-1 and a single stream measured ~27 KB/s; parts in flight are what
# fill a high-latency link. Override with TOS_UPLOAD_TASKS.
TASK_NUM = int(os.environ.get("TOS_UPLOAD_TASKS") or 12)


def public_endpoint(env):
    if env.get("TOS_PUBLIC_ENDPOINT"):
        return env["TOS_PUBLIC_ENDPOINT"]
    ep = settings.need(env, "TOS_ENDPOINT")
    ep = ep.split("://", 1)[-1]
    # tos-<region>.ivolces.com is reachable only inside the VPC; the host uses
    # the public tos-<region>.volces.com for the same bucket.
    return ep.replace(".ivolces.com", ".volces.com")


def connect(env, **kwargs):
    endpoint, region = public_endpoint(env), settings.need(env, "VOLC_REGION")
    if env.get("VOLC_ACCESSKEY") or env.get("VOLC_SECRETKEY"):
        return tos.TosClientV2(settings.need(env, "VOLC_ACCESSKEY"),
                               settings.need(env, "VOLC_SECRETKEY"),
                               endpoint, region, **kwargs)
    # Same policy as the veFaaS client: with no static pair, use an ambient
    # identity. The TOS SDK does not share the veFaaS SDK's credential chain and
    # has no default of its own, so the two providers are selected explicitly —
    # env vars, or the ECS instance role named by TOS_ECS_ROLE.
    if os.environ.get("TOS_ACCESS_KEY"):
        provider = tos.credential.EnvCredentialsProvider()
    elif os.environ.get("TOS_ECS_ROLE"):
        provider = tos.credential.EcsCredentialsProvider(os.environ["TOS_ECS_ROLE"])
    else:
        sys.exit("no credentials: set VOLC_ACCESSKEY/VOLC_SECRETKEY in sandbox/aio/.env,\n"
                 "or TOS_ACCESS_KEY/TOS_SECRET_KEY, or TOS_ECS_ROLE for an instance role")
    return tos.TosClientV2(endpoint=endpoint, region=region,
                           credentials_provider=provider, **kwargs)


def key_for(path):
    """A bucket path from the mount table into an object key prefix."""
    return path.strip("/") + "/"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def put(client, bucket, key, path, label, ckpt_dir=None):
    size = os.path.getsize(path)
    print(f"  {label:<28} {size:>12,} B -> {key}", flush=True)
    if size > PART_SIZE:
        # Resumable, and at the smallest part the API allows. A 200 MiB object
        # to ap-southeast-1 from here runs at a few MiB/s, and an 8 MiB part was
        # enough for a single PUT to exceed the socket timeout mid-body:
        # "TosClientError: http request timeout ... partNumber=1". Small parts
        # bound one request's duration; the checkpoint file makes a retry resume
        # rather than restart.
        client.upload_file(bucket, key, path, part_size=PART_SIZE, task_num=TASK_NUM,
                           enable_checkpoint=True,
                           checkpoint_file=os.path.join(ckpt_dir, "x"),
                           data_transfer_listener=_progress(size))
        print()
    else:
        client.put_object_from_file(bucket, key, path)
    got = client.head_object(bucket, key).content_length
    if got != size:
        sys.exit(f"size mismatch after upload: {got} != {size}")


def _progress(total):
    state = {"done": 0, "t": 0.0}
    lock = threading.Lock()

    def listener(consumed, total_bytes, rw_once, kind):
        # Parts upload concurrently and each reports its own consumed_bytes, so
        # accumulate the per-read delta instead. On a resumed upload the parts
        # already stored are never re-read, so this stops short of 100% — it is
        # a liveness signal, not an accounting of the object.
        with lock:
            state["done"] += rw_once
            done, now = state["done"], time.time()
            if done < total and now - state["t"] < 5:
                return
            state["t"] = now
        print(f"\r    {done / total:6.1%}  {done:>13,} / {total:,} B", end="", flush=True)

    return listener


def checkpoint_dir(directory):
    # upload_file uses checkpoint_file only for its directory — the file name is
    # a hash it computes itself (clientv2.py:2484). So point it at a directory of
    # our own and find the record by globbing, rather than by the name we passed.
    return os.path.join(directory, ".tos-checkpoints")


def live_checkpoint(client, bucket, prefix, ckpt_dir):
    """Return the upload id resumable right now, dropping records that are dead.

    The SDK validates a checkpoint against the local file only, never against
    the server. An upload id that was aborted — including one this script
    aborted itself — therefore survives in the record and every retry fails with
    "NoSuchUpload: The specified upload does not exist", forever.
    """
    try:
        r = client.list_multipart_uploads(bucket, prefix=prefix)
        live = {u.upload_id: u for u in (r.uploads or [])}
    except tos.exceptions.TosError:
        return None

    keep = None
    for record in glob.glob(os.path.join(ckpt_dir, "*.upload")):
        try:
            with open(record) as fh:
                upload_id = json.load(fh).get("upload_id")
        except (ValueError, OSError):
            upload_id = None
        if upload_id in live:
            print(f"  resuming multipart upload {upload_id[:12]}…")
            keep = upload_id
        else:
            print(f"  dropping dead checkpoint {os.path.basename(record)}")
            os.remove(record)

    for upload_id, u in live.items():
        if upload_id == keep:
            continue
        print(f"  aborting stale multipart upload {u.key} ({upload_id[:12]}…)")
        client.abort_multipart_upload(bucket, u.key, upload_id)
    return keep


def put_tree(client, bucket, prefix, directory, label="file"):
    """Upload a directory verbatim under `prefix`, deepest paths included.

    Used for both the runner and a tenant's template. Neither is a tarball,
    because both are read in place off a read-only mount rather than extracted.
    """
    sent = 0
    for root, _dirs, names in os.walk(directory):
        for name in sorted(names):
            if name == ".DS_Store" or "__pycache__" in root:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, directory).replace(os.sep, "/")
            put(client, bucket, prefix + rel, path, f"{label}/{rel}")
            sent += 1
    if not sent:
        sys.exit(f"nothing to upload from {directory}")
    return sent


def touch_keep(client, bucket, prefix):
    """Make an empty prefix mountable without putting anything in it.

    A read-only TOS mount whose prefix holds no object is rejected at
    configuration time, and the dead `_unassigned` backends in the mount table
    are empty by design. One zero-byte marker satisfies the check and leaves the
    prefix functionally empty.
    """
    key = prefix + ".keep"
    try:
        client.head_object(bucket, key)
        return False
    except tos.exceptions.TosServerError:
        client.put_object(bucket, key, content=b"")
        return True


def listing(client, bucket, prefix):
    out, token = [], ""
    while True:
        r = client.list_objects_type2(bucket, prefix=prefix, max_keys=1000,
                                      continuation_token=token)
        out.extend(r.contents)
        if not r.is_truncated:
            return out
        token = r.next_continuation_token


def prefixes(client, bucket, prefix):
    """Immediate child prefixes of `prefix`, using delimiter='/'.

    `batch.json` is an object, not a prefix, so it does not appear here.
    Returned names have no trailing slash and no leading parent path.
    """
    out, token = [], ""
    while True:
        r = client.list_objects_type2(
            bucket, prefix=prefix, delimiter="/",
            continuation_token=token, max_keys=1000)
        for p in (r.common_prefixes or []):
            name = p.prefix[len(prefix):].rstrip("/")
            if name:
                out.append(name)
        if not r.is_truncated:
            return out
        token = r.next_continuation_token
