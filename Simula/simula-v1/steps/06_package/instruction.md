# Phase 06: package

## ROLE

Assemble only one Harbor package per valid candidate, validate its declared layout,
and run nop against the assembled package. Own
`/synthesis/output/generated_task/manifest.json`.

## BOUNDARIES

- Do not redesign instructions, task manifests, steps, or verifiers.
- Do not modify candidate files; repair assembly defects in packaged copies.
- Do not change a slot's deployment dimensions to bypass a package failure.
- Do not add a Simula wrapper around Harbor APIs or skip required nop trials.

## INPUTS

- `/synthesis/state/02_environment.json`
- `/synthesis/state/04_task_design.json`
- `/synthesis/state/05_verifier.json`
- `/synthesis/output/candidates/<id>/`

The environment handoff supplies `source_repo.commit`. Package every valid
candidate in verifier-index order. Read
`/opt/terminaltraj/skills/simula-synthesis/references/packaging.md` for Harbor
validation, nop execution, GPU configuration, and package repair rules.

## HANDOFF

For each candidate create `/synthesis/output/generated_task/<slug>/` with:

```text
<slug>/task.toml
<slug>/environment/
<slug>/instruction.md       # single-step task
<slug>/tests/               # root verifier or shared step verifier
<slug>/steps/<name>/        # multiple-step task: instructions and step tests
<slug>/README.md
```

Use the layout declared by `task.toml`; multiple-step packages need no root
instruction and may use step-specific or shared tests. Write
`generated_task/manifest.json` with `candidate_id`, `path`, `deployment_mode`,
and the pinned source commit for every package. Use a unique lowercase
kebab-case slug of at most three words.

## WORK

### Step 01: assemble

Validate the upstream handoffs:

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 02_environment
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 04_task_design
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 05_verifier
```

Initially copy the candidate environment verbatim, with its task manifest,
instructions, and verifier trees. Preserve `tests/` and `steps/` byte-for-byte;
only align `[task].name` with the slug if needed. Write a short README with
candidate id, slug, source URL/commit, and phase provenance.

### Step 02: validate assembly

Run the assembly check:

```bash
python /opt/terminaltraj/scripts/phase_contract.py check-package \
  /synthesis/state/02_environment.json \
  /synthesis/state/04_task_design.json \
  /synthesis/state/05_verifier.json \
  /synthesis/output/environment \
  /synthesis/output/candidates \
  /synthesis/output/generated_task
```

Fix copy or identity mismatches in the package. Then run the Harbor library
validation defined in `packaging.md` for every manifest entry.

### Step 03: run nop and finalize

Run the shared nop procedure against every assembled package. Actual
`[environment].gpus > 0` requires Daytona and `DAYTONA_API_KEY`; a missing key,
failed trial, or missing reward fails the package. Repair only assembled
environment or copy defects, then repeat validation and nop. Retain the
candidate contract and manifest order throughout repairs.

## GATE

Finish only when every package has the declared Harbor layout, README, and no
extra top-level files; assembly and Harbor validation succeed; and actual nop
returns reward `0` for every package. The final assembly check allows
environment-only nop repairs while preserving instructions, tests, steps, and
task configuration.
