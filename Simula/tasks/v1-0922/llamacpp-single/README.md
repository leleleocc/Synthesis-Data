# Simula synthesis v1

This Harbor trial turns one pinned source repository and one target
specification into one or more executable Harbor tasks. It uses seven small
phases. Each phase consumes its declared inputs and sealed upstream handoffs
and writes the artifact it owns.

`/synthesis/input/target_spec.json` is the immutable input for phases 01-03.
Phase 03 converts it into `03_simula_plan.json`. After that conversion every
slot is the fullest Harbor-task preview JSON, including all five
`deployment_dimensions`. Later phases join that plan by slot id and must not
reread the full target spec. Subagents in phases 04 and 05 receive only the
current slot, its parent global row, plan difficulty, and the reference
sections required for that candidate.

## Input

Harbor uploads the first step workdir as `/synthesis/input/target_spec.json`.
The repository is identified only by:

```json
{"source_repo": {"url": "https://github.com/org/repo", "commit": "<full-commit>"}}
```

There is no staged repository directory. Phase 01 makes a temporary shallow
checkout and writes no handoff when fetch or exact checkout fails. The target
spec also carries the requested languages, domains, subdomains, tags,
difficulty, oracle types, optional mechanisms, optional deployment dimensions,
and candidate budget. Phase 01 rejects a repository that cannot host a
requested deployment shape.

## Pipeline

```text
01_repo_profile_gate   profile, license, executable evidence, target intersection, deployment support, gate
02_environment         sufficiently-base Dockerfile/compose and Harbor network/path contract
03_simula_plan         pinned-code feasibility; global/local/mechanism/complexity slots; Harbor previews
04_task_design         per-slot instruction.md and a copied, then edited, environment
05_verifier_and_task   per-candidate task.toml and deterministic tests/test.sh
06_package             assemble every valid candidate; Harbor library validate; nop
07_review              Static Checks + Implementation Rubric; publish/revise/reject
```

Phase 02 keeps the shared environment sufficiently base: clone the pin, install
language/build tools, declare paths and entrypoints, and install once any
runtime the whole batch will need. Topology follows phase 01 compose evidence;
one batch cannot mix single and multiple container bases. It does not plant a
task-specific defect, golden, or per-slot fixture. If the target requests GPU
and phase 01 evidenced it, set `resources.gpus = 1`. CPU, memory, and storage
are fixed at 4, 8192 MB, and 10240 MB. `environment` and `agent` network are
`public`; `verifier` is `public`, or `no-network` only when the scenario needs
it, verifier dependencies are already installed, and the verifier is not
separate. `data_dir` and
`results_dir` are nullable. The shared base is cloned, built, and smoked once;
later phases do not rebuild it. Phase 04 copies that tree per candidate,
edits the copy, and checks `bash -n`; packaged builds happen in phase 06 nop.

Phase 03 reads the repository code at the pinned URL and commit before
designing slots. It confirms a constructible starting state, interacting
constraints, observable outcomes, and a credible completion path within the
sealed environment. It writes every slot with `deployment_dimensions` for
container mode (`single|multiple`), step mode (`single|multiple`), verifier mode
(`separate|inline`), GPU (`none|optional|required`), and MCP
(`none|optional|required`). If the target lists values, the batch covers them.
If a dimension is unconstrained, the slot freezes the default (`single`,
`single`, `inline`, `none`, `none`) unless the sealed base is compose
(`container_mode=multiple`) or already allocates GPUs (`gpu=required`). Future
kebab-case dimensions pass through. Slot `mechanism` is the closed diversity
axis. Every slot is compound: `complexity_delta` couples two constraints.

Phases 03 and 04 both read `environment/docs/difficulty.md`, the single shared
difficulty definition. Phase 04 includes it in every candidate subagent's
context. Difficulty comes from causal chains, constraint conflicts,
component interactions, and state transitions. Real symptom logs and
reproduction clues are allowed at every band; root-cause disclosure and
repair recipes remain restricted.

Phase 04 and phase 05 use progressive disclosure. Quality and Harbor file
format live in `simula-synthesis/references/`: the
instruction describes phenomena, not the specific problem; the verifier is
a discriminator (Task -> likely errors -> tests that kill those errors, then
prove it with wrong solutions); env and `task.toml` are customized to the
slot (single vs multiple container, single vs multiple step, inline vs
separate verifier). Hard and ultra instructions state observable symptoms
and outcomes without diagnosing a defect site; the agent discovers the locus and satisfies both
coupled constraints (ultra: they share state). Across a batch,
instructions must not be one template with swapped paths.

Phase 05 owns `task.toml`. A single-step task sets agent timeout 7200,
verifier 600, and build 600. A multiple-step task sets build 600 and, on
every step, agent 1800 and verifier 300. Harbor
uses shared `tests/test.sh` or native `steps/<name>/tests/test.sh` entries;
those scripts must not install packages.
Canonical pins are `pytest==9.1.1` and `pytest-json-ctrf==0.5.2`, baked
into the candidate `environment/Dockerfile` when inline or
`tests/Dockerfile` when separate. Across a batch of two or more
candidates, verifier form must not be monolithic.

