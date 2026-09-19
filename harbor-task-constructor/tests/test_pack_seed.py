"""Behavioral tests for the compact previous-life seed boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pack-seed.py"


class PackSeedTests(unittest.TestCase):
    def make_source(self, root: Path) -> Path:
        source = root / "source"
        for relative, content in {
            "task/task.toml": "task",
            "task/tests/test.sh": "current tests",
            "evidence/resume.md": "notes",
        }.items():
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return source

    def add_round(
        self,
        root: Path,
        relative: str,
        *,
        kind: str = "real",
        job_name: str = "job-0001",
    ) -> Path:
        round_root = root / relative
        files = {
            "round.json": json.dumps({"schema_version": 1, "kind": kind}),
            "rollout.lock": "lock",
            "target/run-0001/harbor.log": "harbor output",
            "target/run-0001/exit-code": "0\n",
            f"target/run-0001/jobs/{job_name}/config.json": "{}",
            f"target/run-0001/jobs/{job_name}/result.json": "{}",
            f"target/run-0001/jobs/{job_name}/task__abc/lock.json": "{}",
            f"target/run-0001/jobs/{job_name}/task__abc/result.json": "{}",
            f"target/run-0001/jobs/{job_name}/task__abc/agent/trajectory.json": "{}",
            f"target/run-0001/jobs/{job_name}/task__abc/verifier/reward-details.json": "scores",
            f"target/run-0001/jobs/{job_name}/task__abc/artifacts/manifest.json": "manifest",
        }
        for name, content in files.items():
            path = round_root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return round_root

    def test_compact_round_accepts_a_direct_harbor_timestamp_job_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            self.add_round(
                source,
                "evidence/round-0001",
                job_name="2026-09-06__06-55-52",
            )

            result = self.pack(source, destination)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(
                (
                    destination
                    / "evidence/previous-life/rounds/round-0001/target/run-0001/jobs"
                    / "2026-09-06__06-55-52/config.json"
                ).is_file()
            )

    def test_compact_round_rejects_a_timestamp_nested_under_a_direct_timestamp_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            job_name = "2026-09-06__06-55-52"
            round_root = self.add_round(
                source, "evidence/round-0001", job_name=job_name
            )
            nested_config = (
                round_root
                / f"target/run-0001/jobs/{job_name}/{job_name}/config.json"
            )
            nested_config.parent.mkdir(parents=True)
            nested_config.write_text("{}")

            result = self.pack(source, destination)

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(destination.exists())

    def pack(self, source: Path, destination: Path, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(source), str(destination), *arguments],
            capture_output=True,
            text=True,
        )

    def test_current_life_compact_rounds_replace_the_inherited_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            self.add_round(source, "evidence/round-0001")
            self.add_round(source, "evidence/round-0002", kind="regrade")
            inherited = self.add_round(
                source, "evidence/previous-life/rounds/round-0009"
            )
            (inherited.parent.parent / "older-marker").write_text("old")
            (source / "evidence/unrelated.txt").write_text("ignore")

            result = self.pack(source, destination)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["previous-life", "resume.md", "seed-packaging.json"],
                sorted(path.name for path in (destination / "evidence").iterdir()),
            )
            self.assertFalse(any((destination / "evidence").glob("round-*")))
            self.assertEqual(
                ["round-0001", "round-0002"],
                sorted(
                    path.name
                    for path in (destination / "evidence/previous-life/rounds").iterdir()
                ),
            )
            self.assertTrue(
                next(
                    (destination / "evidence/previous-life/rounds").rglob(
                        "reward-details.json"
                    )
                ).is_file()
            )
            self.assertTrue(
                next(
                    (destination / "evidence/previous-life/rounds").rglob(
                        "agent/trajectory.json"
                    )
                ).is_file()
            )
            self.assertFalse(
                (destination / "evidence/previous-life/older-marker").exists()
            )
            self.assertEqual("current tests", (destination / "task/tests/test.sh").read_text())
            self.assertEqual("notes", (destination / "evidence/resume.md").read_text())
            report = json.loads(
                (destination / "evidence/seed-packaging.json").read_text()
            )
            self.assertEqual("fresh-life", report["policy"])
            self.assertEqual("current-life", report["reference_origin"])
            self.assertEqual(["round-0001", "round-0002"], report["reference_rounds"])
            self.assertGreater(report["reference_files"], 0)
            self.assertGreater(report["reference_bytes"], 0)
            index = (destination / "evidence/previous-life/index.md").read_text()
            self.assertIn("| round-0001 | real | `rounds/round-0001/` |", index)
            self.assertIn("| round-0002 | regrade | `rounds/round-0002/` |", index)
            self.assertIn("- 最新结果 round：`rounds/round-0002/`", index)
            self.assertIn("- 最新 real trajectory round：`rounds/round-0001/`", index)

    def test_existing_compact_reference_carries_forward_only_when_current_life_has_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            self.add_round(source, "evidence/previous-life/rounds/round-0003")
            self.add_round(
                source, "evidence/previous-life/rounds/round-0004", kind="regrade"
            )

            result = self.pack(source, destination)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                ["round-0003", "round-0004"],
                sorted(
                    path.name
                    for path in (destination / "evidence/previous-life/rounds").iterdir()
                ),
            )
            report = json.loads(
                (destination / "evidence/seed-packaging.json").read_text()
            )
            self.assertEqual("carried-forward", report["reference_origin"])
            self.assertEqual(["round-0003", "round-0004"], report["reference_rounds"])

    def test_no_compact_reference_records_an_empty_reference_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"

            result = self.pack(source, destination)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertFalse((destination / "evidence/previous-life").exists())
            report = json.loads(
                (destination / "evidence/seed-packaging.json").read_text()
            )
            self.assertEqual("none", report["reference_origin"])
            self.assertEqual([], report["reference_rounds"])
            self.assertEqual(0, report["reference_files"])
            self.assertEqual(0, report["reference_bytes"])
            self.assertEqual(["task", "evidence/resume.md"], report["included"])

    def test_ineligible_current_round_does_not_block_a_carried_forward_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            invalid = source / "evidence/round-0001"
            invalid.mkdir()
            (invalid / "round.json").write_text("[]")
            self.add_round(source, "evidence/previous-life/rounds/round-0002")

            result = self.pack(source, destination)

            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(
                (destination / "evidence/seed-packaging.json").read_text()
            )
            self.assertEqual("carried-forward", report["reference_origin"])
            self.assertEqual(["round-0002"], report["reference_rounds"])

    def test_unsafe_compact_round_is_rejected_before_destination_is_created(self):
        for forbidden in (
            "artifacts/workspace",
            "agent/sessions",
            "node_modules",
            ".git",
            "__pycache__",
        ):
            with self.subTest(forbidden=forbidden), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, destination = self.make_source(root), root / "packed"
                round_root = self.add_round(source, "evidence/round-0001")
                unsafe = round_root / forbidden / "marker"
                unsafe.parent.mkdir(parents=True)
                unsafe.write_text("unsafe")

                result = self.pack(source, destination)

                self.assertNotEqual(0, result.returncode)
                self.assertFalse(destination.exists())

    def test_compact_round_rejects_unlisted_dependency_and_cache_trees(self):
        for unlisted_tree in (
            ".venv/lib/site-packages/package.py",
            "site-packages/package.py",
            ".cache/build/output",
            ".pytest_cache/state",
            ".gradle/caches/output",
            "build-cache/objects/output",
        ):
            with self.subTest(unlisted_tree=unlisted_tree), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, destination = self.make_source(root), root / "packed"
                round_root = self.add_round(source, "evidence/round-0001")
                unsafe = round_root / unlisted_tree
                unsafe.parent.mkdir(parents=True)
                unsafe.write_text("unsafe")

                result = self.pack(source, destination)

                self.assertNotEqual(0, result.returncode)
                self.assertFalse(destination.exists())

    def test_compact_round_preserves_the_documented_agent_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            round_root = self.add_round(source, "evidence/round-0001")
            log = round_root / "target/run-0001/jobs/job-0001/task__abc/agent/claude-code.txt"
            log.write_text("agent log")

            result = self.pack(source, destination)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                "agent log",
                (
                    destination
                    / "evidence/previous-life/rounds/round-0001"
                    / log.relative_to(round_root)
                ).read_text(),
            )

    def test_nested_previous_life_in_a_compact_round_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, destination = self.make_source(root), root / "packed"
            round_root = self.add_round(source, "evidence/round-0001")
            marker = round_root / "previous-life/marker"
            marker.parent.mkdir(parents=True)
            marker.write_text("nested")

            result = self.pack(source, destination)

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(destination.exists())

    def test_archive_mode_is_deterministic_and_preserves_task_transport_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.make_source(root)
            self.add_round(source, "evidence/round-0001")
            tool = source / "task/tool.sh"
            tool.write_text("#!/bin/sh\necho preserved\n")
            os.chmod(tool, 0o751)
            (source / "task/tool-link").symlink_to("tool.sh")
            (source / "task/empty").mkdir()
            archives = [root / "first.tar.gz", root / "second.tar.gz"]

            for archive in archives:
                result = self.pack(source, archive, "--archive")
                self.assertEqual(0, result.returncode, result.stderr)

            self.assertEqual(archives[0].read_bytes(), archives[1].read_bytes())
            extracted = root / "extracted"
            with tarfile.open(archives[0], "r:gz") as archive:
                archive.extractall(extracted, filter="fully_trusted")
            self.assertTrue((extracted / "task/empty").is_dir())
            self.assertTrue((extracted / "task/tool-link").is_symlink())
            self.assertEqual("tool.sh", os.readlink(extracted / "task/tool-link"))
            self.assertEqual(0o751, (extracted / "task/tool.sh").stat().st_mode & 0o777)
            self.assertTrue(
                (extracted / "evidence/previous-life/rounds/round-0001/round.json").is_file()
            )

    def test_missing_required_paths_disjoint_destinations_and_existing_destinations_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            incomplete = root / "incomplete"
            incomplete.mkdir()
            result = self.pack(incomplete, root / "missing")
            self.assertNotEqual(0, result.returncode)

            source = self.make_source(root)
            result = self.pack(source, source / "nested")
            self.assertNotEqual(0, result.returncode)
            result = self.pack(source, source.parent)
            self.assertNotEqual(0, result.returncode)

            destination = root / "existing"
            destination.mkdir()
            result = self.pack(source, destination)
            self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
