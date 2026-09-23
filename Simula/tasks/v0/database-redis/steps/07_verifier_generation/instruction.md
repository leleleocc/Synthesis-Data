# Phase 07: per-candidate verifier generation

## ROLE

You are phase 07 only. Run independently from files on disk; do not rely on
prior conversation. You own `candidates/<id>/tests/**` and
`/synthesis/state/07_verifier.json` only. You do not edit candidate
`instruction.md` or `task.toml`. You do not own the environment or later
state files.

## BOUNDARIES

- Treat all prior state files and their `.integrity/*.sha256` seals as
  read-only; do not modify them.
- Do not edit that candidate's `instruction.md` or `task.toml`.
- Do not write, install, build, or run tests inside
  `/synthesis/input/repository`; when you try a verifier against source, use
  a scratch copy such as `/tmp/repo`.
- Prefer exercising the sealed base image plus the candidate overlay fixtures.
- Do not generate verifiers for candidates that did not pass step 06. If the
  approved list is empty, report failure and stop.
- Do not modify `/synthesis/output/environment/` and do not re-run
  `check-environment`.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 08/09 work in this turn.

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- `/synthesis/state/03_environment.json`
- `/synthesis/state/05_task_design.json` (per-candidate `oracle_tools`)
- `/synthesis/state/06_task_review.json`
- the instruction files for `approved_candidate_ids`
- `/opt/terminaltraj/skills/harbor-task-creator/SKILL.md` and
  `/opt/terminaltraj/skills/harbor-task-creator/references/example-tasks.md`
  for Harbor verifier wiring (reward file, CTRF, `set -uo pipefail`, tests
  uploaded after the agent). Those walkthroughs are **very simple demos**.
  Copy the reward-channel shape, not their toy assertions, and not their
  verify-time `apt-get` / `curl | sh` / `uvx` installs (this factory is
  offline at verify time).

## HANDOFF

Hard gate: for every approved candidate id in
`06_task_review.json.approved_candidate_ids`:

1. `/synthesis/output/candidates/<id>/tests/test.sh` (executable, `bash -n` clean)
2. any helper/golden files that test needs under that `tests/` tree
3. one record for that id inside `/synthesis/state/07_verifier.json`

Plus the phase handoff itself:

4. `/synthesis/state/07_verifier.json`

