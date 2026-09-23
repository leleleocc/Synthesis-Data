#!/usr/bin/env python3
"""Static contract checks for the TerminalTraj synthesis task (no Docker)."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "environment" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from target_spec import validate_spec  # noqa: E402

ERRORS: list[str] = []

BUILD_FILES = (
    "Dockerfile",
    "docker-compose.yaml",
    "docker-compose.yml",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "Pipfile",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Makefile",
    "CMakeLists.txt",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Gemfile",
    "composer.json",
    "mix.exs",
    "Package.swift",
)


def error(message: str) -> None:
    ERRORS.append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_json_block(markdown: str, heading_hint: str | None = None) -> dict:
    """Pull the first fenced JSON object from an instruction markdown file."""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", markdown, flags=re.S)
    if not blocks:
        raise ValueError("no json fence found")
    if heading_hint:
        for block in blocks:
            if heading_hint in block:
                return json.loads(block)
    return json.loads(blocks[0])


def keys_from_require_json(test_text: str) -> list[str]:
    keys: list[str] = []
    lines = test_text.splitlines()
    for index, line in enumerate(lines):
        if "require_json_keys" not in line:
            continue
        chunk = [line]
        cursor = index
        while chunk[-1].rstrip().endswith("\\"):
            cursor += 1
            chunk.append(lines[cursor])
        text = " ".join(part.rstrip("\\").strip() for part in chunk)
        tokens = text.split()
        path_index = next(
            i
            for i, token in enumerate(tokens)
            if token.endswith(".json")
            or token.startswith("$")
            or token.startswith('"')
            or token.startswith("/")
        )
        keys = tokens[path_index + 1 :]
        break
    return keys


def check_dockerfile() -> None:
    text = read(ROOT / "environment" / "Dockerfile")
    if "chmod +x /opt/terminaltraj/scripts/*.sh" in text:
        error("Dockerfile still uses brittle empty *.sh glob chmod")
    if "find /opt/terminaltraj/scripts" not in text and "chmod +x" in text:
        if not (ROOT / "environment" / "scripts").glob("*.sh"):
            if "*.sh" in text:
                error("Dockerfile chmod references missing *.sh files")
    # Must ship a Docker CLI that can talk to Harbor's DinD (docker:28.3.3-dind).
    # Debian docker.io is too old (Trixie ~26.x); require the matching official CLI.
    has_matching_cli = (
        "docker:28.3.3-cli" in text
        or "docker-ce-cli" in text
        or "docker-28.3.3.tgz" in text
    )
    if not has_matching_cli:
        error(
            "Dockerfile must install a Docker 28.x CLI matching DinD "
            "(COPY --from=docker:28.3.3-cli ..., docker-ce-cli, or static 28.3.3 tarball); "
            "do not use apt docker.io"
        )
    # Flag only if apt-get install still names the docker.io package.
    if re.search(r"apt-get\s+install\b[^\n]*\bdocker\.io\b", text):
        error(
            "Dockerfile installs Debian docker.io via apt; its CLI is too old for "
            "docker:28.3.3-dind and makes docker info fail inside main"
        )
    if re.search(r"apt-get install[\s\S]*docker-compose-v2", text):
        error("Dockerfile installs Ubuntu-only docker-compose-v2; omit it on Debian")
    compose = ROOT / "environment" / "docker-compose.yaml"
    if not compose.is_file():
        error("missing environment/docker-compose.yaml (Daytona DinD trigger)")
        return
    compose_text = read(compose)
    if "docker.sock" not in compose_text:
        error("docker-compose.yaml does not mount /var/run/docker.sock into main")
    if "COPY skills/" not in text and "COPY skills /" not in text:
        error("Dockerfile must COPY environment/skills into the image")


def check_sample_input() -> None:
    target = ROOT / "steps" / "01_repo_profile" / "workdir" / "input" / "target_spec.json"
    repo = ROOT / "steps" / "01_repo_profile" / "workdir" / "input" / "repository"
    if not target.is_file():
        error("missing target_spec.json under step 01 workdir")
        return
    if not repo.is_dir():
        error("missing source repository under step 01 workdir")
        return
    try:
        spec = json.loads(read(target))
    except json.JSONDecodeError as exc:
        error(f"target_spec.json is invalid JSON: {exc}")
        return
    for item in validate_spec(spec):
        error(f"target_spec.json: {item}")
    readmes = list(repo.glob("README*"))
    licenses = [
        repo / name
        for name in (
            "LICENSE",
            "COPYING",
            "LICENSE.txt",
            "LICENSE.md",
            "COPYING.md",
            "LICENCE",
        )
    ]
    if not readmes:
        error("source repository has no README file")
    if not any(path.is_file() for path in licenses):
        error("source repository has no recognized license file")
    if not any((repo / name).is_file() for name in BUILD_FILES):
        error("source repository has no recognized build/runtime manifest")
    taxonomy = ROOT / "environment" / "scripts" / "taxonomy.md"
    if not taxonomy.is_file():
        error("missing environment/scripts/taxonomy.md")
    else:
        tax = read(taxonomy)
        for heading in ("## Science", "## Software", "## ML", "## Operations", "## Security", "## Hardware", "## Media"):
            if heading not in tax:
                error(f"taxonomy.md missing domain heading {heading}")
    target_obj = spec.get("target") if isinstance(spec, dict) else None
    if isinstance(target_obj, dict):
        if "task_types" in target_obj:
            error("target_spec.json still has task_types; use tags")
        for key in ("domains", "subdomains", "tags", "languages", "oracle_types"):
            if key not in target_obj:
                error(f"target_spec.json target missing {key}")


def check_step03_schema_alignment() -> None:
    instruction = read(ROOT / "steps" / "03_environment" / "instruction.md")
    test = read(ROOT / "steps" / "03_environment" / "tests" / "test.sh")
    try:
        schema = extract_json_block(instruction)
    except Exception as exc:  # noqa: BLE001
        error(f"step 03 instruction JSON example unreadable: {exc}")
        return
    required = set(keys_from_require_json(test))
    example = set(schema)
    missing_in_example = sorted(required - example)
    if missing_in_example:
        error(
            "step 03 instruction example missing keys required by test: "
            + ", ".join(missing_in_example)
        )
    for key in ("asset_paths", "network_policy", "data_dir", "results_dir", "build"):
        if key not in schema:
            error(f"step 03 schema example missing {key}")
    for dropped in ("asset_manifest", "service_contract"):
        if dropped in schema:
            error(f"step 03 schema example still has dropped field {dropped}")
    if "target_spec.py check-environment" not in test:
        error("step 03 test does not use the shared check-environment contract")
    if "target_spec.py check-environment" not in instruction:
        error("step 03 instruction does not tell the agent to self-check with check-environment")
    if "git clone" not in instruction:
        error("step 03 instruction does not require cloning the source at the pinned commit")
    if "setup-overlay.sh" not in instruction:
        error("step 03 instruction must ship a no-op setup-overlay.sh")
    later_env_checks = 0
    for step_name in (
        "04_simula_plan",
        "05_task_design",
        "06_task_review",
        "07_verifier_generation",
        "08_verifier_review",
        "09_package",
    ):
        later = read(ROOT / "steps" / step_name / "tests" / "test.sh")
        if "target_spec.py check-environment" in later:
            later_env_checks += 1
            error(f"{step_name} must not re-run check-environment")
    for needle, why in (
        ("## HANDOFF", "HANDOFF section with hard gate before long probes"),
        ("Hard gate", "hard deliverable gate before long probes"),
        ("03_environment.json", "require state handoff on disk"),
        ("CHECKLIST_OK", "on-disk checklist probe before stop"),
        ("Do not write", "forbid writing candidates/tests in phase 03"),
        ("ensure-handoff 03_environment", "write JSON handoff skeleton before full build"),
        ("synth-env:03", "docker build tag for the sealed base"),
        ("shared base", "tell the agent this image is a shared base, not a task"),
        ("Do not shrink later diversity", "forbid specializing the base toward one later task"),
        ("harbor-task-creator", "point at Harbor task-creator skill for image wiring"),
        ("very simple demo", "label skill examples as very simple demos, not the base template"),
        ("example-tasks.md", "point at skill example walkthroughs"),
        ("Deliverables first", "require writing the environment tree before long probes"),
        ("mandatory before any long build", "Step 02 must land files before scratch compiles"),
        ("REFUSING_BUILD_MISSING_ENV_TREE", "refuse docker build when the env tree is missing"),
        ("skeleton: build not yet run", "warn that leaving the skeleton build block fails the phase"),
    ):
        if needle not in instruction:
            error(f"step 03 instruction lacks {why} ({needle!r})")


def check_step01_taxonomy() -> None:
    instruction = read(ROOT / "steps" / "01_repo_profile" / "instruction.md")
    test = read(ROOT / "steps" / "01_repo_profile" / "tests" / "test.sh")
    for needle, why in (
        ("taxonomy.md", "phase 01 must classify from the Terminal-Bench taxonomy"),
        ('"subdomains"', "phase 01 profile includes subdomains"),
        ('"tags"', "phase 01 profile includes tags, not task_types"),
        ("science", "phase 01 must list the closed domain vocabulary"),
        ("Do not write `supported_task_types`", "phase 01 must not emit task_types"),
    ):
        if needle not in instruction:
            error(f"step 01 instruction lacks {why} ({needle!r})")
    if "supported_task_types" in test:
        error("step 01 test still requires supported_task_types")
    if " subdomains " not in f" {test} " and "subdomains" not in test:
        error("step 01 test must require profile.subdomains")
    if "tags" not in test:
        error("step 01 test must require profile.tags")


def check_step02_threshold() -> None:
    instruction = read(ROOT / "steps" / "02_repo_gate" / "instruction.md")
    test = read(ROOT / "steps" / "02_repo_gate" / "tests" / "test.sh")
    if "min_repo_score" not in instruction:
        error("step 02 instruction does not read generation.min_repo_score")
    if "target_spec.py check-repo-gate" not in test:
        error("step 02 test does not enforce the combined filter/score gate")
    if "hard_checks" not in instruction:
        error("step 02 instruction must keep the hard_checks contract")


def check_step04_simula_gate() -> None:
    instruction = read(ROOT / "steps" / "04_simula_plan" / "instruction.md")
    test = read(ROOT / "steps" / "04_simula_plan" / "tests" / "test.sh")
    for needle, why in (
        ("Global Diversification", "Simula Global Diversification work section"),
        ("Local Diversification", "Simula Local Diversification work section"),
        ("Complexification", "Simula Complexification work section"),
        ("max_candidates", "slot count bound to generation.max_candidates"),
        ("03_environment.json", "plan grounded in the sealed environment"),
        ("candidates/", "forbid writing candidates/ in the plan step"),
        ("scenario_angle", "closed scenario-angle factor"),
        ("complexity_delta", "in-band complexity operator"),
        ("check-simula-plan", "self-check with check-simula-plan"),
        ("Do not docker-build", "paper plan; no docker in phase 04"),
    ):
        if needle not in instruction:
            error(f"step 04 instruction lacks {why} ({needle!r})")
    if "target_spec.py check-simula-plan" not in test:
        error("step 04 test must call check-simula-plan")
    if "require_handoff 04_simula_plan" not in test:
        error("step 04 test must require the simula plan handoff")
    if "check-environment" in test:
        error("step 04 test must not re-run check-environment")
    if "instruction.md" in instruction and "/synthesis/output/candidates" in instruction:
        # BOUNDARIES must forbid candidates/; WORK must not ask to write them.
        if "Do not write" not in instruction:
            error("step 04 instruction must forbid writing candidates/")


def check_step05_spec_gate() -> None:
    instruction = read(ROOT / "steps" / "05_task_design" / "instruction.md")
    test = read(ROOT / "steps" / "05_task_design" / "tests" / "test.sh")
    if "target.tags" not in instruction and "target_spec.target" not in instruction:
        error("step 05 instruction does not bind vocabulary fields to target_spec")
    if "task.toml" not in instruction or "instruction.md" not in instruction:
        error("step 05 instruction must require per-candidate instruction.md and task.toml")
    if "environment/" not in instruction:
        error("step 05 instruction must require a per-candidate overlay environment/")
    if "pure ASCII" not in instruction and "pure ascii" not in instruction.lower():
        error("step 05 instruction must require generated instruction.md/task.toml to be ASCII")
    if 'network_mode = "public"' not in instruction:
        error("step 05 instruction must default [environment].network_mode to public")
    if "max_candidates" not in instruction:
        error("step 05 instruction must bind candidate count to generation.max_candidates")
    for needle, why in (
        ("expert_time_estimate_min", "difficulty bands / SOTA-agent time estimates"),
        ("ultra", "ultra difficulty band (6h+ compound)"),
        ("SOTA", "difficulty measured as SOTA-agent wall-clock"),
        ("category", "Terminal-Bench category in [metadata]"),
        ("subcategory", "Terminal-Bench subcategory in [metadata]"),
        ("04_simula_plan.json", "consume the Simula plan instead of inventing a matrix"),
        ("consume the Simula", "diversity comes from the Simula slots"),
        ("complexity_delta", "complexified slots name the extra interacting piece"),
        ("build_seconds", "build_timeout_sec derived from the sealed-base build time"),
        ("env_build", "overlay rebuild status in the design index"),
        ("Do not modify `/synthesis/output/environment/`", "sealed base must stay frozen"),
        ("oracle_tools", "phase 05 must declare observation tools for the later verifier"),
        ('"tags"', "phase 05 index uses tags lists, not task_types"),
        ('"subdomains"', "phase 05 index uses subdomains lists"),
        ('"oracle_types"', "phase 05 index uses oracle_types lists, not a single oracle_type"),
        ("taxonomy.md", "phase 05 must classify from the Terminal-Bench taxonomy"),
    ):
        if needle not in instruction:
            error(f"step 05 instruction lacks {why} ({needle!r})")
    if "candidate matrix" in instruction:
        error("step 05 instruction still invents a candidate matrix; consume 04 slots")
    if "target_spec.py check-design" not in test:
        error("step 05 test does not check design against target_spec")
    if "04_simula_plan" not in test:
        error("step 05 test must verify the 04_simula_plan seal")
    if "task_contract" in instruction or "observable_outcome" in instruction:
        error("step 05 instruction still requires the old heavy design JSON fields")
    if "instruction_path" in instruction or "task_toml_path" in instruction:
        error("step 05 instruction still requires redundant path fields in the design index")
    if '"task_types"' in instruction:
        error("step 05 instruction still uses task_types; use tags")
    stripped = instruction.replace('"oracle_types"', "")
    if '"oracle_type"' in stripped:
        error("step 05 instruction still uses singular oracle_type JSON keys")
    if "max_query_candidates" in instruction or "max_tasks" in instruction:
        error("step 05 instruction still references removed generation budget fields")
    skill_root = ROOT / "environment" / "skills" / "harbor-task-creator"
    if not (skill_root / "SKILL.md").is_file():
        error("missing environment/skills/harbor-task-creator/SKILL.md")
    if not (skill_root / "references" / "task-toml-reference.md").is_file():
        error("missing environment/skills/harbor-task-creator/references/task-toml-reference.md")
    if "harbor-task-creator" not in instruction:
        error("step 05 instruction must tell the agent to synthesize task.toml from harbor-task-creator")
    if "/opt/terminaltraj/skills/harbor-task-creator" not in instruction:
        error("step 05 instruction must point at /opt/terminaltraj/skills/harbor-task-creator")
    if "example-tasks.md" not in instruction:
        error("step 05 instruction must point at harbor-task-creator example-tasks.md")
    if "very simple demo" not in instruction:
        error("step 05 instruction must label skill examples as very simple demos")


def check_multi_candidate_gates() -> None:
    review_instruction = read(ROOT / "steps" / "06_task_review" / "instruction.md")
    review_test = read(ROOT / "steps" / "06_task_review" / "tests" / "test.sh")
    verifier_instruction = read(ROOT / "steps" / "07_verifier_generation" / "instruction.md")
    verifier_test = read(ROOT / "steps" / "07_verifier_generation" / "tests" / "test.sh")
    package_instruction = read(ROOT / "steps" / "09_package" / "instruction.md")
    package_test = read(ROOT / "steps" / "09_package" / "tests" / "test.sh")
    checks = (
        (review_instruction, "approved_candidate_ids", "step 06 prompt lacks approved candidate list"),
        (review_instruction, "pure ASCII", "step 06 prompt must require generated instruction.md to stay ASCII"),
        (review_instruction, "env_build=failed", "step 06 prompt must reject failed overlays"),
        (review_instruction, "Do not write `/synthesis/state/05_task_design.json`", "step 06 prompt must forbid rewriting sealed 05_task_design.json"),
        (review_test, "target_spec.py check-review", "step 06 test lacks review contract check"),
        (verifier_instruction.lower(), "for every approved candidate", "step 07 prompt is not multi-candidate"),
        (verifier_test, "target_spec.py check-verifiers", "step 07 test lacks the shared verifier contract check"),
        (read(ROOT / "steps" / "08_verifier_review" / "tests" / "test.sh"), "target_spec.py check-verifier-review", "step 08 test lacks the shared verifier review check"),
        (read(ROOT / "steps" / "08_verifier_review" / "instruction.md"), "Too strict", "step 08 prompt lacks the too-loose/too-strict calibration lists"),
        (verifier_instruction, "Too strict", "step 07 prompt lacks the too-loose/too-strict calibration lists"),
        (verifier_instruction, "harbor-task-creator", "step 07 prompt must point at harbor-task-creator for reward-channel wiring"),
        (verifier_instruction, "very simple demo", "step 07 prompt must label skill examples as very simple demos"),
        (verifier_instruction, "example-tasks.md", "step 07 prompt must point at skill example walkthroughs"),
        (verifier_instruction, "oracle_tools", "step 07 prompt must use phase-05 oracle_tools"),
        (read(ROOT / "steps" / "08_verifier_review" / "instruction.md"), "oracle_tools", "step 08 prompt must rewrite verify-time installs onto oracle_tools"),
        (read(ROOT / "steps" / "08_verifier_review" / "instruction.md"), "Do not write `/synthesis/state/07_verifier.json`", "step 08 prompt must forbid rewriting sealed 07_verifier.json"),
        (package_instruction, "generated_task/<slug>", "step 09 prompt is not multi-package"),
        (package_instruction, "merged with", "step 09 prompt must merge base with overlay"),
        (package_test, "manifest.json", "step 09 test lacks package manifest check"),
    )
    for text, needle, message in checks:
        if needle not in text:
            error(message)
    if "max_tasks" in review_instruction:
        error("step 06 prompt still caps approvals with max_tasks")


def check_step09_package_gate() -> None:
    test = read(ROOT / "steps" / "09_package" / "tests" / "test.sh")
    instruction = read(ROOT / "steps" / "09_package" / "instruction.md")
    if "manifest.json" not in test:
        error("step 09 test missing manifest.json check")
    if "target_spec.py check-package" not in test:
        error("step 09 test must call check-package")
    if "output/environment" not in test:
        error("step 09 test must pass the synthesized environment path")
    if "05_task_design.json" not in test:
        error("step 09 test must pass phase-05 design state into check-package")
    if "README.md" not in instruction:
        error("step 09 instruction must require per-package README.md")
    if "task.toml" not in instruction or "instruction.md" not in instruction:
        error("step 09 instruction must assemble task.toml and instruction.md from candidates")
    if "Do not redesign" not in instruction and "assemble only" not in instruction.lower():
        error("step 09 instruction must state assemble-only (no redesign)")
    if "check-environment" in test:
        error("step 09 test must not re-run check-environment")


def check_task_toml_steps() -> None:
    task_toml = read(ROOT / "task.toml")
    step_dirs = sorted(
        path.name
        for path in (ROOT / "steps").iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    declared = re.findall(r'name\s*=\s*"([^"]+)"', task_toml)
    step_names = [name for name in declared if re.match(r"^\d{2}_", name)]
    if step_names != step_dirs:
        error(
            "task.toml steps do not match steps/ directories: "
            f"toml={step_names} dirs={step_dirs}"
        )
    for name in step_dirs:
        instruction = ROOT / "steps" / name / "instruction.md"
        test = ROOT / "steps" / name / "tests" / "test.sh"
        if not instruction.is_file():
            error(f"missing {instruction.relative_to(ROOT)}")
        if not test.is_file():
            error(f"missing {test.relative_to(ROOT)}")
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    parsed = tomllib.loads(task_toml)
    by_name = {
        step.get("name"): step
        for step in (parsed.get("steps") or [])
        if isinstance(step, dict)
    }
    # Harbor MultiStepTrial uses step.agent.timeout_sec (falls back to
    # top-level [agent].timeout_sec, then unbounded). Docker builds of the
    # sealed base (03) and optional overlay images (05) need a real budget.
    for name, minimum in (("03_environment", 3600.0), ("05_task_design", 3600.0)):
        timeout = ((by_name.get(name) or {}).get("agent") or {}).get("timeout_sec")
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout < minimum:
            error(
                f"{name} needs [steps.agent].timeout_sec >= {minimum:g} "
                "(Harbor honors this field; docker builds need the budget)"
            )
    eight = by_name.get("09_package") or {}
    if eight.get("min_reward") != 1.0:
        error("09_package needs min_reward = 1.0 so a failed assemble fails the trial")


def check_input_repo_readonly_warning() -> None:
    """Phases after 01 should treat the input tree as read-only reference.

    The final Harbor package clones the pinned upstream commit; it does not
    ship /synthesis/input/repository. A tree-hash seal is intentionally not
    used. Still tell agents not to mutate the fixture and to use a scratch
    copy when they need to run commands.
    """
    for step in sorted((ROOT / "steps").iterdir()):
        if not step.is_dir() or step.name.startswith("01_"):
            continue
        text = read(step / "instruction.md")
        if "sealed by a tree hash" in text:
            error(
                f"{step.name}/instruction.md still describes a source tree-hash "
                "seal; that mechanism was removed"
            )
        if "/synthesis/input/repository" not in text and "input/repository" not in text:
            # 03 uses softer wording; allow "read-only" + scratch as fallback
            if "read-only" not in text.lower() and "scratch" not in text:
                error(
                    f"{step.name}/instruction.md should treat the input repository "
                    "as read-only reference (or mention a scratch copy)"
                )


def check_no_source_tree_seal() -> None:
    """Verifiers must not seal or verify the input repository tree."""
    helpers = read(ROOT / "tests" / "helpers.sh")
    if "verify_source_repo" in helpers or "seal_state_tree" in helpers:
        error("tests/helpers.sh still defines source-tree seal helpers; remove them")
    for test in sorted((ROOT / "steps").glob("*/tests/test.sh")):
        text = read(test)
        if "verify_source_repo" in text or "seal_state_tree" in text or "seal-tree" in text:
            error(f"{test.relative_to(ROOT)} still references source-tree sealing")


PROMPT_SECTIONS = (
    "## ROLE",
    "## BOUNDARIES",
    "## INPUTS",
    "## HANDOFF",
    "## WORK",
    "## GATE",
)


def check_prompt_framework() -> None:
    """Every step instruction uses the six-section prompt framework."""
    for instruction in sorted((ROOT / "steps").glob("*/instruction.md")):
        text = read(instruction)
        positions: list[int] = []
        for header in PROMPT_SECTIONS:
            idx = text.find(header)
            if idx < 0:
                error(f"{instruction.relative_to(ROOT)} missing section {header}")
                positions = []
                break
            positions.append(idx)
        if positions and positions != sorted(positions):
            error(
                f"{instruction.relative_to(ROOT)} sections out of order; "
                "expected ROLE, BOUNDARIES, INPUTS, HANDOFF, WORK, GATE"
            )
        if "## WORK" in text and "### Step 01:" not in text and "### Step 1:" not in text:
            error(f"{instruction.relative_to(ROOT)} WORK must use numbered ### Step 01: ... guides")


def check_phase_handoff_gates() -> None:
    """Every state-producing phase must ensure/require its JSON handoff."""
    from target_spec import PHASE_HANDOFFS  # noqa: WPS433

    # step directory name -> PHASE_HANDOFFS key
    step_phases = {
        "01_repo_profile": "01_repo_profile",
        "02_repo_gate": "02_repo_gate",
        "03_environment": "03_environment",
        "04_simula_plan": "04_simula_plan",
        "05_task_design": "05_task_design",
        "06_task_review": "06_task_review",
        "07_verifier_generation": "07_verifier",
        "08_verifier_review": "08_verifier_review",
    }
    helpers = read(ROOT / "tests" / "helpers.sh")
    if "require_handoff" not in helpers:
        error("tests/helpers.sh must define require_handoff")

    for step_name, phase in step_phases.items():
        instruction = read(ROOT / "steps" / step_name / "instruction.md")
        test = read(ROOT / "steps" / step_name / "tests" / "test.sh")
        ensure = f"ensure-handoff {phase}"
        require = f"require-handoff {phase}"
        if ensure not in instruction:
            error(f"{step_name}/instruction.md must tell the agent to run {ensure}")
        if require not in instruction:
            error(f"{step_name}/instruction.md must self-check with {require}")
        if f"require_handoff {phase}" not in test:
            error(f"{step_name}/tests/test.sh must call require_handoff {phase}")
        handoff_path = PHASE_HANDOFFS[phase]["path"]
        if handoff_path not in instruction:
            error(f"{step_name}/instruction.md must mention {handoff_path}")

    # 08 packages: require upstream handoffs, no new state phase key
    pkg_instruction = read(ROOT / "steps" / "09_package" / "instruction.md")
    for phase in ("03_environment", "05_task_design", "07_verifier"):
        if f"require-handoff {phase}" not in pkg_instruction:
            error(f"09_package/instruction.md must require-handoff {phase}")
    if "ensure-handoff" not in read(ROOT / "environment" / "scripts" / "target_spec.py"):
        error("target_spec.py must implement ensure-handoff")
    if "PHASE_HANDOFFS" not in read(ROOT / "environment" / "scripts" / "target_spec.py"):
        error("target_spec.py must define PHASE_HANDOFFS")


def check_host_read_files_are_ascii() -> None:
    """Files Harbor reads on the host must survive a locale-encoded read.

    Harbor loads task.toml and every steps/*/instruction.md with
    Path.read_text() and no explicit encoding. On Windows that means the
    ANSI code page (GBK on zh-CN systems), so any non-ASCII byte raises
    UnicodeDecodeError, the step agent never starts, and the step fails with
    "missing file". Keep these files pure ASCII.
    """
    candidates = [ROOT / "task.toml"]
    candidates.extend(sorted((ROOT / "steps").glob("*/instruction.md")))
    for path in candidates:
        if not path.is_file():
            continue
        data = path.read_bytes()
        bad = [
            (index + 1, line.decode("utf-8", errors="replace").strip())
            for index, line in enumerate(data.splitlines())
            if any(byte > 0x7F for byte in line)
        ]
        if bad:
            first_line, preview = bad[0]
            error(
                f"{path.relative_to(ROOT)} contains non-ASCII text on "
                f"{len(bad)} line(s) (first at line {first_line}: "
                f"{ascii(preview[:60])}); Harbor reads it with the host locale "
                "encoding, which breaks on Windows/GBK"
            )


