# Phase 02: shared environment

## ROLE

You are phase 02 only. Build the shared Harbor base environment for every
candidate. You own `/synthesis/output/environment/**` and
`/synthesis/state/02_environment.json`.

## BOUNDARIES

- Read the source only from the URL and commit in `target_spec.json`; do not
  expect `/synthesis/input/repository`.
- The Dockerfile or compose file must clone the pinned commit during build.
- Keep this environment sufficiently base. It is the shared runtime for every
  later slot: clone the pin, install language/build tools, declare paths and
  entrypoints, and install once any runtime the whole batch will need. Do not
  add a task-specific defect, planted fault, answer, golden file, verifier,
  or per-slot fixture.
- Topology follows phase 01 evidence, not a later slot wish. Use compose with
  primary service `main` only when `01_repo_profile_gate.deployment_support`
  shows observed compose files. One batch cannot mix single and multiple
  container bases.
- Set `resources` to exactly 4 CPU, 8192 MB memory, and 10240 MB storage.
  With evidenced `gpu=required`, set `resources.gpus = 1`; `optional` may
  use 0 or 1. GPU allocation requires a single-container base.
- `network.environment` and `network.agent` are `public`. `network.verifier`
  is `public`, or `no-network` only when the scenario needs it, verifier
  dependencies are already installed, and the verifier is not separate.
- Do not write candidates, tests, or later state files.
- Skills and docs under `/opt/terminaltraj/` are already in the image; they
  are not inputs. Open `simula-synthesis` then `references/environment.md`,
  When uncertain about compose, GPU, MCP, or
  `[[steps]]` layout, consult
  https://github.com/harbor-framework/harbor/tree/main/examples/tasks.

## INPUTS

- `/synthesis/input/target_spec.json`
- `/synthesis/state/01_repo_profile_gate.json`

URL and commit come from the target spec. Use a temporary checkout only when
the profile is not enough to write the base.

## HANDOFF

Run `python /opt/terminaltraj/scripts/phase_contract.py ensure-handoff 02_environment`
before the build so the final state has a stable contract path.

Create the environment tree and then write `/synthesis/state/02_environment.json`.
The tree contains exactly a buildable `Dockerfile` or `docker-compose.yaml`,
plus any setup files required by that image. If `assets/` exists, the base
Dockerfile must COPY it. Phase 04 copies this tree per candidate and edits
the copy; do not add a merge hook. The state shape is:

```json
{
  "deployment_mode": "single",
  "source_repo": {"url": "...", "commit": "..."},
  "services": [{"name": "main", "image_or_build": "..."}],
  "resources": {"cpus": 4, "memory_mb": 8192, "storage_mb": 10240, "gpus": 0},
  "dependencies": {"system": [], "language": [], "pinned": true},
  "asset_paths": [],
  "network": {
    "environment": {"network_mode": "public", "allowed_hosts": []},
    "agent": {"network_mode": "public", "allowed_hosts": []},
    "verifier": {"network_mode": "public", "allowed_hosts": []}
  },
  "paths": {
    "workdir": "/workspace",
    "source_dir": "/workspace/repo",
    "data_dir": null,
    "results_dir": null
  },
  "entrypoints": [],
  "build": {
    "status": "passed",
    "mode": "docker",
    "buildable": true,
    "smoke_test": true,
    "build_seconds": 0,
    "failures": []
  }
}
```

`environment` and `agent` stay `public`. `verifier` may be `no-network` only
when the scenario needs it, its dependencies are already installed, and it
is not separate; otherwise `public`. Leave `allowed_hosts` empty. `data_dir` and `results_dir` may be null; do not create fake
directories just to satisfy this schema. `workdir` and `source_dir` must be
absolute when present. Compose services must use the primary name `main`.

## WORK

### Step 01: inspect only what the base needs

Use the profile for likely languages and entrypoints. Fetch the pinned source
into a temporary directory only when the build command or runtime layout is
not clear from the profile.

### Step 02: write the base files

Write the Dockerfile or compose file first. Clone the exact commit, install
runtime/build dependencies and any batch-shared runtime, create the declared
workdir and source_dir, and leave task-specific assets, faults, and goldens
to phase 04. Do not install pytest in this shared base; later slots mix
inline and separate verifiers, and phase 05 bakes `pytest==9.1.1` plus
`pytest-json-ctrf==0.5.2` into the candidate image that actually runs the
verifier. The image must still boot and smoke as a shared base. Compose
only when phase 01 evidenced compose. Allocate
`resources.gpus = 1` when GPU is required and phase 01 evidenced it.

### Step 03: build and smoke test

Clone once, build the Dockerfile once (or build and start compose once), and
run a bounded smoke test for at least one declared entrypoint. After smoke
passes, stop. Do not recopy the source, iterate the image, or explore extra
trees. Record the actual build mode, duration, and failures in the state JSON.
A failed build or smoke test is a failed phase.

### Step 04: self-check

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 02_environment
python /opt/terminaltraj/scripts/phase_contract.py check-environment \
  /synthesis/input/target_spec.json \
  /synthesis/state/02_environment.json \
  /synthesis/output/environment
```

Fix every reported issue, then stop.

## GATE

The phase passes only when the shared environment tree is buildable, the smoke
test passed, and both commands in Step 04 succeed. Do not start phase 03 work.