Phase 05 calibrates the actual verifier against temporary correct outputs,
states, or implementations and wrong cases in disposable runtimes. It does
not assume an existing reference solution or require a persistent
`solution/`. Reset between cases and keep solved state out of the initial
candidate environment and published package.

Phase 06 assembles candidates, then runs `Task.is_valid_dir()` and
`TaskConfig.model_validate_toml()`. After that it runs
`harbor run -a nop -p <task-dir> --jobs-dir "$SIMULA_JOBS_DIR"` on every
package (actual `[environment].gpus > 0`: add `-e daytona`).
Reward 0 means the environment built and a no-op agent did not complete
the task. Any other exception is repaired in the assembled copies and
nop is re-run. Initial assembly verifies exact copies; the final gate permits
environment repairs while preserving instruction, tests, steps, and task config
apart from `[task].name` identity. GPU plus compose is rejected before packaging.

Phase 07 re-runs those Harbor library checks, then spawns two independent
read-only reviewers per candidate, in parallel when capacity allows. The
Static Review Agent applies `environment/docs/static-checks.md`. The
Implementation Review Agent applies `environment/docs/task-implementation.toml`
with taxonomy and shared difficulty guidance. Both inspect the current package
without earlier design reasoning. The main phase agent waits for both reports,
owns all repairs and calibration, and requests affected re-reviews after edits.
Per-item results stay in `07_review.json` under `review_reports`.
The review contract requires both reports to cover all named checks and
derives their pass flags from non-advisory failures.

`difficult` and `essential_difficulty` are advisory in phase 07: they do not
block publication or trigger added complexity or difficulty relabeling.
Verification, alignment, security, and other applicable blocking criteria
still have to pass. Do not fetch TASK_REVIEW_AUTOMATION.md. Skip Agent
Trials, Cheat, Fortify, AI-detection, Docker Build, and Oracle Validation.
After any packaged edit, re-run the same nop command. GPU
packages inherit `DAYTONA_API_KEY` from the factory environment (`chmod 600` on `.env`;
never COPY into the image or a package). A failing static check or blocking
rubric criterion is repaired in the packaged task with the smallest change that
makes it pass (env/tests first; instruction.md only for heading, path, or
suffix failures). Too-loose or too-strict means a small `tests/` assertion
edit, re-run, and repeat until the candidate can `publish`. Do not bounce
that repair to phase 05. Only the latest `publish` result enters
`07_review.release_candidate_ids`. Do not write `release_manifest.json`.

When uncertain about compose, GPU, MCP, or `[[steps]]` layout, consult
https://github.com/harbor-framework/harbor/tree/main/examples/tasks.

## Artifacts

State handoffs are under `/synthesis/state/`:

```text
01_repo_profile_gate.json
02_environment.json
03_simula_plan.json
04_task_design.json
05_verifier.json
07_review.json
```

The final package contains `task.toml`, `environment/`, a root instruction
for single-step tasks or declared `steps/<name>/` instructions for
multiple-step tasks, verifier trees, and a provenance `README.md`.
`07_review.json` publishes only candidates whose verifier passed the
too-loose and too-strict review; join `release_candidate_ids` with
`generated_task/manifest.json`.

## Resources

Agent resources live in three trees under `environment/` and are COPY'd into
the image at `/opt/terminaltraj/{docs,scripts,skills}`:

```text
environment/docs/      shared difficulty, Static Checks, Implementation Rubric, taxonomy
environment/scripts/   JSON/handoff validators (phase_contract.py, ...)
environment/skills/    simula-synthesis references + original Harbor examples
```

`simula-synthesis/references/` holds both quality and Harbor file format:
instruction as phenomena, verifier as discriminator, env/toml customized
to the slot, and package/review validation. Closed vocab and on-disk
alignment are `phase_contract.py`.

Harbor layout validation uses the local `simula-synthesis/references/packaging.md`
protocol plus the Harbor Python library (`TaskPaths` / `TaskConfig`). The
original Harbor examples and task field reference remain available; there is
no Simula wrapper for those APIs.

## Local checks

Use Python 3.11 or newer (the factory image uses Python 3.12).

```bash
python3 environment/scripts/check_contracts.py
python3 environment/scripts/check_contract_regressions.py
python3 tests/check_compose_env.py
python3 environment/scripts/phase_contract.py validate \
  steps/01_repo_profile_gate/workdir/input/target_spec.json
find steps -name test.sh -print0 | xargs -0 -n1 bash -n
```

The factory pins Harbor with Daytona support and includes Compose and Buildx.
Compose automatically loads the factory task's root `.env`; its values override
the host's `DAYTONA_API_KEY` fallback. No `harbor run --env-file` is needed for
this factory credential. A missing `.env` is allowed for CPU-only runs.
Its private DinD service and agent share the project-scoped `/synthesis` volume;
Compose build inputs, runtime bind mounts, and nested job logs use the same paths.
The Docker daemon and workspace are isolated per factory trial.

The static checks do not build the target repository. To exercise local DinD,
Compose builds/binds, and single/multi-step nop (test containers are cleaned up):

```bash
docker build -t simula-v1-check:local environment
python3 tests/check_dind_runtime.py --image simula-v1-check:local
```

The factory requires privileged DinD support. No cloud or model calls are made
by this smoke test. Offline contract regressions stay Harbor-free.
