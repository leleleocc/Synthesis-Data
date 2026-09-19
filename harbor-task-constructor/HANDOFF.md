# Project handoff

This is the short operational handoff for `harbor-task-constructor`. It separates
what is implemented and verified from what was only investigated. Read this file
before starting another construction batch.

## Start here

- Remote: `wisdom-knowledge/harbor-task-constructor` (private); its default branch
  is `main`.
- Active development/handoff branch: `codex/life-local-evidence`.
- Implementation baseline at handoff: `de705e22`.
- The local `main` branch is older. Do not assume this work has been integrated
  into `main`.
- Do not claim that four tasks have passed the latest design. The previous
  four-task batch used `c3a63180`; only the corrective canary used `de705e22`.
- Before another production batch, fix the regrade lineage P1 described below.

Then read, in order:

1. [`docs/contract.md`](docs/contract.md) for the host/runtime evidence contract.
2. [`template/instruction.md`](template/instruction.md) and
   [`template/environment/method/sop.md`](template/environment/method/sop.md) for
   the Agent-facing workflow.
3. [`docs/reviews/2026-09-07-round4-life-local-four-task-run.md`](docs/reviews/2026-09-07-round4-life-local-four-task-run.md)
   for the latest real-run evidence and exact task-level outcomes.
4. [`docs/superpowers/specs/2026-09-06-life-local-evidence-design.md`](docs/superpowers/specs/2026-09-06-life-local-evidence-design.md)
   and [`docs/superpowers/plans/2026-09-06-life-local-evidence.md`](docs/superpowers/plans/2026-09-06-life-local-evidence.md)
   for the accepted lifecycle design and implementation history.

## What the repository does

The repository is a standalone Harbor outer task. A construction Agent receives
one real seed task, iterates on its verifier and related task material, measures a
target model and a solver model, and returns a task only when the programmatic
score shows a useful gap.

The important boundaries are:

- `template/` is the runnable outer Harbor task.
- `template/environment/method/` contains the construction runner, parser, SOP,
  and minimal Harbor reference.
- `scripts/run-production.sh` performs the host-side check/install/run gates.
- `scripts/pack-seed.py` creates the compact next-life seed.
- `scripts/import-legacy-round.py` is the one-time compatibility path for trusted
  legacy evidence archives.
- `tests/` protects host tooling, runner/parser behavior, evidence retention, and
  the outer verifier.

Each life starts with one seed representation, either
`environment/seed/build/` or `environment/seed/build.tar.gz`. The runtime operates
on `/app/build/`; only the task, resume note, and allowlisted compact evidence are
eligible for the next life. A new life always starts its first measurement fresh.

## Design principles

The constructor is an evidence-driven verifier optimization loop, not an Agent
that solves the seed task. Its design follows six rules:

1. **Verifier first.** Preserve the task's domain and core contract. Prefer a
   smaller change to `tests/**`, with the matching `solution/**` adjustment when
   required. Change instruction, environment, or task configuration only when a
   runnable counterexample proves a contract or wiring defect.
2. **Light loop before heavy loop.** A fresh target/solver run creates expensive
   rollout evidence. When only tests or solution change, regrade those current-life
   workspaces before paying for another rollout. Regrade never silently falls back
   to a fresh model run.
3. **Freeze the measured input.** After the first valid fresh measurement—or from
   life start when a previous-life capsule exists—the rollout input stays frozen.
   A score that is low, reversed, or saturated is evidence for verifier attribution,
   not permission to rewrite the task.
4. **Move forward and converge.** Each iteration names one score-changing
   hypothesis, tests it, makes one minimal modification, closes the measurement
   loop, and records the result. Historical trajectories answer a named current
   question; they are not an open-ended source of redesign ideas.
5. **Carry knowledge, not workspaces.** Full jobs and workspaces are life-local.
   The next life receives the task, compact score details, selected trajectories,
   and a decision-rich `resume.md`. This preserves useful attribution while
   preventing artifact and attention growth.
6. **Separate task work from batch learning.** The construction Agent converges
   one task autonomously. The host reviews a completed batch, finds repeated
   failure modes, and only then promotes cross-task lessons into the SOP or tools.

The accepted design also makes current SOP workflow authoritative over historical
`resume.md` advice. The explicit precedence sentence and the tighter active-run
attention boundary are listed below as accepted follow-up guidance because they
are not yet present in the production SOP.

## How one construction life runs

There are two nested loops: the Agent closes one task inside a life, while the host
decides what compact evidence should enter the next life.

```text
Host
  source build -> pack-seed -> outer Harbor instance
                              |
Constructor Agent life        v
  recover resume/current task
    -> prove nop=0 and oracle=1
    -> fresh target + solver measurement
    -> parse scores and attribute one verifier hypothesis
    -> minimally edit tests (and solution when needed)
    -> prove nop/oracle again
    -> regrade current-life rollouts
    -> deliver on clean gates, otherwise repeat one hypothesis
                              |
Host                          v
  collect task + compact evidence + resume
    -> batch review -> pack the next life or export the passing task
```

The decision point after every parsed round is:

- incomplete arm with unchanged task: repair only that arm when possible;
- tests/solution changed and compatible current-life rollout exists: regrade;
- no current-life source or measured rollout input changed for a proven defect:
  fresh target and solver run;
- clean final-task-matching round with `target_mean < 0.7` and `R > 0.2`:
  deliver;
- no defensible separating change remains: record an honest `incomplete` resume
  instead of returning a falsely successful task.

