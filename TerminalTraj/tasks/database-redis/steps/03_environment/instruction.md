# Phase 03: environment synthesis and smoke

## ROLE

You are phase 03 only. Run from files on disk; do not rely on chat history.
You own only the sealed base environment and its state handoff:

- `/synthesis/output/environment/**`
- `/synthesis/state/03_environment.json`

You do not own candidates, tests, verifiers, or later state files. After this
phase the base tree is frozen; later phases may add per-candidate overlays, not
edit this directory.

This image is a **shared base**, not a task. Phase 04 must still be able to
emit `generation.max_candidates` diverse tasks (every requested tag and
`oracle_type` the repo can host). Do not specialize the base toward one
scenario, one defect, or one fixture set.

## BOUNDARIES

- Treat `/synthesis/input/repository` as read-only reference input. Do not write,
  install, build, or run tests inside it. If you need to try the repository,
  copy it to a scratch directory such as `/tmp/repo`.
- The image must obtain source with `git clone` at the pinned commit; the final
  Harbor package does not ship the input tree.
- Do not write:
  - `/synthesis/output/candidates/**` (phase 04+)
  - any `tests/`, `test.sh`, golden files, or verifier scaffolds (phase 06)
  - later state files (`04_task_design.json`, ...)
  - edits under `/synthesis/input/repository`
- Prior state JSON and `.integrity/*.sha256` seals are read-only.
- If a tool call returns empty output, retry once with a short probe (`echo ok`
  or rewrite the same small file). Do not abandon the handoff, do not switch to
  writing verifier code, and do not end the turn while the checklist is incomplete.
- Do not start phase 04+ work in this turn.
- Do not design, preview, or plant a specific later task in this image.
  No planted bugs, broken redis.conf, task-only logs, golden answers, or a
  single "the" workload. Those belong in phase 04 overlays. The base must
  remain a working, general Harbor agent image.

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- `/synthesis/state/01_repo_profile.json`
- `/synthesis/state/02_repo_gate.json`
- the complete source repository at `target_spec.source_repo.path` (Docker/compose
  files, lockfiles, CI files, and run instructions included)
- `/opt/terminaltraj/skills/harbor-task-creator/SKILL.md` and
  `/opt/terminaltraj/skills/harbor-task-creator/references/example-tasks.md`
  for Harbor image wiring only (what Harbor mounts, that tests are uploaded
  after the agent, compose primary service name `main`, do not COPY tests or
  solution into the image). Those walkthroughs are **very simple demos**
  (toy fib, toy Flask, four-row Postgres). Copy Harbor rules from them, not
  their size, their planted bugs, or their one-task specialization.

## HANDOFF

Hard gate. The verifier fails if any of these is missing. A partial environment
that builds but lacks the handoff still scores 0.

Under `/synthesis/output/environment/`:

1. `Dockerfile`
2. `setup.sh` (executable)
3. `setup-overlay.sh` (executable; base copy is a documented no-op)
4. `smoke_test.sh` (executable)
5. `assets/` directory (may be empty; required to exist)
6. `docker-compose.yaml` only when `deployment_mode` is `compose`

And the phase handoff:

7. `/synthesis/state/03_environment.json`

