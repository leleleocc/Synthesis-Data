# TerminalTraj synthesis task

This is an outer Harbor multi-step task for synthesizing one Harbor task from
one repository and a `target_spec`. The steps are synthesis phases, not the
user-facing task that will later be rolled out.

The factory is repository-agnostic. Replace the staged tree and edit
`target_spec.json`; later steps must stay inside that envelope. The current
checkout under `steps/01_repo_profile/workdir/input/repository/` is Redis
7.2.16 (BSD-3; 7.4+ changed license, stay on 7.2.x), a fixture chosen for
hard system/database tasks, not a Redis-only pipeline.

## Layout

```text
terminaltraj-synthesis/
  task.toml
  README.md
  environment/Dockerfile
  environment/docker-compose.yaml   # triggers Harbor/Daytona DinD
  environment/scripts/validate_json.py
  environment/scripts/target_spec.py
  environment/scripts/taxonomy.md     # Terminal-Bench domains + seed subdomains
  environment/skills/harbor-task-creator/  # Harbor wiring skill (phases 03/04/06; examples are simple demos)
  tests/helpers.sh
  scripts/check_contracts.py
  steps/
    01_repo_profile/ ... 08_package/
  steps/01_repo_profile/workdir/input/
    target_spec.json
    repository/          # current fixture: redis/redis 7.2.16 (no .git)
```

## Inputs

Harbor uploads the first step's `workdir/` into the shared workdir before
step 01. Runtime paths are:

```text
/synthesis/input/target_spec.json
/synthesis/input/repository/
```

`target_spec.json` is an executable contract, not a comment. Closed vocabularies:

```text
domains:      science | software | ml | operations | security | hardware | media
              (Terminal-Bench taxonomy; factory JSON is kebab-case)
subdomains:   seed list in environment/scripts/taxonomy.md (open: new kebab
              tokens may be added under a listed domain)
tags:         closed factory skill/tech vocabulary (see target_spec.py TAGS)
oracle_types: result | state | behavior
difficulty:   easy (SOTA agent <=1h) | medium (1-3h) | hard (3-6h) |
              ultra (6h+; compound interacting hard parts)
```

`domains` / `subdomains` / `tags` are the repository-and-target view. Each
generated `task.toml` maps them onto Terminal-Bench `[metadata]`: `category`
is the Title Case of one candidate domain (`Science`, `Software`, `ML`,
`Operations`, `Security`, `Hardware`, `Media`); `subcategory` is one
candidate subdomain (seed Title Case, or kebab for an extension); `tags`
equals the candidate tag list. Also required: `expert_time_estimate_min`
(SOTA-agent minutes inside the difficulty band above) and
`junior_time_estimate_min` (>= 2x that estimate). Step 04 derives
`[agent]`, `[verifier]` and `[environment]` timeouts/resources from those
estimates and from the sealed base environment; `[agent].timeout_sec` is at
least the SOTA estimate in seconds; `[environment].network_mode` is always
`public` because Harbor installs the agent at runtime.

Example (current Redis fixture):

```json
{
  "source_repo": {
    "path": "/synthesis/input/repository",
    "url": "https://github.com/redis/redis",
    "commit": "335554f18caf7bbf6b0ac2b3548133d750f00a1b"
  },
  "target": {
    "languages": ["c", "shell"],
    "domains": ["software"],
    "subdomains": ["systems", "databases"],
    "tags": ["build", "caching", "cli", "debugging", "linux", "optimization", "persistence", "redis", "repair"],
    "difficulty": "hard",
    "oracle_types": ["result", "state", "behavior"]
  },
  "generation": {
    "allow_external_assets": false,
    "max_candidates": 6,
    "min_repo_score": 0.2
  }
}
```

