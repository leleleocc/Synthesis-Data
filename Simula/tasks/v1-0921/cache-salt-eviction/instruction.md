The vLLM runtime in this image is serving prefix-cached generation, but tenant isolation on KV pages is not holding. Two clients that submit the identical token prefix with different cache salts still report a prefix-cache hit against each other. Two LoRA adapters with the same tokens also land on the same physical pages. Separately, when a request whose prefix is already computed cannot obtain enough free pages for its unique tail, `allocate_slots` returns no new slots and the computed prefix pages do not keep the block ids and reference counts they had before the failed admission.

Reproduce the live symptoms with `/opt/venv/bin/python3 /workspace/repro_prefix_hits.py`. A captured run is in `/workspace/symptoms.log`:

```
salt isolation: tenantA first_block_hash == tenantB first_block_hash
  saltA='alpha' saltB='bravo' tokens=[7, 7, 7, 7, 9, 9, 9, 9]
lora isolation: adapterX first_block_hash == adapterY first_block_hash
  loraX='sql-adapter' loraY='chat-adapter'
allocate_slots under pressure: result=None
  computed prefix block_ids before=[3, 5] after=[3, 5]
  computed prefix ref_cnt before=[2, 2] after=[3, 3]
```

Restore the running system so both of the following hold together. Isolation without allocation protection is not enough; protecting computed pages without salt and LoRA isolation is not enough.

Write `/workspace/prefix_hit_table.json` with exactly this JSON object (no extra top-level keys):

```json
{
  "hash_isolation": [
    {"tokens": [7, 7, 7, 7, 9, 9, 9, 9], "cache_salt": "alpha", "lora_name": null, "first_block_hash_hex": "<hex>", "n_full_blocks": 2},
    {"tokens": [7, 7, 7, 7, 9, 9, 9, 9], "cache_salt": "bravo", "lora_name": null, "first_block_hash_hex": "<hex>", "n_full_blocks": 2},
    {"tokens": [7, 7, 7, 7, 9, 9, 9, 9], "cache_salt": null, "lora_name": "sql-adapter", "first_block_hash_hex": "<hex>", "n_full_blocks": 2},
    {"tokens": [7, 7, 7, 7, 9, 9, 9, 9], "cache_salt": null, "lora_name": "chat-adapter", "first_block_hash_hex": "<hex>", "n_full_blocks": 2},
    {"tokens": [7, 7, 7, 7, 9, 9, 9, 9], "cache_salt": "alpha", "lora_name": "sql-adapter", "first_block_hash_hex": "<hex>", "n_full_blocks": 2}
  ],
  "cross_hits": [
    {"a": 0, "b": 1, "same_first_block_hash": false},
    {"a": 2, "b": 3, "same_first_block_hash": false},
    {"a": 0, "b": 4, "same_first_block_hash": false}
  ],
  "allocation_pressure": {
    "computed_prefix_block_ids_before": [<int>, ...],
    "computed_prefix_refcnts_before": [<int>, ...],
    "allocate_slots_result": null,
    "computed_prefix_block_ids_after": [<int>, ...],
    "computed_prefix_refcnts_after": [<int>, ...]
  }
}
```

Hash isolation: rows that differ only in `cache_salt` must have different `first_block_hash_hex`. Rows that differ only in `lora_name` must have different `first_block_hash_hex`. A request that combines salt `alpha` with LoRA `sql-adapter` must not share the first-block hash of salt-only `alpha`. Two requests with the same tokens, same salt, and same LoRA name must match. Salt participates only on the first full block of a request (later full blocks do not re-attach salt as a per-block tenant id); isolation still holds because the first digest differs. Use block size 4 and the `sha256` prefix-cache hash.

Allocation pressure: after a prefix of two full blocks is cached, admit a follow-up request that shares that prefix and needs additional unique-tail pages that cannot fit. `allocate_slots` must yield no new slots (`allocate_slots_result` JSON `null`). `computed_prefix_block_ids_after` must equal `computed_prefix_block_ids_before`, and `computed_prefix_refcnts_after` must equal `computed_prefix_refcnts_before`.

Work in `/workspace/repo`. Do not use the network.

You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
