# dns-name-decode

Harbor task packaged from synthesis candidate `c3`.

- Candidate id: c3
- Package slug: dns-name-decode
- Source repo: https://github.com/OISF/suricata
- Source commit: d681600f3648030a67f7d618d30742bfd5fe7169

Provenance:

- Environment is the phase-03 sealed base (`/synthesis/output/environment/`) merged with the phase-04 candidate overlay (`candidates/c3/environment/`). Overlay files win on the same relative path.
- Instruction is the phase-04/05 candidate `instruction.md` (byte-for-byte).
- Tests are the phase-06/07 candidate `tests/` tree (byte-for-byte).
- `task.toml` is the phase-04/05 draft with `[task].name` aligned to `terminaltraj/dns-name-decode` and optional `candidate_id` / `package_slug` metadata.

This README is for humans only and is not used by the agent.
