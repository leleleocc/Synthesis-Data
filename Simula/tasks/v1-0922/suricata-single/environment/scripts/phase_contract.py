#!/usr/bin/env python3
"""Simula phase contracts: handoffs, closed vocab, and on-disk artifacts."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

ORACLE_TYPES = ("result", "state", "behavior")
DIFFICULTIES = ("easy", "medium", "hard", "ultra")
# Closed task mechanisms. scenario_angle stays a free kebab; mechanism is the
# batch-level diversity axis so a plan cannot collapse to one kind of work.
MECHANISMS = (
    "plant-fault",
    "recover-state",
    "reimplement",
    "configure-runtime",
    "build-matrix",
    "protocol-decode",
)

# Terminal-Bench taxonomy domains (docs/taxonomy.md). Closed set. Factory JSON
# stores kebab-case; packaged task.toml [metadata].category uses Title Case.
DOMAINS = (
    "science",
    "software",
    "ml",
    "operations",
    "security",
    "hardware",
    "media",
)
DOMAIN_CATEGORY = {
    "science": "Science",
    "software": "Software",
    "ml": "ML",
    "operations": "Operations",
    "security": "Security",
    "hardware": "Hardware",
    "media": "Media",
}

# Seed subdomains per domain (taxonomy.md). New kebab-case subdomains may be
# added under the best-fitting domain; they are not a closed set.
SEED_SUBDOMAINS: dict[str, tuple[str, ...]] = {
    "science": (
        "biology",
        "chemistry",
        "physics",
        "earth",
        "robotics",
        "math",
        "linguistics",
    ),
    "software": (
        "algorithms",
        "systems",
        "databases",
        "data-engineering",
        "frontend",
        "languages",
    ),
    "ml": ("training", "inference", "evaluation", "kernels"),
    "operations": (
        "finance",
        "logistics",
        "supply-chain",
        "claims",
        "compliance",
        "marketing",
    ),
    "security": ("cryptography", "reverse-engineering", "forensics", "appsec"),
    "hardware": ("cad", "rtl"),
    "media": ("music", "design"),
}
ALL_SEED_SUBDOMAINS = {item for values in SEED_SUBDOMAINS.values() for item in values}
SUBDOMAIN_TO_DOMAINS: dict[str, tuple[str, ...]] = {}
for _domain, _subs in SEED_SUBDOMAINS.items():
    for _sub in _subs:
        SUBDOMAIN_TO_DOMAINS[_sub] = SUBDOMAIN_TO_DOMAINS.get(_sub, ()) + (_domain,)

# Harbor [metadata].subcategory Title Case for seed names; unknown stay kebab.
SUBDOMAIN_CATEGORY = {
    "biology": "Biology",
    "chemistry": "Chemistry",
    "physics": "Physics",
    "earth": "Earth",
    "robotics": "Robotics",
    "math": "Math",
    "linguistics": "Linguistics",
    "algorithms": "Algorithms",
    "systems": "Systems",
    "databases": "Databases",
    "data-engineering": "Data engineering",
    "frontend": "Frontend",
    "languages": "Languages",
    "training": "Training",
    "inference": "Inference",
    "evaluation": "Evaluation",
    "kernels": "Kernels",
    "finance": "Finance",
    "logistics": "Logistics",
    "supply-chain": "Supply chain",
    "claims": "Claims",
    "compliance": "Compliance",
    "marketing": "Marketing",
    "cryptography": "Cryptography",
    "reverse-engineering": "Reverse engineering",
    "forensics": "Forensics",
    "appsec": "AppSec",
    "cad": "CAD",
    "rtl": "RTL",
    "music": "Music",
    "design": "Design",
}

# Closed tag vocabulary (superset of the factory demo list). Replaces task_types.
TAGS = (
    "3d-modeling",
    "ab-testing",
    "access-control",
    "agent",
    "airflow",
    "alerting",
    "algorithms",
    "analysis",
    "anomaly-detection",
    "ansible",
    "apache",
    "api",
    "apparmor",
    "application-security",
    "asan",
    "ast",
    "audio",
    "audio-processing",
    "audio-transcription",
    "authentication",
    "authorization",
    "automation",
    "aws",
    "azure",
    "backend",
    "backup",
    "bash",
    "bazel",
    "benchmarking",
    "binary-analysis",
    "bioinformatics",
    "bpf",
    "build",
    "build-system",
    "c",
    "caching",
    "cad",
    "capacity-planning",
    "certificate",
    "change-data-capture",
    "chaos-engineering",
    "checkpoint",
    "cheminformatics",
    "chemistry",
    "ci-cd",
    "claims",
    "cli",
    "climate",
    "clustering",
    "cmake",
    "code-generation",
    "compiler",
    "compliance",
    "computational-biology",
    "computational-linguistics",
    "computer-vision",
    "concurrency",
    "configuration",
    "consensus",
    "container",
    "container-security",
    "coq",
    "cpp",
    "cron",
    "cross-compilation",
    "cryptography",
    "crystallography",
    "css",
    "csv",
    "cuda",
    "cuda-kernel",
    "data-cleaning",
    "data-engineering",
    "data-extraction",
    "data-generation",
    "data-loader",
    "data-pipeline",
    "data-processing",
    "data-structures",
    "data-transformation",
    "data-validation",
    "database",
    "database-migration",
    "dataset",
    "dbt",
    "debugging",
    "deep-learning",
    "dependency-management",
    "deployment",
    "design",
    "digital-forensics",
    "digital-logic",
    "disassembly",
    "disaster-recovery",
    "distributed-systems",
    "distributed-training",
    "dns",
    "docker",
    "docker-compose",
    "documentation",
    "dynamics",
    "earth-science",
    "ebpf",
    "elasticsearch",
    "embedded",
    "embedding",
    "emulation",
    "encryption",
    "environmental-modeling",
    "etl",
    "evaluation",
    "event-loop",
    "event-sourcing",
    "exploit",
    "failover",
    "fdtd",
    "feature",
    "filesystem",
    "finance",
    "fine-tuning",
    "finite-difference",
    "finite-element",
    "forensics",
    "formal-verification",
    "fortran",
    "fpga",
    "frontend",
    "fuzzing",
    "gcp",
    "gdb",
    "genomics",
    "git",
    "github",
    "go",
    "gpu",
    "gpu-kernel",
    "grafana",
    "graphic-design",
    "graphql",
    "grpc",
    "hardware-design",
    "hashing",
    "hdl",
    "helm",
    "high-availability",
    "host-forensics",
    "html",
    "http",
    "huggingface",
    "hydrology",
    "image-processing",
    "implementation",
    "incident-response",
    "indexing",
    "inference",
    "integration",
    "interpreter",
    "inverse-design",
    "iptables",
    "isabelle",
    "java",
    "javascript",
    "jax",
    "json",
    "k8s",
    "kafka",
    "kernel",
    "key-management",
    "knowledge-graph",
    "kubernetes",
    "layout",
    "lean",
    "lexer",
    "linguistics",
    "linker",
    "linux",
    "llm",
    "llvm",
    "load-balancing",
    "load-testing",
    "log-analysis",
    "logging",
    "logistics",
    "lora",
    "lua",
    "lua-scripting",
    "machine-learning",
    "makefile",
    "malware-analysis",
    "marketing",
    "mathematics",
    "mcp",
    "mechanical-design",
    "memory-management",
    "meson",
    "message-queue",
    "microservices",
    "migration",
    "ml",
    "model-evaluation",
    "model-parallelism",
    "modeling",
    "molecular-dynamics",
    "molecular-modeling",
    "mongodb",
    "monitoring",
    "music",
    "music-theory",
    "mysql",
    "nats",
    "network-forensics",
    "network-security",
    "networking",
    "nginx",
    "ninja",
    "nlp",
    "numerical-simulation",
    "observability",
    "olap",
    "oltp",
    "onnx",
    "opentelemetry",
    "operations",
    "ops",
    "optimization",
    "owl",
    "package-management",
    "parallel-computing",
    "parametric-cad",
    "parquet",
    "parsing",
    "performance",
    "performance-tuning",
    "persistence",
    "physics",
    "postgresql",
    "process-management",
    "profiling",
    "program-analysis",
    "prometheus",
    "prompt-engineering",
    "property-based-testing",
    "proteomics",
    "protobuf",
    "protocol",
    "pubsub",
    "python",
    "pytorch",
    "qemu",
    "quantization",
    "query-optimization",
    "rabbitmq",
    "rag",
    "rdf",
    "reaction-analysis",
    "record-linkage",
    "redis",
    "refactoring",
    "reinforcement-learning",
    "release-engineering",
    "repair",
    "replication",
    "resource-management",
    "rest",
    "restore",
    "retrieval",
    "reverse-engineering",
    "robotics",
    "robotics-control",
    "rtl",
    "rust",
    "sanitizer",
    "schema",
    "search",
    "security-hardening",
    "selinux",
    "serialization",
    "serving",
    "shell",
    "simulation",
    "snapshot-testing",
    "spark",
    "sparql",
    "spectroscopy",
    "sql",
    "sqlite",
    "sre",
    "ssh",
    "ssl",
    "static-analysis",
    "storage",
    "strace",
    "structural-biology",
    "supply-chain",
    "systemd",
    "tcp",
    "tcpdump",
    "tensorflow",
    "terraform",
    "testing",
    "theorem-proving",
    "tls",
    "tokenization",
    "tool-calling",
    "tool-use",
    "training",
    "trajectory-optimization",
    "transaction",
    "transformers",
    "triton",
    "troubleshooting",
    "tsan",
    "typescript",
    "valgrind",
    "vector-db",
    "verilog",
    "vhdl",
    "video-processing",
    "virtualization",
    "visual-design",
    "visualization",
    "vulnerability",
    "vulnerability-analysis",
    "wasm",
    "web",
    "web-security",
    "websocket",
    "xml",
)

KEBAB_TOKEN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# Harbor-task preview axes. Target specs may still omit deployment_dimensions;
# phase 03 still writes every axis onto each slot so later phases never reread
# the spec. Unconstrained axes freeze to DEPLOYMENT_DEFAULTS (or the sealed
# environment's topology). Future kebab-case dimensions pass through.
DEPLOYMENT_ENUMS = {
    "container_mode": ("single", "multiple"),
    "step_mode": ("single", "multiple"),
    "verifier_mode": ("separate", "inline"),
    "gpu": ("none", "optional", "required"),
    "mcp": ("none", "optional", "required"),
}
DEPLOYMENT_DEFAULTS = {
    "container_mode": "single",
    "step_mode": "single",
    "verifier_mode": "inline",
    "gpu": "none",
    "mcp": "none",
}

HARD_CHECKS = (
    "source_present",
    "executable_logic",
    "build_or_runtime_path",
    "target_alignment",
    "license_known",
    "deployment_support",
)

# Difficulty bands in SOTA-agent minutes, stored as Terminal-Bench
# expert_time_estimate_min. A candidate's metadata estimate must fall inside
# its difficulty band. Ultra is 6h+; the 12h cap keeps Harbor timeouts finite.
DIFFICULTY_SOTA_MINUTES = {
    "easy": (1.0, 60.0),
    "medium": (60.0, 180.0),
    "hard": (180.0, 360.0),
    "ultra": (360.0, 720.0),
}
# Alias kept for older call sites / docs.
DIFFICULTY_EXPERT_MINUTES = DIFFICULTY_SOTA_MINUTES
# junior_time_estimate_min must be at least this multiple of the expert estimate.
JUNIOR_MULTIPLIER_MIN = 2.0

ORACLE_HINTS = {
    "result": "Compare output artifacts to a golden file, reference calculation, or invariant.",
    "state": "Check filesystem, process, port, or service predicates after the agent finishes.",
    "behavior": "Probe the program or service with inputs and check responses; not a single golden file.",
}

REVIEW_CHECK_OUTCOMES = ("pass", "fail", "not_applicable")
ADVISORY_REVIEW_CRITERIA = {"difficult", "essential_difficulty"}

# Terminal-Bench implementation-rubric criteria that apply to a verifier
# (same names as docs/prompts/task-implementation.toml).
VERIFIER_CHECK_KEYS = (
    "verifiable",
    "test_instruction_alignment",
    "functional_verification",
    "anti_cheat_robustness",
    "outcome_verified",
    "binary_reward",
    "do_not_modify_enforced",
    "deterministic_reproducible",
)

CANDIDATE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SCENARIO_ANGLES = (
    "migration",
    "incident-cleanup",
    "onboarding",
    "audit",
    "integration",
    "reproduction",
)
SIMULA_VOCAB_KEYS = ("tags", "domains", "subdomains", "languages", "oracle_types")
SIMULA_LOCAL_DIFF_KEYS = (
    "mechanism",
    "scenario_angle",
    "output_shape",
    "primary_input",
    "primary_entrypoint",
)
# Hard/ultra instructions may state outcomes, not the repair recipe.
INSTRUCTION_RECIPE_LEAKS = (
    re.compile(r"\bthe bug is\b", re.I),
    re.compile(r"\bthe defect (?:is|lives|was planted)\b", re.I),
    re.compile(r"\bfix the (?:bug|regression|fault) in\b", re.I),
    re.compile(r"\bplanted (?:a )?(?:bug|fault|regression)\b", re.I),
    re.compile(r"\bthe overlay (?:introduces|plants|injects)\b", re.I),
    re.compile(r"\bthe (?:copied|candidate) environment (?:introduces|plants|injects)\b", re.I),
    re.compile(r"\bbroken in [A-Za-z0-9_./-]+\.[A-Za-z0-9]+\b", re.I),
    re.compile(r"\breimplement (?:the )?(?:function|file|routine)\b", re.I),
    re.compile(r"\bcopy (?:from|the implementation in)\b", re.I),
    re.compile(r"\breference implementation (?:is|at|in)\b", re.I),
    re.compile(r"\bthe (?:faulty|buggy) (?:file|function) is\b", re.I),
    re.compile(r"\blook at (?:src|file|function) [A-Za-z0-9_./-]+", re.I),
)
_FILE_ONLY_COMPLEXITY = re.compile(
    r"^(?:also |additionally )?(?:add|write|emit|produce|include)\b.{0,60}"
    r"\.(json|txt|log|csv|md|out|bin)\s*$",
    re.I,
)
_FAIL_FN_BODY = re.compile(r"\bfail\s*\(\s*\)\s*\{([^}]{0,1200})\}", re.S)
SINGULAR_VOCAB_KEYS = (
    "task_type",
    "task_types",
    "domain",
    "language",
    "oracle_type",
    "tag",
    "subdomain",
)


DIFFICULTY_HINTS = {
    "easy": (
        "SOTA agent finishes in at most 1h. One or two tools, one output "
        "artifact, at most one non-obvious data quirk or flag."
    ),
    "medium": (
        "SOTA agent 1-3h. 2+ tools or a compatible source change, several "
        "outputs or edge cases, at least one requirement that needs reading "
        "docs/source to get right."
    ),
    "hard": (
        "SOTA agent 3-6h. Sparse docs, cross-component behavior, repair plus "
        "regression, or a hidden invariant; wrong shortcuts look plausible."
    ),
    "ultra": (
        "SOTA agent 6h or more (estimate 6-12h). Compound: two or more "
        "interacting hard parts, not a long linear checklist."
    ),
}


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_lower_token(value: Any) -> bool:
    return isinstance(value, str) and value == value.lower() and bool(value.strip())


def _string_list(value: Any, label: str, allowed: tuple[str, ...] | None = None) -> list[str]:
    """Non-empty list of unique tokens; optional closed vocabulary."""
    if not isinstance(value, list) or not value:
        return [f"{label} must be a non-empty list"]
    errors: list[str] = []
    seen: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            errors.append(f"{label} must be a list of strings, not objects")
            break
        if allowed is None:
            if not _is_lower_token(item):
                errors.append(f"{label} entries must be lowercase tokens; got {item!r}")
                continue
        elif item not in allowed:
            errors.append(f"{label} not in vocabulary: {item!r}")
            continue
        if item in seen:
            errors.append(f"{label} must not contain duplicates ({item!r})")
        else:
            seen.add(item)
    return errors


def _subset_of(value: Any, parent: list[Any], label: str, min_len: int = 1) -> list[str]:
    """Non-empty unique list; every item must appear in parent; at least min_len items."""
    if not isinstance(value, list) or not value:
        return [f"{label} must be a non-empty list"]
    errors: list[str] = []
    seen: list[Any] = []
    parent_set = set(parent)
    for item in value:
        if item not in parent_set:
            errors.append(f"{label} contains {item!r} which is not in the target list")
        elif item in seen:
            errors.append(f"{label} must not contain duplicates ({item!r})")
        else:
            seen.append(item)
    need = min(max(min_len, 1), len(parent) if parent else 1)
    if len(seen) < need:
        errors.append(f"{label} must contain at least {need} values from the target list")
    return errors


def _check_deployment_dimensions(value: Any, label: str) -> list[str]:
    """Validate an optional target list of deployment-shape choices."""
    if value is None:
        return []
    if not isinstance(value, dict):
        return [f"{label} must be an object"]
    errors: list[str] = []
    for key, choices in value.items():
        if not isinstance(key, str) or (
            key not in DEPLOYMENT_ENUMS and not KEBAB_TOKEN.fullmatch(key)
        ):
            errors.append(f"{label} keys must be known dimensions or lowercase kebab-case: {key!r}")
            continue
        if not isinstance(choices, list) or not choices:
            errors.append(f"{label}.{key} must be a non-empty list")
            continue
        if len(set(choices)) != len(choices) or any(
            not isinstance(item, str) or not item.strip()
            for item in choices
        ):
            errors.append(f"{label}.{key} must contain unique non-empty strings")
        allowed = DEPLOYMENT_ENUMS.get(key)
        if allowed:
            bad = [item for item in choices if item not in allowed]
            if bad:
                errors.append(f"{label}.{key} not in vocabulary: {bad}")
    return errors


def _deployment_defaults(env_state: dict[str, Any] | None = None) -> dict[str, str]:
    """Harbor preview defaults. Topology follows the sealed base when present."""
    defaults = dict(DEPLOYMENT_DEFAULTS)
    if not isinstance(env_state, dict):
        return defaults
    if env_state.get("deployment_mode") == "compose":
        defaults["container_mode"] = "multiple"
    resources = env_state.get("resources")
    if isinstance(resources, dict):
        gpus = _resource_value(resources, "gpus")
        if gpus is not None and gpus > 0:
            defaults["gpu"] = "required"
    return defaults


def _check_slot_deployment_preview(
    spec: dict[str, Any],
    value: Any,
    label: str,
    env_state: dict[str, Any] | None = None,
) -> list[str]:
    """Every slot is a Harbor-task preview: all five dimensions are required."""
    if not isinstance(value, dict):
        return [
            f"{label} must be an object with {list(DEPLOYMENT_ENUMS)} "
            "(the slot is the post-03 Harbor preview)"
        ]
    errors: list[str] = []
    target_dims = spec["target"].get("deployment_dimensions")
    if not isinstance(target_dims, dict):
        target_dims = {}
    defaults = _deployment_defaults(env_state)
    for key, allowed in DEPLOYMENT_ENUMS.items():
        selected = value.get(key)
        if selected not in allowed:
            errors.append(f"{label}.{key} must be one of {list(allowed)}; got {selected!r}")
            continue
        requested = target_dims.get(key)
        if isinstance(requested, list):
            if selected not in requested:
                errors.append(f"{label}.{key} must select one of target {requested!r}")
        elif selected != defaults[key]:
            errors.append(
                f"{label}.{key} must be {defaults[key]!r} when the target leaves it unconstrained"
            )
    missing = [key for key in DEPLOYMENT_ENUMS if key not in value]
    if missing:
        errors.append(f"{label} missing required Harbor preview keys: {missing}")
    for key, selected in value.items():
        if key in DEPLOYMENT_ENUMS:
            continue
        if not isinstance(key, str) or not KEBAB_TOKEN.fullmatch(key):
            errors.append(f"{label} keys must be known dimensions or lowercase kebab-case: {key!r}")
            continue
        requested = target_dims.get(key)
        if isinstance(requested, list):
            if not isinstance(selected, str) or selected not in requested:
                errors.append(f"{label}.{key} must select one of target {requested!r}")
        elif key not in target_dims:
            errors.append(f"{label}.{key} is not declared by target.deployment_dimensions")
    missing_target = sorted(set(target_dims) - set(value))
    if missing_target:
        errors.append(f"{label} is missing target dimensions: {missing_target}")
    if env_state and value.get("container_mode") in DEPLOYMENT_ENUMS["container_mode"]:
        mode = env_state.get("deployment_mode")
        selected = value.get("container_mode")
        if mode == "compose" and selected != "multiple":
            errors.append(f"{label}.container_mode must be multiple when the sealed base is compose")
        if mode == "single" and selected != "single":
            errors.append(f"{label}.container_mode must be single when the sealed base is single")
    return errors


def simula_mechanism_min(n: int) -> int:
    """A batch needs distinct mechanisms so it cannot collapse to one task kind."""
    if n <= 1:
        return 1
    return min(n, 3)


def _allowed_mechanisms(spec: dict[str, Any]) -> tuple[str, ...]:
    requested = spec.get("target", {}).get("mechanisms") if isinstance(spec.get("target"), dict) else None
    if isinstance(requested, list) and requested:
        return tuple(item for item in requested if item in MECHANISMS)
    return MECHANISMS


def _check_deployment_coverage(spec: dict[str, Any], slots: list[Any]) -> list[str]:
    """Slot projections must cover every requested deployment value."""
    target_dims = spec["target"].get("deployment_dimensions")
    if not isinstance(target_dims, dict):
        return []
    errors: list[str] = []
    for key, requested in target_dims.items():
        if not isinstance(requested, list):
            continue
        seen: set[str] = set()
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            projection = slot.get("deployment_dimensions")
            selected = projection.get(key) if isinstance(projection, dict) else None
            if isinstance(selected, str):
                seen.add(selected)
        missing = [item for item in requested if item not in seen]
        if missing:
            errors.append(
                f"union of slot deployment_dimensions.{key} must cover "
                f"target.deployment_dimensions.{key}; missing {missing}"
            )
    return errors


def _profile_deployment_support_errors(spec: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    """Phase 01 must evidence requested deployment dimensions or reject the repo."""
    target = spec.get("target") if isinstance(spec.get("target"), dict) else {}
    dims = target.get("deployment_dimensions")
    support = profile.get("deployment_support")
    checks = profile.get("hard_checks") if isinstance(profile.get("hard_checks"), dict) else {}
    errors: list[str] = []
    if not isinstance(dims, dict):
        if support not in (None, {}):
            errors.append(
                "profile.deployment_support is only used when target.deployment_dimensions is present"
            )
        if checks.get("deployment_support") is False:
            errors.append(
                "hard_checks.deployment_support must be true when target.deployment_dimensions is absent"
            )
        return errors
    if not isinstance(support, dict):
        errors.append("profile.deployment_support must evidence target.deployment_dimensions")
        return errors
    for key, requested in dims.items():
        entry = support.get(key)
        if not isinstance(entry, dict):
            errors.append(f"profile.deployment_support.{key} must be an object with values and evidence")
            continue
        values = entry.get("values")
        evidence = entry.get("evidence")
        if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item.strip() for item in values):
            errors.append(f"profile.deployment_support.{key}.values must be a non-empty list of strings")
            values = []
        if not isinstance(evidence, list) or not evidence or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            errors.append(f"profile.deployment_support.{key}.evidence must be a non-empty list of paths")
        if checks.get("deployment_support") is True and isinstance(requested, list):
            missing = [item for item in requested if item not in values]
            if missing:
                errors.append(
                    f"hard_checks.deployment_support requires {key} values {requested}; missing {missing}"
                )
    extra = sorted(set(support) - set(dims))
    if extra:
        errors.append(f"profile.deployment_support has undeclared dimensions: {extra}")
    return errors


INSTRUCTION_HEADING_ATX = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+\S")
INSTRUCTION_HEADING_SETX = re.compile(r"(?m)^[^\n]+\n[ \t]*[=-]{3,}[ \t]*$")
INSTRUCTION_RELATIVE_PATH = re.compile(
    r"(?i)(?<![\w./-])(?:\.\./|\./|(?:src|app|data|workspace|opt|tmp|var|home)/)[A-Za-z0-9_./-]+"
)
INSTRUCTION_TEST_LEAK = re.compile(
    r"(?i)\b(?:tests/|solution/|/tests/|/solution/|reward\.txt|test\.sh|solve\.sh)\b"
)
INSTRUCTION_SUFFIX = re.compile(
    r"(?s)\nYou have \d+(?:\.\d+)? seconds to complete this task\. "
    r"Do not cheat by using online solutions or hints specific to this task\.\s*$"
)
VERIFIER_FORM_MARKERS = {
    "bash": re.compile(r"(?m)^#!/usr/bin/env bash|^#!/bin/bash"),
    "python": re.compile(r"(?m)^#!/usr/bin/env python|^#!/usr/bin/python|\bpython3?\b"),
    "pytest": re.compile(r"\bpytest\b"),
}


def _instruction_without_fences(text: str) -> str:
    return re.sub(r"(?ms)^```.*?^```[ \t]*\n?", "\n", text)


def _instruction_tb_quality_errors(path: Path, candidate_id: str) -> list[str]:
    """Positive Terminal-Bench instruction rules, not the later adversarial fixtures."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    errors: list[str] = []
    visible = _instruction_without_fences(text)
    if INSTRUCTION_HEADING_ATX.search(visible) or INSTRUCTION_HEADING_SETX.search(visible):
        errors.append(
            f"candidate {candidate_id!r} instruction.md must not use Markdown headings "
            "(Terminal-Bench check-instruction-headings)"
        )
    if INSTRUCTION_TEST_LEAK.search(visible):
        errors.append(
            f"candidate {candidate_id!r} instruction.md must not mention tests/, solution/, "
            "test.sh, solve.sh, or reward.txt"
        )
    if INSTRUCTION_RELATIVE_PATH.search(visible):
        errors.append(
            f"candidate {candidate_id!r} instruction.md must use absolute paths "
            "(Terminal-Bench check-task-absolute-path)"
        )
    if not INSTRUCTION_SUFFIX.search(text):
        errors.append(
            f"candidate {candidate_id!r} instruction.md must end with the Terminal-Bench "
            "timeout/anti-cheat suffix as its own paragraph"
        )
    return errors


