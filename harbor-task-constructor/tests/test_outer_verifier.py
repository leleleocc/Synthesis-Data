"""Black-box tests for the evidence-only outer verifier."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from template.environment.method.internal.evidence_retention import (
    publish_run,
    write_round_metadata,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "template"
VERIFY = TEMPLATE / "tests" / "verify.py"
PARSER = Path(
    os.environ.get(
        "SOP_TEST_PARSER_PATH",
        TEMPLATE / "environment" / "method" / "parse_scores.py",
    )
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class OuterVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.build_root = self.root / "build"
        self.task = self.build_root / "task"
        self.task.mkdir(parents=True)
        (self.task / "task.toml").write_text("[task]\nid = 'fixture'\n", encoding="utf-8")
        (self.task / "instruction.md").write_text("fixture instruction\n", encoding="utf-8")
        self.evidence = self.build_root / "evidence"
        self.reward_path = self.root / "logs" / "reward.json"
        self.report_path = self.root / "logs" / "gap.json"
        spec = importlib.util.spec_from_file_location("outer_verifier_parser", PARSER)
        assert spec and spec.loader
        self.parser = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.parser
        spec.loader.exec_module(self.parser)

    def tearDown(self) -> None:
        sys.modules.pop("outer_verifier_parser", None)
        self.temp.cleanup()

    @staticmethod
    def flat_details(score: float | None) -> dict[str, object]:
        reward: list[dict[str, object]] = []
        if score is not None:
            reward.append({"kind": "programmatic", "score": score, "criteria": []})
        return {"reward": reward}

    @staticmethod
    def direct_details(score: float, value: float, weight: float) -> dict[str, object]:
        return {
            "reward": {
                "kind": "programmatic",
                "score": score,
                "criteria": [{"name": "builds", "value": value, "weight": weight}],
            }
        }

    def make_arm(
        self,
        round_dir: Path,
        arm: str,
        run: str,
        score: float | None,
        digest: str,
        *,
        trials: list[tuple[float | None, str | None]] | None = None,
    ) -> Path:
        run_dir = round_dir / arm / run
        job = run_dir / "jobs" / "job-0001" / "2026-09-02__20-10-22"
        entries = trials or [(score, None)]
        write_json(
            job / "config.json",
            {
                "n_attempts": len(entries),
                "tasks": [{"path": str(self.task)}],
                "agents": [{"model_name": f"{arm}/model"}],
            },
        )
        for number, (trial_score, exception_type) in enumerate(entries, 1):
            trial = job / f"task__{number:03d}"
            write_json(
                trial / "lock.json",
                {"task": {"digest": digest}, "agent": {"model_name": f"{arm}/model"}},
            )
            write_json(
                trial / "result.json",
                {"exception_info": None if exception_type is None else {"type": exception_type}},
            )
            write_json(trial / "verifier" / "reward-details.json", self.flat_details(trial_score))
        return run_dir

    def make_readable_round(self, *, target: float, solver: float, number: int = 1) -> Path:
        round_dir = self.evidence / f"round-{number:04d}"
        digest = self.parser.harbor_task_digest(self.task)
        self.make_arm(round_dir, "target", "run-0001", target, digest)
        self.make_arm(round_dir, "solver", "run-0001", solver, digest)
        return round_dir

    def make_full_and_compact_rounds(self) -> Path:
        """Publish a compact build round from full evidence with mixed outcomes."""
        full_round = self.evidence / "round-0001"
        digest = self.parser.harbor_task_digest(self.task)
        cases = {
            "target": [(0.2, None), (0.4, "AgentTimeoutError"), (None, "AgentTimeoutError")],
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
                    "tasks": [{"path": str(self.task)}],
                    "agents": [{"model_name": f"{arm}/model"}],
                },
            )
            write_json(job / "result.json", {"exception_info": {"type": "BatchFailure"}})
            for number, (score, exception_type) in enumerate(trials, 1):
                trial = job / f"task__{number:03d}"
                write_json(
                    trial / "lock.json",
                    {"task": {"digest": digest}, "agent": {"model_name": f"{arm}/model"}},
                )
                write_json(
                    trial / "result.json",
                    {"exception_info": None if exception_type is None else {"type": exception_type}},
                )
                write_json(
                    trial / "verifier" / "reward-details.json", self.flat_details(score)
                )
                (trial / "artifacts" / "workspace").mkdir(parents=True)
                (trial / "artifacts" / "workspace" / "private.txt").write_text(
                    "not score evidence", encoding="utf-8"
                )

        compact_build = self.root / "compact-build"
        shutil.copytree(self.task, compact_build / "task")
        compact_round = compact_build / "evidence" / "round-0001"
        for arm in cases:
            compact_run = compact_round / arm / "run-0001"
            compact_run.mkdir(parents=True)
            publish_run(full_round / arm / "run-0001", compact_run, include_agent=True)
        write_round_metadata(compact_round, kind="real", source_round=None)
        return compact_build

    @staticmethod
    def normalize_trial_paths(report: dict[str, object]) -> dict[str, object]:
        """Mask only temporary trial-directory locations, not diagnostic paths."""
        normalized = deepcopy(report)
        for arm in normalized["arms"].values():
            for trials in (arm["trials"], arm["invalid_trials"]):
                for trial in trials:
                    trial["path"] = "<trial-path>"
        return normalized

    def run_verifier(self) -> subprocess.CompletedProcess[str]:
        return self.run_verifier_with_paths()

    def run_verifier_with_paths(
        self,
        *,
        parser_path: Path = PARSER,
        reward_path: Path | None = None,
        report_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        reward_path = reward_path or self.reward_path
        report_path = report_path or self.report_path
        return subprocess.run(
            [sys.executable, str(VERIFY)],
            text=True,
            capture_output=True,
            check=False,
            env=os.environ | {
                "SOP_BUILD_ROOT": str(self.build_root),
                "SOP_REWARD_PATH": str(reward_path),
                "SOP_REPORT_PATH": str(report_path),
                "SOP_PARSER_PATH": str(parser_path),
            },
        )

    def run_verifier_main(
        self,
        *,
        build_root: Path,
        reward_path: Path,
        report_path: Path,
    ) -> int:
        verifier = self.load_verify_module()
        with mock.patch.dict(
            os.environ,
            {
                "SOP_BUILD_ROOT": str(build_root),
                "SOP_REWARD_PATH": str(reward_path),
                "SOP_REPORT_PATH": str(report_path),
                "SOP_PARSER_PATH": str(PARSER),
            },
        ):
            return verifier.main()

    @staticmethod
    def load_verify_module():
        spec = importlib.util.spec_from_file_location("outer_verifier_module", VERIFY)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def reward(self) -> float:
        return json.loads(self.reward_path.read_text(encoding="utf-8"))["reward"]

    def report(self) -> dict[str, object]:
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def test_verifier_scores_raw_last_round(self) -> None:
        round_dir = self.make_readable_round(target=0.8, solver=0.9)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertAlmostEqual((0.9 - 0.8) / 0.9, self.reward())
        self.assertFalse((round_dir / "score.json").exists())

    def test_programmatic_only_reward_details_score_end_to_end(self) -> None:
        round_dir = self.make_readable_round(target=0.8, solver=0.9)
        target_details = next((round_dir / "target").rglob("reward-details.json"))
        solver_details = next((round_dir / "solver").rglob("reward-details.json"))
        write_json(target_details, self.direct_details(0.8, 0.8, 2.0))
        write_json(solver_details, self.direct_details(0.9, 0.9, 2.0))

        result = self.run_verifier()

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertAlmostEqual(1.0 - 0.8 / 0.9, self.reward())
        report = self.report()
        self.assertEqual(0.8, report["arms"]["target"]["mean"])
        self.assertEqual(0.9, report["arms"]["solver"]["mean"])
        self.assertAlmostEqual(0.9 / 0.8 - 1.0, report["R"])
        self.assertEqual(1, len(report["criteria"]))
        criterion = report["criteria"][0]
        self.assertEqual("builds", criterion["path"])
        self.assertEqual("builds", criterion["name"])
        self.assertEqual(2.0, criterion["weight"])
        self.assertEqual({"target": [2.0], "solver": [2.0]}, criterion["weights"])
        self.assertEqual(0.8, criterion["target_mean"])
        self.assertEqual(0.9, criterion["solver_mean"])
        self.assertAlmostEqual(0.1, criterion["delta"])
        self.assertEqual(0, criterion["target_missing"])
        self.assertEqual(0, criterion["solver_missing"])
        self.assertEqual([], report["agent_judges"])

    def test_compact_latest_round_writes_the_full_round_gap_and_reward(self) -> None:
        compact_build = self.make_full_and_compact_rounds()

        self.assertEqual(
            0,
            self.run_verifier_main(
                build_root=self.build_root,
                reward_path=self.reward_path,
                report_path=self.report_path,
            ),
        )
        full_reward = self.reward()
        full_gap = self.report()

        compact_reward_path = self.root / "compact-logs" / "reward.json"
        compact_report_path = self.root / "compact-logs" / "gap.json"
        self.assertEqual(
            0,
            self.run_verifier_main(
                build_root=compact_build,
                reward_path=compact_reward_path,
                report_path=compact_report_path,
            ),
        )
        compact_reward = json.loads(compact_reward_path.read_text(encoding="utf-8"))["reward"]
        compact_gap = json.loads(compact_report_path.read_text(encoding="utf-8"))

        self.assertFalse(any((compact_build / "evidence").rglob("artifacts/workspace")))
        self.assertEqual(full_reward, compact_reward)
        self.assertEqual(
            [criterion["path"] for criterion in full_gap["criteria"]],
            [criterion["path"] for criterion in compact_gap["criteria"]],
        )
        self.assertEqual(
            self.normalize_trial_paths(full_gap), self.normalize_trial_paths(compact_gap)
        )

    def test_incomplete_greatest_round_never_falls_back(self) -> None:
        self.make_readable_round(target=0.2, solver=0.9)
        greatest = self.evidence / "round-0002"
        digest = self.parser.harbor_task_digest(self.task)
        self.make_arm(greatest, "target", "run-0001", 0.2, digest)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0.0, self.reward())
        self.assertEqual("round-0002", self.report()["round"])
        self.assertTrue(self.report()["faults"])

    def test_final_task_digest_mismatch_is_a_no_reading_fault(self) -> None:
        self.make_readable_round(target=0.8, solver=0.9)
        (self.task / "instruction.md").write_text("changed after evidence\n", encoding="utf-8")
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0.0, self.reward())
        self.assertIn("final task digest", "\n".join(self.report()["faults"]))

    def test_each_arm_requires_a_readable_latest_run(self) -> None:
        round_dir = self.make_readable_round(target=0.8, solver=0.9)
        digest = self.parser.harbor_task_digest(self.task)
        self.make_arm(round_dir, "target", "run-0002", None, digest)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0.0, self.reward())
        self.assertIn("included resolved model", "\n".join(self.report()["faults"]))

    def test_mixed_latest_run_keeps_valid_trials_and_reports_excluded_ones(self) -> None:
        round_dir = self.evidence / "round-0001"
        digest = self.parser.harbor_task_digest(self.task)
        self.make_arm(
            round_dir,
            "target",
            "run-0001",
            0.8,
            digest,
            trials=[(0.8, None), (0.3, "UnknownApiError")],
        )
        self.make_arm(round_dir, "solver", "run-0001", 0.9, digest)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertAlmostEqual(1.0 - 0.8 / 0.9, self.reward())
        target = self.report()["arms"]["target"]
        self.assertEqual(1, target["valid"])
        self.assertEqual(1, target["invalid"])
        self.assertEqual("provider_error", target["invalid_trials"][0]["state"])
        self.assertEqual(0.3, target["invalid_trials"][0]["programmatic_score"])

    def test_zero_included_arm_is_a_no_reading_fault(self) -> None:
        round_dir = self.evidence / "round-0001"
        digest = self.parser.harbor_task_digest(self.task)
        self.make_arm(round_dir, "target", "run-0001", None, digest)
        self.make_arm(round_dir, "solver", "run-0001", 0.9, digest)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0.0, self.reward())
        self.assertIn("included resolved model", "\n".join(self.report()["faults"]))

    def test_configured_and_resolved_models_must_match(self) -> None:
        round_dir = self.make_readable_round(target=0.8, solver=0.9)
        config = next((round_dir / "target").rglob("config.json"))
        content = json.loads(config.read_text(encoding="utf-8"))
        content["agents"][0]["model_name"] = "wrong/model"
        write_json(config, content)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0.0, self.reward())
        self.assertIn("does not match included resolved model", "\n".join(self.report()["faults"]))

    def test_R_point_one_keeps_positive_reward_but_not_target_flag(self) -> None:
        self.make_readable_round(target=0.8, solver=0.88)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertAlmostEqual(1.0 - 0.8 / 0.88, self.reward())
        self.assertFalse(self.report()["clears_target_R"])

    def test_R_above_point_two_sets_flag_without_changing_formula(self) -> None:
        self.make_readable_round(target=0.8, solver=1.0)
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertAlmostEqual(1.0 - 0.8 / 1.0, self.reward())
        self.assertTrue(self.report()["clears_target_R"])

    def test_missing_evidence_root_writes_zero_and_fault(self) -> None:
        result = self.run_verifier()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0.0, self.reward())
        self.assertIn("no numbered", "\n".join(self.report()["faults"]))

    def test_import_failing_parser_crashes_without_normal_fault_report(self) -> None:
        parser = self.root / "import_fails.py"
        parser.write_text("raise ImportError('fixture import failure')\n", encoding="utf-8")
        write_json(self.reward_path, {"reward": 0.0})
        result = self.run_verifier_with_paths(parser_path=parser)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(0.0, self.reward())
        self.assertFalse(self.report_path.exists())

    def test_crashing_parser_crashes_without_normal_fault_report(self) -> None:
        parser = self.root / "crashes.py"
        parser.write_text("raise RuntimeError('fixture parser bug')\n", encoding="utf-8")
        write_json(self.reward_path, {"reward": 0.0})
        result = self.run_verifier_with_paths(parser_path=parser)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(0.0, self.reward())
        self.assertFalse(self.report_path.exists())

    def test_load_parser_restores_module_registry_after_success(self) -> None:
        verifier = self.load_verify_module()
        parser = self.root / "success.py"
        parser.write_text("answer = 42\n", encoding="utf-8")
        sentinel = types.ModuleType("sop_parse_scores")
        previous = sys.modules.get("sop_parse_scores")
        sys.modules["sop_parse_scores"] = sentinel
        try:
            loaded = verifier.load_parser(parser)
            self.assertEqual(42, loaded.answer)
            self.assertIs(sentinel, sys.modules["sop_parse_scores"])
        finally:
            if previous is None:
                sys.modules.pop("sop_parse_scores", None)
            else:
                sys.modules["sop_parse_scores"] = previous

    def test_load_parser_restores_module_registry_after_failure(self) -> None:
        verifier = self.load_verify_module()
        parser = self.root / "failure.py"
        parser.write_text("raise RuntimeError('fixture parser bug')\n", encoding="utf-8")
        sentinel = types.ModuleType("sop_parse_scores")
        previous = sys.modules.get("sop_parse_scores")
        sys.modules["sop_parse_scores"] = sentinel
        try:
            with self.assertRaisesRegex(RuntimeError, "fixture parser bug"):
                verifier.load_parser(parser)
            self.assertIs(sentinel, sys.modules["sop_parse_scores"])
        finally:
            if previous is None:
                sys.modules.pop("sop_parse_scores", None)
            else:
                sys.modules["sop_parse_scores"] = previous

    def test_gap_write_failure_does_not_replace_prewritten_zero_reward(self) -> None:
        self.make_readable_round(target=0.8, solver=1.0)
        write_json(self.reward_path, {"reward": 0.0})
        blocked_report = self.root / "blocked-gap.json"
        blocked_report.mkdir()
        result = self.run_verifier_with_paths(report_path=blocked_report)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(0.0, self.reward())


if __name__ == "__main__":
    unittest.main()