Land the skeleton **before** long probes or a full image build:

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 03_environment
```

That creates the state file. Fill known paths (`workdir`, `data_dir`,
`results_dir`, provisional `entrypoints`, `network_policy=build_only` when you
will `git clone` at build time). The `build` object lives only in this state
file. Do not write a companion `environment.json`.

State contract:

```json
{
  "deployment_mode": "single",
  "base_image": "...",
  "services": [{"name": "main", "image_or_build": "...", "ports": [], "healthcheck": "..."}],
  "dependencies": {"system": [], "language": [], "pinned": true},
  "asset_paths": [],
  "network_policy": "build_only",
  "workdir": "/app",
  "data_dir": "/data",
  "results_dir": "/results",
  "entrypoints": ["..."],
  "build": {
    "status": "passed",
    "mode": "docker",
    "buildable": true,
    "smoke_test": true,
    "build_seconds": 142,
    "failures": []
  }
}
```

## WORK

Build the smallest deterministic **shared base** that can host the requested
tags in a requested language. Think platform, not problem: toolchain,
pinned clone, workdir / data_dir / results_dir, declared entrypoints, and a
no-op `setup-overlay.sh`. Per-task fixtures, broken configs, planted defects,
and patches belong in phase 04 overlays, not here.

Do not shrink later diversity. The base must remain usable for every
`target.tags` value the profile said it can host. If a choice would make a
`configuration`/`ops` task easy and a `repair`/`debugging` task impossible
(or the reverse), leave that choice out of the base.

Do not install a verifier stack "just in case" (python3, pytest, jq, ...).
Phase 04 knows the task and owns overlays; it adds observation tools then.
This image is bash + the repository toolchain + declared entrypoints.

Harbor wiring to keep (from the skill; the examples themselves are very
simple demos, not a template for this image):

- Do not COPY `tests/` or `solution/` into the image. Harbor uploads those
  at runtime. Do not install test-only deps (pytest and friends) here.
- Pin every package version. Prefer the repository's real toolchain over a
  generic `python:3.12-slim` toy base.
- If `deployment_mode` is `compose`, the primary service **must** be named
  `main` (Harbor hardcodes that name for exec/upload/download). Give
  dependency services healthchecks. Do not invent a toy sidecar that the
  repository does not run.
- Skill Example 1 (`FROM python:3.12-slim` plus COPY of a buggy
  `fibonacci.py`) is a **task** image with a planted defect. That pattern
  belongs in a phase 04 overlay, never in this shared base.
- Skill Example 3 (Postgres + four-row `shop` seed) is a demo compose file.
  If this repository is a real database/server, use **its** layout, pin, and
  healthcheck, not that toy.

### Step 01: choose topology from tags and domain

Read `target.domains`, `target.subdomains`, and `target.tags`. The base is
still a platform, not a scenario. Use tags only to decide what the image
must be able to host:

* CLI / data tags (`cli`, `data-pipeline`, `etl`, `analysis`): install the
  repository's tools or CLIs; copy or vendor shared fixtures into the data
  directory; do not expect the agent to edit source.
* source-change tags (`repair`, `debugging`, `feature`, `refactoring`,
  `implementation`): copy source into a writable workdir; pin the toolchain
  so the agent can build and run tests. Do not plant the defect in this base.
* ops / runtime tags (`configuration`, `ops`, `deployment`, `high-availability`,
  `monitoring`): prefer the repository's real service or process layout. Use
  `compose` only for a genuine database, queue, worker, or HTTP boundary. Do
  not plant a broken config here.
* `build` / `build-system`: ship the toolchain but leave the build itself for
  the agent (do not pre-build the artifact the task will ask for); keep the
  source in a writable workdir.
* `optimization` / `performance` / `profiling`: ship a working baseline plus
  a way to measure it (timing, size, counts) that does not need the network.

If several of those groups appear in `target.tags`, keep the union in the
base (writable source AND running service AND toolchain), not the most
convenient one.

Do not reuse an upstream Dockerfile unchanged when it is a publish image (wrong
base, missing shell, missing data/results dirs, or no agent workdir). Rewrite it
into a Harbor agent image.

If `generation.allow_external_assets` is false, vendor every needed fixture
during build. Do not require runtime network. `network_policy` may be
`runtime_required` only when the spec allows external assets and the repository
cannot run without the network.

Never include hidden answers, a reference solution, or verifier code. Fixtures
under `assets/` are **shared inputs** only (generic samples, default configs).
Do not ship expected outputs, golden dumps of the answer, or solve scripts.
Do not vendor a fixture whose only purpose is one imagined task; keep assets
small and reusable, or leave `assets/` empty and let overlays add them.

### Step 02: write environment files

`/synthesis/output/environment/` is the sealed base. Harbor later builds each
packaged task's `environment/` with that directory as context after phase 08
merges overlays. Every `COPY` source is relative to this directory. Nothing
outside it (not the input repository tree, not synthesis state) may be referenced.

* `Dockerfile`: `FROM` a pinned base image; obtain source with
  `git clone <target_spec.source_repo.url>` then checkout the exact
  `source_repo.commit` (for example
  `RUN git clone <url> /src && git -C /src checkout <commit>`), never by
  copying the input tree; `COPY setup.sh setup-overlay.sh smoke_test.sh /opt/env/`;
  `COPY assets/ <data_dir>/` when there are fixtures; provision with
  `RUN bash /opt/env/setup.sh` then `RUN bash /opt/env/setup-overlay.sh`.
  Keep the Dockerfile thin; install logic lives in `setup.sh`. Only when
  `source_repo.url` is missing or the commit is `"unknown"` may you vendor the
  source instead: copy the input tree (without `__pycache__`, `*.egg-info`,
  `build/`, `.pytest_cache`) to `/synthesis/output/environment/repository/`,
  `COPY repository/ /src`.
* `setup.sh`: build-time provisioning. Install tools/deps from the cloned
  source, create `workdir` / `data_dir` / `results_dir`, place shared fixtures.
  Idempotent, non-interactive, no network at container runtime.
* `setup-overlay.sh`: **no-op in the base** (shebang plus a comment that phase
  04 overlays may replace this file). Still executable. Phase 08 merge lets a
  candidate overlay replace it without rewriting the Dockerfile.
* `smoke_test.sh`: you will run `bash /opt/env/smoke_test.sh` in a fresh
  container. Exit 0 only when at least one declared entrypoint runs, and
  declared `workdir` / `data_dir` / `results_dir` are writable. Must not modify
  source files. Must not be `exit 0` / empty / `true`.
* `assets/`: vendored **shared** fixtures (empty allowed). Prefer a small
  purposeful set.
* `docker-compose.yaml`: only for `compose`.

Because the source is cloned at build time, `network_policy` is normally
`build_only`. That field describes image build / task need for network, not
Harbor runtime `task.toml` `[environment].network_mode` (phase 04 sets that to
`public` so the agent installer can run).

### Step 03: fill the env contract

Field notes: `deployment_mode` is `single` or `compose`; `base_image` is the
main image; `services` describes each service, build source, ports, healthcheck
(primary service name is `main`); `dependencies` lists system/language deps and
whether pinned; `asset_paths` lists assets actually written under
`/synthesis/output/environment/assets` (not runtime paths like `/data/...`);
`network_policy` is one of `none`, `build_only`, `runtime_required`; `workdir` /
`data_dir` / `results_dir` are absolute task roots; `entrypoints` lists
invokable commands. Do not add extra keys.

Update the state JSON whenever entrypoints or assets change.

### Step 04: docker build and smoke

This phase is the **only** acceptance gate for the sealed base. Write logs to
`/synthesis/logs/build.log`. Wait until `docker info` succeeds, then:

```bash
docker build -t synth-env:03 /synthesis/output/environment
docker run --rm synth-env:03 bash /opt/env/smoke_test.sh
```

If compose: `docker compose -f /synthesis/output/environment/docker-compose.yaml`
from that directory. Confirm the source was cloned at the pinned commit, tools
are available, dependencies resolve, entrypoints exist, and declared
`data_dir` / `results_dir` work. Record `build.build_seconds`.

Build failure is a content problem to fix; it is not a reason to skip the JSON
handoff. After a fix, rebuild and smoke again.

If `docker info` still fails, set `build.mode` to `static`, `build.status` to
`failed`, and describe the missing runtime proof in `build.failures`. Never
claim a Docker build that did not run. A static pass is not allowed: later
phases must not treat an unbuilt image as proven.

On success: `build.status=passed`, `mode=docker`, both booleans true, empty
`failures`. On failure: `status=failed`, both booleans false, concrete failures.

## GATE

Stopping without a passing gate is a failed phase even if `docker build`
succeeded.

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 03_environment
python /opt/terminaltraj/scripts/target_spec.py check-environment \
  /synthesis/input/target_spec.json \
  /synthesis/state/03_environment.json \
  /synthesis/output/environment
```

Confirm on disk:

```bash
test -f /synthesis/state/03_environment.json \
  && test -f /synthesis/output/environment/Dockerfile \
  && test -f /synthesis/output/environment/setup.sh \
  && test -f /synthesis/output/environment/setup-overlay.sh \
  && test -f /synthesis/output/environment/smoke_test.sh \
  && test -d /synthesis/output/environment/assets \
  && echo CHECKLIST_OK
```

Fix environment files until checks pass. When `check-environment` prints no
errors and `CHECKLIST_OK` appears, stop. Do not start phase 04+ work in this
turn.
