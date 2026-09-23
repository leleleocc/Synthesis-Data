# Phase 04: Simula plan (global, local, complexity)

## ROLE

You are phase 04 only. Run from files on disk; do not rely on chat history.
You own only `/synthesis/state/04_simula_plan.json`. This is paper sampling,
not task design. You do not write candidates, instructions, overlays, tests,
or edits under `/synthesis/output/environment/`.

Naive generation clusters on a few semantic modes. This phase is the sampling
scaffold: Global Diversification picks fewer node-sets, Local Diversification
expands each node-set into surface variants, Complexification flags a fraction
of slots. Phase 05 instantiates Harbor files from those slots.

## BOUNDARIES

- Treat `/synthesis/input/repository` as read-only reference input. Do not write,
  install, build, or run tests inside it. If you need to inspect the repository,
  copy it to a scratch directory such as `/tmp/repo`.
- Treat prior state JSON files and their `.integrity/*.sha256` seals as
  read-only. Do not modify `/synthesis/output/environment/`.
- Do not write:
  - `/synthesis/output/candidates/**`
  - any `instruction.md`, `task.toml`, overlay, `tests/`, or golden files
  - later state files (`05_task_design.json`, ...)
- Do not docker-build. Do not re-run `check-environment`.
- Do not invent capabilities the sealed base does not host. Every
  `primary_entrypoint` must be an argv0 from `03_environment.json` `entrypoints`.
- Do not change `target.difficulty`. Complexification stays **inside that band**.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 05+ work in this turn.

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- `/synthesis/state/01_repo_profile.json`
- `/synthesis/state/02_repo_gate.json`
- `/synthesis/state/03_environment.json` (the sealed environment contract)
- `/opt/terminaltraj/scripts/taxonomy.md` (closed domains, seed subdomains)
- the source repository at `target_spec.source_repo.path` (read-only)
- `/synthesis/output/environment/` (read-only; open vendored fixtures if you
  need real paths for `primary_input`)

Ground the plan in those files. This is not a seedless taxonomy. Closed
vocabulary lists come from `target.*`. Runtime facts come from 03
(`entrypoints`, `asset_paths` / `data_dir` fixtures, services,
`network_policy`).

## HANDOFF

Hard gate: `/synthesis/state/04_simula_plan.json`. Stopping without that file
fails the phase.

