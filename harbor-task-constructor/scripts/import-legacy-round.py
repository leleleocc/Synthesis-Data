#!/usr/bin/env python3
"""Import one legacy Harbor round archive as compact host evidence."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from template.environment.method.internal.evidence_retention import (  # noqa: E402
    JOB_FILES,
    REAL_AGENT_FILES,
    TRIAL_FILES,
    publish_run,
    write_round_metadata,
)


_ROUND_NAME = re.compile(r"round-[0-9]{4}\Z")
_RUN_NAME = re.compile(r"run-[0-9]{4}\Z")
_ARMS = ("target", "solver")


def _validate_kind(kind: str, source_round: str | None) -> None:
    if kind not in {"real", "regrade"}:
        raise ValueError(f"unsupported round kind: {kind}")
    if kind == "real" and source_round is not None:
        raise ValueError("real imports cannot name a source round")
    if kind == "regrade" and (
        source_round is None or not _ROUND_NAME.fullmatch(source_round)
    ):
        raise ValueError("regrade imports require a round-NNNN source round")


def _member_parts(member: tarfile.TarInfo) -> tuple[str, ...]:
    """Return a strict portable member path with no archive traversal syntax."""
    name = member.name
    if not name or "\x00" in name or name.startswith("/"):
        raise ValueError(f"unsafe archive member path: {name!r}")
    stripped = name.rstrip("/")
    if not stripped:
        raise ValueError(f"unsafe archive member path: {name!r}")
    parts = tuple(stripped.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"unsafe archive member path: {name!r}")
    return parts


def _selected_file(parts: tuple[str, ...], kind: Literal["real", "regrade"]) -> bool:
    """Whether one regular legacy member belongs to the publisher's allowlist."""
    if len(parts) < 4 or parts[1] not in _ARMS or not _RUN_NAME.fullmatch(parts[2]):
        return False
    remainder = parts[3:]
    if remainder in {("harbor.log",), ("exit-code",)}:
        return True
    if len(remainder) == 3 and remainder[0] == "jobs":
        return remainder[2] in JOB_FILES
    if (
        len(remainder) < 4
        or remainder[0] != "jobs"
        or not remainder[2].startswith("task__")
    ):
        return False
    trial_file = "/".join(remainder[3:])
    return trial_file in TRIAL_FILES or (
        kind == "real" and trial_file in REAL_AGENT_FILES
    )


def _validate_members(
    members: Iterable[tarfile.TarInfo], kind: Literal["real", "regrade"]
) -> tuple[str, list[tuple[tarfile.TarInfo, tuple[str, ...]]], dict[str, set[str]]]:
    """Validate all members before selecting any regular file for extraction."""
    root_names: set[str] = set()
    seen: dict[tuple[str, ...], bool] = {}
    selected: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
    runs = {arm: set() for arm in _ARMS}

    for member in members:
        parts = _member_parts(member)
        if not (member.isdir() or member.isreg()):
            raise ValueError(f"unsafe archive member type: {member.name!r}")
        if parts in seen:
            raise ValueError(f"duplicate archive member: {member.name!r}")
        for index in range(1, len(parts)):
            if seen.get(parts[:index]) is False:
                raise ValueError(f"file is an archive path ancestor: {member.name!r}")
        seen[parts] = member.isdir()
        root_names.add(parts[0])
        if member.isreg() and _selected_file(parts, kind):
            selected.append((member, parts))
            runs[parts[1]].add(parts[2])

    for parts, is_directory in seen.items():
        if not is_directory and any(
            other[: len(parts)] == parts and len(other) > len(parts) for other in seen
        ):
            raise ValueError(f"file has archive descendants: {'/'.join(parts)!r}")
    if len(root_names) != 1:
        raise ValueError("archive must contain exactly one top-level root")
    round_name = next(iter(root_names))
    if not _ROUND_NAME.fullmatch(round_name):
        raise ValueError(f"archive root is not a numbered Harbor round: {round_name!r}")
    if not runs["target"] or not runs["solver"]:
        raise ValueError("archive cannot produce evidence for both target and solver arms")
    return round_name, selected, runs


def _extract_sparse_files(
    archive: tarfile.TarFile,
    selected: Iterable[tuple[tarfile.TarInfo, tuple[str, ...]]],
    sparse_round: Path,
) -> None:
    """Copy already-validated, selected regular members without tar extraction."""
    for member, parts in selected:
        destination = sparse_round.parent / Path(*parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError(f"could not read selected archive member: {member.name!r}")
        with source, destination.open("xb") as output:
            shutil.copyfileobj(source, output)
        os.chmod(destination, member.mode & 0o7777)


def _copy_diagnostics(sparse_run: Path, collected_run: Path) -> None:
    for name in ("harbor.log", "exit-code"):
        source = sparse_run / name
        if not source.is_file():
            continue
        destination = collected_run / name
        shutil.copyfile(source, destination)
        os.chmod(destination, stat.S_IMODE(source.stat().st_mode))


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically publish a staged directory only when its name is unclaimed."""
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = library.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        result = rename(os.fsencode(source), os.fsencode(destination), 0x00000004)
    elif sys.platform.startswith("linux"):
        rename = library.renameat2
        rename.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(
            -100, os.fsencode(source), -100, os.fsencode(destination), 0x00000001
        )
    else:
        raise OSError(
            errno.ENOTSUP,
            "atomic no-replace directory rename is unavailable on this host",
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error_number, "evidence round already exists", destination)
    raise OSError(error_number, os.strerror(error_number), destination)


def import_archive(
    archive: Path,
    evidence_root: Path,
    kind: Literal["real", "regrade"],
    source_round: str | None,
) -> Path:
    """Atomically reconstruct one compact round from a validated legacy archive."""
    _validate_kind(kind, source_round)
    with tarfile.open(archive, mode="r:*") as opened_archive:
        round_name, selected, runs = _validate_members(opened_archive.getmembers(), kind)
        destination = evidence_root / round_name
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"refusing to overwrite evidence round: {destination}")

        evidence_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".legacy-import-", dir=evidence_root) as temporary:
            temporary_root = Path(temporary)
            sparse_round = temporary_root / "source" / round_name
            sparse_round.mkdir(parents=True)
            _extract_sparse_files(opened_archive, selected, sparse_round)

            collected_round = temporary_root / "collected" / round_name
            for arm in _ARMS:
                for run_name in sorted(runs[arm]):
                    sparse_run = sparse_round / arm / run_name
                    (sparse_run / "jobs").mkdir(parents=True, exist_ok=True)
                    collected_run = collected_round / arm / run_name
                    collected_run.mkdir(parents=True)
                    _copy_diagnostics(sparse_run, collected_run)
                    publish_run(sparse_run, collected_run, include_agent=kind == "real")

            write_round_metadata(collected_round, kind, source_round)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"refusing to overwrite evidence round: {destination}")
            _rename_no_replace(collected_round, destination)
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--kind", choices=("real", "regrade"), required=True)
    parser.add_argument("--source-round")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    import_archive(
        arguments.archive,
        arguments.evidence_root,
        arguments.kind,
        arguments.source_round,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
