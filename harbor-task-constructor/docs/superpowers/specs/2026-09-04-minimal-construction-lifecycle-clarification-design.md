# Minimal Construction Lifecycle Clarification Design

## Status

Approved for implementation planning. This design is the reduced successor to the
discarded parser-gate proposal. It keeps the established six-step lifecycle and changes
only the instructions that govern nested-run waiting, next-round admission, and final
handoff.

## Goal

Reduce clean-but-incomplete construction exits without adding a parser mode, runner
state model, new reference document, or new production component.

## Evidence boundary

The 0903 batch had 27 job directories and 23 result files. Ten results ended in API
errors, three in Daytona errors, and one in exit 137; SOP wording cannot repair those
failures. Of nine results marked completed, at least four lacked a readable final
two-arm round. Two of those involved corrupted tool output, one handed off while a
round was in flight, and one handed an unknown round state back to a human.

This change targets only the avoidable clean-exit behavior. Infrastructure recovery is
a separate project.

## Design

### Preserve the lifecycle

Keep the six existing SOP steps and their completion standards. They already separate
state recovery, mechanical validity, measurement, diagnosis, modification, and
delivery. Renaming or merging them would create migration work without addressing the
observed exit mechanism.

### Clarify synchronous waiting

Step 3 states that `run-two-models.sh` is a synchronous operation. The constructor runs
it in the foreground whenever possible. If its tool returns a background session, the
constructor polls that same session until the command exits. It does not create a cron,
assume work continues after its final response, or ask a later human to read the result.
The task stays frozen until both selected arm processes terminate.

### Admit, rather than assume, another round

Step 5 admits a task modification only when it addresses one reproduced scoring defect
or one named capability axis supported by criterion evidence. A new difficulty axis
must have a targeted mutation showing sensitivity and isolation, enough non-saturated
criterion weight to affect the target threshold, and enough remaining time for
modification, mechanical validation, a complete round, and handoff. Otherwise the
constructor preserves the last valid state.

There is no fixed round limit. This retains the possibility of a later successful axis
while preventing speculative edits or rounds that cannot finish.

### Reuse the existing parser as the final checklist

Step 6 and the outer instruction require one existing command before final response:

```bash
/app/method/parse_scores.py \
  --last /app/build/evidence \
  --final-task /app/build/task \
  --json
```

The constructor may finish only when `task_matches_final` is true, both arm means are
readable, both selected arm reports contain at least one valid result, and no nested
round process remains active. The parser already fails on an unreadable latest round or
digest mismatch. This design deliberately does not add a second deliverability API.

Excluded provider or environment trials do not block delivery when the selected arm
still has a valid programmatic result.

## Files changed

- `template/environment/method/sop.md`: clarify Steps 3, 5, and 6 in place.
- `template/instruction.md`: replace duplicated final evidence mechanics with the
  short parser checklist and no-in-flight-exit rule.

## Preserved invariants

- Six SOP steps and six completion standards.
- Nop score 0, oracle score 1, and stable programmatic output.
- `target_mean < 0.7` and `R > 0.2` as joint construction targets.
- A time-exhausted delivery may miss the targets but must remain mechanically valid and
  have readable, matching latest two-arm evidence.
- Latest-round/latest-run selection, raw evidence authority, trial-validity rules,
  model identity checks, and continuous reward.
- Public network requirements and programmatic criterion weight ratio at most 10.
- Agent judge remains diagnostic and excluded from R; direct LLM judging remains
  unsupported.

## Non-goals

- No change to `parse_scores.py`, `run-two-models.sh`, `verify.py`, `task.toml`, or
  `run-production.sh`.
- No new CLI flag, runner marker, reference file, state machine, or test fixture.
- No automatic retry or resume for API, Daytona, or resource failures.
- No change to R, reward, models, timeouts, attempts, concurrency, or evidence layout.
- No new `resume.md` heading or classification table.

## Validation

1. Existing template-shape tests still prove six steps and six completion standards.
2. The complete Python unit suite passes unchanged.
3. Existing shell files pass `bash -n`.
4. The two active instruction files do not exceed their current combined 143 lines.
5. The final diff contains no production changes outside the two approved Markdown
   files.
