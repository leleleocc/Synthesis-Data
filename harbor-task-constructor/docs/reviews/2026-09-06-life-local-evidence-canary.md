# Life-local evidence real Harbor/Daytona canary

## Scope and release rule

This is the Task 9 production canary from
`docs/superpowers/plans/2026-09-06-life-local-evidence.md`, run in the isolated
`life-local-evidence` worktree at commit
`a362a12c64c491c1e759145febb40be7583917a2`.

The protected environment file was sourced only by the fresh-run command. No
credential value is printed or recorded here. A provider, Daytona, sandbox, or
compact-publication failure is a failed gate, not a passing canary.

## Preflight

- Canary root: `jobs/life-local-evidence-canary-20260906` was absent before any
  creation.
- Recovered source:
  `/Users/likuanye/CodexProjects/harbor-task-constructor/exports/recovered-round4-stalled-tasks-20260906/eeb26954-397b-4062-aedb-8b4fc03a21dc`
- Protected env path (values intentionally omitted):
  `/Users/likuanye/CodexProjects/harbor-task-constructor/.env.local`
- Pinned Harbor Python:
  `/Users/likuanye/.local/share/uv/tools/harbor/bin/python3`; Harbor reports
  `0.21.0`.
- Legacy inputs: `round-0006-full.tar.gz` = 487228318 bytes;
  `round-0007-thin.tar.gz` = 8865240 bytes; `resume.md` = 70592 bytes;
  `task.toml` = 1210 bytes.

## Gate record

### Gate 1 — legacy import and indexed canary seed: FAILED

Executed from the isolated worktree (all host-side Python commands used the
pinned Harbor interpreter):

```text
test ! -e jobs/life-local-evidence-canary-20260906                 exit 0
mkdir -p jobs/life-local-evidence-canary-20260906/{legacy-source/evidence,legacy-source/task,runtime}
copy recovered task tree and resume into legacy-source               exit 0
/Users/likuanye/.local/share/uv/tools/harbor/bin/python3 scripts/import-legacy-round.py \
  <recovered>/evidence/round-0006-full.tar.gz \
  jobs/life-local-evidence-canary-20260906/legacy-source/evidence --kind real
                                                                  exit 0
/Users/likuanye/.local/share/uv/tools/harbor/bin/python3 scripts/import-legacy-round.py \
  <recovered>/evidence/round-0007-thin.tar.gz \
  jobs/life-local-evidence-canary-20260906/legacy-source/evidence --kind regrade \
  --source-round round-0006                                exit 0
/Users/likuanye/.local/share/uv/tools/harbor/bin/python3 scripts/pack-seed.py \
  jobs/life-local-evidence-canary-20260906/legacy-source \
  jobs/life-local-evidence-canary-20260906/build            exit 2
```

The two imports produced schema-v1 metadata as expected:

```json
{"schema_version": 1, "kind": "real"}
{"schema_version": 1, "kind": "regrade", "source_round": "round-0006"}
```

The imported `legacy-source` is 36272 KiB and contains 470 regular files. No
`build/` was created after the failed pack, so there is no index provenance,
packed size/count, launcher validation, or outer configuration result to claim.

The exact packer refusal was:

```text
compact round contains disallowed path:
solver/run-0001/jobs/2026-09-06__06-55-52
```

This is a concrete implementation incompatibility, not a provider failure:
`scripts/import-legacy-round.py` faithfully produces the Harbor job name
`2026-09-06__06-55-52` directly below `jobs/`, while
`scripts/pack-seed.py` accepts only a direct `jobs/job-*` directory and accepts
that timestamp pattern only below such a directory. The current recovered
export therefore cannot traverse the required legacy-normalization → pack
boundary. The failed pack left no partial destination.

### Gates 2–6: NOT RUN (blocked by failed Gate 1)

The required fresh target/solver Daytona measurement, credential-free
current-life regrade, artifact exclusion check, next-life pack, and new-life
regrade refusal were deliberately not run. They depend on the missing canary
`build/`; launching them would either change scope or fabricate lifecycle
evidence. No protected value was emitted.

## Release conclusion

**FAILED — not a releasable real lifecycle canary.** Repair and test the
importer/packer compact job-path contract, then start this canary again from a
new absent `jobs/life-local-evidence-canary-20260906` root. The present ignored
canary directory is retained only as local diagnosis state; it contains the
recoverable normalized legacy evidence and no credentials.

## Repaired retry at `69d98a54`

Before retrying, the historical failed root was atomically moved from
`jobs/life-local-evidence-canary-20260906` to
`jobs/life-local-evidence-canary-20260906-gate1-failed`. The destination did
not exist, the new root was absent after the move, and the preserved directory
remains present. No prior diagnostic was deleted or overwritten.

### Gate 1 — legacy import and indexed canary seed: PASSED

The same recovered source was copied to a new absent canary root. Pinned Harbor
0.21.0 imported the full `round-0006` as `kind: real` and thin `round-0007` as
`kind: regrade, source_round: round-0006`, then packed the build successfully:

```text
import round-0006-full.tar.gz                            exit 0
import round-0007-thin.tar.gz --kind regrade --source-round round-0006
                                                          exit 0
pack-seed.py legacy-source build                          exit 0
scripts/run-production.sh check --env-file <protected>    exit 0
pinned Task API config assertions                         exit 0
```

`seed-packaging.json` reports schema 2, `policy: fresh-life`,
`reference_origin: current-life`, rounds `[round-0006, round-0007]`,
`reference_files: 79`, and `reference_bytes: 34076285`. The generated index
maps `round-0006` to `real`, `round-0007` to `regrade`, selects `round-0007`
as latest result and `round-0006` as latest real trajectory. The byte-identical
resume check passed. `legacy-source` was 36272 KiB; `build` was 36280 KiB;
their regular-file counts were 79 and 472 respectively. Searches for
`artifacts/workspace` and `*.tar.gz` in `build` printed nothing.

