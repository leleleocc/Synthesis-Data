After a tensor-parallel rank loss, the engine snapshot no longer keeps failover KV pages aligned with demoted ranks. Pages still recorded against a rank that is gone sit beside empty failover slots, and the tensor-parallel group size still describes the pre-failure grid, so the cache map and the process group no longer agree.

Restore engine state so KV-cache failover and tensor-parallel rank demotion hold together. Moving pages onto remaining ranks while leaving the tensor-parallel group at its pre-failure size is not recovery. Shrinking the group while leaving pages owned by the failed rank is not recovery. After demotion the remaining ranks must own a consistent KV page map: no pages stuck on the failed rank, and demoted world_size must match the surviving tensor-parallel size.

Write the restored snapshot as JSON to /workspace/engine_state_snapshot.json. Drive inspection and any engine-side recovery through /opt/venv/bin/vllm. The object must contain all of the following fields:

```json
{
  "kv_cache_failover_ok": true,
  "tp_rank_demotion_ok": true,
  "ranks": [0],
  "kv_pages_by_rank": {"0": [0]},
  "world_size": 1,
  "tensor_parallel_size": 1
}
```

kv_cache_failover_ok is true only when every live KV page maps to a rank in ranks and no page remains owned by the failed rank. tp_rank_demotion_ok is true only when ranks is exactly the surviving tensor-parallel set, tensor_parallel_size equals the length of ranks, and world_size equals that demoted size. ranks is a JSON array of integer rank ids. kv_pages_by_rank is an object whose keys are those rank ids as strings and whose values are arrays of integer page ids covering every live page. The two booleans are not sufficient on their own: a verifier will check the page map and the demoted grid, not a single flag. Do not download packages or hints from the network.

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
