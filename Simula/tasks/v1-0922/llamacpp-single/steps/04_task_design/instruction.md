# Phase 04: task design

## ROLE

Create one candidate per sealed plan slot: self-contained task instructions,
a customized environment, and an entry in `/synthesis/state/04_task_design.json`.

## BOUNDARIES

- Do not modify upstream handoffs or `/synthesis/output/environment/`.
- Do not create task manifests or verifier tests in this phase.
- Do not build or run candidate images.
- Do not let subagents write outside their assigned candidate's root or step
  `instruction.md` files and `environment/`.

## INPUTS

- `/synthesis/state/02_environment.json`
- `/synthesis/state/03_simula_plan.json`
- `/synthesis/output/environment/`

The slot, its parent `plan.global` row, and `plan.difficulty` define the task.
Read every slot field and apply it; do not treat the slot as a summary to
sample from. The environment contract supplies the source URL/commit, paths,
entrypoints, topology, and resource limits.

Read these resources under `/opt/terminaltraj/` before delegating:

- `skills/simula-synthesis/references/instruction.md`
- `skills/simula-synthesis/references/environment.md`, candidate-copy section
- `docs/difficulty.md`, the shared difficulty definition

`complexity_delta` is a list of `{"axis": "<kebab>", "text": "<non-empty>"}`
items. For `hard` and `ultra` it carries 3 or 4 items, always including
`coupling`. These are the only axes, and phase 03 already chose which ones a
slot carries. Realize exactly the axes in the list, and do not add one it omits:

- `coupling`: two constraints the agent must satisfy together, and what a
  plausible partial fix leaves broken.
- `long-horizon`: the reasoning must cross existing components and state
  transitions, so the repair cannot be localized to one edit.
- `complex-environment`: the starting state is understandable only by exploring
  the sealed base, because no single file explains the joint behavior.
- `compound-task`: focused on one domain from the parent global row, with the
  second constraint pulling in other domains that row covers and changing the
  correct repair.
- `cyclic-dependency`: a minimal local fix of one constraint changes the
  conditions of the other and leaves a further failure.
- `false-shortcut`: a locally consistent repair looks right, survives a shallow
  check, and fails an acceptance condition.
- `live-constraint`: an invariant the sealed base already checks continuously
  while the repair happens, so there is no safe window to stop and edit.
- `evidence-ambiguity`: the observed phenomena support more than one
  explanation, and only one observation distinguishes them.

Each item's `text` is a design input for this phase, not phrasing for the
instruction. The instruction shows the phenomena and must not reveal which
repair fails, which shortcut is tempting, which explanation is wrong, or which
observation distinguishes them.

`deployment_dimensions` has five keys, and all five bind the candidate:

- `container_mode`: `single` stays on the copied Dockerfile; `multiple` keeps
  the copied compose and edits only the services this slot needs. Never add
  compose to a single-container base or drop it from a compose base.
- `verifier_mode`: `inline` puts the verifier in the candidate environment;
  `separate` puts it in its own image. Phase 05 writes the verifier. Record the
  choice so that phase can follow it; do not build either image here.
- `step_mode`: `single` writes the root `instruction.md`; `multiple` writes at
  least two `steps/<name>/instruction.md` files that share one environment and
  preserve runtime state in execution order, and records that order.
- `gpu`: `none` leaves GPUs at 0; `optional` may use 0 or 1; `required` sets
  `resources.gpus = 1`. Do not add a GPU the sealed base does not allocate.
- `mcp`: `none` adds no MCP server; `optional` and `required` need a server
  whose stdio `command` exists in the candidate environment. Agent network is
  `public`, so an HTTP MCP url is reachable.

`plan.difficulty` is the work band from `docs/difficulty.md`. Apply it, and do
not relabel it. Difficulty is the reasoning required before the method is known;
enlarging the environment or adding edits does not raise it.

For Harbor layout examples, consult
https://github.com/harbor-framework/harbor/tree/main/examples/tasks.

## HANDOFF

For each slot id, produce the layout selected by `step_mode`:

```text
/synthesis/output/candidates/<id>/environment/
/synthesis/output/candidates/<id>/instruction.md               # single
/synthesis/output/candidates/<id>/steps/<name>/instruction.md  # multiple
```

For `step_mode=multiple`, also record an ordered `steps` list of at least two
unique step names in the design record; a root instruction is not required.

