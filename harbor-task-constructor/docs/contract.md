# Harbor Task Constructor Contract

## Mission

The outer agent constructs the Harbor task at `/app/build/task/`; it does not solve
the seed task's current instruction. It preserves the domain and core goal while it
may change the instruction, task configuration, solution, tests, workspace,
dependencies, fixtures, services, and starting state.

The delivered task must be mechanically valid: its untouched starting state fails,
its shipped solution passes, and its verifier produces stable programmatic scores.

The outer instruction is a one-time bootstrap and is not mounted as a rereadable file
inside the Agent environment. It states the role and points to `sop.md`; the SOP owns
the persistent construction, evidence, recovery, and completion rules.

## Life-local evidence roots

The input and output share one shape:

```text
build/
├── task/
└── evidence/
    └── resume.md
```

`/app/build/task/` is the only task worktree. `/app/build/evidence/` is the collected,
compact history root; `/app/runtime/harbor-evidence/` is the uncollected, life-local
root for full nested Harbor workspaces. A regrade reads a source only from the runtime
root, so each new life begins without a reusable workspace and establishes a fresh
real target/solver source before it can regrade.

`run-two-models.sh` owns both roots. Every completed nested invocation publishes its
allowlisted compact evidence under `/app/build/evidence/` before parsing; a completed
real invocation remains in the runtime root only while it is the current-life regrade
source. A top-level runner invocation owns the roots through allocation, publication,
and retention; `both` remains the concurrent target/solver operation.

The outer artifact collects only `/app/build`. It therefore returns the final task,
resume notes, inherited compact reference, committed compact current-life rounds, and
any published partial diagnostics, never nested workspaces, session caches,
dependency trees, or build caches.

## Seed capsule

A resumed seed replaces the complete `build/` representation; it never overlays
trees. `pack-seed.py` allowlists the complete current `task/`, `evidence/resume.md`,
the packaging report, and exactly one compact previous-life generation. When the
source life has committed compact top-level rounds, they replace any inherited
reference; when it has zero committed rounds, the existing compact reference carries
forward unchanged. The packer never combines generations and does not synthesize or
rewrite scores.

Current-life compact evidence follows the parser/current-round path. By contrast,
`evidence/previous-life/index.md` maps retained round names, kinds, score and real
trajectory references to exact compact paths for prior-life attribution only; it is
not a regrade source or current-life measurement.

The host-side seed transport has two mutually exclusive representations:
`environment/seed/build/` for an editable template or
`environment/seed/build.tar.gz` for a batch instance. Image construction rejects a
seed containing both or neither, then materializes the selected representation at
`/app/build/`. Compression is not visible to the Agent, runner, verifier, regrade, or
collected artifact. Archive creation preserves selected content, symlinks, empty
directories, and executable modes; canonical host artifacts are never modified.

`resume.md` keeps exactly these headings:

```text
# 已尝试方向
# 关键结果
# 已排除假设
# 当前 task 状态
# 下一步建议
```

It is cumulative inferred guidance. Raw Harbor jobs remain authoritative for task,
model, run, exception, verifier-result, and score attribution. The handoff never
enters reward calculation.

## Construction loop

Every life reads the handoff, then the compact previous-life index when supplied, and
then the current task. Historical scores are conclusions; indexed score details and
trajectories are read only for a concrete attribution question. The SOP owns the
diagnostic order and treats current-life fresh evidence as primary after it exists.

The first measurement in every life is fresh. A compatible current-life real source
permits regrade for a top-level `tests/**` or synchronized `solution/**` change after
nop/oracle; another rollout-input change requires fresh measurement. If a current-life
round is incomplete and task equality is established, only its missing or failed arm
may be appended. Regrade never falls back to collected or previous-life evidence.

After each task modification, mechanical validation, or formal measurement, the agent
updates `resume.md` incrementally. Other process artifacts may use arbitrary
subdirectories below `evidence/`.

## Regrade-ready task boundary

Before its first real measurement, the construction Agent makes the delivered task
single-step, gives it an explicit separate verifier that can grade restored
`/workspace`, and declares the complete `/workspace` as an artifact. In separate
mode, `tests/` defines that verifier environment and bakes `/tests/test.sh` into its
image; `tests/Dockerfile` is the normal supported form. The task and any verifier
environment or phase override remain public. The runner validates this shape but
never rewrites an incoming task.

## Rollout and regrade evidence

A runtime real-model round carries `rollout.lock`, including its Harbor task and
rollout-input digests. Its compact publication retains score details, results, locks,
logs, manifests, and real-run trajectories needed for parser and attribution, but no
workspace. Regrade provenance remains Harbor's `lock.json.source_trial` chain.
Regrade failure never falls back to model execution or older scores.

## Scoring-quality boundary

Task criteria are presumed valid. Implicitness, engineering preference, high weight,
low pass rate, or contribution to model separation is not a scoring defect by itself,
and criterion provenance does not determine criterion weight.

A scoring change requires a concrete delivery-state reproduction failure, a direct
contract contradiction, a runnable behaviorally correct counterexample that exposes
reference-implementation lock-in, or verifier instability or distortion. A confirmed
defect may not be restored to maintain R; separation must be rebuilt through genuine
task difficulty and fresh evidence.

## Evidence and scoring

For each arm, scoring uses only the latest run inside the numerically latest round.
Each latest arm run must contain at least one valid trial with one attributable
`kind: programmatic` Reward Kit score. Agent-judge output is diagnostic and excluded
from R; direct LLM judging is unsupported.

A normally completed trial is valid when the programmatic score is readable.
`AgentTimeoutError` is also valid when verification produced a readable
programmatic score. Other exceptions and timeouts without such a score are invalid.

```text
R = (solver_mean - target_mean) / target_mean
```

The joint work target is `target_mean < 0.7` and `R > 0.2`. Both guide construction;
neither is a binary outer-verifier gate. The outer verifier retains continuous
reward for readable below-target rounds and returns zero with an explicit fault when
the latest round is unreadable.

If `target_mean = 0` and `solver_mean > 0`, R is infinite and clears the R target. If
both means are zero, R is zero. A missing mean on either arm makes the round
unreadable.

Among criteria contributing to the programmatic score, omitted weights count as
`1.0` and `max_weight / min_weight <= 10`. This comparison excludes group,
dimension-aggregation, and agent-judge weights.

## Immutable runtime boundary

The outer task and delivered task explicitly keep
`[environment].network_mode = "public"`. Any independent verifier environment or
agent/verifier phase override must also remain public. Other environment content may
be redesigned.

The fixed method surface is exactly `reference/`, `run-two-models.sh`,
`parse_scores.py`, and `sop.md`. Runner and parser `--help` output owns command
syntax, credentials, evidence layout, validity details, and score-report fields.

The parser, runner, outer continuous-reward formula, trial-validity rules, and outer
verifier are not agent-editable scoring targets. Construction evidence measures the
current task but is not fresh validation evidence for a broader failure-mode claim.
