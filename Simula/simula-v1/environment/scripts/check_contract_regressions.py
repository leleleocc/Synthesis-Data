#!/usr/bin/env python3
"""Small offline regressions for the phase contract gates."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_contract import (  # noqa: E402
    ADVISORY_REVIEW_CRITERIA,
    DEPLOYMENT_DEFAULTS,
    HARBOR_RESOURCE_LIMITS,
    _check_slot_task_preview,
    _complexity_delta_errors,
    _instruction_recipe_errors,
    _instruction_tb_quality_errors,
    _profile_deployment_support_errors,
    _review_check_names,
    _task_verifier_dirs,
    _verifier_fail_logs_errors,
    _verifier_fixture_errors,
    _verifier_form_diversity_errors,
    _verifier_runtime_errors,
    check_design,
    check_simula_plan,
    check_package,
    check_verifiers,
    check_verifier_review,
    validate_spec,
)


def _check_comment_filter() -> None:
    with tempfile.TemporaryDirectory() as raw:
        tests = Path(raw)
        shell = tests / "test.sh"
        shell.write_text(
            "#!/usr/bin/env bash\n"
            "# apt-get install -y fake-package\n"
            "echo 1 > /logs/verifier/reward.txt\n",
            encoding="utf-8",
        )
        assert not _verifier_runtime_errors("c1", tests)
        shell.write_text(
            "#!/usr/bin/env bash\n"
            "apt-get install -y fake-package\n"
            "pip install fake-package\n"
            "echo 1 > /logs/verifier/reward.txt\n",
            encoding="utf-8",
        )
        errors = _verifier_runtime_errors("c1", tests)
        assert any("must not install" in item for item in errors)


def _write_review_fixture(root: Path) -> tuple[dict, dict]:
    package = root / "alpha" / "tests"
    package.mkdir(parents=True)
    (package / "test.sh").write_text(
        "#!/usr/bin/env bash\necho 1 > /logs/verifier/reward.txt\n",
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(
        json.dumps({"generated_tasks": [{"candidate_id": "c1", "path": "alpha"}]}),
        encoding="utf-8",
    )
    state = {"verifiers": [{"candidate_id": "c1"}]}
    review = {
        "reviews": [{
            "candidate_id": "c1",
            "package_slug": "alpha",
            "syntax_ok": True,
            "harbor_shape_ok": True,
            "static_checks_ok": True,
            "rubric_ok": True,
            "calibration_executed": True,
            "calibration_evidence": {"positive": ["valid"], "negative": ["missing output"]},
            "status": "publish",
            "checks": {
                "too_loose": {"outcome": "pass", "explanation": "ok"},
                "too_strict": {"outcome": "pass", "explanation": "ok"},
                "deterministic": {"outcome": "pass", "explanation": "ok"},
            },
            "review_reports": {
                role: [
                    {
                        "name": name,
                        "outcome": "pass",
                        "path": "tests/test.sh",
                        "reason": "fixture assessment",
                        **({"advisory": True} if name in ADVISORY_REVIEW_CRITERIA else {}),
                    }
                    for name in sorted(names)
                ]
                for role, names in _review_check_names().items()
            },
            "issues": [],
        }],
        "release_candidate_ids": ["c1"],
    }
    return state, review


def _check_review_mapping() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        state, review = _write_review_fixture(root)
        assert check_verifier_review(state, review, root) == []
        review["reviews"][0]["package_slug"] = "wrong"
        assert any("package_slug" in error for error in check_verifier_review(state, review, root))
        review["reviews"][0]["package_slug"] = "alpha"
        review["reviews"][0]["static_checks_ok"] = False
        assert any("static_checks_ok" in error for error in check_verifier_review(state, review, root))
        review["reviews"][0]["static_checks_ok"] = True
        (root / "release_manifest.json").write_text("{}", encoding="utf-8")
        assert any(
            "release_manifest" in error
            for error in check_verifier_review(state, review, root)
        )


def _check_review_reports() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        state, review = _write_review_fixture(root)
        record = review["reviews"][0]
        for result in record["review_reports"]["implementation"]:
            if result["name"] in ADVISORY_REVIEW_CRITERIA:
                result["outcome"] = "fail"
                result["reason"] = "The task is easier than the planned band."
        assert check_verifier_review(state, review, root) == []

        missing_reports = copy.deepcopy(review)
        del missing_reports["reviews"][0]["review_reports"]
        assert any("review_reports" in e for e in check_verifier_review(state, missing_reports, root))

        for role in ("static", "implementation"):
            empty = copy.deepcopy(review)
            empty["reviews"][0]["review_reports"][role] = []
            assert any("non-empty list" in e for e in check_verifier_review(state, empty, root))

            omitted = copy.deepcopy(review)
            omitted["reviews"][0]["review_reports"][role].pop()
            assert any("missing checks" in e for e in check_verifier_review(state, omitted, root))

            duplicated = copy.deepcopy(review)
            entries = duplicated["reviews"][0]["review_reports"][role]
            entries.append(copy.deepcopy(entries[0]))
            assert any("duplicate check" in e for e in check_verifier_review(state, duplicated, root))

        static_failure = copy.deepcopy(review)
        result = static_failure["reviews"][0]["review_reports"]["static"][0]
        result["outcome"] = "fail"
        result["advisory"] = True
        errors = check_verifier_review(state, static_failure, root)
        assert any("static_checks_ok must be false" in e for e in errors)
        assert any("advisory=false" in e for e in errors)

        blocking = copy.deepcopy(review)
        result = next(
            entry for entry in blocking["reviews"][0]["review_reports"]["implementation"]
            if entry["name"] == "test_instruction_alignment"
        )
        result["outcome"] = "fail"
        result["reason"] = "A valid output is rejected by an unstated requirement."
        assert any("rubric_ok must be false" in e for e in check_verifier_review(state, blocking, root))
        result["advisory"] = True
        errors = check_verifier_review(state, blocking, root)
        assert any("advisory=false" in e for e in errors)
        assert any("rubric_ok must be false" in e for e in errors)


def _spec(**target_extra: object) -> dict:
    target = {
        "languages": ["c"],
        "domains": ["software"],
        "subdomains": ["systems"],
        "tags": ["cli", "redis"],
        "difficulty": "hard",
        "oracle_types": ["result", "state", "behavior"],
    }
    target.update(target_extra)
    return {
        "source_repo": {"url": "https://github.com/redis/redis", "commit": "a" * 40},
        "target": target,
        "generation": {"allow_external_assets": False, "max_candidates": 3, "min_repo_score": 0.2},
    }


def _dims(**extra: object) -> dict:
    dims = dict(DEPLOYMENT_DEFAULTS)
    dims.update(extra)
    return dims


def _delta(text: str) -> list[dict]:
    """A hard/ultra delta: the coupling the fixture describes, plus two more axes."""
    return [
        {"axis": "coupling", "text": text},
        {"axis": "cyclic-dependency", "text": "a minimal local fix of one leaves the other broken"},
        {"axis": "false-shortcut", "text": "restarting looks healthy and fails the joint check"},
    ]


def _slot(sid: str, gid: str, **extra: object) -> dict:
    slot = {
        "id": sid,
        "global_id": gid,
        "mechanism": "recover-state",
        "scenario_angle": "incident-cleanup",
        "output_shape": "service-state",
        "primary_entrypoint": "redis-server",
        "primary_input": None,
        "complexified": True,
        "complexity_delta": _delta("couple replica offset with AOF rewrite"),
        "deployment_dimensions": _dims(),
    }
    slot.update(extra)
    raw_delta = slot.get("complexity_delta")
    if isinstance(raw_delta, str) and raw_delta.strip():
        slot["complexity_delta"] = _delta(raw_delta)
    return slot


def _check_mechanisms() -> None:
    spec = _spec()
    assert validate_spec(spec) == []
    env = {"entrypoints": ["redis-server", "redis-cli"]}
    global_row = {
        "id": "g1",
        "tags": ["cli", "redis"],
        "domains": ["software"],
        "subdomains": ["systems"],
        "languages": ["c"],
        "oracle_types": ["result", "state", "behavior"],
        "primary_entrypoint": "redis-server",
    }
    collapsed = {
        "difficulty": "hard",
        "global": [global_row],
        "slots": [
            _slot("c1", "g1", mechanism="plant-fault", scenario_angle="audit", output_shape="report-json"),
            _slot("c2", "g1", mechanism="plant-fault", scenario_angle="repair", output_shape="service-state", primary_entrypoint="redis-cli"),
            _slot("c3", "g1", mechanism="plant-fault", scenario_angle="failover", output_shape="replica-state", primary_input="/data/a"),
        ],
    }
    errors = check_simula_plan(spec, collapsed, env_state=env)
    assert any("distinct mechanisms" in item for item in errors)
    diverse = {
        "difficulty": "hard",
        "global": [global_row],
        "slots": [
            _slot(
                "c1",
                "g1",
                mechanism="plant-fault",
                scenario_angle="audit",
                output_shape="report-json",
                complexity_delta="couple checksum mismatch with replica lag",
            ),
            _slot(
                "c2",
                "g1",
                mechanism="recover-state",
                scenario_angle="incident-cleanup",
                output_shape="service-state",
                primary_entrypoint="redis-cli",
                complexity_delta="couple RDB load with expired key eviction",
            ),
            _slot(
                "c3",
                "g1",
                mechanism="configure-runtime",
                scenario_angle="failover",
                output_shape="replica-state",
                primary_input="/data/a",
                complexity_delta="couple replica offset with AOF rewrite",
            ),
        ],
    }
    assert check_simula_plan(spec, diverse, env_state=env) == []
    easy = {
        "difficulty": "hard",
        "global": [global_row],
        "slots": [
            _slot(
                "c1",
                "g1",
                mechanism="plant-fault",
                scenario_angle="audit",
                output_shape="report-json",
                complexity_delta="couple checksum mismatch with replica lag",
            ),
            _slot(
                "c2",
                "g1",
                mechanism="recover-state",
                scenario_angle="incident-cleanup",
                output_shape="service-state",
                primary_entrypoint="redis-cli",
                complexity_delta="couple RDB load with expired key eviction",
            ),
            _slot(
                "c3",
                "g1",
                mechanism="configure-runtime",
                scenario_angle="failover",
                output_shape="replica-state",
                primary_input="/data/a",
                complexified=False,
                complexity_delta="",
            ),
        ],
    }
    errors = check_simula_plan(spec, easy, env_state=env)
    assert any("complexified must be true" in item for item in errors)


def _check_deployment_gates() -> None:
    spec = _spec(deployment_dimensions={"container_mode": ["single", "multiple"]})
    assert validate_spec(spec) == []
    missing = _profile_deployment_support_errors(spec, {"hard_checks": {"deployment_support": True}})
    assert any("deployment_support" in item for item in missing)
    covered = _profile_deployment_support_errors(
        spec,
        {
            "hard_checks": {"deployment_support": True},
            "deployment_support": {
                "container_mode": {
                    "values": ["single", "multiple"],
                    "evidence": ["docker-compose.yml", "src/server.c"],
                }
            },
        },
    )
    assert covered == []
    unconstrained = _profile_deployment_support_errors(
        _spec(),
        {"hard_checks": {"deployment_support": True}, "deployment_support": {}},
    )
    assert unconstrained == []
    env = {"entrypoints": ["redis-server", "redis-cli"]}
    global_row = {
        "id": "g1",
        "tags": ["cli", "redis"],
        "domains": ["software"],
        "subdomains": ["systems"],
        "languages": ["c"],
        "oracle_types": ["result", "state", "behavior"],
        "primary_entrypoint": "redis-server",
    }
    collapsed = {
        "difficulty": "hard",
        "global": [global_row],
        "slots": [
            _slot(
                "c1",
                "g1",
                mechanism="plant-fault",
                scenario_angle="audit",
                output_shape="report-json",
                complexity_delta="couple checksum mismatch with replica lag",
                deployment_dimensions=_dims(container_mode="single"),
            ),
            _slot(
                "c2",
                "g1",
                mechanism="recover-state",
                scenario_angle="incident-cleanup",
                output_shape="service-state",
                primary_entrypoint="redis-cli",
                complexity_delta="couple RDB load with expired key eviction",
                deployment_dimensions=_dims(container_mode="single"),
            ),
            _slot(
                "c3",
                "g1",
                mechanism="configure-runtime",
                scenario_angle="failover",
                output_shape="replica-state",
                primary_input="/data/a",
                complexity_delta="couple replica offset with AOF rewrite",
                deployment_dimensions=_dims(container_mode="single"),
            ),
        ],
    }
    errors = check_simula_plan(spec, collapsed, env_state=env)
    assert any("container_mode" in item for item in errors)
    incomplete = {
        "difficulty": "hard",
        "global": [global_row],
        "slots": [
            _slot(
                "c1",
                "g1",
                mechanism="plant-fault",
                scenario_angle="audit",
                output_shape="report-json",
                complexity_delta="couple checksum mismatch with replica lag",
                deployment_dimensions={"container_mode": "single"},
            ),
            _slot(
                "c2",
                "g1",
                mechanism="recover-state",
                scenario_angle="incident-cleanup",
                output_shape="service-state",
                primary_entrypoint="redis-cli",
                complexity_delta="couple RDB load with expired key eviction",
                deployment_dimensions=_dims(container_mode="multiple"),
            ),
            _slot(
                "c3",
                "g1",
                mechanism="configure-runtime",
                scenario_angle="failover",
                output_shape="replica-state",
                primary_input="/data/a",
                complexity_delta="couple replica offset with AOF rewrite",
            ),
        ],
    }
    errors = check_simula_plan(spec, incomplete, env_state=env)
    assert any("missing required Harbor preview keys" in item or "must be one of" in item for item in errors)
    unconstrained_plan = {
        "difficulty": "hard",
        "global": [global_row],
        "slots": [
            _slot(
                "c1",
                "g1",
                mechanism="plant-fault",
                scenario_angle="audit",
                output_shape="report-json",
                complexity_delta="couple checksum mismatch with replica lag",
                deployment_dimensions=_dims(gpu="required"),
            ),
            _slot(
                "c2",
                "g1",
                mechanism="recover-state",
                scenario_angle="incident-cleanup",
                output_shape="service-state",
                primary_entrypoint="redis-cli",
                complexity_delta="couple RDB load with expired key eviction",
            ),
            _slot(
                "c3",
                "g1",
                mechanism="configure-runtime",
                scenario_angle="failover",
                output_shape="replica-state",
                primary_input="/data/a",
                complexity_delta="couple replica offset with AOF rewrite",
            ),
        ],
    }
    errors = check_simula_plan(_spec(), unconstrained_plan, env_state=env)
    assert any("unconstrained" in item for item in errors)


def _check_complexity_and_recipe(tmp: Path) -> None:
    assert _complexity_delta_errors("c1", "add extra.json", hard=True)
    assert _complexity_delta_errors("c1", [{"axis": "coupling", "text": "add extra.json"}], hard=False)
    assert not _complexity_delta_errors("c1", _delta("couple replica offset with AOF rewrite"), hard=True)
    assert _complexity_delta_errors(
        "c1",
        [{"axis": "coupling", "text": "couple replica offset with AOF rewrite"}],
        hard=True,
    )
    instruction = tmp / "instruction.md"
    instruction.write_text("The bug is in src/t_string.c. Fix it.\n", encoding="utf-8")
    assert _instruction_recipe_errors(instruction, "hard", "c1")
    instruction.write_text("Keep the replica serving cache:probe after failover.\n", encoding="utf-8")
    assert not _instruction_recipe_errors(instruction, "hard", "c1")
    instruction.write_text("# Heading\nWrite src/out.json.\n", encoding="utf-8")
    tb_errors = _instruction_tb_quality_errors(instruction, "c1")
    assert any("headings" in item for item in tb_errors)
    assert any("absolute paths" in item for item in tb_errors)
    assert any("suffix" in item for item in tb_errors)
    instruction.write_text(
        "Keep the replica serving cache:probe after failover. Write /workspace/out.json.\n\n"
        "You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.\n",
        encoding="utf-8",
    )
    assert not _instruction_tb_quality_errors(instruction, "c1")


def _check_verifier_packaging(tmp: Path) -> None:
    tests = tmp / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text(
        "#!/usr/bin/env bash\nfail() { n=$((n+1)); }\ncat goldens/probe.json\n",
        encoding="utf-8",
    )
    source = (tests / "test.sh").read_text(encoding="utf-8")
    assert any("fail()" in item for item in _verifier_fail_logs_errors("c1", tests))
    assert any("goldens/" in item for item in _verifier_fixture_errors("c1", tests, source))
    (tests / "goldens").mkdir()
    (tests / "goldens" / "probe.json").write_text("{}\n", encoding="utf-8")
    (tests / "test.sh").write_text(
        "#!/usr/bin/env bash\nfail() { echo \"$1\" >&2; exit 1; }\ncat goldens/probe.json\n",
        encoding="utf-8",
    )
    source = (tests / "test.sh").read_text(encoding="utf-8")
    assert not _verifier_fail_logs_errors("c1", tests)
    assert not _verifier_fixture_errors("c1", tests, source)


def _check_verifier_form_diversity(tmp: Path) -> None:
    c1 = tmp / "c1" / "tests"
    c2 = tmp / "c2" / "tests"
    c1.mkdir(parents=True)
    c2.mkdir(parents=True)
    (c1 / "test.sh").write_text("#!/usr/bin/env bash\necho 1\n", encoding="utf-8")
    (c2 / "test.sh").write_text("#!/usr/bin/env bash\necho 1\n", encoding="utf-8")
    records = [{"candidate_id": "c1"}, {"candidate_id": "c2"}]
    errors = _verifier_form_diversity_errors(records, tmp)
    assert any("monolithic" in item for item in errors)
    (c2 / "test.sh").write_text("#!/usr/bin/env bash\npython3 check.py\n", encoding="utf-8")
    (c2 / "check.py").write_text("print(0)\n", encoding="utf-8")
    assert not _verifier_form_diversity_errors(records, tmp)


def _check_gpu_quota() -> None:
    assert HARBOR_RESOURCE_LIMITS["gpus"] == 1


def _check_mcp_and_gpu_preview(tmp: Path) -> None:
    cand_env = tmp / "c1" / "environment"
    cand_env.mkdir(parents=True)
    (cand_env / "setup.sh").write_text(
        "#!/usr/bin/env bash\ninstall -m 0755 file-tool /usr/local/bin/file-tool\n",
        encoding="utf-8",
    )
    slot = {"deployment_dimensions": _dims(mcp="required", gpu="required")}
    missing = _check_slot_task_preview(
        "c1",
        slot,
        {"environment": {"gpus": 1}},
        tmp,
        env_state={"network": {"agent": {"network_mode": "no-network", "allowed_hosts": []}}},
    )
    assert any("mcp_servers" in item for item in missing)
    http_mute = _check_slot_task_preview(
        "c1",
        slot,
        {
            "environment": {
                "gpus": 1,
                "mcp_servers": [{"name": "api", "transport": "sse", "url": "http://mcp:8000"}],
            },
            "agent": {"network_mode": "no-network"},
        },
        tmp,
    )
    assert any("HTTP MCP" in item for item in http_mute)
    stdio_ok = _check_slot_task_preview(
        "c1",
        slot,
        {
            "environment": {
                "gpus": 1,
                "mcp_servers": [
                    {"name": "file-tool", "transport": "stdio", "command": "/usr/local/bin/file-tool"}
                ],
            },
            "agent": {"network_mode": "no-network"},
        },
        tmp,
    )
    assert stdio_ok == []
    gpu_zero = _check_slot_task_preview(
        "c1",
        {"deployment_dimensions": _dims(gpu="required")},
        {"environment": {"gpus": 0}},
        tmp,
    )
    assert any("gpus >= 1" in item for item in gpu_zero)
    (cand_env / "docker-compose.yaml").write_text("services: {}\n")
    for gpu in ("optional", "required"):
        errors = _check_slot_task_preview(
            "c1", {"deployment_dimensions": _dims(container_mode="multiple", gpu=gpu)},
            {"environment": {"gpus": 1}}, tmp,
        )
        assert any("Daytona GPU allocation" in item for item in errors)
    assert any("GPU-required compose" in item for item in validate_spec(
        _spec(deployment_dimensions={"container_mode": ["multiple"], "gpu": ["required"]})
    ))


def _check_design_steps(tmp: Path) -> None:
    candidate = tmp / "c1"
    (candidate / "environment").mkdir(parents=True)
    (candidate / "environment/Dockerfile").write_text("FROM python:3.12-slim\n")
    instruction = (
        "Restore the service to a healthy state.\n\n"
        "You have 7200 seconds to complete this task. "
        "Do not cheat by using online solutions or hints specific to this task.\n"
    )
    for name in ("restore", "verify"):
        step = candidate / "steps" / name
        step.mkdir(parents=True)
        (step / "instruction.md").write_text(instruction)
    env = {"deployment_mode": "single"}
    design = {"candidates": [{"id": "c1", "oracle_tools": [], "steps": ["restore", "verify"]}]}
    plan = {"difficulty": "hard", "slots": [
        _slot("c1", "g1", deployment_dimensions=_dims(step_mode="multiple")),
    ]}
    assert check_design(design, tmp, env, plan) == []
    for invalid in (None, [], ["restore"], ["restore", "../escape"], ["restore", 2],
                    ["restore", "restore"], ["restore", "RESTORE"], ["restore", "NUL"]):
        malformed = copy.deepcopy(design)
        malformed["candidates"][0]["steps"] = invalid
        assert check_design(malformed, tmp, env, plan), invalid
    missing = copy.deepcopy(design)
    del missing["candidates"][0]["steps"]
    assert any("ordered steps" in error for error in check_design(missing, tmp, env, plan))
    step_instruction = candidate / "steps/verify/instruction.md"
    step_instruction.unlink()
    assert any("steps/verify/instruction.md" in error for error in check_design(design, tmp, env, plan))
    step_instruction.write_text("\n")
    assert any("steps/verify/instruction.md" in error for error in check_design(design, tmp, env, plan))
    step_instruction.write_text("# Hidden heading\n" + instruction)
    assert any("Markdown headings" in error for error in check_design(design, tmp, env, plan))
    step_instruction.write_text(instruction)

    plan["slots"][0]["deployment_dimensions"] = _dims()
    assert any("must not declare steps" in error for error in check_design(design, tmp, env, plan))
    del design["candidates"][0]["steps"]
    assert any("missing non-empty instruction.md" in error for error in check_design(design, tmp, env, plan))
    (candidate / "instruction.md").write_text(instruction)
    assert check_design(design, tmp, env, plan) == []


def _check_native_package(tmp: Path) -> None:
    candidates = tmp / "candidates"
    candidate = candidates / "c1"
    (candidate / "environment").mkdir(parents=True)
    (candidate / "environment/Dockerfile").write_text("FROM python:3.12-slim\n")
    config = '''schema_version = "1.4"
[task]
name = "simula/c1"
description = "Native step regression"
[metadata]
difficulty = "hard"
category = "Software"
tags = ["cli"]
[environment]
cpus = 4
memory_mb = 8192
storage_mb = 10240
gpus = 0
build_timeout_sec = 600
network_mode = "public"
[agent]
timeout_sec = 1800
network_mode = "public"
[verifier]
timeout_sec = 300
network_mode = "public"
[[steps]]
name = "restore"
[steps.agent]
timeout_sec = 1800
[steps.verifier]
timeout_sec = 300
[[steps]]
name = "verify"
[steps.agent]
timeout_sec = 1800
[steps.verifier]
timeout_sec = 300
'''
    (candidate / "task.toml").write_text(config)
    script = "#!/bin/bash\necho 'state: pass'\necho 0 > /logs/verifier/reward.txt\n"
    for name in ("restore", "verify"):
        step = candidate / "steps" / name
        (step / "tests").mkdir(parents=True)
        (step / "instruction.md").write_text(f"Complete {name}.\n")
        (step / "tests/test.sh").write_text(script)
        (step / "tests/test.sh").chmod(0o755)
    env = {"deployment_mode": "single", "source_repo": {"commit": "a" * 40}}
    design = {"candidates": [{"id": "c1", "oracle_tools": ["bash"], "steps": ["restore", "verify"]}]}
    state = {"verifiers": [{"candidate_id": "c1", "checked_requirements": [
        {"requirement": "service restored", "assertion": "state check"},
    ]}]}
    plan = {"difficulty": "hard", "global": [{"id": "g1", "domains": ["software"],
            "subdomains": ["systems"], "tags": ["cli"]}],
            "slots": [_slot("c1", "g1", deployment_dimensions=_dims(step_mode="multiple"))]}
    errors = check_verifiers(design, state, candidates, env, plan)
    assert not errors, errors
    reordered = config.replace('name = "restore"', 'name = "verify"', 1).rsplit('name = "verify"', 1)
    (candidate / "task.toml").write_text('name = "restore"'.join(reordered))
    assert any("steps must match" in error for error in check_verifiers(design, state, candidates, env, plan))
    (candidate / "task.toml").write_text(config)
    generated = tmp / "generated"
    package = generated / "alpha"
    shutil.copytree(candidate, package)
    (package / "task.toml").write_text(config.replace('name = "simula/c1"', 'name = "simula/alpha"'))
    (package / "README.md").write_text("candidate c1\n")
    (generated / "manifest.json").write_text(json.dumps({"generated_tasks": [{
        "candidate_id": "c1", "path": "alpha", "deployment_mode": "single", "source_commit": "a" * 40,
    }]}))
    args = (env, design, state, tmp / "base", candidates, generated)
    errors = check_package(*args)
    assert not errors, errors

    # Root instructions are optional for native steps and remain exact copies.
    root_instruction = "Restore the service, then verify its state.\n"
    (candidate / "instruction.md").write_text(root_instruction)
    assert any("byte-for-byte" in error for error in check_package(*args))
    (package / "instruction.md").write_text(root_instruction)
    assert check_package(*args) == []
    (package / "instruction.md").write_text("Changed instructions.\n")
    assert any("byte-for-byte" in error for error in check_package(*args))
    (candidate / "instruction.md").unlink()
    assert any("no corresponding candidate" in error for error in check_package(*args))
    (package / "instruction.md").unlink()
    assert check_package(*args) == []
    single_design = copy.deepcopy(design)
    del single_design["candidates"][0]["steps"]
    assert any("missing or empty instruction.md" in error for error in check_package(
        env, single_design, state, tmp / "base", candidates, generated,
    ))
    _, review = _write_review_fixture(tmp / "reports")
    assert check_verifier_review(state, review, generated) == []

    # Nop may repair the assembled environment, but no task or verifier drift.
    (package / "environment/Dockerfile").write_text("FROM python:3.12-slim\nRUN mkdir /app\n")
    assert any("environment files differ" in e for e in check_package(*args))
    assert check_package(*args, allow_environment_repairs=True) == []
    step_test = package / "steps/verify/tests/test.sh"
    step_test.write_text(script + "pip install surprise\n")
    assert any("steps files differ" in e for e in check_package(*args, allow_environment_repairs=True))
    assert any("must not install" in e for e in check_verifier_review(state, review, generated))
    step_test.write_text(script)
    (package / "steps/verify/instruction.md").unlink()
    assert any("steps/verify/instruction.md" in e for e in check_package(*args, allow_environment_repairs=True))

    # Harbor selects a local verifier where present and otherwise shared tests.
    shutil.rmtree(candidate / "steps/verify/tests")
    (candidate / "tests").mkdir()
    (candidate / "tests/test.sh").write_text(script)
    (candidate / "tests/test.sh").chmod(0o755)
    (candidate / "tests/fixtures").mkdir()
    (candidate / "tests/fixtures/input.txt").write_text("shared\n")
    (candidate / "steps/restore/tests/test.sh").write_text(script + "cat /tests/fixtures/input.txt\n")
    dirs, errors = _task_verifier_dirs(candidate)
    assert not errors and dirs == [candidate / "steps/restore/tests", candidate / "tests"]
    errors = check_verifiers(design, state, candidates, env, plan)
    assert not errors, errors
    separate_doc = tomllib.loads(config)
    separate_doc["verifier"]["environment_mode"] = "separate"
    separate_slot = {"deployment_dimensions": _dims(step_mode="multiple", verifier_mode="separate")}
    for tests in dirs:
        (tests / "Dockerfile").write_text("FROM python:3.12-slim\nCOPY . /tests\n")
    assert _check_slot_task_preview("c1", separate_slot, separate_doc, candidates, env) == []
    (dirs[0] / "Dockerfile").unlink()
    assert any("Dockerfile" in e for e in _check_slot_task_preview("c1", separate_slot, separate_doc, candidates, env))
    (candidate / "task.toml").write_text(config.replace('name = "verify"', 'name = "../escape"'))
    assert any("directory component" in e for e in _task_verifier_dirs(candidate)[1])


def _check_rejection_stops_phase(tmp: Path) -> None:
    """Run the real shell gate with its absolute paths relocated to a temp tree."""
    tmp.mkdir()
    synthesis = tmp / "synthesis"
    (synthesis / "input").mkdir(parents=True)
    (synthesis / "state").mkdir()
    spec = _spec()
    instruction = (ROOT / "steps/01_repo_profile_gate/instruction.md").read_text()
    profile = json.loads(re.search(r"```json\s*(\{.*?\})\s*```", instruction, re.S)[1])
    profile["checkout"]["head"] = spec["source_repo"]["commit"]
    (synthesis / "input/target_spec.json").write_text(json.dumps(spec))
    scripts = tmp / "scripts"
    shutil.copytree(ROOT / "environment/scripts", scripts)
    replacements = {"/synthesis": str(synthesis), "/opt/terminaltraj/scripts": str(scripts),
                    "/tests/helpers.sh": str(tmp / "helpers.sh"), "/logs/verifier": str(tmp / "reward")}
    files = [(ROOT / "tests/helpers.sh", tmp / "helpers.sh"),
             (ROOT / "steps/01_repo_profile_gate/tests/test.sh", tmp / "test.sh"),
             (scripts / "phase_contract.py", scripts / "phase_contract.py")]
    for source, destination in files:
        text = source.read_text()
        for old, new in replacements.items():
            text = text.replace(old, new)
        destination.write_text(text)
    (tmp / "bin").mkdir()
    (tmp / "bin/python").symlink_to(sys.executable)
    env = dict(os.environ, PATH=str(tmp / "bin") + os.pathsep + os.environ["PATH"], PYTHONDONTWRITEBYTECODE="1")
    for decision, score, reward in (("accept", 0.9, "1"), ("reject", 0.1, "0")):
        profile.update(decision=decision, task_potential_score=score,
                       blockers=[] if decision == "accept" else ["task potential below threshold"])
        (synthesis / "state/01_repo_profile_gate.json").write_text(json.dumps(profile))
        result = subprocess.run(["bash", str(tmp / "test.sh")], env=env, capture_output=True, text=True)
        assert (tmp / "reward/reward.txt").read_text().strip() == reward, result.stderr
        assert (result.returncode == 0) == (decision == "accept"), result.stderr


if __name__ == "__main__":
    _check_comment_filter()
    _check_review_mapping()
    _check_review_reports()
    _check_mechanisms()
    _check_deployment_gates()
    _check_gpu_quota()
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        _check_complexity_and_recipe(tmp)
        _check_verifier_packaging(tmp)
        _check_verifier_form_diversity(tmp / "forms")
        _check_mcp_and_gpu_preview(tmp / "preview")
        _check_design_steps(tmp / "design")
        _check_native_package(tmp / "native")
        _check_rejection_stops_phase(tmp / "gate")
    print("contract regressions passed")