def check_helpers_and_scripts() -> None:
    helpers = ROOT / "tests" / "helpers.sh"
    validate = ROOT / "environment" / "scripts" / "validate_json.py"
    target_spec = ROOT / "environment" / "scripts" / "target_spec.py"
    state_integrity = ROOT / "environment" / "scripts" / "state_integrity.py"
    if not helpers.is_file():
        error("missing tests/helpers.sh")
    if not validate.is_file():
        error("missing environment/scripts/validate_json.py")
    else:
        try:
            ast.parse(read(validate))
        except SyntaxError as exc:
            error(f"validate_json.py syntax error: {exc}")
    if not target_spec.is_file():
        error("missing environment/scripts/target_spec.py")
    else:
        try:
            ast.parse(read(target_spec))
        except SyntaxError as exc:
            error(f"target_spec.py syntax error: {exc}")
    if not state_integrity.is_file():
        error("missing environment/scripts/state_integrity.py")
    else:
        try:
            ast.parse(read(state_integrity))
        except SyntaxError as exc:
            error(f"state_integrity.py syntax error: {exc}")


def main() -> int:
    check_dockerfile()
    check_sample_input()
    check_step01_taxonomy()
    check_step03_schema_alignment()
    check_step02_threshold()
    check_step04_simula_gate()
    check_step05_spec_gate()
    check_multi_candidate_gates()
    check_step09_package_gate()
    check_task_toml_steps()
    check_host_read_files_are_ascii()
    check_input_repo_readonly_warning()
    check_no_source_tree_seal()
    check_prompt_framework()
    check_phase_handoff_gates()
    check_helpers_and_scripts()

    if ERRORS:
        print("contract check FAILED")
        for item in ERRORS:
            print(f"  - {item}")
        return 1
    print("contract check passed")
    print(f"  steps: {len(list((ROOT / 'steps').iterdir()))}")
    print("  source input: present")
    print("  target_spec: valid")
    print("  dockerfile chmod: safe")
    print("  step 03 schema: aligned")
    print("  host-read files: ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
