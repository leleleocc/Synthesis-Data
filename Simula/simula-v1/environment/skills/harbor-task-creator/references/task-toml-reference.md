# task.toml Complete Field Reference

Parsed by `TaskConfig.model_validate_toml()` from `src/harbor/models/task/config.py`. All models are Pydantic BaseModels.

## Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `schema_version` | `str` | `"1.4"` | Config format version. Always `"1.4"` |
| `source` | `str \| None` | `None` | Provenance identifier (set automatically by adapters) |

## [metadata]

Free-form `dict[str, Any]`. No schema enforcement — any key/value pairs are accepted. Conventional keys used by Harbor tooling:

| Field | Type | Convention | Description |
|-------|------|------------|-------------|
| `author_name` | str | — | Task author name |
| `author_email` | str | — | Task author email |
| `difficulty` | str | — | `"easy"`, `"medium"`, `"hard"`, or `"unknown"` |
| `category` | str | — | `"programming"`, `"devops"`, `"data_analysis"`, etc. |
| `tags` | list[str] | — | Descriptive tags for filtering |
| `estimated_duration_sec` | int | — | Estimated task duration in seconds |
| `expert_time_estimate_min` | int | — | Minutes for a human expert |
| `junior_time_estimate_min` | int | — | Minutes for a junior developer |

Since metadata is a plain dict, you can add any custom keys your benchmark needs.

## [verifier]

Parsed into `VerifierConfig`. Controls how `test.sh` is executed.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout_sec` | `float` | `600.0` | Wall-clock timeout for test.sh execution |
| `env` | `dict[str, str]` | `{}` | Environment variables injected into test.sh execution |

The `env` values are resolved through `harbor.utils.env.resolve_env_vars` before injection. This means you can reference other environment variables in the values.

Example:
```toml
[verifier]
timeout_sec = 120.0
env = { PYTHONPATH = "/app", DATABASE_URL = "postgresql://user:pass@postgres:5432/testdb" }
```

## [agent]

Parsed into `AgentConfig`. Defines execution limits for the agent.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout_sec` | `float` | `600.0` | Max wall-clock seconds for the agent to work |

This timeout can be overridden at trial time with `--agent-timeout` or `--agent-timeout-multiplier` CLI flags.

## [environment]

Parsed into `EnvironmentConfig`. Specifies resource requirements and configuration for the sandbox.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `build_timeout_sec` | `float` | `600.0` | Max seconds for container image build |
| `docker_image` | `str \| None` | `None` | Pre-built image tag (skips Dockerfile build) |
| `cpus` | `int` | `1` | CPU cores allocated to the container |
| `memory_mb` | `int` | `2048` | Memory limit in MB |
| `storage_mb` | `int` | `10240` | Disk storage limit in MB (10 GB default) |
| `gpus` | `int` | `0` | Number of GPUs to allocate |
| `gpu_types` | `list[str] \| None` | `None` | Acceptable GPU types. Daytona accepts `H100`, `H200`, `RTX-PRO-6000`, `RTX-4090`, `RTX-5090`, and `MI355X`. Omit to accept any of those. |
| `allow_internet` | `bool` | `true` | Whether the container has network access |
| `skills_dir` | `str \| None` | `None` | Path to skills directory to install in the agent |
| `mcp_servers` | `list[MCPServerConfig]` | `[]` | MCP server configurations (see below) |

### GPU Notes

Daytona is the only environment backend. GPU tasks run with `-e daytona`.

- Daytona allocates GPUs only for a single-container Dockerfile task. A docker-compose task with `gpus > 0` raises `RuntimeError` at startup.
- When `gpu_types` is set, at least one entry must be a type Daytona provisions: `H100`, `H200`, `RTX-PRO-6000`, `RTX-4090`, `RTX-5090`, or `MI355X`. Other names, including `A100`, are rejected.
- Omit `gpu_types` to accept any provisioned type. GPU sandboxes are ephemeral.
- CLI override: `--override-gpus 1` at trial/job time.

### Network Access

When `allow_internet = false`, Harbor appends a `docker-compose-no-network.yaml` that sets `network_mode: none` on the main service. This fully isolates the container from the internet. Not all environment backends support this — check `can_disable_internet` on the backend.

### Deprecated Fields

These fields still work but emit `DeprecationWarning`:

| Deprecated Field | Type | Replacement | Conversion |
|------------------|------|-------------|------------|
| `memory` | `str \| None` | `memory_mb` | Parsed via `_parse_size_to_mb`: `"1G"` -> 1024, `"512M"` -> 512, `"256K"` -> 0 |
| `storage` | `str \| None` | `storage_mb` | Same conversion as memory |

