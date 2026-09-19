"""Behavioral tests for materializing directory and archive seed transports."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = ROOT / "template/environment/unpack-seed.sh"
PACKER = ROOT / "scripts/pack-seed.py"


class SeedTransportTests(unittest.TestCase):
    def run_materializer(self, seed_root: Path, build_root: Path) -> subprocess.CompletedProcess:
        env = os.environ.copy()
        env.update(SEED_ROOT=str(seed_root), BUILD_ROOT=str(build_root))
        return subprocess.run(
            ["bash", str(MATERIALIZER)],
            env=env,
            capture_output=True,
            text=True,
        )

    def test_directory_seed_moves_to_the_runtime_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            task = seed / "build/task/task.toml"
            task.parent.mkdir(parents=True)
            task.write_text("task")

            result = self.run_materializer(seed, root / "runtime/build")

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("task", (root / "runtime/build/task/task.toml").read_text())
            self.assertFalse((seed / "build").exists())

    def test_archive_seed_extracts_to_the_runtime_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            for rel, content in {
                "task/task.toml": "task",
                "task/run.sh": "#!/bin/sh\nexit 0\n",
                "evidence/resume.md": "notes",
            }.items():
                path = source / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            os.chmod(source / "task/run.sh", 0o751)
            (source / "task/run-link").symlink_to("run.sh")
            (source / "task/empty").mkdir()
            seed = root / "seed"
            seed.mkdir()
            packed = subprocess.run(
                [
                    sys.executable,
                    str(PACKER),
                    str(source),
                    str(seed / "build.tar.gz"),
                    "--archive",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, packed.returncode, packed.stderr)

            build = root / "runtime/build"
            result = self.run_materializer(seed, build)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("task", (build / "task/task.toml").read_text())
            self.assertTrue((build / "task/run-link").is_symlink())
            self.assertEqual("run.sh", os.readlink(build / "task/run-link"))
            self.assertEqual(0o751, (build / "task/run.sh").stat().st_mode & 0o777)
            self.assertTrue((build / "task/empty").is_dir())

    def test_ambiguous_or_missing_seed_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in ("both", "neither"):
                with self.subTest(case=case):
                    seed = root / case / "seed"
                    seed.mkdir(parents=True)
                    if case == "both":
                        (seed / "build").mkdir()
                        (seed / "build.tar.gz").write_bytes(b"not inspected")
                    build = root / case / "runtime/build"

                    result = self.run_materializer(seed, build)

                    self.assertNotEqual(0, result.returncode)
                    self.assertFalse(build.exists())

    def test_existing_runtime_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed"
            (seed / "build").mkdir(parents=True)
            build = root / "runtime/build"
            build.mkdir(parents=True)
            marker = build / "keep"
            marker.write_text("original")

            result = self.run_materializer(seed, build)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual("original", marker.read_text())


if __name__ == "__main__":
    unittest.main()
