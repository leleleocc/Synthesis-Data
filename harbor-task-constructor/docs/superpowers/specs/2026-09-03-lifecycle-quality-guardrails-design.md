# Harbor Task Construction Lifecycle Quality Guardrails

## Status

Approved design scope. This document specifies a minimal change to the existing
single-task construction lifecycle. It does not introduce a separate quality system,
new scoring dimension, or criterion provenance taxonomy.

## Goal

Embed narrowly scoped quality guardrails into the existing six-step construction SOP
so the constructor removes confirmed scoring defects without suppressing useful
distinction from unstated engineering judgment. Every delivered task must still meet
the existing mechanical-validity and target/solver-separation standards.

## Existing delivery invariants

The change preserves all current delivery requirements:

- The untouched starting state is rejected and produces a readable programmatic score.
- The shipped solution is accepted and produces a readable programmatic score.
- `target_mean < 0.7` and `R > 0.2` are both required construction targets.
- The latest target and solver arm runs belong to the latest round and match the final
  task digest.
- The task, verifier environments, and phase overrides retain public networking.
- Scored programmatic criterion weights retain the existing maximum-to-minimum ratio
  constraint of 10.
- The outer verifier and continuous reward formula remain unchanged.

Whether a requirement is explicit, implicit, conventional, or an expression of good
engineering practice does not determine its criterion weight.

## Design principle

Criteria are presumed valid. The constructor must not remove, weaken, or reweight a
criterion merely because it is unstated in the instruction, reflects an engineering
preference, has a high weight, has a low pass rate, or creates model separation.

The constructor may treat scoring as defective only after establishing at least one of
these concrete failure mechanisms:

1. **Delivery-state irreproducibility:** the packaged task cannot reproduce its measured
   nop or oracle result without files, state, or build effects absent from the task.
2. **Direct contradiction:** a criterion conflicts with the instruction, a discoverable
   repository contract, or another scored requirement.
3. **Reference-implementation lock-in:** a runnable counterexample satisfies the target
   behavior but fails solely because the verifier requires private names, exact source
   text, or internal structure unique to the reference solution.
4. **Verifier instability or distortion:** repeated verification of the same artifact
   produces materially unstable scores, or the aggregation mechanism demonstrably turns
   a small underlying scoring change into a disproportionate result.

Low pass rate, including zero passes in a model sample, is diagnostic evidence only. It
does not establish any of the four failure mechanisms by itself.

## Lifecycle integration

The guardrails are inserted into the existing SOP rather than added as new stages.

### Step 2: Establish mechanical validity

Clarify that nop and oracle validation must run against the final deliverable task
state. The validation cannot rely on container-only files, omitted source comments,
uncollected workspaces, or other state that will not be present when the task artifact
is reconstructed.

Before real target/solver measurement, confirmed delivery-state irreproducibility must
be repaired. This remains part of the existing nop/oracle mechanical-validity check.

### Step 4: Inspect criterion differences

When reviewing criterion deltas, invalid trials, and faults, the constructor applies the
four failure mechanisms above. It must not infer invalidity solely from implicitness,
engineering preference, weight, pass rate, or contribution to model separation.

Reference-implementation lock-in requires a runnable behaviorally correct
counterexample, not a reviewer preference or a hypothetical alternative.

### Step 5: Make one coherent task change

A confirmed scoring defect may be repaired as part of the iteration's single coherent
design change. Once the task changes, earlier measurement evidence is stale and a new
round is required under the existing evidence rules.

If a legitimate repair raises `target_mean` or reduces `R`, the constructor must recover
the delivery targets by improving genuine task difficulty. It must not restore a
confirmed defect to recover separation.

### Step 6: Record, iterate, and deliver

When an iteration changes a criterion, aggregation rule, verifier, or delivery-state
input, the constructor records the concrete failure mechanism, counterexample, or
reproduction result under the existing five `resume.md` headings. No new headings or
explicit/implicit classification table are introduced.

The latest task must complete mechanical validation and have a complete, readable,
matching two-arm round before delivery. The existing `target_mean` and `R` targets remain
required.

## Normative contract addition

`docs/contract.md` will receive one short normative section containing these rules:

- Implicitness, engineering preference, high weight, low pass rate, and model separation
  are not scoring defects by themselves.
- A scoring change requires a concrete reproduction failure, direct contradiction,
  behaviorally correct counterexample, or verifier instability/distortion.
- Criterion provenance does not determine criterion weight.
- A confirmed defect cannot be restored to maintain `R`; separation must be rebuilt
  through genuine task difficulty and fresh evidence.

The contract will not duplicate the full SOP wording.

## Files changed by implementation

- `template/environment/method/sop.md`: add the lifecycle-local guardrails to Steps 2,
  4, 5, and 6.
- `docs/contract.md`: add the concise normative boundary.

No other production or test files are changed.

## Non-goals

- No standalone quality-gate pipeline or G0-G6 state machine.
- No requirement-to-test coverage matrix.
- No explicit/implicit criterion taxonomy.
- No automatic weighting based on criterion provenance.
- No new case-count, dependency-locking, judge-type, or repeated-run release policy.
- No changes to the runner, parser, verifier, evidence layout, reward formula, task
  instruction, or `resume.md` headings.
- No prose-presence assertions in `tests/test_template_shape.py`.

## Validation

Implementation validation consists of:

1. Reviewing the SOP to confirm the six existing steps and six completion standards are
   preserved.
2. Running the existing template regression suite without adding wording-sensitive
   tests.
3. Running shell syntax checks for the existing runner and verifier scripts.
4. Reviewing the final diff to confirm only the SOP and contract changed beyond this
   design document.

The validation demonstrates structural preservation. Judgment quality remains governed
by the normative instructions and concrete evidence recorded during task construction;
it is not approximated by string-matching tests.
