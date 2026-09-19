"""Publish compact Harbor evidence and remove superseded runtime rounds."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Literal, Sequence


JOB_FILES = ("config.json", "result.json")
TRIAL_FILES = (
    "lock.json",
    "result.json",
    "verifier/reward-details.json",
    "artifacts/manifest.json",
)
REAL_AGENT_FILES = ("agent/trajectory.json", "agent/claude-code.txt")

_ROUND_NAME = re.compile(r"round-[0-9]{4}")
_PUBLISH_LOCK = ".evidence-retention-jobs.lock"


def _regular_directories(parent: Path) -> list[Path]:
    """Return immediate, non-symlink directories in deterministic order."""
    entries = list(os.scandir(parent))
    return sorted(
        (Path(entry.path) for entry in entries if entry.is_dir(follow_symlinks=False)),
        key=lambda path: path.name,
    )


def _copy_regular_file(source: Path, destination: Path) -> None:
    """Copy a file only when its source is a regular, non-symlink file."""
    try:
        source_mode = source.lstat().st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISREG(source_mode):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination, follow_symlinks=False)


def _copy_selected_files(source: Path, destination: Path, paths: Sequence[str]) -> None:
    for relative_path in paths:
        relative = Path(relative_path)
        _copy_regular_file(source / relative, destination / relative)


def _claim_publish_lock(collected_run: Path) -> Path:
    """Create the cooperative, exclusive lock for a single publish commit."""
    lock_path = collected_run / _PUBLISH_LOCK
    descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    return lock_path


def publish_run(runtime_run: Path, collected_run: Path, include_agent: bool) -> None:
    """Atomically project allowlisted run evidence into an existing collected run."""
    if not collected_run.is_dir():
        raise FileNotFoundError(f"collected run directory is missing: {collected_run}")

    collected_jobs = collected_run / "jobs"
    if collected_jobs.exists() or collected_jobs.is_symlink():
        raise FileExistsError(f"refusing to overwrite collected jobs: {collected_jobs}")

    temporary_root = Path(tempfile.mkdtemp(prefix=".jobs-", dir=collected_run))
    temporary_jobs = temporary_root / "jobs"
    temporary_jobs.mkdir()
    try:
        for job in _regular_directories(runtime_run / "jobs"):
            collected_job = temporary_jobs / job.name
            collected_job.mkdir()
            _copy_selected_files(job, collected_job, JOB_FILES)
            for trial in _regular_directories(job):
                if not trial.name.startswith("task__"):
                    continue
                collected_trial = collected_job / trial.name
                collected_trial.mkdir()
                files = TRIAL_FILES + (REAL_AGENT_FILES if include_agent else ())
                _copy_selected_files(trial, collected_trial, files)

        lock_path = _claim_publish_lock(collected_run)
        try:
            if collected_jobs.exists() or collected_jobs.is_symlink():
                raise FileExistsError(
                    f"refusing to overwrite collected jobs: {collected_jobs}"
                )
            os.rename(temporary_jobs, collected_jobs)
        finally:
            lock_path.unlink(missing_ok=True)
    finally:
        if temporary_root.exists():
            shutil.rmtree(temporary_root)


def write_round_metadata(
    collected_round: Path,
    kind: Literal["real", "regrade"],
    source_round: str | None,
) -> None:
    """Atomically write the round marker after its run projections are complete."""
    if kind not in {"real", "regrade"}:
        raise ValueError(f"unsupported round kind: {kind}")
    if kind == "real" and source_round is not None:
        raise ValueError("real rounds cannot name a source round")
    if kind == "regrade" and (
        not source_round or not _ROUND_NAME.fullmatch(source_round)
    ):
        raise ValueError("regrade rounds require a round-NNNN source round")
    if not collected_round.is_dir():
        raise FileNotFoundError(f"collected round directory is missing: {collected_round}")

    metadata: dict[str, int | str] = {"schema_version": 1, "kind": kind}
    if source_round is not None:
        metadata["source_round"] = source_round
    descriptor, temporary_name = tempfile.mkstemp(prefix=".round-", dir=collected_round)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(metadata, output)
            output.write("\n")
        os.replace(temporary_path, collected_round / "round.json")
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def retain_runtime_source(runtime_root: Path, keep_round: Path | None) -> list[Path]:
    """Delete inactive numbered runtime rounds, retaining active and requested ones."""
    resolved_root = runtime_root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise NotADirectoryError(f"runtime root is not a directory: {runtime_root}")

    resolved_keep: Path | None = None
    if keep_round is not None:
        resolved_keep = keep_round.resolve(strict=False)
        if not _is_within(resolved_keep, resolved_root):
            raise ValueError(f"keep round is outside runtime root: {keep_round}")

    removed: list[Path] = []
    for round_path in sorted(runtime_root.iterdir(), key=lambda path: path.name):
        if not _ROUND_NAME.fullmatch(round_path.name):
            continue
        if round_path.is_symlink():
            continue
        try:
            mode = round_path.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            continue
        if resolved_keep is not None and round_path.resolve(strict=False) == resolved_keep:
            continue
        if (round_path / ".active").exists():
            continue
        shutil.rmtree(round_path)
        removed.append(round_path)
    return removed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    publish = commands.add_parser("publish-run")
    publish.add_argument("--runtime-run", type=Path, required=True)
    publish.add_argument("--collected-run", type=Path, required=True)
    publish.add_argument("--include-agent", action="store_true")

    round_metadata = commands.add_parser("write-round")
    round_metadata.add_argument("--collected-round", type=Path, required=True)
    round_metadata.add_argument("--kind", choices=("real", "regrade"), required=True)
    round_metadata.add_argument("--source-round")

    retain = commands.add_parser("retain")
    retain.add_argument("--runtime-root", type=Path, required=True)
    retain.add_argument("--keep-round", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one evidence-retention command."""
    arguments = _parser().parse_args(argv)
    if arguments.command == "publish-run":
        publish_run(arguments.runtime_run, arguments.collected_run, arguments.include_agent)
    elif arguments.command == "write-round":
        write_round_metadata(
            arguments.collected_round, arguments.kind, arguments.source_round
        )
    else:
        retain_runtime_source(arguments.runtime_root, arguments.keep_round)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
