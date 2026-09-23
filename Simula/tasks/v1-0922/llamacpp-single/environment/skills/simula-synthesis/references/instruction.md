# Candidate instruction.md

This file defines both the quality and Harbor file shape for phase 04. The
instruction is the only thing the task-solving agent sees and must be
self-contained.

Design from the sealed slot fields. The agent never sees the labels.

- `mechanism` and `scenario_angle` shape the opening situation.
- `output_shape` and parent `oracle_types` shape the acceptance evidence.
- `complexity_delta` is a list of `{"axis", "text"}` items. Realize each item's
  `text` as phenomena. Read the `axis` to know which kind of difficulty it is;
  do not guess axes from the prose.
- `primary_entrypoint` / `primary_input` are the absolute paths.
- `plan.difficulty` is the work band, not silence.

The instruction describes phenomena, not the specific problem. The agent
inherits a situation they can observe. They do not inherit a diagnosis.

## Write

- The current situation as what is happening: a service that will not stay
  up, a replica that lags, a file that is missing, an invariant that no
  longer holds. Name the starting state, not the cause.
- Acceptance criteria as the healthy phenomena a verifier can observe:
  processes, ports, invariants, artifacts, absolute input and output paths.
- Both coupled constraints from the `coupling` item of `complexity_delta`, also
  as phenomena (rewrite and replica offset both hold), not as a second output
  file. Realize every other item in that list the same way, one phenomenon per
  `axis`.
- Permitted tools and do-not-modify constraints if necessary.

A verifier must turn every acceptance criterion into an assertion. Vague
goals, unbounded network work, and requirements with no observable output
are invalid.

## Layout

- `step_mode=single`: write the candidate's root `instruction.md`.
- `step_mode=multiple`: write at least two `steps/<name>/instruction.md`
  files and record their execution order in the design record's `steps`
  list. Names are unique directory components. A root instruction is not
  required. Each stage states its observable inputs, outputs, and acceptance
  conditions in the shared runtime; the sequence covers both coupled
  constraints. Phase 05 consumes these files and their order.

Each instruction must be self-contained for its stage. Apply the same
disclosure and format rules to root and step instructions.

## Do not disclose

- A planted fault, root cause, or confirmed internal diagnosis. Follow the
  difficulty band's rules for identifying the affected area; hard/ultra
  instructions must not name a diagnosed defect site.
- Possible solutions, approaches, algorithms, or repair recipes.
- Irrelevant environment internals (unused files, internal APIs, flags,
  layout trivia).
- A tour of the tree or a walkthrough of how to succeed.

Real symptom logs, failing commands, reproduction conditions, and operating
constraints are allowed at every band. Paths and error strings in genuine
evidence are clues, not automatically a diagnosis. Do not annotate them
with the known cause or a repair recipe.

## Difficulty

`docs/difficulty.md`, the shared definition used by phases 03 and 04, is
already in this assignment in full. Apply `plan.difficulty` to the reasoning
and interacting constraints realized in the candidate. Do not re-read or
truncate it, and do not substitute a rule about hiding clues or adding
outputs for the shared difficulty bands.

For `hard` and `ultra`, realize exactly the axes present in this slot's
`complexity_delta` and no others. A slot carries 3 or 4 of them, chosen in
phase 03; do not add an axis the list does not contain and do not drop one it
does. Only realize difficulty the pinned repository and the sealed base
environment can actually support. Difficulty is the reasoning required before
the method is known. Once the approach is understood, carrying it out should
be a few hours. Do not raise difficulty by enlarging the environment,
lengthening the exploration, or adding repetitive edits.

The `text` of each item is a design input. It tells you what to realize in the
environment and what the instruction must make observable. It is not phrasing
to copy. Do not quote it, paraphrase it, or carry over its wording about which
repair fails, which shortcut is tempting, which explanation is wrong, or which
observation distinguishes them. The instruction shows phenomena only. The
task-solving agent must not be able to tell, from the instruction, what the
delta text says.

- `coupling`: both constraints hold together as phenomena, not as a second
  output file.
- `long-horizon`: the reasoning crosses the existing components and state
  transitions the item names. Do not collapse it into one localized edit, and
  do not stretch it by adding edits.
- `complex-environment`: the starting state is understandable only by exploring
  the sealed base, because the relevant behavior is spread across components
  whose joint behavior no single file explains. Complexity is an overlay on
  that base, not a new container, service, GPU, or resource. A large tree is
  not a complex environment.
- `compound-task`: the task stays focused on one domain from the parent global
  row, and the second constraint pulls in other domains that row covers. The
  second domain must change the correct repair, not merely appear alongside it.
- `cyclic-dependency`: show the observable chain. State the initial phenomenon,
  then the phenomenon that remains after a minimal fix still fails, with both
  constraints holding together. Do not say which fix causes it.
- `false-shortcut`: the environment must make the shortcut the item names
  locally consistent, so it looks right and survives a shallow check, and the
  acceptance criteria must be what exposes it. Do not name the shortcut and do
  not warn the agent away from it. Restarting, reverting, or trusting the first
  measurement should be tempting without the instruction saying so.
- `live-constraint`: the invariant the item names must be checkable throughout
  the repair, not only before and after it. State it as an operating condition
  that holds the whole time. Do not say that no safe window exists; the
  condition itself makes that true.
- `evidence-ambiguity`: present phenomena that support every explanation the
  item names, and do not say which is correct or which observation distinguishes
  them. The acceptance criteria must require the outcome that only that
  observation can confirm.

Do not ground difficulty on domain expertise that lives outside the pinned
repository: rate tables, regulatory formulas, specialist terminology, or any
knowledge the repository's code, tests, and docs do not contain.

Do not name a defect file, a planted fault, or a prescribed repair. Two
independent hard edits, or a long checklist, do not meet these bands.

## Diversity

Across a batch of two or more, do not clone one instruction and swap paths.
Vary the opening situation with the slot mechanism and vary the
acceptance-criteria shape. A reader must tell two instructions apart
without looking at paths.

## Shape

- Use absolute input and output paths and an exact, verifiable output format.
- Do not use Markdown headings (`#`, `===`, `---`) outside fenced code,
  relative paths, or evaluation mechanics such as "Submit your answer".
- Do not mention `tests/`, `solution/`, `test.sh`, `solve.sh`, or `reward.txt`.
- End with the Terminal-Bench suffix as its own last paragraph, followed by
  one newline. `N` is 7200 for a single-step task and 1800 for each step of
  a multiple-step task:

```text
You have N seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
```
