# Phase 06: per-candidate task review

## ROLE

You are phase 06 only. Run this phase independently from files on disk; do not
infer requirements from chat history. You own `/synthesis/state/06_task_review.json`
and minimal in-place edits to each candidate's `instruction.md` / `task.toml`
and overlay `environment/` only. This is still a **review** step, not a second
design pass. Phase 07 must implement tests against the **final** instruction on
disk.

## BOUNDARIES

- Treat prior state JSON files and their `.integrity/*.sha256` seals as
  read-only. Do not modify `/synthesis/output/environment/` or
  `/synthesis/input/repository`. If you need to try a command against the source,
  use a scratch directory such as `/tmp/repo`.
- Do not write `/synthesis/state/05_task_design.json` or any other prior
  `/synthesis/state/*.json`. Phase 05 sealed that index. This phase writes
  only `/synthesis/state/06_task_review.json`.
- Do not replace the goal, vocabulary lists, or overall scenario.
- Do not invent a new task or swap fixtures for a different problem.
- Do not edit the sealed base environment, sealed prior state JSON, or other
  candidates' unrelated files.
- Do not perform large rewrites (if the fix needs a new design, reject or leave
  unapproved).
- Do not re-run `check-environment` or rebuild the sealed base.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 07+ work in this turn.

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- `/synthesis/state/01_repo_profile.json`
- `/synthesis/state/03_environment.json`
- `/synthesis/state/05_task_design.json`
- every candidate under `/synthesis/output/candidates/<id>/` (`instruction.md`,
  `task.toml`, and overlay `environment/`)

## HANDOFF

Hard gate: `/synthesis/state/06_task_review.json`. Stopping without that file
fails the phase.

Land the skeleton before long scoring:

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 06_task_review
```

Write `/synthesis/state/06_task_review.json` atomically. Final shape:

```json
{
  "reviews": [{
    "candidate_id": "c1",
    "approved": true,
    "scores": {
      "verifiable": 0.0,
      "well_specified": 0.0,
      "solvable": 0.0,
      "difficult": 0.0,
      "interesting": 0.0,
      "outcome_verified": 0.0,
      "spec_alignment": 0.0
    },
    "checks": {
      "anti_cheat_robustness": {"outcome": "pass", "explanation": "..."},
      "deterministic_reproducible": {"outcome": "pass", "explanation": "..."},
      "essential_difficulty": {"outcome": "pass", "explanation": "..."},
      "novel": {"outcome": "pass", "explanation": "..."},
      "agentic": {"outcome": "pass", "explanation": "..."},
      "instruction_concision": {"outcome": "pass", "explanation": "..."},
      "structured_data_schema": {"outcome": "not_applicable", "explanation": "..."},
      "task_security": {"outcome": "pass", "explanation": "..."},
      "typos": {"outcome": "pass", "explanation": "..."}
    },
    "edits": [
      {
        "path": "/synthesis/output/candidates/c1/instruction.md",
        "reason": "stated normative CSV schema for the output"
      }
    ],
    "blocking_issues": []
  }],
  "approved_candidate_ids": ["c1"]
}
```

Field notes: one review per phase-05 candidate; `approved` matches
`approved_candidate_ids`; `edits` lists minimal fixes applied (empty if none);
paths in `edits` must stay under that candidate's directory.

## WORK

### Step 01: apply only allowed minimal fixes

When a problem is small and local, fix the candidate files in place, then score
the **edited** text.

Allowed:

* `instruction.md`: fix typos; add missing absolute paths; clarify success
  conditions or structured schemas; remove process-prescribing wording; tighten
  anti-cheat lines that the instruction already implies; replace non-ASCII
  punctuation (em-dash, en-dash, smart quotes, arrows) with ASCII (`-`, `'`,
  `"`, `->`) so Harbor can host-read the file on Windows/GBK
* `task.toml`: align `[task].description` / keywords with the instruction;
  if `network_mode` is `no-network`, set it to `public` (Harbor agent install
  needs runtime network); fix timeouts; correct `category`/`tags` or the
  expert/junior time estimates when they do not match the task as written
  (estimates must stay inside the `target.difficulty` band); keep vocabulary
  metadata consistent with the phase-05 index; keep the file ASCII
* overlay `environment/`: remove a leaking fixture; add a missing COPY source;
  tiny path fixes. Do not change topology, do not rewrite the Dockerfile from
  scratch, do not touch the sealed base, and do not add or remove observation
  tools (`oracle_tools` lives in sealed phase-05 state).

Not allowed:

* Replace the goal, vocabulary lists, or overall scenario
* Invent a new task or swap fixtures for a different problem
* Edit `/synthesis/output/environment/`, sealed prior state JSON, or other
  candidates' unrelated files
* Write or rewrite `/synthesis/state/05_task_design.json` (or any prior
  state JSON). The design index is sealed; record review-only decisions in
  `06_task_review.json`
* Large rewrites (if the fix needs a new design, reject or leave unapproved)

Record every edit under that review's `edits` list (`path` + short `reason`).
If you made no edits, use `"edits": []`. After edits, re-read the files before
scoring.

### Step 02: score seven dimensions

Score the final on-disk instruction. Part 1: score seven dimensions in `[0, 1]`
(Terminal-Bench proposal rubric plus spec alignment).

* `verifiable`: a program could decide pass/fail from the end state,
  deterministically, with no subjective judgment.
* `well_specified`: exact output paths, formats, and correctness conditions;
  two reviewers would write equivalent verifiers.
* `solvable`: doable in the sealed base plus this candidate's overlay with
  declared entrypoints and data; a SOTA agent finishes inside the
  `target.difficulty` wall-clock band (easy <=1h, medium 1-3h, hard 3-6h,
  ultra 6h+).
* `difficult`: hard for a good reason at `target.difficulty`, not tedium or
  formatting minutiae. `ultra` must be compound (two or more interacting
  hard parts), not a long easy checklist.
* `interesting`: realistic professional value; not a gimmick or trick question.
* `outcome_verified`: states the goal, not the step-by-step method; constraints
  are only mechanistic anti-cheat rules.
* `spec_alignment`: vocabulary fields fit `target_spec.target` and
  `03_environment.json`.

### Step 03: run nine checks

Part 2: for each criterion give `"pass"`, `"fail"`, or `"not_applicable"` plus
a one- to three-sentence explanation. Use exactly these names:

* `anti_cheat_robustness`
* `deterministic_reproducible`
* `essential_difficulty`
* `novel`
* `agentic`
* `instruction_concision`
* `structured_data_schema`
* `task_security`
* `typos`

(Same meanings as the Terminal-Bench implementation rubric, judged from the
instruction and environment only.)

### Step 04: apply the decision rule and write the review

A candidate may be approved only if all seven scores are at least `0.7`, no
check is `"fail"`, and the design index does not record `env_build=failed`.
The on-disk `instruction.md` and `task.toml` after your edits must be pure ASCII
(Harbor host-reads them with the locale encoding). Approve **every**
candidate that qualifies; do not cap the count. Every rejected candidate needs
at least one concrete `blocking_issues` entry. At least one candidate must be
approved or this phase fails and synthesis stops.

Fill every field of `/synthesis/state/06_task_review.json` from the scored,
edited candidates.

## GATE

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 06_task_review
python /opt/terminaltraj/scripts/target_spec.py check-review \
  /synthesis/input/target_spec.json \
  /synthesis/state/05_task_design.json \
  /synthesis/state/06_task_review.json \
  /synthesis/output/candidates
```

Fix anything reported, then stop.
