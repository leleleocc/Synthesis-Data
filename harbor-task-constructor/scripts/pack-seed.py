#!/usr/bin/env python3
"""Pack a new construction life with a compact previous-life reference window."""

import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tarfile
import tempfile


REQUIRED_PATHS = (Path("task/task.toml"), Path("evidence/resume.md"))
ROUND_NAME = re.compile(r"round-\d{4}")
ROUND_KINDS = {"real", "regrade"}
RUN_NAME = re.compile(r"run-\d{4}")
JOB_NAME = re.compile(r"job-[A-Za-z0-9][A-Za-z0-9_.-]*")
ATTEMPT_NAME = re.compile(r"\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2}")
TRIAL_NAME = re.compile(r"task__[A-Za-z0-9][A-Za-z0-9_.-]*")


def _compact_rounds(rounds_root: Path) -> list[tuple[Path, str]]:
    """Return immediate, schema-v1 compact rounds with their declared kind."""
    if not rounds_root.is_dir():
        return []
    rounds: list[tuple[Path, str]] = []
    for candidate in sorted(rounds_root.iterdir(), key=lambda path: path.name):
        if not candidate.is_dir() or not ROUND_NAME.fullmatch(candidate.name):
            continue
        round_json = candidate / "round.json"
        try:
            metadata = json.loads(round_json.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(metadata, dict):
            continue
        kind = metadata.get("kind")
        if metadata.get("schema_version") == 1 and kind in ROUND_KINDS:
            rounds.append((candidate, kind))
    return rounds


def _allowed_compact_path(parts: tuple[str, ...], mode: int) -> bool:
    """Return whether one compact-evidence entry has a documented path shape."""
    is_directory = stat.S_ISDIR(mode)
    is_regular_file = stat.S_ISREG(mode)
    if len(parts) == 1:
        return (
            is_regular_file and parts[0] in {"round.json", "rollout.lock"}
        ) or (is_directory and parts[0] in {"target", "solver"})
    if parts[0] not in {"target", "solver"} or not RUN_NAME.fullmatch(parts[1]):
        return False
    if len(parts) == 2:
        return is_directory

    run_path = parts[2:]
    if len(run_path) == 1:
        return (
            is_directory and run_path[0] == "jobs"
        ) or (
            is_regular_file and run_path[0] in {"harbor.log", "exit-code"}
        )
    if run_path[0] != "jobs" or not (
        JOB_NAME.fullmatch(run_path[1]) or ATTEMPT_NAME.fullmatch(run_path[1])
    ):
        return False
    if len(run_path) == 2:
        return is_directory

    job_path = run_path[2:]
    if JOB_NAME.fullmatch(run_path[1]) and ATTEMPT_NAME.fullmatch(job_path[0]):
        if len(job_path) == 1:
            return is_directory
        job_path = job_path[1:]
    if len(job_path) == 1 and job_path[0] in {"config.json", "result.json"}:
        return is_regular_file
    if not TRIAL_NAME.fullmatch(job_path[0]):
        return False
    if len(job_path) == 1:
        return is_directory
    if len(job_path) == 2 and job_path[1] in {"lock.json", "result.json"}:
        return is_regular_file
    if len(job_path) == 2 and job_path[1] in {"agent", "verifier", "artifacts"}:
        return is_directory
    if len(job_path) != 3:
        return False
    evidence_directory, evidence_file = job_path[1:]
    return is_regular_file and (
        (evidence_directory == "agent" and evidence_file in {"trajectory.json", "claude-code.txt"})
        or (evidence_directory == "verifier" and evidence_file == "reward-details.json")
        or (evidence_directory == "artifacts" and evidence_file == "manifest.json")
    )


def _validate_compact_round(round_root: Path) -> None:
    """Reject anything outside the compact evidence allowlist before copying."""
    for candidate in round_root.rglob("*"):
        relative = candidate.relative_to(round_root)
        if not _allowed_compact_path(relative.parts, candidate.lstat().st_mode):
            raise ValueError(
                f"compact round contains disallowed path: {relative}"
            )


def _write_index(reference_root: Path, rounds: list[tuple[Path, str]]) -> None:
    lines = [
        "# Previous-life compact references",
        "",
        "| round | kind | relative path |",
        "| --- | --- | --- |",
    ]
    for round_root, kind in rounds:
        lines.append(f"| {round_root.name} | {kind} | `rounds/{round_root.name}/` |")
    latest_round = rounds[-1][0].name
    real_rounds = [round_root.name for round_root, kind in rounds if kind == "real"]
    lines.extend(("", f"- 最新结果 round：`rounds/{latest_round}/`"))
    if real_rounds:
        lines.append(f"- 最新 real trajectory round：`rounds/{real_rounds[-1]}/`")
    else:
        lines.append("- 最新 real trajectory round：无")
    (reference_root / "index.md").write_text("\n".join(lines) + "\n")


def _reference_statistics(reference_root: Path) -> tuple[int, int]:
    files = 0
    bytes_count = 0
    for directory, _, names in os.walk(reference_root, followlinks=False):
        for name in names:
            candidate = Path(directory) / name
            mode = candidate.lstat().st_mode
            if stat.S_ISREG(mode):
                files += 1
                bytes_count += candidate.stat().st_size
    return files, bytes_count


def pack(source: Path, destination: Path) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("source and destination must be disjoint")
    if destination.exists():
        raise ValueError("destination already exists; move the old capsule aside first")
    for required in REQUIRED_PATHS:
        if not (source / required).is_file():
            raise ValueError(f"missing {required.as_posix()}")

    current_rounds = _compact_rounds(source / "evidence")
    if current_rounds:
        selected_rounds = current_rounds
        reference_origin = "current-life"
    else:
        selected_rounds = _compact_rounds(source / "evidence/previous-life/rounds")
        reference_origin = "carried-forward" if selected_rounds else "none"
    for round_root, _ in selected_rounds:
        _validate_compact_round(round_root)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    )
    try:
        shutil.copytree(source / "task", temporary / "task", symlinks=True)
        evidence = temporary / "evidence"
        evidence.mkdir()
        shutil.copy2(source / "evidence/resume.md", evidence / "resume.md", follow_symlinks=False)

        included_paths = ["task", "evidence/resume.md"]
        retained_round_names = [round_root.name for round_root, _ in selected_rounds]
        reference_files = 0
        reference_bytes = 0
        if selected_rounds:
            reference_root = evidence / "previous-life"
            rounds_destination = reference_root / "rounds"
            rounds_destination.mkdir(parents=True)
            for round_root, _ in selected_rounds:
                shutil.copytree(round_root, rounds_destination / round_root.name, symlinks=True)
            _write_index(reference_root, selected_rounds)
            reference_files, reference_bytes = _reference_statistics(reference_root)
            included_paths.append("evidence/previous-life")

        report = {
            "schema_version": 2,
            "policy": "fresh-life",
            "reference_origin": reference_origin,
            "included": included_paths,
            "reference_rounds": retained_round_names,
            "reference_files": reference_files,
            "reference_bytes": reference_bytes,
        }
        (evidence / "seed-packaging.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        os.replace(temporary, destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return report


def archive_build(source: Path, destination: Path) -> None:
    source, destination = source.resolve(), destination.resolve()
    if not source.is_dir():
        raise ValueError(f"archive source is not a directory: {source}")
    if destination.exists():
        raise ValueError("archive destination already exists")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("archive source and destination must be disjoint")
    destination.parent.mkdir(parents=True, exist_ok=True)

    def normalize(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mtime = 0
        info.pax_headers = {}
        return info

    temporary = destination.parent / f".{destination.name}.tmp"
    if temporary.exists():
        raise ValueError(f"temporary archive path already exists: {temporary}")
    try:
        with temporary.open("xb") as raw:
            with gzip.GzipFile(
                filename="", fileobj=raw, mode="wb", compresslevel=1, mtime=0
            ) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.PAX_FORMAT,
                    dereference=False,
                ) as archive:
                    for child in sorted(source.iterdir(), key=lambda path: path.name):
                        archive.add(
                            child,
                            arcname=child.name,
                            recursive=True,
                            filter=normalize,
                        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--archive",
        action="store_true",
        help="write a deterministic build.tar.gz instead of a directory",
    )
    args = parser.parse_args()
    try:
        if args.archive:
            destination = args.destination.resolve()
            if destination.exists():
                raise ValueError("destination already exists; move the old archive aside first")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".pack-seed-", dir=destination.parent
            ) as temporary:
                packed = Path(temporary) / "build"
                report = pack(args.source, packed)
                archive_build(packed, destination)
        else:
            report = pack(args.source, args.destination)
        print(json.dumps(report))
    except ValueError as exc:
        parser.error(str(exc))
