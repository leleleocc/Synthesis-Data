#!/usr/bin/env python3
"""Closed vocabulary and alignment checks for target_spec.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ORACLE_TYPES = ("result", "state", "behavior")
DIFFICULTIES = ("easy", "medium", "hard", "ultra")

# Terminal-Bench taxonomy domains (docs/TAXONOMY.md). Closed set. Factory JSON
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

# Seed subdomains per domain (TAXONOMY.md). New kebab-case subdomains may be
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

HARD_CHECKS = (
    "source_present",
    "executable_logic",
    "build_or_runtime_path",
    "target_alignment",
    "license_known",
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

REVIEW_SCORE_KEYS = (
    "verifiable",
    "well_specified",
    "solvable",
    "difficult",
    "interesting",
    "outcome_verified",
    "spec_alignment",
)

REVIEW_MIN_SCORE = 0.7

# Terminal-Bench implementation-rubric criteria that can be judged from a
# candidate instruction alone (same names as docs/prompts/task-implementation.toml).
REVIEW_CHECK_KEYS = (
    "anti_cheat_robustness",
    "deterministic_reproducible",
    "essential_difficulty",
    "novel",
    "agentic",
    "instruction_concision",
    "structured_data_schema",
    "task_security",
    "typos",
)
REVIEW_CHECK_OUTCOMES = ("pass", "fail", "not_applicable")

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
    "scenario_angle",
    "output_shape",
    "primary_input",
    "primary_entrypoint",
)
SINGULAR_VOCAB_KEYS = (
    "task_type",
    "task_types",
    "domain",
    "language",
    "oracle_type",
    "tag",
    "subdomain",
)


def _non_ascii_error(path: Path, label: str) -> str | None:
    """Harbor host-reads instruction.md / task.toml with the locale encoding."""
    if not path.is_file():
        return None
    data = path.read_bytes()
    for index, line in enumerate(data.splitlines()):
        if any(byte > 0x7F for byte in line):
            preview = line.decode("utf-8", errors="replace").strip()
            return (
                f"{label} contains non-ASCII text (first at line {index + 1}: "
                f"{ascii(preview[:60])}); Harbor reads it with the host locale "
                "encoding, which breaks on Windows/GBK"
            )
    return None

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
    if not isinstance(source, dict) or not source.get("path"):
        errors.append("source_repo.path is required")
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
    if n < 3:
        return 0
    return min(n - 1, max(1, round(n / 3)))


def simula_local_counts(n: int) -> list[int]:
    """Per-node-set slot counts in global-list order, summing to n."""
    k = simula_local_k(n)
    g = simula_global_count(n)
    counts = [k] * g
    remainder = n - g * k
    for index in range(remainder):
        counts[index] += 1
    return counts


def _ascii_only(value: str) -> bool:
    return all(ord(ch) < 128 for ch in value)


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
    """Phase 04: Global / Local / Complexity slots grounded in the sealed base."""
    errors: list[str] = []
    budget = candidate_budget(spec)
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
        env_path = Path("/synthesis/state/03_environment.json")
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
    complexified_n = 0
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
                    f"slot {sid!r} uses {singular!r}; "
                    "use the list fields tags / domains / subdomains / languages / oracle_types"
                )
        gid = slot.get("global_id")
        if gid not in global_by_id:
            errors.append(f"slot {sid!r} global_id {gid!r} is not in plan.global")
        else:
            slots_by_global.setdefault(gid, []).append(slot)
            parent = global_by_id[gid]
            for key in SIMULA_VOCAB_KEYS:
                if slot.get(key) != parent.get(key):
                    errors.append(
                        f"slot {sid!r} {key} must equal global {gid!r} {key} "
                        f"(local does not retarget vocabulary)"
                    )
        errors.extend(_check_vocab_lists(spec, slot, f"slot {sid!r}"))
        oracles = slot.get("oracle_types")
        if isinstance(oracles, list):
            oracle_union.update(item for item in oracles if isinstance(item, str))

        angle = slot.get("scenario_angle")
        if angle not in SCENARIO_ANGLES:
            errors.append(
                f"slot {sid!r} scenario_angle must be one of {list(SCENARIO_ANGLES)}; got {angle!r}"
            )
        shape = slot.get("output_shape")
        if not isinstance(shape, str) or not KEBAB_TOKEN.fullmatch(shape):
            errors.append(
                f"slot {sid!r} output_shape must be a non-empty kebab-case token; got {shape!r}"
            )
        primary_input = slot.get("primary_input")
        if not isinstance(primary_input, str) or not primary_input.strip() or not _ascii_only(primary_input):
            errors.append(f"slot {sid!r} primary_input must be a non-empty ASCII path")
        else:
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
        if flagged not in (True, False):
            errors.append(f"slot {sid!r} complexified must be true or false")
            flagged = False
        if flagged:
            complexified_n += 1
        delta = slot.get("complexity_delta")
        if not isinstance(delta, str):
            errors.append(f"slot {sid!r} complexity_delta must be a string")
        elif flagged:
            if not delta.strip() or not _ascii_only(delta):
                errors.append(
                    f"slot {sid!r} complexity_delta must be non-empty ASCII when complexified"
                )
        elif delta != "":
            errors.append(
                f"slot {sid!r} complexity_delta must be empty when complexified is false"
            )

    for path, count in input_counts.items():
        if count > 2:
            errors.append(
                f"at most two slots may share primary_input {path!r} (got {count})"
            )

    expected_complex = simula_complexified_count(budget)
    if complexified_n != expected_complex:
        errors.append(
            f"plan.slots must mark exactly {expected_complex} complexified slots "
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


def check_filter(filter_doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    checks = filter_doc.get("hard_checks")
    if not isinstance(checks, dict):
        return ["filter.hard_checks must be an object"]
    missing = [key for key in HARD_CHECKS if key not in checks]
    if missing:
        errors.append(f"filter.hard_checks missing {missing}")
    values = []
    for key in HARD_CHECKS:
        value = checks.get(key)
        if value not in (True, False):
            errors.append(f"filter.hard_checks.{key} must be true or false")
        else:
            values.append(value)
    accepted = filter_doc.get("accepted")
    if accepted not in (True, False):
        errors.append("filter.accepted must be true or false")
    elif values and accepted is not all(values):
        errors.append("filter.accepted must be true only when every hard_check is true")
    return errors


def _read_candidate_task_toml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


ENV_BUILD_STATUSES = ("not_required", "passed", "failed")
OVERLAY_FORBIDDEN_FILES = ("environment.json", "docker-compose.yaml")
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


def _overlay_installs_tool(overlay_dir: Path, tool: str) -> bool:
    """True when an overlay build script mentions the argv0 (install or PATH probe)."""
    if not overlay_dir.is_dir() or not tool:
        return False
    token = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(tool)}(?![A-Za-z0-9_.-])")
    for name in ("setup-overlay.sh", "setup.sh", "Dockerfile"):
        path = overlay_dir / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if token.search(text):
            return True
    return False


def overlay_needs_rebuild(overlay_dir: Path) -> bool:
    """True when the overlay changes image-build inputs, not just extra assets."""
    if not overlay_dir.is_dir():
        return False
    for name in ("Dockerfile", "setup.sh", "setup-overlay.sh", "smoke_test.sh"):
        if (overlay_dir / name).is_file():
            return True
    return False


def check_overlay(
    spec: dict[str, Any],
    candidate_id: str,
    overlay_dir: Path,
    env_build: str | None,
) -> list[str]:
    """Per-candidate environment overlay: add-only files, never the sealed base tree."""
    errors: list[str] = []
    cid = f"candidate {candidate_id!r}"
    overlay_dir = Path(overlay_dir)
    if not overlay_dir.is_dir():
        errors.append(f"{cid} missing overlay directory {overlay_dir.as_posix()}")
        return errors
    for name in OVERLAY_FORBIDDEN_FILES:
        if (overlay_dir / name).exists():
            errors.append(
                f"{cid} overlay must not include {name} (sealed base owns topology "
                "and the environment contract)"
            )
    needs_rebuild = overlay_needs_rebuild(overlay_dir)
    if env_build == "not_required" and needs_rebuild:
        errors.append(
            f"{cid} env_build is not_required but overlay replaces Dockerfile or setup; "
            "docker-build the overlay (or a scratch merge) and set env_build=passed"
        )
    if env_build in ("passed", "failed") and not needs_rebuild:
        errors.append(
            f"{cid} env_build={env_build!r} but overlay is assets-only; use not_required"
        )
    dockerfile = overlay_dir / "Dockerfile"
    if dockerfile.is_file():
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        for line in _dockerfile_logical_lines(text):
            if LOCAL_IMAGE_FROM.match(line):
                errors.append(
                    f"{cid} overlay Dockerfile FROM must be a public base image; "
                    "Harbor rebuilds the packaged environment in isolation "
                    f"(got {line!r})"
                )
                break
        if not (overlay_dir / "setup.sh").is_file():
            errors.append(f"{cid} overlay Dockerfile requires overlay setup.sh")
        errors.extend(
            f"{cid} {msg}" for msg in check_dockerfile(text, overlay_dir, spec)
        )
    elif (overlay_dir / "setup.sh").is_file() or (overlay_dir / "smoke_test.sh").is_file():
        errors.append(
            f"{cid} overlay setup.sh / smoke_test.sh require a complete overlay Dockerfile"
        )
    for name in ("setup.sh", "setup-overlay.sh", "smoke_test.sh"):
        script = overlay_dir / name
        if script.is_file() and not _bash_syntax_ok(script):
            errors.append(f"{cid} overlay {name} fails bash -n")
    return errors


def check_design(
    spec: dict[str, Any],
    design: dict[str, Any],
    candidates_dir: Path | None = None,
    env_state: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> list[str]:
    """Phase 05: each candidate is instruction.md + task.toml + overlay environment/."""
    errors: list[str] = []
    target = spec["target"]
    budget = candidate_budget(spec)
    candidates = design.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != budget:
        errors.append(f"design.candidates must have exactly {budget} entries")
        candidates = candidates if isinstance(candidates, list) else []
    ids: set[str] = set()
    candidates_root = Path(candidates_dir) if candidates_dir is not None else Path("/synthesis/output/candidates")
    if env_state is None:
        for env_state_path in (
            Path("/synthesis/state/03_environment.json"),
        ):
            if env_state_path.is_file():
                try:
                    env_state = load_json(env_state_path)
                except Exception:  # noqa: BLE001
                    env_state = None
                else:
                    break
    env_workdir = (env_state or {}).get("workdir")
    difficulty = target.get("difficulty")
    band = DIFFICULTY_EXPERT_MINUTES.get(difficulty)
    if plan is None:
        plan_path = Path("/synthesis/state/04_simula_plan.json")
        if plan_path.is_file():
            try:
                loaded_plan = load_json(plan_path)
            except Exception:  # noqa: BLE001
                plan = None
            else:
                plan = loaded_plan if isinstance(loaded_plan, dict) else None
    slots_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(plan, dict):
        for slot in plan.get("slots") or []:
            if isinstance(slot, dict) and isinstance(slot.get("id"), str):
                slots_by_id[slot["id"]] = slot

    def _num(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

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
                f"candidate {candidate_id!r} is not a slot id from 04_simula_plan"
            )
        elif slot is not None:
            for key in SIMULA_VOCAB_KEYS:
                if candidate.get(key) != slot.get(key):
                    errors.append(
                        f"candidate {candidate_id!r} {key} must equal slot {key} "
                        f"{slot.get(key)!r}"
                    )

        for singular in ("task_type", "task_types", "domain", "language", "oracle_type", "tag", "subdomain"):
            if singular in candidate:
                errors.append(
                    f"candidate {candidate_id!r} uses {singular!r}; "
                    "use the list fields tags / domains / subdomains / languages / oracle_types"
                )
        ctags = candidate.get("tags")
        domain = candidate.get("domains")
        subdomain = candidate.get("subdomains")
        language = candidate.get("languages")
        coracle = candidate.get("oracle_types")
        parent_tags = target["tags"]
        parent_oracles = target["oracle_types"]
        parent_domains = target["domains"]
        parent_subdomains = target["subdomains"]
        parent_languages = target["languages"]
        errors.extend(
            _subset_of(
                ctags,
                parent_tags,
                f"candidate {candidate_id!r} tags",
                min_len=2 if len(parent_tags) >= 2 else 1,
            )
        )
        errors.extend(
            _subset_of(
                domain,
                parent_domains,
                f"candidate {candidate_id!r} domains",
                min_len=2 if len(parent_domains) >= 2 else 1,
            )
        )
        errors.extend(
            _subset_of(
                subdomain,
                parent_subdomains,
                f"candidate {candidate_id!r} subdomains",
                min_len=2 if len(parent_subdomains) >= 2 else 1,
            )
        )
        errors.extend(
            _check_subdomains(
                subdomain,
                domain if isinstance(domain, list) else [],
                f"candidate {candidate_id!r} subdomains",
            )
        )
        errors.extend(
            _subset_of(
                language,
                parent_languages,
                f"candidate {candidate_id!r} languages",
                min_len=2 if len(parent_languages) >= 2 else 1,
            )
        )
        errors.extend(
            _subset_of(
                coracle,
                parent_oracles,
                f"candidate {candidate_id!r} oracle_types",
                min_len=2 if len(parent_oracles) >= 2 else 1,
            )
        )
        env_build = candidate.get("env_build")
        if env_build not in ENV_BUILD_STATUSES:
            errors.append(
                f"candidate {candidate_id!r} env_build must be one of {list(ENV_BUILD_STATUSES)}"
            )
        oracle_tools = candidate.get("oracle_tools")
        if not isinstance(oracle_tools, list):
            errors.append(f"candidate {candidate_id!r} oracle_tools must be a list (empty means bash-only)")
        else:
            for tool in oracle_tools:
                if (
                    not isinstance(tool, str)
                    or not tool.strip()
                    or "/" in tool
                    or " " in tool
                    or tool != tool.strip()
                ):
                    errors.append(
                        f"candidate {candidate_id!r} oracle_tools entries must be argv0 names "
                        f"(no spaces or paths); got {tool!r}"
                    )
                    break

        overlay_dir = candidates_root / candidate_id / "environment"
        errors.extend(
            check_overlay(
                spec,
                candidate_id,
                overlay_dir,
                env_build if env_build in ENV_BUILD_STATUSES else None,
            )
        )
        if isinstance(oracle_tools, list):
            entrypoints = _entrypoint_argv0(env_state)
            for tool in oracle_tools:
                if not isinstance(tool, str) or not tool.strip() or "/" in tool or " " in tool:
                    continue
                if tool in entrypoints:
                    continue
                if not _overlay_installs_tool(overlay_dir, tool):
                    errors.append(
                        f"candidate {candidate_id!r} oracle_tool {tool!r} is not a sealed-base "
                        "entrypoint and is not installed in the overlay "
                        "(setup-overlay.sh / setup.sh / Dockerfile)"
                    )
                elif env_build == "not_required":
                    errors.append(
                        f"candidate {candidate_id!r} oracle_tool {tool!r} needs an overlay "
                        "install; env_build cannot be not_required"
                    )

        instruction_file = candidates_root / candidate_id / "instruction.md"
        if not instruction_file.is_file() or not instruction_file.read_text(encoding="utf-8", errors="replace").strip():
            errors.append(f"candidate {candidate_id!r} missing non-empty instruction.md")
        else:
            ascii_err = _non_ascii_error(instruction_file, f"candidate {candidate_id!r} instruction.md")
            if ascii_err:
                errors.append(ascii_err)

        toml_file = candidates_root / candidate_id / "task.toml"
        if not toml_file.is_file() or not toml_file.read_text(encoding="utf-8", errors="replace").strip():
            errors.append(f"candidate {candidate_id!r} missing non-empty task.toml")
            continue
        ascii_err = _non_ascii_error(toml_file, f"candidate {candidate_id!r} task.toml")
        if ascii_err:
            errors.append(ascii_err)

        parsed, parse_error = _read_candidate_task_toml(toml_file)
        if parsed is None:
            errors.append(f"candidate {candidate_id!r} task.toml does not parse: {parse_error}")
            continue
        if "steps" in parsed:
            errors.append(f"candidate {candidate_id!r} task.toml must be single-step (no [[steps]])")
        cid = f"candidate {candidate_id!r}"
        task_table = parsed.get("task")
        if not isinstance(task_table, dict) or not str(task_table.get("name", "")).strip():
            errors.append(f"{cid} task.toml needs [task].name")
        else:
            if not isinstance(task_table.get("description"), str) or not task_table["description"].strip():
                errors.append(f"{cid} task.toml needs [task].description")
            keywords = task_table.get("keywords")
            if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
                errors.append(f"{cid} task.toml needs a non-empty [task].keywords list")
        for section in ("verifier", "agent", "environment", "metadata"):
            if not isinstance(parsed.get(section), dict):
                errors.append(f"{cid} task.toml needs [{section}]")

        # [metadata]: vocabulary lists plus Terminal-Bench taxonomy fields.
        metadata = parsed.get("metadata") if isinstance(parsed.get("metadata"), dict) else {}
        for key, expected in (
            ("tags", ctags),
            ("domains", domain),
            ("subdomains", subdomain),
            ("languages", language),
            ("oracle_types", coracle),
        ):
            if metadata.get(key) != expected:
                errors.append(f"{cid} task.toml [metadata].{key} must match index list {expected!r}")
        for leftover in ("task_type", "task_types", "domain", "language", "oracle_type", "tag", "subdomain"):
            if leftover in metadata:
                errors.append(
                    f"{cid} task.toml [metadata] uses {leftover!r}; "
                    "use tags / domains / subdomains / languages / oracle_types lists"
                )
        if difficulty and metadata.get("difficulty") != difficulty:
            errors.append(f"{cid} task.toml [metadata].difficulty must be {difficulty!r}")
        category = metadata.get("category")
        allowed_categories = [
            _packaged_category(item) for item in (domain or []) if isinstance(item, str)
        ]
        if category not in allowed_categories:
            errors.append(
                f"{cid} task.toml [metadata].category must be one of {allowed_categories} "
                "(Terminal-Bench Title Case of a candidate domain)"
            )
        subcategory = metadata.get("subcategory")
        allowed_subcategories = [
            _packaged_subcategory(item) for item in (subdomain or []) if isinstance(item, str)
        ]
        if subcategory not in allowed_subcategories:
            errors.append(
                f"{cid} task.toml [metadata].subcategory must be one of {allowed_subcategories} "
                "(seed Title Case or kebab extension from candidate.subdomains)"
            )
        meta_tags = metadata.get("tags")
        if not isinstance(meta_tags, list) or not meta_tags:
            errors.append(f"{cid} task.toml [metadata].tags must match the index tags list")
        expert = _num(metadata.get("expert_time_estimate_min"))
        junior = _num(metadata.get("junior_time_estimate_min"))
        if expert is None or expert <= 0:
            errors.append(f"{cid} task.toml [metadata].expert_time_estimate_min must be a positive number")
        elif band and not (band[0] <= expert <= band[1]):
            errors.append(
                f"{cid} expert_time_estimate_min {expert} is outside the {difficulty!r} band "
                f"{band[0]}-{band[1]} min"
            )
        if junior is None or junior <= 0:
            errors.append(f"{cid} task.toml [metadata].junior_time_estimate_min must be a positive number")
        elif expert is not None and junior < expert * JUNIOR_MULTIPLIER_MIN:
            errors.append(
                f"{cid} junior_time_estimate_min must be at least {JUNIOR_MULTIPLIER_MIN}x the expert estimate"
            )

        # [environment]: runtime network public; resources derived from the sealed base.
        environment = parsed.get("environment") if isinstance(parsed.get("environment"), dict) else {}
        mode = environment.get("network_mode")
        if mode is not None and mode != "public":
            errors.append(
                f"{cid} task.toml [environment].network_mode must be 'public' "
                f"(Harbor agent install needs runtime network; got {mode!r})"
            )
        build_timeout = _num(environment.get("build_timeout_sec"))
        if build_timeout is None or build_timeout < 600:
            errors.append(f"{cid} [environment].build_timeout_sec must be a number >= 600")
        for key, low in (("cpus", 1), ("memory_mb", 1024), ("storage_mb", 4096)):
            value = environment.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < low:
                errors.append(f"{cid} [environment].{key} must be an integer >= {low}")
        if env_workdir and environment.get("workdir") not in (None, env_workdir):
            errors.append(
                f"{cid} [environment].workdir must be {env_workdir!r} (sealed base workdir) when set"
            )
        if environment.get("docker_image") is not None:
            errors.append(f"{cid} [environment].docker_image must not be set; the package builds environment/Dockerfile")

        # [agent]/[verifier] timeouts. expert_time_estimate_min is SOTA-agent
        # wall-clock minutes, so the agent budget must cover that estimate.
        for section, low in (("verifier", 60.0), ("agent", 300.0)):
            table = parsed.get(section) if isinstance(parsed.get(section), dict) else {}
            timeout = _num(table.get("timeout_sec"))
            if timeout is None or timeout < low:
                errors.append(f"{cid} [{section}].timeout_sec must be a number >= {low:g}")
        agent_timeout = _num((parsed.get("agent") or {}).get("timeout_sec")) if isinstance(parsed.get("agent"), dict) else None
        if agent_timeout is not None and expert is not None and agent_timeout < expert * 60:
            errors.append(
                f"{cid} [agent].timeout_sec {agent_timeout:g} is below the SOTA estimate "
                f"({expert:g} min); give the agent at least that wall-clock budget"
            )
    if slots_by_id:
        missing = sorted(set(slots_by_id) - ids)
        extra = sorted(ids - set(slots_by_id))
        if missing or extra:
            errors.append(
                "design.candidates ids must equal 04_simula_plan slot ids "
                f"(missing={missing}, extra={extra})"
            )
    return errors


def check_review(
    spec: dict[str, Any],
    design: dict[str, Any],
    review: dict[str, Any],
    candidates_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    candidates = design.get("candidates")
    reviews = review.get("reviews")
    approved = review.get("approved_candidate_ids")
    candidates_root = Path(candidates_dir) if candidates_dir is not None else Path("/synthesis/output/candidates")
    if not isinstance(candidates, list) or not isinstance(reviews, list):
        return ["review.reviews and design.candidates must be lists"]
    candidate_ids = {c.get("id") for c in candidates if isinstance(c, dict)}
    review_ids = [item.get("candidate_id") for item in reviews if isinstance(item, dict)]
    if set(review_ids) != candidate_ids or len(review_ids) != len(candidate_ids):
        errors.append("review must contain exactly one review for every candidate")
    if not isinstance(approved, list) or not approved:
        errors.append("review.approved_candidate_ids must be a non-empty list")
        approved = []
    if len(set(approved)) != len(approved) or not set(approved).issubset(candidate_ids):
        errors.append("review.approved_candidate_ids must be unique candidate ids")
    approved_set = set(approved)
    design_by_id = {
        item.get("id"): item
        for item in candidates
        if isinstance(item, dict)
    }
    for item in reviews:
        if not isinstance(item, dict):
            errors.append("review entries must be objects")
            continue
        candidate_id = item.get("candidate_id")
        scores = item.get("scores")
        qualifies = False
        if not isinstance(scores, dict):
            errors.append(f"review {candidate_id!r} scores must be an object")
        else:
            for key in REVIEW_SCORE_KEYS:
                value = scores.get(key)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= float(value) <= 1:
                    errors.append(f"review {candidate_id!r} score {key} must be in [0, 1]")
            qualifies = all(
                isinstance(scores.get(key), (int, float))
                and not isinstance(scores.get(key), bool)
                and float(scores[key]) >= REVIEW_MIN_SCORE
                for key in REVIEW_SCORE_KEYS
            )
        checks = item.get("checks")
        failed_checks: list[str] = []
        if not isinstance(checks, dict):
            errors.append(f"review {candidate_id!r} checks must be an object")
        else:
            for key in REVIEW_CHECK_KEYS:
                entry = checks.get(key)
                outcome = entry.get("outcome") if isinstance(entry, dict) else None
                if outcome not in REVIEW_CHECK_OUTCOMES:
                    errors.append(
                        f"review {candidate_id!r} check {key} needs outcome in {list(REVIEW_CHECK_OUTCOMES)}"
                    )
                elif outcome == "fail":
                    failed_checks.append(key)
        approved_flag = item.get("approved")
        if not isinstance(approved_flag, bool):
            errors.append(f"review {candidate_id!r} approved must be boolean")
            continue
        in_list = candidate_id in approved_set
        if approved_flag != in_list:
            errors.append(
                f"review {candidate_id!r} approved={approved_flag} does not match approved_candidate_ids"
            )
        if in_list and not qualifies:
            errors.append(
                f"review {candidate_id!r} is approved but has a score below {REVIEW_MIN_SCORE}"
            )
        if in_list and failed_checks:
            errors.append(
                f"review {candidate_id!r} is approved but failed checks: {failed_checks}"
            )
        design_entry = design_by_id.get(candidate_id) or {}
        if in_list and design_entry.get("env_build") == "failed":
            errors.append(
                f"review {candidate_id!r} is approved but overlay env_build=failed"
            )
        if not in_list:
            issues = item.get("blocking_issues")
            if not isinstance(issues, list) or not issues:
                errors.append(f"review {candidate_id!r} needs a blocking_issues reason when rejected")
        edits = item.get("edits", [])
        if edits is None:
            edits = []
        if not isinstance(edits, list):
            errors.append(f"review {candidate_id!r} edits must be a list")
        else:
            prefix = f"/synthesis/output/candidates/{candidate_id}/"
            for edit in edits:
                if not isinstance(edit, dict):
                    errors.append(f"review {candidate_id!r} edit entries must be objects")
                    continue
                path = edit.get("path")
                reason = edit.get("reason")
                if not isinstance(path, str) or not path.startswith(prefix):
                    errors.append(
                        f"review {candidate_id!r} edit path must stay under {prefix!r}"
                    )
                else:
                    rel = path[len(prefix) :]
                    allowed = rel in {"instruction.md", "task.toml"} or rel.startswith(
                        "environment/"
                    )
                    if not allowed:
                        errors.append(
                            f"review {candidate_id!r} may only edit instruction.md, "
                            f"task.toml, or overlay environment/ (got {path!r})"
                        )
                if not isinstance(reason, str) or not reason.strip():
                    errors.append(f"review {candidate_id!r} edit needs a non-empty reason")
        if in_list:
            for rel, kind in (("instruction.md", "instruction.md"), ("task.toml", "task.toml")):
                ascii_err = _non_ascii_error(
                    candidates_root / str(candidate_id) / rel,
                    f"review {candidate_id!r} {kind}",
                )
                if ascii_err:
                    errors.append(ascii_err)
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


ENVIRONMENT_FILES = (
    "Dockerfile",
    "setup.sh",
    "setup-overlay.sh",
    "smoke_test.sh",
)
NETWORK_POLICIES = ("none", "build_only", "runtime_required")
BUILD_MODES = ("docker", "static")
BUILD_STATUSES = ("passed", "failed")


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
    if not any(line.upper().startswith("RUN ") and "setup.sh" in line for line in lines):
        errors.append("Dockerfile must RUN setup.sh (for example: RUN bash /opt/env/setup.sh)")
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

    for name in ENVIRONMENT_FILES:
        if not (env_dir / name).is_file():
            errors.append(f"missing {env_dir / name}")
    if not (env_dir / "assets").is_dir():
        errors.append(f"missing assets directory {env_dir / 'assets'}")

    mode = state.get("deployment_mode")
    if mode not in ("single", "compose"):
        errors.append("deployment_mode must be single or compose")
    policy = state.get("network_policy")
    if policy not in NETWORK_POLICIES:
        errors.append(f"network_policy must be one of {list(NETWORK_POLICIES)}")
    allow_external = bool(spec.get("generation", {}).get("allow_external_assets"))
    if not allow_external and policy == "runtime_required":
        errors.append("network_policy runtime_required is forbidden when allow_external_assets is false")
    services = state.get("services")
    if not isinstance(services, list) or not services:
        errors.append("services must be a non-empty list")
    else:
        for service in services:
            if not isinstance(service, dict) or not service.get("name"):
                errors.append("every service needs a name")
                break
    for key in ("workdir", "data_dir", "results_dir"):
        value = state.get(key)
        if not isinstance(value, str) or not value.startswith("/"):
            errors.append(f"{key} must be an absolute path")
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

    compose_file = env_dir / "docker-compose.yaml"
    if mode == "compose":
        if not compose_file.is_file():
            errors.append("compose mode needs docker-compose.yaml")
        elif "services:" not in compose_file.read_text(encoding="utf-8", errors="replace"):
            errors.append("docker-compose.yaml has no services section")
    elif mode == "single" and compose_file.exists():
        errors.append("single mode must not ship docker-compose.yaml")

    dockerfile = env_dir / "Dockerfile"
    dockerfile_text = ""
    if dockerfile.is_file():
        dockerfile_text = dockerfile.read_text(encoding="utf-8", errors="replace")
        errors.extend(check_dockerfile(dockerfile_text, env_dir, spec))
        if "setup-overlay.sh" not in dockerfile_text:
            errors.append("Dockerfile must COPY and RUN setup-overlay.sh after setup.sh")

    bash = shutil.which("bash")
    if bash:
        for name in ("setup.sh", "setup-overlay.sh", "smoke_test.sh"):
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
        for key in ("workdir", "data_dir", "results_dir"):
            value = state.get(key)
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


def check_repo_gate(spec: dict[str, Any], gate: dict[str, Any]) -> list[str]:
    """Combined hard filter + score gate."""
    return check_filter(gate) + check_score(spec, gate)


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


def _verifier_runtime_errors(cid: Any, tests_dir: Path, oracle_tools: list[str] | None = None) -> list[str]:
    """Phase 07/08 tests must stay offline; extras come from phase-05 oracle_tools."""
    errors: list[str] = []
    allowed = {str(t) for t in (oracle_tools or [])}
    if not tests_dir.is_dir():
        return errors
    for path in tests_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".sh", ".py", ".bash"} and path.name != "test.sh":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.as_posix()
        if _VERIFY_INSTALL_RE.search(text):
            errors.append(
                f"{cid}: {rel} installs packages at verify time; "
                "phase 05 must put observation tools in the overlay / oracle_tools"
            )
        if _VERIFY_PYTEST_RE.search(text) and "pytest" not in allowed:
            errors.append(
                f"{cid}: {rel} uses pytest but oracle_tools does not list pytest"
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
    path = Path("/synthesis/state/05_task_design.json")
    if not path.is_file():
        return None
    try:
        doc = load_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def check_verifiers(
    review: dict[str, Any],
    state: dict[str, Any],
    candidates_dir: Path,
    design: dict[str, Any] | None = None,
) -> list[str]:
    """Phase 07: one Harbor-style tests/test.sh per approved candidate."""
    errors: list[str] = []
    candidates_dir = Path(candidates_dir)
    approved = review.get("approved_candidate_ids")
    if not isinstance(approved, list):
        return ["approved_candidate_ids must be a list"]
    records = state.get("verifiers")
    if not isinstance(records, list) or not records:
        return ["verifiers must be a non-empty list"]
    ids = [r.get("candidate_id") if isinstance(r, dict) else None for r in records]
    if sorted(map(str, ids)) != sorted(map(str, approved)) or len(set(ids)) != len(ids):
        errors.append(f"verifier candidate ids {ids} must be exactly the approved ids {approved}")
    if design is None:
        design = _load_design_state()
    tools_by_id = _oracle_tools_by_id(design)
    for record in records:
        if not isinstance(record, dict):
            errors.append("verifier records must be objects")
            continue
        cid = record.get("candidate_id")
        expected = candidates_dir / str(cid) / "tests" / "test.sh"
        if not expected.is_file():
            errors.append(f"{cid}: missing {expected.as_posix()}")
            continue
        if not _is_executable(expected):
            errors.append(f"{cid}: test.sh is not executable")
        source = expected.read_text(encoding="utf-8", errors="replace")
        if not source.strip():
            errors.append(f"{cid}: test.sh is empty")
        elif "reward.txt" not in source:
            errors.append(f"{cid}: test.sh never writes /logs/verifier/reward.txt")
        if not _bash_syntax_ok(expected):
            errors.append(f"{cid}: test.sh fails bash -n")
        if str(cid) in tools_by_id and tools_by_id[str(cid)] is None:
            errors.append(f"{cid}: 05_task_design.json is missing oracle_tools")
        errors.extend(_verifier_runtime_errors(cid, expected.parent, tools_by_id.get(str(cid))))
        requirements = record.get("checked_requirements")
        if not isinstance(requirements, list) or not requirements:
            errors.append(f"{cid}: checked_requirements must be a non-empty list")
        else:
            for item in requirements:
                if not isinstance(item, dict) or not item.get("requirement") or not item.get("assertion"):
                    errors.append(f"{cid}: every checked_requirement needs requirement and assertion")
                    break
    return errors


def check_verifier_review(state: dict[str, Any], review: dict[str, Any], candidates_dir: Path) -> list[str]:
    """Phase 08: rubric verdicts per verifier, syntax re-checked."""
    errors: list[str] = []
    candidates_dir = Path(candidates_dir)
    expected_ids = [item.get("candidate_id") for item in state.get("verifiers", []) if isinstance(item, dict)]
    reviews = review.get("reviews")
    if not isinstance(reviews, list):
        return ["reviews must be a list"]
    ids = [item.get("candidate_id") if isinstance(item, dict) else None for item in reviews]
    if sorted(map(str, ids)) != sorted(map(str, expected_ids)) or len(set(ids)) != len(ids):
        errors.append(f"reviews {ids} must cover exactly the verifier records {expected_ids}")
    approved_list = review.get("approved_candidate_ids")
    if not isinstance(approved_list, list) or len(set(map(str, approved_list))) != len(approved_list):
        errors.append("approved_candidate_ids must be a list of unique ids")
        approved_list = []
    approved_set = set(map(str, approved_list))
    if not approved_set.issubset(set(map(str, ids))):
        errors.append("approved_candidate_ids contains unknown candidates")
    tools_by_id = _oracle_tools_by_id(_load_design_state())
    for item in reviews:
        if not isinstance(item, dict):
            errors.append("review entries must be objects")
            continue
        cid = str(item.get("candidate_id"))
        tests_dir = candidates_dir / cid / "tests"
        syntax = _bash_syntax_ok(tests_dir / "test.sh")
        if item.get("syntax_ok") is not syntax:
            errors.append(f"{cid}: syntax_ok must be {syntax} (bash -n result)")
        errors.extend(_verifier_runtime_errors(cid, tests_dir, tools_by_id.get(cid)))
        checks = item.get("checks")
        failed: list[str] = []
        if not isinstance(checks, dict):
            errors.append(f"{cid}: checks must be an object")
        else:
            for key in VERIFIER_CHECK_KEYS:
                entry = checks.get(key)
                outcome = entry.get("outcome") if isinstance(entry, dict) else None
                if outcome not in REVIEW_CHECK_OUTCOMES:
                    errors.append(f"{cid}: check {key} needs outcome in {list(REVIEW_CHECK_OUTCOMES)}")
                elif outcome == "fail":
                    failed.append(key)
        if not isinstance(item.get("issues"), list):
            errors.append(f"{cid}: issues must be a list")
        approved_flag = item.get("approved")
        if not isinstance(approved_flag, bool):
            errors.append(f"{cid}: approved must be a boolean")
            continue
        in_list = cid in approved_set
        if approved_flag != in_list:
            errors.append(f"{cid}: approved flag does not match approved_candidate_ids")
        if in_list and not syntax:
            errors.append(f"{cid}: approved but test.sh fails bash -n")
        if in_list and failed:
            errors.append(f"{cid}: approved but failed checks: {failed}")
        if not in_list and not item.get("issues"):
            errors.append(f"{cid}: rejected verifiers need at least one issue")
        edits = item.get("edits", [])
        if edits is None:
            edits = []
        if not isinstance(edits, list):
            errors.append(f"{cid}: edits must be a list")
        else:
            tests_prefix = f"/synthesis/output/candidates/{cid}/tests/"
            instr = f"/synthesis/output/candidates/{cid}/instruction.md"
            for edit in edits:
                if not isinstance(edit, dict):
                    errors.append(f"{cid}: edit entries must be objects")
                    continue
                path = edit.get("path")
                reason = edit.get("reason")
                if not isinstance(path, str):
                    errors.append(f"{cid}: edit path must be a string")
                    continue
                if not (path.startswith(tests_prefix) or path == instr):
                    errors.append(
                        f"{cid}: edit path must be under {tests_prefix!r} "
                        f"(or the candidate instruction.md for typo-only fixes)"
                    )
                if not isinstance(reason, str) or not reason.strip():
                    errors.append(f"{cid}: edit needs a non-empty reason")
    if not approved_list:
        errors.append("no verifier was approved")
    return errors


PACKAGE_TOP_LEVEL = {"task.toml", "instruction.md", "README.md", "environment", "tests"}
PACKAGE_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){0,2}$")
TASK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
TASK_TOML_TOP_KEYS = {
    "schema_version", "multi_step_reward_strategy", "task", "metadata", "verifier",
    "agent", "environment", "solution", "source", "artifacts",
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
# Runtime Harbor network for packaged tasks. Independent of 04 network_policy
# (that field only describes whether the image build / the task itself needs
# the network). Agent install needs public.
NETWORK_MODE_FOR_POLICY = {"none": "public", "build_only": "public", "runtime_required": "public"}


def _tree_files(root: Path) -> dict[str, Path]:
    return {item.relative_to(root).as_posix(): item for item in root.rglob("*") if item.is_file()}


def _same_bytes(left: Path, right: Path) -> bool:
    return left.is_file() and right.is_file() and left.read_bytes() == right.read_bytes()


def check_task_toml_assembled(text: str, slug: str, env_state: dict[str, Any]) -> list[str]:
    """Packaged task.toml must stay a valid single-step Harbor file (from phase 05/06)."""
    import tomllib

    errors: list[str] = []
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [f"task.toml does not parse: {exc}"]
    unknown = sorted(set(parsed) - TASK_TOML_TOP_KEYS)
    if unknown:
        errors.append(f"task.toml has unknown top-level keys {unknown}")
    if "steps" in parsed:
        errors.append("packaged task must be single-step (no [[steps]])")
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
    expected = NETWORK_MODE_FOR_POLICY.get(env_state.get("network_policy"), "public")
    mode = environment.get("network_mode")
    if mode is not None and mode != expected:
        errors.append(
            f"[environment].network_mode must be {expected!r} (Harbor agent "
            f"install needs runtime network; got {mode!r})"
        )
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
    spec: dict[str, Any],
    env_state: dict[str, Any],
    design_state: dict[str, Any],
    verifier_state: dict[str, Any],
    review_state: dict[str, Any],
    env_dir: Path,
    candidates_dir: Path,
    generated_dir: Path,
) -> list[str]:
    """Assemble-only packages: sealed base merged with overlay, plus instruction/tests."""
    errors: list[str] = []
    env_dir, candidates_dir, generated_dir = Path(env_dir), Path(candidates_dir), Path(generated_dir)
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

    approved = [str(x) for x in review_state.get("approved_candidate_ids", [])]
    if not approved:
        return ["approved_candidate_ids is empty"]
    ids = [str(item.get("candidate_id")) if isinstance(item, dict) else None for item in tasks]
    if ids != approved:
        # Prefer same order as approved list; still require same multiset.
        if sorted(map(str, ids)) != sorted(approved) or len(set(ids)) != len(ids):
            errors.append(f"manifest candidate ids {ids} must be exactly the approved ids {approved}")
        else:
            errors.append(f"manifest candidate order {ids} should match approved order {approved}")
    expected_commit = (spec.get("source_repo") or {}).get("commit") or "unknown"
    design_ids = {
        str(c.get("id"))
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
        if cid not in design_ids:
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
        for rel in ("task.toml", "instruction.md", "README.md", "environment/Dockerfile", "tests/test.sh"):
            path = package / rel
            if not path.is_file() or not path.read_bytes().strip():
                errors.append(f"{slug}: missing or empty {rel}")

        # environment: sealed base merged with the candidate overlay (overlay wins)
        overlay_dir = candidates_dir / cid / "environment"
        merged_env = dict(_tree_files(env_dir))
        if overlay_dir.is_dir():
            merged_env.update(_tree_files(overlay_dir))
        package_env = _tree_files(package / "environment") if (package / "environment").is_dir() else {}
        if set(merged_env) != set(package_env):
            errors.append(
                f"{slug}: environment/ must be base merged with {overlay_dir.as_posix()} "
                f"(missing {sorted(set(merged_env) - set(package_env))[:5]}, "
                f"extra {sorted(set(package_env) - set(merged_env))[:5]})"
            )
        else:
            changed = [
                rel for rel in merged_env if not _same_bytes(merged_env[rel], package_env[rel])
            ]
            if changed:
                errors.append(f"{slug}: environment files differ from base+overlay merge: {changed[:5]}")

        # tests: exact tree copy from candidate
        source_tests_dir = candidates_dir / cid / "tests"
        if not source_tests_dir.is_dir():
            errors.append(f"{slug}: missing candidate tests dir {source_tests_dir.as_posix()}")
        else:
            expected_tests = _tree_files(source_tests_dir)
            actual_tests = _tree_files(package / "tests") if (package / "tests").is_dir() else {}
            if set(expected_tests) != set(actual_tests):
                errors.append(f"{slug}: tests/ must be a verbatim copy of {source_tests_dir.as_posix()}")
            else:
                changed = [rel for rel in expected_tests if not _same_bytes(expected_tests[rel], actual_tests[rel])]
                if changed:
                    errors.append(f"{slug}: tests files differ from candidate tests: {changed[:5]}")
            test_script = package / "tests" / "test.sh"
            if test_script.is_file() and not _is_executable(test_script):
                errors.append(f"{slug}: tests/test.sh is not executable")

        # instruction: exact copy
        src_instruction = candidates_dir / cid / "instruction.md"
        if not src_instruction.is_file():
            errors.append(f"{slug}: missing candidate instruction.md")
        elif not _same_bytes(src_instruction, package / "instruction.md"):
            errors.append(f"{slug}: instruction.md must be a byte-for-byte copy of the candidate file")
        ascii_err = _non_ascii_error(package / "instruction.md", f"{slug}/instruction.md")
        if ascii_err:
            errors.append(ascii_err)
        ascii_err = _non_ascii_error(package / "task.toml", f"{slug}/task.toml")
        if ascii_err:
            errors.append(ascii_err)

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
    "01_repo_profile": {
        "path": "/synthesis/state/01_repo_profile.json",
        "skeleton": {
            "source_repo": {"path": "", "commit": "unknown"},
            "languages": [],
            "domains": [],
            "subdomains": [],
            "entrypoints": [],
            "tags": [],
        },
    },
    "02_repo_gate": {
        "path": "/synthesis/state/02_repo_gate.json",
        "skeleton": {
            "accepted": False,
            "hard_checks": {
                "source_present": False,
                "executable_logic": False,
                "build_or_runtime_path": False,
                "target_alignment": False,
                "license_known": False,
            },
            "blockers": ["skeleton: not yet evaluated"],
            "repo_score": 0.0,
            "buildability_score": 0.0,
            "task_potential_score": 0.0,
            "decision": "reject",
        },
    },
    "03_environment": {
        "path": "/synthesis/state/03_environment.json",
        "skeleton": {
            "deployment_mode": "single",
            "base_image": "",
            "services": [],
            "dependencies": {"system": [], "language": [], "pinned": False},
            "asset_paths": [],
            "network_policy": "build_only",
            "workdir": "/app",
            "data_dir": "/data",
            "results_dir": "/results",
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
    "04_simula_plan": {
        "path": "/synthesis/state/04_simula_plan.json",
        "skeleton": {"global": [], "slots": []},
    },
    "05_task_design": {
        "path": "/synthesis/state/05_task_design.json",
        "skeleton": {"candidates": []},
    },
    "06_task_review": {
        "path": "/synthesis/state/06_task_review.json",
        "skeleton": {"reviews": [], "approved_candidate_ids": []},
    },
    "07_verifier": {
        "path": "/synthesis/state/07_verifier.json",
        "skeleton": {"verifiers": []},
    },
    "08_verifier_review": {
        "path": "/synthesis/state/08_verifier_review.json",
        "skeleton": {"reviews": [], "approved_candidate_ids": []},
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
            "usage: target_spec.py validate SPEC | check-profile SPEC PROFILE | "
            "check-filter FILTER | check-repo-gate SPEC GATE | "
            "check-simula-plan SPEC PLAN ENV_STATE | "
            "check-design SPEC DESIGN [CANDIDATES_DIR] | "
            "check-review SPEC DESIGN REVIEW [CANDIDATES_DIR] | "
            "check-score SPEC SCORE | check-environment SPEC STATE ENV_DIR | "
            "check-verifiers REVIEW STATE CANDIDATES_DIR | "
            "check-verifier-review STATE06 STATE07 CANDIDATES_DIR | "
            "check-package SPEC STATE03 DESIGN05 STATE07 APPROVED_STATE ENV_DIR CANDIDATES_DIR GENERATED_DIR | "
            "ensure-handoff PHASE [--force] | require-handoff PHASE | "
            "list-handoffs | min-score SPEC",
            file=sys.stderr,
        )
        return 2
    command = argv[1]
    if command == "validate":
        spec = load_json(argv[2])
        return _fail(validate_spec(spec))
    if command == "min-score":
        spec = load_json(argv[2])
        errors = validate_spec(spec)
        if errors:
            return _fail(errors)
        print(min_repo_score(spec))
        return 0
    if command == "check-profile":
        spec = load_json(argv[2])
        profile = load_json(argv[3])
        return _fail(validate_spec(spec) + check_profile(spec, profile))
    if command == "check-filter":
        return _fail(check_filter(load_json(argv[2])))
    if command == "check-repo-gate":
        spec = load_json(argv[2])
        gate = load_json(argv[3])
        return _fail(validate_spec(spec) + check_repo_gate(spec, gate))
    if command == "check-simula-plan":
        if len(argv) < 4:
            print("check-simula-plan requires: SPEC PLAN [ENV_STATE]", file=sys.stderr)
            return 2
        spec = load_json(argv[2])
        plan = load_json(argv[3])
        env_state = load_json(argv[4]) if len(argv) > 4 else None
        return _fail(validate_spec(spec) + check_simula_plan(spec, plan, env_state=env_state))
    if command == "check-design":
        spec = load_json(argv[2])
        design = load_json(argv[3])
        candidates_dir = Path(argv[4]) if len(argv) > 4 else None
        return _fail(validate_spec(spec) + check_design(spec, design, candidates_dir=candidates_dir))
    if command == "check-review":
        spec = load_json(argv[2])
        design = load_json(argv[3])
        review = load_json(argv[4])
        candidates_dir = Path(argv[5]) if len(argv) > 5 else None
        return _fail(
            validate_spec(spec)
            + check_review(spec, design, review, candidates_dir=candidates_dir)
        )
    if command == "check-score":
        spec = load_json(argv[2])
        score = load_json(argv[3])
        return _fail(validate_spec(spec) + check_score(spec, score))
    if command == "check-environment":
        spec = load_json(argv[2])
        state = load_json(argv[3])
        errors = validate_spec(spec) + check_environment(spec, state, Path(argv[4]))
        if isinstance(state.get("build"), dict):
            errors.extend(check_environment_build(state))
        return _fail(errors)
    if command == "check-verifiers":
        return _fail(check_verifiers(load_json(argv[2]), load_json(argv[3]), Path(argv[4])))
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
        # SPEC STATE03 DESIGN05 STATE07 APPROVED_STATE ENV_DIR CANDIDATES_DIR GENERATED_DIR
        if len(argv) < 10:
            print(
                "check-package requires: SPEC STATE03 DESIGN05 STATE07 "
                "APPROVED_STATE ENV_DIR CANDIDATES_DIR GENERATED_DIR",
                file=sys.stderr,
            )
            return 2
        spec = load_json(argv[2])
        return _fail(
            validate_spec(spec)
            + check_package(
                spec,
                load_json(argv[3]),
                load_json(argv[4]),
                load_json(argv[5]),
                load_json(argv[6]),
                Path(argv[7]),
                Path(argv[8]),
                Path(argv[9]),
            )
        )
    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