Example: `memory = "4G"` is equivalent to `memory_mb = 4096`. Prefer the `_mb` fields in new tasks.

### Pre-built Images

Set `docker_image` to skip building from the Dockerfile entirely:

```toml
[environment]
docker_image = "ghcr.io/my-org/my-task-image:v1.2"
```

When set, Harbor pulls this image instead of building from `environment/Dockerfile`. The Dockerfile is ignored.

## [[steps]]

Parsed as a repeated TOML array of tables. Use `[[steps]]` only when the
slot preview is `step_mode=multiple`. A single-step slot must omit it.

Each step has at least `name`. Optional nested `[steps.agent]` and
`[steps.verifier]` override timeouts for that step. Harbor already parses
this factory's own `task.toml` this way. Do not add a decorative extra
step; steps must match the instruction's coupled constraints.

Example:

```toml
[[steps]]
name = "prepare"

[[steps]]
name = "verify"
```

When uncertain about compose, GPU, MCP, or `[[steps]]` layout, consult
https://github.com/harbor-framework/harbor/tree/main/examples/tasks.

## [[environment.mcp_servers]]

Parsed into `MCPServerConfig`. Use `[[double brackets]]` — this is a repeated TOML section (array of tables).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | (required) | Server identifier |
| `transport` | `str` | `"sse"` | `"sse"`, `"streamable-http"`, or `"stdio"` |
| `url` | `str \| None` | `None` | Server URL (required for `sse` and `streamable-http`) |
| `command` | `str \| None` | `None` | Executable path (required for `stdio`) |
| `args` | `list[str]` | `[]` | Command arguments (for `stdio` only) |

**Validation:** The `validate_transport_fields` Pydantic validator enforces:
- For `sse` and `streamable-http`: `url` must be provided
- For `stdio`: `command` must be provided

Example with both transport types:
```toml
[[environment.mcp_servers]]
name = "api-tools"
transport = "streamable-http"
url = "http://mcp-server:8000/mcp"

[[environment.mcp_servers]]
name = "file-tool"
transport = "stdio"
command = "/usr/local/bin/file-tool"
args = ["--json-output"]
```

## [solution]

Parsed into `SolutionConfig`. Controls the execution of `solution/solve.sh` by the Oracle Agent.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `env` | `dict[str, str]` | `{}` | Environment variables for solve.sh execution |

The Oracle Agent always injects `DEBIAN_FRONTEND=noninteractive` in addition to any variables defined here. Values are resolved through `resolve_env_vars`.

## Complete Example

```toml
schema_version = "1.4"

[metadata]
author_name = "Jane Smith"
author_email = "jane@example.com"
difficulty = "medium"
category = "programming"
tags = ["python", "algorithms", "sorting"]
estimated_duration_sec = 300
expert_time_estimate_min = 5
junior_time_estimate_min = 15

[verifier]
timeout_sec = 120.0
env = { PYTHONPATH = "/app" }

[agent]
timeout_sec = 600.0

[environment]
build_timeout_sec = 300.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
allow_internet = true

[[environment.mcp_servers]]
name = "code-tools"
transport = "streamable-http"
url = "http://mcp-server:8000/mcp"

[solution]
env = { DEBUG = "0" }
```

## Environment Backend

Daytona is the only environment backend. Select it with `-e daytona`.

| Backend | Class | GPUs | Disable Internet | Description |
|---------|-------|------|-----------------|-------------|
| `daytona` | `DaytonaEnvironment` | Yes, single-container only | Yes | Cloud sandbox. Compose tasks cannot receive a GPU. |

`gpu_types` must be chosen from `H100`, `H200`, `RTX-PRO-6000`, `RTX-4090`, `RTX-5090`, and `MI355X`.

## Reward File Reference

The verifier parses reward files in this priority order:

| File | Format | Example | Notes |
|------|--------|---------|-------|
| `/logs/verifier/reward.txt` | Single float as text | `1.0` | Parsed to `{"reward": float_value}`. Checked first. |
| `/logs/verifier/reward.json` | JSON object with named rewards | `{"reward": 1.0, "quality": 0.8}` | Only read if reward.txt doesn't exist. |
| `/logs/verifier/ctrf.json` | CTRF test results | (pytest-json-ctrf output) | Display only — NOT used for reward. Shown in Harbor Viewer. |

**Error conditions:**
- Neither reward.txt nor reward.json exists: `RewardFileNotFoundError`
- Reward file exists but is empty: `RewardFileEmptyError`
- Reward file content can't be parsed (non-numeric text, invalid JSON): `VerifierOutputParseError`

There is no `rewards.json` (plural) — the file must be named `reward.json`.
