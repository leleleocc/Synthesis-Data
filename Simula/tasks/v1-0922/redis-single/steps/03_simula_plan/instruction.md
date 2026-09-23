# Phase 03: Simula plan

## ROLE

You own `/synthesis/state/03_simula_plan.json`. Produce a paper plan for the
candidate slots. Do not create candidate files, task.toml, tests, or images.

## BOUNDARIES

- Read the target spec, the sealed phase 01 profile, the sealed phase 02
  environment contract, and the repository code at the pinned URL and commit.
  There is no staged repository directory. Use a temporary checkout, verify
  that HEAD equals `source_repo.commit`, and inspect its contents without
  changing them. If the exact checkout fails, stop without finalizing a plan.
- Do not build Docker images or re-run the environment checker.
- Do not write `/synthesis/output/candidates/` or later state files.
- Keep every value inside the target vocabulary and the environment entrypoint
  list. `primary_input` may be null when the environment has no data fixture.
- Treat `/synthesis/input/target_spec.json` as immutable and convert it here.
  After this phase, later agents join `03_simula_plan.json` and must not
  reread the full target spec. Freeze `plan.difficulty` from
  `target.difficulty`.
- Every slot is the fullest Harbor-task preview JSON. It always includes
  `deployment_dimensions` with all five keys: container mode
  (`single|multiple`), verifier mode (`separate|inline`), step mode
  (`single|multiple`), GPU (`none|optional|required`), and MCP
  (`none|optional|required`). If `target.deployment_dimensions` lists values,
  pick one per slot and cover every listed value across the batch. If the
  target leaves a dimension unconstrained, freeze the default (`single`,
  `inline`, `single`, `none`, `none`) unless the sealed base is compose
  (`container_mode=multiple`) or already allocates GPUs (`gpu=required`).
  Preserve unknown future dimensions as opaque extension keys.
- Assign every slot a closed `mechanism`: `plant-fault`, `recover-state`,
  `reimplement`, `configure-runtime`, `build-matrix`, or `protocol-decode`.
  If `target.mechanisms` is present, cover that list. Otherwise sample from
  the closed set. Repository evidence must support the chosen mechanism.
- Skills and docs under `/opt/terminaltraj/` are already in the image; they
  are not inputs. Read `/opt/terminaltraj/docs/difficulty.md` before planning;
  it defines the difficulty bands shared with phase 04. Use
  `docs/taxonomy.md` for domain names. Do not open harbor-task-creator.
  Slot field names are in this instruction.
  `phase_contract.py check-simula-plan` is the schema gate.

## INPUTS

- `/synthesis/input/target_spec.json`
- `/synthesis/state/01_repo_profile_gate.json`
- `/synthesis/state/02_environment.json`
- Repository code, tests, and docs from `source_repo.url` at
  `source_repo.commit`, as given in the target spec

## HANDOFF

Run `python /opt/terminaltraj/scripts/phase_contract.py ensure-handoff 03_simula_plan`
before sampling. Write `/synthesis/state/03_simula_plan.json` with
`difficulty`, `global`, and `slots`. Slot ids become candidate ids. This plan
is the spec for phases 04-07.

Each global row contains list fields `tags`, `domains`, `subdomains`,
`languages`, and `oracle_types`, plus `primary_entrypoint`. Each slot contains
local axes: `id`, `global_id`, `mechanism`, `scenario_angle`,
`output_shape`, `primary_entrypoint`, `primary_input`, `complexified`,
`complexity_delta`, and `deployment_dimensions`. Do not copy vocabulary lists
or `difficulty` onto a slot; join the parent global row by `global_id`. Use
`null` for `primary_input` when no data directory is needed. Every slot sets
`complexified` to true. `complexity_delta` is a list of
`{"axis": "<kebab>", "text": "<non-empty>"}` items, not a prose string and not
another output file. A single unconstrained mechanism is not a valid candidate.

The taxonomy must stay diverse, scalable, and explainable: global rows are
the vocabulary node-sets, local slots vary mechanism and output, and
`complexity_delta` names the coupled constraints so a later agent
can join the slot without the original spec.

## WORK

### Step 01: inspect the repository and establish feasibility

Read the relevant implementations, existing tests, configuration, and run
paths at the exact commit. Use the profile to navigate, then verify the
behavior in the code before designing slots. Follow
`/opt/terminaltraj/docs/difficulty.md`: establish a starting state that phase
04 can construct, constraints that actually interact, observable outcomes
that phase 05 can check, and a credible repair or completion path within the
sealed environment and resource budget. Do not implement a solution here.

Plan directly from that assessment. Resolve feasibility issues before
freezing a slot; do not fill a mechanism or complexity quota with a scenario
that the repository cannot support. Keep this reasoning within planning;
do not add a candidate ranking stage or new handoff artifacts.

### Step 02: Global Diversification

Choose a small set of distinct evidence-grounded global rows. Every list is a
non-empty unique subset of the corresponding target list. Keep the union of
global `oracle_types` covering the target oracle types.