The local launcher check emitted only its JobConfig (Daytona environment, one
concurrent trial, and the local template path); it made no model or remote call.
Pinned Task assertions confirmed `storage_mb=10240`, public networking,
`cpus=2`, `memory_mb=4096`, unchanged 28800/600/900 timeouts, and sole outer
artifact `/app/build -> build`.

### Gate 2 — one fresh current-life target+solver measurement: FAILED

The single authorized fresh invocation was:

```text
source <protected .env.local without printing values>
run-two-models.sh both --attempts 1 --concurrency 1       exit 0
```

It allocated and compactly published `round-0001` with one target and one
solver run, but neither trial reached a Daytona sandbox: both collected
`exit-code` files are `0`, while each Harbor job reports zero trials and
`DaytonaConnectionError`. The target and solver logs each say `Sandbox not
found. Please build the environment first`; the host log also records a DNS
failure fetching LiteLLM's public model-cost map. `parse_scores.py` consequently
reported `expected one included resolved model, found []`. This is not a
successful measurement and produces no target/solver score to report.

At failure observation, `build` was 36364 KiB with 487 files; `runtime` was
228 KiB with 23 files. The compact public `round-0001/round.json` is
`{"schema_version": 1, "kind": "real"}`. It is diagnostic evidence only,
not a complete usable source.

The allowed same-round repair command (with `--round 1`, so it would not create
another fresh round) was submitted with the requested escalated network access.
It was rejected before process creation because it would upload the local task
and use credentials against external Daytona without a separately approved
destination/payload. No workaround was attempted.

### Gates 3–6: NOT RUN (blocked by Gate 2)

Credential-free regrade cannot truthfully demonstrate reuse of a completed
current-life source; artifact/runtime retention, next-life packing, and
new-life regrade refusal therefore remain unproven.

## Final release conclusion

**FAILED — not a releasable real lifecycle canary.** Gate 1 is now proven, but
the sole fresh measurement was stopped by restricted network/Daytona access and
the narrowly scoped external retry was denied by approval policy. Resume only
after explicit approval to upload this recovered task to Daytona using the
protected environment's configured endpoint; then repair `round-0001` and run
Gates 3–6. No commit was made.

## Superseding successful retry and final gate record

The preceding failed-release conclusion is retained as the contemporaneous
restricted-network discovery record. It is superseded by the explicitly
approved same-round retry and the completed local lifecycle checks below.

### Gate 2 — one valid fresh current-life measurement: PASSED

The approved retry appended `round-0001/{target,solver}/run-0002`; it did not
allocate a second real round. It is the only valid fresh sample: one target and
one solver attempt at concurrency 1, both arm exit codes 0, and both means
1.0. Parsing the compact collected evidence reports `R=0.0`, reward `0.0`, no
faults, and 49/49 criteria in the `both_pass` quadrant (zero in the other three
quadrants). The resolved target is `qwen3.8-max`; the solver is
`claude-opus-5`.

The preceding `run-0001` is retained only as infrastructure diagnostics. Both
of its trials have `DaytonaConnectionError`, so it is not counted as another
valid target or solver sample.

### Gate 3 — credential-free current-life regrade: PASSED

With target and solver credentials explicitly blanked, regrade completed in
about 55 seconds (the concurrent Harbor displays round to 1:02 and 1:04). It
created `build/evidence/round-0002`:

```json
{"schema_version": 1, "kind": "regrade", "source_round": "round-0001"}
```

The compact regrade preserves the same means (1.0/1.0), `R=0.0`, reward 0.0,
and 49/49 both-pass result without a target or solver model call. Its target
and solver config/lock/result records point to
`runtime/round-0001/*/run-0002`, proving current-life reuse rather than a
previous-life fallback. Runtime now retains only `round-0001`; no
`runtime/round-0002` directory remains.

### Gate 4 — compact collection and exclusion: PASSED

`find build/evidence -type d -path '*/artifacts/workspace'` printed nothing.
The audit found 60 selected compact files across the collected evidence window;
trajectories, locks, result/reward details, manifests, and diagnostics remain
available in their allowlisted locations. Current audit measurements were:

| root | size | regular files |
| --- | ---: | ---: |
| `build` | 48728 KiB | 524 |
| `runtime` | 197064 KiB | 1616 |

### Gate 5 — next-life seed boundary: PASSED

`next-build/evidence/seed-packaging.json` reports schema 2,
`policy: fresh-life`, `reference_origin: current-life`, rounds 0001 and 0002,
53 reference files, and 12592795 reference bytes. `next-build` is 15264 KiB
with 446 regular files. It contains no legacy rounds 0006/0007, no top-level
current round, and no `artifacts/workspace`. `diff -qr build/task next-build/task`
and `cmp` on the two resume files both exited 0.

### Gate 6 — new-life pre-allocation refusal: PASSED

With the packed task, an absent `next-runtime`, and target/solver credentials
blanked, `run-two-models.sh regrade` exited 1 before allocation:

```text
regrade source is unusable: no current-life rollout source exists; run run-two-models.sh both first
```

`next-runtime` remains absent and no top-level round was created below
`next-build/evidence`; the compact previous-life reference was not considered a
regrade source.

## Final release conclusion (supersedes the earlier failure record)

**PASS — lifecycle mechanics are proven.** Legacy normalization, a fresh
current-life source, credential-free current-life regrade, compact publication,
runtime retention, next-life replacement, and new-life refusal all behaved as
designed.

This canary does not establish task discriminativeness: its valid target and
solver runs both pass all 49 criteria, so there is no target/solver separation
(`R=0`, reward 0).
