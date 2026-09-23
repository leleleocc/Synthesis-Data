# Candidate tests/

This file defines phase 05 verifier design and the Harbor test-tree shape.
`phase_contract.py` checks fixtures, fail
reasons, and form diversity; it does not invent the oracle.

The verifier is a discriminator, not a test collection. The goal is not
"generate N tests". The goal is: can this distinguish a correct
implementation from an incorrect one.

## Design

Do not go Task -> Tests. Go Task -> likely errors -> tests that kill those
errors. Typical error modes: off-by-one, boundary values, malformed input,
missing output, copied input, hardcoded stubs, state inconsistency, and
violations of the coupled `complexity_delta` constraints.

Two assertions that kill wrong implementations are worth more than twenty
happy-path checks. Do not pad coverage.

## Calibrate with correct and wrong cases

After writing the discriminator, execute the actual `tests/test.sh` in
disposable, isolated copies of the candidate runtime against:

- a temporarily constructed correct output, state, or implementation,
  appropriate to the task (must pass)
- missing output, empty output, wrong values, copies of input, hardcoded
  stubs, and negative-space violations where the instruction makes them
  relevant (must fail)

No existing reference solution is assumed. Calibration does not require a
persistent `solution/` or `solve.sh`. For behavior and state tasks, the correct
case must exercise the real system or recovered state; do not fabricate a
reward or mock verifier checks. Reset the runtime between cases and use the
same verifier for correct and wrong cases. After any verifier change, rerun
both kinds of case.

For native steps, execute the declared sequence with each step's selected
verifier, preserving prior-stage state within a case. Reset the runtime
between cases. Include plausible shortcuts identified during review, plus
valid alternate formatting, unspecified ordering, harmless extra fields,
and stated tolerances where the instruction permits them.

Keep temporary repairs, solved outputs, and runtime state out of the
candidate's initial environment and package. Retain only fixtures, goldens,
and helpers genuinely needed by the verifier under `tests/`.

If a wrong case passes, the verifier is too-loose. If a reasonable correct
case fails, it is too-strict. This is more useful than test counts.

## Output

Harbor still needs a binary reward: write `1` or `0` to
`/logs/verifier/reward.txt` on every exit path, only after the real checks
complete. That bit is the gate.

Do not stop at the bit. Print a per-check line so later review can score
quality instead of discarding the whole run:

```
normal case: pass
edge case: fail
error handling: fail
state check: pass
```

Every failure path must also print a reason. A silent `fail()` counter is
invalid.

## Mechanics

`tests/test.sh` is the shared Harbor entry; native steps may override it with
`steps/<name>/tests/test.sh`; apply the following to each selected tests tree.
Harbor uploads that tree to `/tests/` and runs its executable `test.sh` after
the corresponding agent step.
Each selected entry must not install packages
(`pip`, `uvx --with`, `apt-get`, `curl | sh`). Canonical pins:
`pytest==9.1.1` and `pytest-json-ctrf==0.5.2`. Inline: bake them into the
candidate `environment/Dockerfile`. Separate: bake them into
`tests/Dockerfile`. Then invoke bash, python, pytest, or another language.
Compute expected values from pristine fixtures or a fixed reference, never
from files the agent can edit. Existence-only checks are not enough.
Behavior and state oracles must probe the running system or recovered
state. Ship every `goldens/`, `fixtures/`, and helper under `tests/`.
Do not copy tests or solutions into the agent image. Inline pinned pytest
is a runtime dependency, not an answer leak.

Across a batch of two or more candidates, use at least two languages or
preview forms. Follow the oracle, not one template.
