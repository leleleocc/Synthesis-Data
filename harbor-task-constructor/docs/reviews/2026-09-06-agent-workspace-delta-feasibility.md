# Agent-workspace delta feasibility boundary

## Decision

**No — reject code-delta capture from this implementation.** Harbor 0.21.0
does expose Agent-start and Agent-end *notifications*, but not a runner-level
filesystem observation hook. The current canary's workspace artifact is a
task-declared, post-Agent collection of one final tree. It supplies neither a
pre-Agent tree nor file-level change information. Under the requested
genericity gate, capture would therefore require task-specific artifact or
startup adapters; it is not a generic runner feature to add to this work.

This decision is about the pinned Harbor 0.21.0 interface and the actual
canary layout, not about whether a future Harbor-core design could introduce a
new snapshot API.

## Evidence inspected

- The pinned interpreter at
  `/Users/likuanye/.local/share/uv/tools/harbor/bin/python3` reports Harbor
  `0.21.0`; source references below are from its installed `harbor/` package.
- The canary's task declares `[[artifacts]] source = "/workspace"` in
  `jobs/life-local-evidence-canary-20260906/build/task/task.toml:37-38`.
  Its retained real-trial manifests, for example
  `jobs/life-local-evidence-canary-20260906/legacy-source/evidence/round-0006/target/run-0001/jobs/2026-09-06__06-55-52/task__w2fJZUA/artifacts/manifest.json`,
  record one successful `/workspace` directory entry at
  `artifacts/workspace`. The corresponding trial `config.json` and `lock.json`
  identify the local task, Claude Code agent, and Daytona environment; they
  contain no baseline workspace path or snapshot digest.
- The fresh canary's failed first attempt confirms the same collection shape:
  `jobs/life-local-evidence-canary-20260906/runtime/round-0001/target/run-0001/jobs/2026-09-07__00-00-04/task__JkjXVcL/`
  has `config.json`, `lock.json`, and `artifacts/manifest.json`; the latter
  attempts `/logs/artifacts` and `/workspace`, both with `status: "failed"`.
  That manifest is a record of final collection attempts, not evidence of an
  initial filesystem state. No pre-Agent baseline is inferred from it.
- The canary release record says compact publication intentionally excludes
  `artifacts/workspace` (`docs/reviews/2026-09-06-life-local-evidence-canary.md:214-220`).
  Thus even a retained final workspace is not a public compact evidence
  contract.

## Genericity gate

| Question | Answer | Direct evidence |
| --- | --- | --- |
| 1. Can one hook observe the initialized workspace before every Agent starts? | **No.** | `harbor/trial/trial.py:404-415` starts the environment, health-checks it, uploads skills, and runs Agent setup before `_run_agent_phase`. That method emits `AGENT_START` at `:445-456`, immediately before `agent.run` at `:458-488`. `Job.on_agent_started` merely registers a `HookCallback` (`harbor/job.py:183-185`); `TrialHookEvent` exposes only event, task name, config, result, lock, and timestamp (`harbor/trial/hooks.py:29-60`)—not the live `Trial`, `BaseEnvironment`, or an operation on `/workspace`. The callback cannot read the initialized remote workspace. |
| 2. Can the same hook observe the final workspace without changing task startup? | **No.** | `_run_agent_phase` emits `AGENT_END` in its `finally` block (`harbor/trial/trial.py:490-495`), and `Job.on_agent_ended` has the same payload restriction (`harbor/job.py:187-189`). In a single-step trial, Harbor then invokes its own artifact collection directly after Agent execution (`harbor/trial/single_step.py:41-47`); that is not a hook that exposes the live environment. `ArtifactHandler` downloads only the merged, declared artifact entries (`harbor/trial/artifact_handler.py:173-208, 325-377`). The canary gets `/workspace` only because this individual task declares it, so using that path as a general seam changes artifact/startup configuration task by task. |
| 3. Can a filesystem delta preserve adds, edits, deletes, modes, and non-Git trees? | **No, not as a Harbor-wide guarantee from this interface.** | A final-tree artifact cannot represent a deletion without an independent initial tree. Harbor's generic `BaseEnvironment.download_dir` contract promises only a directory download and overwrite (`harbor/environments/base.py:946-955`), not entries, modes, or metadata. Daytona's POSIX implementation transports a tarball (`harbor/environments/daytona/environment.py:1862-1896`), but its Windows branch recursively makes local directories and downloads files (`:1782-1805`), with no mode, symlink, or deletion metadata. The existing artifact manifest contains only `source`, `destination`, `type`, `status`, and `service` (`harbor/models/trial/artifact_manifest.py:5-17`), not a file manifest or a before/after relation. Git status cannot repair that gap for non-Git trees. |

## Lifecycle boundary

```text
environment start -> health check -> Agent setup -> AGENT_START notification
                                                -> agent.run
                                                -> AGENT_END notification
                                                -> declared final artifact collection
                                                -> verifier
```

The two notifications bracket `agent.run`, but their public callback context
does not carry the live environment needed to snapshot `/workspace`.
`/workspace` collection is instead a configured deliverable path, as the
canary demonstrates. It is one final tree and cannot be retroactively turned
into a delta baseline.

## Consequence

Because all three answers are not an unqualified yes, the requested
runner-level seam does not exist. Do not implement code-delta capture in this
life-local-evidence work. Any follow-up must begin separately and decide
whether to introduce a Harbor-core snapshot/delta API with an explicit
cross-provider metadata contract; absent that, it would rely on per-task
adapters and is rejected here.
