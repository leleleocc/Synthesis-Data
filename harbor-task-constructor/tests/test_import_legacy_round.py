"""Contract tests for the host-only legacy evidence archive importer."""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True

from template.environment.method.internal.evidence_retention import (
    publish_run,
    write_round_metadata,
)


SCRIPT = Path(__file__).parents[1] / "scripts" / "import-legacy-round.py"
PACKER = Path(__file__).parents[1] / "scripts" / "pack-seed.py"


def load_importer():
    spec = importlib.util.spec_from_file_location("import_legacy_round", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LegacyRoundImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def create_legacy_round(
        self,
        root: Path,
        arms: tuple[str, ...] = ("target", "solver"),
        job_name: str = "job-0001",
    ) -> Path:
        round_root = root / "round-0006"
        for arm in arms:
            run = round_root / arm / "run-0001"
            self.write_file(run / "harbor.log", f"{arm} log")
            self.write_file(run / "exit-code", "0")
            job = run / "jobs" / job_name
            self.write_file(job / "config.json", '{"task":"legacy"}')
            self.write_file(job / "result.json", '{"status":"ok"}')
            self.write_file(job / "lock.json", "private job lock")
            trial = job / "task__trial-0001"
            self.write_file(trial / "lock.json", "scoring lock")
            self.write_file(trial / "result.json", '{"reward":1}')
            self.write_file(trial / "verifier/reward-details.json", '{"detail":1}')
            self.write_file(trial / "artifacts/manifest.json", '{"files":[]}')
            self.write_file(trial / "artifacts/workspace/node_modules/blob", "large sentinel")
            self.write_file(trial / "agent/trajectory.json", '{"steps":[]}')
            self.write_file(trial / "agent/claude-code.txt", "agent transcript")
            self.write_file(trial / "agent/sessions/session.jsonl", "private session")
        return round_root

    def test_imported_direct_timestamp_job_round_packs_without_private_files(self) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(
            self.root / "source", job_name="2026-09-06__06-55-52"
        )
        archive = self.archive_round(source_round)
        seed = self.root / "seed"
        self.write_file(seed / "task/task.toml", "task")
        self.write_file(seed / "evidence/resume.md", "notes")

        imported = importer.import_archive(
            archive, seed / "evidence", kind="real", source_round=None
        )
        packed = self.root / "packed"
        result = subprocess.run(
            [sys.executable, str(PACKER), str(seed), str(packed)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        retained = (
            packed
            / "evidence/previous-life/rounds/round-0006/target/run-0001/jobs"
            / "2026-09-06__06-55-52"
        )
        self.assertTrue((retained / "config.json").is_file())
        self.assertTrue((retained / "task__trial-0001/agent/trajectory.json").is_file())
        self.assertFalse((retained / "lock.json").exists())
        self.assertFalse((retained / "task__trial-0001/artifacts/workspace").exists())
        self.assertFalse((retained / "task__trial-0001/agent/sessions").exists())
        self.assertFalse(any(imported.rglob("artifacts/workspace")))

    def archive_round(self, source_round: Path, name: str = "legacy.tar.gz") -> Path:
        archive = self.root / name
        with tarfile.open(archive, "w:gz") as output:
            output.add(source_round, arcname=source_round.name)
        return archive

    def files_and_bytes(self, root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def publish_expected(self, source_round: Path, evidence_root: Path, kind: str) -> Path:
        collected = evidence_root / source_round.name
        for arm in ("target", "solver"):
            source_run = source_round / arm / "run-0001"
            collected_run = collected / arm / "run-0001"
            collected_run.mkdir(parents=True)
            for diagnostic in ("harbor.log", "exit-code"):
                shutil.copyfile(source_run / diagnostic, collected_run / diagnostic)
            publish_run(source_run, collected_run, include_agent=kind == "real")
        write_round_metadata(
            collected,
            kind=kind,
            source_round="round-0006" if kind == "regrade" else None,
        )
        return collected

    def test_import_real_matches_the_runtime_publisher_and_never_stages_workspace(
        self,
    ) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(self.root / "source")
        archive = self.archive_round(source_round)
        archive_before = archive.read_bytes()
        expected = self.publish_expected(source_round, self.root / "expected", "real")
        sparse_runs: list[Path] = []
        original_publish = importer.publish_run

        def inspect_sparse_source(runtime_run: Path, collected_run: Path, include_agent: bool) -> None:
            sparse_runs.append(runtime_run)
            self.assertFalse((runtime_run / "jobs/job-0001/lock.json").exists())
            self.assertFalse(
                (
                    runtime_run
                    / "jobs/job-0001/task__trial-0001/artifacts/workspace"
                ).exists()
            )
            self.assertFalse(
                (runtime_run / "jobs/job-0001/task__trial-0001/agent/sessions").exists()
            )
            original_publish(runtime_run, collected_run, include_agent)

        with mock.patch.object(importer, "publish_run", side_effect=inspect_sparse_source):
            imported = importer.import_archive(
                archive, self.root / "imported", kind="real", source_round=None
            )

        self.assertEqual("round-0006", imported.name)
        self.assertEqual(2, len(sparse_runs))
        self.assertEqual(archive_before, archive.read_bytes())
        self.assertEqual(self.files_and_bytes(expected), self.files_and_bytes(imported))
        self.assertTrue(next(imported.rglob("agent/trajectory.json")).is_file())
        self.assertTrue(next(imported.rglob("agent/claude-code.txt")).is_file())
        self.assertFalse(any(imported.rglob("artifacts/workspace")))
        self.assertFalse(any(imported.rglob("sessions")))
        self.assertFalse(any(imported.rglob("jobs/*/lock.json")))

    def test_import_regrade_records_provenance_and_omits_agent_files(self) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(self.root / "source")
        archive = self.archive_round(source_round)
        expected = self.publish_expected(source_round, self.root / "expected", "regrade")

        imported = importer.import_archive(
            archive,
            self.root / "imported",
            kind="regrade",
            source_round="round-0006",
        )

        self.assertEqual(self.files_and_bytes(expected), self.files_and_bytes(imported))
        self.assertEqual(
            {"schema_version": 1, "kind": "regrade", "source_round": "round-0006"},
            json.loads((imported / "round.json").read_text(encoding="utf-8")),
        )
        self.assertFalse(any(imported.rglob("agent")))

    def test_rejects_unsafe_members_and_never_creates_a_destination(self) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(self.root / "source")
        archive = self.archive_round(source_round)
        unsafe_members = {
            "absolute": tarfile.TarInfo("/round-0006/evil"),
            "parent": tarfile.TarInfo("round-0006/../evil"),
            "symlink": tarfile.TarInfo("round-0006/target/link"),
            "hardlink": tarfile.TarInfo("round-0006/target/link"),
            "character-device": tarfile.TarInfo("round-0006/target/device"),
            "block-device": tarfile.TarInfo("round-0006/target/device"),
            "fifo": tarfile.TarInfo("round-0006/target/fifo"),
        }
        unsafe_members["symlink"].type = tarfile.SYMTYPE
        unsafe_members["hardlink"].type = tarfile.LNKTYPE
        unsafe_members["character-device"].type = tarfile.CHRTYPE
        unsafe_members["block-device"].type = tarfile.BLKTYPE
        unsafe_members["fifo"].type = tarfile.FIFOTYPE

        for label, member in unsafe_members.items():
            with self.subTest(label=label):
                bad_archive = self.root / f"{label}.tar"
                with tarfile.open(bad_archive, "w") as output:
                    output.add(source_round, arcname=source_round.name)
                    output.addfile(member)
                before = bad_archive.read_bytes()

                with self.assertRaises(ValueError):
                    importer.import_archive(
                        bad_archive, self.root / f"evidence-{label}", "real", None
                    )

                self.assertEqual(before, bad_archive.read_bytes())
                self.assertFalse((self.root / f"evidence-{label}" / "round-0006").exists())

    def test_rejects_invalid_archive_roots_and_missing_arm_output(self) -> None:
        importer = load_importer()
        scenarios: list[tuple[str, Path]] = []
        empty = self.root / "empty.tar"
        with tarfile.open(empty, "w"):
            pass
        scenarios.append(("empty", empty))

        valid = self.create_legacy_round(self.root / "valid")
        two_roots = self.root / "two-roots.tar"
        with tarfile.open(two_roots, "w") as output:
            output.add(valid, arcname=valid.name)
            member = tarfile.TarInfo("round-0007/other")
            member.size = 1
            output.addfile(member, io.BytesIO(b"x"))
        scenarios.append(("two-roots", two_roots))

        invalid_root = self.root / "invalid-root.tar"
        with tarfile.open(invalid_root, "w") as output:
            member = tarfile.TarInfo("not-a-round/file")
            member.size = 1
            output.addfile(member, io.BytesIO(b"x"))
        scenarios.append(("invalid-root", invalid_root))

        target_only = self.create_legacy_round(self.root / "target-only", ("target",))
        scenarios.append(("target-only", self.archive_round(target_only, "target-only.tar")))

        for label, archive in scenarios:
            with self.subTest(label=label):
                before = archive.read_bytes()
                evidence_root = self.root / f"evidence-{label}"
                with self.assertRaises(ValueError):
                    importer.import_archive(archive, evidence_root, "real", None)
                self.assertEqual(before, archive.read_bytes())
                self.assertFalse((evidence_root / "round-0006").exists())

    def test_rejects_an_arm_with_only_unallowlisted_legacy_files(self) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(self.root / "source")
        solver_run = source_round / "solver" / "run-0001"
        for relative in (
            "harbor.log",
            "exit-code",
            "jobs/job-0001/config.json",
            "jobs/job-0001/result.json",
            "jobs/job-0001/task__trial-0001/lock.json",
            "jobs/job-0001/task__trial-0001/result.json",
            "jobs/job-0001/task__trial-0001/verifier/reward-details.json",
            "jobs/job-0001/task__trial-0001/artifacts/manifest.json",
            "jobs/job-0001/task__trial-0001/agent/trajectory.json",
            "jobs/job-0001/task__trial-0001/agent/claude-code.txt",
        ):
            (solver_run / relative).unlink()
        archive = self.archive_round(source_round)
        evidence_root = self.root / "evidence"

        with self.assertRaises(ValueError):
            importer.import_archive(archive, evidence_root, "real", None)

        self.assertFalse((evidence_root / "round-0006").exists())

    def test_rejects_existing_destination_and_invalid_kind_provenance(self) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(self.root / "source")
        archive = self.archive_round(source_round)
        destination = self.root / "evidence"
        existing = destination / "round-0006"
        existing.mkdir(parents=True)
        self.write_file(existing / "sentinel", "preserve")
        before = archive.read_bytes()

        with self.assertRaises(FileExistsError):
            importer.import_archive(archive, destination, "real", None)
        with self.assertRaises(ValueError):
            importer.import_archive(archive, self.root / "bad-regrade", "regrade", None)
        with self.assertRaises(ValueError):
            importer.import_archive(archive, self.root / "bad-real", "real", "round-0006")

        self.assertEqual(before, archive.read_bytes())
        self.assertEqual("preserve", (existing / "sentinel").read_text(encoding="utf-8"))

    def test_finalization_does_not_replace_a_round_created_at_commit_time(self) -> None:
        importer = load_importer()
        source_round = self.create_legacy_round(self.root / "source")
        archive = self.archive_round(source_round)
        evidence_root = self.root / "evidence"
        destination = evidence_root / "round-0006"
        ready_to_create = threading.Event()
        created = threading.Event()

        def concurrent_creator() -> None:
            ready_to_create.wait(timeout=5)
            destination.mkdir(parents=True)
            self.write_file(destination / "sentinel", "concurrent owner")
            created.set()

        creator = threading.Thread(target=concurrent_creator)
        creator.start()
        original_finalize = importer._rename_no_replace

        def finalize_after_competitor(source: Path, target: Path) -> None:
            ready_to_create.set()
            self.assertTrue(created.wait(timeout=5))
            original_finalize(source, target)

        with mock.patch.object(
            importer, "_rename_no_replace", side_effect=finalize_after_competitor
        ):
            with self.assertRaises(FileExistsError):
                importer.import_archive(archive, evidence_root, "real", None)
        creator.join(timeout=5)

        self.assertFalse(creator.is_alive())
        self.assertEqual(
            "concurrent owner", (destination / "sentinel").read_text(encoding="utf-8")
        )
        self.assertFalse((destination / "round.json").exists())


if __name__ == "__main__":
    unittest.main()
