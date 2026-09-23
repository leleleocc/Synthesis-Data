---
name: simula-synthesis
description: Generate Simula candidate instructions, environments, task manifests, and verifiers with phase-scoped progressive disclosure.
---

# Simula synthesis local skill

Read only the reference file needed for the current phase and candidate. Do
not copy the whole skill into a prompt or expose later-phase fields early.

`/synthesis/input/target_spec.json` is the immutable input for phases 01-03.
Phase 03 converts it into `03_simula_plan.json` (`difficulty`, `global`,
`slots`). After that conversion a slot is the fullest Harbor-task preview:
local axes plus all five `deployment_dimensions`. Phases 04-07 must not
reread the full target spec; they join the sealed plan by slot id.

The orchestrator should pass a small projection to a subagent: phase 04
receives one slot, its parent global row, plan difficulty, and the
instruction/environment fields it needs; phase 05 receives that same slot,
the candidate instruction, and verifier/task fields.

Every slot has a closed `mechanism` (`plant-fault`, `recover-state`,
`reimplement`, `configure-runtime`, `build-matrix`, `protocol-decode`). Phase
03 samples at least `min(N, 3)` distinct mechanisms. Optional
`target.mechanisms` narrows the set and must be covered. Every slot is
compound: `complexified` is true and `complexity_delta` names two constraints
the agent must satisfy together.

References under this skill combine quality and Harbor file format. Read only
the reference needed for the current phase; `phase_contract.py` checks closed
vocab and on-disk alignment. The remaining Harbor skill references are the
original example and task field reference.

Phase 02 reads `references/environment.md`. Keep the base
generic. Topology follows phase 01 compose evidence, not a later slot
wish. One batch cannot mix single and multiple container bases. Phase 02
may set `resources.gpus = 1` when the target and phase 01 evidence request
GPU. Install once any runtime the whole batch will need. Clone once,
build once, smoke once.

Phase 03 reads the repository code at the pinned URL and commit, assesses
feasibility, and then designs slots. Phases 03 and 04 both read
`/opt/terminaltraj/docs/difficulty.md`, their shared difficulty definition;
phase 04 includes it in every candidate subagent's context. Slot fields are
in the phase instruction; `phase_contract.py check-simula-plan` is the gate.

Phase 04 reads `references/instruction.md` and `references/environment.md`.
Design from the sealed slot: `mechanism` and `scenario_angle` shape the
opening; `output_shape` and parent `oracle_types` shape acceptance
evidence; `complexity_delta` is both coupled constraints. Copy the sealed
environment, then plant the mechanism in that copy without naming it. The
instruction describes phenomena, not the specific problem. Hard and ultra
require enough work: the agent must discover the locus; both coupled
constraints are load-bearing; ultra constraints share state. Across a
batch, instructions must not be clones. Follow the shared difficulty bands
for disclosure: keep real logs and reproduction clues, including paths and
error strings, but do not identify a file as the diagnosed defect site in
hard/ultra instructions or supply a root cause or repair recipe. Keep sealed
topology on the copy. Do not
docker build a candidate image; `bash -n` is the environment check. Write
`04_task_design.json` as candidates appear.

Phase 05 reads `references/tests.md` and `references/task-toml.md`. The
verifier is a discriminator: Task -> likely errors -> tests that kill those
errors, then prove it with wrong solutions. `tests/test.sh` must not
install packages. Bake `pytest==9.1.1` and `pytest-json-ctrf==0.5.2` into
the candidate `environment/Dockerfile` when inline, or `tests/Dockerfile`
when separate. Customize `task.toml` to the slot (single vs multiple
container, single vs multiple step, inline vs separate verifier, GPU
quota, MCP transport). Agent network is `public`, so HTTP MCP can reach
its url. A stdio `command` must appear in the candidate environment.

Phase 05 owns `task.toml`; phase 06 only assembles it and must install Harbor
to run `TaskPaths.is_valid()` plus `TaskConfig.model_validate_toml()`, then
`harbor run -a nop -p <task-dir>` on every package (GPU: `-e daytona`).
Reward 0 is the pass. Phase 07 re-runs those library checks, then
must spawn two read-only reviewers per candidate: a static reviewer for
`/opt/terminaltraj/docs/static-checks.md`, and an implementation reviewer
for `/opt/terminaltraj/docs/task-implementation.toml` plus taxonomy and
`difficulty.md` context. Their initial reviews run in parallel when capacity
allows, against the same unchanged package. Pass the actual package and
relevant review docs,
without earlier design reasoning or self-assessments. Each returns
per-item `name`, `outcome` (`pass`, `fail`, or `not_applicable`), `path`, and
`reason`; retain the reports in `review_reports.static` and
`review_reports.implementation`. Process a bounded number of candidates at
once.

Only the phase 07 main agent merges findings, edits files, executes
calibration and nop, writes review state, and decides publication. After
repairs, the affected reviewer re-reviews the current files; use both if
both scopes changed or the impact is uncertain. Keep the package unchanged
while reviewers inspect it. `difficult` and `essential_difficulty` are
advisory: perceived ease, band mismatch, or difficulty-source preferences
must not cause rejection, repair, difficulty relabeling, or
`rubric_ok=false`. Keep their honest outcomes with `advisory: true`, not
`not_applicable` merely to bypass a disagreement. Other criteria must
identify independent correctness, fairness, alignment, resource, or
task-validity defects to block publication.

Skip Agent Trials, Cheat, Fortify, AI-detection, Docker Build, and Oracle
Validation. After any packaged edit, re-run nop. GPU nop needs
`DAYTONA_API_KEY` from the factory environment. The main agent repairs a
failing blocking check in the packaged task with the smallest change that
makes it pass: prefer environment and tests; edit instruction.md only for
heading, absolute-path, or suffix failures. Too-loose or too-strict means
a small `tests/` assertion edit, re-run, and repeat until publish; do not
bounce the candidate to phase 05.
Do not fetch TASK_REVIEW_AUTOMATION.md.