Step 04 must give every candidate **lists** (`tags`, `domains`, `subdomains`,
`languages`, `oracle_types`) that are unique subsets of those target lists.
When a target list has two or more values, that candidate field must contain
at least two (a one-tag or one-oracle job is too thin). Emit **exactly**
`generation.max_candidates` candidates. Step 05 reviews every candidate
against the instruction-level part of the Terminal-Bench task rubric: seven
scores (proposal rubric plus spec alignment) that must all be at least `0.7`,
and nine pass/fail/not_applicable checks named after the CI rubric criteria
(`anti_cheat_robustness`, `deterministic_reproducible`, `essential_difficulty`,
`novel`, `agentic`, `instruction_concision`, `structured_data_schema`,
`task_security`, `typos`) none of which may fail. Every qualified candidate
is approved; there is no second count cap. All approved candidates continue
to packaging.
Step tests call `environment/scripts/target_spec.py` to enforce this envelope.
`generation.min_repo_score` is the accept threshold for step 02.

## Pipeline

```text
01 repo profile          # evidence portrait; sealed
02 repo gate             # hard_checks AND score >= min_repo_score
03 environment           # shared base (not a task), docker build, smoke; freeze
04 task design           # exactly max_candidates: instructions first, then toml + overlay + oracle_tools
05 task review           # review instruction; minimal in-place fixes; approve all that qualify
06 verifier generation   # per approved candidate: tests/** only
07 verifier review       # review tests; minimal in-place fixes under tests/ allowed
08 package               # assemble: instruction/task.toml/tests + base env merged with overlay
```

Ownership of artifacts:

- **Environment base (03):** only `/synthesis/output/environment/` (frozen afterwards)
- **Task (04/05):** `candidates/<id>/instruction.md`, `task.toml`, overlay `environment/`
- **Tests (06/07):** only `candidates/<id>/tests/**`
- **Package (08):** merge those pieces into `generated_task/<slug>/` and add `README.md`

Every `steps/*/instruction.md` uses the same six-section prompt framework, in
order: **ROLE**, **BOUNDARIES**, **INPUTS**, **HANDOFF**, **WORK** (with
`### Step 01:` ... guides), **GATE**.

Each step that owns a contract writes a JSON handoff under `/synthesis/state/`
(`01_repo_profile` ... `07_verifier_review`). Agents must land a skeleton first
via `target_spec.py ensure-handoff <phase>` in **HANDOFF** before long probes,
and finish **GATE** with `require-handoff` plus the phase `check-*`. Step
verifiers call the same `require_handoff` helper so a missing JSON fails the
step even when other files look complete. Those state JSON files are sealed
(`state_integrity.py seal` / `verify`) so later phases cannot silently review a
different handoff. The input fixture under `/synthesis/input/repository` is
**not** tree-hashed: the final Harbor package obtains source with `git clone`
at `target_spec.source_repo.commit`. Phases after 01 still treat that tree as
read-only reference and tell the agent to use a scratch copy such as
`/tmp/repo` if they must run commands.

The sealed base is the only environment that is docker-built and smoked in
synthesis (step 03 agent turn). Later step verifiers do not re-run
`check-environment` or `docker build`. Step 04 may docker-build a **candidate
overlay** when that overlay replaces Dockerfile or setup; overlay failure
rejects that candidate in step 05 and never rewrites the base.

Harbor honors per-step `[steps.agent].timeout_sec` (see `StepConfig.agent` and
`MultiStepTrial._step_agent_timeout_sec`). Steps 03 and 04 set this to 3600 so
a Redis-sized `docker build` is not killed. Other steps omit it and stay
unbounded unless the job passes an agent timeout override. Every step,
including 08, sets `min_reward = 1.0` so a failed assemble fails the trial
(Harbor `mean` would otherwise hide an 08 zero).

Phase 08 writes `/synthesis/output/generated_task/<slug>/` per survivor:

```text
instruction.md  # from 04, after 05 edits
task.toml       # from 04 (name/slug alignment only)
environment/    # 03 base merged with 04 overlay (overlay wins on the same path)
tests/          # from 06, after 07 edits
README.md       # provenance for humans
```

`manifest.json` beside the packages maps candidate ids to package slugs.

## Overlays

