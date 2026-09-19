"""Static contract checks for the thin outer-task scaffold."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


class TemplateShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = Path(__file__).resolve().parents[1] / "template"

    def test_fake_lab_and_oracle_files_are_absent(self) -> None:
        forbidden = [
            self.template / "environment/lab",
            self.template / "tests/lab",
            self.template / "sync-lab.sh",
            self.template / "environment/method/local-arms.md",
            self.template / "environment/method/selfcheck.py",
            self.template / "solution/build_tree.py",
            self.template / "solution/solve.sh",
            self.template / "environment/seed/STATE.md",
            self.template / "environment/seed/task",
        ]
        self.assertEqual([], [str(path) for path in forbidden if path.exists()])

    def test_method_surface_has_exactly_four_entries(self) -> None:
        method = self.template / "environment/method"
        self.assertEqual(
            ["parse_scores.py", "reference", "run-two-models.sh", "sop.md"],
            sorted(
                path.name
                for path in method.iterdir()
                if path.name not in {"__pycache__", "internal"}
            ),
        )
        self.assertEqual(
            ["evidence_retention.py"],
            sorted(path.name for path in (method / "internal").iterdir()),
        )

    def test_production_verifier_bundle_excludes_development_test_modules(self) -> None:
        verifier = self.template / "tests"
        self.assertEqual([], sorted(path.name for path in verifier.glob("test_*.py")))

    def test_seed_is_a_round_trip_build_capsule(self) -> None:
        seed = self.template / "environment/seed"
        build = seed / "build"
        self.assertTrue((build / "task").is_dir())
        self.assertFalse((seed / "task").exists())

        resume = build / "evidence/resume.md"
        self.assertTrue(resume.is_file())
        headings = [
            line
            for line in resume.read_text(encoding="utf-8").splitlines()
            if line.startswith("# ")
        ]
        self.assertEqual(
            ["# 已尝试方向", "# 关键结果", "# 已排除假设", "# 当前 task 状态", "# 下一步建议"],
            headings,
        )

    def test_sop_is_six_checkable_steps_with_tool_owned_mechanics(self) -> None:
        text = (self.template / "environment/method/sop.md").read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        self.assertEqual(6, text.count("完成标准："))
        self.assertIn("/app/method/run-two-models.sh --help", text)
        self.assertIn("/app/method/parse_scores.py --help", text)
        self.assertIn("nop", text)
        self.assertIn("oracle", text)
        self.assertIn("R > 0.2", text)
        for required in (
            "先读 `/app/build/evidence/resume.md`",
            "已有历史",
            "最后一个 round 不完整",
            "task 未变化",
            "新开 round",
            "target_mean < 0.7",
            "最大 weight / 最小 weight <= 10",
        ):
            self.assertIn(required, text)
        for required in (
            "新 life 的第一次正式测量必须 fresh",
            "regrade 只复用当前 life",
            "/app/runtime/harbor-evidence",
            "compact evidence",
            "/app/build/evidence/previous-life/index.md",
            "分数或 verifier 假设",
            "模型行为假设",
            "当前 life 的 fresh 证据优先",
            "当前 life 跟随 parser/current round 路径",
            "previous-life attribution 才按 `/app/build/evidence/previous-life/index.md`",
        ):
            self.assertIn(required, text)
        for obsolete in (
            "最新 real rollout 的两臂可复用 workspace",
            "不要删除或改写历史证据",
        ):
            self.assertNotIn(obsolete, text)
        for required in (
            "/app/build/task/task.toml",
            '[verifier].environment_mode = "separate"',
            '[[artifacts]] source = "/workspace"',
            "run-two-models.sh regrade",
            "不会自动回退到模型运行",
            "current-life real source",
            "`tests/` 是 verifier 的构建上下文",
            "`/tests/test.sh`",
        ):
            self.assertIn(required, normalized)
        for duplicated_detail in (
            "run.json",
            "score.json",
            "--max-retries",
            "HARBOR_TARGET_",
            "HARBOR_SOLVER_",
            "DAYTONA_API_KEY",
            "AgentTimeoutError",
            "observables.tsv",
            "selfcheck.py",
        ):
            self.assertNotIn(duplicated_detail, text)

    def test_dockerfile_installs_pinned_runtime_and_copies_only_injection(self) -> None:
        text = (self.template / "environment/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("FROM python:3.12-slim", text)
        self.assertIn("'harbor[daytona]==0.21.0'", text)
        self.assertIn("'harbor-rewardkit==0.2.*'", text)
        self.assertIn("      gzip \\", text)
        self.assertIn("      tar \\", text)
        self.assertIn("COPY method/ /app/method/", text)
        self.assertIn("COPY unpack-seed.sh /tmp/unpack-seed.sh", text)
        self.assertIn("COPY seed/ /tmp/seed/", text)
        self.assertIn("RUN /bin/sh /tmp/unpack-seed.sh", text)
        self.assertNotIn("COPY seed/build/ /app/build/", text)
        self.assertNotIn("COPY seed/task/", text)
        self.assertNotIn("RUN mkdir -p /app/build/evidence", text)
        self.assertIn("WORKDIR /app/build", text)
        self.assertNotIn("COPY lab/", text)
        self.assertNotIn("COPY seed/ /app/seed/", text)

    def test_task_configuration_forwards_all_nested_run_bundles(self) -> None:
        with (self.template / "task.toml").open("rb") as handle:
            task = tomllib.load(handle)
        names = [
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
        ]
        self.assertEqual(
            {name: "${" + name + "}" for name in names},
            task["environment"]["env"],
        )
        self.assertNotIn("env", task["agent"])

    def test_task_configuration_keeps_runtime_policy_and_one_artifact(self) -> None:
        with (self.template / "task.toml").open("rb") as handle:
            task = tomllib.load(handle)
        self.assertEqual(
            "harbor-task-constructor/construct-model-separating-task",
            task["task"]["name"],
        )
        self.assertEqual(28800.0, task["agent"]["timeout_sec"])
        self.assertEqual(600.0, task["verifier"]["timeout_sec"])
        self.assertEqual(900.0, task["environment"]["build_timeout_sec"])
        self.assertEqual(2, task["environment"]["cpus"])
        self.assertEqual(4096, task["environment"]["memory_mb"])
        self.assertEqual(10240, task["environment"]["storage_mb"])
        self.assertEqual("public", task["environment"]["network_mode"])
        self.assertEqual(
            [{"source": "/app/build", "destination": "build"}],
            task["artifacts"],
        )


if __name__ == "__main__":
    unittest.main()
