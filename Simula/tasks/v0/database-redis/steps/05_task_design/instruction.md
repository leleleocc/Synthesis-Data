# Phase 05: task design and query generation

## ROLE

You are phase 05 only. Run this phase independently from files on disk; do not
rely on chat history. You own only:

- `/synthesis/output/candidates/<id>/instruction.md`
- `/synthesis/output/candidates/<id>/task.toml`
- `/synthesis/output/candidates/<id>/environment/` (overlay; directory required)
- `/synthesis/state/05_task_design.json`

You do not own verifiers, golden files, `metadata.json`, the sealed base
environment, or later state. Do not spend this phase end-to-end prototyping
every pipeline in Docker; read the environment contract and fixtures, design on
paper, write the files, then optionally spot-check one command if needed.

## BOUNDARIES

- Treat `/synthesis/input/repository` as read-only reference input. Do not write,
  install, build, or run tests inside it. If you need to try commands to design
  candidates, first copy it to a scratch directory such as `/tmp/repo`. Prefer the
  sealed environment contract and fixtures under `/synthesis/output/environment/`;
  the final package clones the upstream commit rather than shipping this tree.
- **Do not modify `/synthesis/output/environment/`.** That tree is sealed after
  phase 03. Per-task files go in `candidates/<id>/environment/` only.
- For every candidate you keep, write **exactly** `instruction.md`, `task.toml`,
  and an `environment/` overlay directory under `/synthesis/output/candidates/<id>/`.
- No verifier, no golden files, no `metadata.json`, no extra design JSON fields
  beyond the small index in HANDOFF.
- Treat prior state JSON files and their `.integrity/*.sha256` seals as
  read-only.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 06/07 work in this turn.
- Do not invent a parallel set of candidates. Slot ids and vocab lists come from
  `/synthesis/state/04_simula_plan.json`.

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- states `01_repo_profile.json`, `02_repo_gate.json`, `03_environment.json`,
  `04_simula_plan.json`
- the source repository at `target_spec.source_repo.path`
- `/synthesis/output/environment/` (read-only)
- `/opt/terminaltraj/scripts/taxonomy.md` (closed domains, seed subdomains)
- `/opt/terminaltraj/skills/harbor-task-creator/` (Harbor wiring). Read
  `SKILL.md`, `references/task-toml-reference.md`, and
  `references/example-tasks.md` before writing instructions or toml.
  Those four walkthroughs are **very simple demos** (fib bug, toy Flask
  API, four-row Postgres migration, toy MCP report). Use them for Harbor
  mechanics only (self-contained instruction, reward channel, compose
  service name `main`, quality-check anti-patterns). They are not the
  difficulty bar, not the instruction style to clone, and not a license
  to emit N variants of a tutorial.

## HANDOFF

Hard gate: `/synthesis/state/05_task_design.json`. Stopping without the state
file fails the phase even if some `instruction.md` files exist.

