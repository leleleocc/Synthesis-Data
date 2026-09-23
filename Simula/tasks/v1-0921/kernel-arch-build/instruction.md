The cache-kernel compile matrix in this image does not produce a library that can load on the host GPU. `TORCH_CUDA_ARCH_LIST` currently compiles cache kernels for a non-host architecture; loading that binary illegal-instructs on the card that is actually attached. At the same time, cooperative top-k is being compiled for every arch in the list: `nvcc` fails on sm75/sm80 because that source is only valid on the sm90+/sm100+/sm120 intersection. A gather built from this matrix also accepts MLA `head_dim` values outside `{320, 576}`.

Operating constraint: the environment variable `TORCH_CUDA_ARCH_LIST` selects gencode. Cooperative top-k must stay gated on the sm90+/sm100+/sm120 intersection used by CMake (`9.0a` / `10.0f` / `12.0f` families on CUDA 13, `9.0a` / `10.0a` / `12.0a` families on CUDA 12). Enabling it unconditionally for sm75/80 fails nvcc. Compiling `cache_kernels.cu` and `cache_kernels_fused.cu` only for a non-host arch loads then illegal-instruction.

Inspect `/workspace/symptoms.log` and run `/bin/bash /workspace/repro_arch.sh`.

Produce all of the following. Compiling for the host arch without keeping cooperative top-k gated is failure. Gating cooperative top-k while still emitting a non-host-only cache kernel is failure. The gather op must still reject `head_dim` outside `{320, 576}`.

1. `/workspace/cache_kernels.so` — a shared object containing the gather op compiled for the host GPU architecture taken from `TORCH_CUDA_ARCH_LIST` (the arch list you settle on must include the real host arch, not only a non-host arch).
2. `/workspace/gather_head_dim_reject.txt` — the rejection message from invoking gather with `head_dim=128` (the text must mention 320 or 576).
3. `/workspace/arch_matrix.json` with exactly:

```json
{
  "torch_cuda_arch_list": "<the list used to build>",
  "host_arch": "<host sm, e.g. 8.0>",
  "cache_kernels_archs": ["<arch>", "..."],
  "cooperative_topk_enabled": false,
  "gather_rejects_head_dim_128": true
}
```

`cooperative_topk_enabled` must be false unless the host arch actually intersects sm90+/sm100+/sm120. `cache_kernels_archs` must include `host_arch`.

Work in `/workspace/repo`. Do not modify `/opt/venv`. Do not use the network.

You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
