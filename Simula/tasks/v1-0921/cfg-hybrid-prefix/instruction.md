Hybrid prefix-cache runtime settings will not hold. A full-attention group (block size 16) plus a Mamba group (block size 32) is supposed to come up only when the prefix match unit divides every prefix-cacheable group's block size and the KV layout is block-compact under mixed HNC. Right now a `prefix_match_unit` of 24 is accepted, `LHBNC` is accepted for mixed HNC, and the legacy names `NHD` / `HND` no longer resolve to `LBNHC` / `LBHNC`. `HybridKVCacheCoordinator` must not construct until hash granularity and layout are jointly valid.

Reproduce with `/opt/venv/bin/python3 /workspace/repro_hybrid_cfg.py`. Captured output is in `/workspace/symptoms.log`. Operators expected `Invalid prefix_match_unit` when 24 is paired with group sizes `[16, 32]`, and `Specs with mixed HNC shapes need a block-compact layout` when `LHBNC` is requested for mixed HNC. Those errors are currently missing; `NHD` is reported as an unknown layout.

Restore configuration so both constraints hold. `prefix_match_unit` must divide every prefix-cacheable group's block size (unit 24 against `[16, 32]` is illegal because 16 is not divisible by 24). A non-compact layout with mixed HNC is failure. Hash granularity and layout must be jointly valid before the coordinator can construct.

Write `/workspace/hybrid_cache_config.json` with exactly:

```json
{
  "illegal_unit": {
    "prefix_match_unit": 24,
    "group_block_sizes": [16, 32],
    "raised": true,
    "error_contains": "prefix_match_unit"
  },
  "illegal_layout": {
    "requested_layout": "LHBNC",
    "mixed_hnc": true,
    "raised": true,
    "error_contains": "block-compact"
  },
  "aliases": {
    "NHD": "LBNHC",
    "HND": "LBHNC"
  },
  "legal": {
    "prefix_match_unit": 16,
    "group_block_sizes": [16, 32],
    "scheduler_block_size": 32,
    "hash_block_size": 16,
    "layout": "LBNHC",
    "coordinator_constructs": true
  }
}
```

Illegal unit 24 against groups `[16, 32]` must raise a message containing `prefix_match_unit`. Mixed-HNC plus `LHBNC` must raise a message containing `block-compact`. `NHD` must alias to `LBNHC` and `HND` to `LBHNC`. The legal combo (unit 16, groups 16 and 32, layout `LBNHC`) must resolve `scheduler_block_size` 32, `hash_block_size` 16, and allow `HybridKVCacheCoordinator` to construct (`coordinator_constructs` true).

Work in `/workspace/repo`. Do not modify `/opt/venv`. Do not use the network.

You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
