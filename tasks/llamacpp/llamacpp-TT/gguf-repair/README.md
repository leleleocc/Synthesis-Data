# gguf-repair

Harbor task package assembled by phase 08 (assemble only).

- Candidate id: c2
- Package slug: gguf-repair
- Source repo: https://github.com/ggml-org/llama.cpp
- Source commit: b29c606e28a01b1bc8c1351026a0fa6e616bf6c4

Provenance:

- `instruction.md` is a byte-for-byte copy of the phase 04 task (with any phase 05 review edits) from `candidates/c2/instruction.md`.
- `task.toml` is the phase 04/05 draft; `[task].name` matches this package directory.
- `environment/` is the sealed phase-03 base at `/synthesis/output/environment/` merged with the phase-04 overlay at `candidates/c2/environment/` (overlay wins on the same relative path).
- `tests/` is a byte-for-byte copy of the phase 06 verifier tree after any phase 07 review edits from `candidates/c2/tests/`.

This README is for humans only and is not used by the agent.
