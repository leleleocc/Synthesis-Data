# Task difficulty

This is the shared difficulty definition for phases 03 and 04. Read it before
planning or designing a candidate. Phase 04 must include this document in each
candidate subagent's context together with `plan.difficulty`.

Phase 07 uses this definition for advisory feedback only. It does not reject
a task for being too easy, requiring less expertise or time than expected, or
missing an exact difficulty band. Difficulty observations must not trigger
added complexity or relabeling there. Actual verifier and instruction
alignment failures still require repair under their own review criteria.

Difficulty is the reasoning needed to understand the system and achieve the
required outcome while preserving its relevant invariants. A task can expose
real logs, failing commands, reproduction conditions, and symptoms at every
difficulty level. Those clues do not supply the diagnosis or the repair.

An obscure fact, withheld evidence, a larger repository, more output files,
longer builds, or more repetitive edits does not by itself make a task hard.
Keep the existing difficulty enum, time estimates, and resource limits.

## Sources of difficulty

Choose interactions that the pinned repository can actually exhibit; these
are design options, not a checklist every candidate must satisfy.

- Causal chains: an upstream state or assumption causes a downstream symptom;
  fixing only the symptom leaves the cause active or moves the failure.
- Competing constraints: correctness must coexist with compatibility,
  performance, durability, or a bounded resource budget. A locally reasonable
  change can violate another required property.
- Component boundaries: interfaces, configuration, data representations,
  ownership, or lifecycles disagree across components. Understanding each
  component separately is insufficient to explain the joint behavior.
- Time and state: retries, concurrency, restart, recovery, or failover expose
  failures absent from the normal path. The repair must preserve an invariant
  across the relevant transitions.
- Causal diagnosis: available evidence admits multiple plausible explanations.
  The agent must distinguish the initiating fault from secondary failures and
  choose observations that resolve the ambiguity.

## Difficulty bands

- `easy`: a localized cause and a short reasoning chain. Both constraints
  remain observable; one can be a straightforward bound on the main repair.
  The instruction may identify the affected file.
- `medium`: diagnosis within a subsystem requires reading code or docs and
  handling a meaningful interaction or edge transition. The instruction may
  identify the subsystem; the agent determines the cause and exact change.
- `hard`: the agent reconstructs a causal chain, reasons across a component
  boundary, or resolves a substantive constraint conflict. Both coupled
  constraints are load-bearing: a plausible local fix can leave a secondary
  failure or break another invariant. The instruction provides observable
  evidence; the agent discovers the repair locus and validates the joint
  outcome.
- `ultra`: interacting hard parts share state. A naive fix to one changes the
  conditions of the other, so the agent must reason about their feedback and
  preserve a joint invariant across relevant operations or transitions.
  Two independent hard edits or a long checklist do not meet this band.

## Phase 03: establish feasibility, then plan

Inspect the relevant code, tests, configuration, and run paths at the pinned
commit before committing to a slot. Establish a realizable starting state,
the source-supported interaction, observable success conditions, and a
credible way to satisfy them within the sealed environment and task budget.
Reading repository code is part of planning; do not build candidate images
or produce a solution in this phase.

Use `complexity_delta` to describe both constraints and how they interact,
including what a plausible partial fix would leave broken. Keep the stated
band in `plan.difficulty`; do not add new handoff fields or difficulty labels.
For example, "recover replica service while keeping its durable offset
consistent across restart; reconnecting alone can advertise lost writes"
expresses an interaction. "Repair replication and write a report" does not.

## Phase 04: realize the planned difficulty

Implement the starting state and the interaction in the candidate environment.
Express both observable outcomes in the instruction so neither is optional.
Confirm that the coupled behavior is present in the actual design and that
the planned reasoning, rather than accidental setup friction, is necessary.

Include real symptom logs, failing commands, reproduction conditions, and
relevant operating constraints when they help define the problem. A log may
naturally contain a path or error string; that is not a diagnosis. For hard
and ultra, do not identify a file as the known defect site, reveal a planted
fault, or prescribe a repair. Explain enough to make the task actionable
without telling the solver which hypothesis is correct.
