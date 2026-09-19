"""The NAS workspace: attaching to it, and deciding when it may be removed.

Attach has three outcomes and no fourth:

  reused    a .attached marker is present, so a previous run left a tree here and
            this run continues it. This is what makes an interrupted construction
            resumable rather than restarted.
  restored  nothing here, so a tree is extracted in: the newest verified archive
            if this task has ever produced one, and only otherwise the seed.
            Archives and the seed are deliberately separate prefixes — both hold
            /app-shaped tarballs, so a seed sharing archives/ would be picked by
            the same newest-first rule and a corrected seed pushed mid-task would
            silently restore over the construction.
  refused   a non-empty tree with no marker, which means a restore died partway.
            Refused rather than merged: merging two states silently resurrects
            files a previous round deleted.
"""

import os
import shutil

from . import archive as archives

REUSED = "reused"
RESTORED = "restored"


class AttachRefused(Exception):
    pass


def attach(cfg, log):
    """Ensure cfg.workspace holds a tree. Returns REUSED or RESTORED."""
    log.say(f"  workspace: {cfg.workspace}")

    if os.path.exists(cfg.attached_marker):
        count = archives.count_files(cfg.workspace)
        log.ok(f"workspace already present — reusing it, {count} files, no restore")
        return REUSED

    if os.path.isdir(cfg.workspace) and os.listdir(cfg.workspace):
        raise AttachRefused(
            f"{cfg.workspace} is non-empty but has no .attached marker. "
            "A previous restore died partway. Move it aside and re-run.")

    chosen, origin = _pick_source(cfg, log)
    if chosen is None:
        raise AttachRefused(
            f"nothing to attach from: no complete archive under {cfg.archives_dir} "
            f"and no seed under {cfg.seed_dir}")
    log.say(f"  chosen: {chosen} (from {origin})")

    # Extract into a staging sibling and rename into place, so an interrupted
    # restore never leaves a half-tree at the workspace path — which is exactly
    # the state the refusal above would then trip over.
    staging = os.path.join(cfg.nas, f".restore-{cfg.pid}")
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging)
    log.say(f"  extracting to {staging} ...")
    archives.restore(chosen, staging)

    count = archives.count_files(staging)
    # Write the marker *inside* the staging directory, so the rename publishes
    # the tree and the marker in one step. Written afterwards, a process that
    # died in the gap would leave a complete tree that the refusal above then
    # rejects forever as a half-finished restore. archive.EXCLUDED keeps it out
    # of every archive, so the two orderings are otherwise identical.
    open(os.path.join(staging, ".attached"), "w").close()
    try:
        os.rmdir(cfg.workspace)
    except OSError:
        pass
    os.rename(staging, cfg.workspace)
    log.ok(f"restored {count} files to {cfg.workspace}")
    return RESTORED


def _pick_source(cfg, log):
    """The tree to restore: the newest archive, or failing that the seed.

    Strictly in that order and never merged. An archive is this task's own prior
    output and always wins; the seed is only the starting point for a task that
    has never produced one. Ordering alone could not express that — both are
    timestamped /app-shaped tarballs in the same shape, so a seed pushed after a
    run would sort newest and quietly undo it.
    """
    chosen = archives.newest_verified(cfg.archives_dir, log)
    if chosen is not None:
        return chosen, "archives"
    log.say("  no archive yet — falling back to the seed")
    return archives.newest_verified(cfg.seed_dir, log), "seed"


def fingerprint(tree):
    """A cheap snapshot of the tree's content state.

    Used for stall detection: if the fingerprint does not change between two
    consecutive iterations, the model made no file-system progress. Three
    consecutive identical fingerprints signals a stall and stops the loop.

    Intentionally cheap: file count plus the newest mtime in the tree. Not a
    hash — the point is to detect the common case (model outputs something each
    round) without a full walk on large trees.
    """
    count = 0
    newest = 0.0
    try:
        for root, dirs, files in os.walk(tree):
            # Skip hidden dot-directories so .claude/ journal churn does not
            # count as progress.
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if name.startswith("."):
                    continue
                count += 1
                try:
                    mtime = os.path.getmtime(os.path.join(root, name))
                    if mtime > newest:
                        newest = mtime
                except OSError:
                    pass
    except OSError:
        pass
    return (count, newest)
