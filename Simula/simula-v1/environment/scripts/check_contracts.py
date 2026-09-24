#!/usr/bin/env python3
"""Static contract checks for the seven-phase Simula synthesis task."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from phase_contract import PHASE_HANDOFFS, validate_spec  # noqa: E402

ERRORS: list[str] = []
PHASES = [
    "01_repo_profile_gate",
    "02_environment",
    "03_simula_plan",
    "04_task_design",
    "05_verifier_and_task",
    "06_package",
    "07_review",
]
OLD_PHASES = {
    "01_repo_profile", "02_repo_gate", "03_environment", "04_simula_plan",
    "05_task_design", "06_task_review", "07_verifier_generation",
    "08_verifier_review", "09_package",
}
PROMPT_SECTIONS = ("## ROLE", "## BOUNDARIES", "## INPUTS", "## HANDOFF", "## WORK", "## GATE")


def error(message: str) -> None:
    ERRORS.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_json_block(text: str) -> dict:
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if not blocks:
        raise ValueError("no JSON example found")
    value = json.loads(blocks[0])
    if not isinstance(value, dict):
        raise ValueError("JSON example must be an object")
    return value


def check_source_input() -> None:
    path = ROOT / "steps/01_repo_profile_gate/workdir/input/target_spec.json"
    if not path.is_file():
        error("missing phase 01 target_spec.json")
        return
    try:
        spec = json.loads(read(path))
    except json.JSONDecodeError as exc:
        error(f"target_spec.json is invalid JSON: {exc}")
        return
    for item in validate_spec(spec):
        error(f"target_spec.json: {item}")
    source = spec.get("source_repo") if isinstance(spec, dict) else None
    if not isinstance(source, dict) or set(source) != {"url", "commit"}:
        error("source_repo must contain exactly url and commit")
    if isinstance(spec, dict) and "repository" in spec:
        error("target_spec must not contain a staged repository directory")
    target = spec.get("target") if isinstance(spec, dict) else None
    if isinstance(target, dict):
        for key in ("domains", "subdomains", "tags", "languages", "oracle_types"):
            if key not in target:
                error(f"target missing {key}")
        if "task_types" in target:
            error("target.task_types is removed")


def check_phase_layout() -> None:
    dirs = sorted(p.name for p in (ROOT / "steps").iterdir() if p.is_dir() and not p.name.startswith("."))
    if dirs != sorted(PHASES):
        error(f"steps directories must be exactly {PHASES}; got {dirs}")
    stale = sorted(set(dirs) & OLD_PHASES)
    if stale:
        error(f"old phase directories remain: {stale}")
    for phase in PHASES:
        instruction = ROOT / "steps" / phase / "instruction.md"
        test = ROOT / "steps" / phase / "tests" / "test.sh"
        if not instruction.is_file():
            error(f"missing {instruction.relative_to(ROOT)}")
        if not test.is_file():
            error(f"missing {test.relative_to(ROOT)}")
        if instruction.is_file():
            text = read(instruction)
            positions = [text.find(section) for section in PROMPT_SECTIONS]
            if any(pos < 0 for pos in positions) or positions != sorted(positions):
                error(f"{phase}/instruction.md must use the six prompt sections in order")


def check_task_toml() -> None:
    path = ROOT / "task.toml"
    if not path.is_file():
        error("missing task.toml")
        return
    text = read(path)
    try:
        import tomllib
        parsed = tomllib.loads(text)
        declared = [step.get("name") for step in parsed.get("steps", []) if isinstance(step, dict)]
        step_min = {step.get("name"): step.get("min_reward") for step in parsed.get("steps", []) if isinstance(step, dict)}
    except ModuleNotFoundError:
        declared = re.findall(r'(?ms)^\[\[steps\]\]\s*\n(?:[^\n]*\n)*?name\s*=\s*"([^"]+)"', text)
        step_min = {name: 1.0 for name in declared}
    except Exception as exc:  # noqa: BLE001
        error(f"task.toml does not parse: {exc}")
        return
    if declared != PHASES:
        error(f"task.toml steps must be {PHASES}; got {declared}")
    for phase in PHASES:
        if phase not in declared:
            error(f"task.toml missing {phase}")
        if step_min.get(phase) != 1.0:
            error(f"{phase} must have min_reward = 1.0")
    artifacts = parsed.get("artifacts", []) if "parsed" in locals() else []
    if isinstance(artifacts, list):
        artifact_strings = [str(item) for item in artifacts]
        for parent in artifact_strings:
            if any(child != parent and child.startswith(parent.rstrip("/") + "/") for child in artifact_strings):
                error(f"task.toml artifacts must not contain nested paths under {parent}")


def check_phase01() -> None:
    instruction = read(ROOT / "steps/01_repo_profile_gate/instruction.md")
    test = read(ROOT / "steps/01_repo_profile_gate/tests/test.sh")
    for needle in ("source_repo.url", "source_repo.commit", "check-repo-profile-gate", "hard_checks", "taxonomy.md", "deployment_support", "checkout.head"):
        if needle not in instruction:
            error(f"phase 01 instruction missing {needle}")
    if ("/synthesis/input/repository" in instruction and "do not" not in instruction.lower()) or "oracle_type" in instruction.lower():
        error("phase 01 must not expose a local repository path or oracle type")
    for needle in ("require_handoff 01_repo_profile_gate", "check-repo-profile-gate", "source_repo.path"):
        if needle not in test:
            error(f"phase 01 test missing {needle}")


def check_phase02() -> None:
    instruction = read(ROOT / "steps/02_environment/instruction.md")
    test = read(ROOT / "steps/02_environment/tests/test.sh")
    try:
        example = extract_json_block(instruction)
    except Exception as exc:  # noqa: BLE001
        error(f"phase 02 JSON example invalid: {exc}")
        example = {}
    for key in ("deployment_mode", "source_repo", "services", "resources", "dependencies", "asset_paths", "network", "paths", "entrypoints", "build"):
        if key not in example:
            error(f"phase 02 example missing {key}")
    paths = example.get("paths", {}) if isinstance(example.get("paths"), dict) else {}
    if paths.get("data_dir", "missing") is not None or paths.get("results_dir", "missing") is not None:
        error("phase 02 data_dir and results_dir must be nullable")
    network = example.get("network", {}) if isinstance(example.get("network"), dict) else {}
    for section in ("environment", "agent", "verifier"):
        policy = network.get(section, {})
        if policy.get("network_mode") not in {"public", "no-network", "allowlist"}:
            error(f"phase 02 network.{section} must use a Harbor network mode")
    for needle in ("require_handoff 02_environment", "check-environment"):
        if needle not in test:
            error(f"phase 02 test missing {needle}")
    if "sufficiently base" not in instruction:
        error("phase 02 instruction must keep the shared environment sufficiently base")
    if "references/environment.md" not in instruction:
        error("phase 02 must use the environment writing paradigm")
    if "resources.gpus = 1" not in instruction:
        error("phase 02 must allocate GPU quota when target and phase 01 evidence request it")
    if "examples/tasks" not in instruction:
        error("phase 02 must point at Harbor example tasks when layout is uncertain")
    if "clone once" not in instruction.lower() and "build the dockerfile once" not in instruction.lower():
        error("phase 02 must clone once, build once, and smoke once")
    if "/synthesis/input/repository" in instruction and "do not" not in instruction.lower():
        error("phase 02 must use URL+commit source coordinates")


def check_phase03() -> None:
    instruction = read(ROOT / "steps/03_simula_plan/instruction.md")
    test = read(ROOT / "steps/03_simula_plan/tests/test.sh")
    for needle in (
        "Global Diversification",
        "Local Diversification",
        "Complexification",
        "Harbor preview",
        "scenario_angle",
        "complexity_delta",
        "check-simula-plan",
        "03_simula_plan.json",
        "mechanism",
        "difficulty",
        "deployment_dimensions",
    ):
        if needle not in instruction:
            error(f"phase 03 instruction missing {needle}")
    if "phase_contract.py check-simula-plan" not in test or "require_handoff 03_simula_plan" not in test:
        error("phase 03 test must check its handoff and plan contract")
    if "docker build" in instruction.lower() or "check-environment" in test:
        error("phase 03 must not build or re-check the environment")
    if "harbor-task-creator/SKILL.md" in instruction:
        error("phase 03 must not open the full harbor-task-creator skill")


def check_phase04() -> None:
    instruction = read(ROOT / "steps/04_task_design/instruction.md")
    test = read(ROOT / "steps/04_task_design/tests/test.sh")
    for needle in (
        "03_simula_plan",
        "progressive disclosure",
        "instruction.md",
        "environment/",
        "check-design",
        "references/instruction.md",
        "references/environment.md",
        "docs/difficulty.md",
        "docs/failure-mode.md",
        "deployment_dimensions",
        "instruction diversity",
        "Wait for every candidate subagent",
        "examples/tasks",
        "scenario_angle",
        "output_shape",
        "oracle_types",
    ):
        if needle.lower() not in instruction.lower():
            error(f"phase 04 instruction missing progressive-disclosure item {needle}")
    if "acceptance criteria" not in instruction.lower() or "current situation" not in instruction.lower():
        error("phase 04 instruction must state the current situation and acceptance criteria")
    if "phenomena" not in instruction.lower() and "specific problem" not in instruction.lower():
        error("phase 04 instruction must describe phenomena, not the specific problem")
    instruction_ref = read(ROOT / "environment/skills/simula-synthesis/references/instruction.md")
    format_ref = read(ROOT / "environment/skills/simula-synthesis/references/instruction.md")
    for needle in ("Do not disclose", "root cause", "repair recipes"):
        if needle.lower() not in instruction_ref.lower():
            error(f"phase 04 instruction-quality reference missing {needle}")
    for needle in ("Markdown headings", "absolute path only for an artifact the agent must create", "Terminal-Bench suffix"):
        if needle.lower() not in format_ref.lower():
            error(f"phase 04 format reference missing {needle}")
    for needle in ("require_handoff 04_task_design", "check-design"):
        if needle not in test:
            error(f"phase 04 test missing {needle}")
    if "bash -n" not in instruction:
        error("phase 04 must check environment scripts with bash -n")
    if "do not build or run candidate images" not in instruction.lower():
        error("phase 04 must forbid docker build of candidate images")
    if "setup-overlay" in instruction.lower() or "env_build" in instruction.lower():
        error("phase 04 must copy the sealed environment and edit the copy, not overlay it")


def check_phase05() -> None:
    instruction = read(ROOT / "steps/05_verifier_and_task/instruction.md")
    test = read(ROOT / "steps/05_verifier_and_task/tests/test.sh")
    task_ref = read(ROOT / "environment/skills/simula-synthesis/references/task-toml.md")
    tests_ref = read(ROOT / "environment/skills/simula-synthesis/references/tests.md")
    for needle in (
        "03_simula_plan",
        "oracle_tools",
        "task.toml",
        "check-verifiers",
        "references/tests.md",
        "references/task-toml.md",
        "goldens",
        "deployment_dimensions",
        "discriminator",
        "wrong solutions",
    ):
        if needle not in instruction:
            error(f"phase 05 instruction missing {needle}")
    for needle in ("require_handoff 05_verifier", "check-verifiers"):
        if needle not in test:
            error(f"phase 05 test missing {needle}")
    for needle in ("tests/test.sh", "pytest==9.1.1", "pytest-json-ctrf==0.5.2", "stdio", "examples/tasks"):
        if needle not in tests_ref and needle not in task_ref:
            error(f"phase 05 reference missing {needle}")
    if "install packages" not in instruction.lower() and "must not install packages" not in tests_ref.lower():
        error("phase 05 must forbid verifier-time package installation")
    if "harbor-task-creator/SKILL.md" in instruction:
        error("phase 05 must not open the full harbor-task-creator skill")


def check_phase06() -> None:
    instruction = read(ROOT / "steps/06_package/instruction.md")
    test = read(ROOT / "steps/06_package/tests/test.sh")
    packaging_ref = read(ROOT / "environment/skills/simula-synthesis/references/packaging.md")
    for needle in (
        "assemble only",
        "generated_task",
        "manifest.json",
        "README.md",
        "04_task_design.json",
        "05_verifier.json",
        "TaskPaths",
        "TaskConfig",
        "packaging.md",
        "harbor run -a nop",
        "DAYTONA_API_KEY",
    ):
        if needle.lower() not in instruction.lower() and needle.lower() not in test.lower() and needle.lower() not in packaging_ref.lower():
            error(f"phase 06 package contract missing {needle}")
    if "reward 0" not in instruction.lower() and "reward is 0" not in instruction.lower() and "reward `0`" not in packaging_ref.lower():
        error("phase 06 must treat nop reward 0 as the pass")
    if "check-package" not in test:
        error("phase 06 test must run check-package")
    if "require_harbor_packages" not in test:
        error("phase 06 test must call require_harbor_packages (Harbor library, not a Simula wrapper)")
    if "check-harbor-packages" in instruction or "check-harbor-packages" in test:
        error("phase 06 must not wrap Harbor APIs in phase_contract.py")
    if "check-environment" in test:
        error("phase 06 must not re-run check-environment")


def check_phase07() -> None:
    instruction = read(ROOT / "steps/07_review/instruction.md")
    test = read(ROOT / "steps/07_review/tests/test.sh")
    packaging_ref = read(ROOT / "environment/skills/simula-synthesis/references/packaging.md")
    for needle in (
        "publish",
        "revise",
        "reject",
        "too-loose",
        "too-strict",
        "generated_task",
        "07_review.json",
        "release_candidate_ids",
        "Static Checks",
        "Implementation Rubric",
        "harbor_shape_ok",
        "Static Review Agent",
        "Implementation Review Agent",
        "review_reports",
        "advisory",
        "difficulty.md",
        "static-checks.md",
        "task-implementation.toml",
        "taxonomy.md",
        "smallest change",
        "packaging.md",
        "references/tests.md",
        "DAYTONA_API_KEY",
        "harbor run -a nop",
        "examples/tasks",
    ):
        if needle.lower() not in instruction.lower() and needle.lower() not in packaging_ref.lower():
            error(f"phase 07 review contract missing {needle}")
    collapsed = " ".join(instruction.split())
    if "TASK_REVIEW_AUTOMATION.md" in collapsed and "Do not fetch" not in collapsed:
        error("phase 07 must use local docs, not fetch TASK_REVIEW_AUTOMATION.md")
    if "github.com/harbor-framework/terminal-bench" in collapsed and "Do not fetch" not in collapsed:
        error("phase 07 must not use the remote Terminal-Bench review URL as the source")
    if "Write `release_manifest.json`" in instruction or "write release_manifest.json as" in instruction.lower():
        error("phase 07 must not write release_manifest.json")
    if ("environment/" not in instruction and "environment" not in packaging_ref) or ("tests/" not in instruction and "tests" not in packaging_ref):
        error("phase 07 must repair environment and tests unless the instruction conflicts")
    if "smallest assertion" not in instruction.lower() and "smallest assertion" not in packaging_ref.lower():
        error("phase 07 must repair too-loose/too-strict in tests with the smallest change until publish")
    if "returns the candidate to phase 05" in instruction or "return the candidate to phase 05" in instruction:
        error("phase 07 must not bounce too-loose/too-strict repairs to phase 05")
    docs = ROOT / "environment" / "docs"
    for name in ("static-checks.md", "task-implementation.toml", "taxonomy.md", "difficulty.md", "failure-mode.md"):
        if not (docs / name).is_file():
            error(f"missing environment/docs/{name}")
    dockerfile = read(ROOT / "environment" / "Dockerfile")
    if "COPY docs/ /opt/terminaltraj/docs/" not in dockerfile:
        error("environment Dockerfile must copy docs/ to /opt/terminaltraj/docs/")
    if "check-review" not in test and "check-verifier-review" not in test:
        error("phase 07 test must run the review contract")
    if "require_harbor_packages" not in test:
        error("phase 07 test must call require_harbor_packages (Harbor library, not a Simula wrapper)")
    if "check-harbor-packages" in instruction or "check-harbor-packages" in test:
        error("phase 07 must not wrap Harbor APIs in phase_contract.py")


def check_handoffs() -> None:
    expected = {
        "01_repo_profile_gate": "/synthesis/state/01_repo_profile_gate.json",
        "02_environment": "/synthesis/state/02_environment.json",
        "03_simula_plan": "/synthesis/state/03_simula_plan.json",
        "04_task_design": "/synthesis/state/04_task_design.json",
        "05_verifier": "/synthesis/state/05_verifier.json",
        "07_review": "/synthesis/state/07_review.json",
    }
    if set(PHASE_HANDOFFS) != set(expected):
        error(f"PHASE_HANDOFFS keys must be {sorted(expected)}")
    for key, path in expected.items():
        if PHASE_HANDOFFS.get(key, {}).get("path") != path:
            error(f"handoff {key} path must be {path}")
    for phase in PHASES:
        text = read(ROOT / "steps" / phase / "instruction.md")
        if phase in PHASE_HANDOFFS and (f"ensure-handoff {phase}" not in text or f"require-handoff {phase}" not in text):
            error(f"{phase} must ensure and require its handoff")
    package = read(ROOT / "steps/06_package/instruction.md")
    for phase in ("02_environment", "04_task_design", "05_verifier"):
        if f"require-handoff {phase}" not in package.replace("`", ""):
            error(f"phase 06 must require-handoff {phase}")


def check_scripts() -> None:
    if (ROOT / "scripts").exists():
        error("repo-root scripts/ was collapsed into environment/scripts/")
    docs = ROOT / "environment" / "docs"
    scripts = ROOT / "environment" / "scripts"
    skills = ROOT / "environment" / "skills"
    for path in (docs, scripts, skills):
        if not path.is_dir():
            error(f"missing {path.relative_to(ROOT)}")
    dockerfile = read(ROOT / "environment" / "Dockerfile")
    for line in (
        "COPY docs/ /opt/terminaltraj/docs/",
        "COPY scripts/ /opt/terminaltraj/scripts/",
        "COPY skills/ /opt/terminaltraj/skills/",
    ):
        if line not in dockerfile:
            error(f"environment Dockerfile must {line}")
    for path in (
        scripts / "phase_contract.py",
        scripts / "validate_json.py",
        scripts / "state_integrity.py",
        scripts / "check_contracts.py",
        scripts / "check_contract_regressions.py",
    ):
        if not path.is_file():
            error(f"missing {path.relative_to(ROOT)}")
            continue
        try:
            compile(read(path), str(path), "exec")
        except SyntaxError as exc:
            error(f"{path.relative_to(ROOT)} syntax error: {exc}")
    helpers = ROOT / "tests/helpers.sh"
    helper_text = read(helpers) if helpers.is_file() else ""
    if "require_handoff" not in helper_text:
        error("tests/helpers.sh must define require_handoff")
    if "require_harbor_packages" not in helper_text:
        error("tests/helpers.sh must define require_harbor_packages")
    if "TaskPaths" not in helper_text or "TaskConfig" not in helper_text:
        error("require_harbor_packages must call Harbor TaskPaths and TaskConfig")
    refs = skills / "simula-synthesis" / "references"
    expected_refs = {
        "environment.md",
        "instruction.md",
        "packaging.md",
        "task-toml.md",
        "tests.md",
    }
    if refs.is_dir():
        present = {p.name for p in refs.iterdir() if p.is_file()}
        if present != expected_refs:
            error(
                "simula-synthesis/references must contain the five shared phase references "
                f"{sorted(expected_refs)}; got {sorted(present)}"
            )
    else:
        error("missing environment/skills/simula-synthesis/references")


def main() -> int:
    check_source_input()
    check_phase_layout()
    check_task_toml()
    check_phase01()
    check_phase02()
    check_phase03()
    check_phase04()
    check_phase05()
    check_phase06()
    check_phase07()
    check_handoffs()
    check_scripts()
    if ERRORS:
        print("contract check FAILED")
        for item in ERRORS:
            print(f"  - {item}")
        return 1
    print("contract check passed")
    print(f"  phases: {len(PHASES)}")
    print("  source input: URL + pinned commit")
    print("  progressive disclosure: phase 03 slots; 04+ do not reread target_spec")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
