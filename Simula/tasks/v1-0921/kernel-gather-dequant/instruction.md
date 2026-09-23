Paged MLA KV gather in this image does not produce a usable dense cache. When `seq_starts` is nonzero, destination rows come from the wrong pages (the gather behaves as if every sequence began at page 0). When the paged cache is fp8 and the destination is fp16 or bf16, the dest holds raw stored bits rather than values dequantized with the supplied scale. Only MLA entry sizes 320 and 576 are legal.

Fixtures are already on disk:

- `/workspace/fixtures/src_cache_fp16.pt` — `[12, 16, 576]` float16 pages
- `/workspace/fixtures/src_cache_bf16_320.pt` — `[12, 16, 320]` bfloat16 pages
- `/workspace/fixtures/src_cache_fp8.pt` — `[12, 16, 576]` uint8 fp8 pages
- `/workspace/fixtures/block_table.pt` — int32 `[[8, 9, 10, 11]]`
- `/workspace/fixtures/cu_seq_lens.pt` — int32 `[0, 16]`
- `/workspace/fixtures/seq_starts.pt` — int32 `[128]` so the first logical page is `128 / 16 = 8`
- `/workspace/fixtures/scale.pt` — float32 `[2.0]`
- `/workspace/fixtures/token_to_seq.pt` — unused placeholder

Reproduce with `/workspace/repro_gather.py`. Captured symptoms are in `/workspace/symptoms.log` (wrong dest rows, fp8 bits in the fp16 dest).

Write `/workspace/gathered_cache.pt` via `torch.save` of a dict with exactly these keys:

- `fp16_seq_offset`: CPU tensor `[16, 576]` float16, gather of `/workspace/fixtures/src_cache_fp16.pt` using the fixtures above (`kv_cache_dtype` auto / fp16). The compact table `[[8, 9, 10, 11]]` maps logical pages 8–11 onto those physical pages; destination rows must honor `seq_starts`, not physical page 0.
- `bf16_entry320`: CPU tensor `[16, 320]` bfloat16 from `/workspace/fixtures/src_cache_bf16_320.pt` with the same table / starts (auto copy, entry 320).
- `fp8_dequant_fp16`: CPU tensor `[16, 576]` float16 from `/workspace/fixtures/src_cache_fp8.pt` using scale `2.0` (stored bits are `float8_e4m3fn`).
- `fp8_dequant_bf16`: CPU tensor `[16, 576]` bfloat16 from the same fp8 cache and scale.
- `rejected_head_dim`: a string containing `320` or `576`.

Padding the table without applying `seq_starts` copies physical page 0 and fails. Skipping dequant leaves raw stored bits in the fp16 dest and fails.

Work in `/workspace/repo`. Do not use the network.

You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
