from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from harbor.models.task.task import Task


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts" / "run-production.sh"


class ProductionLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.capture = self.root / "harbor-args.txt"
        self.env_file = self.root / "production.env"
        self.env_file.write_text(
            "\n".join(
                [
                    "DAYTONA_API_KEY=daytona-secret",
                    "ANTHROPIC_BASE_URL=https://constructor.example.test",
                    "ANTHROPIC_AUTH_TOKEN=constructor-secret",
                    "HARBOR_CONSTRUCTOR_MODEL=constructor/model",
                    "HARBOR_CONSTRUCTOR_REASONING_EFFORT=high",
                    "HARBOR_TARGET_MODEL_NAME=target/model",
                    "HARBOR_TARGET_BASE_URL=https://target.example.test",
                    "HARBOR_TARGET_AUTH_TOKEN=target-secret",
                    "HARBOR_SOLVER_MODEL_NAME=solver/model",
                    "HARBOR_SOLVER_BASE_URL=https://solver.example.test",
                    "HARBOR_SOLVER_AUTH_TOKEN=solver-secret",
                    "HARBOR_JUDGE_BASE_URL=https://judge.example.test",
                    "HARBOR_JUDGE_AUTH_TOKEN=judge-secret",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        fake_harbor = self.bin_dir / "harbor"
        fake_harbor.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$FAKE_HARBOR_CAPTURE\"\n",
            encoding="utf-8",
        )
        fake_harbor.chmod(fake_harbor.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_launcher(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(LAUNCHER), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ
            | {
                "PATH": f"{self.bin_dir}:{os.environ['PATH']}",
                "FAKE_HARBOR_CAPTURE": str(self.capture),
            },
        )

    def captured_args(self) -> list[str]:
        return self.capture.read_text(encoding="utf-8").splitlines()

    def test_check_runs_config_resolution_without_remote_execution(self) -> None:
        jobs_dir = self.root / "jobs"

        result = self.run_launcher(
            "check",
            "--env-file",
            str(self.env_file),
            "--jobs-dir",
            str(jobs_dir),
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "run",
                "--path",
                str(ROOT / "template"),
                "--env",
                "daytona",
                "--env-file",
                str(self.env_file),
                "--agent",
                "claude-code",
                "--model",
                "constructor/model",
                "--agent-kwarg",
                "reasoning_effort=high",
                "--n-attempts",
                "1",
                "--n-concurrent",
                "1",
                "--max-retries",
                "0",
                "--jobs-dir",
                str(jobs_dir),
                "--print-config",
            ],
            self.captured_args(),
        )

    def test_check_documentation_distinguishes_job_config_from_task_manifest(self) -> None:
        result = self.run_launcher("--help")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertEqual(0, result.returncode, result.stderr)
        for semantic_term in (
            "local task path",
            "does not expand nested task values",
        ):
            self.assertIn(semantic_term, result.stdout)
            self.assertIn(semantic_term, readme)

    def test_harbor_task_api_validates_template_and_exposes_runtime_policy(self) -> None:
        task_path = ROOT / "template"

        self.assertTrue(Task.is_valid_dir(task_path))
        config = Task(task_path).config

        self.assertEqual(10240, config.environment.storage_mb)
        self.assertEqual(28800, config.agent.timeout_sec)
        self.assertEqual(600, config.verifier.timeout_sec)
        self.assertEqual(900, config.environment.build_timeout_sec)
        self.assertEqual("public", config.environment.network_mode.value)
        self.assertEqual(2, config.environment.cpus)
        self.assertEqual(4096, config.environment.memory_mb)
        self.assertEqual(
            [("/app/build", "build")],
            [(artifact.source, artifact.destination) for artifact in config.artifacts],
        )

    def test_install_refuses_to_allocate_remote_resources_without_yes(self) -> None:
        result = self.run_launcher("install", "--env-file", str(self.env_file))

        self.assertEqual(2, result.returncode)
        self.assertIn("requires --yes", result.stderr)
        self.assertFalse(self.capture.exists())

    def test_install_runs_only_environment_and_agent_setup(self) -> None:
        result = self.run_launcher(
            "install",
            "--env-file",
            str(self.env_file),
            "--job-name",
            "install-smoke",
            "--yes",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        args = self.captured_args()
        self.assertIn("--install-only", args)
        self.assertIn("--yes", args)
        self.assertEqual("install-smoke", args[args.index("--job-name") + 1])
        self.assertNotIn("--print-config", args)

    def test_run_starts_one_non_retrying_outer_attempt(self) -> None:
        result = self.run_launcher(
            "run",
            "--env-file",
            str(self.env_file),
            "--job-name",
            "ledger-life-0001",
            "--yes",
        )

        self.assertEqual(0, result.returncode, result.stderr)
        args = self.captured_args()
        self.assertIn("--yes", args)
        self.assertNotIn("--install-only", args)
        self.assertNotIn("--print-config", args)
        self.assertEqual("1", args[args.index("--n-attempts") + 1])
        self.assertEqual("1", args[args.index("--n-concurrent") + 1])
        self.assertEqual("0", args[args.index("--max-retries") + 1])
        self.assertEqual("ledger-life-0001", args[args.index("--job-name") + 1])

    def test_missing_required_value_names_it_and_never_calls_harbor(self) -> None:
        content = self.env_file.read_text(encoding="utf-8")
        self.env_file.write_text(
            content.replace("HARBOR_SOLVER_AUTH_TOKEN=solver-secret\n", ""),
            encoding="utf-8",
        )

        result = self.run_launcher(
            "check",
            "--env-file",
            str(self.env_file),
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("HARBOR_SOLVER_AUTH_TOKEN", result.stderr)
        self.assertFalse(self.capture.exists())


if __name__ == "__main__":
    unittest.main()
