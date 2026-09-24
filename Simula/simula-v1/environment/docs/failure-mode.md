# Failure modes for task design

Phase 04 reads this before designing a candidate and pastes it, in full, into
every candidate subagent's assignment. It says which agent failures a task is
allowed to cause. It does not change `plan.difficulty` and it does not add an
axis to `complexity_delta`.

The modes come from Zhao et al., *Failure as a Process: An Anatomy of CLI
Coding Agent Trajectories* (arXiv:2607.09510). On Terminal-Bench, 1,184 failed
trajectories, the decisive error lands at a median of step 7, while the
trajectory runs to a median of 27. The first visible sign of failure comes
about 10 steps after that error. The opening situation and the starting
environment fix the agent's belief before a verifier ever runs.

## What a hard task may cause

These are failures of belief or execution while the needed information is
already in the environment. A hard or ultra candidate should be able to induce
one of them. An easy candidate should not.

- **False premise** (30.7%). The agent acts on an unverified assumption about
  the task or the environment. This is the largest mode. The first conspicuous
  symptom in the starting state must not be, and must not look like, the root
  cause. A message such as `sudo: not found` that is really a missing binary
  will be read as a permissions problem and lock the trajectory.
- **False shortcut.** A local repair is consistent, survives a shallow check,
  and leaves a coupled constraint broken. The counter-evidence must stay hidden
  until that shallow check passes. Placing it in the first command output lets
  the agent recover immediately, which is the easy version of this task.
- **Capability limitation** (8.8%). The strategy is reasonable and the agent
  still fails to carry it out. Prefer this over hiding knowledge. The repair
  should be hard to execute because of an interaction in the pinned repository,
  not because a fact was withheld.
- **Output misreading** (4.4%) and **ignored signal** (4.1%). Command output or
  a later observation contradicts the agent's assumption. Use these only when
  the real signal is genuinely easy to misread. Do not plant a misleading
  string that has one intended reading.

## What a task must not cause

These failures blame the task. A candidate that depends on one of them goes
back to the subagent.

- **Environment blocker** (8.8%). The correct repair cannot be carried out
  because a file, permission, service, or dependency is missing or unreachable.
  The correct path must be completable inside the sealed environment.
- **Knowledge gap** (24.0%). The agent lacks domain, tool, or API knowledge that
  the pinned repository does not contain. A stronger model skips this, so it is
  not difficulty. Do not raise the band by hiding a command, a formula, or a
  term that the repo's code, tests, and docs do not teach.
- **Specification neglect** (14.9%). The agent ignores or forgets a requirement
  the instruction stated. Every extra untested sentence raises this. State only
  the broken outcome and the end state the verifier checks. A requirement the
  verifier does not enforce is a defect, not difficulty.
- **Premature action** (3.7%). The agent acts before it can verify anything.
  Give the starting state something that can be observed. Do not make the first
  step a blind edit.

## Verifier

82% of failed trajectories keep running after the error is past recovery, and
26% fabricate a successful result, usually at the moment recovery becomes
impossible. Repairing the wrong cause consumes 39% of wasted steps.

Check an invariant that holds only after the real repair. A file that exists,
a command that exits zero, or a format that parses is not enough, because a
locked agent will produce exactly that. The fabricated artifact and the
artifact from repairing the wrong cause must both fail.
