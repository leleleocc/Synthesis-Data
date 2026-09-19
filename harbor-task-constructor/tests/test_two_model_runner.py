"""Black-box tests for the append-only two-model Harbor runner."""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from harbor.publisher.packager import Packager


RUNNER = (
    Path(__file__).resolve().parents[1]
    / "template"
    / "environment"
    / "method"
    / "run-two-models.sh"
)
HARBOR_PYTHON = sys.executable


PARSER = r'''import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("round")
    parser.add_argument("--final-task", required=True)
    parser.parse_args()
    if __import__("os").environ.get("FAKE_PARSER_FAIL"):
        raise SystemExit(41)
    print("fixture parser display")
'''


FAKE_HARBOR = r'''#!/usr/bin/env python3
import json
import os
import signal
import stat
import sys
import time
from pathlib import Path

args = sys.argv[1:]
capture = Path(os.environ["FAKE_CAPTURE"])
with capture.open("a", encoding="utf-8") as output:
    output.write(json.dumps(args) + "\n")
is_regrade = args[:2] == ["job", "regrade"]
if is_regrade:
    source_job = Path(args[2])
    arm = "target" if "target" in source_job.parts else "solver"
    env_names = []
    env_values = {}
    env_file_mode = None
else:
    env_file = Path(args[args.index("--env-file") + 1])
    env_names = sorted(line.partition("=")[0] for line in env_file.read_text(encoding="utf-8").splitlines())
    env_values = dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines())
    env_file_mode = stat.S_IMODE(env_file.stat().st_mode)
    model = args[args.index("--model") + 1]
jobs = Path(args[args.index("--jobs-dir") + 1])
jobs.mkdir(parents=True, exist_ok=True)
metadata = {
    "argv": args,
    "is_regrade": is_regrade,
    "arm": arm if is_regrade else None,
    "source_job": str(source_job) if is_regrade else None,
    "environment_names": sorted(os.environ),
    "env_file_names": env_names,
    "env_file_values": env_values,
    "env_file_mode": env_file_mode,
    "daytona_value": os.environ.get("DAYTONA_API_KEY"),
    "outer_agent_values": {name: os.environ.get(name) for name in ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")},
    "judge_values": {name: os.environ.get(name) for name in ("HARBOR_JUDGE_BASE_URL", "HARBOR_JUDGE_AUTH_TOKEN")},
    "pid": os.getpid(),
}
with Path(os.environ["FAKE_META"]).open("a", encoding="utf-8") as output:
    output.write(json.dumps(metadata) + "\n")
job = jobs / "job-0001"
job.mkdir()
(job / "config.json").write_text("{}")
print("Harbor started", flush=True)
barrier_dir = os.environ.get("FAKE_HARBOR_BARRIER_DIR")
if barrier_dir:
    barrier = Path(barrier_dir)
    (barrier / f"ready-{os.getpid()}").write_text("", encoding="utf-8")
    while not (barrier / "release").exists():
        time.sleep(0.01)
if is_regrade:
    sleep_name = f"FAKE_HARBOR_SLEEP_REGRADE_{arm.upper()}"
else:
    sleep_name = f"FAKE_HARBOR_SLEEP_{model.split('-', 1)[0].upper()}"
sleep_for = float(os.environ.get(sleep_name, os.environ.get("FAKE_HARBOR_SLEEP", "0")))
if sleep_for:
    def stopped(_signum, _frame):
        Path(os.environ["FAKE_SIGNAL_LOG"]).open("a", encoding="utf-8").write(str(os.getpid()) + "\n")
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, stopped)
    time.sleep(sleep_for)
if is_regrade and os.environ.get("FAKE_HARBOR_FAIL_REGRADE_ARM") == arm:
    raise SystemExit(23)
if not is_regrade and os.environ.get("FAKE_HARBOR_FAIL_MODEL") == model:
    raise SystemExit(17)
(job / "result.json").write_text("{}")
trial = job / "task__fixture"
trial.mkdir()
if is_regrade:
    marker = json.loads((source_job.parents[3] / "rollout.lock").read_text())
else:
    marker = json.loads((jobs.parents[2] / "rollout.lock").read_text())
(trial / "lock.json").write_text(json.dumps({"task": {"digest": marker["task_digest"]}}))
(trial / "result.json").write_text(json.dumps({"task_name": "fixture/regrade-task", "exception_info": None}))
artifacts = trial / "artifacts"
(artifacts / "workspace").mkdir(parents=True)
(artifacts / "workspace/large-output.bin").write_bytes(b"full workspace")
(artifacts / "manifest.json").write_text(json.dumps([{
    "source": "/workspace", "destination": "artifacts/workspace", "type": "directory", "service": None, "status": "ok"
}]))
(trial / "agent").mkdir()
(trial / "agent/trajectory.json").write_text("{}")
(trial / "agent/claude-code.txt").write_text("transcript")
(trial / "agent/debug.log").write_text("not collected")
'''


class TwoModelRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task = self.root / "task"
        self.task.mkdir()
        (self.task / "task.toml").write_text(
            '''schema_version = "1.3"
[task]
name = "fixture/regrade-task"
version = "1.0.0"
[verifier]
environment_mode = "separate"
[environment]
network_mode = "public"
[[artifacts]]
source = "/workspace"
''',
            encoding="utf-8",
        )
        (self.task / "instruction.md").write_text("Solve the fixture task.\n", encoding="utf-8")
        (self.task / ".gitignore").write_text("# fixture\n", encoding="utf-8")
        environment = self.task / "environment"
        environment.mkdir()
        (environment / "Dockerfile").write_text("FROM alpine:3.20\n", encoding="utf-8")
        tests = self.task / "tests"
        tests.mkdir()
        (tests / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
        test_script = tests / "test.sh"
        test_script.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
        test_script.chmod(test_script.stat().st_mode | stat.S_IXUSR)
        solution = self.task / "solution"
        solution.mkdir()
        solve_script = solution / "solve.sh"
        solve_script.write_text("#!/usr/bin/env sh\necho solved\n", encoding="utf-8")
        solve_script.chmod(solve_script.stat().st_mode | stat.S_IXUSR)
        self.evidence = self.root / "evidence"
        self.runtime_evidence = self.root / "runtime-evidence"
        self.parser = self.root / "parse_scores.py"
        self.parser.write_text(PARSER, encoding="utf-8")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        harbor = self.bin / "harbor"
        harbor.write_text(FAKE_HARBOR, encoding="utf-8")
        harbor.chmod(harbor.stat().st_mode | stat.S_IXUSR)
        self.capture = self.root / "captured-argv.jsonl"
        self.metadata = self.root / "captured-metadata.jsonl"
        self.signal_log = self.root / "signals.log"
        self.secret_values = ("daytona-secret", "target-secret", "solver-secret", "judge-secret")
        self.outer_api_key = "outer-api-key-secret"
        self.base_env = {
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "SOP_TASK_ROOT": str(self.task),
            "SOP_EVIDENCE_ROOT": str(self.evidence),
            "SOP_RUNTIME_EVIDENCE_ROOT": str(self.runtime_evidence),
            "SOP_PARSER_PATH": str(self.parser),
            "SOP_HARBOR_PYTHON": HARBOR_PYTHON,
            "FAKE_CAPTURE": str(self.capture),
            "FAKE_META": str(self.metadata),
            "FAKE_SIGNAL_LOG": str(self.signal_log),
            "DAYTONA_API_KEY": self.secret_values[0],
            "HARBOR_JUDGE_BASE_URL": "https://judge.fixture.invalid/v1",
            "HARBOR_JUDGE_AUTH_TOKEN": self.secret_values[3],
            "HARBOR_TARGET_MODEL_NAME": "target-model",
            "HARBOR_TARGET_BASE_URL": "https://target.fixture.invalid/v1",
            "HARBOR_TARGET_AUTH_TOKEN": self.secret_values[1],
            "HARBOR_TARGET_REASONING_EFFORT": "high",
            "HARBOR_SOLVER_MODEL_NAME": "solver-model",
            "HARBOR_SOLVER_BASE_URL": "https://solver.fixture.invalid/v1",
            "HARBOR_SOLVER_AUTH_TOKEN": self.secret_values[2],
            "HARBOR_SOLVER_REASONING_EFFORT": "low",
            "HARBOR_TARGET_UNRELATED": "target-pollution",
            "HARBOR_SOLVER_UNRELATED": "solver-pollution",
            # Deliberately retain conflicting outer credentials: a child must
            # see only its selected arm through --env-file.
            "TARGET_MODEL": "legacy-target-model",
            "TARGET_ANTHROPIC_BASE_URL": "https://legacy-target.fixture.invalid/v1",
            "TARGET_ANTHROPIC_AUTH_TOKEN": "legacy-target-secret",
            "SOLVER_MODEL": "legacy-solver-model",
            "SOLVER_ANTHROPIC_BASE_URL": "https://legacy-solver.fixture.invalid/v1",
            "SOLVER_ANTHROPIC_AUTH_TOKEN": "legacy-solver-secret",
            "OPENAI_API_KEY": "rogue-openai-secret",
            "ANTHROPIC_API_KEY": self.outer_api_key,
            "ANTHROPIC_BASE_URL": "https://outer.fixture.invalid/v1",
            "ANTHROPIC_AUTH_TOKEN": "outer-secret",
            "UNRELATED_PARENT_SENTINEL": "must-not-reach-child",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_runner(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(RUNNER), *args],
            text=True,
            capture_output=True,
            env=os.environ | self.base_env | (env or {}),
            check=False,
        )

    def read_captured_commands(self) -> list[list[str]]:
        if not self.capture.exists():
            return []
        return [json.loads(line) for line in self.capture.read_text(encoding="utf-8").splitlines()]

    def read_metadata(self) -> list[dict[str, object]]:
        if not self.metadata.exists():
            return []
        return [json.loads(line) for line in self.metadata.read_text(encoding="utf-8").splitlines()]

    def task_digest(self) -> str:
        digest, _ = Packager.compute_content_hash(self.task)
        return f"sha256:{digest}"

    def prepare_regrade_rollout(self) -> Path:
        """Create a real-round marker, then replace fake jobs with Harbor-shaped sources."""
        if self.evidence.exists():
            shutil.rmtree(self.evidence)
        if self.runtime_evidence.exists():
            shutil.rmtree(self.runtime_evidence)
        self.assertEqual(0, self.run_runner("both").returncode)
        self.capture.unlink()
        source_round = self.runtime_evidence / "round-0001"
        for arm in ("target", "solver"):
            shutil.rmtree(source_round / arm)
        return source_round

    def make_regrade_source(
        self,
        round_dir: Path,
        arm: str,
        run: str = "run-0001",
        *,
        job_count: int = 1,
        exit_code: str | None = "0\n",
        task_name: str = "fixture/regrade-task",
        digest: str | None = None,
        result: str | None = None,
        workspace_status: str = "ok",
        workspace_path: str | None = "workspace",
        include_service: bool = True,
        exception_info: object = None,
    ) -> Path:
        """Build immediate Harbor jobs and trials without faking the selector itself."""
        marker = json.loads((round_dir / "rollout.lock").read_text(encoding="utf-8"))
        run_dir = round_dir / arm / run
        jobs = run_dir / "jobs"
        shutil.rmtree(jobs, ignore_errors=True)
        jobs.mkdir(parents=True)
        if exit_code is not None:
            (run_dir / "exit-code").write_text(exit_code, encoding="utf-8")
        else:
            (run_dir / "exit-code").unlink(missing_ok=True)
        for number in range(job_count):
            job = jobs / f"job-{number + 1:04d}"
            job.mkdir()
            (job / "config.json").write_text(
                json.dumps({"agents": [{"name": "claude-code", "model_name": f"{arm}-model"}]}),
                encoding="utf-8",
            )
            (job / "result.json").write_text("{}\n", encoding="utf-8")
            trial = job / "task__001"
            trial.mkdir()
            (trial / "lock.json").write_text(
                json.dumps({
                    "task": {"digest": digest or marker["task_digest"]},
                    "agent": {"name": "claude-code", "model_name": f"{arm}-model"},
                }),
                encoding="utf-8",
            )
            (trial / "result.json").write_text(
                result if result is not None else json.dumps({"task_name": task_name, "exception_info": exception_info}),
                encoding="utf-8",
            )
            artifacts = trial / "artifacts"
            artifacts.mkdir()
            manifest_entry = {
                "source": "/workspace",
                "destination": "artifacts/workspace",
                "type": "directory",
                "status": workspace_status,
            }
            if include_service:
                manifest_entry["service"] = None
            (artifacts / "manifest.json").write_text(
                json.dumps([manifest_entry]),
                encoding="utf-8",
            )
            if workspace_status == "ok" and workspace_path is not None:
                (artifacts / workspace_path).mkdir(parents=True)
        return jobs / "job-0001"

    def assert_regrade_preflight_failed(self, before: list[str]) -> None:
        captured_before = self.read_captured_commands()
        result = self.run_runner("regrade")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(before, sorted(path.name for path in self.evidence.glob("round-*")))
        self.assertEqual(captured_before, self.read_captured_commands())

    def wait_for_barrier(self, barrier: Path, expected: int) -> None:
        deadline = time.monotonic() + 5
        while len(list(barrier.glob("ready-*"))) < expected and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(expected, len(list(barrier.glob("ready-*"))))

    @staticmethod
    def stop_processes(processes: list[subprocess.Popen[str]]) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            process.communicate(timeout=5)

    @staticmethod
    def option(args: list[str], name: str) -> str:
        return args[args.index(name) + 1]

    def test_global_help_documents_the_authoritative_runner_contract_without_side_effects(self) -> None:
        empty_credentials = {
            name: ""
            for name in (
                "DAYTONA_API_KEY",
                "HARBOR_TARGET_MODEL_NAME",
                "HARBOR_TARGET_BASE_URL",
                "HARBOR_TARGET_AUTH_TOKEN",
                "HARBOR_TARGET_REASONING_EFFORT",
                "HARBOR_SOLVER_MODEL_NAME",
                "HARBOR_SOLVER_BASE_URL",
                "HARBOR_SOLVER_AUTH_TOKEN",
                "HARBOR_SOLVER_REASONING_EFFORT",
                "HARBOR_JUDGE_BASE_URL",
                "HARBOR_JUDGE_AUTH_TOKEN",
            )
        }
        expected_environment_names = tuple(empty_credentials)
        fixture_credentials = self.secret_values + (
            "legacy-target-secret",
            "legacy-solver-secret",
            "outer-secret",
        )

        for flag in ("--help", "-h"):
            with self.subTest(flag=flag):
                result = self.run_runner(flag, env=empty_credentials)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("", result.stderr)
                self.assertIn("{both|target|solver|regrade}", result.stdout)
                for mode in ("both", "target", "solver", "regrade"):
                    self.assertIn(mode, result.stdout)
                for option in ("--round", "--attempts", "--concurrency"):
                    self.assertIn(option, result.stdout)
                self.assertIn("--max-retries 0", result.stdout)
                self.assertIn("no retry option", result.stdout)
                for name in expected_environment_names:
                    self.assertIn(name, result.stdout)
                self.assertIn("reasoning effort is optional", result.stdout)
                self.assertIn("Target bundle (required for both or target)", result.stdout)
                self.assertIn("Solver bundle (required for both or solver)", result.stdout)
                self.assertIn(
                    "round-NNNN/{target,solver}/run-NNNN/{jobs,harbor.log,exit-code}",
                    result.stdout,
                )
                self.assertIn("does not write run.json or score.json", result.stdout)
                self.assertIn("Without --round", result.stdout)
                self.assertIn("With --round", result.stdout)
                self.assertIn("rollout identities must match", result.stdout)
                self.assertIn("Parser output is display-only", result.stdout)
                self.assertIn("exit status is the Harbor child status", result.stdout)
                for credential in fixture_credentials:
                    self.assertNotIn(credential, result.stdout)
                self.assertFalse(self.evidence.exists())
                self.assertEqual([], self.read_captured_commands())

    def test_unknown_mode_remains_a_usage_error_without_evidence(self) -> None:
        result = self.run_runner("unknown-mode")
        self.assertEqual(2, result.returncode)
        self.assertIn("invalid mode", result.stderr)
        self.assertFalse(self.evidence.exists())
        self.assertEqual([], self.read_captured_commands())

    def test_both_creates_one_round_and_two_independent_arm_runs(self) -> None:
        result = self.run_runner("both", "--attempts", "2", "--concurrency", "2")
        self.assertEqual(0, result.returncode, result.stderr)
        round_dir = self.evidence / "round-0001"
        self.assertTrue((round_dir / "target/run-0001/jobs").is_dir())
        self.assertTrue((round_dir / "solver/run-0001/jobs").is_dir())
        self.assertEqual("0\n", (round_dir / "target/run-0001/exit-code").read_text())
        self.assertEqual("0\n", (round_dir / "solver/run-0001/exit-code").read_text())
        captures = self.read_captured_commands()
        self.assertEqual(2, len(captures))
        for args in captures:
            retry_index = args.index("--max-retries")
            self.assertEqual("0", args[retry_index + 1])
            self.assertEqual("2", self.option(args, "--n-attempts"))
            self.assertEqual("2", self.option(args, "--n-concurrent"))
            self.assertIn("--allow-agent-host", args)

    def test_fresh_both_defaults_to_two_attempts_and_concurrency(self) -> None:
        result = self.run_runner("both")
        self.assertEqual(0, result.returncode, result.stderr)
        captures = self.read_captured_commands()
        self.assertEqual(2, len(captures))
        for args in captures:
            self.assertEqual("2", self.option(args, "--n-attempts"))
            self.assertEqual("2", self.option(args, "--n-concurrent"))

    def test_both_records_rollout_identity(self) -> None:
        result = self.run_runner("both")
        self.assertEqual(0, result.returncode, result.stderr)
        lock = json.loads((self.runtime_evidence / "round-0001/rollout.lock").read_text())
        self.assertEqual({"schema_version", "task_digest", "rollout_input_digest"}, set(lock))
        self.assertEqual(2, lock["schema_version"])
        self.assertEqual(self.task_digest(), lock["task_digest"])
        self.assertRegex(lock["rollout_input_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_full_jobs_stay_runtime_and_collected_jobs_are_compact(self) -> None:
        result = self.run_runner("both")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.runtime_evidence / "round-0001/rollout.lock").is_file())
        self.assertFalse((self.evidence / "round-0001/rollout.lock").exists())
        self.assertEqual({"schema_version": 1, "kind": "real"}, json.loads((self.evidence / "round-0001/round.json").read_text()))
        self.assertEqual([], list(self.evidence.rglob("artifacts/workspace")))
        self.assertEqual(2, len(list(self.runtime_evidence.rglob("artifacts/workspace"))))
        self.assertEqual(2, len(list(self.evidence.rglob("agent/trajectory.json"))))
        self.assertEqual([], list(self.evidence.rglob("agent/debug.log")))
        for args in self.read_captured_commands():
            self.assertTrue(Path(self.option(args, "--jobs-dir")).is_relative_to(self.runtime_evidence))

    def test_collected_only_real_looking_source_cannot_be_regraded_or_repaired(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        shutil.rmtree(self.runtime_evidence, ignore_errors=True)
        (self.evidence / "round-0001/score.json").write_text('{"score": 1}')
        regrade = self.run_runner("regrade")
        self.assertNotEqual(0, regrade.returncode)
        self.assertIn("no current-life rollout source", regrade.stderr)
        self.assertFalse((self.evidence / "round-0002").exists())
        repair = self.run_runner("solver", "--round", "1")
        self.assertNotEqual(0, repair.returncode)
        self.assertFalse((self.evidence / "round-0001/solver/run-0002").exists())

    def test_regrade_publishes_compact_evidence_then_removes_derived_runtime(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        result = self.run_runner("regrade")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["round-0001"], sorted(path.name for path in self.runtime_evidence.glob("round-*")))
        round_dir = self.evidence / "round-0002"
        self.assertEqual({"schema_version": 1, "kind": "regrade", "source_round": "round-0001"}, json.loads((round_dir / "round.json").read_text()))
        self.assertEqual(2, len(list(round_dir.rglob("task__*/result.json"))))
        self.assertEqual([], list(round_dir.rglob("agent")))

    def test_partial_failure_publishes_only_existing_harbor_files(self) -> None:
        result = self.run_runner("target", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertEqual(17, result.returncode, result.stderr)
        run = self.evidence / "round-0001/target/run-0001"
        self.assertEqual("17\n", (run / "exit-code").read_text())
        self.assertIn("Harbor started", (run / "harbor.log").read_text())
        self.assertEqual(["config.json"], sorted(path.name for path in (run / "jobs/job-0001").iterdir()))
        self.assertTrue((self.evidence / "round-0001/round.json").is_file())
        self.assertFalse((self.runtime_evidence / "round-0001/.active").exists())

    def test_replacement_preserves_previous_source_until_new_real_round_publishes(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        barrier = self.root / "replacement-barrier"
        barrier.mkdir()
        runner = subprocess.Popen([str(RUNNER), "both"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(barrier)})
        try:
            self.wait_for_barrier(barrier, 2)
            self.assertTrue((self.runtime_evidence / "round-0001/target/run-0001/jobs/job-0001/task__fixture/artifacts/workspace").is_dir())
            self.assertTrue((self.runtime_evidence / "round-0002/.active").is_file())
            self.assertFalse((self.evidence / "round-0002/round.json").exists())
            (barrier / "release").write_text("")
            _stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(0, runner.returncode, stderr)
        finally:
            self.stop_processes([runner])
        self.assertEqual(["round-0002"], sorted(path.name for path in self.runtime_evidence.glob("round-*")))
        self.assertTrue((self.evidence / "round-0001/round.json").is_file())

    def test_failed_replacement_keeps_previous_source_and_partial_until_next_admission(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        failed = self.run_runner("both", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertEqual(17, failed.returncode)
        self.assertEqual(["round-0001", "round-0002"], sorted(path.name for path in self.runtime_evidence.glob("round-*")))
        barrier = self.root / "next-barrier"
        barrier.mkdir()
        runner = subprocess.Popen([str(RUNNER), "target"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(barrier)})
        try:
            self.wait_for_barrier(barrier, 1)
            self.assertEqual(["round-0001", "round-0003"], sorted(path.name for path in self.runtime_evidence.glob("round-*")))
            self.assertTrue((self.evidence / "round-0002/target/run-0001/harbor.log").is_file())
            (barrier / "release").write_text("")
            _stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(0, runner.returncode, stderr)
        finally:
            self.stop_processes([runner])

    def test_failed_append_preserves_original_complete_source_during_next_fresh(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        original = self.runtime_evidence / "round-0001/target/run-0001/jobs/job-0001/task__fixture/artifacts/workspace/large-output.bin"
        original_content = original.read_bytes()
        failed = self.run_runner("target", "--round", "1", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertEqual(17, failed.returncode, failed.stderr)
        self.assert_regrade_preflight_failed(["round-0001"])
        barrier = self.root / "fresh-after-failed-append"
        barrier.mkdir()
        runner = subprocess.Popen([str(RUNNER), "both"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(barrier)})
        try:
            self.wait_for_barrier(barrier, 2)
            self.assertTrue(original.is_file())
            self.assertEqual(original_content, original.read_bytes())
            self.assertTrue((self.runtime_evidence / "round-0002/.active").is_file())
            (barrier / "release").write_text("")
            _stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(0, runner.returncode, stderr)
        finally:
            self.stop_processes([runner])
        self.assertFalse((self.runtime_evidence / "round-0001").exists())
        self.assertEqual("17\n", (self.evidence / "round-0001/target/run-0002/exit-code").read_text())

    def test_signal_immediately_after_write_round_completes_regrade_retention(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        barrier = self.root / "published-regrade-barrier"
        barrier.mkdir()
        hooked_retention = self.root / "hooked-retention.py"
        real_retention = RUNNER.parent / "internal/evidence_retention.py"
        # Block immediately after the actual write-round process succeeds.
        # SIGTERM is delivered while Bash still waits on this wrapper, so its
        # trap runs before the shell can record the command's successful return.
        hooked_retention.write_text(
            "import subprocess, sys, time\nfrom pathlib import Path\n"
            f"subprocess.run([sys.executable, {str(real_retention)!r}, *sys.argv[1:]], check=True)\n"
            "if sys.argv[1] == 'write-round':\n"
            f"    barrier = Path({str(barrier)!r})\n"
            "    (barrier / 'ready-published').write_text('')\n"
            "    while not (barrier / 'release').exists(): time.sleep(0.01)\n"
        )
        runner = subprocess.Popen([str(RUNNER), "regrade"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.base_env | {"SOP_RETENTION_MODULE": str(hooked_retention)})
        try:
            self.wait_for_barrier(barrier, 1)
            collected_round = self.evidence / "round-0002"
            self.assertEqual("regrade", json.loads((collected_round / "round.json").read_text())["kind"])
            self.assertTrue((self.runtime_evidence / "round-0002/.active").is_file())
            runner.send_signal(signal.SIGTERM)
            (barrier / "release").write_text("")
            _stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(143, runner.returncode, stderr)
            self.assertFalse((self.runtime_evidence / "round-0002").exists())
            self.assertTrue((self.runtime_evidence / "round-0001/rollout.lock").is_file())
            self.assertTrue((collected_round / "target/run-0001/jobs/job-0001/result.json").is_file())
            self.assertEqual("0\n", (collected_round / "target/run-0001/exit-code").read_text())
            self.assertFalse((self.evidence / ".allocation.lock").exists())
        finally:
            (barrier / "release").write_text("")
            self.stop_processes([runner])

    def test_historical_arms_do_not_promote_a_round_that_never_completed(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        self.assertEqual(0, self.run_runner("target").returncode)
        failed = self.run_runner("target", "--round", "2", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertEqual(17, failed.returncode)
        self.assertEqual(0, self.run_runner("solver", "--round", "2").returncode)
        self.assert_regrade_preflight_failed(["round-0001", "round-0002"])
        barrier = self.root / "fresh-after-incomplete-history"
        barrier.mkdir()
        runner = subprocess.Popen([str(RUNNER), "both"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(barrier)})
        try:
            self.wait_for_barrier(barrier, 2)
            self.assertTrue((self.runtime_evidence / "round-0001/rollout.lock").is_file())
            self.assertFalse((self.runtime_evidence / "round-0002").exists())
            (barrier / "release").write_text("")
            _stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(0, runner.returncode, stderr)
        finally:
            self.stop_processes([runner])

    def test_task_identity_change_keeps_previous_complete_source_until_replacement(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        task_config = self.task / "task.toml"
        task_config.write_text(task_config.read_text().replace("fixture/regrade-task", "fixture/new-task"))
        result = self.run_runner("target")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.runtime_evidence / "round-0001/target/run-0001/jobs/job-0001/task__fixture/artifacts/workspace").is_dir())

    def test_unusable_new_real_round_does_not_replace_previous_source(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        task_config = self.task / "task.toml"
        task_config.write_text(task_config.read_text().replace("fixture/regrade-task", "fixture/new-task"))
        # The fixture still emits the original task name, so these zero-exit
        # jobs are readable but cannot serve as the new task's rollout source.
        result = self.run_runner("both")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.runtime_evidence / "round-0001/rollout.lock").is_file())
        self.assertTrue((self.evidence / "round-0002/round.json").is_file())
        self.assert_regrade_preflight_failed(["round-0001", "round-0002"])

    def test_publication_failure_keeps_runtime_and_logs_and_returns_failure(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        broken_retention = self.root / "broken-retention.py"
        real_retention = RUNNER.parent / "internal/evidence_retention.py"
        broken_retention.write_text(
            "import runpy, sys\n"
            "if sys.argv[1] == 'publish-run': raise SystemExit(29)\n"
            f"runpy.run_path({str(real_retention)!r}, run_name='__main__')\n"
        )
        result = self.run_runner("regrade", env={"SOP_RETENTION_MODULE": str(broken_retention)})
        self.assertNotEqual(0, result.returncode)
        self.assertTrue((self.runtime_evidence / "round-0001").is_dir())
        self.assertTrue((self.runtime_evidence / "round-0002/target/run-0001/jobs").is_dir())
        self.assertFalse((self.runtime_evidence / "round-0002/.active").exists())
        self.assertFalse((self.evidence / "round-0002/round.json").exists())
        self.assertEqual("0\n", (self.evidence / "round-0002/target/run-0001/exit-code").read_text())
        self.assertTrue((self.evidence / "round-0002/target/run-0001/harbor.log").is_file())

    def test_repair_keeps_prior_source_and_existing_compact_arm_until_complete(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        self.assertEqual(0, self.run_runner("target").returncode)
        target_result = self.evidence / "round-0002/target/run-0001/jobs/job-0001/result.json"
        before = target_result.read_bytes()
        barrier = self.root / "repair-barrier"
        barrier.mkdir()
        runner = subprocess.Popen([str(RUNNER), "solver", "--round", "2"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(barrier)})
        try:
            self.wait_for_barrier(barrier, 1)
            self.assertTrue((self.runtime_evidence / "round-0001").is_dir())
            self.assertTrue((self.runtime_evidence / "round-0002/.active").is_file())
            self.assertEqual(before, target_result.read_bytes())
            (barrier / "release").write_text("")
            _stdout, stderr = runner.communicate(timeout=5)
            self.assertEqual(0, runner.returncode, stderr)
        finally:
            self.stop_processes([runner])
        self.assertEqual(before, target_result.read_bytes())
        self.assertEqual(["round-0002"], sorted(path.name for path in self.runtime_evidence.glob("round-*")))

    def test_regrade_selects_latest_rollout_and_latest_runs(self) -> None:
        source_round = self.prepare_regrade_rollout()
        first_target = self.make_regrade_source(source_round, "target")
        latest_target = self.make_regrade_source(source_round, "target", "run-0002")
        latest_solver = self.make_regrade_source(source_round, "solver", workspace_status="empty")
        # This is a prior regrade round: lacking rollout.lock means it can
        # never become a source, even though its numeric name is newer.
        (self.evidence / "round-0002/target/run-0001/jobs").mkdir(parents=True)
        result = self.run_runner("regrade")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            {str(latest_target.resolve()), str(latest_solver.resolve())},
            {args[2] for args in self.read_captured_commands()},
        )
        self.assertNotIn(str(first_target.resolve()), {args[2] for args in self.read_captured_commands()})

    def test_regrade_owns_invocation_lock_before_allocation(self) -> None:
        source_round = self.prepare_regrade_rollout()
        self.make_regrade_source(source_round, "target")
        self.make_regrade_source(source_round, "solver")
        allocation_barrier = self.root / "allocation-barrier"
        allocation_barrier.mkdir()
        regrade = subprocess.Popen(
            [str(RUNNER), "regrade"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.base_env | {"SOP_TEST_ALLOCATION_BARRIER_DIR": str(allocation_barrier)},
        )
        try:
            self.wait_for_barrier(allocation_barrier, 1)

            newer_rollout = self.run_runner("target")
            self.assertNotEqual(0, newer_rollout.returncode)
            self.assertIn("another two-model invocation is active", newer_rollout.stderr)
            self.assertFalse((self.evidence / "round-0002").exists())
            self.assertEqual([], self.read_captured_commands())

            (allocation_barrier / "release").write_text("", encoding="utf-8")
            _stdout, stderr = regrade.communicate(timeout=5)
            self.assertEqual(0, regrade.returncode, stderr)
            self.assertEqual(2, len(self.read_captured_commands()))
            self.assertEqual(
                ["round-0001", "round-0002"],
                sorted(path.name for path in self.evidence.glob("round-*")),
            )
        finally:
            self.stop_processes([regrade])

    def test_regrade_accepts_genuine_harbor_workspace_manifest_destination(self) -> None:
        source_round = self.prepare_regrade_rollout()
        jobs = (
            self.make_regrade_source(source_round, "target"),
            self.make_regrade_source(source_round, "solver"),
        )
        for job in jobs:
            manifest_path = next(job.glob("task__*/artifacts/manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest[0]["destination"] = "artifacts/workspace"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = self.run_runner("regrade")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, len(self.read_captured_commands()))

    def test_regrade_runs_both_arms_with_current_task(self) -> None:
        source_round = self.prepare_regrade_rollout()
        target_source = self.make_regrade_source(source_round, "target")
        solver_source = self.make_regrade_source(source_round, "solver")
        result = self.run_runner(
            "regrade",
            "--concurrency",
            "2",
            env={
                "HARBOR_TARGET_MODEL_NAME": "",
                "HARBOR_TARGET_BASE_URL": "",
                "HARBOR_TARGET_AUTH_TOKEN": "",
                "HARBOR_SOLVER_MODEL_NAME": "",
                "HARBOR_SOLVER_BASE_URL": "",
                "HARBOR_SOLVER_AUTH_TOKEN": "",
            },
        )
        self.assertEqual(0, result.returncode, result.stderr)
        regrade_round = self.evidence / "round-0002"
        self.assertFalse((regrade_round / "rollout.lock").exists())
        captures = self.read_captured_commands()
        self.assertEqual(2, len(captures))
        expected_sources = {str(target_source.resolve()), str(solver_source.resolve())}
        self.assertEqual(expected_sources, {args[2] for args in captures})
        for args in captures:
            self.assertEqual(["job", "regrade"], args[:2])
            self.assertEqual(str(self.task), self.option(args, "--task-path"))
            self.assertEqual("daytona", self.option(args, "--env"))
            self.assertEqual("2", self.option(args, "--n-concurrent"))
            self.assertTrue(self.option(args, "--jobs-dir").endswith("/jobs"))
            for forbidden in ("--model", "--agent", "--n-attempts", "--allow-agent-host", "--env-file"):
                self.assertNotIn(forbidden, args)
        for arm in ("target", "solver"):
            run_dir = regrade_round / arm / "run-0001"
            self.assertTrue((run_dir / "jobs").is_dir())
            self.assertEqual("0\n", (run_dir / "exit-code").read_text())

    def test_regrade_defaults_to_one_concurrent_job(self) -> None:
        source_round = self.prepare_regrade_rollout()
        self.make_regrade_source(source_round, "target")
        self.make_regrade_source(source_round, "solver")

        result = self.run_runner(
            "regrade",
            env={
                "HARBOR_TARGET_MODEL_NAME": "",
                "HARBOR_TARGET_BASE_URL": "",
                "HARBOR_TARGET_AUTH_TOKEN": "",
                "HARBOR_SOLVER_MODEL_NAME": "",
                "HARBOR_SOLVER_BASE_URL": "",
                "HARBOR_SOLVER_AUTH_TOKEN": "",
            },
        )

        self.assertEqual(0, result.returncode, result.stderr)
        captures = self.read_captured_commands()
        self.assertEqual(2, len(captures))
        for args in captures:
            self.assertEqual("1", self.option(args, "--n-concurrent"))

    def test_regrade_accepts_solution_change_without_another_rollout(self) -> None:
        source_round = self.prepare_regrade_rollout()
        self.make_regrade_source(source_round, "target")
        self.make_regrade_source(source_round, "solver")
        solve_script = self.task / "solution/solve.sh"
        solve_script.write_text("#!/bin/sh\necho updated oracle\n", encoding="utf-8")
        solve_script.chmod(0o755)

        result = self.run_runner("regrade")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, len(self.read_captured_commands()))

    def test_regrade_scrubs_model_credentials(self) -> None:
        source_round = self.prepare_regrade_rollout()
        self.make_regrade_source(source_round, "target")
        self.make_regrade_source(source_round, "solver")
        self.metadata.unlink()
        result = self.run_runner("regrade")
        self.assertEqual(0, result.returncode, result.stderr)
        metadata = self.read_metadata()
        self.assertEqual(2, len(metadata))
        for item in metadata:
            self.assertTrue(item["is_regrade"])
            self.assertEqual([], item["env_file_names"])
            self.assertEqual(self.secret_values[0], item["daytona_value"])
            self.assertIn("DAYTONA_API_KEY", item["environment_names"])
            self.assertEqual(
                {"HARBOR_JUDGE_BASE_URL": "https://judge.fixture.invalid/v1", "HARBOR_JUDGE_AUTH_TOKEN": self.secret_values[3]},
                item["judge_values"],
            )
            self.assertEqual({"ANTHROPIC_BASE_URL": None, "ANTHROPIC_AUTH_TOKEN": None}, item["outer_agent_values"])
            for inherited_name in (
                "OPENAI_API_KEY",
                "TARGET_ANTHROPIC_AUTH_TOKEN",
                "SOLVER_ANTHROPIC_AUTH_TOKEN",
                "UNRELATED_PARENT_SENTINEL",
            ):
                self.assertNotIn(inherited_name, item["environment_names"])
            self.assertFalse(any(
                name.startswith("HARBOR_TARGET_")
                or name.startswith("HARBOR_SOLVER_")
                or name.startswith("ANTHROPIC_")
                for name in item["environment_names"]
            ))

    def test_regrade_partial_failure_is_append_only(self) -> None:
        source_round = self.prepare_regrade_rollout()
        target_source = self.make_regrade_source(source_round, "target")
        solver_source = self.make_regrade_source(source_round, "solver")
        failed = self.run_runner("regrade", env={"FAKE_HARBOR_FAIL_REGRADE_ARM": "target"})
        self.assertEqual(23, failed.returncode)
        failed_round = self.evidence / "round-0002"
        self.assertFalse((failed_round / "rollout.lock").exists())
        self.assertEqual("23\n", (failed_round / "target/run-0001/exit-code").read_text())
        self.assertEqual("0\n", (failed_round / "solver/run-0001/exit-code").read_text())
        self.assertFalse((self.runtime_evidence / "round-0002").exists())
        self.capture.unlink()
        retried = self.run_runner("regrade")
        self.assertEqual(0, retried.returncode, retried.stderr)
        self.assertFalse((self.runtime_evidence / "round-0003/rollout.lock").exists())
        captures = self.read_captured_commands()
        self.assertEqual({str(target_source.resolve()), str(solver_source.resolve())}, {args[2] for args in captures})

    def test_regrade_never_falls_back(self) -> None:
        first = self.prepare_regrade_rollout()
        self.make_regrade_source(first, "target")
        self.make_regrade_source(first, "solver")
        latest = self.runtime_evidence / "round-0002"
        latest.mkdir()
        (self.evidence / "round-0002").mkdir()
        shutil.copy(first / "rollout.lock", latest / "rollout.lock")
        self.make_regrade_source(latest, "target", exit_code=None)
        self.make_regrade_source(latest, "solver")
        self.assert_regrade_preflight_failed(["round-0001", "round-0002"])

    def test_regrade_requires_replayable_trials(self) -> None:
        cases = (
            ("missing arm", lambda round_dir: None),
            ("missing exit code", lambda round_dir: self.make_regrade_source(round_dir, "target", exit_code=None)),
            ("nonnumeric exit code", lambda round_dir: self.make_regrade_source(round_dir, "target", exit_code="done\n")),
            ("zero jobs", lambda round_dir: self.make_regrade_source(round_dir, "target", job_count=0)),
            ("two jobs", lambda round_dir: self.make_regrade_source(round_dir, "target", job_count=2)),
            ("unreadable result", lambda round_dir: self.make_regrade_source(round_dir, "target", result="not json")),
            ("task name mismatch", lambda round_dir: self.make_regrade_source(round_dir, "target", task_name="fixture/other")),
            ("task digest mismatch", lambda round_dir: self.make_regrade_source(round_dir, "target", digest="sha256:" + "0" * 64)),
            ("missing workspace", lambda round_dir: self.make_regrade_source(round_dir, "target", workspace_path=None)),
            ("failed workspace", lambda round_dir: self.make_regrade_source(round_dir, "target", workspace_status="failed")),
            ("misplaced workspace", lambda round_dir: self.make_regrade_source(round_dir, "target", workspace_path="wrong-place")),
            ("manifest missing main-service", lambda round_dir: self.make_regrade_source(round_dir, "target", include_service=False)),
        )
        for name, make_broken_target in cases:
            with self.subTest(name=name):
                source_round = self.prepare_regrade_rollout()
                make_broken_target(source_round)
                self.make_regrade_source(source_round, "solver")
                self.assert_regrade_preflight_failed(["round-0001"])

        # A provider-failure trial need not itself have artifacts if another
        # trial in the same selected job remains replayable.
        source_round = self.prepare_regrade_rollout()
        target_job = self.make_regrade_source(source_round, "target")
        broken = target_job / "task__provider-failure"
        broken.mkdir()
        (broken / "lock.json").write_text(json.dumps({"task": {"digest": self.task_digest()}}), encoding="utf-8")
        (broken / "result.json").write_text(json.dumps({"task_name": "fixture/regrade-task", "exception_info": {"type": "UnknownApiError"}}), encoding="utf-8")
        self.make_regrade_source(source_round, "solver")
        accepted = self.run_runner("regrade")
        self.assertEqual(0, accepted.returncode, accepted.stderr)
        self.assertEqual(2, len(self.read_captured_commands()))

        # The source marker tracks rollout inputs: verifier and oracle fixes
        # are eligible, while an instruction edit requires a new real rollout.
        source_round = self.prepare_regrade_rollout()
        self.make_regrade_source(source_round, "target")
        self.make_regrade_source(source_round, "solver")
        (self.task / "tests/test.sh").write_text("#!/usr/bin/env sh\necho fixed\n", encoding="utf-8")
        verifier_only = self.run_runner("regrade")
        self.assertEqual(0, verifier_only.returncode, verifier_only.stderr)
        self.assertEqual(2, len(self.read_captured_commands()))
        (self.task / "instruction.md").write_text("This edit needs a rollout.\n", encoding="utf-8")
        self.assert_regrade_preflight_failed(["round-0001", "round-0002"])

    def test_tests_and_solution_are_excluded_from_rollout_input_identity(self) -> None:
        self.assertEqual(0, self.run_runner("target").returncode)
        lock_path = self.runtime_evidence / "round-0001/rollout.lock"
        initial = json.loads(lock_path.read_text())
        (self.task / "tests/test.sh").write_text("#!/usr/bin/env sh\necho changed\n", encoding="utf-8")
        changed_tests = self.run_runner("target")
        self.assertEqual(0, changed_tests.returncode, changed_tests.stderr)
        after_tests = json.loads((self.runtime_evidence / "round-0002/rollout.lock").read_text())
        self.assertNotEqual(initial["task_digest"], after_tests["task_digest"])
        self.assertEqual(initial["rollout_input_digest"], after_tests["rollout_input_digest"])

        solve_script = self.task / "solution/solve.sh"
        solve_script.write_text("#!/bin/sh\necho changed oracle\n", encoding="utf-8")
        solve_script.chmod(0o755)
        changed_solution = self.run_runner("target")
        self.assertEqual(0, changed_solution.returncode, changed_solution.stderr)
        after_solution = json.loads((self.runtime_evidence / "round-0003/rollout.lock").read_text())
        self.assertNotEqual(after_tests["task_digest"], after_solution["task_digest"])
        self.assertEqual(after_tests["rollout_input_digest"], after_solution["rollout_input_digest"])

        for path, mutate in (
            (self.task / "instruction.md", lambda file: file.write_text("Changed instruction.\n", encoding="utf-8")),
            (self.task / ".gitignore", lambda file: file.write_text("# changed fixture\n", encoding="utf-8")),
        ):
            with self.subTest(path=path):
                mutate(path)
                result = self.run_runner("target")
                self.assertEqual(0, result.returncode, result.stderr)
                round_number = len(list(self.evidence.glob("round-*")))
                changed = json.loads((self.runtime_evidence / f"round-{round_number:04d}/rollout.lock").read_text())
                self.assertNotEqual(after_solution["rollout_input_digest"], changed["rollout_input_digest"])
                after_solution = changed

    def test_real_modes_reject_non_regrade_ready_tasks(self) -> None:
        config = self.task / "task.toml"
        original = config.read_text(encoding="utf-8")
        cases = (
            ("missing separate mode", original.replace('environment_mode = "separate"\n', ""), "explicit [verifier].environment_mode"),
            ("steps", original + '\n[[steps]]\nname = "one"\n', "does not support [[steps]]"),
            ("missing workspace artifact", original.replace('source = "/workspace"', 'source = "/tmp/output"'), "exactly one main-service /workspace artifact"),
            ("workspace exclusion", original + 'exclude = ["cache"]\n', "workspace artifact without exclusions"),
            ("non-public environment", original.replace('network_mode = "public"', 'network_mode = "no-network"'), "[environment].network_mode = public"),
            ("non-public agent phase", original.replace('[environment]', '[agent]\nnetwork_mode = "no-network"\n[environment]'), "[agent].network_mode to be public"),
            ("non-public verifier phase", original.replace('[environment]', 'network_mode = "no-network"\n[environment]'), "[verifier].network_mode to be public"),
            ("non-public verifier environment", original.replace('[environment]', '[verifier.environment]\nnetwork_mode = "no-network"\n[environment]'), "[verifier.environment].network_mode to be public"),
            ("workspace descendant artifact", original + '\n[[artifacts]]\nsource = "/workspace/cache"\n', "overlaps /workspace"),
            ("relative workspace destination", original + '\n[[artifacts]]\nsource = "workspace/cache"\n', "destination that overlaps workspace"),
        )
        for name, content, phrase in cases:
            with self.subTest(name=name):
                config.write_text(content, encoding="utf-8")
                result = self.run_runner("target")
                self.assertNotEqual(0, result.returncode)
                self.assertIn(phrase, result.stderr)
                self.assertFalse(self.evidence.exists())
                self.assertEqual([], self.read_captured_commands())
        config.write_text(original, encoding="utf-8")
        with self.subTest(name="missing separate verifier environment definition"):
            (self.task / "tests/Dockerfile").unlink()
            result = self.run_runner("target")
            self.assertNotEqual(0, result.returncode)
            self.assertIn("separate verifier environment definition", result.stderr)
            self.assertFalse(self.evidence.exists())
            self.assertEqual([], self.read_captured_commands())

    def test_regrade_not_ready_error_directs_the_required_fresh_rollout(self) -> None:
        config = self.task / "task.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace('environment_mode = "separate"\n', ""),
            encoding="utf-8",
        )

        result = self.run_runner("regrade")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Next action:", result.stderr)
        self.assertIn("validate nop/oracle", result.stderr)
        self.assertIn("/app/method/run-two-models.sh both", result.stderr)
        self.assertIn("tests/ or solution/", result.stderr)
        self.assertFalse(self.evidence.exists())
        self.assertEqual([], self.read_captured_commands())

    def test_regrade_without_rollout_directs_creation_of_a_real_source(self) -> None:
        result = self.run_runner("regrade")

        self.assertNotEqual(0, result.returncode)
        self.assertIn("no current-life rollout source", result.stderr)
        self.assertIn("Next action:", result.stderr)
        self.assertIn("/app/method/run-two-models.sh both", result.stderr)
        self.assertIn("tests/ or solution/", result.stderr)
        self.assertFalse(self.evidence.exists())
        self.assertEqual([], self.read_captured_commands())

    def test_single_arm_creates_a_new_diagnostic_round(self) -> None:
        result = self.run_runner("target")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.evidence / "round-0001/target/run-0001/jobs").is_dir())
        self.assertFalse((self.evidence / "round-0001/solver").exists())

    def test_existing_round_appends_missing_arm_when_rollout_identity_matches(self) -> None:
        self.assertEqual(0, self.run_runner("target").returncode)
        result = self.run_runner("solver", "--round", "1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.evidence / "round-0001/target/run-0001").is_dir())
        self.assertTrue((self.evidence / "round-0001/solver/run-0001").is_dir())

    def test_existing_round_rejects_changed_task_before_allocating_run(self) -> None:
        self.assertEqual(0, self.run_runner("target").returncode)
        (self.task / "tests/test.sh").write_text("#!/usr/bin/env sh\necho changed\n", encoding="utf-8")
        result = self.run_runner("solver", "--round", "1")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("rollout identity", result.stderr)
        self.assertFalse((self.evidence / "round-0001/solver").exists())

    def test_existing_round_rejects_non_integer_schema_version_before_allocating_run(self) -> None:
        self.assertEqual(0, self.run_runner("target").returncode)
        self.capture.unlink()
        lock_path = self.runtime_evidence / "round-0001/rollout.lock"
        lock = json.loads(lock_path.read_text())
        for schema_version in (True, 1.0):
            with self.subTest(schema_version=schema_version):
                lock["schema_version"] = schema_version
                lock_path.write_text(json.dumps(lock), encoding="utf-8")
                result = self.run_runner("solver", "--round", "1")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("rollout identity", result.stderr)
                self.assertFalse((self.evidence / "round-0001/solver").exists())
                self.assertEqual([], self.read_captured_commands())

    def test_failed_arm_keeps_exit_code_and_next_run_is_explicitly_appended(self) -> None:
        failed = self.run_runner("target", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertEqual(17, failed.returncode)
        first = self.evidence / "round-0001/target/run-0001"
        self.assertTrue((first / "jobs").is_dir())
        self.assertEqual("17\n", (first / "exit-code").read_text())
        retry = self.run_runner("target", "--round", "1")
        self.assertEqual(0, retry.returncode, retry.stderr)
        self.assertEqual("0\n", (self.evidence / "round-0001/target/run-0002/exit-code").read_text())

    def test_default_round_numbers_are_monotonic(self) -> None:
        self.assertEqual(0, self.run_runner("both").returncode)
        self.assertEqual(0, self.run_runner("target").returncode)
        self.assertTrue((self.evidence / "round-0001").is_dir())
        self.assertTrue((self.evidence / "round-0002/target/run-0001").is_dir())

    def test_rejects_user_retry_override_before_creating_evidence(self) -> None:
        result = self.run_runner("target", "--max-retries", "9")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--max-retries", result.stderr)
        self.assertFalse(self.evidence.exists())

    def test_reports_every_missing_credential_for_selected_arm(self) -> None:
        env = {key: "" for key in self.base_env if key not in {"PATH", "SOP_TASK_ROOT", "SOP_EVIDENCE_ROOT", "SOP_PARSER_PATH", "FAKE_CAPTURE", "FAKE_META", "FAKE_SIGNAL_LOG"}}
        result = self.run_runner("target", env=env)
        self.assertNotEqual(0, result.returncode)
        for name in (
            "DAYTONA_API_KEY",
            "HARBOR_JUDGE_BASE_URL",
            "HARBOR_JUDGE_AUTH_TOKEN",
            "HARBOR_TARGET_MODEL_NAME",
            "HARBOR_TARGET_BASE_URL",
            "HARBOR_TARGET_AUTH_TOKEN",
        ):
            self.assertIn(name, result.stderr)
        self.assertFalse(self.evidence.exists())

    def test_arm_env_files_are_distinct_private_and_do_not_mix_credentials(self) -> None:
        result = self.run_runner("both")
        self.assertEqual(0, result.returncode, result.stderr)
        metadata = {self.option(item["argv"], "--model"): item for item in self.read_metadata()}  # type: ignore[arg-type]
        target = metadata["target-model"]
        solver = metadata["solver-model"]
        self.assertEqual(0o600, target["env_file_mode"])
        self.assertEqual(0o600, solver["env_file_mode"])
        self.assertEqual(
            ["ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "DAYTONA_API_KEY"],
            target["env_file_names"],
        )
        self.assertEqual(target["env_file_names"], solver["env_file_names"])
        self.assertNotEqual(self.option(target["argv"], "--env-file"), self.option(solver["argv"], "--env-file"))  # type: ignore[arg-type]
        self.assertEqual(
            {"DAYTONA_API_KEY": self.secret_values[0], "ANTHROPIC_BASE_URL": "https://target.fixture.invalid/v1", "ANTHROPIC_AUTH_TOKEN": self.secret_values[1]},
            target["env_file_values"],
        )
        self.assertEqual(
            {"DAYTONA_API_KEY": self.secret_values[0], "ANTHROPIC_BASE_URL": "https://solver.fixture.invalid/v1", "ANTHROPIC_AUTH_TOKEN": self.secret_values[2]},
            solver["env_file_values"],
        )
        for item in (target, solver):
            self.assertIn("HARBOR_JUDGE_BASE_URL", item["environment_names"])
            self.assertIn("HARBOR_JUDGE_AUTH_TOKEN", item["environment_names"])
            self.assertNotIn("DAYTONA_API_KEY", item["environment_names"])
            self.assertIsNone(item["daytona_value"])
            self.assertNotIn("ANTHROPIC_AUTH_TOKEN", item["environment_names"])
            self.assertEqual({"ANTHROPIC_BASE_URL": None, "ANTHROPIC_AUTH_TOKEN": None}, item["outer_agent_values"])
            self.assertEqual(
                {"HARBOR_JUDGE_BASE_URL": "https://judge.fixture.invalid/v1", "HARBOR_JUDGE_AUTH_TOKEN": self.secret_values[3]},
                item["judge_values"],
            )
            for inherited_name in (
                "OPENAI_API_KEY",
                "TARGET_ANTHROPIC_AUTH_TOKEN",
                "SOLVER_ANTHROPIC_AUTH_TOKEN",
                "UNRELATED_PARENT_SENTINEL",
            ):
                self.assertNotIn(inherited_name, item["environment_names"])
            self.assertFalse(any(name.startswith("HARBOR_TARGET_") or name.startswith("HARBOR_SOLVER_") for name in item["environment_names"]))

    def test_parent_anthropic_api_key_is_not_inherited_by_arm(self) -> None:
        result = self.run_runner("target")
        self.assertEqual(0, result.returncode, result.stderr)
        metadata = self.read_metadata()[0]
        self.assertNotIn("ANTHROPIC_API_KEY", metadata["environment_names"])
        self.assertEqual(
            self.secret_values[1],
            metadata["env_file_values"]["ANTHROPIC_AUTH_TOKEN"],
        )

    def test_runner_output_never_exposes_fixture_tokens(self) -> None:
        result = self.run_runner("both", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertNotEqual(0, result.returncode)
        transcript = result.stdout + result.stderr
        for secret in self.secret_values:
            self.assertNotIn(secret, transcript)

    def test_parser_failure_after_partial_round_does_not_replace_harbor_status(self) -> None:
        result = self.run_runner("target", env={"FAKE_PARSER_FAIL": "1"})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("0\n", (self.evidence / "round-0001/target/run-0001/exit-code").read_text())

    def test_final_score_display_uses_selected_harbor_python(self) -> None:
        capture = self.root / "python-argv.jsonl"
        wrapper = self.root / "recording-python"
        wrapper.write_text(
            r'''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

capture = Path(os.environ["FAKE_PYTHON_CAPTURE"])
with capture.open("a", encoding="utf-8") as output:
    output.write(json.dumps(sys.argv[1:]) + "\n")
real_python = os.environ["FAKE_REAL_PYTHON"]
os.execv(real_python, [real_python, *sys.argv[1:]])
''',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

        result = self.run_runner(
            "target",
            env={
                "SOP_HARBOR_PYTHON": str(wrapper),
                "FAKE_PYTHON_CAPTURE": str(capture),
                "FAKE_REAL_PYTHON": HARBOR_PYTHON,
            },
        )

        self.assertEqual(0, result.returncode, result.stderr)
        calls = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
        self.assertIn(
            [
                str(self.parser),
                str(self.evidence / "round-0001"),
                "--final-task",
                str(self.task),
            ],
            calls,
        )

    def test_both_preserves_successful_solver_when_target_fails(self) -> None:
        result = self.run_runner("both", env={"FAKE_HARBOR_FAIL_MODEL": "target-model"})
        self.assertEqual(17, result.returncode)
        round_dir = self.evidence / "round-0001"
        self.assertEqual("17\n", (round_dir / "target/run-0001/exit-code").read_text())
        self.assertEqual("0\n", (round_dir / "solver/run-0001/exit-code").read_text())

    def test_both_rejects_invalid_other_arm_url_before_allocating_evidence(self) -> None:
        result = self.run_runner("both", env={"HARBOR_SOLVER_BASE_URL": "not-a-url"})
        self.assertNotEqual(0, result.returncode)
        self.assertIn("hostname", result.stderr)
        self.assertFalse(self.evidence.exists())
        self.assertEqual([], self.read_captured_commands())

    def test_numbering_reports_exhaustion_without_creating_five_digit_directories(self) -> None:
        (self.evidence / "round-9999").mkdir(parents=True)
        round_result = self.run_runner("target")
        self.assertNotEqual(0, round_result.returncode)
        self.assertIn("exhausted", round_result.stderr)
        self.assertFalse((self.evidence / "round-10000").exists())
        (self.evidence / "round-9999").rmdir()
        self.assertEqual(0, self.run_runner("target").returncode)
        run_root = self.evidence / "round-0001/target/run-9999"
        run_root.mkdir(parents=True)
        run_result = self.run_runner("target", "--round", "1")
        self.assertNotEqual(0, run_result.returncode)
        self.assertIn("exhausted", run_result.stderr)
        self.assertFalse((self.evidence / "round-0001/target/run-10000").exists())

    def test_both_existing_round_preflights_every_arm_number_before_launching(self) -> None:
        self.assertEqual(0, self.run_runner("target").returncode)
        self.capture.unlink()
        solver_root = self.evidence / "round-0001/solver/run-9999"
        solver_root.mkdir(parents=True)
        result = self.run_runner("both", "--round", "1", env={"FAKE_HARBOR_SLEEP": "5"})
        self.assertNotEqual(0, result.returncode)
        self.assertIn("exhausted", result.stderr)
        self.assertEqual([], self.read_captured_commands())
        self.assertFalse((self.evidence / "round-0001/target/run-0002").exists())
        self.assertFalse((self.evidence / "round-0001/solver/run-10000").exists())

    def test_concurrent_same_arm_append_is_rejected_before_allocation(self) -> None:
        self.assertEqual(0, self.run_runner("target").returncode)
        self.capture.unlink()
        harbor_barrier = self.root / "harbor-barrier"
        harbor_barrier.mkdir()
        env = self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(harbor_barrier)}
        processes = [
            subprocess.Popen([str(RUNNER), "target", "--round", "1"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        ]
        try:
            self.wait_for_barrier(harbor_barrier, 1)
            rejected = self.run_runner("target", "--round", "1")
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("another two-model invocation is active", rejected.stderr)
            self.assertFalse((self.evidence / "round-0001/target/run-0003").exists())
            self.assertFalse((self.runtime_evidence / "round-0001/target/run-0003").exists())
            (harbor_barrier / "release").write_text("", encoding="utf-8")
            _stdout, stderr = processes[0].communicate(timeout=5)
            self.assertEqual(0, processes[0].returncode, stderr)
        finally:
            self.stop_processes(processes)

    def test_concurrent_default_invocation_is_rejected_but_both_arms_overlap(self) -> None:
        harbor_barrier = self.root / "harbor-barrier"
        harbor_barrier.mkdir()
        env = self.base_env | {"FAKE_HARBOR_BARRIER_DIR": str(harbor_barrier)}
        processes = [
            subprocess.Popen([str(RUNNER), "both"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        ]
        try:
            self.wait_for_barrier(harbor_barrier, 2)
            rejected = self.run_runner("target")
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("another two-model invocation is active", rejected.stderr)
            self.assertFalse((self.evidence / "round-0002").exists())
            self.assertFalse((self.runtime_evidence / "round-0002").exists())
            (harbor_barrier / "release").write_text("", encoding="utf-8")
            _stdout, stderr = processes[0].communicate(timeout=5)
            self.assertEqual(0, processes[0].returncode, stderr)
        finally:
            self.stop_processes(processes)

    def test_signal_cleanup_targets_only_current_fake_harbor_children(self) -> None:
        unrelated = subprocess.Popen(["sleep", "30"])
        try:
            env = self.base_env | {"FAKE_HARBOR_SLEEP": "30"}
            runner = subprocess.Popen([str(RUNNER), "both"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            deadline = time.monotonic() + 5
            while len(self.read_metadata()) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(2, len(self.read_metadata()))
            runner.send_signal(signal.SIGTERM)
            runner.communicate(timeout=5)
            self.assertFalse((self.runtime_evidence / "round-0001/.active").exists())
            self.assertTrue((self.evidence / "round-0001/target/run-0001/jobs/job-0001/config.json").is_file())
            self.assertFalse((self.evidence / "round-0001/target/run-0001/jobs/job-0001/result.json").exists())
            child_pids = {str(item["pid"]) for item in self.read_metadata()}
            signalled = set(self.signal_log.read_text(encoding="utf-8").splitlines())
            self.assertEqual(child_pids, signalled)
            for arm in ("target", "solver"):
                exit_code = self.evidence / f"round-0001/{arm}/run-0001/exit-code"
                self.assertTrue(exit_code.is_file())
                self.assertRegex(exit_code.read_text(), r"^[1-9][0-9]*\n$")
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)

    def test_regrade_signal_cleanup_targets_only_current_fake_harbor_children(self) -> None:
        source_round = self.prepare_regrade_rollout()
        self.make_regrade_source(source_round, "target")
        self.make_regrade_source(source_round, "solver")
        self.metadata.unlink()
        unrelated = subprocess.Popen(["sleep", "30"])
        try:
            env = self.base_env | {"FAKE_HARBOR_SLEEP": "30"}
            runner = subprocess.Popen([str(RUNNER), "regrade"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            deadline = time.monotonic() + 5
            while len(self.read_metadata()) < 2 and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(2, len(self.read_metadata()))
            runner.send_signal(signal.SIGTERM)
            runner.communicate(timeout=5)
            self.assertEqual(143, runner.returncode)
            self.assertFalse((self.runtime_evidence / "round-0002").exists())
            self.assertTrue((source_round / "rollout.lock").is_file())
            self.assertTrue((self.evidence / "round-0002/round.json").is_file())
            child_pids = {str(item["pid"]) for item in self.read_metadata()}
            signalled = set(self.signal_log.read_text(encoding="utf-8").splitlines())
            self.assertEqual(child_pids, signalled)
            for arm in ("target", "solver"):
                exit_code = self.evidence / f"round-0002/{arm}/run-0001/exit-code"
                self.assertTrue(exit_code.is_file())
                self.assertRegex(exit_code.read_text(), r"^[1-9][0-9]*\n$")
            self.assertIsNone(unrelated.poll())
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)

    def test_signal_after_fast_arm_reap_preserves_its_success_exit_code(self) -> None:
        active_runs = self.root / "active-runs.txt"
        env = self.base_env | {
            "FAKE_HARBOR_SLEEP_SOLVER": "30",
            "SOP_TEST_ACTIVE_RUNS_PATH": str(active_runs),
        }
        runner = subprocess.Popen(
            [str(RUNNER), "both"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        try:
            target_exit = self.evidence / "round-0001/target/run-0001/exit-code"
            deadline = time.monotonic() + 5
            expected_active = str(self.evidence / "round-0001/solver/run-0001")
            while (
                not target_exit.is_file()
                or target_exit.read_text() != "0\n"
                or not active_runs.is_file()
                or active_runs.read_text().strip() != expected_active
                or len(self.read_metadata()) < 2
            ) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual("0\n", target_exit.read_text())
            self.assertEqual(expected_active, active_runs.read_text().strip())
            self.assertEqual(2, len(self.read_metadata()))
            runner.send_signal(signal.SIGTERM)
            runner.communicate(timeout=5)
            solver_exit = self.evidence / "round-0001/solver/run-0001/exit-code"
            self.assertEqual("0\n", target_exit.read_text())
            self.assertEqual("143\n", solver_exit.read_text())
            for arm in ("target", "solver"):
                run = self.evidence / f"round-0001/{arm}/run-0001"
                self.assertTrue((run / "jobs").is_dir())
                self.assertTrue((run / "harbor.log").is_file())
                self.assertTrue((run / "exit-code").is_file())
        finally:
            if runner.poll() is None:
                runner.terminate()
                runner.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
