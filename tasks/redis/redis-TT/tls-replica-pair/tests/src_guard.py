#!/usr/bin/env python3
"""Hash the pristine /src tree (skip .git) the same way the golden was built."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

SRC_TREE_HASH = "bbbcb9a478f30e1258cd18bb0a60376702e6a78ed869a2424f8b0c226ec43cd1"


def src_tree_hash(root: str = "/src") -> str:
    base = Path(root)
    digest = hashlib.sha256()
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d != ".git")
        for name in sorted(files):
            path = Path(dirpath) / name
            rel = path.relative_to(base).as_posix()
            digest.update(rel.encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def assert_src_unmodified(errors: list[str], root: str = "/src") -> None:
    if not Path(root).is_dir():
        errors.append(f"{root} is missing")
        return
    got = src_tree_hash(root)
    if got != SRC_TREE_HASH:
        errors.append(
            f"{root} tree hash {got} != pinned {SRC_TREE_HASH} (files under /src were modified)"
        )
