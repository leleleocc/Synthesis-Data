---
name: ospolicy-helper-tool
description: Standalone /results/ospolicy tool mirrors Suricata host-OS-policy + CIDR helpers; kept for reuse
metadata: 
  node_type: memory
  type: project
  originSessionId: 0ec16fae-f781-4c83-b329-868ac40a015d
  modified: 2026-09-19T14:22:17.330Z
---

`/results/ospolicy` (Python 3, mode 0755) is a standalone port of `/app/src/util-cidr.c` and
`/app/src/util-host-os-info.c`, built 2025-09-19 so a config hand-off can resolve host-OS policy for
an address without running the Suricata engine. Subcommands: `cidr ipv4-mask|ipv4-prefix|ipv6-prefix`
and `load <yaml>` (IPs on stdin, prints `<ip> <flavour>`). Policy fixture: `/data/host-os-policy.yaml`.
It is meant to stay in place and be invoked on further addresses.

**Why:** it lives outside the repo (nothing under `/app` may be modified), so neither the tool nor its
rationale is recoverable from git history.

**How to apply:** reuse it instead of re-porting the C; re-validate changes against the differential
harness approach in [[suricata-c-oracle-technique]].
