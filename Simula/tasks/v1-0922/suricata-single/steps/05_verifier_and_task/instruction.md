# Phase 05: verifier and task

## ROLE

Create a Harbor `task.toml` and calibrated verifiers for every phase 04
candidate. Own `/synthesis/state/05_verifier.json`.

## BOUNDARIES

- Do not change upstream handoffs, root or step instructions, or the sealed
  environment. Candidate environment edits are limited to baking inline
  verifier dependencies as defined in `tests.md`.
- Do not install packages from verifier entries.
- Do not retain calibration repairs, solved outputs, or runtime state in
  the candidate's initial environment or package.
- Do not let subagents write outside their assigned candidate's `task.toml`,
  verifier trees, and permitted environment edits.

## INPUTS

- `/synthesis/state/02_environment.json`
- `/synthesis/state/03_simula_plan.json`
- `/synthesis/state/04_task_design.json`
- `/synthesis/output/candidates/<id>/`

Join each candidate to its sealed slot by id. The slot, parent `plan.global`
row, `plan.difficulty`, environment contract, and phase 04 instructions define
the task. For `step_mode=multiple`, the design record's `steps` list gives
the order of the existing `steps/<name>/instruction.md` files.

Read these references under `/opt/terminaltraj/skills/simula-synthesis/`:

- `references/task-toml.md`
- `references/tests.md`

## HANDOFF

For each candidate, produce `task.toml` and the selected verifier trees:
root `tests/`, step-local `steps/<name>/tests/`, or shared root tests used by
native steps. Each selected tree has an executable `test.sh` and its required
fixtures and helpers.

The handoff contains a `verifiers` list with one record per candidate:
`candidate_id`, `checked_requirements`, and a deterministic status.
`checked_requirements` maps every instruction success condition, including
relevant negative-space requirements, to an assertion. The main agent owns
this index; `oracle_tools` remains in the design index.

## WORK

### Step 01: prepare and delegate

Run `python /opt/terminaltraj/scripts/phase_contract.py ensure-handoff 05_verifier`.
Process each candidate, delegating within available capacity. Give each
assignment its slot, parent global row, `plan.difficulty`, design record,
environment-contract fields, candidate paths, and the two references above.

### Step 02: implement and calibrate

Create the manifest using `task-toml.md`, preserving every
`deployment_dimensions` value. Match native `[[steps]]` to phase 04's ordered
step instructions and match each instruction suffix to its effective timeout.

Design the verifier as a discriminator using `tests.md`: derive likely errors
from the acceptance criteria, then write assertions that reject those errors.
Cover both coupled constraints and map the assertions in `checked_requirements`.
Bake verifier dependencies into the appropriate image and keep fixtures,
goldens, and helpers in the selected tests tree.

Execute the actual verifier against temporarily constructed correct cases
and relevant wrong solutions in disposable runtimes. Follow `tests.md` for
reset, native-step sequencing, determinism, and recalibration after edits.
Return completed paths, requirement mappings, and executed calibration results.

### Step 03: collect and validate

Wait for every delegated task to finish; resume or complete unfinished work.
Inspect the files and calibration results before completing the verifier
index. Check shell syntax with `bash -n`, manifest alignment, and verifier
form diversity across the batch. Repair missing or inconsistent artifacts.

## GATE

Finish only when every candidate has a valid manifest, deterministic executable
verifiers, successful positive and negative calibration, and a complete record.
Both commands must succeed:

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 05_verifier
python /opt/terminaltraj/scripts/phase_contract.py check-verifiers \
  /synthesis/state/04_task_design.json \
  /synthesis/state/05_verifier.json \
  /synthesis/output/candidates
```

Resolve all reported errors before returning the handoff.
