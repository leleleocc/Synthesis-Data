#!/usr/bin/env python3
"""Local Docker smoke test: factory -> DinD -> Compose build/binds -> Harbor nop."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
TASK_CONFIG = '''schema_version = "1.4"
[task]
name = "simula/runtime-probe"
version = "1.0.0"
description = "Exercise factory filesystem and native verifier paths."
[metadata]
difficulty = "easy"
category = "software-engineering"
[environment]
build_timeout_sec = 240
cpus = 1
memory_mb = 256
storage_mb = 1024
gpus = 0
[agent]
timeout_sec = 30
[verifier]
timeout_sec = 30
'''
VERIFIER = '''#!/bin/bash
set -euo pipefail
cmp /image-marker /mounted/marker
printf 'checked\\n' > /probe-results/verifier
if [ -f /completed ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
'''


def fixture(root: Path, multiple: bool, separate: bool = False) -> None:
    environment = root / "environment"
    (environment / "mounted").mkdir(parents=True)
    (environment / "mounted/marker").write_text("shared-build-and-runtime\n")
    (environment / "marker").write_text("shared-build-and-runtime\n")
    (environment / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY marker /image-marker\nWORKDIR /app\n"
    )
    (environment / "docker-compose.yaml").write_text(json.dumps({
        "services": {"main": {
            "build": {"context": ".", "dockerfile": "Dockerfile"},
            "command": ["sleep", "infinity"],
            "volumes": ["./mounted:/mounted:ro", "/synthesis/runtime-probe/results:/probe-results"],
        }},
    }))
    (root / "instruction.md").write_text("Create /completed.\n")
    config = TASK_CONFIG
    (root / "tests").mkdir()
    (root / "tests/test.sh").write_text(VERIFIER)
    (root / "tests/test.sh").chmod(0o755)
    if multiple:
        for name in ("prepare", "verify"):
            config += f'\n[[steps]]\nname = "{name}"\nmin_reward = 0.0\n'
            step = root / "steps" / name
            step.mkdir(parents=True)
            (step / "instruction.md").write_text("Create /completed.\n")
        # One native override and one shared fallback exercise both Harbor paths.
        local = root / "steps/verify/tests"
        local.mkdir()
        (local / "test.sh").write_text(VERIFIER)
        (local / "test.sh").chmod(0o755)
    if separate:
        config = config.replace("[verifier]\n", '[verifier]\nenvironment_mode = "separate"\n')
        for tests, marker in ((root / "tests", "shared"), (root / "steps/verify/tests", "local")):
            (tests / "Dockerfile").write_text("FROM python:3.12-slim\nCOPY . /tests\n")
            (tests / "context").write_text(marker + "\n")
            (tests / "test.sh").write_text(
                f"#!/bin/bash\nset -eu\ngrep -qx {marker} /tests/context\n"
                f"echo 'context: {marker}'\necho 0 > /logs/verifier/reward.txt\n"
            )
    (root / "task.toml").write_text(config)


PROBE = '''import json
from pathlib import Path
import subprocess

root = Path("/synthesis/runtime-probe")
(root / "results").mkdir(exist_ok=True)
compose = ["docker", "compose", "-p", "simula-bind-probe", "-f", str(root / "single/environment/docker-compose.yaml")]
def run(args):
    subprocess.run(args, check=True, timeout=360)
try:
    run(compose + ["build"])
    run(compose + ["up", "-d"])
    run(compose + ["exec", "-T", "main", "sh", "-c",
        "cmp /image-marker /mounted/marker && echo daemon-write > /probe-results/from-container"])
    assert (root / "results/from-container").read_text().strip() == "daemon-write"
    (root / "single/environment/mounted/marker").write_text("factory-write\\n")
    run(compose + ["exec", "-T", "main", "sh", "-c", "test $(cat /mounted/marker) = factory-write"])
    (root / "single/environment/mounted/marker").write_text("shared-build-and-runtime\\n")
finally:
    run(compose + ["down", "--volumes"])
for name in ("single", "multiple", "separate"):
    jobs = root / (name + "-jobs")
    run(["harbor", "run", "-a", "nop", "-e", "docker", "-p", str(root / name),
         "--jobs-dir", str(jobs), "--job-name", name])
    trials = list(jobs.glob("*/*/result.json"))
    assert len(trials) == 1, trials
    result = json.loads(trials[0].read_text())
    assert result.get("exception_info") is None, result.get("exception_info")
    assert result["verifier_result"]["rewards"]["reward"] == 0, result
    if name != "single":
        steps = result["step_results"]
        assert len(steps) == 2, steps
        assert all(s.get("exception_info") is None and s["verifier_result"]["rewards"]["reward"] == 0 for s in steps), steps
    if name == "separate":
        for step, marker in (("prepare", "shared"), ("verify", "local")):
            output = trials[0].parent / "steps" / step / "verifier/test-stdout.txt"
            assert "context: " + marker in output.read_text(), output
    else:
        assert (root / "results/verifier").read_text().strip() == "checked"
print("Compose build, bidirectional binds, and single/multi-step inline/separate nop passed")
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Locally built Simula factory image")
    args = parser.parse_args()
    project = "simula-check-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=project) as raw:
        temp = Path(raw)
        environment = temp / "environment"
        environment.mkdir()
        for name in ("docker-compose.yaml", "host.env"):
            shutil.copy2(ROOT / "environment" / name, environment / name)
        override = temp / "override.json"
        override.write_text(json.dumps({"services": {"main": {
            "image": args.image, "command": ["sleep", "infinity"],
            "environment": {"DAYTONA_API_KEY": ""},
        }}}))
        compose = ["docker", "compose", "-p", project,
                   "-f", str(environment / "docker-compose.yaml"), "-f", str(override)]
        env = dict(os.environ, DAYTONA_API_KEY="")
        def run(command: list[str], timeout: int = 360) -> None:
            subprocess.run(command, check=True, timeout=timeout, env=env)
        probe = temp / "runtime-probe"
        fixture(probe / "single", False)
        fixture(probe / "multiple", True)
        fixture(probe / "separate", True, separate=True)
        (probe / "probe.py").write_text(PROBE)
        try:
            run(compose + ["up", "-d", "--wait", "--wait-timeout", "120"])
            run(compose + ["cp", str(probe), "main:/synthesis/runtime-probe"])
            run(compose + ["exec", "-T", "-w", "/tmp", "main", "python",
                           "/synthesis/runtime-probe/probe.py"], timeout=900)
        finally:
            run(compose + ["down", "--volumes", "--remove-orphans"], timeout=120)


if __name__ == "__main__":
    main()