### Step 03: Local Diversification

For each global row, create local slots that vary `mechanism`,
`scenario_angle`, `output_shape`, and entrypoint while preserving that row's
vocabulary. The number of slots must equal `generation.max_candidates`. Use at
least `min(N, 3)` distinct mechanisms. `scenario_angle` is a free kebab for
local flavor; mechanism is the batch diversity axis.

### Step 04: Complexification

Every slot is compound. `complexity_delta` is a list of objects,
`{"axis": "<kebab>", "text": "<non-empty>"}`, not a prose string. The `coupling`
item is required on every slot: it names the two constraints the agent must
satisfy together, the causal chain, constraint conflict, component interaction,
or state transition that joins them, and what a plausible partial fix would
leave broken. Use interactions observed in the repository, such as rewrite vs
replica offset or failover vs demotion. A slot whose only mechanism is
unconstrained is too easy and fails the gate. Withholding logs or reproduction
clues does not raise its difficulty. Keep complexity inside `target.difficulty`;
do not add a difficulty enum, a slot field, or a second output file.

`phase_contract.py check-simula-plan` checks the list shape: each `axis` is one
of the closed axis names below, each `text` is non-empty, and a `hard` or
`ultra` slot carries 3 or 4 items including `coupling`. It does not judge
whether a text is feasible. That judgment is this step's.

When `plan.difficulty` is `hard` or `ultra`, choose 3 or 4 axes per slot,
counting `coupling`, and vary the choice across the batch. Do not put all of
them on every slot. Pick only axes the pinned repository can actually exhibit
and the sealed base environment can realize. `live-constraint` in particular
requires a service the sealed base already runs continuously while the repair
happens; a task whose agent edits source and then reruns has no such window,
so do not select it there. Measure difficulty by the reasoning required before
the method is known, not by the amount of work after it is known. Once the
approach is understood, carrying it out should be a few hours, not weeks.
Enlarging the environment, lengthening the exploration, or adding repetitive
edits does not raise difficulty. Do not invent containers, GPUs, resources, or
external domain knowledge the base does not have, and do not relabel
`plan.difficulty`.

- `coupling` (required): the two constraints and how they interact, as above.
- `long-horizon`: name the existing components and state transitions the
  reasoning must cross, so the repair cannot be localized to one edit. The
  length comes from the chain of reasoning, not from how long the edits take.
- `complex-environment`: the starting state is understandable only by exploring
  the sealed base, because the relevant behavior is spread across components
  whose joint behavior no single file explains. Add complexity as an overlay on
  that base, never as a new container or service. Exploration that is long only
  because the tree is large does not count.
- `compound-task`: the slot stays focused on one domain from the parent global
  row, and the second constraint pulls in other domains that row already covers.
  The second domain must change the correct repair, not merely appear alongside it.
- `cyclic-dependency`: state what a minimal local fix leaves broken, and which
  further failure that fix causes. A naive fix of one constraint must change the
  conditions of the other. Two independent edits do not count.
- `false-shortcut`: name a locally consistent repair that looks right and
  survives a shallow check, and the acceptance condition under which it fails.
  Restarting, reverting, or anchoring to the first measurement are typical
  shapes. A shortcut that fails obviously does not count.
- `live-constraint`: name an invariant that the sealed base already checks
  continuously while the repair happens, so there is no safe window in which to
  stop the system and edit. Select it only when that running service exists. A
  repair that only has to hold before and after, with a quiet gap in between,
  does not count.
- `evidence-ambiguity`: name at least two explanations the observed phenomena
  support, and the observation that distinguishes them. The agent must design
  that observation; the text must not reveal which explanation is correct.

Each `text` is a design input for phase 04, not phrasing to hand to the
task-solving agent. Say what phase 04 must realize and what its instruction
must not reveal.

Domain expertise that lives outside the pinned repository is not a source of
difficulty. Do not ground a slot on rate tables, regulatory formulas,
specialist terminology, or any knowledge the repository's code, tests, and
docs do not contain. A slot whose difficulty depends on such knowledge is
invented and fails this step.

`scenario_angle` stays a free kebab naming the shape of the work, such as
`multi-stage-diagnosis`, `environment-exploration`, `cross-domain-repair`,
`cascade-untangle`, `false-shortcut`, `live-invariant`, or
`ambiguous-evidence`. These are examples, not a closed list.

### Step 05: Harbor preview

Fill `deployment_dimensions` on every slot. Cover requested target values.
Default unconstrained axes. Match `container_mode` to the sealed
`deployment_mode` (`single` vs `compose`/`multiple`).

### Step 06: self-check

Run:

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 03_simula_plan
python /opt/terminaltraj/scripts/phase_contract.py check-simula-plan \
  /synthesis/input/target_spec.json \
  /synthesis/state/03_simula_plan.json \
  /synthesis/state/02_environment.json
```

Fix every error before stopping.

## GATE

The only phase output is the validated `03_simula_plan.json`. Seal it with the
phase test; leave candidate and verifier files for later phases.
