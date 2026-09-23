#!/usr/bin/env python3
"""Check factory credentials with Compose itself, without a daemon or real keys."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="simula-compose-env-") as raw:
        root = Path(raw)
        environment = root / "copied-factory/environment"
        environment.mkdir(parents=True)
        for name in ("docker-compose.yaml", "host.env"):
            shutil.copy2(ROOT / "environment" / name, environment / name)
        override = root / "override.json"
        override.write_text(json.dumps({"services": {"main": {"image": "unused:local"}}}))
        env = dict(os.environ)
        for key in tuple(env):
            if key.startswith("COMPOSE_") or key == "DAYTONA_API_KEY":
                env.pop(key)
        command = [
            "docker", "compose", "--project-directory", str(environment),
            "-f", str(environment / "docker-compose.yaml"), "-f", str(override),
            "config", "--format", "json",
        ]
        cases = (
            (None, None, ""),
            (None, "host-test-key", "host-test-key"),
            ("file-test-key", None, "file-test-key"),
            ("file-test-key", "host-test-key", "file-test-key"),
        )
        for file_key, host_key, expected in cases:
            dotenv = environment.parent / ".env"
            if file_key is None:
                dotenv.unlink(missing_ok=True)
            else:
                dotenv.write_text(f"DAYTONA_API_KEY={file_key}\n")
            if host_key is None:
                env.pop("DAYTONA_API_KEY", None)
            else:
                env["DAYTONA_API_KEY"] = host_key
            # Harbor uses environment/; also exercise an unrelated launch cwd.
            for cwd in (environment, root):
                result = subprocess.run(
                    command, cwd=cwd, env=env, capture_output=True, text=True,
                    check=True, timeout=30,
                )
                services = json.loads(result.stdout)["services"]
                assert services["main"]["environment"]["DAYTONA_API_KEY"] == expected
                assert "DAYTONA_API_KEY" not in services["docker"]["environment"]
        print("Compose env loading passed: task file, host fallback, precedence, no credentials")


if __name__ == "__main__":
    main()