def _instruction_recipe_errors(path: Path, difficulty: Any, candidate_id: str) -> list[str]:
    """Hard/ultra instructions may state outcomes, not the repair locus or recipe."""
    if difficulty not in ("hard", "ultra") or not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for pattern in INSTRUCTION_RECIPE_LEAKS:
        if pattern.search(text):
            return [
                f"candidate {candidate_id!r} instruction names a defect site, planted "
                "fault, or reference implementation; hard/ultra tasks state observable "
                "outcomes only"
            ]
    return []


COMPLEXITY_AXES = (
    "coupling",
    "long-horizon",
    "complex-environment",
    "compound-task",
    "cyclic-dependency",
    "false-shortcut",
    "live-constraint",
    "evidence-ambiguity",
)
COMPLEXITY_AXIS_MIN = 3
COMPLEXITY_AXIS_MAX = 4


def _complexity_delta_errors(sid: str, delta: Any, *, hard: bool) -> list[str]:
    """complexity_delta is a list of {axis, text}; hard/ultra slots carry 3 or 4 axes."""
    if isinstance(delta, str):
        return [
            f"slot {sid!r} complexity_delta must be a list of "
            "{\"axis\": <kebab>, \"text\": <non-empty>} items, not a string"
        ]
    if not isinstance(delta, list) or not delta:
        return [f"slot {sid!r} complexity_delta must be a non-empty list"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(delta):
        label = f"slot {sid!r} complexity_delta[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object with \"axis\" and \"text\"")
            continue
        axis = item.get("axis")
        text = item.get("text")
        if axis not in COMPLEXITY_AXES:
            errors.append(
                f"{label} axis must be one of {list(COMPLEXITY_AXES)}; got {axis!r}"
            )
        elif axis in seen:
            errors.append(f"slot {sid!r} complexity_delta repeats axis {axis!r}")
        else:
            seen.add(axis)
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label} text must be a non-empty string")
        elif _FILE_ONLY_COMPLEXITY.match(text.strip()):
            errors.append(
                f"{label} must add an interacting constraint, not another output file"
            )
    if hard and not errors and not COMPLEXITY_AXIS_MIN <= len(seen) <= COMPLEXITY_AXIS_MAX:
        errors.append(
            f"slot {sid!r} complexity_delta must carry {COMPLEXITY_AXIS_MIN} to "
            f"{COMPLEXITY_AXIS_MAX} axes for hard/ultra; got {len(seen)}"
        )
    if hard and not errors and "coupling" not in seen:
        errors.append(
            f"slot {sid!r} complexity_delta must include the coupling axis; "
            "every candidate couples two constraints"
        )
    return errors


def _verifier_fail_logs_errors(cid: Any, tests_dir: Path) -> list[str]:
    script = tests_dir / "test.sh"
    if not script.is_file():
        return []
    try:
        text = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for match in _FAIL_FN_BODY.finditer(text):
        body = match.group(1)
        if not re.search(r"\b(echo|printf|cat|tee|logger)\b", body):
            return [
                f"{cid}: fail() must print a reason; silent counters hide verifier failures"
            ]
    return []


