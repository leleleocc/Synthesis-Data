A prior prefix-cache reset invariant is gone. Operators issued a reset while requests still held KV pages; the call reported success, the hash map was wiped, and in-flight pages were treated as reusable. After every holder was later freed, a second reset still left hashed blocks, so a follow-up request with the same prefix hit stale pages instead of missing.

Reproduce with `/opt/venv/bin/python3 /workspace/repro_cache_reset.py`. Captured output is in `/workspace/symptoms.log`:

```
holders live: reset_prefix_cache returned True
  inflight block_ids=[2, 4] ref_cnt=[1, 1]
  hash map emptied while holders still own pages
after free: reset_prefix_cache returned True
  block.block_hash still set on previously cached pages
post-reset shared prefix: get_computed_blocks hit_tokens=8 (stale pages reused)
```

Restore the invariant so both of the following hold. Succeeding while any non-null block still has nonzero `ref_cnt` is failure. Clearing only the hash map and leaving `block.block_hash` set is failure.

Write `/workspace/cache_reset_report.json` with exactly this JSON object:

```json
{
  "while_holders": {
    "reset_returned": false,
    "hash_map_still_populated": true,
    "inflight_block_ids": [<int>, ...],
    "inflight_refcnts": [<int>, ...]
  },
  "after_free": {
    "reset_returned": true,
    "hash_map_empty": true,
    "all_block_hashes_null": true
  },
  "post_reset_shared_prefix": {
    "get_computed_blocks_hit_tokens": 0,
    "allocate_reused_stale_pages": false
  }
}
```

While any non-null block has `ref_cnt` nonzero, `reset_prefix_cache` must return false, must keep `cached_block_hash_to_block` populated, and must leave the recorded in-flight block ids and refcounts unchanged. After every holder is freed, the reset must return true, the hash map must be empty, every `block.block_hash` must be null, and a subsequent shared-prefix `get_computed_blocks` must report 0 hit tokens (allocate must not reuse stale pages).

Use block size 4, tokens `[3, 3, 3, 3, 5, 5, 5, 5]`, and `/workspace/repo`. Do not modify `/opt/venv`. Do not use the network.

You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
