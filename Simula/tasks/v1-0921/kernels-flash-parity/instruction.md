Flash-attn and the paged KV cache no longer produce an agreeing parity table. Kernel block sizes advertised on the flash path and the physical stride of the paged cache must line up together; a table that is green on page size while stride permutations still disagree is not agreement, and a table that is green on stride while the kernel still advertises an illegal page size is not agreement.

Drive inspection through /opt/venv/bin/vllm. Write the parity table as JSON to /workspace/kernel_parity_table.json. The file is a kernel parity table, not an HTTP report and not a cmake log. It must be a single JSON object with all of the following fields:

```json
{
  "block_size_ok": true,
  "stride_ok": true,
  "kv_cache_shape": [null, null, null, null],
  "rows": [
    {
      "block_size": 16,
      "layout_name": "LBHNC",
      "stride_order": [0, 1, 2, 3, 4],
      "parity_ok": true
    }
  ]
}
```

block_size_ok is JSON true only when the flash-attn backend advertises kernel block sizes that are MultipleOf(16), or the 128-token flash page size when that kernel is selected, and the preferred block size floors against that set. stride_ok is JSON true only when every physical KV layout reports a stride_order that is the permutation of logical axes [L, B, H, N, C] for that layout: LBHNC is [0, 1, 2, 3, 4], LBNHC is [0, 1, 3, 2, 4], LHBNC is [0, 2, 1, 3, 4], BLHNC is [1, 0, 2, 3, 4], BLNHC is [1, 0, 3, 2, 4], and BHLNC is [1, 2, 0, 3, 4]. rows must include at least block sizes 16 and 128 against each of those six layouts. For each row, block_size is a JSON integer, layout_name is the layout name as a string, stride_order is a JSON array of five integers, and parity_ok is JSON true only when that advertised page size is compatible with that layout's physical stride along the page axis.

kv_cache_shape records the packed four-integer layout [num_blocks, num_kv_heads, block_size, 2*head_size] (JSON null for extents that are not a single concrete device allocation). K and V views of that packed cache must carry block_size along the page axis. Advertised kernel block sizes must be compatible with the physical stride of the paged cache. Both block_size_ok and stride_ok must be true, and every row must have parity_ok true. Do not download packages or hints from the network.

You have 1800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
