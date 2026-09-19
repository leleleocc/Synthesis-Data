# Phase 02: repository gate

## ROLE

You are phase 02 only. Run independently from disk; do not rely on chat history.
You own `/synthesis/state/02_repo_gate.json` only. You do not redesign the
profile, environment, or candidates.

## BOUNDARIES

- Treat `/synthesis/input/repository` as read-only reference input. Do not write,
  install, build, or run tests inside it.
- If you need to try a command, first copy it to a scratch directory such as
  `/tmp/repo`. The final Harbor package clones the upstream commit from
  `target_spec`; it does not ship this tree.
- This phase is **static**: do not install the package or run its test suite.
  Judge buildability from manifests, lockfiles, CI, Dockerfiles, and test layout;
  phase 03 does the real build.
- Treat prior state JSON and `.integrity/*.sha256` seals as read-only.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 03+ work in this turn.

## INPUTS

Read:

- `/synthesis/input/target_spec.json`
- `/synthesis/state/01_repo_profile.json`
- the source repository at `target_spec.source_repo.path`

## HANDOFF

Hard gate: `/synthesis/state/02_repo_gate.json`.

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 02_repo_gate
```

Stopping without that file fails the phase. Final shape:

```json
{
  "accepted": true,
  "hard_checks": {
    "source_present": true,
    "executable_logic": true,
    "build_or_runtime_path": true,
    "target_alignment": true,
    "license_known": true
  },
  "blockers": [],
  "repo_score": 0.0,
  "buildability_score": 0.0,
  "task_potential_score": 0.0,
  "decision": "accept"
}
```

## WORK

Apply cheap evidence-based gates first, then score. Do not skip the hard checks
because the repository looks high quality.

### Step 01: evaluate hard checks

Each value is `true` or `false`; unknown is `false`:

* `source_present`: a non-empty source tree exists at `source_repo.path`
* `executable_logic`: the tree has runnable programs, CLIs, services, or scripts
* `build_or_runtime_path`: a Dockerfile, compose file, language manifest, or
  documented run command exists
* `target_alignment`: the profile can host the requested envelope
  (profile `tags` intersect `target.tags`; detected languages intersect
  `target.languages`; detected domains intersect `target.domains`;
  detected subdomains intersect `target.subdomains`)
* `license_known`: a license file or equivalent notice is present

`accepted` is true only when every `hard_checks` value is true. Reject
documentation-only trees, empty templates, and repositories whose only behavior
is unrelated to the target. Do not deduplicate. Do not perform TerminalBench
leakage filtering. Do not turn unknown evidence into `true`.

`blockers` records failed or unknown critical conditions (empty when accepted).

### Step 02: score the repository

If `accepted` is false, `decision` must be `reject` and you may leave scores at
0. Do not invent a passing score to override a failed hard check.

Otherwise score the repository, not a hypothetical task. Consider completeness,
engineering quality, buildability, executable interaction potential, and the
likelihood of producing a meaningful terminal task under the requested tags.
Use file evidence; do not reward popularity or size. All scores are numbers in
`[0, 1]`.

Field notes: `repo_score` = overall completeness/quality;
`buildability_score` = reproducible build/run; `task_potential_score` =
potential for a verifiable terminal task. Do not add extra keys.

### Step 03: apply the threshold

The accept threshold is `target_spec.generation.min_repo_score`. Do not hardcode
a different cutoff. `decision` is `accept` only when `accepted` is true and all
three scores are at least that threshold. Otherwise `reject` and name the failed
threshold or missing evidence.

## GATE

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 02_repo_gate
python /opt/terminaltraj/scripts/target_spec.py check-repo-gate \
  /synthesis/input/target_spec.json \
  /synthesis/state/02_repo_gate.json
```

Fix anything reported, then stop.