Inside the Agent, `resume -> mechanical gate -> measurement -> attribution ->
minimal change -> measurement` repeats until delivery. Across lives, the host uses
`pack-seed.py` to reset runtime/regrade sources while retaining compact conclusions;
the first formal measurement of every new life is fresh.

## Verified behavior

The latest real jobs establish the following:

- `run-two-models.sh both` defaults to two target and two solver attempts, with
  both arms concurrent.
- Tests/solution-only changes can reuse current-life rollouts through `regrade`;
  regrade job configs contain source jobs and no new Agent/model configuration.
- Corrected compact publication retains result details, trajectories, and resume
  notes without retaining task workspaces.
- The pre-fresh gate in `de705e22` kept the canary's rollout input frozen and
  allowed an honest `incomplete` result when no separating axis survived.
- The outer four-task batch reached a terminal state without constructor
  exceptions. One task (`387bef85`) produced a valid final separator at target
  `0.625`, solver `1.0`, `R=0.6`; the other tasks supplied useful failure evidence.

The complete numbers, timelines, and trajectory findings are in the latest
four-task review linked above.

## Blocking correctness issue

The production parser currently evaluates a regrade trial from the regrade
result's exception state alone. Harbor regrades every recorded source trial. If
the source rollout failed at the provider/environment layer but still has an
archived workspace, its successful replay can therefore be counted as a new
completed zero.

This happened in the real `387bef85` evidence:

- current parser: target `0.67705`, solver `0.5`, `R=-0.261502`;
- correct source-eligibility treatment: target `0.67705`, solver `1.0`,
  `R=0.476996`.

The fix should stay parser-local. Resolve each regrade trial against its compact
source trial, preserve source rollout eligibility, and fail closed on missing or
inconsistent lineage. A successful regrade may repair a verifier-only
`RewardFileNotFoundError`; it must not repair provider, environment, cancellation,
or unscored timeout failures. Scored Agent timeouts retain the existing policy.

An isolated prototype and regression exercise existed only under `/private/tmp`.
It was deliberately not copied into this repository and is not production code.
Implement the behavior test-first in `tests/test_parse_scores.py` and
`template/environment/method/parse_scores.py`.

Minimum parser coverage:

1. the real `387bef85` regression shape;
2. a source-state table covering completed, scored timeout, provider/environment/
   cancelled, unscored timeout, and verifier-only missing reward;
3. malformed lineage covering missing marker/path/id, cross-arm references, and
   source-round or digest mismatch;
4. an ordinary fresh-round regression proving existing eligibility is unchanged.

## Accepted follow-up guidance, not yet implemented

After the parser fix, make only these small Agent-facing changes:

1. While a formal run is active, permit monitoring and infrastructure attribution
   only; remove the scratch-probe exception.
2. State that the current SOP governs workflow and overrides conflicting advice in
   historical `resume.md`; history remains evidence and hypothesis input.
3. In the both-pass branch, do not add or expand tests unless current arm evidence
   predicts useful separation or demonstrates a verifier false positive/negative.
4. Reserve `evidence/round-*` for the runner. Put disposable construction analysis
   under `evidence/analysis/`, which is not inherited by the next life.

These are prose changes. Pressure-test them in real Agent trajectories; do not add
source-text tests merely to assert wording.

Keep regrade latency separate from correctness. The observed roughly 22-minute
regrade was caused by a full 600-second Agent judge and serial replay within each
arm. Do not mix a concurrency or programmatic-only optimization into the lineage
fix without a separate decision and validation.

## Continuation runbook

1. Implement the parser-lineage fix and its focused tests.
2. Apply the four concise SOP changes above and review the resulting instruction
   as an Agent-facing document.
3. Run the complete repository validation listed below.
4. Build four fresh instances from the latest completed task artifacts with
   `scripts/pack-seed.py`. Use exactly one seed representation per instance.
5. Confirm all four instances have the same final template Git digest before
   dispatch.
6. Launch one outer attempt per task with four-way outer concurrency. Do not add
   retries; the constructor owns its inner sampling loop.
7. Inspect live sandbox trajectories for adherence to the fresh-measurement gate,
   regrade-before-rerun behavior, active-run attention boundary, and compact
   evidence paths.
8. After all tasks are terminal, update the latest review with results and
   evidence-backed SOP candidates.

Production setup and launcher commands are intentionally kept in
[`README.md`](README.md) rather than duplicated here. The environment file is
trusted shell input and must remain outside Git.

## Validation

Use Python 3.11+ with Harbor 0.21.0 importable:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
bash -n template/environment/method/run-two-models.sh
bash -n scripts/run-production.sh
bash -n template/tests/test.sh
git diff --check
```

Before a production launch, also run the `check` gate from `README.md` with the
real external environment file.

## Local-only state and secrets

The following are intentionally ignored and are not part of the Git handoff:

- `.env.local` and every credential or API key;
- `jobs/`, `instances-*`, and generated exports;
- full Harbor/Daytona workspaces and downloaded build artifacts;
- seed archives staged under `/private/tmp`;
- temporary parser prototypes.

The task body is the important portable state. For cross-life reuse, retain the
compact trajectory, result detail, score metadata, and resume material produced
by `pack-seed.py`; do not move a complete prior workspace into the next life.
The latest local job artifacts may be regenerated or transferred separately when
real-run audit access is required.

## Handoff completion criteria

The next authoritative milestone is complete only when:

- the regrade lineage P1 and regression tests are merged;
- the full local validation passes;
- four instances use the same final template digest;
- all four latest-template jobs reach a terminal state; and
- the batch review records score sources, regrade usage, artifact sizes, Agent
  behavior, and any remaining correctness or efficiency defects.
