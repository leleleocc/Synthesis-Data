# Regrade-Backed Test Debugging Design

> **Superseded:** Its cross-life rollout retention is superseded by the
> [life-local evidence design](2026-09-06-life-local-evidence-design.md) and its
> [implementation plan](../plans/2026-09-06-life-local-evidence.md). Harbor regrade
> remains supported inside one life; only cross-life workspace/rollout retention changed.

## Status and goal

Implemented direction. Let the constructor change a delivered task's verifier surface — `tests/**` and
`solution/**` — and obtain new official target and solver scores without another model rollout. Changes to
rollout inputs still require real model runs.

The design targets Harbor 0.21.0, pinned by the constructor image. A regrade is valid only when it verifies
the latest real rollout's recorded workspaces against the current verifier, with an inspectable source chain
and no agent/model phase.

## Verified Harbor baseline

`harbor job regrade SOURCE -p TASK --env daytona` reruns verification for every recorded source trial. It
builds the verifier from the supplied current task's `tests/`, copies only the source `agent/` and `artifacts/`,
and skips the agent phase. It requires a single-step task, `environment_mode = "separate"`, and verifier inputs
covered by each source trial's artifact manifest. The source job is unchanged.

In the inspected 2026-09-04 batch, all eight delivered tasks used shared verification and none of 121 nested
trial manifests contained `/workspace`. Those rounds are ineligible. This feature is forward-only.

## Public interface

Extend the existing runner with one explicit mode:

```text
run-two-models.sh regrade [--concurrency N]
```

`both`, `target`, and `solver` remain real-model modes. `regrade` always grades both arms in a fresh round,
rejects `--round` and `--attempts`, and never falls back to a costly model run.

The runner remains one deep module. Its small interface owns readiness checks, rollout identity, source
selection, Harbor invocation, credential isolation, allocation, and failure evidence.

## Seed task normalization

The incoming task is `/app/build/task/task.toml`, not the outer `template/task.toml`. Before its first
measurement, the construction Agent must make that task regrade-ready:

```toml
[verifier]
environment_mode = "separate"
# retain the task's timeout, network, and environment settings

[[artifacts]]
source = "/workspace"
```

The Agent must also ensure that:

- the task is single-step;
- tests work in a separate verifier against the restored `/workspace`;
- in separate mode, `tests/` defines the verifier environment and bakes
  `/tests/test.sh` into that image (`tests/Dockerfile` is the normal supported form);
- public network behavior is retained;
- no artifact declaration collides with `/workspace`; and
- nop and oracle pass after the conversion.

This is a task-design change, so the first score after conversion must use a real rollout. The reference task
shows the supported shape. The host must not patch arbitrary seed TOML: it cannot infer verifier or artifact
semantics safely. On resume, the Agent leaves a ready task unchanged; otherwise it converts it and performs a
new real rollout.

The runner hard-refuses every real-model mode until this contract holds, including
Harbor's separate-verifier environment-definition requirement, avoiding an
hour-long unusable run.

## Rollout identity

Only a real-model round contains `rollout.lock`:

```json
{
  "schema_version": 2,
  "task_digest": "sha256:...",
  "rollout_input_digest": "sha256:..."
}
```

The marker is written after readiness preflight and round allocation, before model launch. Regrade rounds add
no custom metadata. Harbor trial `lock.json`, especially `lock.json.source_trial`, is authoritative for task
identity, source provenance, agent configuration, and model identity.

`task_digest` is the complete packaged Harbor task identity recorded for source provenance.
`rollout_input_digest` covers every publishable input outside top-level `tests/**` and `solution/**`, including
`.gitignore`; relative path, contents, and executable mode participate. Tests and solution may change together
because neither changes the workspace produced by an existing target or solver rollout. Changes to
`task.toml`, `instruction.md`, README, `environment/**`, steps, or any other rollout input require a new real
rollout.

## Source selection and eligibility