Land the handoff **before** long ground-truth probes:

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 07_verifier
```

Then, for each approved id, write a minimal `tests/test.sh` skeleton (reward
channel + one placeholder assertion) and append a stub verifier record. Only
after those paths exist should you spend turns drilling fixtures or running
redis/docker experiments. Probes that never write `tests/` still score 0.

Same layout a normal Harbor task uses: `tests/test.sh` is the entrypoint;
helper scripts and oracle data (golden files, reference inputs, expected
values, a small `test_outputs.py`) sit next to it. Harbor copies `tests/`
into the container only after the agent has finished, so nothing under
`tests/` is visible to the agent. That is where ground truth belongs, never
in the environment image or under `assets/`.

Write `/synthesis/state/07_verifier.json` atomically:

```json
{
  "verifiers": [{
    "candidate_id": "c1",
    "checked_requirements": [{"requirement": "...", "assertion": "...", "oracle": "..."}]
  }]
}
```

Field notes: `verifiers` must contain one record per candidate in
`approved_candidate_ids`; `candidate_id` is the candidate ID;
`tests/test.sh` must exist under that candidate, be executable, and pass
`bash -n`; `checked_requirements` maps each requirement quoted or paraphrased
from the instruction to the assertion in the script and the oracle it relies
on (including any tolerance and why), and is what step 08 uses to judge
alignment. Do not add extra keys. The 04 index already records oracle types.

## WORK

### Step 01: land skeletons first

Run `ensure-handoff 07_verifier` immediately. For every approved id, write a
minimal executable `tests/test.sh` (reward channel plus one placeholder
assertion) and a stub verifier record. Do not start long docker/redis probes
until those paths exist.

### Step 02: honor the Harbor verifier contract

Harbor runtime (same as the skill; keep this even though the examples are
very simple demos):

- Harbor bind-mounts `/logs/verifier/`. After the agent stops it copies
  `tests/` to `/tests/` and runs `test.sh` with cwd `/tests/`. The agent
  never sees `tests/` or `solution/`. Ground truth belongs only here.
- Always write `/logs/verifier/reward.txt` on every exit path (missing
  file is `RewardFileNotFoundError`; empty is `RewardFileEmptyError`).
  Use `reward.txt` (singular), never `rewards.json`.
- Do not use `set -e` in `test.sh`; a failed assertion must still write
  the reward. The skill pattern is `set -uo pipefail`, `|| true` after
  the test runner, then decide 1 or 0 from the real status.

Factory overlay (stricter than the demos; do not copy demo `test.sh`):

- It runs after the agent, inside the task environment, as root, with no
  guaranteed working directory. Use absolute paths everywhere.
- It writes exactly `1` or `0` to `/logs/verifier/reward.txt` on every exit
  path (binary reward, no partial credit) and exits non-zero on failure. Write
  the reward last, from the final verdict; never pre-write `1`.
- It is deterministic, bounded in time, and **offline**. No `apt-get`,
  `yum`, `pip install`, `uvx`, or `curl | sh` at verify time. Skill
  Examples 1-4 all install packages in `test.sh`; that is demo
  convenience, forbidden here.
- Tools: POSIX `bash` / coreutils, plus this candidate's `oracle_tools`
  from `05_task_design.json` (phase 05 put anything missing into the
  overlay). Also allowed: 03 `entrypoints`. Do not call a binary that is
  on neither list. If `oracle_tools` includes `python3`, use stdlib
  (`json`, `hashlib`, `pathlib`); do not `import pytest` unless
  `oracle_tools` names pytest (it should not).
- It verifies behavior by executing or reading the agent's outputs, not by
  grepping source files or shell history for keywords.
- If it executes agent-produced code, `test.sh` derives the reward from the
  child's exit status and output; executed code must never write the reward.
- Skip pytest/CTRF unless `oracle_tools` names pytest. Default is bash,
  plus `python3` only when listed.
- Skill Example 1 (`assert fib(10) == 55` inline) and Pattern 2 (file
  exists + grep) are too loose for this factory. Skill Example 2's pytest
  file is the useful demo of **coverage** (every instruction behavior has
  a named check), not of the runner. Match that coverage with bash /
  listed `oracle_tools`, at this candidate's real difficulty.

### Step 03: map the instruction to assertions

The instruction is the contract. Every assertion must trace to a requirement
stated in the candidate instruction, and every requirement in the instruction
must have an assertion. Calibrate between two failure modes, both of which
step 08 rejects.

### Step 04: reject too-loose checks

Too loose (a wrong or partial solution would pass):

* Only checking that an output file exists or is non-empty, not its content.
* Checking a subset of the instruction's requirements: one of several output
  files, the column count but not the values, the header but not the rows.
* Accepting degenerate outputs: an empty file, a header-only CSV, an empty
  JSON object, or a copy of the input.
* Not checking the negative space: if the instruction says "only rows where
  X", also assert that excluded rows are absent; if it says "sorted by Y",
  check the order, not just the set.
* Deriving the expected answer from the agent's own output, or recomputing it
  from inputs the agent could have edited. Compute expectations from a
  pristine copy under `tests/` or from a reference calculation.
* Matching keywords in the agent's files instead of running or parsing them.
* Reward-channel bugs: writing `1` before the checks; swallowing failures
  with `|| true` and then still writing `1`; or exiting before writing
  `reward.txt`. Use `set -uo pipefail` (no `-e`); decide 1 or 0 from the
  real status after the checks.
* Tolerances or normalization so generous that wrong answers pass: sorting,
  lower-casing, or stripping whitespace before comparison hides real errors
  when the instruction asked for a specific order or exact values.
* Not enforcing a "do not modify X" constraint the instruction states; hash
  X against a pristine copy or make X load-bearing for the check.

### Step 05: reject too-strict checks

Too strict (a correct solution would fail):

* Asserting hard-coded values the instruction never specified: exact
  byte-for-byte output, whitespace, trailing newline, quoting style, float
  formatting, or a particular precision.
* Requiring an ordering (row order, column order, JSON key order) the
  instruction did not state.
* Requiring a specific tool, command, flag, or approach: checking shell
  history, requiring that a particular utility was used, or requiring
  intermediate files the instruction never mentioned.
* Requiring output paths, file names, or formats that are not in the
  instruction, or testing edge cases (empty input, malformed rows) the
  instruction never mentioned.
* Exact float equality where the instruction gives no precision; use a
  tolerance and justify it in `checked_requirements`.
* Failing on harmless extras the instruction did not forbid: additional
  columns, extra files, log output on stderr, a different but valid encoding
  of the same value.
* Baking one reference implementation's incidental formatting choices into a
  golden file and diffing against it literally.
* Depending on details that vary between valid runs: timestamps, locale,
  temporary file names, hostnames.

### Step 06: record ambiguity instead of inventing requirements

When the instruction is ambiguous about something the verifier needs
(ordering, precision, formatting), accept every reasonable reading rather than
picking one. If no reading can be verified, do not invent a requirement; omit
it from `checked_requirements` so step 08 can reject the candidate.

Replace each skeleton with a real verifier, keep helper/golden files under
that `tests/` tree, and fill the matching `07_verifier.json` record.

## GATE

Stopping without a passing self-check is a failed phase even if every probe
succeeded. Run:

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 07_verifier
python /opt/terminaltraj/scripts/target_spec.py check-verifiers \
  /synthesis/state/06_task_review.json \
  /synthesis/state/07_verifier.json \
  /synthesis/output/candidates
```

Also confirm on disk:

```bash
python - <<'PY'
import json
from pathlib import Path
ids = json.loads(Path("/synthesis/state/06_task_review.json").read_text())["approved_candidate_ids"]
missing = [i for i in ids if not Path(f"/synthesis/output/candidates/{i}/tests/test.sh").is_file()]
assert not missing, f"missing tests/test.sh for {missing}"
print("CHECKLIST_OK", ids)
PY
```

Fix anything reported, then stop. Do not start phase 08/09 work in this turn.
