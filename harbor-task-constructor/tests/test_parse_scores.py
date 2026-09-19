"""Behavioral tests for the read-only Harbor score parser."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from template.environment.method.internal.evidence_retention import (
    publish_run,
    write_round_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "template" / "environment" / "method" / "parse_scores.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class ParseScoresTests(unittest.TestCase):
    def setUp(self) -> None:
        spec = importlib.util.spec_from_file_location("parse_scores", MODULE)
        assert spec and spec.loader
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()
        sys.modules.pop("parse_scores", None)

    @staticmethod
    def flat_details(programmatic: float | None, judge: float = 1.0) -> dict:
        reward = [
            {
                "score": judge,
                "kind": "agent",
                "criteria": [{"name": "delivered", "value": judge, "raw": "yes", "weight": 1.0}],
            }
        ]
        if programmatic is not None:
            reward.insert(
                0,
                {
                    "score": programmatic,
                    "kind": "programmatic",
                    "criteria": [
                        {"name": "builds", "value": 1.0, "raw": True, "weight": 1.0},
                        {"name": "runs", "value": 0.0, "raw": False, "weight": 2.0},
                    ],
                },
            )
        return {"reward": reward}

    def make_trial(
        self,
        *,
        exception_type: str | None,
        programmatic: float | None,
        details: dict | None = None,
        digest: str = "sha256:fixture",
        name: str = "task__one",
    ) -> Path:
        trial = self.root / name
        write_json(
            trial / "lock.json",
            {"task": {"digest": digest}, "agent": {"name": "claude-code", "model_name": "example/model"}},
        )
        write_json(
            trial / "result.json",
            {"exception_info": None if exception_type is None else {"type": exception_type}},
        )
        write_json(trial / "verifier" / "reward-details.json", details or self.flat_details(programmatic))
        return trial

    def make_arm(
        self,
        round_dir: Path,
        arm: str,
        run: str,
        scores: list[float],
        *,
        digest: str = "sha256:fixture",
        regrade: bool = False,
    ) -> Path:
        run_dir = round_dir / arm / run
        job = run_dir / "jobs" / "job-0001" / "2026-09-02__20-10-22"
        if regrade:
            config = {
                "job_name": "2026-09-02__20-10-22",
                "jobs_dir": str(run_dir / "jobs"),
                "n_concurrent_trials": 2,
                "tasks": [{"path": "/current/task"}],
                "source_jobs": [{"action": "regrade", "type": "local", "path": "/source/job"}],
            }
        else:
            config = {
                "n_attempts": len(scores),
                "n_concurrent_trials": 2,
                "retry": {"max_retries": 1},
                "tasks": [{"path": "/current/task"}],
                "agents": [{"name": "claude-code", "model_name": "example/model", "kwargs": {"reasoning_effort": "high"}}],
            }
        write_json(
            job / "config.json",
            config,
        )
        # Harbor's job-level directory can itself have a lock, but it is not a
        # concrete task trial and cannot carry a task digest.
        write_json(job / "lock.json", {"task": {"path": "/source/task"}})
        write_json(job / "result.json", {"exception_info": {"type": "BatchFailure"}})
        for number, score in enumerate(scores, 1):
            trial = job / f"task__{number:03d}"
            write_json(
                trial / "lock.json",
                {
                    "task": {"digest": digest},
                    "agent": {
                        "name": "claude-code",
                        "model_name": "example/model",
                        "kwargs": {"reasoning_effort": "high"},
                    },
                },
            )
            write_json(trial / "result.json", {"exception_info": None})
            write_json(trial / "verifier" / "reward-details.json", self.flat_details(score))
        return run_dir

    def make_full_and_compact_rounds(self) -> tuple[Path, Path]:
        """Publish a real two-arm round whose trials exercise exception policy."""
        full_round = self.root / "full" / "round-0001"
        cases = {
            "target": [
                (0.2, None),
                (0.4, "AgentTimeoutError"),
                (None, "AgentTimeoutError"),
            ],
            "solver": [(0.9, None), (0.7, "UnknownApiError")],
        }
        for arm, trials in cases.items():
            run = full_round / arm / "run-0001"
            job = run / "jobs" / "job-0001"
            write_json(
                job / "config.json",
                {
                    "n_attempts": len(trials),
                    "n_concurrent_trials": 2,
                    "retry": {"max_retries": 0},
                    "tasks": [{"path": "/runtime/task"}],
                    "agents": [{"name": "claude-code", "model_name": f"{arm}/model"}],
                },
            )
            write_json(job / "result.json", {"exception_info": {"type": "BatchFailure"}})
            for number, (score, exception_type) in enumerate(trials, 1):
                trial = job / f"task__{number:03d}"
                write_json(
                    trial / "lock.json",
                    {
                        "task": {"digest": "sha256:fixture"},
                        "agent": {"name": "claude-code", "model_name": f"{arm}/model"},
                    },
                )
                write_json(
                    trial / "result.json",
                    {"exception_info": None if exception_type is None else {"type": exception_type}},
                )
                write_json(
                    trial / "verifier" / "reward-details.json",
                    self.flat_details(score),
                )
                (trial / "artifacts" / "workspace").mkdir(parents=True)
                (trial / "artifacts" / "workspace" / "private.txt").write_text(
                    "not score evidence", encoding="utf-8"
                )

        compact_round = self.root / "compact" / "round-0001"
        for arm in cases:
            compact_run = compact_round / arm / "run-0001"
            compact_run.mkdir(parents=True)
            publish_run(full_round / arm / "run-0001", compact_run, include_agent=True)
        write_round_metadata(compact_round, kind="real", source_round=None)
        return full_round, compact_round

    @staticmethod
    def normalize_trial_paths(report: dict[str, object]) -> dict[str, object]:
        """Mask only temporary trial-directory locations, not diagnostic paths."""
        normalized = deepcopy(report)
        for arm in normalized["arms"].values():
            for trial in arm["trials"]:
                trial["path"] = "<trial-path>"
        return normalized

    def test_regrade_job_uses_preserved_trial_lock_model_metadata(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2, 0.4], regrade=True)
        got = self.module.parse_arm_run(arm)
        self.assertEqual(2, got["requested"])
        self.assertEqual(2, got["concurrency"])
        self.assertEqual(0, got["max_retries"])
        self.assertEqual("example/model", got["model"])
        self.assertEqual("high", got["reasoning_effort"])

    def test_unsupported_source_action_with_agents_keeps_ordinary_model_validation(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2])
        config_path = next(arm.rglob("config.json"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["source_jobs"] = [{"action": "resume", "type": "local", "path": "/source/job"}]
        config["agents"][0]["model_name"] = "configured/other"
        write_json(config_path, config)

        with self.assertRaisesRegex(self.module.ReadingError, "configured model"):
            self.module.parse_arm_run(arm)

    def test_unsupported_source_only_action_does_not_qualify_as_job_config(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2], regrade=True)
        config_path = next(arm.rglob("config.json"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["source_jobs"][0]["action"] = "resume"
        write_json(config_path, config)

        with self.assertRaisesRegex(self.module.ReadingError, "one qualifying Harbor job config"):
            self.module.parse_arm_run(arm)

    def test_ordinary_job_uses_harbor_defaults_when_optional_fields_are_omitted(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2])
        config_path = next(arm.rglob("config.json"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        del config["n_attempts"]
        del config["n_concurrent_trials"]
        del config["retry"]
        write_json(config_path, config)
        got = self.module.parse_arm_run(arm)
        self.assertEqual(1, got["requested"])
        self.assertEqual(4, got["concurrency"])
        self.assertEqual(0, got["max_retries"])
        self.assertEqual("example/model", got["model"])
        self.assertEqual("high", got["reasoning_effort"])

    def test_regrade_job_rejects_mixed_included_lock_models(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2, 0.4], regrade=True)
        second_lock = sorted(arm.rglob("task__*/lock.json"))[1]
        lock = json.loads(second_lock.read_text(encoding="utf-8"))
        lock["agent"]["model_name"] = "other/model"
        write_json(second_lock, lock)
        with self.assertRaisesRegex(self.module.ReadingError, "one included resolved model"):
            self.module.parse_arm_run(arm)

    def test_regrade_job_rejects_mixed_non_null_lock_reasoning_efforts(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2, 0.4], regrade=True)
        second_lock = sorted(arm.rglob("task__*/lock.json"))[1]
        lock = json.loads(second_lock.read_text(encoding="utf-8"))
        lock["agent"]["kwargs"]["reasoning_effort"] = "low"
        write_json(second_lock, lock)
        with self.assertRaisesRegex(self.module.ReadingError, "one resolved reasoning effort"):
            self.module.parse_arm_run(arm)

    def test_nested_singular_task_config_does_not_qualify_as_job_config(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2])
        trial = next(arm.rglob("task__*"))
        write_json(
            trial / "config.json",
            {
                "task": {"path": "/current/task"},
                "trial_name": trial.name,
                "trials_dir": str(trial.parent),
                "agent": {"name": "claude-code", "model_name": "example/model"},
                "job_id": "fixture-job-id",
            },
        )
        got = self.module.parse_arm_run(arm)
        self.assertEqual(1, got["requested"])
        self.assertEqual(1, got["valid"])

    def test_arm_rejects_multiple_genuine_regrade_job_configs(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2], regrade=True)
        first_config = next(arm.rglob("config.json"))
        config = json.loads(first_config.read_text(encoding="utf-8"))
        second_job = arm / "jobs" / "job-0002" / "2026-09-03__00-00-00"
        config["job_name"] = "2026-09-03__00-00-00"
        write_json(second_job / "config.json", config)
        with self.assertRaisesRegex(self.module.ReadingError, "one qualifying Harbor job config"):
            self.module.parse_arm_run(arm)

    def test_flat_reward_details_selects_programmatic_not_agent_judge(self) -> None:
        trial = self.make_trial(exception_type=None, programmatic=0.25, name="flat")
        got = self.module.parse_trial(trial)
        self.assertTrue(got["included"])
        self.assertEqual(0.25, got["programmatic_score"])
        self.assertEqual([1.0], [item["score"] for item in got["agent_judges"]])

    def test_exception_policy_distinguishes_timeout_from_interference(self) -> None:
        cases = [
            ("AgentTimeoutError", 0.4, "timed_out_scored", True),
            ("AgentTimeoutError", None, "timed_out_unscored", False),
            ("UnknownApiError", 0.0, "provider_error", False),
            ("DaytonaConnectionError", 0.7, "environment_error", False),
            ("CancelledError", 0.7, "cancelled", False),
            ("RewardFileNotFoundError", None, "verifier_error", False),
            ("UnclassifiedFailure", 0.7, "unknown_invalid", False),
        ]
        for exception_type, score, state, included in cases:
            with self.subTest(exception_type=exception_type):
                trial = self.make_trial(exception_type=exception_type, programmatic=score, name=exception_type)
                got = self.module.parse_trial(trial)
                self.assertEqual(state, got["state"])
                self.assertEqual(included, got["included"])

    def test_compact_published_round_matches_full_parser_report(self) -> None:
        full_round, compact_round = self.make_full_and_compact_rounds()

        full = self.module.parse_round(full_round)
        compact = self.module.parse_round(compact_round)

        self.assertFalse(any(compact_round.rglob("artifacts/workspace")))
        self.assertEqual(
            [criterion["path"] for criterion in full["criteria"]],
            [criterion["path"] for criterion in compact["criteria"]],
        )
        self.assertEqual(
            self.normalize_trial_paths(full), self.normalize_trial_paths(compact)
        )
        self.assertEqual(full["arms"]["target"]["mean"], compact["arms"]["target"]["mean"])
        self.assertEqual(full["arms"]["solver"]["mean"], compact["arms"]["solver"]["mean"])
        self.assertEqual(full["R"], compact["R"])
        self.assertEqual(full["reward"], compact["reward"])
        self.assertEqual(
            ["completed", "timed_out_scored", "timed_out_unscored", "completed", "provider_error"],
            [
                trial["state"]
                for arm in (compact["arms"]["target"], compact["arms"]["solver"])
                for trial in arm["trials"]
            ],
        )

    def test_nested_all_programmatic_group_is_readable_with_qualified_paths(self) -> None:
        details = {
            "reward": {
                "kind": "group",
                "score": 0.5,
                "components": [
                    {"name": "left", "detail": {"kind": "programmatic", "score": 0.4, "criteria": [{"name": "same", "value": 0.4}]}},
                    {"name": "right", "detail": {"kind": "programmatic", "score": 0.6, "criteria": [{"name": "same", "value": 0.6}]}},
                ],
            }
        }
        got = self.module.parse_trial(self.make_trial(exception_type=None, programmatic=None, details=details, name="nested"))
        self.assertTrue(got["included"])
        self.assertEqual(0.5, got["programmatic_score"])
        self.assertEqual(["left/same", "right/same"], [item["path"] for item in got["criteria"]])

    def test_ambiguous_nested_groups_and_missing_programmatic_are_invalid(self) -> None:
        details = {"reward": [
            {"kind": "group", "score": 0.2, "components": [{"detail": {"kind": "programmatic", "score": 0.2}}]},
            {"kind": "group", "score": 0.3, "components": [{"detail": {"kind": "programmatic", "score": 0.3}}]},
        ]}
        got = self.module.parse_trial(self.make_trial(exception_type=None, programmatic=None, details=details, name="ambiguous"))
        self.assertFalse(got["included"])
        self.assertEqual("unknown_invalid", got["state"])

    def test_completed_zero_is_included_and_batch_result_is_ignored(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.0])
        got = self.module.parse_arm_run(arm)
        self.assertEqual(1, got["valid"])
        self.assertEqual(0.0, got["mean"])
        self.assertEqual([], got["invalid_trials"])

    def test_latest_numbered_and_parse_round_use_only_greatest_arm_run(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        self.make_arm(round_dir, "target", "run-0001", [0.1])
        self.make_arm(round_dir, "target", "run-0002", [0.8])
        self.make_arm(round_dir, "solver", "run-0001", [1.0])
        got = self.module.parse_round(round_dir)
        self.assertEqual("run-0002", got["arms"]["target"]["run"])
        self.assertEqual(0.8, got["arms"]["target"]["mean"])
        self.assertEqual("run-0002", self.module.latest_numbered(round_dir / "target", "run-").name)
        with self.assertRaises(self.module.ReadingError):
            self.module.latest_numbered(self.root, "round-")

    def test_arm_surfaces_job_sampling_and_preserves_missing_criterion_values(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2, 0.4])
        second = next((arm / "jobs").rglob("task__002"))
        details = self.flat_details(0.4)
        details["reward"][0]["criteria"] = [{"name": "only-second", "value": 1.0, "weight": 1.0}]
        write_json(second / "verifier" / "reward-details.json", details)
        got = self.module.parse_arm_run(arm)
        self.assertEqual(2, got["requested"])
        self.assertEqual(2, got["valid"])
        self.assertEqual(2, got["concurrency"])
        self.assertEqual(1, got["max_retries"])
        self.assertEqual("example/model", got["model"])
        self.assertEqual("high", got["reasoning_effort"])
        self.assertEqual({"builds": [1.0, None], "runs": [0.0, None], "only-second": [None, 1.0]}, {x["path"]: x["values"] for x in got["criteria"]})

    def test_locks_must_agree_and_final_task_digest_is_enforced(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        self.make_arm(round_dir, "target", "run-0001", [0.2], digest="sha256:a")
        self.make_arm(round_dir, "solver", "run-0001", [0.8], digest="sha256:b")
        with self.assertRaises(self.module.ReadingError):
            self.module.parse_round(round_dir)

        final_task = self.root / "task"
        final_task.mkdir()
        (final_task / "task.toml").write_text("[task]\nid = 'fixture'\n", encoding="utf-8")
        (final_task / "instruction.md").write_text("first instruction", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        matching = self.root / "evidence" / "round-0002"
        self.make_arm(matching, "target", "run-0001", [0.2], digest=digest)
        self.make_arm(matching, "solver", "run-0001", [0.8], digest=digest)
        self.assertEqual(digest, self.module.check_round_task(matching, final_task))
        (final_task / "instruction.md").write_text("changed instruction", encoding="utf-8")
        with self.assertRaises(self.module.ReadingError):
            self.module.check_round_task(matching, final_task)

    def test_round_scores_cover_finite_infinite_zero_and_negative_cases(self) -> None:
        cases = [
            ("finite", [0.8828], [0.9375], 0.061962, 0.058347, "finite", False),
            ("infinite", [0.0], [0.5], None, 1.0, "infinite", True),
            ("both-zero", [0.0], [0.0], 0.0, 0.0, "finite", False),
            ("negative", [0.8], [0.4], -0.5, 0.0, "finite", False),
        ]
        for name, target_scores, solver_scores, R, reward, state, clears in cases:
            with self.subTest(name=name):
                round_dir = self.root / "scores" / name / "round-0001"
                self.make_arm(round_dir, "target", "run-0001", target_scores)
                self.make_arm(round_dir, "solver", "run-0001", solver_scores)
                got = self.module.parse_round(round_dir)
                if R is None:
                    self.assertIsNone(got["R"])
                else:
                    self.assertAlmostEqual(R, got["R"], places=6)
                self.assertAlmostEqual(reward, got["reward"], places=6)
                self.assertEqual(state, got["R_state"])
                self.assertEqual(clears, got["clears_target_R"])

    def test_round_separates_score_gates_and_surfaces_binary_quality_red_flags(self) -> None:
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.5, 0.5, 0.5], digest=digest)
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.8, 0.8, 0.8], digest=digest)

        target_values = [
            {"both-pass": 1.0, "useful": 0.0, "reverse": 1.0, "both-fail": 0.0, "continuous": 0.2},
            {"both-pass": 1.0, "useful": 0.0, "reverse": 1.0, "both-fail": 0.0, "continuous": 0.3},
            {"both-pass": 1.0, "useful": 1.0, "reverse": 0.0, "both-fail": 0.0, "continuous": 0.4},
        ]
        solver_values = [
            {"both-pass": 1.0, "useful": 1.0, "reverse": 0.0, "both-fail": 0.0, "continuous": 0.6},
            {"both-pass": 1.0, "useful": 1.0, "reverse": 0.0, "both-fail": 0.0, "continuous": 0.7},
            {"both-pass": 0.0, "useful": 1.0, "reverse": 1.0, "both-fail": 1.0, "continuous": 0.8},
        ]
        for trial, score, values in [
            *zip(sorted(target.rglob("task__*")), [0.5] * 3, target_values),
            *zip(sorted(solver.rglob("task__*")), [0.8] * 3, solver_values),
        ]:
            details = self.flat_details(score)
            details["reward"][0]["criteria"] = [
                {"name": name, "value": value, "weight": 1.0}
                for name, value in values.items()
            ]
            write_json(trial / "verifier" / "reward-details.json", details)

        got = self.module.parse_round(round_dir, final_task)
        self.assertEqual(
            {"target_mean_lt_0_7": True, "R_gt_0_2": True, "all": True},
            got["score_gates"],
        )
        self.assertTrue(got["clears_target_mean"])
        self.assertTrue(got["clears_R"])
        self.assertTrue(got["clears_all_gates"])
        self.assertEqual(
            {
                "both_pass": ["both-pass"],
                "target_fail_solver_pass": ["useful"],
                "target_pass_solver_fail": ["reverse"],
                "both_fail": ["both-fail"],
            },
            got["quality_scan"]["binary_quadrants"],
        )
        self.assertEqual(["continuous"], got["quality_scan"]["unclassified"])
        self.assertEqual(0.25, got["quality_scan"]["both_pass_share"])
        self.assertEqual(["direction_reversal", "both_fail"], got["quality_scan"]["red_flags"])
        self.assertEqual("inspect_red_flags", got["next_action"])
        self.assertIn("Stop fresh sampling", got["action_hint"])
        self.assertIn("regrade", got["action_hint"])

    def test_passing_clean_round_tells_cli_to_deliver_without_another_fresh_run(self) -> None:
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.5], digest=digest)
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.8], digest=digest)
        target_details = self.flat_details(0.5)
        target_details["reward"][0]["criteria"] = [{"name": "useful", "value": 0.0, "weight": 1.0}]
        solver_details = self.flat_details(0.8)
        solver_details["reward"][0]["criteria"] = [{"name": "useful", "value": 1.0, "weight": 1.0}]
        write_json(next(target.rglob("task__*")) / "verifier" / "reward-details.json", target_details)
        write_json(next(solver.rglob("task__*")) / "verifier" / "reward-details.json", solver_details)

        got = self.module.parse_round(round_dir, final_task)
        self.assertEqual([], got["quality_scan"]["red_flags"])
        self.assertEqual("deliver", got["next_action"])
        proc = subprocess.run(
            [sys.executable, str(MODULE), str(round_dir), "--final-task", str(final_task)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("NEXT_ACTION=deliver", proc.stdout)
        self.assertIn("Stop fresh sampling", proc.stdout)

    def test_compact_root_with_full_check_workspace_blocks_delivery_and_names_cleanup(self) -> None:
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        evidence = self.root / "evidence"
        round_dir = evidence / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.5], digest=digest)
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.8], digest=digest)
        target_details = self.flat_details(0.5)
        target_details["reward"][0]["criteria"] = [
            {"name": "useful", "value": 0.0, "weight": 1.0}
        ]
        solver_details = self.flat_details(0.8)
        solver_details["reward"][0]["criteria"] = [
            {"name": "useful", "value": 1.0, "weight": 1.0}
        ]
        write_json(next(target.rglob("task__*")) / "verifier" / "reward-details.json", target_details)
        write_json(next(solver.rglob("task__*")) / "verifier" / "reward-details.json", solver_details)
        write_round_metadata(round_dir, kind="real", source_round=None)
        full_workspace = (
            evidence
            / "checks/oracle/jobs/2026-09-06__18-23-17/task__trial/artifacts/workspace"
        )
        (full_workspace / "large-output.bin").parent.mkdir(parents=True)
        (full_workspace / "large-output.bin").write_bytes(b"large")
        nested_workspace = full_workspace / "node_modules/pkg/artifacts/workspace"
        nested_workspace.mkdir(parents=True)
        (nested_workspace / "sentinel.bin").write_bytes(b"must not be traversed")

        got = self.module.parse_round(round_dir, final_task)

        self.assertEqual(
            ["checks/oracle/jobs/2026-09-06__18-23-17/task__trial/artifacts/workspace"],
            got["quality_scan"]["collected_full_workspaces"],
        )
        self.assertIn("collected_full_workspaces", got["quality_scan"]["red_flags"])
        self.assertEqual("inspect_red_flags", got["next_action"])
        self.assertIn("/app/runtime/harbor-checks", got["action_hint"])
        self.assertIn("rerun the parser", got["action_hint"])
        self.assertNotIn("run nop/oracle", got["action_hint"])

    def test_full_check_workspace_cleanup_precedes_score_iteration(self) -> None:
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        evidence = self.root / "evidence"
        round_dir = evidence / "round-0001"
        self.make_arm(round_dir, "target", "run-0001", [0.8], digest=digest)
        self.make_arm(round_dir, "solver", "run-0001", [0.9], digest=digest)
        write_round_metadata(round_dir, kind="real", source_round=None)
        full_workspace = evidence / "checks/nop/jobs/job/task__trial/artifacts/workspace"
        full_workspace.mkdir(parents=True)

        got = self.module.parse_round(round_dir, final_task)

        self.assertFalse(got["clears_all_gates"])
        self.assertEqual("inspect_red_flags", got["next_action"])
        self.assertIn("/app/runtime/harbor-checks", got["action_hint"])
        self.assertIn("Reuse the current score round", got["action_hint"])

    def test_criterion_count_above_preference_is_advisory_and_still_allows_delivery(self) -> None:
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.5], digest=digest)
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.8], digest=digest)
        target_details = self.flat_details(0.5)
        target_details["reward"][0]["criteria"] = [
            {"name": f"useful-{number:02d}", "value": 0.0, "weight": 1.0}
            for number in range(51)
        ]
        solver_details = self.flat_details(0.8)
        solver_details["reward"][0]["criteria"] = [
            {"name": f"useful-{number:02d}", "value": 1.0, "weight": 1.0}
            for number in range(51)
        ]
        write_json(next(target.rglob("task__*")) / "verifier" / "reward-details.json", target_details)
        write_json(next(solver.rglob("task__*")) / "verifier" / "reward-details.json", solver_details)
        got = self.module.parse_round(round_dir, final_task)
        self.assertEqual(50, got["quality_scan"]["criterion_preferred_max"])
        self.assertTrue(got["quality_scan"]["criterion_count_high"])
        self.assertEqual(["criterion_count_high"], got["quality_scan"]["advisories"])
        self.assertEqual([], got["quality_scan"]["red_flags"])
        self.assertEqual("deliver", got["next_action"])
        self.assertIn("do not block delivery", got["action_hint"])

    def test_both_pass_majority_requests_one_review_without_resuming_fresh_sampling(self) -> None:
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        digest = self.module.harbor_task_digest(final_task)
        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.5], digest=digest)
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.8], digest=digest)
        target_details = self.flat_details(0.5)
        target_details["reward"][0]["criteria"] = [
            {"name": name, "value": value, "weight": 1.0}
            for name, value in {"both-1": 1.0, "both-2": 1.0, "both-3": 1.0, "useful": 0.0}.items()
        ]
        solver_details = self.flat_details(0.8)
        solver_details["reward"][0]["criteria"] = [
            {"name": name, "value": 1.0, "weight": 1.0}
            for name in ("both-1", "both-2", "both-3", "useful")
        ]
        write_json(next(target.rglob("task__*")) / "verifier" / "reward-details.json", target_details)
        write_json(next(solver.rglob("task__*")) / "verifier" / "reward-details.json", solver_details)

        got = self.module.parse_round(round_dir, final_task)
        self.assertEqual(0.75, got["quality_scan"]["both_pass_share"])
        self.assertEqual(["both_pass_dominates"], got["quality_scan"]["red_flags"])
        self.assertEqual("inspect_red_flags", got["next_action"])
        self.assertIn("not an automatic defect", got["action_hint"])
        self.assertIn("Stop fresh sampling", got["action_hint"])

    def test_round_that_only_clears_R_still_requires_iteration(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        self.make_arm(round_dir, "target", "run-0001", [0.8])
        self.make_arm(round_dir, "solver", "run-0001", [1.0])
        got = self.module.parse_round(round_dir)
        self.assertTrue(got["clears_target_R"])
        self.assertTrue(got["clears_R"])
        self.assertFalse(got["clears_target_mean"])
        self.assertFalse(got["clears_all_gates"])
        self.assertEqual("verify_final_task", got["next_action"])
        self.assertIn("--final-task", got["action_hint"])

    def test_trial_needs_only_lock_result_and_reward_details_not_run_or_score_json(self) -> None:
        trial = self.make_trial(exception_type=None, programmatic=0.5, name="minimal")
        self.assertFalse((trial / "run.json").exists())
        self.assertFalse((trial / "score.json").exists())
        self.assertTrue(self.module.parse_trial(trial)["included"])

    def test_trial_discovery_keeps_missing_result_or_lock_visible_and_checks_all_locks(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.3], digest="sha256:expected")
        self.make_arm(round_dir, "solver", "run-0001", [0.8], digest="sha256:expected")
        job = arm / "jobs" / "job-0001" / "2026-09-02__20-10-22"
        missing_lock = job / "task__missing_lock"
        write_json(missing_lock / "result.json", {"exception_info": None})
        write_json(missing_lock / "verifier" / "reward-details.json", self.flat_details(0.6))
        lock_only = job / "task__lock_only"
        write_json(lock_only / "lock.json", {"task": {"digest": "sha256:other"}})
        got = self.module.parse_arm_run(arm)
        self.assertEqual(2, got["invalid"])
        self.assertEqual({"task__missing_lock", "task__lock_only"}, {item["trial"] for item in got["invalid_trials"]})
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        with self.assertRaises(self.module.ReadingError):
            self.module.check_round_task(round_dir, final_task)

    def test_final_task_match_is_unknown_when_no_trial_lock_exists(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.2])
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.8])
        for lock in list(target.rglob("task__*/lock.json")) + list(solver.rglob("task__*/lock.json")):
            lock.unlink()
        final_task = self.root / "final-task"
        final_task.mkdir()
        (final_task / "instruction.md").write_text("fixture", encoding="utf-8")
        self.assertIsNone(self.module.check_round_task(round_dir, final_task))
        with self.assertRaisesRegex(self.module.ReadingError, "included resolved model"):
            self.module.parse_round(round_dir, final_task)

    def test_mixed_flat_and_nested_programmatic_candidates_are_ambiguous(self) -> None:
        details = {"reward": [
            {"kind": "programmatic", "score": 0.2, "criteria": []},
            {"kind": "group", "score": 0.3, "components": [{"detail": {"kind": "programmatic", "score": 0.3}}]},
        ]}
        got = self.module.parse_trial(self.make_trial(exception_type=None, programmatic=None, details=details, name="mixed"))
        self.assertFalse(got["included"])
        self.assertEqual("unknown_invalid", got["state"])

    def test_trial_reports_resolved_lock_model_separately_from_requested_job_model(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.5])
        trial_lock = next(arm.rglob("task__*/lock.json"))
        lock = json.loads(trial_lock.read_text(encoding="utf-8"))
        lock["agent"] = {"name": "claude-code", "model_name": "resolved/model"}
        write_json(trial_lock, lock)
        config = next(arm.rglob("config.json"))
        config_data = json.loads(config.read_text(encoding="utf-8"))
        config_data["agents"][0]["model_name"] = "resolved/model"
        write_json(config, config_data)
        got = self.module.parse_arm_run(arm)
        self.assertEqual("resolved/model", got["model"])
        self.assertEqual("resolved/model", got["trials"][0]["resolved_model"])
        self.assertEqual(["resolved/model"], got["resolved_models"])

    def test_nonfinite_programmatic_scores_and_criterion_values_are_invalid(self) -> None:
        for number in (math.nan, math.inf, -math.inf):
            with self.subTest(number=number):
                trial = self.make_trial(exception_type=None, programmatic=number, name=f"nonfinite-{repr(number)}")
                got = self.module.parse_trial(trial)
                self.assertFalse(got["included"])
                self.assertIsNone(got["programmatic_score"])
        details = self.flat_details(0.5)
        details["reward"][0]["criteria"][0]["value"] = math.nan
        details["reward"][0]["criteria"][0]["raw"] = math.nan
        got = self.module.parse_trial(self.make_trial(exception_type=None, programmatic=None, details=details, name="criterion-nan"))
        self.assertTrue(got["included"])
        self.assertIsNone(got["criteria"][0]["value"])
        self.assertIsNone(got["criteria"][0]["raw"])

    def test_cli_last_missing_root_is_a_clean_argument_error(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(MODULE), "--last", str(self.root / "missing")],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("error:", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_derived_overflow_is_a_reading_error_not_nonfinite_json(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        self.make_arm(round_dir, "target", "run-0001", [5e-324])
        self.make_arm(round_dir, "solver", "run-0001", [1e308])
        with self.assertRaisesRegex(self.module.ReadingError, "non-finite derived R"):
            self.module.parse_round(round_dir)
        proc = subprocess.run(
            [sys.executable, str(MODULE), str(round_dir), "--json"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("error: non-finite derived R", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def test_completed_requires_an_explicit_null_exception_info_key(self) -> None:
        trial = self.make_trial(exception_type=None, programmatic=0.4, name="missing-exception-key")
        write_json(trial / "result.json", {})
        got = self.module.parse_trial(trial)
        self.assertFalse(got["included"])
        self.assertEqual("unknown_invalid", got["state"])
        self.assertIn("exception_info", got["fault"])

    def test_included_trial_requires_a_resolved_lock_model(self) -> None:
        trial = self.make_trial(exception_type=None, programmatic=0.4, name="missing-lock-model")
        write_json(trial / "lock.json", {"task": {"digest": "sha256:fixture"}, "agent": {"name": "claude-code"}})
        got = self.module.parse_trial(trial)
        self.assertFalse(got["included"])
        self.assertEqual("unknown_invalid", got["state"])
        self.assertIn("resolved model", got["fault"])

    def test_arm_rejects_mixed_resolved_models_and_config_mismatch(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2, 0.4])
        locks = sorted(arm.rglob("task__*/lock.json"))
        changed = json.loads(locks[1].read_text(encoding="utf-8"))
        changed["agent"]["model_name"] = "other/model"
        write_json(locks[1], changed)
        with self.assertRaisesRegex(self.module.ReadingError, "resolved model"):
            self.module.parse_arm_run(arm)
        changed["agent"]["model_name"] = "example/model"
        write_json(locks[1], changed)
        config = next(arm.rglob("config.json"))
        configured = json.loads(config.read_text(encoding="utf-8"))
        configured["agents"][0]["model_name"] = "configured/other"
        write_json(config, configured)
        with self.assertRaisesRegex(self.module.ReadingError, "does not match"):
            self.module.parse_arm_run(arm)

    def test_arm_rejects_missing_or_multiple_configured_models(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2])
        config = next(arm.rglob("config.json"))
        data = json.loads(config.read_text(encoding="utf-8"))
        data["agents"] = []
        write_json(config, data)
        with self.assertRaisesRegex(self.module.ReadingError, "configured model"):
            self.module.parse_arm_run(arm)
        data["agents"] = [
            {"name": "claude-code", "model_name": "example/model"},
            {"name": "claude-code", "model_name": "second/model"},
        ]
        write_json(config, data)
        with self.assertRaisesRegex(self.module.ReadingError, "configured model"):
            self.module.parse_arm_run(arm)

    def test_round_reports_criterion_deltas_weights_and_agent_judge_diagnostics(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.2, 0.4])
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.6, 0.8])
        target_trials = sorted(target.rglob("task__*"))
        solver_trials = sorted(solver.rglob("task__*"))
        target_one = self.flat_details(0.2, judge=99.0)
        target_one["reward"][0]["criteria"] = [{"name": "shared", "value": 1.0, "weight": 2.0}]
        target_one["reward"][1]["judge_output"] = json.dumps({"reasoning": "judge reasoning"})
        target_one["reward"][1]["criteria"][0]["reasoning"] = "criterion reasoning"
        target_two = self.flat_details(0.4, judge=98.0)
        target_two["reward"][0]["criteria"] = [{"name": "target-only", "value": 0.2, "weight": 1.0}]
        solver_one = self.flat_details(0.6, judge=97.0)
        solver_one["reward"][0]["criteria"] = [{"name": "shared", "value": 0.5, "weight": 2.0}]
        solver_two = self.flat_details(0.8, judge=96.0)
        solver_two["reward"][0]["criteria"] = [{"name": "shared", "value": 0.75, "weight": 3.0}]
        for trial, details in zip(target_trials + solver_trials, [target_one, target_two, solver_one, solver_two]):
            write_json(trial / "verifier" / "reward-details.json", details)
        got = self.module.parse_round(round_dir)
        shared = next(row for row in got["criteria"] if row["path"] == "shared")
        self.assertEqual(None, shared["weight"])
        self.assertEqual({"target": [2.0], "solver": [2.0, 3.0]}, shared["weights"])
        self.assertEqual(1.0, shared["target_mean"])
        self.assertEqual(0.625, shared["solver_mean"])
        self.assertEqual(-0.375, shared["delta"])
        self.assertEqual(1, shared["target_missing"])
        self.assertEqual(0, shared["solver_missing"])
        target_only = next(row for row in got["criteria"] if row["path"] == "target-only")
        self.assertEqual(0.2, target_only["target_mean"])
        self.assertIsNone(target_only["solver_mean"])
        self.assertEqual(1, target_only["target_missing"])
        self.assertEqual(2, target_only["solver_missing"])
        self.assertIsNone(target_only["delta"])
        self.assertAlmostEqual(1.3333333333, got["R"], places=6)
        self.assertEqual(99.0, got["agent_judges"][0]["score"])
        self.assertEqual(json.dumps({"reasoning": "judge reasoning"}), got["agent_judges"][0]["judge_output"])
        self.assertEqual("criterion reasoning", got["agent_judges"][0]["criteria"][0]["reasoning"])
        proc = subprocess.run([sys.executable, str(MODULE), str(round_dir)], capture_output=True, text=True)
        self.assertEqual(0, proc.returncode)
        self.assertIn("criterion", proc.stdout)
        self.assertIn("shared", proc.stdout)
        self.assertIn("agent judges", proc.stdout)
        self.assertIn("judge reasoning", proc.stdout)
        self.assertIn("criterion reasoning", proc.stdout)

    def test_nested_programmatic_group_keeps_top_level_agent_judge_diagnostic(self) -> None:
        def details(score: float, judge_score: float) -> dict:
            return {
                "program": {
                    "kind": "group",
                    "score": score,
                    "components": [{
                        "name": "programmatic",
                        "detail": {"kind": "programmatic", "score": score, "criteria": [{"name": "checks", "value": score, "weight": 1.0}]},
                    }],
                },
                "judge": {
                    "kind": "agent",
                    "score": judge_score,
                    "judge_output": json.dumps({"reasoning": "nested judge reasoning"}),
                    "criteria": [{"name": "quality", "value": judge_score, "weight": 1.0, "reasoning": "nested criterion reasoning"}],
                },
            }

        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.2])
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.4])
        target_trial = next(target.rglob("task__*"))
        solver_trial = next(solver.rglob("task__*"))
        write_json(target_trial / "verifier" / "reward-details.json", details(0.2, 99.0))
        write_json(solver_trial / "verifier" / "reward-details.json", details(0.4, 1.0))
        got = self.module.parse_round(round_dir)
        self.assertEqual(1.0, got["R"])
        self.assertEqual(99.0, got["agent_judges"][0]["score"])
        self.assertEqual(json.dumps({"reasoning": "nested judge reasoning"}), got["agent_judges"][0]["judge_output"])
        self.assertEqual("nested criterion reasoning", got["agent_judges"][0]["criteria"][0]["reasoning"])
        self.assertEqual(["programmatic/checks"], [row["path"] for row in got["criteria"]])
        write_json(target_trial / "verifier" / "reward-details.json", details(0.2, -99.0))
        self.assertEqual(1.0, self.module.parse_round(round_dir)["R"])

    def test_model_identity_normalizes_whitespace_in_lock_and_config(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.4])
        lock_path = next(arm.rglob("task__*/lock.json"))
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        lock["agent"]["model_name"] = "  example/model  "
        write_json(lock_path, lock)
        config_path = next(arm.rglob("config.json"))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["agents"][0]["model_name"] = "  example/model  "
        write_json(config_path, config)
        got = self.module.parse_arm_run(arm)
        self.assertEqual("example/model", got["model"])
        self.assertEqual(["example/model"], got["resolved_models"])

    def test_single_object_programmatic_rewardkit_detail_is_included(self) -> None:
        details = {
            "reward": {
                "score": 1.0,
                "criteria": [{
                    "name": "answer_is_ready",
                    "value": 1.0,
                    "raw": True,
                    "weight": 1.0,
                    "description": "answer_is_ready",
                }],
                "kind": "programmatic",
            }
        }
        got = self.module.parse_trial(
            self.make_trial(exception_type=None, programmatic=None, details=details, name="single-object")
        )
        self.assertTrue(got["included"])
        self.assertEqual(1.0, got["programmatic_score"])
        self.assertEqual(["answer_is_ready"], [criterion["path"] for criterion in got["criteria"]])
        self.assertEqual([], got["agent_judges"])

    def test_round_reads_single_object_programmatic_rewardkit_details(self) -> None:
        def details(score: float, value: float) -> dict:
            return {
                "reward": {
                    "score": score,
                    "criteria": [{
                        "name": "answer_is_ready",
                        "value": value,
                        "raw": value == 1.0,
                        "weight": 1.0,
                        "description": "answer_is_ready",
                    }],
                    "kind": "programmatic",
                }
            }

        round_dir = self.root / "evidence" / "round-0001"
        target = self.make_arm(round_dir, "target", "run-0001", [0.25])
        solver = self.make_arm(round_dir, "solver", "run-0001", [0.5])
        write_json(next(target.rglob("task__*")) / "verifier" / "reward-details.json", details(0.25, 0.25))
        write_json(next(solver.rglob("task__*")) / "verifier" / "reward-details.json", details(0.5, 0.5))
        got = self.module.parse_round(round_dir)
        self.assertEqual(0.25, got["arms"]["target"]["mean"])
        self.assertEqual(0.5, got["arms"]["solver"]["mean"])
        self.assertEqual(1.0, got["R"])
        self.assertEqual(0.5, got["reward"])
        self.assertEqual("answer_is_ready", got["criteria"][0]["path"])
        self.assertEqual(0.25, got["criteria"][0]["target_mean"])
        self.assertEqual(0.5, got["criteria"][0]["solver_mean"])

    def test_arm_rejects_two_qualifying_jobs_even_with_different_reasoning(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2])
        first_job = next(arm.rglob("config.json")).parent
        second_job = arm / "jobs" / "job-0002" / "2026-09-03__00-00-00"
        config = json.loads((first_job / "config.json").read_text(encoding="utf-8"))
        config["agents"][0]["kwargs"]["reasoning_effort"] = "low"
        write_json(second_job / "config.json", config)
        write_json(second_job / "task__002" / "lock.json", {"task": {"digest": "sha256:fixture"}, "agent": {"name": "claude-code", "model_name": "example/model"}})
        write_json(second_job / "task__002" / "result.json", {"exception_info": None})
        write_json(second_job / "task__002" / "verifier" / "reward-details.json", self.flat_details(0.4))
        with self.assertRaisesRegex(self.module.ReadingError, "one qualifying Harbor job config"):
            self.module.parse_arm_run(arm)

    def test_arm_rejects_two_identical_jobs_before_combining_their_trials(self) -> None:
        round_dir = self.root / "evidence" / "round-0001"
        arm = self.make_arm(round_dir, "target", "run-0001", [0.2])
        first_job = next(arm.rglob("config.json")).parent
        second_job = arm / "jobs" / "job-0002" / "2026-09-03__00-00-00"
        config = json.loads((first_job / "config.json").read_text(encoding="utf-8"))
        write_json(second_job / "config.json", config)
        write_json(second_job / "task__002" / "lock.json", {"task": {"digest": "sha256:fixture"}, "agent": {"name": "claude-code", "model_name": "example/model"}})
        write_json(second_job / "task__002" / "result.json", {"exception_info": None})
        write_json(second_job / "task__002" / "verifier" / "reward-details.json", self.flat_details(0.4))
        with self.assertRaisesRegex(self.module.ReadingError, "one qualifying Harbor job config"):
            self.module.parse_arm_run(arm)


if __name__ == "__main__":
    unittest.main()
