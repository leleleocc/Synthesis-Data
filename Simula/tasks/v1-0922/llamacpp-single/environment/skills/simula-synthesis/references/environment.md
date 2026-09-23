# Environment, customized to the slot

This reference covers the shared base and each candidate's customized copy.
`phase_contract.py` checks the environment contract and on-disk alignment.

## Shared base (phase 02)

Keep the base generic enough that every later slot can copy it: clone
the pin, install language and build tools, declare paths and entrypoints,
install once any runtime the whole batch will need, smoke one entrypoint.
Do not plant a task-specific defect, golden, or per-slot fixture.

Prefer `ubuntu:24.04` unless the pinned source needs another runtime. Pin
versions, do not use `FROM --platform=...`, and keep Dockerfile COPY sources
inside the environment build context. Copy `assets/` when it exists. Do not copy
`tests/` or `solution/`, and do not install pytest in the shared base.

Topology belongs to this sealed base and follows phase 01 compose evidence,
not a later slot wish. If the repo has observed compose files, the base is
compose with primary service `main`. Otherwise prefer a single Dockerfile.
One batch cannot mix single and multiple container bases. Do not bind-mount
host paths. Health-check dependencies the agent needs. Verifier dependencies
are added in phase 05 as defined in `tests.md`.

Set resources to exactly 4 CPU, 8192 MB memory, and 10240 MB storage. GPU
stays 0 or 1. When phase 01
evidences a required GPU, set `resources.gpus = 1`; optional GPU may use 0 or
1. GPU allocation requires a single-container base.

The image must boot as a shared base. Clone once, build once, smoke once,
then stop. Phase 04 copies this tree; do not add a merge hook.

## Candidate copy (phase 04)

Use the sealed slot's `deployment_dimensions` and starting state.
Copy `/synthesis/output/environment/` to
`candidates/<id>/environment/`, then edit that copy. Keep the sealed
topology: if the base is compose, keep compose; if the base is a single
Dockerfile, do not add compose. Do not docker build a candidate image;
`bash -n` is the environment check. Packaged builds happen in phase 06 nop.

- `container_mode=single`: stay on the copied Dockerfile.
- `container_mode=multiple`: the copy already has compose; edit what this
  slot's services need.
- `step_mode=multiple`: steps share this candidate environment and preserve
  runtime state in execution order. Their instruction layout is in
  `instruction.md`; customize stage-specific assets in this same copy.
- Slot extras the sealed base lacks (plants, a command binary, a
  runtime pin) go in the copy: source files, setup scripts, or assets.
- `mcp=required` or `optional`: stdio `command` must appear in the
  candidate environment. Agent network is `public`, so an HTTP MCP url
  is reachable.

Harbor layout examples:
https://github.com/harbor-framework/harbor/tree/main/examples/tasks.