The sealed base is a shared Harbor agent image: toolchain, pinned clone,
workdir / data / results, and a no-op `setup-overlay.sh`. It does **not**
preinstall a verifier stack. Phase 04, which already knows the task, lists
`oracle_tools` and installs any missing observation binary in that
candidate's overlay (`setup-overlay.sh` preferred). Phase 06 `test.sh` stays
offline and may call only bash plus those tools. Diversity that cannot share
one image (a planted bug, a broken redis.conf, extra logs, extra CLIs) lives
in `candidates/<id>/environment/`.

- Assets-only overlay: no rebuild (`env_build=not_required`).
- `setup-overlay.sh` only: prove with a scratch merge build; do not edit the
  sealed base.
- Overlay `Dockerfile` / `setup.sh` / `smoke_test.sh`: the Dockerfile must be
  a complete, independently buildable Harbor environment (`FROM` a public
  image, `git clone` the pin). Never `FROM synth-env:03`; Harbor rebuilds the
  packaged image in isolation.

## Local checks (no Docker agent run)

From this directory:

```bash
python scripts/check_contracts.py
python environment/scripts/target_spec.py validate \
  steps/01_repo_profile/workdir/input/target_spec.json
```

This validates Dockerfile safety, `target_spec` vocabulary, sample input
presence (README, license, any language manifest - not Python-only),
step/toml alignment, the step-03 instruction/test schema match, and that
`task.toml` plus every `steps/*/instruction.md` is pure ASCII.

The ASCII rule exists because Harbor reads those files on the host with
`Path.read_text()` and no explicit encoding. On a Windows host with a GBK
(zh-CN) code page any non-ASCII byte raises `UnicodeDecodeError` before the
step agent starts, so the step fails with "missing file" in its verifier.
The same crash hits **generated** `instruction.md` files when you later
`harbor run -p generated_task/<slug>`. Phases 04 and 05 must write those
files as pure ASCII (hyphen instead of em-dash, `->` instead of arrows).
Setting `PYTHONUTF8=1` in the shell that runs `harbor run` also avoids this
(and the related "Failed to convert Claude Code events to trajectory" warning),
but keeping the files ASCII works regardless of the host locale.

`environment/docker-compose.yaml` is what switches Harbor off the single-container path. On Daytona (`--env daytona`) that file makes Harbor start a DinD VM (`docker:28.3.3-dind`) and compose `main` inside it, with `/var/run/docker.sock` mounted so step 03 can `docker build` the generated image (DooD, not a nested daemon). The synthesis Dockerfile must ship a Docker **28.x** CLI (`COPY --from=docker:28.3.3-cli ...`); Debian `docker.io` (~26.x on Trixie) cannot talk to that daemon and makes `docker info` fail inside main. Local `--env docker` uses the same compose overlay against the host daemon.

```bash
harbor task start-env -p . --non-interactive
# or a full multi-step trial with your configured agent:
# harbor run -p . -a <agent> -m <model>
```

## Scope notes

The task deliberately omits TerminalBench leakage filtering and deduplication.
Add those as a separate preprocessing stage if benchmark contamination control
is required later.

Harbor multi-step trials are sequential gates (`min_reward`), not rewrite loops.
A failed query/verifier review aborts the trial; rerun after adjusting prompts
or inputs rather than expecting an automatic return to phase 04/06. Step 02
still requires `accepted` and `decision=accept` for the trial to continue.

Step 03 must report `build.mode=docker` with `build.status=passed`. Static
mode is an honest failure if `docker info` fails; it is not proof the inner
image builds. Step 07 reviews verifiers statically (syntax, coverage of the
success conditions, oracle independence); it does not execute them, because the
repository's tools are not installed in the synthesis container.

These quality gates follow the same principles as Harbor's multi-step task
contract and Terminal-Bench's task-implementation rubric: stated behavior must
be tested, tests must be informative and resistant to reward hacking, and
dependencies and paths must be reproducible.

## References

* Harbor multi-step tasks: https://www.harborframework.com/docs/tasks/multi-step
* Terminal-Bench task rubric: https://github.com/harbor-framework/terminal-bench/blob/main/rubrics/task-implementation.toml