For `step_mode=multiple`, also produce the ordered native step instructions
under `/synthesis/output/candidates/<id>/steps/<name>/instruction.md`. These
files belong to phase 04; phase 05 consumes them and adds only the matching
manifest and verifier entries.Visit https://docs.harborframework.com/core-concepts/tasks/multi-step#adding-step-specific-environment-files for more multi-step informations.

The design index contains a `candidates` list. Each record has `id` and
`oracle_tools`; a multiple-step record also has its ordered `steps` names.
Task attributes are resolved from the plan by id. The main agent owns this
index.

## WORK

### Step 01: prepare and delegate

Run `python /opt/terminaltraj/scripts/phase_contract.py ensure-handoff 04_task_design`.
Copy the sealed environment into each candidate directory and register its id
in the design index as the directory is created.

Assign one subagent per slot, scheduling within available capacity. Apply
progressive disclosure only to the spec: the subagent must not reread
`/synthesis/input/target_spec.json`, because the slot already carries it.
Carry full context otherwise. Paste the following verbatim into every
assignment, so the subagent does not re-read or truncate them:

- the slot's complete field set, every key and value
- the full parent global row
- `plan.difficulty`
- the complete text of `docs/difficulty.md`
- the complete text of `references/instruction.md`
- the environment-contract excerpts the slot uses: source URL and commit,
  paths, entrypoints, topology, and resource limits
- the assigned candidate output paths

Do not include other slots. A summary or a path in place of one of these
documents is not full context.

### Step 02: design the candidate

Each subagent completes its assigned instruction and environment:

- Use `mechanism` and `scenario_angle` to establish the current situation as
  observable phenomena. Use `output_shape` and parent `oracle_types` to define
  acceptance criteria with concrete inputs, outputs, and operating constraints.
- Realize each item of `complexity_delta` in the environment and require its
  outcome in the instruction. The list has 3 or 4 items for `hard` and `ultra`;
  realize exactly those `axis` values and no others. Apply `plan.difficulty`
  using the shared definition and its disclosure rules, retaining useful symptom
  logs, failing commands, and reproduction conditions. Each item's `text` is a
  design input, not phrasing to copy: do not quote it, paraphrase it, or let the
  instruction reveal which repair fails, which shortcut is tempting, which
  explanation is wrong, or which observation distinguishes them. Show phenomena
  only. Do not raise difficulty by enlarging the environment or adding edits,
  and do not ground it on knowledge outside the pinned repository. Do not name a
  defect file, a planted fault, or a prescribed repair.
- Use `primary_entrypoint` and `primary_input` for task paths and keep domain,
  language, and terminology consistent with the parent global row. For
  `step_mode=multiple`, write a sequence of observable stages in the step
  instruction files and return their execution order.
- Customize the copied source, scripts, or assets to establish the slot's
  starting state. Follow the candidate-copy environment rules for topology,
  runtime dependencies, and MCP wiring.

Apply the instruction reference's quality and format rules. Return the
completed paths and the available tools needed to verify the acceptance criteria.

### Step 03: collect and validate

Wait for every candidate subagent to finish and collect its result. Resume or
complete unfinished work before proceeding. Inspect the actual files against
the assigned slot, the environment contract, and the referenced quality rules;
record each candidate's `oracle_tools` and native step order in the design index.

Check each candidate against its slot's `complexity_delta` item by item. For
every `axis` in the list, the environment must realize that item's `text` and
the instruction must make its outcome observable as phenomena. An axis in the
list with no corresponding phenomenon, or a phenomenon that adds an axis the
list does not contain, goes back to the subagent. Confirm the instruction does
not quote or paraphrase the item's `text` and does not reveal which repair
fails, which shortcut is tempting, which explanation is wrong, or which
observation distinguishes them.

Check each candidate against all five `deployment_dimensions`: the copy keeps
the sealed `container_mode`, the recorded verifier choice matches
`verifier_mode`, the instruction layout and `steps` order match `step_mode`,
the GPU count matches `gpu`, and an `mcp` server, when required, has its
command in the candidate environment. A candidate that drops or flips any of
the five is not done.

Check shell scripts with `bash -n`. Review instruction diversity across the
batch: openings, acceptance criteria, and environment changes must reflect the
distinct slots. Repair any missing, inconsistent, or invalid candidate files.

## GATE

Finish only after all subagent work is complete, every slot has a valid candidate,
the design index is complete, and both commands below succeed:

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 04_task_design
python /opt/terminaltraj/scripts/phase_contract.py check-design \
  /synthesis/state/04_task_design.json \
  /synthesis/output/candidates
```

Resolve all reported errors before returning the handoff.
