"""Pack a directory into the workspace-shaped tarball the runner restores.

Same shape as `runner/archive.py` writes, because the runner's attach step reads
both from the same code path: whatever is packed here lands directly as the
working tree, with no materializer in between. The three properties that makes
load-bearing:

  * `arcname="."` — the *contents* of the source directory become the tree, not
    the directory itself. Getting this wrong yields a tree one level too deep,
    which restores without error and then fails at the first relative path.
  * The `.sha256` sidecar is written last, and an archive without one is treated
    as absent, so a half-written package is never attached.
  * A `.manifest.json` rides alongside rather than inside, so the sidecar keeps
    covering exactly the archive's own bytes.
"""

import hashlib
import json
import os
import tarfile
import time

# .attached is the runner's own marker for "a tree is present here"; packing one
# would make a restored tree claim it had already been attached. The other two
# are local debris that would otherwise differ between two packs of the same
# source and make the digests useless for comparison.
EXCLUDED_NAMES = {".attached", ".DS_Store"}
EXCLUDED_DIRS = {"__pycache__", ".git"}


def stamp_now():
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _keep(info):
    parts = info.name.split("/")
    if any(p in EXCLUDED_DIRS for p in parts):
        return None
    return None if os.path.basename(info.name) in EXCLUDED_NAMES else info


def count_files(root):
    total = 0
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        total += sum(1 for f in files if f not in EXCLUDED_NAMES)
    return total


def pack(source, out_dir, task_id, stamp=None):
    """Pack `source` to <out_dir>/<stamp>.tar.gz. Returns (path, sha256)."""
    if not os.path.isdir(source):
        raise NotADirectoryError(source)
    stamp = stamp or stamp_now()
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, f"{stamp}.tar.gz")

    with tarfile.open(dest, mode="w:gz") as tf:
        tf.add(source, arcname=".", filter=_keep)

    digest = sha256_of(dest)
    _write_manifest(dest, source, digest, task_id)
    # Last: the sidecar's presence is what marks the package complete, both for
    # `sbx task push` (which uploads it last) and for the runner (which skips
    # any archive lacking one).
    with open(dest + ".sha256", "w") as fh:
        fh.write(digest + "\n")
    return dest, digest


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_manifest(archive, source, digest, task_id):
    counts, top = {}, []
    for entry in sorted(os.listdir(source)):
        if entry in EXCLUDED_NAMES or entry in EXCLUDED_DIRS:
            continue
        top.append(entry)
        full = os.path.join(source, entry)
        if os.path.isdir(full):
            counts[entry] = count_files(full)
    manifest = {
        "task_id": task_id,
        "archive": os.path.basename(archive),
        "sha256": digest,
        "files": count_files(source),
        "top_level": top,
        "counts": counts,
    }
    with open(archive + ".manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def find_package(directory):
    """The newest complete package in a directory, as (archive-name).

    Complete means both sidecars are present — the same rule the runner applies,
    so a package this refuses is one the sandbox would have ignored anyway.
    """
    archives = sorted(f for f in os.listdir(directory) if f.endswith(".tar.gz"))
    if not archives:
        raise FileNotFoundError(f"no .tar.gz in {directory}")
    archive = archives[-1]
    for suffix in (".sha256", ".manifest.json"):
        if not os.path.exists(os.path.join(directory, archive + suffix)):
            raise FileNotFoundError(f"missing {archive}{suffix}")
    return archive
