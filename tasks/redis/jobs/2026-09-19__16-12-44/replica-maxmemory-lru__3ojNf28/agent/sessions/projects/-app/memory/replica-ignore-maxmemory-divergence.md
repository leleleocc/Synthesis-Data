---
name: replica-ignore-maxmemory-divergence
description: "Setting replica-ignore-maxmemory no makes a Redis replica reject the master's writes (silent divergence) rather than evict, when maxmemory is near baseline overhead"
metadata: 
  node_type: memory
  type: project
  originSessionId: e2e7d767-66ec-4f68-8c5b-d3aa2768141f
  modified: 2026-09-19T08:27:46.089Z
---

In the cache-tier work on this Redis 7.2.16 checkout (Sep 19 2026), `replica-ignore-maxmemory no` with `maxmemory 1048576` on the replica does NOT produce graceful replica-side eviction. The replica's own `startup.allocated` is ~866 KB (~83% of a 1 MiB cap), so with the replication client buffer it exceeds `maxmemory` at **zero keys**. `allkeys-lru` then has nothing to evict, eviction fails, and the replica answers its master with `-OOM command not allowed when used memory > 'maxmemory'`, logged as `== CRITICAL == This replica is sending an error to its master`.

Observed result: master `dbsize=1202` vs replica `dbsize=0` while `master_link_status` stayed `up` — divergence invisible to link-status monitoring. This is why upstream defaults `replica-ignore-maxmemory` to `yes`.

**Why:** the goal was to stop replicas from ignoring `maxmemory`, but at caps near baseline overhead the setting converts a RAM-overrun problem into a silent data-consistency problem.

**How to apply:** when enabling `replica-ignore-maxmemory no`, size replica `maxmemory` well above `startup.allocated` + `repl-backlog-size` + client buffers (check `MEMORY STATS`), and alert on master/replica `dbsize` divergence, not just link status. Related: [[redis-small-maxmemory-backlog-oom]].
