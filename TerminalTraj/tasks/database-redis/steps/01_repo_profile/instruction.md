# Phase 01: repository profile

## ROLE

You are phase 01 only. Run from files on disk; do not rely on chat history.
You own `/synthesis/state/01_repo_profile.json` only. You do not own the
environment, candidates, tests, or later state files.

## BOUNDARIES

- Do not modify `/synthesis/input/repository` (or `source_repo.path`).
- Do not write under `/synthesis/output/`.
- If a tool call returns empty output, retry once; do not skip the handoff.
- Do not start phase 02+ work in this turn.

## INPUTS

Read only:

- `/synthesis/input/target_spec.json`
- the repository at `target_spec.source_repo.path`
- `/opt/terminaltraj/scripts/taxonomy.md` (Terminal-Bench domain/subdomain list)

`target_spec.target` is the requested generation envelope, not a description of
the repository. Profile what the repository actually is, then note which
requested domains, subdomains, and tags it can support.

## HANDOFF

Hard gate: `/synthesis/state/01_repo_profile.json`. Missing file fails the phase
even if you inspected the tree thoroughly.

Before long inspection:

```bash
python /opt/terminaltraj/scripts/target_spec.py ensure-handoff 01_repo_profile
```

Overwrite the skeleton as you learn. Final shape:

```json
{
  "source_repo": {"path": "...", "commit": "..."},
  "languages": ["c", "shell"],
  "domains": ["software"],
  "subdomains": ["systems", "databases"],
  "entrypoints": ["..."],
  "tags": ["cli", "caching"]
}
```

## WORK

### Step 01: scan evidence

Inspect commit metadata when available, license files, README/docs, Docker or
compose files, build manifests, lockfiles, entrypoints, tests, and representative
source. Record only languages, domains, subdomains, entrypoints, and tags the
tree can actually host.

### Step 02: map to the taxonomy and tag vocabulary

Classify by the **primary skill** the repository exercises, not incidental
tooling (a finance system that happens to use Python is still Operations /
Finance).

* domains (closed, lowercase kebab): `science`, `software`, `ml`,
  `operations`, `security`, `hardware`, `media`. These match Terminal-Bench
  `category` Title Case (`Science`, `Software`, `ML`, `Operations`,
  `Security`, `Hardware`, `Media`). Do not invent a domain.
* subdomains: seed list in `/opt/terminaltraj/scripts/taxonomy.md` (kebab:
  `biology`, `systems`, `databases`, `data-engineering`, `reverse-engineering`,
  `supply-chain`, `appsec`, ...). Seed names must sit under a listed domain.
  If nothing fits, add a new lowercase kebab-case subdomain under the
  best-fitting domain. Do not use a domain name as a subdomain.
* tags: closed factory vocabulary (skill and tech tokens: `debugging`,
  `optimization`, `build-system`, `redis`, `caching`, `cli`, `linux`, ...).
  List only tags the tree can actually host. Do not treat tags as a
  replacement for `languages`.
* oracle types (not stored here; used later): `result`, `state`, `behavior`

`languages` is a list of lowercase language ids (python, go, rust, javascript,
c, cpp, java, php, shell, ...). If a commit is unavailable, use `"unknown"`;
never invent a commit.

### Step 03: write the handoff

Fill every field in `01_repo_profile.json` from evidence. Do not add extra
keys. Do not write `supported_task_types` or `task_types`.

## GATE

```bash
python /opt/terminaltraj/scripts/target_spec.py require-handoff 01_repo_profile
python /opt/terminaltraj/scripts/target_spec.py check-profile \
  /synthesis/input/target_spec.json \
  /synthesis/state/01_repo_profile.json
```

Fix anything reported, then stop.
