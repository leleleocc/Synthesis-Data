from pathlib import Path
import os
import tomllib
import unittest

ROOT = (
    Path(__file__).resolve().parents[1]
    / "template/environment/method/reference/minimal-harbor-task"
)


class ReferenceTaskTests(unittest.TestCase):
    def test_reference_is_regrade_ready(self):
        task = tomllib.loads((ROOT / "task.toml").read_text(encoding="utf-8"))
        self.assertNotIn("steps", task)
        self.assertEqual("separate", task["verifier"]["environment_mode"])
        self.assertEqual([{"source": "/workspace"}], task["artifacts"])
        self.assertEqual("public", task["environment"]["network_mode"])
        verifier_environment = task["verifier"].get("environment", task["environment"])
        self.assertEqual("public", verifier_environment["network_mode"])

    def test_reference_has_one_complete_harbor_tree(self):
        required = {
            "task.toml", "instruction.md", "environment/Dockerfile",
            "environment/workspace/README.md", "solution/solve.sh",
            "tests/Dockerfile", "tests/test.sh", "tests/checks.py", "tests/judge.toml",
        }
        actual = {str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file()}
        self.assertEqual(required, actual)

    def test_reference_preserves_measured_fixed_mechanics(self):
        task = tomllib.loads((ROOT / "task.toml").read_text())
        self.assertEqual("public", task["environment"]["network_mode"])
        self.assertEqual(3600.0, task["agent"]["timeout_sec"])
        self.assertEqual("${HARBOR_JUDGE_BASE_URL}", task["verifier"]["env"]["ANTHROPIC_BASE_URL"])
        self.assertEqual("${HARBOR_JUDGE_AUTH_TOKEN}", task["verifier"]["env"]["ANTHROPIC_AUTH_TOKEN"])
        self.assertIn("rewardkit /tests --workspace /workspace", (ROOT / "tests/test.sh").read_text())
        checks = (ROOT / "tests/checks.py").read_text()
        self.assertIn("@criterion(shared=True)", checks)
        self.assertIn("rk.answer_is_ready(weight=1)", checks)
        judge = (ROOT / "tests/judge.toml").read_text()
        self.assertIn('judge = "claude-code"', judge)
        self.assertIn('mode = "batched"', judge)
        self.assertTrue(os.access(ROOT / "solution/solve.sh", os.X_OK))
        self.assertTrue(os.access(ROOT / "tests/test.sh", os.X_OK))
        fixed = sum(path.read_text().count("FIXED:") for path in ROOT.rglob("*") if path.is_file())
        self.assertGreaterEqual(fixed, 8)

    def test_reference_verifier_image_uses_the_proven_rewardkit_cli_installation(self):
        dockerfile = (ROOT / "tests/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("apt-get install -y --no-install-recommends curl ca-certificates", dockerfile)
        self.assertIn("UV_INSTALL_DIR=/usr/local/bin", dockerfile)
        self.assertIn("uv tool install --python 3.12 'harbor-rewardkit==0.2.*'", dockerfile)
        self.assertIn("ln -sf /root/.local/bin/rewardkit /usr/local/bin/rewardkit", dockerfile)
        self.assertIn("rewardkit --help > /dev/null", dockerfile)

    def test_solution_and_programmatic_check_share_the_same_exact_contract(self):
        solve = (ROOT / "solution/solve.sh").read_text()
        checks = (ROOT / "tests/checks.py").read_text()
        self.assertIn("printf '%s\\n' ready > /workspace/answer.txt", solve)
        self.assertIn('path.read_text(encoding="utf-8") == "ready\\n"', checks)
