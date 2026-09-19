---
name: suricata-c-oracle-technique
description: How to compile real Suricata sources standalone as a C oracle without touching /app
metadata: 
  node_type: memory
  type: reference
  originSessionId: 0ec16fae-f781-4c83-b329-868ac40a015d
  modified: 2026-09-19T14:22:25.484Z
---

To differentially test a port of Suricata logic, compile the *real* `/app/src` sources against stub
headers in a scratch dir: **copy the .c/.h under test into the shim dir**, because quoted `#include`s
resolve relative to the including file first, so `-I/shim` alone cannot override `/app/src/suricata-common.h`
(which pulls in the generated `autoconf.h`). Needed stubs: SCMalloc/SCFree, no-op SCLog*/DEBUG_VALIDATE_BUG_ON,
`SCError` enum with `SC_EEXIST`, `sc_errno`, plus verbatim `MaskIPNetblock`. Then assert the oracle
reproduces the expectations baked into Suricata's own `#ifdef UNITTESTS` cases before trusting it.

**Why:** the radix-tree and byte-order semantics (longest-prefix match, `%08x` of a network-order word)
are easy to get subtly wrong by reading alone, and the unit tests are a free ground truth.

**How to apply:** use for any future port of Suricata internals; see [[ospolicy-helper-tool]].
