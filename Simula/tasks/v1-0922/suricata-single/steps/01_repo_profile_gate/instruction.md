# Phase 01: repository profile and gate

## ROLE

You are phase 01 only. Run from files on disk; do not rely on chat history.
You own `/synthesis/state/01_repo_profile_gate.json` only. You do not own the
environment, candidates, tests, or later state files.

## BOUNDARIES

- Read the repository only from the pinned URL and commit in
  `/synthesis/input/target_spec.json`.
- Do not expect or use `/synthesis/input/repository`, and do not add a local
  source path to the target spec or the handoff.
- Clone and inspect in a temporary directory only. Do not modify the upstream
  checkout or write under `/synthesis/output/`.
- The state handoff must not be created until the pinned fetch and checkout
  succeed. A fetch, URL, or commit failure must leave no
  `/synthesis/state/01_repo_profile_gate.json`; the missing handoff is the
  phase failure signal.
- At the start of a retry, remove any stale
  `/synthesis/state/01_repo_profile_gate.json` and its integrity seal before
  fetching, so a failed retry cannot reuse a previous success.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 02+ work in this turn.
- Skills and docs under `/opt/terminaltraj/` are already in the image; they
  are not inputs. Use `docs/taxonomy.md` when classifying domains.

## INPUTS

- `/synthesis/input/target_spec.json`

Use `source_repo.url` and `source_repo.commit` as the only repository
coordinates. The target fields describe the requested generation envelope.
Profile what the pinned repository actually contains, then record the
requested domains, subdomains, tags, and deployment dimensions it can
support. Do not infer capabilities from the target alone. A requested GPU,
MCP, multi-container, or separate-verifier shape needs files or run paths in
the tree, or the gate rejects.

## HANDOFF

Hard gate: `/synthesis/state/01_repo_profile_gate.json`. Do not create a
skeleton before the pinned checkout succeeds.

First create a temporary checkout and verify the exact commit:

```bash
rm -f /synthesis/state/01_repo_profile_gate.json \
  /synthesis/state/.integrity/01_repo_profile_gate.sha256
tmpdir=$(mktemp -d)
git init "$tmpdir/repo"
git -C "$tmpdir/repo" remote add origin "<source_repo.url>"
git -C "$tmpdir/repo" fetch --depth 1 origin "<source_repo.commit>"
git -C "$tmpdir/repo" checkout --detach FETCH_HEAD
```

If any command fails, clean up the temporary directory and stop without writing
the JSON handoff. After the checkout succeeds, create the handoff once:

```bash
python /opt/terminaltraj/scripts/phase_contract.py ensure-handoff 01_repo_profile_gate
```

Overwrite the skeleton as evidence is collected. Final shape:

```json
{
  "checkout": {
    "verified": true,
    "head": "0123456789abcdef0123456789abcdef01234567"
  },
  "languages": ["c", "shell"],
  "domains": ["software"],
  "subdomains": ["systems", "databases"],
  "entrypoints": ["..."],
  "tags": ["cli", "caching"],
  "evidence": {
    "license_files": ["COPYING"],
    "build_files": ["Makefile"],
    "entrypoint_files": ["src/server.c"]
  },
  "license": {"known": true},
  "executable": {"present": true},
  "deployment_support": {},
  "hard_checks": {
    "source_present": true,
    "executable_logic": true,
    "build_or_runtime_path": true,
    "target_alignment": true,
    "license_known": true,
    "deployment_support": true
  },
  "blockers": [],
  "repo_score": 0.85,
  "buildability_score": 0.8,
  "task_potential_score": 0.9,
  "decision": "accept"
}
```

Do not add a local path, task-type field, or unobserved evidence. Do not copy
`source_repo`, `target_alignment`, `accepted`, `license.files`, or
`executable.entrypoints`. `checkout.head` is the pin; set it from
`git rev-parse HEAD`. License files live under `evidence.license_files`;
runnable names live under `entrypoints`. The validator computes
alignment as the intersection of profile lists with the target. The profile
does not select task verification behavior; leave that to later phases.

## WORK

### Step 01: fetch the pinned source

Read and validate the URL and commit as non-empty strings. Fetch exactly that
commit with a shallow Git operation into a temporary directory. Confirm
`git rev-parse HEAD` equals the requested commit before creating the handoff.

### Step 02: collect repository evidence

Inspect commit metadata, license files, README/docs, Docker or compose files,
build manifests, lockfiles, entrypoints, tests, and representative source.
Record only languages, domains, subdomains, entrypoints, and tags that the tree
can actually host. Record license evidence and executable evidence separately.

Classify by the primary skill the repository exercises, not incidental tooling.
Use the closed domains `science`, `software`, `ml`, `operations`, `security`,
`hardware`, and `media`; use the seed subdomains in `taxonomy.md` or a new
lowercase kebab-case subdomain under the best-fitting domain. Use only the
factory tag vocabulary. Languages are lowercase language ids. Never invent a
commit or turn a missing signal into a positive fact.

### Step 03: apply the repository gate

Set each `hard_checks` value from evidence. `source_present` means the pinned
checkout is non-empty; `executable_logic` means it has runnable programs,
CLIs, services, or scripts; `build_or_runtime_path` means a build manifest,
container file, or documented run path exists; `target_alignment` requires an
intersection with the requested language, domain, subdomain, and tag values;
`license_known` requires a license file or equivalent notice;
`deployment_support` is true when every requested
`target.deployment_dimensions` value has observed evidence, or when that object
is absent. If the target requests a dimension, record `deployment_support` as
`{dimension: {values: [...], evidence: [paths]}}`. Invented compose, GPU, or
MCP support is a reject.

If any hard check fails, set `decision` to `reject`, list the blocker, and do
not use a passing score to override it. Otherwise score repository
completeness, reproducible buildability, and meaningful task potential in
`[0, 1]`. Read `generation.min_repo_score` and set `decision` to `accept` only
when every hard check is true and all three scores meet that threshold;
otherwise reject and name the failed threshold. Do not emit a separate
`accepted` field.

### Step 04: self-check the handoff

Run both contract checks before stopping:

```bash
python /opt/terminaltraj/scripts/phase_contract.py require-handoff 01_repo_profile_gate
python /opt/terminaltraj/scripts/phase_contract.py check-repo-profile-gate \
  /synthesis/input/target_spec.json \
  /synthesis/state/01_repo_profile_gate.json
```

Fix every reported issue, then stop.

## GATE

The phase passes only when the pinned checkout was verified, the combined JSON
exists with no local source path, and both commands in Step 04 succeed.