The source is the numerically latest round containing `rollout.lock`. Regrade never uses another regrade,
falls back to an older rollout, or synthesizes missing evidence. Within the source round it uses each arm's
numerically latest run and requires exactly one Harbor source-job directory in that run.

All checks finish before allocating a regrade round. Regrade is allowed only when:

- the current task is single-step, uses a separate verifier whose `tests/` build
  context defines its environment, and collects `/workspace`;
- current and source task names match;
- the current rollout-input digest equals `rollout.lock.rollout_input_digest`;
- each source arm's Harbor command exited;
- each arm has at least one trial with readable `result.json` and a complete
  `/workspace` artifact at the expected host path; and
- each eligible source trial's task digest equals `rollout.lock.task_digest`.

An old programmatic score is not required: fixing a broken test is a core use case. Provider or environment
failures may coexist as excluded trials if each arm still has one regradable workspace. An unusable latest
rollout or arm run is an error. A single-arm `--round` repair may append only to a rollout whose lock matches
the current complete task; otherwise the caller must make a new real rollout.

## Execution and scoring

For `both`, `target`, or `solver`, the runner validates readiness and performs the existing real model flow.
Full `/workspace` artifacts make those trials reusable. The existing append-only
`round-NNNN/{target,solver}/run-NNNN/` evidence layout is preserved.

For a verifier-loop iteration, the Agent:

1. changes `tests/**` and synchronizes `solution/**` as needed;
2. reruns nop and oracle checks against that pair;
3. invokes `run-two-models.sh regrade`;
4. lets the runner preflight both source arms, then allocate a new round; and
5. reads that round with the existing score parser.

The runner calls `harbor job regrade` once per source arm, using the current task and Daytona verifier
environment. Regrade children receive Daytona and judge credentials only; target/solver credentials and
endpoints are removed. Each arm keeps the normal `jobs`, `harbor.log`, and `exit-code` evidence.

A successful regrade round is the official latest-round score. Repeated verifier-loop edits keep using the
latest real rollout as source; a later rollout-input edit requires a new rollout. Do not modify the parser or
outer verifier unless a genuine Harbor fixture first reproduces an incompatibility and a focused failing test
captures it.

## Failure behavior

Preflight failure returns nonzero without allocating a round or invoking Harbor, and names the failed
condition. Once execution begins, evidence is append-only. If one arm fails, available jobs, logs, and exit
codes remain; neither runner nor parser falls back. An incomplete latest regrade is not deliverable.

## Verification

Existing fake-Harbor tests cover arguments, readiness, preflight-before-allocation, source selection,
rollout-input refusal, solution eligibility, credential scrubbing, concurrency, partial failure, numbering,
and cleanup. Reference tests cover the single-step, separate-verifier, `/workspace` contract.

Mocks are not completion evidence. Implementation must also record raw paths and results for:

1. a low-cost real Harbor 0.21 fixture that completes a source trial, changes only a
   defective test, regrades it, proves the result changes, confirms current and
   `source_trial` locks, and confirms there was no agent phase; and
2. one real nested Daytona target/solver canary that performs a rollout, a verifier-loop
   edit, and a two-arm regrade accepted by the existing parser with no second model
   call.

No permanent network-dependent integration test is added. If the real fixture reveals an incompatibility,
first add the smallest deterministic regression test, then change only the affected module.

## Implementation scope

- `template/environment/method/run-two-models.sh`
- `template/environment/method/sop.md`
- `template/environment/method/reference/minimal-harbor-task/task.toml`
- `template/environment/method/reference/minimal-harbor-task/tests/Dockerfile`
- `docs/contract.md`
- existing runner, reference-task, and template-shape tests

`template/instruction.md`, `parse_scores.py`, the outer verifier, new public helpers,
and new persistent integration suites are outside the planned scope.

## Non-goals

No automatic rollout/regrade decision, automatic fallback, multi-step support,
single-arm regrade, regrade chain, legacy migration, general Daytona/API recovery,
artifact exclusions, or change to R, reward semantics, model identity, latest-round
selection, or trial-validity rules.
