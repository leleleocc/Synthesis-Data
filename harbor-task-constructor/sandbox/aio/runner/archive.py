"""Archives: the workspace packed into TOS, and restored back out of it.

Two invariants carried over from the shell version, both load-bearing:

  * The .sha256 sidecar is written last, and an archive without a matching
    sidecar is treated as absent. That is what stops an instance starting
    mid-upload from attaching half an archive.

  * The bytes are hashed as they are written and the object is then read back
    and hashed again. Comparing those two is the only thing that would expose a
    write the mount accepted but silently truncated.
"""

import hashlib
import json
import os
import tarfile
import time

CHUNK = 1 << 20
EXCLUDED = {".attached"}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


class _Tee:
    """A write-only file object that hashes everything on its way to disk.

    Stands in for `tar -czf - | tee file | sha256sum`: one pass, and the digest
    describes what was actually handed to the mount.
    """

    def __init__(self, fh, digest):
        self._fh = fh
        self._digest = digest

    def write(self, data):
        self._digest.update(data)
        return self._fh.write(data)

    def flush(self):
        self._fh.flush()

    def tell(self):
        return self._fh.tell()


def _sidecar_digest(archive):
    try:
        with open(archive + ".sha256") as fh:
            return fh.read().split()[0]
    except (OSError, IndexError):
        return None


def complete_archives(archives_dir):
    """Archives with a sidecar, newest first. Timestamped names sort lexically."""
    try:
        names = sorted(os.listdir(archives_dir), reverse=True)
    except OSError:
        return []
    return [os.path.join(archives_dir, n) for n in names
            if n.endswith(".tar.gz")
            and _sidecar_digest(os.path.join(archives_dir, n)) is not None]


def newest_verified(archives_dir, log):
    """The newest archive whose contents match its sidecar, or None."""
    try:
        names = sorted(os.listdir(archives_dir), reverse=True)
    except OSError:
        log.say(f"  no archive directory at {archives_dir}")
        return None

    for name in names:
        if not name.endswith(".tar.gz"):
            continue
        path = os.path.join(archives_dir, name)
        want = _sidecar_digest(path)
        if want is None:
            log.say(f"  skip {name}: no sidecar "
                    "(incomplete upload or interrupted write)")
            continue
        log.say(f"  verifying {name} ({os.path.getsize(path):,} B) ...")
        got = sha256_of(path)
        if want != got:
            log.say(f"  skip {name}: sha256 mismatch")
            log.say(f"    want {want}")
            log.say(f"    got  {got}")
            continue
        return path
    return None


def create(workspace, archives_dir, stamp, log):
    """Pack the workspace to <archives_dir>/<stamp>.tar.gz, sidecar last.

    Returns (path, sha256) on success, or (path, None) if the round trip did not
    match — in which case no sidecar is written and the archive stays invisible.
    """
    os.makedirs(archives_dir, exist_ok=True)
    dest = os.path.join(archives_dir, f"{stamp}.tar.gz")
    log.say(f"  writing {dest}")

    def keep(info):
        return None if os.path.basename(info.name) in EXCLUDED else info

    started = time.time()
    intended = hashlib.sha256()
    with open(dest, "wb") as raw:
        with tarfile.open(fileobj=_Tee(raw, intended), mode="w:gz") as tf:
            tf.add(workspace, arcname=".", filter=keep)
    elapsed = time.time() - started

    size = os.path.getsize(dest)
    log.say(f"  wrote {size:,} B in {elapsed:.0f}s")
    log.say("  re-reading from TOS to compare...")
    actual = sha256_of(dest)
    if intended.hexdigest() != actual:
        log.bad("SILENT CORRUPTION through the TOS mount")
        log.say(f"    intended  {intended.hexdigest()}")
        log.say(f"    read back {actual}")
        log.say("    no sidecar written, so this archive stays invisible to attach")
        return dest, None

    log.ok(f"round trip intact — sha256 {actual}")
    _write_manifest(dest, workspace, actual)
    # Last, and only now: the sidecar is what marks the archive complete.
    with open(dest + ".sha256", "w") as fh:
        fh.write(actual + "\n")
    log.ok("sidecar written")
    return dest, actual


def _write_manifest(archive, workspace, digest):
    counts, top = {}, []
    for entry in sorted(os.listdir(workspace)):
        if entry in EXCLUDED:
            continue
        top.append(entry)
        full = os.path.join(workspace, entry)
        if os.path.isdir(full):
            counts[entry] = sum(len(f) for _, _, f in os.walk(full))
    manifest = {
        "archive": os.path.basename(archive),
        "sha256": digest,
        "files": count_files(workspace),
        "top_level": top,
        "counts": counts,
    }
    with open(archive + ".manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)


def count_files(root):
    total = 0
    for _, _, files in os.walk(root):
        total += sum(1 for f in files if f not in EXCLUDED)
    return total


def restore(archive, destination):
    """Extract into an empty destination. The caller renames it into place."""
    with tarfile.open(archive, "r:gz") as tf:
        try:
            # Fidelity is the point: this is a workspace we packed ourselves into
            # our own task-scoped prefix, and the default 'data' filter would
            # rewrite modes we specifically check survived the round trip. The
            # keyword does not exist before 3.11.4, hence the fallback.
            tf.extractall(destination, filter="fully_trusted")
        except TypeError:
            tf.extractall(destination)
