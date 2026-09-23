# Phase 07: verifier review

## ROLE

Coordinate two independent read-only reviews for each packaged candidate,
repair blocking defects, and run final verifier calibration. Own
`/synthesis/state/07_review.json`; publish candidates by joining
`release_candidate_ids` with `generated_task/manifest.json`.

## BOUNDARIES

- Do not let reviewers edit files, execute package code, run trials, write the
  handoff, or decide publication.
- Do not edit a candidate while any reviewer is inspecting it.
- Do not redesign the goal or oracle, change slot deployment dimensions, or
  return a candidate to an earlier phase for repair.
- Do not block publication, relabel difficulty, or add complexity to satisfy
  difficulty advice.

## INPUTS

- `/synthesis/state/05_verifier.json`
- `/synthesis/output/generated_task/`

Read these resources under `/opt/terminaltraj/`:

- `skills/simula-synthesis/references/packaging.md`
- `skills/simula-synthesis/references/tests.md`
- `docs/static-checks.md`
- `docs/task-implementation.toml`
- `docs/taxonomy.md`
- `docs/difficulty.md`

The package layout comes from `task.toml`. For multiple-step tasks, inspect
each declared `steps/<name>/instruction.md` and its selected verifier.

## HANDOFF

Write one review per packaged candidate to `/synthesis/state/07_review.json`:

```json
{
  "reviews": [{
    "candidate_id": "c1",
    "package_slug": "example-task",
    "syntax_ok": true,
    "harbor_shape_ok": true,
    "static_checks_ok": true,
    "rubric_ok": true,
    "calibration_executed": true,
    "calibration_evidence": {"positive": ["..."], "negative": ["..."]},
    "status": "publish",
    "checks": {
      "too_loose": {"outcome": "pass", "explanation": "..."},
      "too_strict": {"outcome": "pass", "explanation": "..."},
      "deterministic": {"outcome": "pass", "explanation": "..."}
    },
    "review_reports": {"static": [], "implementation": []},
    "issues": []
  }],
  "release_candidate_ids": ["c1"]
}
```

Replace placeholders with executed calibration cases and complete latest
reviewer reports in the format defined by `packaging.md`. Set
`calibration_executed` only after running the actual packaged verifier against
both positive and negative cases. Status is `publish`, `revise`, or `reject`;
non-publish records have non-empty `issues`. This handoff and the generated-task
manifest define the release set.

## WORK

### Step 01: validate packages

Run `python /opt/terminaltraj/scripts/phase_contract.py ensure-handoff 07_review`.
Apply the Harbor library validation in `packaging.md` to every package and
check script syntax. Set `harbor_shape_ok` and `syntax_ok` from these results.

### Step 02: delegate and collect reviews

Spawn a Static Review Agent and an Implementation Review Agent for every
candidate, in parallel when capacity permits. Give each the actual package,
its role, and assigned review documents as defined in `packaging.md`. Limit
concurrent candidates to available capacity and keep each package stable
through the review round.

The static reviewer covers every named check in `static-checks.md`. The
implementation reviewer covers every criterion in `task-implementation.toml`,
using `taxonomy.md` for category and `difficulty.md` for advisory context.
Both return per-item results, including reasons for `not_applicable`, and
identify concrete repair scopes or calibration cases.

Wait for both reviewers and collect complete reports before editing. Resume or
complete interrupted reviews; a missing report or omitted criterion is not a
pass. The main agent owns all execution, repairs, and release decisions.

### Step 03: repair and re-review

Reconcile findings against the package and documented rules. Repair blocking
failures with the smallest change, preferring environment and tests. Modify
root or step instructions only for instruction-shape failures. Keep deployment
dimensions aligned with the candidate's slot.

After each edit, obtain affected re-review using the scope rules in
`packaging.md`. Wait for every active reviewer before further edits. Retain
unaffected results so the final reports cover all checks; repeat Harbor and
syntax validation after relevant changes. Set `static_checks_ok` from all
applicable static checks and `rubric_ok` from applicable non-advisory criteria.

### Step 04: calibrate and verify repairs

Execute correct and wrong cases against the actual packaged verifier, following
`tests.md` and `packaging.md`. Include plausible failures identified by review
and valid alternatives permitted by the instruction. Reset between cases and
record the executed cases and outcomes. Repair too-loose or too-strict
assertions in the selected test tree, then rerun both positive and negative
calibration and obtain affected re-review.

Phase 06 already ran nop. After any package edit, rerun nop using the shared
procedure; actual GPU packages require Daytona. A crash, missing reward, or
reward other than `0` requires repair, affected re-review, and another nop.

### Step 05: decide and validate the handoff

Use the final package, verifier, reports, and executed results to decide the
status. Publish when all blocking checks pass; `difficult` and
`essential_difficulty` remain honest advisory findings with `advisory: true`.
Use `reject` only when the instruction cannot support a fair oracle.

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 07_review
python /opt/terminaltraj/scripts/phase_contract.py check-verifier-review \
  /synthesis/state/05_verifier.json \
  /synthesis/state/07_review.json \
  /synthesis/output/generated_task
```

Resolve all reported issues before returning the handoff.

## GATE

Finish with complete latest reports for every packaged candidate, at least one
`publish` candidate, and `release_candidate_ids` containing publish candidates
only. Publication requires Harbor shape, syntax, all applicable blocking
checks, alignment, determinism, positive and negative calibration, and nop
reward `0` after package edits. Difficulty advice does not affect this gate.