Land the index before writing many candidates:

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 05_task_design
```

Fill the index as you add candidates (not a second copy of the task content).
Final shape:

```json
{
  "candidates": [
    {
      "id": "c1",
      "tags": ["debugging", "repair", "configuration", "redis"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["state", "behavior"],
      "env_build": "not_required",
      "oracle_tools": ["redis-cli", "python3"]
    }
  ]
}
```

The index is identity plus vocabulary lists plus overlay/oracle metadata.
On-disk files live at `candidates/<id>/`; do not duplicate those paths in JSON.
Do not use singular vocabulary keys (`tag`, `domain`, `subdomain`, `language`,
`oracle_type`) and do not write `task_types`.

`env_build` is `not_required` when the overlay is assets-only (or empty);
`passed` after you docker-build a Dockerfile/setup overlay; `failed` if that
build did not succeed. Phase 06 will not approve `failed`.

`oracle_tools` is the observation surface for phase 07: argv0 names that
`tests/test.sh` may call (plus POSIX `bash` / coreutils, which you do not
list). Every name must already be a sealed-base entrypoint **or** be
installed by this candidate's overlay. Empty list means bash-only. Do not
list pytest unless the overlay actually installs it (prefer `python3`
stdlib).

## WORK

Work in this order. Do not write `task.toml` or overlays until every
instruction is on disk.

### Step 01: read the sealed environment contract first

Everything a candidate can rely on is in `03_environment.json`, not in your
imagination:

- `entrypoints`: the only commands the task may require. Do not assume tools
  that are not installed (check `dependencies` and `smoke_test.sh`).
- `data_dir` / `results_dir` / `workdir`: read roots and write roots. Shared
  inputs live under `data_dir` (see `asset_paths` for what was vendored and open
  the fixtures to learn their real quirks); outputs go under `results_dir`.
- `network_policy`: what the environment cannot do at runtime. A task that
  needs a missing service, dataset, or network is invalid.
- `build`: `mode`, `build_seconds`. Size `[environment].build_timeout_sec`
  from `build_seconds`.

Write down (for yourself) the entrypoints, the shared fixtures worth using, and
the data quirks you found. Real tasks come from those quirks. Also note how a
later verifier could observe success with those entrypoints. A missing
observation binary is an overlay + `oracle_tools` item in this phase, not a
phase-03 or phase-07 install.

### Step 02: consume the Simula slots

Read `/synthesis/state/04_simula_plan.json`. Emit **exactly those slots**
in the same ids. Count equals `generation.max_candidates`. Do not invent a
parallel matrix. Do not drop or add ids. Each candidate's `tags`,
`oracle_types`, `domains`, `subdomains`, and `languages` **equal** the
matching slot (not a new subset).

Phase 04 already chose Global node-sets, Local surface variants, and which
slots are complexified. Your job is to write Harbor files for those slots:

- Use the slot's `scenario_angle`, `output_shape`, `primary_entrypoint`, and
  `primary_input` as the job. Same `global_id` means the same concept; the
  surface (angle, output, input, entrypoint) is what differs.
- Combine the slot tags so they actually interact in the job. The instruction
  goal must name the interacting pieces.
- Classify by primary skill, not incidental tooling. `domains` come from
  the closed Terminal-Bench set (`science`, `software`, `ml`, `operations`,
  `security`, `hardware`, `media`). `subdomains` come from
  `target.subdomains` (seed names in `/opt/terminaltraj/scripts/taxonomy.md`,
  plus kebab extensions already listed there).
- If `complexified` is true, the instruction **goal** must name
  `complexity_delta` as interacting pieces (second subsystem, hidden
  invariant, extra oracle), not as a recipe. Stay inside `target.difficulty`;
  do not bump the band.
- Do not copy `scenario_angle` / `complexity_delta` into
  `05_task_design.json`. That index stays identity plus vocab lists plus
  `env_build` / `oracle_tools`. Read those fields from the Simula file when
  writing the instruction.

Tag meaning (each listed tag must come from `target.tags`). Tags describe
skill and tech, not a closed task-kind enum. Typical combinations:

- `cli` / `tool-use` / `data-pipeline` / `etl` / `analysis`: run installed
  tools on provided inputs; do not edit source. Data work reads `data_dir`
  and writes `results_dir`.
- `repair` / `debugging` / `troubleshooting`: fix a stated defect; oracle
  covers the failing case plus a regression check.
- `feature` / `implementation` / `refactoring`: bounded source/interface
  change that adds or reshapes behavior while keeping unstated behavior.
- `configuration` / `ops` / `deployment`: change runtime config, services,
  permissions, or process state; the oracle is a state predicate.
- `build` / `build-system`: compile/package/port/run a component from source
  in this environment; success is an artifact plus a working entrypoint.
- `optimization` / `performance` / `profiling`: improve a measurable
  property of an existing command or program with stated behavior unchanged.

Oracle-type meaning (each listed type must come from `target.oracle_types`).
A candidate with two or more oracle types must actually use each: for example
`result` plus `state` means an output artifact **and** a leftover process or
filesystem predicate, not two names for the same check.

- `result`: compare output artifacts to a golden value or invariant.
- `state`: filesystem/process/port/service predicates after the agent stops.
- `behavior`: probe the program or service with inputs and check responses.

### Step 03: calibrate difficulty to `target.difficulty`

All candidates use `target.difficulty`. Bands are **SOTA-agent wall-clock**
(not human-expert minutes). Write them into `task.toml` as
`expert_time_estimate_min` (keep the Harbor/TB field name):

| difficulty | SOTA agent | shape |
| ---------- | ---------- | ----- |
| easy | at most 1h (1-60 min) | one or two tools, one output artifact, at most one non-obvious quirk or flag |
| medium | 1-3h (60-180 min) | 2+ tools or a compatible source change, several outputs or edge cases, at least one requirement that needs reading docs/source |
| hard | 3-6h (180-360 min) | sparse docs, cross-component behavior, repair plus regression, or a hidden invariant; plausible shortcuts are wrong |
| ultra | 6h or more (360-720 min) | compound: two or more interacting hard parts (not a long linear checklist). Name the interacting pieces in the instruction goal, not as a step-by-step recipe |

`junior_time_estimate_min` is at least 2x that SOTA estimate (weaker-agent
budget; still required by the Harbor metadata shape). Difficulty comes from
real reasoning (the right flag, the right join key, the quirk in the data,
the invariant to preserve, or interacting subsystems), never from vague
wording, trick questions, tedium, or byte-exact formatting minutiae.

The skill examples label themselves easy/medium/hard with 300s-900s agent
timeouts. Those labels are **demo tags**, not this factory's bands. Example 1
(one-line fib bug) is minutes of work; Example 2 (five Flask routes) and
Example 3 (add a column and a view) would fail `target.difficulty` here
unless the spec is `easy` and the repository genuinely has nothing harder.
Do not copy their timeouts or their `difficulty` strings.

### Step 04: write every instruction.md first

User-facing only. Goal first, absolute paths in backticks, brief (about two to
four paragraphs). No verifier talk, no golden answers, no step-by-step tool
recipe, no headings/roleplay/tool laundry lists. Success must be checkable from
the end state. Structured outputs need a normative schema in the text (exact
file names, columns/keys and their order, delimiter, encoding, trailing
newline, rounding). State constraints only when they are mechanistic
anti-cheat rules ("do not modify files under `/data`"), not process
prescriptions.

Harbor instruction rules (from the skill; the example texts are very simple
demos, not a voice to clone):

- The instruction is the only thing the later agent sees. It must be
  self-contained. Agents cannot ask clarifying questions.
- Name every output path the tests will check. Do not say "submit your
  answer"; agents write files. Do not mention tests, scoring, or
  `tests/` / `solution/` paths.
- Skill Example 1 uses a markdown H1 ("Fix the Fibonacci Function") and
  a one-file toy bug. Do **not** copy that heading style (this factory
  wants goal-first paragraphs, no headings) and do not emit a one-line
  fib/sort repair as a candidate unless `target.difficulty` is `easy`
  and the repo has nothing else.
- Skill Example 2/4 show the useful part: every endpoint or JSON key is
  specified so two reviewers would write the same verifier. Keep that
  precision; drop the tutorial tone and the tiny scope.

Write `instruction.md` as **pure ASCII**. Do not use em-dashes, en-dashes,
smart quotes, arrows, or other non-ASCII punctuation; use `-`, `'`, `"`, and
`->` instead. Harbor reads `instruction.md` with the host locale encoding (GBK
on Windows zh-CN), so any byte above 0x7F crashes the trial before the agent
starts.

Apply realism and anti-leak rules:

- The task is grounded in this repository's actual tools and this
  environment's actual fixtures. Reference real paths under `data_dir`.
- Prefer inputs with genuine quirks over clean toy files; the instruction
  states the requirement, not the quirk (the agent must discover it).
- Nothing in the image may contain the answer: no expected outputs shipped
  next to inputs that the task asks the agent to produce, no golden files, no
  solution scripts. If a vendored `*_converted.*` or reference file would give
  the answer away, choose an output that differs from it (subset, filter,
  join, reshape, different format) or a different input.
- Do not require network, secrets, or tools outside `entrypoints` plus the
  standard shell/Python in the image.
- Do not ask for anything the verifier cannot check from the end state.

Do not write `task.toml` or overlay files until every candidate has
`instruction.md` on disk.

### Step 05: write each task.toml

Synthesize a single-step Harbor `task.toml` from the Harbor task-creator
skill. Read these files before writing any toml:

```text
/opt/terminaltraj/skills/harbor-task-creator/SKILL.md
/opt/terminaltraj/skills/harbor-task-creator/references/task-toml-reference.md
/opt/terminaltraj/skills/harbor-task-creator/references/example-tasks.md
```

Use the skill for Harbor field names, types, and defaults only. Do not follow
its tests/, solution/, or Dockerfile recipes in this phase (phase 07 owns
tests; the sealed base owns the image). Write `task.toml` as **pure ASCII**.
No `[[steps]]`, no `[environment].docker_image`, no invented keys.

The example `task.toml` files in `example-tasks.md` are very simple demos:
top-level `version = "1.0"`, `category = "programming"`, 300s-900s
timeouts, no `[task]` table. Do not copy those. Follow the factory overlay
below. Do not add `[[environment.mcp_servers]]` unless this repository
actually ships an MCP server the agent must call.

Factory overlay (check-design enforces this; it is not in the skill):

- Top-level `schema_version = "1.4"` plus a `[task]` table. Do not use the
  skill's top-level `version = "1.0"` in place of `[task]`.
- Keep `[task]`: `name = "terminaltraj/<id-or-short-slug>"`, `description`
  one sentence matching the instruction goal, `keywords` >= 1 (domain,
  subdomain, tag, primary entrypoint, technique), `authors` as in prior
  packages.
- `[metadata]` vocabulary lists equal the index entry (`tags`, `domains`,
  `subdomains`, `languages`, `oracle_types`); `difficulty` equals
  `target.difficulty`. `category` is the Terminal-Bench Title Case of
  **one** candidate domain (`Science`, `Software`, `ML`, `Operations`,
  `Security`, `Hardware`, `Media`). `subcategory` is the packaged spelling
  of **one** candidate subdomain (seed Title Case from taxonomy.md, or the
  kebab token for an extension). `tags` equals the index `tags` list.
- `expert_time_estimate_min` is SOTA-agent minutes inside the band above;
  `junior_time_estimate_min >= 2 x` that estimate.
- `[agent].timeout_sec` >= 300 and >= the SOTA estimate in seconds
  (`expert_time_estimate_min * 60`). Do not set `[agent].network_mode`.
- `[verifier].timeout_sec` >= 60.
- `[environment].network_mode = "public"` always (runtime Harbor agent
  install; do not copy 03 `network_policy`; do not set the skill's
  `allow_internet = false`).
- `[environment].build_timeout_sec` >= 600. If 03 `build` has
  `build_seconds`, use at least 2 x that; otherwise 900, or 1800 when the
  image compiles native code.
- `[environment].cpus` >= 1, `memory_mb` >= 1024, `storage_mb` >= 4096;
  `workdir` equals the 03 workdir when set. Raise CPU/memory from the
  sealed environment, not by habit.

### Step 06: write each overlay environment/

Every candidate needs `/synthesis/output/candidates/<id>/environment/` (create
it even if empty of files). Phase 09 merges this tree over the sealed base
(overlay wins on the same relative path).

After the instruction exists, decide how phase 07 will observe success
(file content, process/port, CLI probe, hash). List those commands in
`oracle_tools`. If a tool is missing from 03 `entrypoints`, install it
in this overlay (`setup-overlay.sh` preferred; full Dockerfile only when
the image itself must change). Typical adds: `python3` (stdlib) for JSON
or structured checks, `jq` for JSON, `redis-cli` if the base did not
declare it. Do not add pytest "for Harbor style". Verify-time `apt-get`
is forbidden, so missing tools belong here, not in `test.sh`.

Add-only rules:

- Extra fixtures, broken configs, patches, observation tools, and
  candidate-specific inputs go here. Do not delete base entrypoints,
  directories, or dependencies.
- Do not write `environment.json` or `docker-compose.yaml` in the overlay
  (the sealed base owns topology and the env contract).
- Assets-only overlay (files under `assets/` or other data files, no
  Dockerfile / setup / smoke): set `env_build` to `not_required`. Do not
  rebuild.
- If you add `setup-overlay.sh` only: that file replaces the base no-op at
  merge time. Docker-build a **scratch merge** (copy base, copy overlay on
  top, `docker build`) to prove it, then set `env_build=passed`. Do not
  change `/synthesis/output/environment/`.
- If you add `Dockerfile`, `setup.sh`, or `smoke_test.sh`: the overlay
  Dockerfile must be a **complete, independently buildable** Harbor
  environment Dockerfile (`FROM` a public base, `git clone` the pinned
  commit, `COPY`/`RUN` setup). Never `FROM synth-env:03` or any local tag;
  Harbor rebuilds the packaged image in isolation. Prove it with
  `docker build` of that overlay directory (or a scratch merge if you only
  replaced setup-overlay.sh). Set `env_build=passed` or `failed`.
- Overlay build failure does not rewrite the sealed base. Record
  `env_build=failed`; phase 06 will reject that candidate.
- Skill Example 1/2 Dockerfiles (`FROM python:3.12-slim`, COPY one toy
  file, empty WORKDIR) are very simple demo **task** images, not overlays
  on a shared base. Prefer assets or `setup-overlay.sh`. A full overlay
  Dockerfile is only for a candidate that cannot share the sealed image.
  Observation tools (`python3`, a CLI) go in `setup-overlay.sh` unless
  the image itself must change.

Do not re-run `check-environment` on the sealed base.

## GATE

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 04_simula_plan
python /opt/terminaltraj/scripts/target_spec.py require-handoff 05_task_design
python /opt/terminaltraj/scripts/target_spec.py check-design \
  /synthesis/input/target_spec.json \
  /synthesis/state/05_task_design.json \
  /synthesis/output/candidates
```

Fix anything it reports, then stop. Do not start phase 06/07 work in this turn.
