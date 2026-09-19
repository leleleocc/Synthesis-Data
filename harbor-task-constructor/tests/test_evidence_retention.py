"""Contract tests for compact Harbor evidence publication and retention."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

sys.dont_write_bytecode = True

import template.environment.method.internal.evidence_retention as evidence_retention
from template.environment.method.internal.evidence_retention import (
    publish_run,
    retain_runtime_source,
    write_round_metadata,
)


class EvidenceRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_file(self, path: Path, content: str = "evidence") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def create_job(self, run: Path, job_name: str) -> Path:
        job = run / "jobs" / job_name
        self.write_file(job / "config.json", '{"task":"example"}')
        self.write_file(job / "result.json", '{"status":"ok"}')
        self.write_file(job / "lock.json", "job lock")
        for trial_name in ("task__alpha", "task__beta"):
            trial = job / trial_name
            self.write_file(trial / "lock.json", "trial lock")
            self.write_file(trial / "result.json", '{"reward":1}')
            self.write_file(trial / "verifier/reward-details.json", '{"detail":1}')
            self.write_file(trial / "artifacts/manifest.json", '{"files":[]}')
            self.write_file(trial / "agent/trajectory.json", '{"steps":[]}')
            self.write_file(trial / "agent/claude-code.txt", "raw Claude log")
            self.write_file(trial / "rollout.lock", "private rollout lock")
            self.write_file(trial / "sessions/session.jsonl", '{"private":true}')
            self.write_file(
                trial / "artifacts/workspace/node_modules/blob", "large private blob"
            )
        return job

    def test_real_publication_copies_only_allowlisted_trial_evidence(self) -> None:
        runtime = self.root / "runtime"
        collected = self.root / "collected" / "round-0001"
        collected.mkdir(parents=True)
        for arm in ("target", "solver"):
            self.create_job(runtime / arm / "run-0001", "job-0001")
            (collected / arm / "run-0001").mkdir(parents=True)
            publish_run(
                runtime / arm / "run-0001",
                collected / arm / "run-0001",
                include_agent=True,
            )
        write_round_metadata(collected, kind="real", source_round=None)

        self.assertTrue((collected / "round.json").is_file())
        self.assertTrue(next(collected.rglob("agent/trajectory.json")).is_file())
        self.assertTrue(next(collected.rglob("agent/claude-code.txt")).is_file())
        self.assertEqual([], list(collected.rglob("artifacts/workspace")))
        self.assertEqual([], list(collected.rglob("sessions")))
        self.assertEqual([], list(collected.rglob("rollout.lock")))
        self.assertEqual([], list(collected.rglob("jobs/*/lock.json")))
        self.assertEqual(
            {"schema_version": 1, "kind": "real"},
            json.loads((collected / "round.json").read_text(encoding="utf-8")),
        )

    def test_publication_rejects_a_missing_runtime_jobs_directory(self) -> None:
        collected_run = self.root / "collected/target/run-0001"
        collected_run.mkdir(parents=True)

        with self.assertRaises(FileNotFoundError):
            publish_run(self.root / "runtime/target/run-0001", collected_run, False)

        self.assertFalse((collected_run / "jobs").exists())

    def test_regrade_metadata_rejects_non_round_source_names(self) -> None:
        collected = self.root / "collected/round-0002"
        collected.mkdir(parents=True)

        for source_round in ("typo", "round-001", "round-00001", "round-000a"):
            with self.subTest(source_round=source_round):
                with self.assertRaises(ValueError):
                    write_round_metadata(collected, "regrade", source_round)
        self.assertFalse((collected / "round.json").exists())

    def test_cli_returns_nonzero_for_missing_runtime_source(self) -> None:
        collected_run = self.root / "collected/target/run-0001"
        collected_run.mkdir(parents=True)
        module = Path(evidence_retention.__file__)

        completed = subprocess.run(
            [
                sys.executable,
                str(module),
                "publish-run",
                "--runtime-run",
                str(self.root / "runtime/target/run-0001"),
                "--collected-run",
                str(collected_run),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode)
        self.assertFalse((collected_run / "jobs").exists())

    def test_concurrent_empty_publications_do_not_replace_each_other(self) -> None:
        runtime_run = self.root / "runtime/target/run-0001"
        (runtime_run / "jobs").mkdir(parents=True)
        collected_run = self.root / "collected/target/run-0001"
        collected_run.mkdir(parents=True)
        temporary_barrier = threading.Barrier(2)
        original_mkdtemp = tempfile.mkdtemp
        outcomes: list[BaseException | None] = []

        def synchronized_mkdtemp(*args: object, **kwargs: object) -> str:
            temporary_barrier.wait(timeout=5)
            return original_mkdtemp(*args, **kwargs)

        def publish() -> None:
            try:
                publish_run(runtime_run, collected_run, include_agent=False)
            except BaseException as error:
                outcomes.append(error)
            else:
                outcomes.append(None)

        with mock.patch.object(
            evidence_retention.tempfile, "mkdtemp", side_effect=synchronized_mkdtemp
        ):
            first = threading.Thread(target=publish)
            second = threading.Thread(target=publish)
            first.start()
            second.start()
            first.join(timeout=10)
            second.join(timeout=10)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(1, outcomes.count(None))
        self.assertEqual(1, sum(isinstance(error, FileExistsError) for error in outcomes))
        self.assertTrue((collected_run / "jobs").is_dir())

    def test_regrade_omits_agent_evidence_and_preserves_missing_scoring_files(self) -> None:
        runtime_run = self.root / "runtime/regrade/run-0001"
        collected = self.root / "collected/round-0002"
        collected_run = collected / "solver/run-0001"
        collected_run.mkdir(parents=True)
        job = self.create_job(runtime_run, "job-0001")
        (job / "task__alpha/result.json").unlink()
        (job / "task__beta/verifier/reward-details.json").unlink()

        publish_run(runtime_run, collected_run, include_agent=False)
        write_round_metadata(collected, kind="regrade", source_round="round-0001")

        published = collected_run / "jobs/job-0001"
        self.assertFalse((published / "task__alpha/result.json").exists())
        self.assertFalse(
            (published / "task__beta/verifier/reward-details.json").exists()
        )
        self.assertEqual([], list(published.rglob("agent")))
        self.assertEqual(
            {"schema_version": 1, "kind": "regrade", "source_round": "round-0001"},
            json.loads((collected / "round.json").read_text(encoding="utf-8")),
        )

    def test_publication_preserves_a_discovered_trial_with_all_scoring_files_missing(self) -> None:
        runtime_run = self.root / "runtime/target/run-0001"
        collected_run = self.root / "collected/target/run-0001"
        collected_run.mkdir(parents=True)
        job = self.create_job(runtime_run, "job-0001")
        trial = job / "task__alpha"
        for relative_path in (
            "lock.json",
            "result.json",
            "verifier/reward-details.json",
            "artifacts/manifest.json",
        ):
            (trial / relative_path).unlink()

        publish_run(runtime_run, collected_run, include_agent=False)

        published_trial = collected_run / "jobs/job-0001/task__alpha"
        self.assertTrue(published_trial.is_dir())
        self.assertFalse((published_trial / "result.json").exists())
        self.assertFalse((published_trial / "verifier/reward-details.json").exists())

    def test_failed_projection_leaves_existing_run_log_and_exit_code_unchanged(self) -> None:
        runtime_run = self.root / "runtime/target/run-0001"
        collected_run = self.root / "collected/target/run-0001"
        self.create_job(runtime_run, "job-0001")
        collected_run.mkdir(parents=True)
        self.write_file(collected_run / "harbor.log", "keep this log")
        self.write_file(collected_run / "exit-code", "17")
        (collected_run / "jobs").mkdir()

        with self.assertRaises(FileExistsError):
            publish_run(runtime_run, collected_run, include_agent=True)

        self.assertEqual("keep this log", (collected_run / "harbor.log").read_text())
        self.assertEqual("17", (collected_run / "exit-code").read_text())

    def test_retention_removes_only_inactive_numbered_rounds(self) -> None:
        root = self.root / "runtime"
        for number in (1, 2, 3, 4):
            (root / f"round-{number:04d}").mkdir(parents=True)
        self.write_file(root / "round-0004/.active")

        removed = retain_runtime_source(root, keep_round=root / "round-0003")

        self.assertEqual([root / "round-0001", root / "round-0002"], removed)
        self.assertTrue((root / "round-0003").is_dir())
        self.assertTrue((root / "round-0004/.active").is_file())

    def test_retention_rejects_external_keep_and_never_follows_round_symlink(self) -> None:
        root = self.root / "runtime"
        root.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        self.write_file(outside / "sentinel", "must survive")
        (root / "round-0001").mkdir()
        try:
            os.symlink(outside, root / "round-0002")
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symlinks unavailable: {error}")

        with self.assertRaises(ValueError):
            retain_runtime_source(root, keep_round=outside)
        removed = retain_runtime_source(root, keep_round=None)

        self.assertEqual([root / "round-0001"], removed)
        self.assertTrue((root / "round-0002").is_symlink())
        self.assertEqual("must survive", (outside / "sentinel").read_text())

    def test_retention_without_keep_preserves_all_active_rounds(self) -> None:
        root = self.root / "runtime"
        (root / "round-0001").mkdir(parents=True)
        (root / "round-0002").mkdir()
        self.write_file(root / "round-0002/.active")
        (root / "round-0003").mkdir()
        self.write_file(root / "round-0003/.active")

        removed = retain_runtime_source(root, keep_round=None)

        self.assertEqual([root / "round-0001"], removed)
        self.assertTrue((root / "round-0002/.active").is_file())
        self.assertTrue((root / "round-0003/.active").is_file())


if __name__ == "__main__":
    unittest.main()
