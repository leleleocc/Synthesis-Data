# repair-tls-decoder

Harbor task package assembled by phase 09 (assemble only).

- **candidate_id**: c6
- **package_slug**: repair-tls-decoder
- **source_repo**: https://github.com/OISF/suricata
- **source_commit**: d681600f3648030a67f7d618d30742bfd5fe7169
- **summary**: Repair TLS app-layer decoder, rebuild, and classify TLS pcap

## Provenance

| Piece | Origin |
| --- | --- |
| `instruction.md` | phases 05-06 (`candidates/c6/instruction.md`) |
| `task.toml` | phase 06 candidate, with `[task].name` aligned to slug |
| `environment/` | phase-03 sealed base (`/synthesis/output/environment`) merged with phase-05 overlay (`candidates/c6/environment/`) |
| `tests/` | phases 07-08 (`candidates/c6/tests/`) |

This README is human provenance only; it is not consumed by the Harbor agent.
