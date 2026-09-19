---
name: redis-small-maxmemory-backlog-oom
description: "A Redis master with maxmemory 2 MiB goes permanently OOM once the 1 MiB replication backlog fills, because overhead alone exceeds the cap at zero keys"
metadata: 
  node_type: memory
  type: project
  originSessionId: e2e7d767-66ec-4f68-8c5b-d3aa2768141f
  modified: 2026-09-19T08:27:55.621Z
---

On this Redis 7.2.16 cache tier (Sep 19 2026), the master with `maxmemory 2097152` became permanently unwritable after a write burst. `MEMORY STATS` showed `startup.allocated` 866 KB + `replication.backlog` 1,045,708 B = ~1.9 MB of `overhead.total`, so `used_memory` stayed at ~2.24 MB with `dbsize=0`. `allkeys-lru` had no keys left to free, so every write returned `OOM command not allowed when used memory > 'maxmemory'`. The backlog grows to `repl-backlog-size` (default 1 MiB) and is not released while replication is attached; only a restart cleared it.

**Why:** eviction can only reclaim key data, never the replication backlog or startup allocations — so a cap set below overhead + backlog is a permanent-OOM trap rather than a cache that evicts.

**How to apply:** keep `maxmemory` comfortably above `startup.allocated` + `repl-backlog-size` + client output buffers, or lower `repl-backlog-size` to match a small cap. Reads keep working while the master is OOM, so health checks that only PING will miss it. Related: [[replica-ignore-maxmemory-divergence]].
