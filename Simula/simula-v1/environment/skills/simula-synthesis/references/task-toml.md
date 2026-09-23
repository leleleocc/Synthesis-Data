# Candidate task.toml, customized to the slot

Harbor parses this file with `TaskConfig.model_validate_toml()` and
`phase_contract.py` checks its alignment. The required sections are
`[task]`, `[metadata]`, `[environment]`, `[agent]`, and `[verifier]`.
Full field reference:
`/opt/terminaltraj/skills/harbor-task-creator/references/task-toml-reference.md`.

Phase 05 owns this file. Phase 06 only copies it. Phase 07 may make the
smallest packaged edit; it does not send the candidate back to phase 05.

Read the sealed slot `deployment_dimensions` and realize that preview.
Do not emit one generic manifest for every candidate.

## Layout from the slot

Each line applies only when the sealed slot has that value.

- If `container_mode=single`: one image; no compose service list.
- If `container_mode=multiple`: compose layout; primary service `main`.
- If `step_mode=single`: no `[[steps]]`.
- If `step_mode=multiple`: declare `[[steps]]` in the order recorded by phase
  04's `steps` list. Use its existing `steps/<name>/instruction.md` and add
  step-local or shared tests.
- If `verifier_mode=inline`: tests run in the agent environment.
- If `verifier_mode=separate`: set `verifier.environment_mode` and ship
  `Dockerfile` in every selected tests directory, baking its verifier into `/tests`.
  The agent environment is torn down before this verifier starts. Do not make
  verification depend on a service from the agent's compose stack; export its
  state with top-level `artifacts` or `[[verifier.collect]]`, then restore or
  recreate it in the verifier. A sidecar is valid only when it is managed
  independently and remains reachable after the agent environment stops.
- If `gpu=none`: `gpus = 0`.
- If `gpu=optional`: `gpus` is 0 or 1, matching the sealed allocation. A GPU
  task is still a single-container Dockerfile.
- If `gpu=required`: `gpus >= 1` and match sealed `resources.gpus`. Phase 02
  may allocate that quota when the target and phase 01 evidence request GPU.
- If `mcp=none`: do not declare `[[environment.mcp_servers]]`.
- If `mcp=optional`: declare `[[environment.mcp_servers]]` or omit it. A
  declared server follows the `mcp=required` transport rules.
- If `mcp=required`: declare `[[environment.mcp_servers]]`. Each server needs
  `name` and a Harbor transport: `sse`/`streamable-http` need `url`; `stdio`
  needs `command` that appears in the candidate environment. Agent network
  is `public`, so an HTTP MCP url is reachable.

## Identity, timeouts, network

`[task].name` is `<org>/<name>`; phase 06 may align the name with the package folder.
`[metadata].difficulty` is `plan.difficulty`. Category, subcategory, and
tags come from the parent global row.

Set `[environment]` resources to exactly `cpus = 4`, `memory_mb = 8192`,
`storage_mb = 10240`. `gpus` is 0 or 1 from the sealed allocation. Do not
raise or lower CPU, memory, or storage.

If `step_mode=single`: `[agent].timeout_sec` is 7200, `[verifier].timeout_sec`
is 600, and `[environment].build_timeout_sec` is 600. The instruction suffix
uses that 7200.

If `step_mode=multiple`: `[environment].build_timeout_sec` is 600. Every
`[[steps]]` sets `[steps.agent].timeout_sec` to 1800 and
`[steps.verifier].timeout_sec` to 300. Each step instruction suffix uses
that step's 1800. Also set the top-level `[agent].timeout_sec` to 1800 and
`[verifier].timeout_sec` to 300.

`[environment].network_mode` and `[agent].network_mode` are `public`.
`[verifier].network_mode` is `public`, or `no-network` only when the scenario
needs it, verifier dependencies are already installed, and
`verifier_mode` is not `separate`. Leave `allowed_hosts` empty. Do not set
`allow_internet`. When uncertain about compose, GPU, MCP, or `[[steps]]`
layout, consult
https://github.com/harbor-framework/harbor/tree/main/examples/tasks.
