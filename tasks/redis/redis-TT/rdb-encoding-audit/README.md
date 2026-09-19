# rdb-encoding-audit

Harbor task package assembled by phase 08 (assemble only).

- Candidate id: `c3`
- Package slug: `rdb-encoding-audit`
- Source repo: https://github.com/redis/redis
- Source commit: `335554f18caf7bbf6b0ac2b3548133d750f00a1b`

Provenance:

- `instruction.md` is a byte-for-byte copy of the phase 04 task (with any phase 05 review edits).
- `task.toml` is the phase 04/05 draft with package identity aligned to this directory.
- `environment/` is the sealed phase 03 base (`/synthesis/output/environment/`) merged with the phase 04 candidate overlay (`candidates/c3/environment/`); overlay files win on the same relative path.
- `tests/` is a byte-for-byte copy of the phase 06 verifier tree (with any phase 07 review edits).

This README is for humans only and is not used by the agent.
