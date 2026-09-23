# Phase 08: package Harbor tasks (assemble only)

## ROLE

You are phase 08 only. Assemble only. Run independently from files on disk.
Do not redesign tasks. Do not rewrite tests. Do not rebuild the environment.
You copy already-owned pieces into one Harbor task directory per survivor and
add a short `README.md`.

## BOUNDARIES

- Treat `/synthesis/input/repository` as read-only.
- Packaging copies the sealed base `/synthesis/output/environment/` merged
  with each candidate overlay; do not vendor the input tree into the package
  (the task Dockerfile clones the pinned commit).
- Do not modify `/synthesis/output/environment/`.
- Do not re-run `check-environment` or `docker build`.
- If you must try a command, use a scratch directory such as `/tmp/repo`.
- Do not invent new Harbor fields.
- If a tool call returns empty output, retry once; do not skip the package tree.
- Nothing else in the package root: no `metadata.json`, no nested synthesis
  state, no source checkout, no scratch files.

What each earlier phase already owns:

- Environment (03 sealed base + 04 overlay): `/synthesis/output/environment/`
  and `candidates/<id>/environment/`
- Task (04, reviewed by 05): `candidates/<id>/instruction.md` and `task.toml`
- Tests (06, reviewed by 07): `candidates/<id>/tests/**`
- This phase: merge those pieces into one Harbor task directory per survivor
  and add a short `README.md`

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- `/synthesis/state/05_task_review.json`
- `/synthesis/state/06_verifier.json`
- `/synthesis/state/07_verifier_review.json` (if present)
- `/synthesis/state/03_environment.json`
- `/synthesis/state/04_task_design.json`
- every approved candidate under `/synthesis/output/candidates/`
- `/synthesis/output/environment/`

## HANDOFF

This phase has no new state JSON. The handoff is the package tree plus
`manifest.json`.

For each approved id create `/synthesis/output/generated_task/<slug>/`:

```text
<slug>/
  instruction.md   # byte-for-byte copy of candidates/<id>/instruction.md
  task.toml        # copy of candidates/<id>/task.toml (see rename rule below)
  environment/     # sealed base merged with candidates/<id>/environment/
  tests/           # byte-for-byte copy of candidates/<id>/tests/
  README.md        # short provenance note (not used by the agent)
```

`<slug>` is a descriptive lowercase kebab-case name of at most three words
(for example `dedupe-survey-csv`), unique across packages. Prefer deriving it
from the instruction goal; do not use bare ids like `c1` unless nothing better
fits.

Also write `/synthesis/output/generated_task/manifest.json`:

```json
{
  "generated_tasks": [
    {
      "candidate_id": "c1",
      "path": "<slug>",
      "deployment_mode": "single",
      "source_commit": "<target_spec.source_repo.commit or unknown>"
    }
  ]
}
```

`path` is the directory name under `generated_task/`. `deployment_mode` must
match `03_environment.json`. One entry per packaged candidate, same order as
the approved list.

Required outputs: `manifest.json` and each package directory with
`instruction.md`, `task.toml`, `environment/`, `tests/`, and `README.md`.

## WORK

### Step 01: choose who to package

Use `state/07_verifier_review.json.approved_candidate_ids` when that file
exists and lists ids; otherwise use
`state/05_task_review.json.approved_candidate_ids`. Package every id in that
list (order preserved). Count must be >= 1.

### Step 02: copy with the five rules

1. `instruction.md`: exact copy from the candidate **after** phase 05
   (including any minimal review edits). Phase 08 does not edit it further.
   It must already be pure ASCII (phases 04-05 own that); Harbor host-reads
   this file with the locale encoding and non-ASCII bytes crash Windows/GBK.
2. `tests/`: exact recursive copy of the candidate `tests/` tree **after**
   phase 07 (including any minimal review edits). Keep `test.sh` executable.
3. `environment/`: copy `/synthesis/output/environment/`, then copy
   `candidates/<id>/environment/` on top of it (same relative path: overlay
   wins). No Dockerfile rewrites, no path prefix hacks, no extra files beyond
   that merge. Do not run `check-environment`.
4. `task.toml`: start from the candidate `task.toml` **after** phase 05.
   The only phase-08 edit is aligning identity with the package directory:
   - `[task].name` may become `terminaltraj/<slug>` (or keep org prefix if
     already `org/something`, then set the name part to `<slug>`)
   - optional: set `[metadata].candidate_id = "<id>"` and
     `[metadata].package_slug = "<slug>"` if those keys help audit
   Do not invent new Harbor fields. Do not change timeouts, network_mode, or
   vocabulary metadata unless required for the name/slug alignment above.
5. `README.md` (required): plain text or markdown for humans only. Include at
   least candidate id, slug, source repo url/commit from target_spec, and that
   environment is phase-03 base merged with the phase-04 overlay, tests came
   from phase 06-07, and instruction from phases 04-05. No solution, no hidden
   answers.

### Step 03: write the manifest

Write `manifest.json` with one entry per packaged candidate, same order as the
approved list. Confirm `manifest.json` and each package directory exist on disk.

## GATE

Phase 08 has no new state JSON; its handoff is the package tree. Still confirm
upstream handoffs exist, then run the package contract:

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 03_environment
python /opt/terminaltraj/scripts/target_spec.py require-handoff 04_task_design
python /opt/terminaltraj/scripts/target_spec.py require-handoff 06_verifier
test -f /synthesis/state/07_verifier_review.json \
  && python /opt/terminaltraj/scripts/target_spec.py require-handoff 07_verifier_review \
  || true
python /opt/terminaltraj/scripts/target_spec.py check-package \
  /synthesis/input/target_spec.json \
  /synthesis/state/03_environment.json \
  /synthesis/state/04_task_design.json \
  /synthesis/state/06_verifier.json \
  /synthesis/state/07_verifier_review.json \
  /synthesis/output/environment \
  /synthesis/output/candidates \
  /synthesis/output/generated_task
```

If `07_verifier_review.json` is missing, pass `05_task_review.json` in its
place as the approved-id source (same CLI slot). Fix anything reported, then
stop. Confirm `manifest.json` and each package directory exist on disk.
