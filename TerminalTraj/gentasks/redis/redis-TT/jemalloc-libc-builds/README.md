# jemalloc-libc-builds

Harbor task package assembled by phase 08 (assemble only).

- Candidate id: `c6`
- Package slug: `jemalloc-libc-builds`
- Source repo: https://github.com/redis/redis
- Source commit: `335554f18caf7bbf6b0ac2b3548133d750f00a1b`

Provenance:

- `instruction.md` is the phase 04 task text after phase 05 review edits.
- `tests/` is the phase 06 verifier tree after phase 07 review edits.
- `environment/` is the sealed phase 03 base at `/synthesis/output/environment/` merged with the phase 04 overlay at `candidates/c6/environment/` (overlay wins on the same relative path).
- `task.toml` is the phase 04/05 draft with `[task].name` aligned to this package directory.

This README is for humans only and is not used by the agent.