def _verifier_fixture_errors(
    cid: Any, tests_dir: Path, source: str, shared_tests_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    for name in ("goldens", "fixtures"):
        if not re.search(rf"(?:^|[\s\"'/]){name}(?:/|['\"]|$)", source):
            continue
        roots = [tests_dir] + ([shared_tests_dir] if shared_tests_dir is not None else [])
        files = [path for root in roots for path in (root / name).rglob("*") if path.is_file()]
        if not files:
            errors.append(
                f"{cid}: test.sh references {name}/ but tests/{name} is missing or empty"
            )
    return errors


def _check_subdomains(value: Any, allowed_domains: list[Any], label: str) -> list[str]:
    """Non-empty unique kebab tokens. Seed names must sit under an allowed domain."""
    if not isinstance(value, list) or not value:
        return [f"{label} must be a non-empty list"]
    errors: list[str] = []
    seen: set[str] = set()
    domain_set = set(allowed_domains)
    for item in value:
        if not isinstance(item, str) or not KEBAB_TOKEN.fullmatch(item):
            errors.append(f"{label} entries must be lowercase kebab-case tokens; got {item!r}")
            continue
        if item in DOMAINS:
            errors.append(f"{label} {item!r} is a domain; use a subdomain")
            continue
        if item in seen:
            errors.append(f"{label} must not contain duplicates ({item!r})")
            continue
        seen.add(item)
        homes = SUBDOMAIN_TO_DOMAINS.get(item)
        if homes and domain_set and not any(home in domain_set for home in homes):
            errors.append(
                f"{label} {item!r} belongs to {list(homes)} which is outside {sorted(domain_set)}"
            )
    return errors


def _packaged_category(domain: str) -> str:
    return DOMAIN_CATEGORY.get(domain, domain)


def _packaged_subcategory(subdomain: str) -> str:
    return SUBDOMAIN_CATEGORY.get(subdomain, subdomain)


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["target_spec must be an object"]
    source = spec.get("source_repo")
    target = spec.get("target")
    generation = spec.get("generation")
    if not isinstance(source, dict):
        errors.append("source_repo is required")
    else:
        url = source.get("url")
        commit = source.get("commit")
        if not isinstance(url, str) or not url.strip():
            errors.append("source_repo.url is required")
        elif not re.match(r"^(?:https?|ssh|git)://|^git@", url.strip()):
            errors.append("source_repo.url must be an http(s), ssh, git, or scp-style URL")
        if not isinstance(commit, str) or not commit.strip() or commit.strip() == "unknown":
            errors.append("source_repo.commit must be a known commit id")
        if "path" in source:
            errors.append("source_repo.path was removed; provide only url and commit")
    if not isinstance(target, dict):
        errors.append("target is required")
        return errors
    if "task_types" in target:
        errors.append("target.task_types was removed; use target.tags")
    languages = target.get("languages")
    domains = target.get("domains")
    subdomains = target.get("subdomains")
    tags = target.get("tags")
    oracle_types = target.get("oracle_types")
    difficulty = target.get("difficulty")
    if not isinstance(languages, list) or not languages or not all(_is_lower_token(x) for x in languages):
        errors.append("target.languages must be a non-empty list of lowercase language names")
    errors.extend(_string_list(domains, "target.domains", DOMAINS))
    errors.extend(_check_subdomains(subdomains, domains if isinstance(domains, list) else [], "target.subdomains"))
    errors.extend(_string_list(tags, "target.tags", TAGS))
    if not isinstance(oracle_types, list) or not oracle_types:
        errors.append("target.oracle_types must be a non-empty list")
    else:
        bad = [x for x in oracle_types if x not in ORACLE_TYPES]
        if bad:
            errors.append(f"target.oracle_types not in vocabulary: {bad}")
    if difficulty not in DIFFICULTIES:
        errors.append("target.difficulty must be easy, medium, hard, or ultra")
    mechanisms = target.get("mechanisms")
    if mechanisms is not None:
        errors.extend(_string_list(mechanisms, "target.mechanisms", MECHANISMS))
        if (
            isinstance(mechanisms, list)
            and isinstance(generation, dict)
            and isinstance(generation.get("max_candidates"), int)
            and not isinstance(generation.get("max_candidates"), bool)
            and len(mechanisms) > generation["max_candidates"]
        ):
            errors.append("target.mechanisms cannot exceed generation.max_candidates")
    errors.extend(
        _check_deployment_dimensions(
            target.get("deployment_dimensions"), "target.deployment_dimensions"
        )
    )
    dims = target.get("deployment_dimensions")
    if isinstance(dims, dict) and isinstance(dims.get("container_mode"), list) and isinstance(dims.get("gpu"), list):
        if "multiple" in dims["container_mode"] and "required" in dims["gpu"]:
            errors.append("GPU-required compose batches are unsupported by the Daytona backend")
    if not isinstance(generation, dict):
        errors.append("generation is required")
        return errors
    if not isinstance(generation.get("allow_external_assets"), bool):
        errors.append("generation.allow_external_assets must be a boolean")
    max_c = generation.get("max_candidates")
    if not isinstance(max_c, int) or isinstance(max_c, bool) or max_c < 1:
        errors.append("generation.max_candidates must be a positive integer")
    if "max_query_candidates" in generation or "max_tasks" in generation:
        errors.append(
            "generation.max_query_candidates and generation.max_tasks were removed; "
            "use generation.max_candidates"
        )
    min_score = generation.get("min_repo_score")
    if not isinstance(min_score, (int, float)) or isinstance(min_score, bool) or not 0 <= float(min_score) <= 1:
        errors.append("generation.min_repo_score must be a number in [0, 1]")
    return errors


def min_repo_score(spec: dict[str, Any]) -> float:
    return float(spec["generation"]["min_repo_score"])


def candidate_budget(spec: dict[str, Any]) -> int:
    return int(spec["generation"]["max_candidates"])


def simula_local_k(n: int) -> int:
    return 2 if n >= 2 else 1


def simula_global_count(n: int) -> int:
    if n <= 0:
        return 1
    return max(1, n // simula_local_k(n))


def simula_complexified_count(n: int) -> int:
    """Every slot is compound: a single unconstrained mechanism is too easy."""
    return max(0, n)


def simula_local_counts(n: int) -> list[int]:
    """Per-node-set slot counts in global-list order, summing to n."""
    k = simula_local_k(n)
    g = simula_global_count(n)
    counts = [k] * g
    remainder = n - g * k
    for index in range(remainder):
        counts[index] += 1
    return counts


def _check_vocab_lists(
    spec: dict[str, Any],
    row: dict[str, Any],
    label: str,
) -> list[str]:
    """List-min-two unique subsets of target.* plus subdomain/domain pairing."""
    errors: list[str] = []
    target = spec["target"]
    tags = row.get("tags")
    domains = row.get("domains")
    subdomains = row.get("subdomains")
    languages = row.get("languages")
    oracles = row.get("oracle_types")
    parent_tags = target["tags"]
    parent_oracles = target["oracle_types"]
    parent_domains = target["domains"]
    parent_subdomains = target["subdomains"]
    parent_languages = target["languages"]
    errors.extend(
        _subset_of(tags, parent_tags, f"{label} tags", min_len=2 if len(parent_tags) >= 2 else 1)
    )
    errors.extend(
        _subset_of(
            domains,
            parent_domains,
            f"{label} domains",
            min_len=2 if len(parent_domains) >= 2 else 1,
        )
    )
    errors.extend(
        _subset_of(
            subdomains,
            parent_subdomains,
            f"{label} subdomains",
            min_len=2 if len(parent_subdomains) >= 2 else 1,
        )
    )
    errors.extend(
        _check_subdomains(
            subdomains,
            domains if isinstance(domains, list) else [],
            f"{label} subdomains",
        )
    )
    errors.extend(
        _subset_of(
            languages,
            parent_languages,
            f"{label} languages",
            min_len=2 if len(parent_languages) >= 2 else 1,
        )
    )
    errors.extend(
        _subset_of(
            oracles,
            parent_oracles,
            f"{label} oracle_types",
            min_len=2 if len(parent_oracles) >= 2 else 1,
        )
    )
    return errors


def check_simula_plan(
    spec: dict[str, Any],
    plan: dict[str, Any],
    env_state: dict[str, Any] | None = None,
) -> list[str]:
    """Phase 03: Global / Local / Complexity slots; this plan is the post-03 spec."""
    errors: list[str] = []
    budget = candidate_budget(spec)
    difficulty = plan.get("difficulty")
    if difficulty != spec["target"].get("difficulty"):
        errors.append(
            f"plan.difficulty must equal target.difficulty {spec['target'].get('difficulty')!r}"
        )
    global_rows = plan.get("global")
    slots = plan.get("slots")
    if not isinstance(global_rows, list) or not global_rows:
        errors.append("plan.global must be a non-empty list")
        global_rows = global_rows if isinstance(global_rows, list) else []
    if not isinstance(slots, list):
        errors.append("plan.slots must be a list")
        slots = []
    if len(slots) != budget:
        errors.append(f"plan.slots must have exactly {budget} entries")

    expected_g = simula_global_count(budget)
    if len(global_rows) != expected_g:
        errors.append(
            f"plan.global must have exactly {expected_g} node-sets "
            f"(N={budget}, local_k={simula_local_k(budget)})"
        )

    if env_state is None:
        env_path = Path("/synthesis/state/02_environment.json")
        if env_path.is_file():
            try:
                loaded = load_json(env_path)
            except Exception:  # noqa: BLE001
                env_state = None
            else:
                env_state = loaded if isinstance(loaded, dict) else None
    entrypoints = _entrypoint_argv0(env_state)

    global_by_id: dict[str, dict[str, Any]] = {}
    for row in global_rows:
        if not isinstance(row, dict):
            errors.append("plan.global entries must be objects")
            continue
        gid = row.get("id")
        if not isinstance(gid, str) or not CANDIDATE_ID_PATTERN.fullmatch(gid):
            errors.append(f"global {gid!r} id must match ^[A-Za-z0-9][A-Za-z0-9._-]*$")
            continue
        if gid in global_by_id:
            errors.append(f"plan.global ids must be unique (duplicate {gid!r})")
        global_by_id[gid] = row
        for singular in SINGULAR_VOCAB_KEYS:
            if singular in row:
                errors.append(
                    f"global {gid!r} uses {singular!r}; "
                    "use the list fields tags / domains / subdomains / languages / oracle_types"
                )
        errors.extend(_check_vocab_lists(spec, row, f"global {gid!r}"))
        entry = row.get("primary_entrypoint")
        if not isinstance(entry, str) or not entry.strip() or " " in entry or "/" in entry:
            errors.append(
                f"global {gid!r} primary_entrypoint must be an argv0 name; got {entry!r}"
            )
        elif entrypoints and entry not in entrypoints:
            errors.append(
                f"global {gid!r} primary_entrypoint {entry!r} is not a sealed-base entrypoint"
            )

    slot_ids: set[str] = set()
    slots_by_global: dict[str, list[dict[str, Any]]] = {gid: [] for gid in global_by_id}
    pair_seen: set[tuple[str, str]] = set()
    input_counts: dict[str, int] = {}
    oracle_union: set[str] = set()
    mechanism_union: set[str] = set()
    complexified_n = 0
    allowed_mechanisms = _allowed_mechanisms(spec)
    for slot in slots:
        if not isinstance(slot, dict):
            errors.append("plan.slots entries must be objects")
            continue
        sid = slot.get("id")
        if not isinstance(sid, str) or not CANDIDATE_ID_PATTERN.fullmatch(sid):
            errors.append(f"slot {sid!r} id must match ^[A-Za-z0-9][A-Za-z0-9._-]*$")
            continue
        if sid in slot_ids:
            errors.append(f"plan.slots ids must be unique (duplicate {sid!r})")
        slot_ids.add(sid)
        for singular in SINGULAR_VOCAB_KEYS:
            if singular in slot:
                errors.append(
                    f"slot {sid!r} uses {singular!r}; vocabulary lives on plan.global"
                )
        gid = slot.get("global_id")
        if gid not in global_by_id:
            errors.append(f"slot {sid!r} global_id {gid!r} is not in plan.global")
        else:
            slots_by_global.setdefault(gid, []).append(slot)
            parent = global_by_id[gid]
            oracles = parent.get("oracle_types")
            if isinstance(oracles, list):
                oracle_union.update(item for item in oracles if isinstance(item, str))
        copied = [key for key in SIMULA_VOCAB_KEYS if key in slot]
        if copied:
            errors.append(
                f"slot {sid!r} must not copy vocabulary {copied}; those lists live on global {gid!r}"
            )
        if "difficulty" in slot:
            errors.append(f"slot {sid!r} must not copy difficulty; it lives on the plan")
        errors.extend(
            _check_slot_deployment_preview(
                spec,
                slot.get("deployment_dimensions"),
                f"slot {sid!r} deployment_dimensions",
                env_state=env_state,
            )
        )

        mechanism = slot.get("mechanism")
        if mechanism not in allowed_mechanisms:
            errors.append(
                f"slot {sid!r} mechanism must be one of {list(allowed_mechanisms)}; got {mechanism!r}"
            )
        elif isinstance(mechanism, str):
            mechanism_union.add(mechanism)

        angle = slot.get("scenario_angle")
        if not isinstance(angle, str) or not KEBAB_TOKEN.fullmatch(angle):
            errors.append(
                f"slot {sid!r} scenario_angle must be a lowercase kebab token; got {angle!r}"
            )
        shape = slot.get("output_shape")
        if not isinstance(shape, str) or not KEBAB_TOKEN.fullmatch(shape):
            errors.append(
                f"slot {sid!r} output_shape must be a non-empty kebab-case token; got {shape!r}"
            )
        primary_input = slot.get("primary_input")
        if primary_input is not None and (
            not isinstance(primary_input, str) or not primary_input.strip()
        ):
            errors.append(f"slot {sid!r} primary_input must be null or a non-empty path")
        elif isinstance(primary_input, str):
            input_counts[primary_input] = input_counts.get(primary_input, 0) + 1
        entry = slot.get("primary_entrypoint")
        if not isinstance(entry, str) or not entry.strip() or " " in entry or "/" in entry:
            errors.append(
                f"slot {sid!r} primary_entrypoint must be an argv0 name; got {entry!r}"
            )
        elif entrypoints and entry not in entrypoints:
            errors.append(
                f"slot {sid!r} primary_entrypoint {entry!r} is not a sealed-base entrypoint"
            )
        if isinstance(entry, str) and isinstance(shape, str):
            pair = (entry, shape)
            if pair in pair_seen:
                errors.append(
                    f"slot {sid!r} shares primary_entrypoint {entry!r} and output_shape "
                    f"{shape!r} with another slot"
                )
            pair_seen.add(pair)

        flagged = slot.get("complexified")
        if flagged is not True:
            errors.append(
                f"slot {sid!r} complexified must be true; every candidate couples two constraints"
            )
        else:
            complexified_n += 1
        delta = slot.get("complexity_delta")
        errors.extend(
            _complexity_delta_errors(sid, delta, hard=difficulty in ("hard", "ultra"))
        )

    for path, count in input_counts.items():
        if count > 2:
            errors.append(
                f"at most two slots may share primary_input {path!r} (got {count})"
            )

    expected_complex = simula_complexified_count(budget)
    if complexified_n != expected_complex:
        errors.append(
            f"plan.slots must complexify every candidate "
            f"(N={budget}); got {complexified_n}"
        )

    expected_counts = simula_local_counts(budget)
    ordered_ids = [row.get("id") for row in global_rows if isinstance(row, dict)]
    for gid, expected in zip(ordered_ids, expected_counts):
        if not isinstance(gid, str):
            continue
        got = len(slots_by_global.get(gid) or [])
        if got != expected:
            errors.append(
                f"global {gid!r} must have {expected} local slots; got {got}"
            )
    for gid, group in slots_by_global.items():
        if gid not in ordered_ids:
            continue
        for left_index, left in enumerate(group):
            for right in group[left_index + 1 :]:
                differ = sum(
                    1
                    for key in SIMULA_LOCAL_DIFF_KEYS
                    if left.get(key) != right.get(key)
                )
                if differ < 2:
                    errors.append(
                        f"slots {left.get('id')!r} and {right.get('id')!r} share global "
                        f"{gid!r} but differ in {differ} of {list(SIMULA_LOCAL_DIFF_KEYS)} "
                        "(need at least 2)"
                    )

    target_oracles = spec["target"]["oracle_types"]
    missing_oracles = [item for item in target_oracles if item not in oracle_union]
    if missing_oracles:
        errors.append(
            f"union of slot oracle_types must cover target.oracle_types; missing {missing_oracles}"
        )
    need_mechanisms = min(simula_mechanism_min(budget), len(allowed_mechanisms))
    if len(mechanism_union) < need_mechanisms:
        errors.append(
            f"plan.slots must use at least {need_mechanisms} distinct mechanisms "
            f"(N={budget}); got {sorted(mechanism_union)}"
        )
    requested_mechanisms = spec["target"].get("mechanisms")
    if isinstance(requested_mechanisms, list):
        missing_mechs = [item for item in requested_mechanisms if item not in mechanism_union]
        if missing_mechs:
            errors.append(
                f"union of slot mechanisms must cover target.mechanisms; missing {missing_mechs}"
            )
    errors.extend(_check_deployment_coverage(spec, slots))
    return errors


def check_profile(spec: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if "supported_task_types" in profile or "task_types" in profile:
        errors.append("profile.supported_task_types was removed; use profile.tags")
    errors.extend(_string_list(profile.get("languages"), "profile.languages"))
    errors.extend(_string_list(profile.get("domains"), "profile.domains", DOMAINS))
    errors.extend(
        _check_subdomains(
            profile.get("subdomains"),
            profile.get("domains") if isinstance(profile.get("domains"), list) else [],
            "profile.subdomains",
        )
    )
    errors.extend(_string_list(profile.get("tags"), "profile.tags", TAGS))
    return errors


def _target_profile_intersection(
    spec: dict[str, Any], profile: dict[str, Any]
) -> dict[str, list[str]]:
    """Requested target lists that the profile actually observed."""
    target = spec.get("target") if isinstance(spec.get("target"), dict) else {}
    out: dict[str, list[str]] = {}
    for key in ("languages", "domains", "subdomains", "tags"):
        target_values = [item for item in (target.get(key) or []) if isinstance(item, str)]
        profile_values = {item for item in (profile.get(key) or []) if isinstance(item, str)}
        out[key] = [item for item in target_values if item in profile_values]
    return out


def _profile_evidence_errors(profile: dict[str, Any]) -> list[str]:
    """Validate compact evidence fields used by the repository gate."""
    errors: list[str] = []
    evidence = profile.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("profile.evidence must be an object")
        evidence = {}
    else:
        for key in ("license_files", "build_files", "entrypoint_files"):
            value = evidence.get(key)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                errors.append(f"profile.evidence.{key} must be a list of strings")

    license_doc = profile.get("license")
    if not isinstance(license_doc, dict):
        errors.append("profile.license must be an object")
    else:
        known = license_doc.get("known")
        if known not in (True, False):
            errors.append("profile.license.known must be true or false")
        if "files" in license_doc:
            errors.append("profile.license.files was removed; use evidence.license_files")
        if known is True:
            files = evidence.get("license_files") if isinstance(evidence, dict) else None
            if not isinstance(files, list) or not files:
                errors.append(
                    "evidence.license_files must be non-empty when license.known is true"
                )

    executable = profile.get("executable")
    if not isinstance(executable, dict):
        errors.append("profile.executable must be an object")
    else:
        present = executable.get("present")
        if present not in (True, False):
            errors.append("profile.executable.present must be true or false")
        if "entrypoints" in executable:
            errors.append(
                "profile.executable.entrypoints was removed; use profile.entrypoints"
            )
        if present is True:
            entrypoints = profile.get("entrypoints")
            if not isinstance(entrypoints, list) or not entrypoints:
                errors.append(
                    "profile.entrypoints must be non-empty when executable.present is true"
                )
    return errors


def check_repo_profile_gate(spec: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    """Validate phase 01's combined repository profile and acceptance gate."""
    errors = check_profile(spec, profile)
    if "source_repo" in profile:
        errors.append("profile.source_repo was removed; checkout.head is the pin")
    if "target_alignment" in profile:
        errors.append(
            "profile.target_alignment was removed; hard_checks.target_alignment "
            "is the intersection of profile and target lists"
        )
    if "accepted" in profile:
        errors.append("profile.accepted was removed; use profile.decision")

    checkout = profile.get("checkout")
    expected_commit = (spec.get("source_repo") or {}).get("commit")
    checkout_ok = False
    if not isinstance(checkout, dict):
        errors.append("profile.checkout must be an object proving the pinned checkout")
    else:
        if checkout.get("verified") is not True:
            errors.append("profile.checkout.verified must be true")
        if checkout.get("head") != expected_commit:
            errors.append("profile.checkout.head must equal target_spec.source_repo.commit")
        checkout_ok = (
            checkout.get("verified") is True and checkout.get("head") == expected_commit
        )
    errors.extend(_profile_evidence_errors(profile))

    profile_entrypoints = profile.get("entrypoints")
    if not isinstance(profile_entrypoints, list):
        errors.append("profile.entrypoints must be a list")

    intersection = _target_profile_intersection(spec, profile)
    alignment_ok = all(intersection[key] for key in ("languages", "domains", "subdomains", "tags"))

    errors.extend(_profile_deployment_support_errors(spec, profile))
    checks = profile.get("hard_checks")
    errors.extend(check_filter(profile))
    executable = profile.get("executable")
    if isinstance(checks, dict):
        if checks.get("source_present") is True and not checkout_ok:
            errors.append("hard_checks.source_present requires a verified pinned checkout")
        if checks.get("executable_logic") is True and not (
            isinstance(executable, dict) and executable.get("present") is True
        ):
            errors.append("hard_checks.executable_logic requires executable.present=true")
        if checks.get("build_or_runtime_path") is True:
            evidence = profile.get("evidence")
            if not isinstance(evidence, dict) or not evidence.get("build_files"):
                errors.append(
                    "hard_checks.build_or_runtime_path requires evidence.build_files"
                )
        if checks.get("license_known") is True:
            license_doc = profile.get("license")
            if not isinstance(license_doc, dict) or license_doc.get("known") is not True:
                errors.append("hard_checks.license_known requires license.known=true")
        if checks.get("target_alignment") is True and not alignment_ok:
            errors.append(
                "hard_checks.target_alignment requires a non-empty intersection "
                "of profile and target languages, domains, subdomains, and tags"
            )
        if checks.get("target_alignment") is False and alignment_ok:
            errors.append(
                "hard_checks.target_alignment must be true when profile lists intersect the target"
            )

    errors.extend(check_score(spec, profile))
    decision = profile.get("decision")
    if decision not in ("accept", "reject"):
        errors.append("profile.decision must be accept or reject")
    else:
        checks_ok = isinstance(checks, dict) and all(
            checks.get(key) is True for key in HARD_CHECKS
        )
        threshold = min_repo_score(spec)
        scores = [
            profile.get(key)
            for key in ("repo_score", "buildability_score", "task_potential_score")
        ]
        scores_ok = all(
            isinstance(score, (int, float)) and not isinstance(score, bool) and score >= threshold
            for score in scores
        )
        expected_decision = "accept" if checks_ok and scores_ok else "reject"
        if decision != expected_decision:
            errors.append("profile.decision does not match hard checks and min_repo_score")
    blockers = profile.get("blockers")
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item.strip() for item in blockers
    ):
        errors.append("profile.blockers must be a list of strings")
    if decision == "accept" and isinstance(blockers, list) and blockers:
        errors.append("accepted profile.blockers must be empty")
    if decision == "reject" and isinstance(blockers, list) and not blockers:
        errors.append("rejected profile.blockers must name the failed check or score threshold")
    return errors


def check_filter(filter_doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = filter_doc.get("hard_checks")
    if not isinstance(checks, dict):
        return ["filter.hard_checks must be an object"]
    missing = [key for key in HARD_CHECKS if key not in checks]
    if missing:
        errors.append(f"filter.hard_checks missing {missing}")
    for key in HARD_CHECKS:
        value = checks.get(key)
        if value not in (True, False):
            errors.append(f"filter.hard_checks.{key} must be true or false")
    if "accepted" in filter_doc:
        errors.append("filter.accepted was removed; use decision on the profile gate")
    return errors


LOCAL_IMAGE_FROM = re.compile(
    r"^FROM\s+(?:--\S+\s+)*((?:synth-env|localhost)[:/]|[a-z0-9._-]*(?:env):[0-9]+)\b",
    re.I,
)


def _entrypoint_argv0(env_state: dict[str, Any] | None) -> set[str]:
    """Argv0 names from 03 entrypoints (full command lines allowed)."""
    names: set[str] = set()
    if not isinstance(env_state, dict):
        return names
    for item in env_state.get("entrypoints") or []:
        if not isinstance(item, str) or not item.strip():
            continue
        argv0 = item.strip().split()[0]
        names.add(Path(argv0).name)
    return names


_BINARY_ENV_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".woff", ".woff2", ".ttf", ".otf", ".so", ".a", ".o",
}


def _env_mentions_token(env_dir: Path, tool: str) -> bool:
    """True when a candidate environment text file mentions the argv0."""
    if not env_dir.is_dir() or not tool:
        return False
    token = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(tool)}(?![A-Za-z0-9_.-])")
    for path in env_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() in _BINARY_ENV_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if token.search(text):
            return True
    return False


def check_candidate_environment(
    candidate_id: str,
    env_dir: Path,
    env_state: dict[str, Any] | None = None,
) -> list[str]:
    """Per-candidate environment: a copy of the sealed base, then slot edits."""
    errors: list[str] = []
    cid = f"candidate {candidate_id!r}"
    env_dir = Path(env_dir)
    if not env_dir.is_dir():
        errors.append(f"{cid} missing environment directory {env_dir.as_posix()}")
        return errors
    mode = env_state.get("deployment_mode") if isinstance(env_state, dict) else None
    dockerfile = env_dir / "Dockerfile"
    compose = env_dir / "docker-compose.yaml"
    if not compose.is_file() and (env_dir / "docker-compose.yml").is_file():
        compose = env_dir / "docker-compose.yml"
    if mode == "compose":
        if not compose.is_file():
            errors.append(f"{cid} environment must copy the sealed compose file")
        if not dockerfile.is_file():
            errors.append(f"{cid} environment must copy the sealed Dockerfile")
    elif mode == "single":
        if not dockerfile.is_file():
            errors.append(f"{cid} environment must copy the sealed Dockerfile")
        if compose.exists():
            errors.append(f"{cid} single-container environment must not ship compose")
    elif not dockerfile.is_file() and not compose.is_file():
        errors.append(f"{cid} environment must contain Dockerfile or compose")
    for script in sorted(env_dir.glob("*.sh")):
        if script.is_file() and not _bash_syntax_ok(script):
            errors.append(f"{cid} {script.name} fails bash -n")
    return errors


def _slots_by_id(plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(plan, dict):
        return out
    for slot in plan.get("slots") or []:
        if isinstance(slot, dict) and isinstance(slot.get("id"), str):
            out[slot["id"]] = slot
    return out


def _globals_by_id(plan: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(plan, dict):
        return out
    for row in plan.get("global") or []:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            out[row["id"]] = row
    return out


def _plan_difficulty(plan: dict[str, Any] | None) -> str | None:
    if not isinstance(plan, dict):
        return None
    difficulty = plan.get("difficulty")
    return difficulty if difficulty in DIFFICULTIES else None


def _design_step_names(candidate: dict[str, Any], multiple: bool) -> tuple[list[str], list[str]]:
    label = f"candidate {candidate.get('id')!r}"
    if not multiple:
        return [], [f"{label} step_mode=single must not declare steps"] if "steps" in candidate else []
    steps = candidate.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        return [], [f"{label} step_mode=multiple requires at least two ordered steps in 04_task_design"]
    errors: list[str] = []
    names: list[str] = []
    seen: set[str] = set()
    invalid_chars = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
    for name in steps:
        if (
            not isinstance(name, str)
            or not CANDIDATE_ID_PATTERN.fullmatch(name)
            or name.endswith((".", " "))
            or len(name.encode("utf-8")) > 255
            or invalid_chars.search(name)
            or re.fullmatch(r"(?i)CON|PRN|AUX|NUL|(?:COM|LPT)[1-9¹²³]", name.split(".")[0].rstrip(" "))
        ):
            errors.append(f"{label} step name {name!r} must be a portable directory component")
        elif unicodedata.normalize("NFC", name).casefold() in seen:
            errors.append(f"{label} duplicate step name {name!r}")
        else:
            seen.add(unicodedata.normalize("NFC", name).casefold())
            names.append(name)
    return names, errors


def check_design(
    design: dict[str, Any],
    candidates_dir: Path | None = None,
    env_state: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> list[str]:
    """Phase 04: each candidate supplies its instructions and copied environment.

    Vocabulary, mechanism, difficulty, and deployment live on the sealed 03 plan.
    The design index records oracle tools and, for multiple steps, their order.
    """
    errors: list[str] = []
    candidates = design.get("candidates")
    if not isinstance(candidates, list):
        errors.append("design.candidates must be a list")
        candidates = []
    ids: set[str] = set()
    candidates_root = Path(candidates_dir) if candidates_dir is not None else Path("/synthesis/output/candidates")
    if env_state is None:
        for env_state_path in (
            Path("/synthesis/state/02_environment.json"),
        ):
            if env_state_path.is_file():
                try:
                    env_state = load_json(env_state_path)
                except Exception:  # noqa: BLE001
                    env_state = None
                else:
                    break
    if plan is None:
        plan_path = Path("/synthesis/state/03_simula_plan.json")
        if plan_path.is_file():
            try:
                loaded_plan = load_json(plan_path)
            except Exception:  # noqa: BLE001
                plan = None
            else:
                plan = loaded_plan if isinstance(loaded_plan, dict) else None
    slots_by_id = _slots_by_id(plan)
    difficulty = _plan_difficulty(plan)
    copied_keys = SIMULA_VOCAB_KEYS + (
        "mechanism",
        "difficulty",
        "deployment_dimensions",
        "scenario_angle",
        "output_shape",
        "primary_entrypoint",
        "primary_input",
        "complexified",
        "complexity_delta",
        "global_id",
    )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("design.candidates entries must be objects")
            continue
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
            errors.append(
                f"candidate {candidate_id!r} id must match "
                "^[A-Za-z0-9][A-Za-z0-9._-]*$"
            )
            continue
        if candidate_id in ids:
            errors.append("design.candidates ids must be unique")
        ids.add(candidate_id)
        slot = slots_by_id.get(candidate_id)
        if slots_by_id and slot is None:
            errors.append(
                f"candidate {candidate_id!r} is not a slot id from 03_simula_plan"
            )
        leaked = [key for key in copied_keys if key in candidate]
        if leaked:
            errors.append(
                f"candidate {candidate_id!r} must not copy slot fields {leaked}; "
                "join 03_simula_plan by id"
            )
        for singular in SINGULAR_VOCAB_KEYS:
            if singular in candidate:
                errors.append(
                    f"candidate {candidate_id!r} uses {singular!r}; vocabulary lives on the plan"
                )
        if "env_build" in candidate:
            errors.append(
                f"candidate {candidate_id!r} must not set env_build; "
                "phase 04 copies the sealed environment and edits the copy"
            )
        oracle_tools = candidate.get("oracle_tools", [])
        if not isinstance(oracle_tools, list):
            errors.append(f"candidate {candidate_id!r} oracle_tools must be a list")

        env_dir = candidates_root / candidate_id / "environment"
        errors.extend(check_candidate_environment(candidate_id, env_dir, env_state))
        if isinstance(oracle_tools, list):
            entrypoints = _entrypoint_argv0(env_state)
            for tool in oracle_tools:
                if not isinstance(tool, str) or not tool.strip() or "/" in tool or " " in tool:
                    continue
                if tool in entrypoints:
                    continue
                if not _env_mentions_token(env_dir, tool):
                    errors.append(
                        f"candidate {candidate_id!r} oracle_tool {tool!r} is not a sealed-base "
                        "entrypoint and is not present in the candidate environment"
                    )

        dimensions = slot.get("deployment_dimensions", {}) if isinstance(slot, dict) else {}
        if not isinstance(dimensions, dict):
            dimensions = {}
        multiple = dimensions.get("step_mode") == "multiple"
        step_names, step_errors = _design_step_names(candidate, multiple)
        errors.extend(step_errors)
        instruction_paths = (
            [Path("steps") / name / "instruction.md" for name in step_names]
            if multiple else [Path("instruction.md")]
        )
        for relative_path in instruction_paths:
            instruction_file = candidates_root / candidate_id / relative_path
            if not instruction_file.is_file() or not instruction_file.read_bytes().strip():
                errors.append(f"candidate {candidate_id!r} missing non-empty {relative_path}")
                continue
            label = f"{candidate_id}/{relative_path.parent}" if multiple else candidate_id
            errors.extend(
                _instruction_recipe_errors(
                    instruction_file,
                    difficulty,
                    label,
                )
            )
            errors.extend(_instruction_tb_quality_errors(instruction_file, label))

        # task.toml is intentionally owned by phase 05. Phase 04 only checks
        # the instruction and candidate environment.
    if slots_by_id:
        missing = sorted(set(slots_by_id) - ids)
        extra = sorted(ids - set(slots_by_id))
        if missing or extra:
            errors.append(
                "design.candidates ids must equal 03_simula_plan slot ids "
                f"(missing={missing}, extra={extra})"
            )
        elif len(candidates) != len(slots_by_id):
            errors.append(
                f"design.candidates must have exactly {len(slots_by_id)} entries"
            )
    elif not slots_by_id:
        errors.append("check-design requires sealed 03_simula_plan.json")
    return errors



def check_score(spec: dict[str, Any], score: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    threshold = min_repo_score(spec)
    decision = score.get("decision")
    if decision not in ("accept", "reject"):
        errors.append("score.decision must be accept or reject")
    numbers = []
    for key in ("repo_score", "buildability_score", "task_potential_score"):
        value = score.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 1:
            errors.append(f"score.{key} must be a number in [0, 1]")
        else:
            numbers.append(float(value))
    if decision == "accept" and numbers and any(value < threshold for value in numbers):
        errors.append(f"accept requires all scores >= {threshold}")
    if decision == "reject" and numbers and all(value >= threshold for value in numbers):
        # allow reject for non-score reasons; not an error
        pass
    return errors


NETWORK_MODES = ("public", "no-network", "allowlist")
BUILD_MODES = ("docker", "static")
BUILD_STATUSES = ("passed", "failed")
MCP_TRANSPORTS = ("sse", "streamable-http", "stdio")
HTTP_MCP_TRANSPORTS = ("sse", "streamable-http")

# Harbor task limits used by the synthesis contract.  A target can narrow
# these through the sealed environment handoff, but a candidate may never
# raise them.  Keeping the defaults here also makes local contract checks
# useful when only phase 04/05 artifacts are available.
HARBOR_RESOURCE_LIMITS = {
    "cpus": 4,
    "memory_mb": 8192,
    "storage_mb": 10240,
    "gpus": 1,
}


def _load_optional_json(paths: list[Path]) -> dict[str, Any] | None:
    for path in paths:
        if not path.is_file():
            continue
        try:
            value = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _canonical_phase_inputs(candidates_dir: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Find sealed environment and plan handoffs for post-03 checks.

    Phases 04+ join 03_simula_plan rather than re-reading target_spec.
    The Harbor container uses ``/synthesis``.  The repository fallback keeps
    the same command useful in CI without requiring callers to duplicate paths.
    """
    candidates_dir = Path(candidates_dir)
    output_root = candidates_dir.parent
    synthesis_root = output_root.parent
    state_root = Path("/synthesis/state")
    if synthesis_root.name == "output":
        state_root = synthesis_root.parent / "state"
    env = _load_optional_json([
        Path("/synthesis/state/02_environment.json"),
        state_root / "02_environment.json",
    ])
    plan = _load_optional_json([
        Path("/synthesis/state/03_simula_plan.json"),
        state_root / "03_simula_plan.json",
    ])
    return env, plan


def _resource_value(section: dict[str, Any], key: str) -> float | None:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _resource_limits(env_state: dict[str, Any] | None) -> dict[str, float]:
    limits = {key: float(value) for key, value in HARBOR_RESOURCE_LIMITS.items()}
    if not isinstance(env_state, dict):
        return limits
    for source_key in ("resources", "limits"):
        source = env_state.get(source_key)
        if not isinstance(source, dict):
            continue
        for key, default in limits.items():
            value = _resource_value(source, key)
            if value is not None and value >= 0:
                limits[key] = min(default, value)
    return limits


def _timeout_errors(cid: str, task_doc: dict[str, Any], multiple: bool) -> list[str]:
    """Fixed timeouts: single-step 7200/600, each multi-step 1800/300, build 600."""
    errors: list[str] = []
    agent_timeout, verifier_timeout = (1800, 300) if multiple else (7200, 600)

    def _exact(label: str, section: dict[str, Any] | None, key: str, expected: float) -> None:
        if not isinstance(section, dict) or key not in section:
            errors.append(f"{cid}: {label} must be {expected:g}")
            return
        value = section.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) != expected:
            errors.append(f"{cid}: {label} must be {expected:g}")

    _exact("[agent].timeout_sec", task_doc.get("agent") if isinstance(task_doc.get("agent"), dict) else {}, "timeout_sec", agent_timeout)
    _exact("[verifier].timeout_sec", task_doc.get("verifier") if isinstance(task_doc.get("verifier"), dict) else {}, "timeout_sec", verifier_timeout)
    env_doc = task_doc.get("environment") if isinstance(task_doc.get("environment"), dict) else {}
    _exact("[environment].build_timeout_sec", env_doc, "build_timeout_sec", 600)
    if multiple:
        steps = task_doc.get("steps") if isinstance(task_doc.get("steps"), list) else []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            name = step.get("name") or index
            _exact(f"[[steps]] {name!r} [steps.agent].timeout_sec", step.get("agent") if isinstance(step.get("agent"), dict) else {}, "timeout_sec", 1800)
            _exact(f"[[steps]] {name!r} [steps.verifier].timeout_sec", step.get("verifier") if isinstance(step.get("verifier"), dict) else {}, "timeout_sec", 300)
    return errors


def _network_policy(env_state: dict[str, Any] | None, phase: str) -> dict[str, Any] | None:
    if not isinstance(env_state, dict):
        return None
    network = env_state.get("network")
    if not isinstance(network, dict) or not isinstance(network.get(phase), dict):
        return None
    return network[phase]


def _dockerfile_logical_lines(text: str) -> list[str]:
    logical: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}".strip() if pending else line
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical.append(pending)
        pending = ""
    if pending:
        logical.append(pending)
    return logical


def source_pin(spec: dict[str, Any]) -> tuple[str, str] | None:
    """(url, commit) when the spec pins a clonable source, else None."""
    source = spec.get("source_repo") or {}
    url = source.get("url")
    commit = source.get("commit")
    if isinstance(url, str) and url.strip() and isinstance(commit, str) and commit.strip() and commit != "unknown":
        return url.strip(), commit.strip()
    return None


def check_dockerfile(text: str, context_dir: Path, spec: dict[str, Any]) -> list[str]:
    """Dockerfile rules shared by the synthesis environment and the packaged task.

    The build context is the directory holding the Dockerfile (Harbor builds
    environment/Dockerfile with environment/ as context).
    """
    import shlex

    errors: list[str] = []
    context_dir = Path(context_dir)
    lines = _dockerfile_logical_lines(text)
    if not any(line.upper().startswith("FROM ") for line in lines):
        errors.append("Dockerfile has no FROM")
    # A self-contained Dockerfile may install dependencies directly. A setup
    # script is optional in the minimal environment contract.
    pin = source_pin(spec)
    if pin:
        url, commit = pin
        if not any(line.upper().startswith("RUN ") and "git clone" in line for line in lines):
            errors.append(f"Dockerfile must obtain the source with git clone {url} (pinned commit)")
        if commit not in text:
            errors.append(f"Dockerfile must check out the pinned commit {commit}")
    else:
        if not (context_dir / "repository").is_dir():
            errors.append("source is not clonable (no url or unknown commit): vendor it under repository/ in the build context")
    for line in lines:
        if not line.upper().startswith("COPY "):
            continue
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            errors.append(f"Dockerfile COPY is not parseable: {exc}")
            continue
        if any(token.startswith("--from=") for token in tokens[1:]):
            continue
        sources = [token for token in tokens[1:] if not token.startswith("--")]
        if len(sources) < 2:
            errors.append(f"Dockerfile COPY needs a source and a destination: {line}")
            continue
        for source in sources[:-1]:
            if source.startswith("/") or ".." in Path(source).parts:
                errors.append(f"Dockerfile COPY source must be relative to the build context: {source}")
            elif not list(context_dir.glob(source)):
                errors.append(f"Dockerfile COPY source does not exist in the build context: {source}")
    return errors


def _smoke_is_stub(text: str) -> bool:
    body = re.sub(r"(?m)^\s*(#|//).*$", "", text)
    body = re.sub(r"^\s*#!.*$", "", body, flags=re.M).strip()
    return (not body) or body in {"exit 0", "exit 0;", "true", ":"}


def check_environment(spec: dict[str, Any], state: dict[str, Any], env_dir: Path) -> list[str]:
    """Sealed-base environment contract. Does not re-run docker build."""
    import shutil
    import subprocess

    errors: list[str] = []
    env_dir = Path(env_dir)
    asset_root = (env_dir / "assets").resolve()

    mode = state.get("deployment_mode")
    required_build_file = "Dockerfile" if mode == "single" else "docker-compose.yaml"
    if not (env_dir / required_build_file).is_file() and mode == "compose" and (env_dir / "docker-compose.yml").is_file():
        required_build_file = "docker-compose.yml"
    if not (env_dir / required_build_file).is_file():
        errors.append(f"missing {env_dir / required_build_file}")
    if state.get("asset_paths") and not (env_dir / "assets").is_dir():
        errors.append(f"asset_paths are declared but assets directory is missing: {env_dir / 'assets'}")

    if mode not in ("single", "compose"):
        errors.append("deployment_mode must be single or compose")
    source = state.get("source_repo")
    expected_source = spec.get("source_repo") if isinstance(spec.get("source_repo"), dict) else {}
    if source != expected_source:
        errors.append("environment.source_repo must match target_spec.source_repo")
    network = state.get("network")
    if not isinstance(network, dict):
        errors.append("network must contain environment, agent, and verifier policies")
        network = {}
    for phase in ("environment", "agent", "verifier"):
        policy = network.get(phase)
        if not isinstance(policy, dict):
            errors.append(f"network.{phase} must be an object")
            continue
        mode_value = policy.get("network_mode")
        if mode_value not in NETWORK_MODES:
            errors.append(f"network.{phase}.network_mode must be one of {list(NETWORK_MODES)}")
        hosts = policy.get("allowed_hosts", [])
        if not isinstance(hosts, list) or any(not isinstance(host, str) or not host.strip() for host in hosts):
            errors.append(f"network.{phase}.allowed_hosts must be a list of strings")
        if mode_value != "allowlist" and hosts:
            errors.append(f"network.{phase}.allowed_hosts must be empty unless network_mode=allowlist")
    if mode == "compose":
        for phase in ("environment", "agent", "verifier"):
            policy = network.get(phase) if isinstance(network.get(phase), dict) else {}
            if policy.get("network_mode") == "allowlist":
                errors.append("compose environments do not support allowlist network mode")
    services = state.get("services")
    if not isinstance(services, list) or not services:
        errors.append("services must be a non-empty list")
    else:
        for service in services:
            if not isinstance(service, dict) or not service.get("name"):
                errors.append("every service needs a name")
                break
        if mode == "compose" and not any(
            isinstance(service, dict) and service.get("name") == "main" for service in services
        ):
            errors.append("compose environments must declare a primary service named main")
    resources = state.get("resources")
    if not isinstance(resources, dict):
        errors.append("resources must declare cpus, memory_mb, storage_mb, and gpus")
    else:
        for key in ("cpus", "memory_mb", "storage_mb"):
            value = _resource_value(resources, key)
            required = float(HARBOR_RESOURCE_LIMITS[key])
            if value != required:
                errors.append(f"resources.{key} must be {required:g}")
        gpus = _resource_value(resources, "gpus")
        if gpus is None or gpus < 0 or gpus > HARBOR_RESOURCE_LIMITS["gpus"]:
            errors.append(f"resources.gpus must be a number in [0, {HARBOR_RESOURCE_LIMITS['gpus']:g}]")
        if mode == "compose" and (gpus or 0) > 0:
            errors.append("Daytona GPU allocation requires a single-container Dockerfile base")
    for phase in ("environment", "agent"):
        policy = network.get(phase) if isinstance(network.get(phase), dict) else {}
        if policy.get("network_mode") != "public":
            errors.append(f"network.{phase}.network_mode must be public")
    verifier_policy = network.get("verifier") if isinstance(network.get("verifier"), dict) else {}
    if verifier_policy.get("network_mode") not in ("public", "no-network"):
        errors.append("network.verifier.network_mode must be public or no-network")
    paths = state.get("paths")
    if not isinstance(paths, dict):
        errors.append("paths must be an object")
        paths = {}
    for key in ("workdir", "source_dir"):
        value = paths.get(key)
        if not isinstance(value, str) or not value.startswith("/"):
            errors.append(f"paths.{key} must be an absolute path")
    for key in ("data_dir", "results_dir"):
        value = paths.get(key)
        if value is not None and (not isinstance(value, str) or not value.startswith("/")):
            errors.append(f"paths.{key} must be null or an absolute path")
    asset_paths = state.get("asset_paths")
    if not isinstance(asset_paths, list):
        errors.append("asset_paths must be a list")
    else:
        for asset in asset_paths:
            path = Path(str(asset))
            try:
                path.resolve().relative_to(asset_root)
            except ValueError:
                errors.append(f"asset path must be under {asset_root}: {asset}")
                continue
            if not (path.is_file() or path.is_dir()):
                errors.append(f"asset path does not exist: {asset}")

    dockerfile = env_dir / "Dockerfile"
    compose_file = env_dir / "docker-compose.yaml"
    if not compose_file.is_file() and (env_dir / "docker-compose.yml").is_file():
        compose_file = env_dir / "docker-compose.yml"
    if mode == "compose":
        if not compose_file.is_file():
            errors.append("compose mode needs docker-compose.yaml or docker-compose.yml")
        else:
            compose_text = compose_file.read_text(encoding="utf-8", errors="replace")
            if "services:" not in compose_text:
                errors.append(f"{compose_file.name} has no services section")
            if not re.search(r"(?im)^\s+build\s*:", compose_text):
                errors.append(f"{compose_file.name} must build the pinned source image")
            if not dockerfile.is_file():
                errors.append("compose mode must ship environment/Dockerfile for the pinned source build")
    elif mode == "single" and compose_file.exists():
        errors.append("single mode must not ship a compose file")

    dockerfile_text = ""
    if dockerfile.is_file():
        dockerfile_text = dockerfile.read_text(encoding="utf-8", errors="replace")
        errors.extend(check_dockerfile(dockerfile_text, env_dir, spec))
        if (env_dir / "assets").is_dir() and not re.search(
            r"(?im)^COPY\s+assets(?:/|\s)", dockerfile_text
        ):
            errors.append("base Dockerfile must COPY assets/ when assets/ is present")

    bash = shutil.which("bash")
    if bash:
        for name in ("setup.sh", "smoke_test.sh"):
            script = env_dir / name
            if not script.is_file():
                continue
            result = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
            if result.returncode != 0:
                errors.append(f"{name} has a shell syntax error: {result.stderr.strip()}")

    smoke = env_dir / "smoke_test.sh"
    if smoke.is_file():
        smoke_text = smoke.read_text(encoding="utf-8", errors="replace")
        if _smoke_is_stub(smoke_text):
            errors.append("smoke_test.sh must not be a no-op stub (exit 0 / empty body)")
        for key in ("workdir", "source_dir", "data_dir", "results_dir"):
            value = (state.get("paths") or {}).get(key)
            if isinstance(value, str) and value and value not in smoke_text:
                errors.append(f"smoke_test.sh must probe {key} ({value})")
        entrypoints = state.get("entrypoints") if isinstance(state.get("entrypoints"), list) else []
        named = [str(item) for item in entrypoints if isinstance(item, str) and item.strip()]
        if named and not any(item in smoke_text for item in named):
            errors.append("smoke_test.sh must invoke at least one declared entrypoint")
    return errors


def check_environment_build(state: dict[str, Any]) -> list[str]:
    """Build/smoke report. Static mode cannot pass the environment gate."""
    errors: list[str] = []
    build = state.get("build")
    if not isinstance(build, dict):
        return ["build must be an object"]
    status = build.get("status")
    mode = build.get("mode")
    if status not in BUILD_STATUSES:
        errors.append("build.status must be passed or failed")
    if mode not in BUILD_MODES:
        errors.append("build.mode must be docker or static")
    for key in ("buildable", "smoke_test"):
        if build.get(key) not in (True, False):
            errors.append(f"build.{key} must be a boolean")
    failures = build.get("failures")
    if not isinstance(failures, list):
        errors.append("build.failures must be a list")
    seconds = build.get("build_seconds")
    if status == "passed":
        if build.get("buildable") is not True or build.get("smoke_test") is not True:
            errors.append("build.status=passed requires buildable and smoke_test true")
        if mode != "docker":
            errors.append("build.status=passed requires mode=docker; static is not proof the image builds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds < 0:
            errors.append("build.build_seconds must be a non-negative number when the docker build passed")
        if failures:
            errors.append("build.failures must be empty when status=passed")
    elif status == "failed":
        if not failures:
            errors.append("build.failures must name the failure when status=failed")
    return errors


def _bash_syntax_ok(script: Path) -> bool:
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if not bash or not script.is_file():
        return False
    try:
        return subprocess.run([bash, "-n", str(script)], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _is_executable(path: Path) -> bool:
    import os

    if os.name == "nt":
        return True
    return bool(path.stat().st_mode & 0o111)


_VERIFY_INSTALL_RE = re.compile(
    r"apt-get|\bapt\s+install\b|\byum\s+install\b|\bdnf\s+install\b|\bapk\s+add\b|"
    r"pip3?\s+install|\bpython3?\s+-m\s+pip\b|\buvx\b|\buv\s+pip\b|"
    r"curl\s+[^\n]*\|\s*(?:sh|bash)|wget\s+[^\n]*\|\s*(?:sh|bash)",
    re.I,
)
_VERIFY_PYTEST_RE = re.compile(r"\bpytest\b", re.I)


def _strip_shell_comments(text: str) -> str:
    """Remove shell comments while preserving quoted command text.

    A verifier is commonly a shell wrapper.  Scanning its raw source makes a
    documentation comment such as ``# apt-get install ...`` look like a
    runtime install.  This small lexer is deliberately conservative: it only
    treats ``#`` as a comment marker outside single/double quotes and after a
    non-escaped command boundary.
    """
    lines: list[str] = []
    for raw in text.splitlines(keepends=True):
        quote: str | None = None
        escaped = False
        kept: list[str] = []
        for char in raw:
            if escaped:
                kept.append(char)
                escaped = False
                continue
            if char == "\\" and quote != "'":
                kept.append(char)
                escaped = True
                continue
            if quote:
                kept.append(char)
                if char == quote:
                    quote = None
                continue
            if char in ("'", '"'):
                quote = char
                kept.append(char)
                continue
            # In shell, ``#`` starts a comment only at a command boundary;
            # parameter expansions such as ``${value#prefix}`` are code.
            previous = kept[-1] if kept else ""
            if char == "#" and (not previous or previous.isspace() or previous in ";|&()"):
                break
            kept.append(char)
        lines.append("".join(kept))
    return "".join(lines)


def _strip_python_comments(text: str) -> str:
    """Remove Python COMMENT tokens without changing strings or code."""
    import io
    import tokenize

    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        kept = [token for token in tokens if token.type != tokenize.COMMENT]
        return tokenize.untokenize(kept)
    except (IndentationError, SyntaxError, tokenize.TokenError):
        # Syntax is checked separately.  Keep the source when tokenization is
        # unavailable so this check does not hide a more useful diagnostic.
        return text


def _runtime_source(text: str, path: Path) -> str:
    if path.suffix.lower() == ".py":
        return _strip_python_comments(text)
    return _strip_shell_comments(text)


def _verifier_runtime_errors(cid: Any, tests_dir: Path, oracle_tools: list[str] | None = None) -> list[str]:
    """tests/test.sh must not install packages; bake pytest into the image instead.

    ``oracle_tools`` is accepted for call-site compatibility and ignored.
    """
    del oracle_tools
    errors: list[str] = []
    tests_dir = Path(tests_dir)
    if not tests_dir.is_dir():
        return errors
    for path in sorted(tests_dir.rglob("*")):
        if not path.is_file():
            continue
        # Only the verifier entry and other shell wrappers install tooling.
        # Python fixtures can mention "pip install" in comments without running it.
        if path.suffix.lower() not in {".sh", ".bash"} and path.name != "test.sh":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        source = _runtime_source(text, path)
        if _VERIFY_INSTALL_RE.search(source):
            errors.append(
                f"{cid}: {path.relative_to(tests_dir).as_posix()} must not install "
                "packages at verify time; bake pytest==9.1.1 and pytest-json-ctrf==0.5.2 "
                "into the image that runs the verifier"
            )
    return errors


def _oracle_tools_by_id(design: dict[str, Any] | None) -> dict[str, list[str] | None]:
    out: dict[str, list[str] | None] = {}
    if not isinstance(design, dict):
        return out
    for item in design.get("candidates") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            tools = item.get("oracle_tools")
            out[str(item["id"])] = tools if isinstance(tools, list) else None
    return out


def _load_design_state() -> dict[str, Any] | None:
    path = Path("/synthesis/state/04_task_design.json")
    if not path.is_file():
        return None
    try:
        doc = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _verifier_form(tests_dir: Path) -> str:
    """Classify a candidate verifier as bash, python, or pytest."""
    if not tests_dir.is_dir():
        return "bash"
    py_tests = [path for path in tests_dir.rglob("*.py") if path.is_file()]
    try:
        source = (tests_dir / "test.sh").read_text(encoding="utf-8", errors="replace")
    except OSError:
        source = ""
    if VERIFIER_FORM_MARKERS["pytest"].search(source) or any(
        path.name.startswith("test_") for path in py_tests
    ):
        return "pytest"
    if py_tests or VERIFIER_FORM_MARKERS["python"].search(source):
        return "python"
    return "bash"


def _verifier_form_diversity_errors(records: list[Any], candidates_dir: Path) -> list[str]:
    """A batch of 2+ verifiers must not collapse to one language/form."""
    forms: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        cid = record.get("candidate_id")
        dirs, _ = _task_verifier_dirs(Path(candidates_dir) / str(cid))
        forms.update(_verifier_form(path) for path in dirs)
    n = sum(1 for record in records if isinstance(record, dict))
    if n >= 2 and len(forms) < 2:
        return [
            "verifier language/form must not be monolithic; "
            f"need at least two of bash/python/pytest across the batch, got {sorted(forms)}"
        ]
    return []


def _task_verifier_dirs(
    task_dir: Path, task_doc: dict[str, Any] | None = None,
) -> tuple[list[Path], list[str]]:
    """Resolve Harbor's per-step verifier override and shared-tests fallback."""
    errors: list[str] = []
    if task_doc is None:
        task_doc = {}
        config = task_dir / "task.toml"
        if config.is_file():
            try:
                import tomllib
                task_doc = tomllib.loads(config.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                return [], [f"{task_dir.name}: task.toml does not parse: {exc}"]
    shared = task_dir / "tests"
    steps = task_doc.get("steps")
    if steps is None:
        dirs = [shared]
    elif not isinstance(steps, list) or not steps:
        return [], [f"{task_dir.name}: steps must be a non-empty array"]
    else:
        dirs = []
        names: set[str] = set()
        for step in steps:
            name = step.get("name") if isinstance(step, dict) else None
            if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name:
                errors.append(f"{task_dir.name}: step name must be one directory component")
                continue
            if name in names:
                errors.append(f"{task_dir.name}: duplicate step name {name!r}")
                continue
            names.add(name)
            step_dir = task_dir / "steps" / name
            instruction = step_dir / "instruction.md"
            if not instruction.is_file() or not instruction.read_bytes().strip():
                errors.append(f"{task_dir.name}: missing or empty steps/{name}/instruction.md")
            local = step_dir / "tests"
            verifier = step.get("verifier") if isinstance(step.get("verifier"), dict) else {}
            inherited = task_doc.get("verifier") if isinstance(task_doc.get("verifier"), dict) else {}
            inherited_mode = inherited.get("environment_mode") or (
                "separate" if inherited.get("environment") is not None else "shared"
            )
            mode = verifier.get("environment_mode") or (
                "separate" if verifier.get("environment") is not None else inherited_mode
            )
            tests = local if (local.is_dir() if mode == "separate" else (local / "test.sh").is_file()) else shared
            if tests not in dirs:
                dirs.append(tests)
    for tests in dirs:
        script = tests / "test.sh"
        if not script.is_file() or not script.read_bytes().strip():
            errors.append(f"{task_dir.name}: missing or empty {tests.relative_to(task_dir)}/test.sh")
    return dirs, errors


def _env_mentions_command(env_dir: Path, command: str) -> bool:
    """stdio MCP command must appear in the candidate environment copy."""
    token = Path(str(command)).name
    return bool(token) and (
        _env_mentions_token(env_dir, str(command)) or _env_mentions_token(env_dir, token)
    )


def _agent_network_mode(task_doc: dict[str, Any], env_state: dict[str, Any] | None) -> str | None:
    agent_doc = task_doc.get("agent") if isinstance(task_doc.get("agent"), dict) else {}
    mode = agent_doc.get("network_mode")
    if mode in NETWORK_MODES:
        return str(mode)
    policy = _network_policy(env_state, "agent") if env_state else None
    if isinstance(policy, dict) and policy.get("network_mode") in NETWORK_MODES:
        return str(policy.get("network_mode"))
    return None


def _check_mcp_servers(
    cid: str,
    servers: list[Any],
    env_dir: Path,
    agent_network_mode: str | None,
) -> list[str]:
    """Harbor MCPServerConfig transport fields, plus environment/network alignment."""
    errors: list[str] = []
    for index, server in enumerate(servers):
        label = f"{cid}: mcp_servers[{index}]"
        if not isinstance(server, dict):
            errors.append(f"{label} must be an object")
            continue
        name = server.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label} needs a name")
        transport = server.get("transport") or "sse"
        if transport not in MCP_TRANSPORTS:
            errors.append(f"{label}.transport must be one of {list(MCP_TRANSPORTS)}")
            continue
        if transport in HTTP_MCP_TRANSPORTS:
            url = server.get("url")
            if not isinstance(url, str) or not url.strip():
                errors.append(f"{label}: sse/streamable-http requires url")
            if agent_network_mode == "no-network":
                errors.append(
                    f"{label}: HTTP MCP is mute when agent network_mode=no-network; use stdio"
                )
        if transport == "stdio":
            command = server.get("command")
            if not isinstance(command, str) or not command.strip():
                errors.append(f"{label}: stdio requires command")
            elif not _env_mentions_command(env_dir, command):
                errors.append(
                    f"{label}: stdio command must appear in the candidate environment"
                )
    return errors


def _check_slot_task_preview(
    cid: str,
    slot: dict[str, Any],
    task_doc: dict[str, Any],
    candidates_dir: Path,
    env_state: dict[str, Any] | None = None,
) -> list[str]:
    """task.toml and tests layout must realize the slot Harbor preview."""
    errors: list[str] = []
    dims = slot.get("deployment_dimensions") if isinstance(slot.get("deployment_dimensions"), dict) else {}
    env_doc = task_doc.get("environment") if isinstance(task_doc.get("environment"), dict) else {}
    verifier = task_doc.get("verifier") if isinstance(task_doc.get("verifier"), dict) else {}
    cand_env = Path(candidates_dir) / cid / "environment"
    container_mode = dims.get("container_mode")
    if container_mode == "multiple":
        compose = cand_env / "docker-compose.yaml"
        compose_yml = cand_env / "docker-compose.yml"
        if not compose.is_file() and not compose_yml.is_file():
            errors.append(
                f"{cid}: container_mode=multiple requires compose in the candidate environment"
            )
    if container_mode == "single" and (
        (cand_env / "docker-compose.yaml").exists() or (cand_env / "docker-compose.yml").exists()
    ):
        errors.append(f"{cid}: single-container slot must not ship compose")
    if dims.get("step_mode") == "multiple" and (
        not isinstance(task_doc.get("steps"), list) or len(task_doc["steps"]) < 2
    ):
        errors.append(f"{cid}: step_mode=multiple requires at least two [[steps]] in task.toml")
    if dims.get("step_mode") == "single" and "steps" in task_doc:
        errors.append(f"{cid}: step_mode=single forbids [[steps]] in task.toml")
    if dims.get("verifier_mode") == "separate":
        if verifier.get("environment_mode") not in ("separate", "isolated"):
            errors.append(
                f"{cid}: verifier_mode=separate requires verifier.environment_mode=separate"
            )
        verifier_dirs, _ = _task_verifier_dirs(Path(candidates_dir) / cid, task_doc)
        for verifier_dir in verifier_dirs:
            if not (verifier_dir / "Dockerfile").is_file():
                errors.append(f"{cid}: verifier_mode=separate requires {verifier_dir}/Dockerfile")
    if dims.get("gpu") == "required":
        gpus = _resource_value(env_doc, "gpus")
        if gpus is None or gpus < 1:
            errors.append(f"{cid}: gpu=required requires [environment].gpus >= 1")
    if dims.get("gpu") == "none":
        gpus = _resource_value(env_doc, "gpus")
        if gpus is not None and gpus > 0:
            errors.append(f"{cid}: gpu=none requires [environment].gpus = 0")
    if container_mode == "multiple" and (_resource_value(env_doc, "gpus") or 0) > 0:
        errors.append(f"{cid}: Daytona GPU allocation requires a single-container Dockerfile task")
    servers = env_doc.get("mcp_servers")
    if dims.get("mcp") == "required":
        if not isinstance(servers, list) or not servers:
            errors.append(f"{cid}: mcp=required requires [[environment.mcp_servers]]")
    if dims.get("mcp") == "none" and servers:
        errors.append(f"{cid}: mcp=none forbids [[environment.mcp_servers]]")
    if isinstance(servers, list) and servers and dims.get("mcp") != "none":
        errors.extend(
            _check_mcp_servers(
                cid,
                servers,
                cand_env,
                _agent_network_mode(task_doc, env_state),
            )
        )
    return errors


def check_verifiers(
    design: dict[str, Any],
    state: dict[str, Any],
    candidates_dir: Path,
    env_state: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> list[str]:
    """Phase 05: validate task.toml and verifier files for every design candidate.

    Vocabulary and difficulty come from the sealed 03 plan, not target_spec.
    """
    errors: list[str] = []
    candidates_dir = Path(candidates_dir)
    if env_state is None or plan is None:
        loaded_env, loaded_plan = _canonical_phase_inputs(candidates_dir)
        if env_state is None:
            env_state = loaded_env
        if plan is None:
            plan = loaded_plan
    design_candidates = design.get("candidates")
    if not isinstance(design_candidates, list) or not design_candidates:
        return ["04_task_design.candidates must be a non-empty list"]
    expected_ids = [item.get("id") for item in design_candidates if isinstance(item, dict)]
    records = state.get("verifiers")
    if not isinstance(records, list) or not records:
        return ["verifiers must be a non-empty list"]
    ids = [r.get("candidate_id") if isinstance(r, dict) else None for r in records]
    if sorted(map(str, ids)) != sorted(map(str, expected_ids)) or len(set(ids)) != len(ids):
        errors.append(f"verifier candidate ids {ids} must cover 04_task_design ids {expected_ids}")
    tools_by_id = _oracle_tools_by_id(design)
    design_by_id = {str(item.get("id")): item for item in design_candidates if isinstance(item, dict)}
    slots_by_id = _slots_by_id(plan)
    globals_by_id = _globals_by_id(plan)
    plan_difficulty = _plan_difficulty(plan)
    for record in records:
        if not isinstance(record, dict):
            errors.append("verifier records must be objects")
            continue
        cid = record.get("candidate_id")
        task_dir = candidates_dir / str(cid)
        task_toml = candidates_dir / str(cid) / "task.toml"
        task_doc: dict[str, Any] = {}
        slot = slots_by_id.get(str(cid), {})
        if not task_toml.is_file() or not task_toml.read_bytes().strip():
            errors.append(f"{cid}: missing task.toml")
        else:
            try:
                import tomllib
                task_doc = tomllib.loads(task_toml.read_text(encoding="utf-8"))
            except (ImportError, ValueError, OSError) as exc:
                errors.append(f"{cid}: task.toml does not parse: {exc}")
                task_doc = {}
            for section in ("task", "metadata", "environment", "agent", "verifier"):
                if not isinstance(task_doc.get(section), dict):
                    errors.append(f"{cid}: task.toml needs [{section}]")
            task_doc_task = task_doc.get("task") if isinstance(task_doc.get("task"), dict) else {}
            if not str(task_doc_task.get("name", "")).strip() or not str(task_doc_task.get("description", "")).strip():
                errors.append(f"{cid}: task.toml task.name and task.description must be non-empty")
            metadata = task_doc.get("metadata") if isinstance(task_doc.get("metadata"), dict) else {}
            slot = slots_by_id.get(str(cid), {})
            global_row = globals_by_id.get(str(slot.get("global_id")), {})
            if not metadata.get("category"):
                errors.append(f"{cid}: metadata.category must identify a slot domain")
            else:
                slot_domains = global_row.get("domains") or []
                expected_categories = {
                    _packaged_category(value) for value in slot_domains if isinstance(value, str)
                }
                if expected_categories and metadata.get("category") not in expected_categories:
                    errors.append(
                        f"{cid}: metadata.category {metadata.get('category')!r} must match a slot domain {sorted(expected_categories)}"
                    )
            slot_subdomains = global_row.get("subdomains") or []
            if "subcategory" in metadata:
                expected_subcategories = {
                    _packaged_subcategory(value) for value in slot_subdomains if isinstance(value, str)
                }
                if metadata.get("subcategory") not in expected_subcategories:
                    errors.append(
                        f"{cid}: metadata.subcategory {metadata.get('subcategory')!r} must match a slot subdomain {sorted(expected_subcategories)}"
                    )
            if metadata.get("difficulty") not in DIFFICULTIES:
                errors.append(f"{cid}: metadata.difficulty must use the plan difficulty vocabulary")
            elif plan_difficulty and metadata.get("difficulty") != plan_difficulty:
                errors.append(f"{cid}: metadata.difficulty must match plan difficulty {plan_difficulty!r}")
            tags = metadata.get("tags")
            slot_tags = global_row.get("tags") or []
            if not isinstance(tags, list) or not tags:
                errors.append(f"{cid}: metadata.tags must be a non-empty slot tag subset")
            elif any(item not in slot_tags for item in tags):
                errors.append(f"{cid}: metadata.tags must be a slot tag subset")
            for estimate_key in ("expert_time_estimate_min", "junior_time_estimate_min"):
                estimate = metadata.get(estimate_key)
                if estimate is not None and (
                    isinstance(estimate, bool) or not isinstance(estimate, (int, float)) or estimate <= 0
                ):
                    errors.append(f"{cid}: metadata.{estimate_key} must be a positive number")
            expert = metadata.get("expert_time_estimate_min")
            junior = metadata.get("junior_time_estimate_min")
            if isinstance(expert, (int, float)) and not isinstance(expert, bool) and plan_difficulty in DIFFICULTY_SOTA_MINUTES:
                low, high = DIFFICULTY_SOTA_MINUTES[plan_difficulty]
                if not low <= float(expert) <= high:
                    errors.append(f"{cid}: metadata.expert_time_estimate_min must fit {plan_difficulty} difficulty band [{low}, {high}]")
            if isinstance(expert, (int, float)) and isinstance(junior, (int, float)) and not isinstance(expert, bool) and not isinstance(junior, bool) and float(junior) < float(expert) * JUNIOR_MULTIPLIER_MIN:
                errors.append(f"{cid}: metadata.junior_time_estimate_min must be at least {JUNIOR_MULTIPLIER_MIN:g}x expert estimate")
            env_doc = task_doc.get("environment") if isinstance(task_doc.get("environment"), dict) else {}
            dimensions = slot.get("deployment_dimensions") if isinstance(slot, dict) else {}
            multiple = isinstance(dimensions, dict) and dimensions.get("step_mode") == "multiple"
            errors.extend(_timeout_errors(str(cid), task_doc, multiple))
            for section in ("environment", "agent"):
                section_doc = task_doc.get(section) if isinstance(task_doc.get(section), dict) else {}
                if section_doc.get("network_mode") != "public":
                    errors.append(f"{cid}: [{section}].network_mode must be public")
            verifier_doc = task_doc.get("verifier") if isinstance(task_doc.get("verifier"), dict) else {}
            verifier_net = verifier_doc.get("network_mode")
            separate = isinstance(dimensions, dict) and dimensions.get("verifier_mode") == "separate"
            if verifier_net == "no-network" and separate:
                errors.append(f"{cid}: [verifier].network_mode must be public when verifier_mode=separate")
            elif verifier_net not in ("public", "no-network"):
                errors.append(
                    f"{cid}: [verifier].network_mode must be public, or no-network when the "
                    "scenario needs it and verifier dependencies are already installed"
                )
            for section in ("environment", "agent", "verifier"):
                section_doc = task_doc.get(section) if isinstance(task_doc.get(section), dict) else {}
                if section_doc.get("allowed_hosts", []):
                    errors.append(f"{cid}: [{section}].allowed_hosts must be empty")
                policy = _network_policy(env_state, section)
                if policy is not None and section_doc.get("network_mode") != policy.get("network_mode"):
                    errors.append(
                        f"{cid}: [{section}].network_mode must match sealed environment {policy.get('network_mode')!r}"
                    )
            for key in ("cpus", "memory_mb", "storage_mb"):
                required = float(HARBOR_RESOURCE_LIMITS[key])
                if _resource_value(env_doc, key) != required:
                    errors.append(f"{cid}: [environment].{key} must be {required:g}")
            gpus = _resource_value(env_doc, "gpus")
            if gpus is None or gpus < 0 or gpus > HARBOR_RESOURCE_LIMITS["gpus"]:
                errors.append(f"{cid}: [environment].gpus must be in [0, {HARBOR_RESOURCE_LIMITS['gpus']:g}]")
            if isinstance(env_state, dict):
                sealed_resources = env_state.get("resources") or env_state.get("limits")
                if isinstance(sealed_resources, dict):
                    for key in ("cpus", "memory_mb", "storage_mb", "gpus"):
                        expected_resource = _resource_value(sealed_resources, key)
                        actual_resource = _resource_value(env_doc, key)
                        if expected_resource is not None and actual_resource is not None and actual_resource != expected_resource:
                            errors.append(f"{cid}: [environment].{key} must match sealed environment resources")
        step_names, step_errors = _design_step_names(design_by_id.get(str(cid), {}), multiple)
        errors.extend(step_errors)
        if multiple:
            manifest_steps = task_doc.get("steps")
            manifest_names = (
                [step.get("name") if isinstance(step, dict) else None for step in manifest_steps]
                if isinstance(manifest_steps, list) else None
            )
            if manifest_names != step_names:
                errors.append(f"{cid}: task.toml steps must match 04_task_design.steps in order: {step_names}")
        verifier_dirs, layout_errors = _task_verifier_dirs(task_dir, task_doc)
        errors.extend(layout_errors)
        for tests_dir in verifier_dirs:
            expected = tests_dir / "test.sh"
            if not expected.is_file():
                continue
            label = f"{cid}: {expected.relative_to(task_dir)}"
            if not _is_executable(expected):
                errors.append(f"{label} is not executable")
            source = expected.read_text(encoding="utf-8", errors="replace")
            if not source.strip():
                errors.append(f"{label} is empty")
            elif "reward.txt" not in source:
                errors.append(f"{label} never writes /logs/verifier/reward.txt")
            if not _bash_syntax_ok(expected):
                errors.append(f"{label} fails bash -n")
            errors.extend(_verifier_runtime_errors(label, tests_dir, tools_by_id.get(str(cid))))
            errors.extend(_verifier_fail_logs_errors(label, tests_dir))
            errors.extend(_verifier_fixture_errors(label, tests_dir, source, task_dir / "tests"))
        if task_dir / "tests" not in verifier_dirs:
            errors.extend(_verifier_runtime_errors(cid, task_dir / "tests"))
        if str(cid) in tools_by_id and tools_by_id[str(cid)] is None:
            errors.append(f"{cid}: 04_task_design.json is missing oracle_tools")
        requirements = record.get("checked_requirements")
        if not isinstance(requirements, list) or not requirements:
            errors.append(f"{cid}: checked_requirements must be a non-empty list")
        else:
            for item in requirements:
                if not isinstance(item, dict) or not item.get("requirement") or not item.get("assertion"):
                    errors.append(f"{cid}: every checked_requirement needs requirement and assertion")
                    break
        if "oracle_tools" in record:
            errors.append(f"{cid}: oracle_tools lives on 04_task_design; do not copy it into the verifier record")
        if task_toml.is_file() and isinstance(task_doc, dict):
            errors.extend(
                _check_slot_task_preview(str(cid), slot, task_doc, candidates_dir, env_state)
            )
    errors.extend(_verifier_form_diversity_errors(records, candidates_dir))
    return errors


def _review_check_names() -> dict[str, set[str]]:
    import tomllib

    docs = Path(__file__).resolve().parents[1] / "docs"
    static_names = re.findall(
        r"^check-[a-z0-9-]+$", (docs / "static-checks.md").read_text(encoding="utf-8"), re.M
    )
    rubric = tomllib.loads((docs / "task-implementation.toml").read_text(encoding="utf-8"))
    rubric_names = [criterion["name"] for criterion in rubric["criteria"]]
    names_by_role = {"static": static_names, "implementation": rubric_names}
    for role, names in names_by_role.items():
        if not names or any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError(f"{role} review document must declare named checks")
        if len(set(names)) != len(names):
            raise ValueError(f"{role} review document contains duplicate check names")
    if not ADVISORY_REVIEW_CRITERIA.issubset(rubric_names):
        raise ValueError("implementation rubric is missing the advisory difficulty criteria")
    return {role: set(names) for role, names in names_by_role.items()}


def _review_report_errors(
    cid: str, item: dict[str, Any], expected_names: dict[str, set[str]]
) -> list[str]:
    reports = item.get("review_reports")
    if not isinstance(reports, dict):
        return [f"{cid}: review_reports must contain static and implementation reports"]
    errors: list[str] = []
    for role, flag in (("static", "static_checks_ok"), ("implementation", "rubric_ok")):
        label = f"{cid}: review_reports.{role}"
        records = reports.get(role)
        if not isinstance(records, list) or not records:
            errors.append(f"{label} must be a non-empty list")
            continue
        seen: set[str] = set()
        blocking_failures: list[str] = []
        for record in records:
            if not isinstance(record, dict):
                errors.append(f"{label} entries must be objects")
                continue
            name = record.get("name")
            if not isinstance(name, str) or name not in expected_names[role]:
                errors.append(f"{label} has unknown check {name!r}")
                continue
            if name in seen:
                errors.append(f"{label} has duplicate check {name!r}")
            seen.add(name)
            outcome = record.get("outcome")
            if outcome not in REVIEW_CHECK_OUTCOMES:
                errors.append(f"{label}.{name} needs outcome in {list(REVIEW_CHECK_OUTCOMES)}")
            for field in ("path", "reason"):
                value = record.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{label}.{name} needs a non-empty {field}")
            advisory = role == "implementation" and name in ADVISORY_REVIEW_CRITERIA
            if record.get("advisory", False) is not advisory:
                errors.append(f"{label}.{name} must use advisory={str(advisory).lower()}")
            if outcome == "fail" and not advisory:
                blocking_failures.append(name)
        missing = expected_names[role] - seen
        if missing:
            errors.append(f"{label} is missing checks: {sorted(missing)}")
        expected_flag = not blocking_failures
        if item.get(flag) is not expected_flag:
            errors.append(
                f"{cid}: {flag} must be {str(expected_flag).lower()} from the latest {role} "
                f"report (blocking failures: {sorted(blocking_failures)})"
            )
    return errors


def check_verifier_review(state: dict[str, Any], review: dict[str, Any], package_dir: Path) -> list[str]:
    """Phase 07: review packaged verifiers for loose/strict behavior."""
    errors: list[str] = []
    try:
        review_names = _review_check_names()
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        return [f"cannot load phase 07 review check names (Python 3.11+ required): {exc}"]
    package_dir = Path(package_dir)
    manifest_map: dict[str, str] = {}
    manifest_paths: set[str] = set()
    manifest_path = package_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = load_json(manifest_path)
            generated_tasks = manifest.get("generated_tasks") if isinstance(manifest, dict) else None
            if not isinstance(generated_tasks, list):
                errors.append("manifest.generated_tasks must be a list")
                generated_tasks = []
            for entry in generated_tasks:
                if isinstance(entry, dict) and entry.get("candidate_id") and entry.get("path"):
                    cid = str(entry["candidate_id"])
                    slug = str(entry["path"])
                    if cid in manifest_map:
                        errors.append(f"manifest has duplicate candidate_id {cid!r}")
                    if slug in manifest_paths:
                        errors.append(f"manifest has duplicate package path {slug!r}")
                    manifest_map[cid] = slug
                    manifest_paths.add(slug)
                    if not PACKAGE_SLUG_PATTERN.fullmatch(slug):
                        errors.append(f"manifest package path for {cid} is not a valid slug")
                    elif not (package_dir / slug).is_dir():
                        errors.append(f"manifest package path for {cid} does not exist: {slug}")
                else:
                    errors.append("manifest generated_tasks entries need candidate_id and path")
        except (OSError, json.JSONDecodeError):
            errors.append("generated_task/manifest.json is not valid JSON")
    else:
        errors.append("generated_task/manifest.json is missing")
    expected_ids = [item.get("candidate_id") for item in state.get("verifiers", []) if isinstance(item, dict)]
    manifest_ids = set(manifest_map)
    expected_id_set = set(map(str, expected_ids))
    if manifest_ids != expected_id_set:
        errors.append(
            "generated_task/manifest.json candidate ids must match verifier records "
            f"(manifest={sorted(manifest_ids)}, verifier={sorted(expected_id_set)})"
        )
    reviews = review.get("reviews")
    if not isinstance(reviews, list):
        return ["reviews must be a list"]
    ids = [item.get("candidate_id") if isinstance(item, dict) else None for item in reviews]
    if sorted(map(str, ids)) != sorted(map(str, expected_ids)) or len(set(ids)) != len(ids):
        errors.append(f"reviews {ids} must cover exactly the verifier records {expected_ids}")
    release_ids = review.get("release_candidate_ids")
    if not isinstance(release_ids, list) or len(set(map(str, release_ids))) != len(release_ids):
        errors.append("release_candidate_ids must be a list of unique ids")
        release_ids = []
    release_set = set(map(str, release_ids))
    if not release_set.issubset(set(map(str, ids))):
        errors.append("release_candidate_ids contains unknown candidates")
    tools_by_id = _oracle_tools_by_id(_load_design_state())
    for item in reviews:
        if not isinstance(item, dict):
            errors.append("review entries must be objects")
            continue
        cid = str(item.get("candidate_id"))
        errors.extend(_review_report_errors(cid, item, review_names))
        manifest_slug = manifest_map.get(cid)
        declared_slug = item.get("package_slug")
        if not isinstance(declared_slug, str) or not declared_slug.strip():
            errors.append(f"{cid}: package_slug is required")
        elif declared_slug != manifest_slug:
            errors.append(f"{cid}: package_slug must match generated_task/manifest.json")
        if manifest_slug is None:
            errors.append(f"{cid}: candidate is missing from generated_task/manifest.json")
        package_slug = str(manifest_slug or declared_slug or cid)
        package = package_dir / package_slug
        if not package.is_dir():
            errors.append(f"{cid}: package directory does not exist: {package_slug}")
        verifier_dirs, layout_errors = _task_verifier_dirs(package)
        errors.extend(layout_errors)
        syntax = bool(verifier_dirs) and not layout_errors and all(
            _bash_syntax_ok(tests_dir / "test.sh") for tests_dir in verifier_dirs
        )
        if item.get("syntax_ok") is not syntax:
            errors.append(f"{cid}: syntax_ok must be {syntax} (bash -n result)")
        for tests_dir in verifier_dirs:
            errors.extend(_verifier_runtime_errors(cid, tests_dir, tools_by_id.get(cid)))
        if package / "tests" not in verifier_dirs:
            errors.extend(_verifier_runtime_errors(cid, package / "tests"))
        checks = item.get("checks")
        failed: list[str] = []
        if not isinstance(checks, dict):
            errors.append(f"{cid}: checks must be an object")
        else:
            for key in ("too_loose", "too_strict", "deterministic"):
                entry = checks.get(key)
                outcome = entry.get("outcome") if isinstance(entry, dict) else None
                if outcome not in REVIEW_CHECK_OUTCOMES:
                    errors.append(f"{cid}: check {key} needs outcome in {list(REVIEW_CHECK_OUTCOMES)}")
                elif outcome == "fail":
                    failed.append(key)
        if not isinstance(item.get("issues"), list):
            errors.append(f"{cid}: issues must be a list")
        status = item.get("status")
        if status not in {"publish", "revise", "reject"}:
            errors.append(f"{cid}: status must be publish, revise, or reject")
            continue
        if status == "publish" and (not syntax or failed):
            errors.append(f"{cid}: publish requires syntax_ok and all review checks to pass")
        if status == "publish":
            for flag in ("harbor_shape_ok", "static_checks_ok", "rubric_ok"):
                if item.get(flag) is not True:
                    errors.append(f"{cid}: publish requires {flag}=true")
        if status == "publish" and item.get("calibration_executed") is not True:
            errors.append(f"{cid}: publish requires executed calibration evidence")
        if status == "publish":
            calibration = item.get("calibration_evidence")
            if not isinstance(calibration, dict):
                errors.append(f"{cid}: publish requires calibration_evidence")
            else:
                for case_kind in ("positive", "negative"):
                    cases = calibration.get(case_kind)
                    if not isinstance(cases, list) or not cases or any(not isinstance(case, str) or not case.strip() for case in cases):
                        errors.append(f"{cid}: calibration_evidence.{case_kind} must list executed cases")
        if status == "publish":
            for check_name in ("too_loose", "too_strict", "deterministic"):
                entry = checks.get(check_name) if isinstance(checks, dict) else None
                if not isinstance(entry, dict) or entry.get("outcome") != "pass":
                    errors.append(f"{cid}: publish requires {check_name}=pass")
        if status in {"revise", "reject"} and not item.get("issues"):
            errors.append(f"{cid}: {status} requires non-empty issues")
        if (status == "publish") != (cid in release_set):
            errors.append(f"{cid}: release_candidate_ids must contain exactly publish records")
    if not release_ids:
        errors.append("release_candidate_ids must contain at least one publish candidate")
    if (package_dir / "release_manifest.json").exists():
        errors.append(
            "release_manifest.json was removed; join 07_review.release_candidate_ids "
            "with generated_task/manifest.json"
        )
    return errors


PACKAGE_TOP_LEVEL = {"task.toml", "instruction.md", "README.md", "environment", "tests", "steps"}
PACKAGE_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,2}$")
TASK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
TASK_TOML_TOP_KEYS = {
    "schema_version", "version", "multi_step_reward_strategy", "task", "metadata", "verifier",
    "agent", "environment", "solution", "source", "artifacts", "steps",
}
TASK_TOML_TASK_KEYS = {"name", "version", "description", "authors", "keywords"}
TASK_TOML_ENVIRONMENT_KEYS = {
    "build_timeout_sec", "network_mode", "allowed_hosts", "docker_image", "os", "cpus",
    "memory_mb", "storage_mb", "gpus", "gpu_types", "tpu", "allow_internet", "env",
    "mcp_servers", "skills_dir", "healthcheck",
}
TASK_TOML_VERIFIER_KEYS = {
    "timeout_sec", "network_mode", "allowed_hosts", "env", "user", "environment_mode",
    "environment", "collect",
}
TASK_TOML_AGENT_KEYS = {"timeout_sec", "network_mode", "allowed_hosts", "user"}
def _tree_files(root: Path) -> dict[str, Path]:
    return {item.relative_to(root).as_posix(): item for item in root.rglob("*") if item.is_file()}


def _same_bytes(left: Path, right: Path) -> bool:
    return left.is_file() and right.is_file() and left.read_bytes() == right.read_bytes()


def check_task_toml_assembled(text: str, slug: str, env_state: dict[str, Any]) -> list[str]:
    """Packaged task.toml must stay a valid Harbor file (from phase 05/06)."""
    import tomllib

    errors: list[str] = []
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [f"task.toml does not parse: {exc}"]
    unknown = sorted(set(parsed) - TASK_TOML_TOP_KEYS)
    if unknown:
        errors.append(f"task.toml has unknown top-level keys {unknown}")
    task = parsed.get("task")
    if not isinstance(task, dict):
        errors.append("task.toml needs a [task] section")
    else:
        name = task.get("name")
        if not isinstance(name, str) or not TASK_NAME_PATTERN.match(name) or ".." in name:
            errors.append("[task].name must be '<org>/<name>'")
        elif name.split("/", 1)[1] != slug:
            errors.append(f"[task].name must end with the package directory name {slug!r}")
        if not str(task.get("description", "")).strip():
            errors.append("[task].description must not be empty")
    for section in ("metadata", "verifier", "agent", "environment"):
        if not isinstance(parsed.get(section), dict):
            errors.append(f"task.toml needs a [{section}] section")
    environment = parsed.get("environment") if isinstance(parsed.get("environment"), dict) else {}
    network = env_state.get("network") if isinstance(env_state.get("network"), dict) else {}
    environment_policy = network.get("environment") if isinstance(network.get("environment"), dict) else {}
    expected = environment_policy.get("network_mode", "public")
    mode = environment.get("network_mode")
    if mode is not None and mode != expected:
        errors.append(
            f"[environment].network_mode must match the sealed baseline {expected!r}; got {mode!r}"
        )
    for section in ("agent", "verifier"):
        policy = network.get(section) if isinstance(network.get(section), dict) else {}
        declared = parsed.get(section) if isinstance(parsed.get(section), dict) else {}
        declared_mode = declared.get("network_mode")
        expected_mode = policy.get("network_mode")
        if declared_mode is not None and expected_mode in NETWORK_MODES and declared_mode != expected_mode:
            errors.append(f"[{section}].network_mode must match environment contract {expected_mode!r}")
    return errors


def _toml_core_equal(left_text: str, right_text: str, slug: str) -> list[str]:
    """Allow only [task].name (and optional package identity metadata) to differ."""
    import tomllib
    import copy

    errors: list[str] = []
    try:
        left = tomllib.loads(left_text)
        right = tomllib.loads(right_text)
    except tomllib.TOMLDecodeError as exc:
        return [f"task.toml compare failed to parse: {exc}"]
    l2 = copy.deepcopy(left)
    r2 = copy.deepcopy(right)
    for doc in (l2, r2):
        task = doc.get("task")
        if isinstance(task, dict):
            task.pop("name", None)
        meta = doc.get("metadata")
        if isinstance(meta, dict):
            meta.pop("candidate_id", None)
            meta.pop("package_slug", None)
    if l2 != r2:
        errors.append(
            f"task.toml must be the phase-05/06 draft aside from [task].name "
            f"(and optional candidate_id/package_slug metadata); slug={slug!r}"
        )
    return errors


def check_package(
    env_state: dict[str, Any],
    design_state: dict[str, Any],
    verifier_state: dict[str, Any],
    env_dir: Path,
    candidates_dir: Path,
    generated_dir: Path,
    *,
    allow_environment_repairs: bool = False,
) -> list[str]:
    """Validate assembly, allowing environment-only nop repairs at the final gate."""
    errors: list[str] = []
    # env_dir remains in the CLI for call-site compatibility; assembly copies
    # candidates/<id>/environment/ verbatim and does not merge the sealed tree.
    del env_dir
    candidates_dir, generated_dir = Path(candidates_dir), Path(generated_dir)
    manifest_path = generated_dir / "manifest.json"
    if not manifest_path.is_file():
        return [f"missing {manifest_path.as_posix()}"]
    try:
        manifest = load_json(manifest_path)
    except json.JSONDecodeError as exc:
        return [f"manifest.json is not valid JSON: {exc}"]
    tasks = manifest.get("generated_tasks") if isinstance(manifest, dict) else None
    if not isinstance(tasks, list) or not tasks:
        return ["manifest.generated_tasks must be a non-empty list"]

    records = verifier_state.get("verifiers")
    if not isinstance(records, list) or not records:
        return ["verifiers is empty"]
    approved = [str(item.get("candidate_id")) for item in records if isinstance(item, dict)]
    if not approved:
        return ["no verifier candidates are ready for packaging"]
    ids = [str(item.get("candidate_id")) if isinstance(item, dict) else None for item in tasks]
    if ids != approved:
        # Prefer same order as approved list; still require same multiset.
        if sorted(map(str, ids)) != sorted(approved) or len(set(ids)) != len(ids):
            errors.append(f"manifest candidate ids {ids} must be exactly the approved ids {approved}")
        else:
            errors.append(f"manifest candidate order {ids} should match approved order {approved}")
    expected_commit = ((env_state.get("source_repo") or {}).get("commit") if isinstance(env_state, dict) else None) or "unknown"
    design_by_id = {
        str(c.get("id")): c
        for c in (design_state.get("candidates") or [])
        if isinstance(c, dict)
    }
    verifier_ids = {
        str(item.get("candidate_id"))
        for item in verifier_state.get("verifiers", [])
        if isinstance(item, dict)
    }
    seen_paths: set[str] = set()

    for item in tasks:
        if not isinstance(item, dict):
            errors.append("manifest entries must be objects")
            continue
        cid = str(item.get("candidate_id"))
        if cid not in design_by_id:
            errors.append(f"{cid}: not present in the task-design index")
        if cid not in verifier_ids:
            errors.append(f"{cid}: not present in the verifier index")
        slug = item.get("path")
        if not isinstance(slug, str) or not PACKAGE_SLUG_PATTERN.match(slug):
            errors.append(f"{cid}: package path must be a kebab-case slug of at most 3 words, got {slug!r}")
            continue
        if slug in seen_paths:
            errors.append(f"{cid}: duplicate package path {slug!r}")
        seen_paths.add(slug)
        if item.get("source_commit") != expected_commit:
            errors.append(f"{cid}: manifest source_commit must be {expected_commit!r}")
        if item.get("deployment_mode") != env_state.get("deployment_mode"):
            errors.append(f"{cid}: manifest deployment_mode must match the sealed base environment")

        package = generated_dir / slug
        if not package.is_dir():
            errors.append(f"{cid}: missing package directory {slug}/")
            continue
        extras = sorted(entry.name for entry in package.iterdir() if entry.name not in PACKAGE_TOP_LEVEL)
        if extras:
            errors.append(f"{slug}: unexpected top-level entries {extras}; allowed are {sorted(PACKAGE_TOP_LEVEL)}")
        environment_entry = "environment/Dockerfile" if env_state.get("deployment_mode") == "single" else "environment/docker-compose.yaml"
        if env_state.get("deployment_mode") == "compose" and not (package / environment_entry).is_file():
            environment_entry = "environment/docker-compose.yml"
        candidate = design_by_id.get(cid, {})
        multiple = "steps" in candidate
        _, step_errors = _design_step_names(candidate, multiple)
        errors.extend(step_errors)
        required_files = ["task.toml", "README.md", environment_entry]
        if not multiple:
            required_files.append("instruction.md")
        for rel in required_files:
            path = package / rel
            if not path.is_file() or not path.read_bytes().strip():
                errors.append(f"{slug}: missing or empty {rel}")

        # The initial copy is exact; the final gate permits environment-only nop repairs.
        source_env_dir = candidates_dir / cid / "environment"
        if not source_env_dir.is_dir():
            errors.append(f"{slug}: missing candidate environment dir {source_env_dir.as_posix()}")
        elif not allow_environment_repairs:
            expected_env = _tree_files(source_env_dir)
            package_env = _tree_files(package / "environment") if (package / "environment").is_dir() else {}
            if set(expected_env) != set(package_env):
                errors.append(
                    f"{slug}: environment/ must be a verbatim copy of {source_env_dir.as_posix()} "
                    f"(missing {sorted(set(expected_env) - set(package_env))[:5]}, "
                    f"extra {sorted(set(package_env) - set(expected_env))[:5]})"
                )
            else:
                changed = [
                    rel for rel in expected_env if not _same_bytes(expected_env[rel], package_env[rel])
                ]
                if changed:
                    errors.append(
                        f"{slug}: environment files differ from candidate environment: {changed[:5]}"
                    )

        # Shared tests and native step trees remain exact candidate copies.
        for tree in ("tests", "steps"):
            source_dir = candidates_dir / cid / tree
            copied_dir = package / tree
            expected_files = _tree_files(source_dir) if source_dir.is_dir() else {}
            actual_files = _tree_files(copied_dir) if copied_dir.is_dir() else {}
            if source_dir.is_dir() != copied_dir.is_dir() or set(expected_files) != set(actual_files):
                errors.append(f"{slug}: {tree}/ must be a verbatim copy of the candidate {tree}/")
            else:
                changed = [rel for rel in expected_files if not _same_bytes(expected_files[rel], actual_files[rel])]
                if changed:
                    errors.append(f"{slug}: {tree} files differ from candidate {tree}: {changed[:5]}")
        verifier_dirs, layout_errors = _task_verifier_dirs(package)
        errors.extend(layout_errors)
        for tests_dir in verifier_dirs:
            test_script = tests_dir / "test.sh"
            if test_script.is_file() and not _is_executable(test_script):
                errors.append(f"{slug}: {test_script.relative_to(package)} is not executable")

        # A multi-step root instruction is optional, but must be copied if supplied.
        src_instruction = candidates_dir / cid / "instruction.md"
        if not src_instruction.is_file() and not multiple:
            errors.append(f"{slug}: missing candidate instruction.md")
        elif src_instruction.is_file() and not _same_bytes(src_instruction, package / "instruction.md"):
            errors.append(f"{slug}: instruction.md must be a byte-for-byte copy of the candidate file")
        elif not src_instruction.exists() and (package / "instruction.md").exists():
            errors.append(f"{slug}: instruction.md has no corresponding candidate file")

        # task.toml: phase-05/06 draft with name/slug alignment only
        src_toml = candidates_dir / cid / "task.toml"
        pkg_toml = package / "task.toml"
        if not src_toml.is_file():
            errors.append(f"{slug}: missing candidate task.toml")
        elif pkg_toml.is_file():
            src_text = src_toml.read_text(encoding="utf-8", errors="replace")
            pkg_text = pkg_toml.read_text(encoding="utf-8", errors="replace")
            errors.extend(f"{slug}: {msg}" for msg in check_task_toml_assembled(pkg_text, slug, env_state))
            errors.extend(f"{slug}: {msg}" for msg in _toml_core_equal(src_text, pkg_text, slug))

        readme = package / "README.md"
        if readme.is_file():
            body = readme.read_text(encoding="utf-8", errors="replace")
            if cid not in body and f"candidate" not in body.lower():
                errors.append(f"{slug}: README.md should mention the candidate id or provenance")
    return errors


def _fail(errors: list[str]) -> int:
    if not errors:
        return 0
    for item in errors:
        print(item, file=sys.stderr)
    return 1


# Per-phase state JSON handoffs. Agents must land these on disk before long
# probes; verifiers require them. Skeletons are valid JSON with required top
# keys present (values may be empty placeholders the agent fills in).
PHASE_HANDOFFS: dict[str, dict[str, Any]] = {
    "01_repo_profile_gate": {
        "path": "/synthesis/state/01_repo_profile_gate.json",
        "skeleton": {
            "checkout": {"verified": False, "head": ""},
            "languages": [],
            "domains": [],
            "subdomains": [],
            "entrypoints": [],
            "tags": [],
            "evidence": {
                "license_files": [],
                "build_files": [],
                "entrypoint_files": [],
            },
            "license": {"known": False},
            "executable": {"present": False},
            "hard_checks": {
                "source_present": False,
                "executable_logic": False,
                "build_or_runtime_path": False,
                "target_alignment": False,
                "license_known": False,
                "deployment_support": False,
            },
            "deployment_support": {},
            "blockers": [],
            "repo_score": 0.0,
            "buildability_score": 0.0,
            "task_potential_score": 0.0,
            "decision": "reject",
        },
    },
    "02_environment": {
        "path": "/synthesis/state/02_environment.json",
        "skeleton": {
            "deployment_mode": "single",
            "source_repo": {"url": "", "commit": ""},
            "services": [],
            "resources": {"cpus": 4, "memory_mb": 8192, "storage_mb": 10240, "gpus": 0},
            "dependencies": {"system": [], "language": [], "pinned": False},
            "asset_paths": [],
            "network": {
                "environment": {"network_mode": "public", "allowed_hosts": []},
                "agent": {"network_mode": "public", "allowed_hosts": []},
                "verifier": {"network_mode": "public", "allowed_hosts": []},
            },
            "paths": {
                "workdir": "/workspace",
                "source_dir": "/workspace/repo",
                "data_dir": None,
                "results_dir": None,
            },
            "entrypoints": [],
            "build": {
                "status": "failed",
                "mode": "static",
                "buildable": False,
                "smoke_test": False,
                "build_seconds": None,
                "failures": ["skeleton: build not yet run"],
            },
        },
    },
    "03_simula_plan": {
        "path": "/synthesis/state/03_simula_plan.json",
        "skeleton": {"difficulty": "", "global": [], "slots": []},
    },
    "04_task_design": {
        "path": "/synthesis/state/04_task_design.json",
        "skeleton": {"candidates": []},
    },
    "05_verifier": {
        "path": "/synthesis/state/05_verifier.json",
        "skeleton": {"verifiers": []},
    },
    "07_review": {
        "path": "/synthesis/state/07_review.json",
        "skeleton": {"reviews": [], "release_candidate_ids": []},
    },
}


def _atomic_write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(doc, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def ensure_handoff(phase: str, force: bool = False) -> list[str]:
    """Create skeleton state JSON for a phase if missing (or always when force)."""
    spec = PHASE_HANDOFFS.get(phase)
    if spec is None:
        return [f"unknown handoff phase {phase!r}; known: {sorted(PHASE_HANDOFFS)}"]
    path = Path(spec["path"])
    notes: list[str] = []
    if force or not path.is_file():
        _atomic_write_json(path, spec["skeleton"])
        notes.append(f"wrote skeleton {path.as_posix()}")
    else:
        notes.append(f"exists {path.as_posix()}")
    for extra in spec.get("also_write") or []:
        extra_path = Path(extra["path"])
        if extra.get("same_as"):
            source = Path(extra["same_as"])
            if source.is_file() and (force or not extra_path.is_file()):
                extra_path.parent.mkdir(parents=True, exist_ok=True)
                extra_path.write_bytes(source.read_bytes())
                notes.append(f"synced {extra_path.as_posix()} from {source.as_posix()}")
            elif force or not extra_path.is_file():
                _atomic_write_json(extra_path, spec["skeleton"])
                notes.append(f"wrote skeleton {extra_path.as_posix()}")
            else:
                notes.append(f"exists {extra_path.as_posix()}")
        elif force or not extra_path.is_file():
            _atomic_write_json(extra_path, extra.get("skeleton") or {})
            notes.append(f"wrote skeleton {extra_path.as_posix()}")
    return notes


def require_handoff(phase: str) -> list[str]:
    """Fail unless the phase state JSON exists and parses as an object."""
    spec = PHASE_HANDOFFS.get(phase)
    if spec is None:
        return [f"unknown handoff phase {phase!r}; known: {sorted(PHASE_HANDOFFS)}"]
    errors: list[str] = []
    path = Path(spec["path"])
    if not path.is_file():
        errors.append(f"missing handoff {path.as_posix()}")
        return errors
    try:
        doc = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"handoff {path.as_posix()} is not valid JSON: {exc}")
        return errors
    if not isinstance(doc, dict):
        errors.append(f"handoff {path.as_posix()} must be a JSON object")
        return errors
    for key in spec["skeleton"]:
        if key not in doc:
            errors.append(f"handoff {path.as_posix()} missing top-level key {key!r}")
    for extra in spec.get("also_write") or []:
        extra_path = Path(extra["path"])
        if not extra_path.is_file():
            errors.append(f"missing companion handoff {extra_path.as_posix()}")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: phase_contract.py validate SPEC | "
            "check-repo-profile-gate SPEC PROFILE | "
            "check-simula-plan SPEC PLAN ENV_STATE | "
            "check-design DESIGN [CANDIDATES_DIR [ENV_STATE PLAN]] | "
            "check-environment SPEC STATE ENV_DIR | "
            "check-verifiers DESIGN STATE CANDIDATES_DIR [ENV_STATE PLAN] | "
            "check-verifier-review STATE05 REVIEW PACKAGE_DIR | "
            "check-package ENV_STATE DESIGN_STATE VERIFIER_STATE ENV_DIR CANDIDATES_DIR GENERATED_DIR | "
            "ensure-handoff PHASE [--force] | require-handoff PHASE | "
            "list-handoffs",
            file=sys.stderr,
        )
        return 2
    command = argv[1]
    if command == "validate":
        spec = load_json(argv[2])
        return _fail(validate_spec(spec))
    if command == "check-repo-profile-gate":
        spec = load_json(argv[2])
        profile = load_json(argv[3])
        return _fail(validate_spec(spec) + check_repo_profile_gate(spec, profile))
    if command == "check-simula-plan":
        if len(argv) < 4:
            print("check-simula-plan requires: SPEC PLAN [ENV_STATE]", file=sys.stderr)
            return 2
        spec = load_json(argv[2])
        plan = load_json(argv[3])
        env_state = load_json(argv[4]) if len(argv) > 4 else None
        return _fail(validate_spec(spec) + check_simula_plan(spec, plan, env_state=env_state))
    if command == "check-design":
        if len(argv) < 3:
            print("check-design requires: DESIGN [CANDIDATES_DIR [ENV_STATE PLAN]]", file=sys.stderr)
            return 2
        design = load_json(argv[2])
        candidates_dir = Path(argv[3]) if len(argv) > 3 else None
        env_state = load_json(argv[4]) if len(argv) > 4 else None
        plan = load_json(argv[5]) if len(argv) > 5 else None
        return _fail(
            check_design(design, candidates_dir=candidates_dir, env_state=env_state, plan=plan)
        )
    if command == "check-environment":
        spec = load_json(argv[2])
        state = load_json(argv[3])
        errors = validate_spec(spec) + check_environment(spec, state, Path(argv[4]))
        if isinstance(state.get("build"), dict):
            errors.extend(check_environment_build(state))
        return _fail(errors)
    if command == "check-verifiers":
        if len(argv) < 5:
            print(
                "check-verifiers requires: DESIGN STATE CANDIDATES_DIR [ENV_STATE PLAN]",
                file=sys.stderr,
            )
            return 2
        design = load_json(argv[2])
        state = load_json(argv[3])
        candidates_dir = Path(argv[4])
        env_state = load_json(argv[5]) if len(argv) > 5 else None
        plan = load_json(argv[6]) if len(argv) > 6 else None
        return _fail(
            check_verifiers(design, state, candidates_dir, env_state=env_state, plan=plan)
        )
    if command == "check-verifier-review":
        return _fail(check_verifier_review(load_json(argv[2]), load_json(argv[3]), Path(argv[4])))
    if command == "list-handoffs":
        for phase, spec in PHASE_HANDOFFS.items():
            extras = ", ".join(extra["path"] for extra in spec.get("also_write") or [])
            suffix = f" (+ {extras})" if extras else ""
            print(f"{phase}\t{spec['path']}{suffix}")
        return 0
    if command == "ensure-handoff":
        if len(argv) < 3:
            print("ensure-handoff requires PHASE", file=sys.stderr)
            return 2
        force = "--force" in argv[3:]
        notes = ensure_handoff(argv[2], force=force)
        if notes and notes[0].startswith("unknown "):
            return _fail(notes)
        for note in notes:
            print(note)
        return 0
    if command == "require-handoff":
        if len(argv) < 3:
            print("require-handoff requires PHASE", file=sys.stderr)
            return 2
        return _fail(require_handoff(argv[2]))
    if command == "check-package":
        if len(argv) not in (8, 9) or (len(argv) == 9 and argv[8] != "--allow-environment-repairs"):
            print(
                "check-package requires: ENV_STATE DESIGN_STATE VERIFIER_STATE "
                "ENV_DIR CANDIDATES_DIR GENERATED_DIR [--allow-environment-repairs]",
                file=sys.stderr,
            )
            return 2
        return _fail(
            check_package(
                load_json(argv[2]),
                load_json(argv[3]),
                load_json(argv[4]),
                Path(argv[5]),
                Path(argv[6]),
                Path(argv[7]),
                allow_environment_repairs=len(argv) == 9,
            )
        )
    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