Land the skeleton before sampling:

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 04_simula_plan
```

Do not put factor trees in JSON. Slot `id` is the later candidate id. Vocab
lists on a slot **equal** its `global` row (local does not retarget tags).
`complexity_delta` is non-empty ASCII if and only if `complexified` is true;
use `""` otherwise.

Final shape (N=6 illustration; your slot count is `generation.max_candidates`):

```json
{
  "global": [
    {
      "id": "g1",
      "tags": ["debugging", "repair", "persistence"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["state", "behavior"],
      "primary_entrypoint": "redis-server"
    },
    {
      "id": "g2",
      "tags": ["build", "optimization", "cli"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["result", "behavior"],
      "primary_entrypoint": "redis-cli"
    },
    {
      "id": "g3",
      "tags": ["caching", "linux", "redis"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["result", "state"],
      "primary_entrypoint": "redis-server"
    }
  ],
  "slots": [
    {
      "id": "c1",
      "global_id": "g1",
      "tags": ["debugging", "repair", "persistence"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["state", "behavior"],
      "scenario_angle": "incident-cleanup",
      "output_shape": "running-process-and-config",
      "primary_entrypoint": "redis-server",
      "primary_input": "/data/redis.conf",
      "complexified": true,
      "complexity_delta": "preserve replica offset while rewriting AOF"
    },
    {
      "id": "c2",
      "global_id": "g1",
      "tags": ["debugging", "repair", "persistence"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["state", "behavior"],
      "scenario_angle": "audit",
      "output_shape": "repaired-source-tree",
      "primary_entrypoint": "redis-cli",
      "primary_input": "/data/dump.rdb",
      "complexified": false,
      "complexity_delta": ""
    },
    {
      "id": "c3",
      "global_id": "g2",
      "tags": ["build", "optimization", "cli"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["result", "behavior"],
      "scenario_angle": "migration",
      "output_shape": "compiled-binary",
      "primary_entrypoint": "redis-server",
      "primary_input": "/src/Makefile",
      "complexified": true,
      "complexity_delta": "keep the replica handshake while changing compiler flags"
    },
    {
      "id": "c4",
      "global_id": "g2",
      "tags": ["build", "optimization", "cli"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["result", "behavior"],
      "scenario_angle": "onboarding",
      "output_shape": "persistence-files",
      "primary_entrypoint": "redis-cli",
      "primary_input": "/data/appendonly.aof",
      "complexified": false,
      "complexity_delta": ""
    },
    {
      "id": "c5",
      "global_id": "g3",
      "tags": ["caching", "linux", "redis"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["result", "state"],
      "scenario_angle": "integration",
      "output_shape": "replica-report",
      "primary_entrypoint": "redis-server",
      "primary_input": "/data/sentinel.conf",
      "complexified": false,
      "complexity_delta": ""
    },
    {
      "id": "c6",
      "global_id": "g3",
      "tags": ["caching", "linux", "redis"],
      "domains": ["software"],
      "subdomains": ["systems", "databases"],
      "languages": ["c", "shell"],
      "oracle_types": ["result", "state"],
      "scenario_angle": "reproduction",
      "output_shape": "benchmark-log",
      "primary_entrypoint": "redis-cli",
      "primary_input": "/data/nodes.conf",
      "complexified": false,
      "complexity_delta": ""
    }
  ]
}
```

Do not use singular vocabulary keys (`tag`, `domain`, `subdomain`, `language`,
`oracle_type`) and do not write `task_types`.

## WORK

Derived knobs from `generation.max_candidates` = N (do not add new spec keys):

- `local_k` = 2 if N >= 2 else 1
- G = max(1, N // local_k) global node-sets
- each node-set gets `local_k` slots; remainder `N - G * local_k` adds +1 to
  the first node-sets so the slot count is **exactly N**
- complexified count = max(1, round(N/3)) if N >= 3 else 0, capped at N-1
  (never all slots)

For N=6: G=3, local_k=2, 2 of 6 complexified.

List-min-two still applies: `tags`, `oracle_types`, `domains`, `subdomains`,
`languages` are non-empty unique subsets of the matching `target.*` lists.
When a target list has two or more values, that field must contain at least
two.

### Step 01: Global Diversification

Build factor trees from evidence, not from an empty domain. Keep the trees in
your notes; do not write them into JSON.

Closed factors: `target.tags`, `target.subdomains`, `target.oracle_types`,
`target.languages`, `target.domains`.

Grounded factors from 03: `entrypoints`, `asset_paths` / `data_dir` fixtures,
services, `network_policy` limits.

Scenario-angle factor (closed here, not in TAGS): `migration`,
`incident-cleanup`, `onboarding`, `audit`, `integration`, `reproduction`.

Sample **G node-sets**. Each node-set is the vocabulary lists plus a
`primary_entrypoint` that exists in 03 `entrypoints` (argv0 of a declared
command). Cover every `target.oracle_types` value across the G sets. Spread
tags and subdomains; do not emit G copies of one tag pair.

### Step 02: Local Diversification

For each node-set, write its K **surface variants** as slots. Slots of one
`global_id` **share** the vocab lists (copy them; do not retarget tags) and
**differ** in at least two of: `scenario_angle`, `output_shape`,
`primary_input`, `primary_entrypoint`. Same concept, different job.

`scenario_angle` is one of the six closed values above. `output_shape` is a
non-empty kebab token (for example `running-process-and-config`).
`primary_input` is a real path under the sealed `data_dir` / workdir / source
(open the fixtures; do not invent a file 03 does not have unless phase 05
will add it in an overlay - prefer a path that already exists).
`primary_entrypoint` is still an argv0 from 03 `entrypoints`.

Across the whole plan:

- no two slots share `primary_entrypoint` **and** `output_shape`
- at most two slots share a `primary_input`

Local **allows** the same tag pair across slots of one `global_id`. That is
the point.

### Step 03: Complexification

Mark `complexified=true` on exactly the derived count of slots. Name one extra
interacting piece in `complexity_delta`: a second subsystem, a hidden
invariant, or an extra oracle type still inside `target.oracle_types`.

Stay in `target.difficulty`. Do not bump a `hard` slot to `ultra`. Do not
turn the slot into a linear checklist. Unmarked slots stay at the same
difficulty with a single interaction (list-min-two tags still apply).

`complexity_delta` must be pure ASCII when set (hyphen, not em-dash).

## GATE

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 04_simula_plan
python /opt/terminaltraj/scripts/target_spec.py check-simula-plan \
  /synthesis/input/target_spec.json \
  /synthesis/state/04_simula_plan.json \
  /synthesis/state/03_environment.json
```

Fix anything it reports, then stop. Do not start phase 05+ work in this turn.
