---
name: redis-cache-tier-maxmemory-floor
description: "The 2 MiB master / 1 MiB replica maxmemory caps on the 7.2.16 cache tier are below Redis's own overhead floor, so the tier holds no data"
metadata: 
  node_type: memory
  type: project
  originSessionId: c2df0739-b0ec-42de-b4eb-4fbed7d803e0
  modified: 2026-09-19T08:31:49.127Z
---

The cache tier at `/results/master.conf` (6379) and `/results/replica.conf` (6380) is configured
with `maxmemory 2097152` on the master and `maxmemory 1048576` on the replica. Measured on this
Redis 7.2.16 jemalloc build, those caps are below the server's fixed overhead:

- `used_memory_startup` is ~866 KB on both servers, before a single key is stored.
- `repl-backlog-size` defaults to 1 MiB and grows to full size under sustained writes; it is not
  released while a replica is attached.
- Replica steady state is ~1.10-1.13 MB, i.e. permanently above its 1 MiB cap. It evicts every
  replicated key (`dbsize` stays 0) and logs `== CRITICAL == This replica is sending an error to
  its master: -OOM ... after processing the command 'set'`.
- Master is fine fresh (~1.02 MB used, ~1 MB headroom) but after ~4000 x 256 B writes the grown
  backlog pushed it to ~2.11 MB, OOM-locking writes with an empty keyspace.

**Why:** `replica-ignore-maxmemory no` is the correct fix for the original complaint (replicas
ignoring `maxmemory` and never evicting), and it is verified working. The caps themselves, not the
eviction setting, are what makes the tier unable to retain data.

**How to apply:** Keep `replica-ignore-maxmemory no`. Do not treat empty `dbsize` on the replica as
a replication fault - check `used_memory` against `used_memory_startup` first. To make the tier
actually cache, raise the caps well above the ~866 KB baseline (8-16 MiB+) and/or lower
`repl-backlog-size`. The current values were specified explicitly by the user, so change them only
on their call.
